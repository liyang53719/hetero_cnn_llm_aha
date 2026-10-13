"""Bounded real Vector16/SRAM left-fold tests, no Matrix/checkpoint/RTL run.

All partials enter the original physical tile write/RMW/seal ports. All three
Adds use the existing SharedVector16Loan and actual Vector16 library, with
independent rational FP32 comparisons. No output bytes or tags are relabeled
to fabricate a sum. Synthetic fixtures are not fullshape O numerical evidence.
"""
from dataclasses import replace
import hashlib
import os
import time
import unittest

from . import chained_tiles as t
from . import chained_sum as s
from ..qwen35_35b_prefill import sum_tiles as old
from ..qwen35_gdn_prefill.projection_driver import SharedVector16Loan
from ..qwen35_gdn_prefill.chunk.vector import Vector16, IEEE_POLICY
from ..qwen2_resident_matrix.ffn_public.test_prefix_owners import ref_add


def setUpModule():
    if not os.environ.get('GDN_VECTOR16_LIBRARY'):
        raise ValueError('explicit existing GDN_VECTOR16_LIBRARY required; no build/cache lookup')


def packets(part, beats):
    witness = (0x4c000000, 0x3f800000, 0xcc000000, 0x3f800000)
    return [tuple(witness[part] if lane == 0 else
                  (0x3f000001 + part * 127 + index * 16 + lane)
                  for lane in range(16)) for index in range(beats)]


def load(bank, slot, identity, values, rows=16, cols=32, ng=0, matrix_order=False):
    ctl = t.Control(0, slot, identity, ng, rows, cols,
                    matrix_producer_order=matrix_order)
    assert bank.tick(control=ctl)['ctl_fire'] and not bank.poison
    assert len(values) == rows // 16 * cols
    for produced in range(len(values)):
        index = t.base.producer_index(produced, rows, cols) if matrix_order else produced
        assert bank.tick(write=t.Write(slot, identity, ng, index, values[index]))['write_fire']
        assert not bank.poison
        assert bank.tick()['rmw_commit']
    assert bank.tick(control=replace(ctl, op=1))['ctl_fire'] and not bank.poison


def read(bank, identity, index, ng=0, *, phase='sum'):
    assert bank.tick(read=t.Read(0, identity, ng, index, phase=phase))['read_fire']
    bank.tick(response_ready=False)
    edge = bank.tick()
    assert edge['response_fire'] and not bank.poison
    return edge['response'].words


def footprint(bank, ranges=((0, 1024), (1344, 1376))):
    digest = hashlib.sha256()
    for words in bank.banks.words:
        for begin, end in ranges:
            for value in words[begin:end]:
                digest.update(value.to_bytes(32, 'little'))
    return digest.hexdigest()


class Harness:
    def __init__(self, rows=16, cols=32, bank=None):
        self.rows, self.cols, self.beats = rows, cols, rows // 16 * cols
        self.banks = t.ChainedTileBankModel() if bank is None else bank
        self.vector = Vector16(os.environ['GDN_VECTOR16_LIBRARY'], exception_policy=IEEE_POLICY)
        self.loan = SharedVector16Loan(self.vector)
        self.controller = s.ChainedSumController(self.banks)
        self.values = [packets(part, self.beats) for part in range(4)]
        self.calls = (s.SumInvocation(21, 11, 12, 0, rows, cols),
                      s.SumInvocation(22, 21, 13, 0, rows, cols, 'sum'),
                      s.SumInvocation(23, 22, 14, 0, rows, cols, 'sum'))
        self.edges = []

    def tick(self, **inputs):
        edge = s.shared_loan_edge(self.controller, self.loan, **inputs)
        self.edges.append(edge)
        return edge

    def first(self):
        load(self.banks, 0, 11, self.values[0], self.rows, self.cols, matrix_order=True)
        load(self.banks, 1, 12, self.values[1], self.rows, self.cols, matrix_order=True)

    def rhs(self, part):
        load(self.banks, 1, 11 + part, self.values[part], self.rows, self.cols, matrix_order=True)

    def until(self, predicate, **inputs):
        deadline = time.monotonic() + 20
        for _ in range(self.beats * 40 + 100):
            if predicate():
                return
            assert time.monotonic() < deadline, 'bounded bank/Vector protocol budget'
            self.tick(**inputs)
        raise AssertionError('protocol predicate not reached')

    def complete(self, call):
        assert self.tick(start=call)['start_fire']
        for i in range(self.beats * 40 + 100):
            edge = self.tick(bank_ready=i % 7 != 0)
            if edge['complete']:
                return edge
        raise AssertionError('bounded real-Vector sum did not complete')

    def finish_started(self):
        for _ in range(self.beats * 40 + 100):
            edge = self.tick()
            if edge['complete']:
                return
        raise AssertionError('started sum did not complete')


