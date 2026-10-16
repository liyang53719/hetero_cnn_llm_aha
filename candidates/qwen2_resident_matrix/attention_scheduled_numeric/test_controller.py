"""Selected-cell finite equivalence with hypothetical timing; no storage/RTL proof."""
import unittest
from .controller import Controller, Timing, NumericalFault
from ..attention_matrix_batch.test_model import (
    ExactScalar, OriginalSchedule, batched_attention, exp_negative, fixture, ref_fma)


class ControllerTests(unittest.TestCase):
    def run_checked(self, tokens, data, timing):
        scalar = ExactScalar(object())
        observations = []
        def operation(op, a, b):
            observations.append(controller.ordinary_owner_ready())
            return scalar(op, a, b)
        def fma(a, b, c):
            observations.append(controller.ordinary_owner_ready())
            self.assertIsNotNone(controller.port)
            return ref_fma(a, b, c)
        def exponential(a):
            observations.append(controller.ordinary_owner_ready())
            self.assertIsNotNone(controller.port)
            return exp_negative(scalar, scalar.client, a)
        controller = Controller(operation, fma, exponential, timing=timing)
        self.assertTrue(controller.ordinary_owner_ready())
        result = controller.run(tokens, *data)
        self.assertTrue(observations)
        self.assertFalse(any(observations), 'contender became ready during accepted arithmetic')
        self.assertTrue(controller.ordinary_owner_ready())
        self.assertIsNone(controller.port)
        with self.assertRaises(ValueError):
            controller.run(tokens, *data)
        return result

    def test_m1_m2_stalled_words_match_actual_source_and_batch(self):
        for m in (1, 2):
            with self.subTest(tokens=m):
                data = fixture(m)
                original = OriginalSchedule(m, *data)
                expected = original.run()
                batch_output, batch_scores, _ = batched_attention(m, *data)
                result = self.run_checked(m, data, Timing(3, 7, 2, 3))
                self.assertEqual(result.output, expected)
                self.assertEqual(result.output, batch_output)
                self.assertEqual(result.scores, original.scores()[1])
                self.assertEqual(result.scores, batch_scores)
                counts = dict(result.counts)
                pairs = 6*m*(m+1)
                steps = 96*m + m*(m+1)
                self.assertEqual(counts['matrix_groups'], 14*m)
                self.assertEqual(counts['matrix_result_acks'], 14*m)
                self.assertEqual(counts['matrix_steps'], steps)
                self.assertEqual(counts['matrix_returns'], steps)
                self.assertEqual(counts['selected_fmas'], 256*pairs)
                self.assertEqual(counts['ingress_bf16_conversions'], 272*steps)
                self.assertEqual(counts['scalar_packets'], 206*m+4*m*(m+1))
                self.assertEqual(counts['scalar_packet_acks'], counts['scalar_packets'])
                self.assertEqual(counts['scheduled_scalar_lane_calls'], 21*pairs+12*m)
                self.assertEqual(counts['vector16_add'], 16*pairs)
                self.assertEqual(counts['vector16_mul'], pairs)
                self.assertEqual(counts['sfu16_add'], 2*pairs)
                self.assertEqual(counts['sfu16_exp'], pairs)
                self.assertEqual(counts['sfu16_div'], 12*m)
                self.assertEqual(counts['sfu16_mul'], pairs)
                self.assertEqual(counts['exp_internal_fp32_nodes'], 17*pairs)
                self.assertEqual(counts['scheduled_fp32_primitive_nodes'], 37*pairs+12*m)

    def test_hypothetical_latency_and_stalls_change_ticks_not_words_or_calls(self):
        data = fixture(2, seed=314159)
        baseline = self.run_checked(2, data, Timing(1, 3, 0, 0))
        latency = self.run_checked(2, data, Timing(6, 11, 0, 0))
        stalled = self.run_checked(2, data, Timing(6, 11, 2, 4))
        for result in (latency, stalled):
            self.assertEqual(result.output, baseline.output)
            self.assertEqual(result.scores, baseline.scores)
            self.assertEqual(result.counts, baseline.counts)
        self.assertLess(baseline.hypothetical_ticks, latency.hypothetical_ticks)
        self.assertLess(latency.hypothetical_ticks, stalled.hypothetical_ticks)

    def test_boundary_and_final_output_conversion_faults_block_contenders(self):
        # Six QK heads consume twelve boundary conversions before the first PV
        # output conversion. Ingress conversions are separate callbacks.
        for fail_at in (1, 13):
            with self.subTest(boundary_conversion=fail_at):
                scalar = ExactScalar(object())
                class FailingBoundary(Controller):
                    def bf(self, value):
                        self.inject_boundary_fault = self.counts['boundary_bf16_conversions'] + 1 == fail_at
                        try:
                            return super().bf(value)
                        finally:
                            self.inject_boundary_fault = False
                def operation(op, a, b):
                    if op == 'bf' and getattr(controller, 'inject_boundary_fault', False):
                        return 0x7f800000
                    return scalar(op, a, b)
                controller = FailingBoundary(operation, ref_fma,
                    lambda a: exp_negative(scalar, scalar.client, a),
                    timing=Timing(2, 3, 1, 1))
                with self.assertRaisesRegex(NumericalFault, 'boundary'):
                    controller.run(1, *fixture(1))
                self.assertTrue(controller.failed)
                self.assertFalse(controller.finished)
                self.assertFalse(controller.ordinary_owner_ready())
                self.assertEqual(controller.counts['boundary_bf16_conversions'], fail_at)
                self.assertEqual(controller.counts['matrix_result_acks'], 1 if fail_at == 1 else 7)

    def test_source_closure_and_actual_original_helper_mutation(self):
        import shutil
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from . import check_sources as c
        self.assertEqual(c.check()['sources'], 28)
        helper = 'candidates/qwen2_resident_matrix/ffn_public/prefix_owners.py'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in (*c.SOURCES, *c.OWN, c.PREFIX+'pins.json'):
                target = root/name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(c.ROOT/name, target)
            with patch.object(c, 'ROOT', root), patch.object(c, 'HERE', root/c.PREFIX):
                self.assertEqual(c.check()['own'], 6)
                path = root/helper
                path.write_text(path.read_text().replace('def _write(', 'def _changed_write(', 1))
                with self.assertRaisesRegex(ValueError, 'source drift'):
                    c.check()

    def test_explicit_small_scope_and_typed_timing(self):
        for params in ((True,3,0,0), (0,3,0,0), (1,True,0,0), (1,2,0,0), (1,3,-1,0), (1,3,0,21)):
            with self.assertRaises(ValueError):
                Timing(*params)
        for tokens in (0,3,128,True):
            scalar = ExactScalar(object())
            controller = Controller(scalar, ref_fma, lambda a: exp_negative(scalar,scalar.client,a), timing=Timing(1,3,0,0))
            with self.assertRaises(ValueError):
                controller.run(tokens, *fixture(1))
            self.assertEqual(controller.ticks,0)
            self.assertEqual(scalar.calls,{})

    def test_fault_keeps_contenders_blocked_and_does_not_return_output(self):
        scalar = ExactScalar(object())
        controller = Controller(scalar, lambda a,b,c: 0x7f800000,
            lambda a: exp_negative(scalar, scalar.client, a), timing=Timing(2,3,1,1))
        with self.assertRaises(NumericalFault):
            controller.run(1, *fixture(1))
        self.assertTrue(controller.failed)
        self.assertFalse(controller.ordinary_owner_ready())
        self.assertEqual(controller.counts['matrix_result_acks'], 1)
        self.assertEqual(controller.counts['scalar_packets'], 0)


if __name__ == '__main__':
    unittest.main()
