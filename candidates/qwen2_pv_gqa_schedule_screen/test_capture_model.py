"""Behavioral protocol tests with opaque integer labels, not floating point."""
from dataclasses import replace
import random
import struct
import unittest

import model as g
from capture_model import BoundedFifo, CaptureModel, ProtocolError


ZERO = bytes(16384)


def labeled_value(step):
    """A return's bytes identify its actual key and logical row, not its math."""
    raw = bytearray(16384)
    for row in range(32):
        word = (step.cohort << 16) | (step.key << 8) | row
        r, c = g.physical_cell(row, 0)
        offset = r * 1024 + c * 4
        raw[offset:offset + 512] = struct.pack('<I', word) * 128
    return bytes(raw)


def advance_to_emit(m, context=0):
    for _ in range(128):
        step = m.issue(context)
        if step is None:
            raise AssertionError('cannot advance to first causal return')
        m.accept_return(step, labeled_value(step) if step.emit else ZERO)
        if step.emit:
            return step
    raise AssertionError('no causal emission')


def finish_capture(m):
    while m.capture is not None:
        request = m.accept_write()
        if request is None:
            raise AssertionError('capture did not expose a write')
        m.accept_ack(request)


def replay(tokens=128, seed=419):
    """Read/write/return handshakes, with deterministic stalls; no clock count."""
    randomizer = random.Random(seed)
    m = CaptureModel()
    tiles = tuple(g.cohorts(tokens))
    observer_writes = 0
    for kv in range(2):
        selected = [t for t in tiles if t.kv_head == kv]
        for base in range(0, len(selected), 5):
            group = selected[base:base + 5]
            m.begin(group, kv_committed=True, probabilities_committed=True)
            context = 0
            # Bound is only a test-harness runaway guard, never a cycle budget.
            for _ in range(100000):
                if m.pending_write is not None and randomizer.randrange(3):
                    request = m.pending_write
                    expected = (request.cohort << 16) | (request.query << 8) | request.row
                    if request.data != struct.pack('<I', expected) * 16:
                        raise AssertionError('captured live/suffix key instead of returning row-final key')
                    m.accept_ack(request)
                    observer_writes += 1
                m.accept_write(ready=bool(randomizer.randrange(3)))
                m.capture_next(ready=bool(randomizer.randrange(3)))
                if m.metadata.head is not None and randomizer.randrange(3):
                    step = m.metadata.head
                    m.accept_return(step, labeled_value(step) if step.emit else ZERO)
                m.issue(context, ready=bool(randomizer.randrange(3)))
                context = (context + 1) % len(group)
                if m.done_ready:
                    m.accept_done(m.epoch, m.group)
                if m.terminal_ready:
                    m.retire_group()
                    break
            else:
                raise AssertionError('bounded behavioral replay did not terminate')
    return m, observer_writes