class ChainedSumTests(unittest.TestCase):
    def test_three_real_adds_are_left_fold_not_balanced(self):
        h = Harness()
        h.first()
        identity = (id(h.banks), id(h.banks.banks), id(h.vector), h.vector.resource_address)
        untouched = footprint(h.banks)
        for index, call in enumerate(h.calls):
            if index:
                h.rhs(index + 1)
            h.complete(call)
            self.assertEqual(h.banks.lineage.merges, index + 1)
            self.assertEqual(h.banks.lineage.identity, call.identity)
            self.assertTrue(h.banks.sum_ready)
            self.assertFalse(h.banks.tags[1].live)
            self.assertIsNone(h.banks.overwrite)
            self.assertEqual((h.banks.tags[0].identity, h.banks.tags[0].phase,
                              h.banks.tags[0].produced, h.banks.tags[0].consumed),
                             (call.identity, 'sum', h.beats, 0))
            self.assertEqual(footprint(h.banks), untouched)
        actual = [read(h.banks, 23, i) for i in range(h.beats)]
        expected = [tuple(ref_add(ref_add(ref_add(a, b), c), d)
                          for a, b, c, d in zip(*row)) for row in zip(*h.values)]
        balanced = ref_add(ref_add(0x4c000000, 0x3f800000),
                           ref_add(0xcc000000, 0x3f800000))
        self.assertEqual(expected[0][0], 0x3f800000)
        self.assertEqual(balanced, 0)
        self.assertEqual(actual, expected)
        self.assertTrue(any(word & 0xffff for row in actual for word in row[1:]))
        self.assertEqual(h.controller.counts['completed'], 3)
        self.assertEqual(h.controller.counts['accepted_operand_beats'], 6 * h.beats)
        self.assertEqual(h.controller.counts['add_requests'], 3 * h.beats)
        self.assertEqual(h.controller.counts['add_results'], 3 * h.beats)
        self.assertEqual(h.controller.counts['output_beats'], 3 * h.beats)
        self.assertEqual(h.vector.calls['add'], 3 * h.beats)
        self.assertEqual(h.vector.lane_ops['add'], 48 * h.beats)
        self.assertEqual(h.loan.calls, h.loan.retirements)
        self.assertTrue(h.loan.ports()['drained'])
        self.assertEqual(identity, (id(h.banks), id(h.banks.banks), id(h.vector), h.vector.resource_address))
        self.assertEqual(len(h.banks.lineage.used_ids), 7)
        self.assertEqual(t.resource_ledger()['additional_tensor_storage_bytes'], 0)

    def test_m128_n160_physical_ports_three_adds(self):
        h = Harness(rows=128, cols=160)
        h.first()
        for index, call in enumerate(h.calls):
            if index:
                h.rhs(index + 1)
            before = dict(h.banks.counters)
            h.complete(call)
            after = h.banks.counters
            self.assertEqual(after['read_requests'] - before['read_requests'], 2 * h.beats)
            self.assertEqual(after['write_requests'] - before['write_requests'], h.beats)
            self.assertEqual(after['physical_read_bytes'] - before['physical_read_bytes'], 3 * h.beats * 512)
            self.assertEqual(after['physical_write_bytes'] - before['physical_write_bytes'], h.beats * 512)
        self.assertEqual(h.vector.calls['add'], 3840)
        self.assertTrue(all(len(edge['bank']['reads']) <= 16 and
                            len(edge['bank']['writes']) <= 16 for edge in h.edges))
        self.assertEqual(len(h.banks.tags), 2)
        self.assertEqual(h.banks.banks.depth, 1376)

    def test_same_wrapper_legacy_upstream_then_chained_without_reset(self):
        h = Harness()
        underlying, vector_address = h.banks.banks, h.vector.resource_address
        legacy = s.LegacyInplaceSumController(h.banks)
        for slot in (0, 1):
            load(h.banks, slot, 41, h.values[slot])
        call = old.SumInvocation(42, 41, 0, 16, 32)
        self.assertTrue(s.shared_loan_edge(legacy, h.loan, start=call)['start_fire'])
        for _ in range(2000):
            if s.shared_loan_edge(legacy, h.loan)['complete']:
                break
        else:
            self.fail('legacy adapter completion')
        self.assertIsNone(h.banks.lineage)
        for index in range(h.beats):
            self.assertEqual(read(h.banks, 42, index),
                             tuple(ref_add(a, b) for a, b in zip(h.values[0][index], h.values[1][index])))
        h.banks.tick(control=t.Control(2, 0, 42, 0, 16, 32, phase='sum'))
        self.assertFalse(h.banks.leased)
        h.first()
        for index, call in enumerate(h.calls):
            if index:
                h.rhs(index + 1)
            h.complete(call)
        self.assertIs(h.banks.banks, underlying)
        self.assertEqual(h.vector.resource_address, vector_address)
        self.assertEqual(h.vector.calls['add'], 4 * h.beats)

    def test_held_rhs_and_real_vector_result_are_stable(self):
        h = Harness()
        h.first()
        h.complete(h.calls[0])
        h.rhs(2)
        self.assertTrue(h.tick(start=h.calls[1])['start_fire'])
        h.until(lambda: h.controller.state == 'rhsWait' and h.banks.response is not None)
        external = object()
        self.assertTrue(h.vector.acquire(external))
        held = h.banks.response
        requests = h.controller.counts['add_requests']
        for _ in range(5):
            edge = h.tick()
            self.assertFalse(edge['bank']['response_fire'] or edge['request_fire'])
            self.assertIs(h.banks.response, held)
            self.assertEqual(h.controller.counts['add_requests'], requests)
        h.vector.release(external)
        h.until(lambda: h.loan.result is not None)
        held = h.loan.result
        for _ in range(5):
            edge = h.tick(bank_ready=False)
            self.assertFalse(edge['result_fire'] or edge['bank']['write_fire'])
            self.assertIs(h.loan.result, held)
        h.finish_started()
        self.assertEqual(h.banks.lineage.merges, 2)

    def test_accepted_sum_rmw_commits_before_abort_reset(self):
        h = Harness()
        h.first()
        h.complete(h.calls[0])
        h.rhs(2)
        h.tick(start=h.calls[1])
        h.until(lambda: h.banks.pending is not None and h.banks.pending[0] == 'write')
        _, q, word, lane, captured = h.banks.pending
        commits = h.banks.counters['rmw_commits']
        edge = h.tick(coordinated_reset=True)
        self.assertTrue(edge['reset_rejected'])
        self.assertFalse(edge['reset'] or edge['complete'])
        self.assertEqual(h.banks.counters['rmw_commits'], commits + 1)
        mask = 0xffffffff << (lane * 32)
        for bank in range(16):
            self.assertEqual(h.banks.banks.words[bank][word],
                             (captured[bank] & ~mask) | (q.words[bank] << (lane * 32)))
        h.until(lambda: h.controller.state == 'locked')
        self.assertTrue(h.banks.poison and h.loan.poison)
        self.assertFalse(h.banks.sum_ready)
        before = footprint(h.banks, ((0, 1376),))
        self.assertTrue(h.tick(coordinated_reset=True)['reset'])
        self.assertEqual(footprint(h.banks, ((0, 1376),)), before)
        self.assertIsNone(h.banks.lineage)
        self.assertFalse(h.banks.poison or h.loan.poison)

    def test_reset_with_real_held_vector_response_drains_before_clear(self):
        h = Harness()
        h.first()
        h.tick(start=h.calls[0])
        h.until(lambda: h.loan.result is not None)
        self.assertIs(h.vector.client, h.loan)
        edge = h.tick(coordinated_reset=True)
        self.assertTrue(edge['reset_rejected'])
        self.assertFalse(edge['result_fire'] or edge['bank']['write_fire'] or edge['complete'])
        self.assertTrue(h.loan.ports()['drained'])
        self.assertIsNone(h.vector.client)
        h.until(lambda: h.controller.state == 'locked')
        self.assertEqual(h.controller.counts['completed'], 0)
        self.assertTrue(h.tick(coordinated_reset=True)['reset'])

    def test_real_add_overflow_retires_error_without_write(self):
        h = Harness()
        h.values[0][0] = h.values[1][0] = (0x7f7fffff,) * 16
        h.first()
        h.tick(start=h.calls[0])
        saw_error = False
        for _ in range(100):
            edge = h.tick()
            if edge['result_fire']:
                saw_error = True
                self.assertFalse(edge['loan_abort'] or edge['bank']['write_fire'])
            if h.controller.state == 'locked':
                break
        self.assertTrue(saw_error and h.banks.poison and h.loan.poison)
        self.assertEqual(h.controller.counts['output_beats'], 0)
        self.assertEqual(h.controller.counts['completed'], 0)
        self.assertEqual(h.vector.calls['add'], 1)

    def test_wrong_phase_identity_and_reused_ids_rejected(self):
        for change in (dict(lhs_phase='partial'), dict(lhs_identity=999),
                       dict(rhs_identity=999), dict(identity=11), dict(identity=21),
                       dict(lhs_phase='rhs'), dict(output_slot=1)):
            with self.subTest(change=change):
                h = Harness()
                h.first()
                h.complete(h.calls[0])
                h.rhs(2)
                before = h.banks.counters['write_requests']
                self.assertTrue(h.tick(start=replace(h.calls[1], **change))['start_fire'])
                self.assertTrue(h.controller.poison)
                self.assertEqual(h.banks.counters['write_requests'], before)
        h = Harness()
        h.first()
        h.complete(h.calls[0])
        h.banks.tick(control=t.Control(0, 1, 12, 0, 16, 32))
        self.assertTrue(h.banks.poison)

    def test_consumed_lhs_unsealed_rhs_and_fourth_merge_rejected(self):
        for kind in ('consumed', 'unsealed', 'fourth'):
            with self.subTest(kind=kind):
                h = Harness()
                h.first()
                h.complete(h.calls[0])
                if kind == 'fourth':
                    for index in (1, 2):
                        h.rhs(index + 1)
                        h.complete(h.calls[index])
                    h.banks.tick(control=t.Control(0, 1, 15, 0, 16, 32))
                    self.assertTrue(h.banks.poison)
                    continue
                h.rhs(2)
                if kind == 'consumed':
                    read(h.banks, 21, 0)
                else:
                    # Fault injection into control metadata, never a positive
                    # producer fixture or tag conversion in the implementation.
                    h.banks.tags[1].sealed = False
                h.tick(start=h.calls[1])
                self.assertTrue(h.controller.poison)

    def test_bad_held_operand_response_drains_no_add(self):
        for field, value in (('identity', 99), ('phase', 'rhs'), ('index', 1)):
            h = Harness()
            h.first()
            h.tick(start=h.calls[0])
            h.until(lambda: h.controller.state == 'lhsWait' and h.banks.response is not None)
            h.banks.response = replace(h.banks.response, **{field: value})
            edge = h.tick()
            self.assertTrue(edge['bank']['response_fire'])
            self.assertFalse(edge['request_fire'] or edge['complete'])
            h.until(lambda: h.controller.state == 'locked')
            self.assertEqual(h.vector.calls['add'], 0)

    def test_final_result_and_retire_abort_suppress_completion(self):
        for target in ('last_result', 'retire'):
            h = Harness()
            h.first()
            h.tick(start=h.calls[0])
            h.until(lambda: h.controller.state == 'retire' if target == 'retire' else
                    h.controller.index == h.beats - 1 and h.loan.result is not None)
            self.assertFalse(h.tick(abort=True)['complete'])
            h.until(lambda: h.controller.state == 'locked')
            self.assertEqual(h.controller.counts['completed'], 0)
            self.assertFalse(h.banks.sum_ready)

    def test_legacy_default_still_rejects_sum_input(self):
        bank = t.base.TileBankModel()
        vector = Vector16(os.environ['GDN_VECTOR16_LIBRARY'], exception_policy=IEEE_POLICY)
        loan = SharedVector16Loan(vector)
        controller = old.InplaceSumController(bank)
        for slot in (0, 1):
            load(bank, slot, 41, packets(slot, 32))
        first = old.SumInvocation(42, 41, 0, 16, 32)
        self.assertTrue(old.shared_loan_edge(controller, loan, start=first)['start_fire'])
        for _ in range(2000):
            if old.shared_loan_edge(controller, loan)['complete']:
                break
        else:
            self.fail('original default completion')
        load(bank, 1, 42, packets(2, 32))
        next_call = old.SumInvocation(43, 42, 0, 16, 32)
        before = bank.counters['write_requests']
        self.assertTrue(old.shared_loan_edge(controller, loan, start=next_call)['start_fire'])
        self.assertTrue(controller.poison)
        self.assertEqual(bank.counters['write_requests'], before)
        with self.assertRaises(ValueError):
            s.ChainedSumController(bank)

    def test_next_n_window_reuses_ids_only_after_final_read_release(self):
        h = Harness()
        for ng in (0, 160):
            for slot, identity, part in ((0, 11, 0), (1, 12, 1)):
                load(h.banks, slot, identity, h.values[part], ng=ng)
            for index, call in enumerate(h.calls):
                if index:
                    load(h.banks, 1, 12 + index, h.values[index + 1], ng=ng)
                h.complete(replace(call, ng=ng))
            self.assertEqual(h.banks.lineage.ng, ng)
            self.assertEqual(h.banks.lineage.used_ids, (11, 12, 21, 13, 22, 14, 23))
            for index in range(h.beats):
                read(h.banks, 23, index, ng=ng)
            self.assertTrue(h.banks.tick(control=t.Control(2, 0, 23, ng, 16, 32, phase='sum'))['ctl_fire'])
            self.assertFalse(h.banks.leased)
        self.assertEqual(h.controller.counts['completed'], 6)
        self.assertEqual(len(h.banks.lineage.used_ids), 7)

    def test_new_window_cannot_discard_live_or_partially_consumed_sum(self):
        for consume_one in (False, True):
            h = Harness()
            h.first()
            for index, call in enumerate(h.calls):
                if index:
                    h.rhs(index + 1)
                h.complete(call)
            if consume_one:
                read(h.banks, 23, 0)
            h.banks.tick(control=t.Control(0, 0, 11, 160, 16, 32))
            self.assertTrue(h.banks.poison)


if __name__ == '__main__':
    unittest.main()
