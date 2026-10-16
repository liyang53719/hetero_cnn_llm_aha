"""Bounded exact M1/M2 checks only; no RTL or physical timing evidence."""
from collections import Counter
import unittest
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch
from . import check_sources
from .controller import Controller, NumericalFault, TileView
from ..attention_scheduled_numeric.controller import Controller as Scheduled, Timing
from ..attention_scheduled_numeric.ports import ScalarPort
from ..attention_matrix_batch.test_model import (
    ExactScalar, OriginalSchedule, exp_negative, fixture, ref_fma)


class RetainedResultTests(unittest.TestCase):
    def make_controller(self, cls=Controller):
        scalar = ExactScalar(object())
        return cls(scalar, ref_fma, lambda a: exp_negative(scalar, scalar.client, a),
                   timing=Timing(2, 3, 1, 2))

    def assert_drained_failure(self, controller):
        self.assertTrue(controller.failed)
        self.assertFalse(controller.finished)
        self.assertFalse(controller.ordinary_owner_ready())
        self.assertIsNone(controller.port)
        self.assertIsNone(controller.slot)
        self.assertTrue(controller.ack_events[-1][2])
        for view in controller.views:
            with self.assertRaises(ValueError):
                view[0]

    def test_m1_m2_exact_oracles_counts_and_live_payload(self):
        test = self
        class Observed(Controller):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.payloads, self.masks, self.fold_ops = {}, {}, Counter()
            def matrix_group(self, *args):
                view = super().matrix_group(*args)
                test.assertIsInstance(view, TileView)
                test.assertFalse(hasattr(view, 'words'))
                port = self.slot['port']
                self.payloads[port.group] = port.held
                self.masks[port.group] = self.slot['mask']
                return view
            def read_result(self, group, index):
                if self.slot is None:
                    return super().read_result(group, index)
                port = self.slot['port']
                test.assertIs(port.held, self.payloads[group])
                result = super().read_result(group, index)
                test.assertEqual(result, port.held.words[index])
                return result
            def retire_slot(self, *, poison=False):
                port = self.slot['port']
                test.assertIs(port.held, self.payloads[port.group])
                test.assertEqual(self.invariant(), dict(occupied=1, available=1))
                test.assertEqual(self.slot['seen'], self.slot['selected'])
                super().retire_slot(poison=poison)
                test.assertTrue(port.retired)
                test.assertIsNone(port.held)
                test.assertIsNone(port.pending)
                with test.assertRaises(ValueError):
                    self.views[-1][0]
        for tokens, reads in ((1, 1728), (2, 3648)):
            with self.subTest(tokens=tokens):
                scalar = ExactScalar(object())
                def operation(op, a, b):
                    self.assertFalse(controller.ordinary_owner_ready())
                    if isinstance(controller.port, ScalarPort) and controller.slot is not None:
                        port = controller.slot['port']
                        self.assertEqual(controller.slot['mask'], 255)
                        self.assertIs(port.held, controller.payloads[port.group])
                        self.assertFalse(port.retired)
                        controller.fold_ops[op] += 1
                    return scalar(op, a, b)
                controller = Observed(operation, ref_fma,
                    lambda a: exp_negative(scalar, scalar.client, a), timing=Timing(2, 3, 1, 2))
                data = fixture(tokens)
                original = OriginalSchedule(tokens, *data)
                expected = original.run()
                previous = self.make_controller(Scheduled).run(tokens, *data)
                result = controller.run(tokens, *data)
                self.assertEqual(result.output, expected)
                self.assertEqual(result.scores, original.scores()[1])
                self.assertEqual((result.output, result.scores), (previous.output, previous.scores))
                counts, old_counts = dict(result.counts), dict(previous.counts)
                for key, value in old_counts.items():
                    self.assertEqual(counts[key], value, key)
                self.assertEqual(counts['joined_result_word_reads'], reads)
                self.assertEqual(len(controller.read_events), reads)
                self.assertEqual(counts['matrix_result_acks'], 14*tokens)
                self.assertEqual(len(controller.ack_events), 14*tokens)
                self.assertFalse(any(poison for _, _, poison in controller.ack_events))
                self.assertEqual(controller.peak_slots, 1)
                self.assertEqual(controller.invariant(), dict(occupied=0, available=2))
                self.assertIsNone(controller.port)
                self.assertTrue(controller.ordinary_owner_ready())
                pairs = 6*tokens*(tokens+1)
                self.assertEqual(controller.fold_ops, Counter(add=16*pairs, mul=pairs, bf=2*pairs))
                rates = Counter((edge, group) for edge, group, _ in controller.read_events)
                for (_, group), rate in rates.items():
                    self.assertLessEqual(rate, 16 if controller.masks[group] == 255 else 1)
                ack_times = {group: edge for edge, group, _ in controller.ack_events}
                for edge, group, _ in controller.read_events:
                    self.assertLessEqual(edge, ack_times[group])
                for group, mask in controller.masks.items():
                    if mask == 15:
                        self.assertEqual(max(e for e,g,_ in controller.read_events if g == group), ack_times[group])
                self.assertGreater(counts['retained_result_hold_edges'], 0)

    def test_early_retirement_second_group_and_expired_view_rejected(self):
        controller = self.make_controller()
        payloads = (((0,)*16, (0,)*256),)
        view = controller.matrix_group(payloads, ((0, 0), (0, 1)), 255)
        port, held = controller.slot['port'], controller.slot['port'].held
        with self.assertRaisesRegex(ValueError, 'incompletely'):
            controller.retire_slot()
        with self.assertRaisesRegex(ValueError, 'contention'):
            controller.matrix_group(payloads, ((0, 0),), 255)
        self.assertEqual(controller.counts['matrix_groups'], 1)
        self.assertFalse(controller.ordinary_owner_ready())
        with self.assertRaises(ValueError):
            view[2]
        for _ in range(5):
            controller.hold_edge()
            self.assertIs(port.held, held)
            self.assertIs(port.held.words, held.words)
        self.assertEqual(view[0], 0)
        with self.assertRaisesRegex(ValueError, 'incompletely'):
            controller.retire_slot()
        self.assertEqual(view[1], 0)
        controller.retire_slot()
        self.assertFalse(controller.ack_events[-1][2])
        with self.assertRaisesRegex(ValueError, 'stale'):
            view[0]
        self.assertTrue(controller.ordinary_owner_ready())

    def test_qk_selector_bandwidth_is_enforced(self):
        controller = self.make_controller()
        view = controller.matrix_group((((0,)*16, (0,)*256),), ((0, 0),), 255)
        for _ in range(16):
            self.assertEqual(view[0], 0)
        with self.assertRaisesRegex(ValueError, 'bandwidth'):
            view[0]
        controller.retire_slot()

    def test_first_and_last_pv_output_bf_faults_drain_retained_slot(self):
        for fail_at in (13, 1560):
            with self.subTest(boundary_conversion=fail_at):
                scalar, observed = ExactScalar(object()), []
                class Faulty(Controller):
                    def bf(self, value):
                        self.inject = self.counts['boundary_bf16_conversions']+1 == fail_at
                        try:
                            return super().bf(value)
                        finally:
                            self.inject = False
                def operation(op, a, b):
                    if op == 'bf' and getattr(controller, 'inject', False):
                        self.assertIsNotNone(controller.slot)
                        self.assertEqual(controller.slot['mask'], 15)
                        observed.append(controller.slot['port'])
                        self.assertFalse(observed[-1].retired)
                        return 0x7f800000
                    return scalar(op, a, b)
                controller = Faulty(operation, ref_fma,
                    lambda a: exp_negative(scalar, scalar.client, a), timing=Timing(1, 3, 0, 0))
                with self.assertRaisesRegex(NumericalFault, 'boundary'):
                    controller.run(1, *fixture(1))
                self.assert_drained_failure(controller)
                self.assertEqual(len(observed), 1)
                self.assertTrue(observed[0].retired)
                self.assertIsNone(observed[0].held)
                self.assertEqual(controller.counts['matrix_result_acks'], 7 if fail_at == 13 else 14)

    def test_scalar_fold_callback_failure_drains_both_ports(self):
        scalar, captured = ExactScalar(object()), []
        def operation(op, a, b):
            if op == 'add':
                self.assertIsNotNone(controller.slot)
                self.assertIsInstance(controller.port, ScalarPort)
                captured.append((controller.slot['port'], controller.port))
                raise ArithmeticError('injected scalar fold failure')
            return scalar(op, a, b)
        controller = Controller(operation, ref_fma,
            lambda a: exp_negative(scalar, scalar.client, a), timing=Timing(2, 3, 1, 2))
        with self.assertRaisesRegex(NumericalFault, 'scalar failed'):
            controller.run(1, *fixture(1))
        self.assert_drained_failure(controller)
        self.assertEqual(len(captured), 1)
        matrix, scalar_port = captured[0]
        self.assertTrue(matrix.retired)
        self.assertIsNone(matrix.held)
        self.assertIsNone(scalar_port.schedule.pending)
        self.assertIsNone(scalar_port.held)
        self.assertEqual(controller.counts['matrix_result_acks'], 1)
        self.assertEqual(controller.counts['scalar_packets'], 1)
        self.assertEqual(controller.counts['scalar_packet_acks'], 1)

    def test_final_qk_score_conversion_failure_drains_held_slot(self):
        scalar, observed = ExactScalar(object()), []
        conversions = 0
        def operation(op, a, b):
            nonlocal conversions
            if op == 'bf' and controller.slot is not None:
                conversions += 1
                if conversions == 2:
                    self.assertEqual(controller.slot['mask'], 255)
                    observed.append(controller.slot['port'])
                    self.assertFalse(observed[-1].retired)
                    return 0x7f800000
            return scalar(op, a, b)
        controller = Controller(operation, ref_fma,
            lambda a: exp_negative(scalar, scalar.client, a), timing=Timing(2, 3, 1, 2))
        with self.assertRaises(NumericalFault):
            controller.run(1, *fixture(1))
        self.assert_drained_failure(controller)
        self.assertEqual(len(observed), 1)
        self.assertTrue(observed[0].retired)
        self.assertIsNone(observed[0].held)

    def test_actual_fifo_source_drift_fails_closed(self):
        self.assertEqual(check_sources.check()['status'], 'PASS_SOURCE_ONLY')
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            for relative in (*check_sources.SOURCES, *check_sources.OWN):
                target = root/relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(check_sources.ROOT/relative, target)
            fifo = root/'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/MatrixPipeline.scala'
            fifo.write_text(fifo.read_text().replace('Reg(Vec(2,new MatrixStreamResult))',
                'Reg(Vec(3,new MatrixStreamResult))'))
            with patch.object(check_sources, 'ROOT', root):
                with self.assertRaisesRegex(ValueError, 'source drift'):
                    check_sources.check()

    def test_matrix_arithmetic_failure_drains_and_blocks_admission(self):
        scalar = ExactScalar(object())
        controller = Controller(scalar, lambda a, b, c: 0x7f800000,
            lambda a: exp_negative(scalar, scalar.client, a), timing=Timing(2, 3, 1, 1))
        with self.assertRaisesRegex(NumericalFault, 'Matrix failed'):
            controller.run(1, *fixture(1))
        self.assert_drained_failure(controller)
        self.assertEqual(controller.counts['matrix_result_acks'], 1)
        self.assertEqual(controller.counts['scalar_packets'], 0)


if __name__ == '__main__':
    unittest.main()