class CaptureBehaviorTests(unittest.TestCase):
    def fresh(self, tiles=None):
        m = CaptureModel()
        m.begin(tuple(g.cohorts())[:5] if tiles is None else tiles,
                kv_committed=True, probabilities_committed=True)
        return m

    def test_full_m128_opaque_replay_preserves_causal_capture_and_counts(self):
        m, writes = replay()
        self.assertEqual(m.counts['issues'], 3216)
        self.assertEqual(m.counts['returns'], 3216)
        self.assertEqual(m.counts['emitted_returns'], 288)
        self.assertEqual(m.counts['captured_rows'], 1536)
        self.assertEqual(m.counts['acknowledged_bytes'], 786432)
        self.assertEqual(writes, 12288)
        self.assertEqual(m.counts['success_terminals'], 10)
        self.assertEqual(m.state, 'idle')
        self.assertFalse(m.poison)
        self.assertLessEqual(m.highwater['metadata'], 5)
        self.assertEqual(m.highwater['results'], 2)
        self.assertEqual(m.highwater['capture'], 1)
        self.assertEqual(m.highwater['write'], 1)

    def test_small_shapes_and_multiple_backpressure_seeds(self):
        for tokens in (1, 2, 5, 16, 31):
            for seed in (3, 71):
                m, writes = replay(tokens, seed)
                self.assertEqual(m.counts['issues'], g.report(tokens)['candidate']['matrix_issue_steps'])
                self.assertEqual(m.counts['captured_rows'], tokens * 12)
                self.assertEqual(writes, tokens * 12 * 8)

    def test_dimension_and_half_mapping_with_independent_physical_labels(self):
        tile = next(g.cohorts())
        m = self.fresh([tile])
        # Encode physical row/column directly; do not use physical_cell or the
        # repeated logical-row test helper to manufacture the expected data.
        physical = struct.pack('<4096I', *range(4096))
        addresses = set()
        for key in range(tile.keys):
            step = m.issue(0)
            m.accept_return(step, physical)
            if step.emit:
                m.capture_next()
                while m.capture is not None:
                    request = m.accept_write()
                    first = (request.row % 16) * 256 + (request.row // 16) * 128 + request.beat * 16
                    self.assertEqual(request.data, struct.pack('<16I', *range(first, first + 16)))
                    query, head = tile.rows[request.row]
                    self.assertEqual(request.address,
                                     0x100000 + query * 6144 + head * 512 + request.beat * 64)
                    self.assertNotIn(request.address, addresses)
                    addresses.add(request.address)
                    m.accept_ack(request)
        self.assertEqual(len(addresses), 32 * 8)
        m.accept_done(m.epoch, m.group)
        m.retire_group()

    def test_five_contexts_and_conservative_metadata_credit(self):
        m = self.fresh()
        steps = [m.issue(c) for c in range(5)]
        self.assertEqual(len(m.metadata), 5)
        self.assertTrue(all(m.issue(c) is None for c in range(5)))
        self.assertTrue(m.accept_return(steps[0], labeled_value(steps[0])))
        self.assertIsNotNone(m.issue(0))
        self.assertEqual(len(m.metadata), 5)
        self.assertEqual(m.metadata.capacity, 8)

    def test_eight_entry_fifo_cannot_overflow(self):
        # The generic storage boundary is tested independently; five busy
        # contexts cannot reach eight live steps in the conservative harness.
        queue = BoundedFifo(8)
        for i in range(8):
            queue.push(i)
        with self.assertRaises(ProtocolError):
            queue.push(8)
        self.assertEqual([queue.pop() for _ in range(8)], list(range(8)))
        with self.assertRaises(ProtocolError):
            queue.pop()

    def test_returner_cannot_rewrite_last_or_causal_capture_mask(self):
        for alteration in (dict(last=True), dict(final_rows=()), dict(final_rows=(31,))):
            m = self.fresh()
            first = m.issue(0)
            with self.assertRaises(ProtocolError):
                m.accept_return(replace(first, **alteration), labeled_value(first))
            self.assertEqual(m.metadata.head, first)
            self.assertEqual(m.counts['returns'], 0)
            self.assertEqual(m.counts['captured_rows'], 0)

    def test_result_queue_held_until_capture_and_context_lease_not_reused(self):
        m = self.fresh([next(g.cohorts())])
        for _ in range(2):
            step = m.issue(0)
            m.accept_return(step, labeled_value(step))
        third = m.issue(0)
        held = m.results.head
        self.assertFalse(m.return_ready)
        self.assertFalse(m.accept_return(third, labeled_value(third)))
        self.assertEqual(len(m.metadata), 1)
        self.assertIs(m.results.head, held)
        self.assertTrue(m.contexts[0]['busy'])
        self.assertTrue(m.capture_next())
        self.assertTrue(m.accept_return(third, labeled_value(third)))
        before = bytes(m.capture['raw'])
        self.assertFalse(m.capture_next())
        self.assertEqual(bytes(m.capture['raw']), before)

    def test_capture_batch_drains_before_other_cohort_and_does_not_wait_for_full_cohort(self):
        tiles = tuple(g.cohorts())
        m = self.fresh([tiles[0], tiles[1]])
        first = advance_to_emit(m, 0)
        second = advance_to_emit(m, 1)
        self.assertEqual(len(m.results), 2)
        m.capture_next()
        self.assertEqual(m.capture['step'], first)
        self.assertLess(len(m.capture['rows']), 32)
        finish_capture(m)
        self.assertFalse(m.contexts[0]['last_returned'])
        self.assertTrue(m.capture_next())
        self.assertEqual(m.capture['step'], second)

    def test_nonfinal_results_do_not_consume_output_fifo(self):
        m = self.fresh([tuple(g.cohorts())[5]])
        step = m.issue(0)
        self.assertFalse(step.emit)
        self.assertTrue(m.accept_return(step, ZERO))
        self.assertEqual(len(m.results), 0)
        self.assertFalse(m.capture_next())

    def test_write_request_stable_and_capture_released_only_after_exact_ack(self):
        m = self.fresh([next(g.cohorts(1))])
        advance_to_emit(m)
        m.capture_next()
        request = m.write_request
        for _ in range(5):
            self.assertIsNone(m.accept_write(ready=False))
            self.assertIs(m.write_request, request)
        self.assertEqual(m.accept_write(), request)
        self.assertIsNone(m.write_request)
        self.assertFalse(m.terminal_ready)
        m.accept_ack(request)
        finish_capture(m)
        self.assertIsNone(m.capture)

    def test_stale_duplicate_and_out_of_order_returns_reject(self):
        for field, value in (('epoch', 99), ('group', 99), ('cohort', 99), ('key', 99), ('context', 4)):
            m = self.fresh()
            step = m.issue(0)
            with self.assertRaises(ProtocolError):
                m.accept_return(replace(step, **{field: value}), ZERO)
            self.assertEqual(m.metadata.head, step)
            self.assertTrue(m.poison)
        m = self.fresh()
        first, second = m.issue(0), m.issue(1)
        with self.assertRaises(ProtocolError):
            m.accept_return(second, ZERO)
        m.accept_return(first, ZERO)
        m.accept_return(second, ZERO)
        with self.assertRaises(ProtocolError):
            m.accept_return(second, ZERO)

    def test_invalid_width_context_and_key_reject_without_accepting_work(self):
        m = self.fresh()
        step = m.issue(0)
        with self.assertRaises(ProtocolError):
            m.accept_return(step, bytes(512))
        self.assertEqual(m.counts['returns'], 0)
        for bad in (5, -1, True):
            with self.assertRaises(ProtocolError):
                self.fresh().issue(bad)
        m = self.fresh()
        with self.assertRaises(ProtocolError):
            m.issue(0, 1)
        self.assertEqual(m.counts['issues'], 0)

    def test_reject_uncommitted_overcapacity_mixed_kv_and_overlapping_cohorts(self):
        tiles = tuple(g.cohorts())
        cases = [([tiles[0]], False, True), ([tiles[0]], True, False),
                 (tiles[:6], True, True), ([tiles[0], tiles[24]], True, True),
                 ([tiles[0], replace(tiles[0], identity=99)], True, True)]
        for group, kv, prob in cases:
            with self.assertRaises(ProtocolError):
                CaptureModel().begin(group, kv_committed=kv, probabilities_committed=prob)

    def test_matrix_done_cannot_replace_output_ack_fence(self):
        m = self.fresh([next(g.cohorts(1))])
        advance_to_emit(m)
        self.assertFalse(m.done_ready)
        m.capture_next()
        self.assertTrue(m.done_ready)
        m.accept_done(m.epoch, m.group)
        self.assertFalse(m.terminal_ready)
        finish_capture(m)
        self.assertTrue(m.terminal_ready)
        m.retire_group()
        self.assertEqual(m.state, 'idle')

    def test_early_and_duplicate_done_or_terminal_reject(self):
        m = self.fresh()
        with self.assertRaises(ProtocolError):
            m.accept_done(m.epoch, m.group)
        m = self.fresh()
        with self.assertRaises(ProtocolError):
            m.retire_group()

    def test_bad_ack_does_not_erase_accepted_write(self):
        for kind in ('tag', 'bytes'):
            m = self.fresh([next(g.cohorts(1))])
            advance_to_emit(m)
            m.capture_next()
            request = m.accept_write()
            with self.assertRaises(ProtocolError):
                if kind == 'tag':
                    m.accept_ack(replace(request, sequence=request.sequence + 1))
                else:
                    m.accept_ack(request, nbytes=63)
            self.assertEqual(m.pending_write, request)
            self.assertFalse(m.terminal_ready)
            m.accept_ack(request)
            self.assertIsNone(m.pending_write)
            self.assertTrue(m.poison)

    def test_error_ack_poison_never_publishes_success(self):
        m = self.fresh([next(g.cohorts(1))])
        advance_to_emit(m)
        m.capture_next()
        request = m.accept_write()
        m.accept_ack(request, error=True)
        m.accept_done(m.epoch, m.group, error=True)
        m.retire_group()
        self.assertEqual(m.state, 'locked')
        self.assertEqual(m.counts['success_terminals'], 0)
        self.assertEqual(m.counts['error_terminals'], 1)

    def test_first_backend_error_done_consumed_once_with_pending_write(self):
        m = self.fresh([next(g.cohorts(1))])
        advance_to_emit(m)
        m.capture_next()
        request = m.accept_write()
        m.accept_done(m.epoch, m.group, error=True)
        self.assertTrue(m.backend_done)
        self.assertTrue(m.poison)
        self.assertFalse(m.terminal_ready)
        m.accept_ack(request)
        m.retire_group()
        self.assertEqual(m.counts['matrix_done'], 1)
        self.assertEqual(m.counts['error_terminals'], 1)

    def test_local_write_error_does_not_require_backend_to_return_error(self):
        m = self.fresh([next(g.cohorts(1))])
        advance_to_emit(m)
        m.capture_next()
        request = m.accept_write()
        m.accept_ack(request, error=True)
        m.accept_done(m.epoch, m.group, error=False)
        m.retire_group()
        self.assertEqual(m.counts['matrix_done'], 1)
        self.assertEqual(m.counts['error_terminals'], 1)
        self.assertEqual(m.counts['success_terminals'], 0)

    def test_backend_error_can_close_incomplete_group_after_actual_returns_drain(self):
        m = self.fresh([tuple(g.cohorts())[5]])
        step = m.issue(0)
        self.assertFalse(step.last)
        self.assertFalse(step.emit)
        self.assertFalse(m.can_accept_done(error=True))  # Real return still owed.
        m.accept_return(step, ZERO)
        self.assertFalse(m.done_ready)  # No successful last was returned.
        self.assertFalse(m.can_accept_done(error=False))
        self.assertTrue(m.can_accept_done(error=True))
        m.accept_done(m.epoch, m.group, error=True)
        self.assertFalse(m.can_accept_done(error=True))  # One-shot completion.
        m.retire_group()
        self.assertEqual(m.state, 'locked')
        self.assertEqual(m.counts['matrix_done'], 1)
        self.assertEqual(m.counts['error_terminals'], 1)

    def test_error_done_readiness_requires_drain_and_exact_boolean_status(self):
        m = self.fresh([next(g.cohorts(1))])
        advance_to_emit(m)
        self.assertFalse(m.can_accept_done(error=True))  # Buffered result owed.
        m.capture_next()
        for status in (True, False):
            self.assertTrue(m.can_accept_done(error=status))
        for status in (0, 1, None, 'error'):
            self.assertFalse(m.can_accept_done(error=status))
        self.assertEqual(m.done_ready, m.can_accept_done(error=False))

    def test_abort_and_local_reset_drain_real_returns_and_ack_before_reset(self):
        m = self.fresh()
        first = m.issue(0)
        m.accept_return(first, labeled_value(first))
        m.capture_next()
        request = m.accept_write()
        outstanding = m.issue(1)
        m.abort()
        with self.assertRaises(ProtocolError):
            m.coordinated_reset(backend_reset_confirmed=True)
        self.assertEqual(m.pending_write, request)
        self.assertEqual(m.metadata.head, outstanding)
        self.assertIsNone(m.issue(0))
        m.accept_return(outstanding, ZERO)
        m.accept_done(m.epoch, m.group, error=True)
        self.assertFalse(m.terminal_ready)
        m.accept_ack(request)
        m.retire_group()
        with self.assertRaises(ProtocolError):
            m.coordinated_reset(backend_reset_confirmed=False)
        old_epoch = m.epoch
        m.coordinated_reset(backend_reset_confirmed=True)
        self.assertEqual(m.epoch, old_epoch + 1)
        m.begin([next(g.cohorts(1))], kv_committed=True, probabilities_committed=True)
        new = m.issue(0)
        with self.assertRaises(ProtocolError):
            m.accept_return(first, ZERO)
        self.assertEqual(m.metadata.head, new)

    def test_abort_drains_buffered_results_without_fabricating_capture(self):
        m = self.fresh([next(g.cohorts())])
        for _ in range(2):
            step = m.issue(0)
            m.accept_return(step, labeled_value(step))
        m.abort()
        self.assertFalse(m.done_ready)
        self.assertTrue(m.drain_result())
        self.assertTrue(m.drain_result())
        self.assertFalse(m.drain_result())
        m.accept_done(m.epoch, m.group, error=True)
        m.retire_group()
        self.assertEqual(m.counts['writes'], 0)

    def test_never_claims_numeric_or_rtl_or_utilization(self):
        report = self.fresh().report()
        self.assertEqual(report['status'], 'BEHAVIOR_SPEC_ONLY_CANDIDATE_BLOCKED')
        for key in ('arithmetic_executed', 'bit_exact', 'actual_rtl_run', 'source_interface_implemented', 'timing_model'):
            self.assertFalse(report[key])
        self.assertIsNone(report['hardware_cycles'])
        self.assertIsNone(report['hardware_utilization'])


if __name__ == '__main__':
    unittest.main()
