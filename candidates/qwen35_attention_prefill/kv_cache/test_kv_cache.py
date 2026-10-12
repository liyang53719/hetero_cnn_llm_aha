"""Small stdlib-only software gates using true 1024-byte KV tokens.

Upstream and downstream test producers use real TypedMemory data/ACK/terminal
publication, with synthetic bytes. No model, compile, RTL, native comparison,
or claim of executing actual projection/RoPE/final-residual arithmetic.
"""
from dataclasses import FrozenInstanceError, replace
from copy import deepcopy
import struct
import unittest
from unittest.mock import patch

from ...qwen2_resident_matrix.transposed_down.model import WriteCommand, WriteAck
from ...qwen35_gdn_prefill.typed_dense import TypedMemory
from . import owner as o
from .driver import TypedKvCacheDriver
from .fence import CommittedKvState, FullBlockTerminal, KvBlockFence


def token_bytes(tokens, seed):
    # Include Inf/NaN/subnormal/signed-zero encodings: this is an exact copy,
    # so no floating-point conversion or numerical classification is legal.
    special = (0x7F80, 0xFF80, 0x7FC1, 0x8000, 0x0001)
    return struct.pack('<' + str(tokens * 512) + 'H',
                       *(special[i] if i < len(special) else (seed + 73 * i) % 65536
                         for i in range(tokens * 512)))


def producer(memory, base, raw, tag):
    """Synthetic upstream/final producer through actual write/ACK publication."""
    output = memory.allocate_output(base, len(raw))
    for offset in range(0, len(raw), 64):
        memory.begin_write(WriteCommand(base + offset, 1, (tag << 32) | offset))
        memory.write_data(struct.unpack('<32H', raw[offset:offset + 64]), True)
        memory.acknowledge(WriteAck((tag << 32) | offset, False, 64))
    memory.publish(base, (tag, None, len(raw)))
    return output


class LyingCoverage(set):
    def __eq__(self, other):
        return True

    def __ne__(self, other):
        return False


class OffsetImpostor:
    def __init__(self, offset):
        self.offset = offset

    def __hash__(self):
        return hash(self.offset)

    def __eq__(self, other):
        return self.offset == other


class KvCacheTests(unittest.TestCase):
    def setUp(self):
        self.memory = TypedMemory()
        self.fence = KvBlockFence(self.memory)
        self.owner = o.KvCacheOwner()
        self.ordinal = 0

    def new_job(self, tokens=1, *, staging=None, tag=None):
        self.ordinal += 1
        index = self.ordinal
        # Keep addresses above 32 bits, with distinguishable lower bits.
        new_k = 0x100000000 + index * 0x100000
        new_v = new_k + 0x10000
        raw_k, raw_v = token_bytes(tokens, index * 109), token_bytes(tokens, index * 313)
        producer(self.memory, new_k, raw_k, index * 10)
        producer(self.memory, new_v, raw_v, index * 10 + 1)
        state = self.fence.state
        job = o.KvCacheJob(index if tag is None else tag, state.k_root, state.v_root,
                            state.valid_tokens, new_k, new_v,
                            0x200000000 + index * 0x100000 if staging is None else staging,
                            tokens, state.generation, state.generation)
        for base, extent in job.output_spans:
            self.memory.allocate_output(base, extent)
        return job, raw_k, raw_v

    def start(self, tokens=1, **kwargs):
        job, raw_k, raw_v = self.new_job(tokens, **kwargs)
        driver = TypedKvCacheDriver(self.owner, self.memory, job, self.fence)
        return driver, raw_k, raw_v

    def until(self, driver, condition, controls=None):
        for tick in range(20000):
            if condition(driver):
                return
            driver.tick(**({} if controls is None else controls(driver, tick)))
        self.fail('bounded tiny software transaction did not complete')

    def finish(self, driver, controls=None):
        self.until(driver, lambda d: d.response is not None, controls)
        return driver.response

    def final_write(self, driver):
        return (driver.pending is not None and driver.owner.request.write and
                driver.counts['write_bytes'] == driver.job.write_bytes)

    def synthetic_downstream(self, driver, *, status=None, accepted=True):
        # Deliberately a stand-in for an eventual actual final residual owner.
        base = 0x300000000 + driver.job.tag * 0x100000
        raw = bytes((i + driver.job.tag) % 256 for i in range(64))
        producer(self.memory, base, raw, 1000 + driver.job.tag)
        return FullBlockTerminal(driver.job.tag, driver.job.current_generation, driver.receipt,
                                  status, accepted, 1000 + driver.job.tag, base, 64, 64)

    def commit(self, driver):
        return self.fence.commit_after_fullblock(driver.receipt, self.synthetic_downstream(driver))

    def test_actual_cold_then_carried_on_same_memory_1_plus_2_tokens(self):
        cold, k1, v1 = self.start(1)
        initial = self.fence.state
        with patch.object(self.memory, 'read64', wraps=self.memory.read64) as reads:
            self.finish(cold, lambda _, i: dict(memory_ready=i % 3 != 0,
                memory_response_ready=i % 4 != 0, response_ready=i % 5 != 0))
        self.assertEqual([r.raw() for r in cold.outputs], [k1, v1])
        self.assertEqual(cold.counts['read_bytes'], 2048)
        self.assertTrue(all(call.args[0] in range(cold.job.new_k, cold.job.new_k + 1024, 64) or
                            call.args[0] in range(cold.job.new_v, cold.job.new_v + 1024, 64)
                            for call in reads.call_args_list))
        self.assertEqual(len(reads.call_args_list), 32)
        self.assertIs(self.fence.state, initial)
        self.assertEqual(cold.response.current_generation, 0)
        self.assertEqual(cold.receipt.committed_before, CommittedKvState())
        self.assertEqual(self.commit(cold).generation, 1)
        old_bytes = tuple(r.raw() for r in cold.outputs)
        carried, k2, v2 = self.start(2)
        self.assertIs(carried.memory, cold.memory)
        self.assertIs(carried.inputs[0], cold.outputs[0])
        self.assertIs(carried.inputs[1], cold.outputs[1])
        with patch.object(self.memory, 'read64', wraps=self.memory.read64) as reads:
            self.finish(carried)
        self.assertEqual([r.raw() for r in carried.outputs], [k1 + k2, v1 + v2])
        self.assertEqual(tuple(r.raw() for r in cold.outputs), old_bytes)
        self.assertEqual(carried.counts['read_bytes'], 6144)
        self.assertEqual(carried.counts['write_bytes'], 6144)
        self.assertEqual(carried.counts['ack_bytes'], 6144)
        self.assertEqual(carried.job.staging_v - carried.job.staging_k, 256 * 1024)
        self.assertEqual([r.extent for r in carried.outputs], [3072, 3072])
        self.assertEqual(self.fence.state.valid_tokens, 1)
        self.assertEqual(carried.response.current_generation, 1)
        self.assertEqual(len(reads.call_args_list), 96)
        state = self.commit(carried)
        self.assertEqual((state.k_root, state.v_root, state.valid_tokens, state.generation),
                         (carried.job.staging_k, carried.job.staging_v, 3, 2))
        self.assertEqual(carried.owner.report()['arithmetic_resources'], 0)
        self.assertFalse(carried.report()['fullblock_executed'])

    def test_exact_m128_cold_and_carried256_descriptor_extents_without_execution(self):
        cold = o.KvCacheJob(1, 0, 0, 0, 0x100000, 0x200000, 0x400000, 128, 0, 0)
        cold.validate()
        carried = o.KvCacheJob(2, cold.staging_k, cold.staging_v, 128,
                               0x1000000, 0x2000000, 0x3000000, 128, 1, 1)
        carried.validate()
        self.assertEqual(cold.output_spans, ((0x400000, 131072), (0x440000, 131072)))
        self.assertEqual(carried.output_spans, ((0x3000000, 262144), (0x3040000, 262144)))

    def test_final_second_span_ack_and_held_terminal_keep_both_private(self):
        driver, _, _ = self.start()
        with patch.object(self.memory, 'publish_many', wraps=self.memory.publish_many) as publish:
            self.until(driver, self.final_write)
            self.assertEqual(self.memory._resolve(driver.owner.request.address).base, driver.job.staging_v)
            for _ in range(3):
                driver.tick(memory_response_ready=False)
                self.assertTrue(all(not r.published for r in driver.outputs))
                self.assertIsNone(self.owner.ports()['response'])
            driver.tick(response_ready=False)
            held = self.owner.ports()['response']
            for _ in range(3):
                driver.tick(response_ready=False)
                self.assertIs(self.owner.ports()['response'], held)
                for region in driver.outputs:
                    with self.assertRaisesRegex(ValueError, 'read before producer terminal'):
                        self.memory.read64(region.base)
            self.assertEqual(publish.call_count, 0)
            with self.assertRaisesRegex(ValueError, 'held completion'):
                self.owner.reset()
            driver.tick()
            self.assertEqual(publish.call_count, 1)
            self.assertEqual(publish.call_args.args[0], (driver.job.staging_k, driver.job.staging_v))
        self.assertEqual(driver.response, held)
        self.assertTrue(all(r.published for r in driver.outputs))
        self.assertEqual(self.fence.state.generation, 0)

    def test_second_span_final_ack_failure_does_not_publish_or_advance(self):
        driver, _, _ = self.start(3)
        self.until(driver, self.final_write)
        driver.tick(ack_error=True, response_ready=False)
        held = self.owner.ports()['response']
        for _ in range(2):
            driver.tick(response_ready=False)
            self.assertIs(self.owner.ports()['response'], held)
        self.finish(driver)
        self.assertEqual(driver.response.status, 'Memory')
        self.assertEqual(driver.response.write_bytes, driver.job.write_bytes - 64)
        self.assertFalse(any(r.published for r in driver.outputs))
        self.assertEqual(driver.outputs[0].written, driver.outputs[0].acknowledged)
        self.assertEqual(len(driver.outputs[1].written - driver.outputs[1].acknowledged), 1)
        self.assertIsNone(driver.receipt)
        self.assertEqual(self.fence.state, CommittedKvState())
        self.assertIsNone(self.memory.pending)
        self.owner.reset()
        with self.assertRaisesRegex(ValueError, 'fresh staging'):
            TypedKvCacheDriver(self.owner, self.memory, driver.job, self.fence)
        retry, k, v = self.start(3)
        self.finish(retry)
        self.assertEqual([r.raw() for r in retry.outputs], [k, v])

    def test_failed_carried_stage_preserves_old_committed_prefix(self):
        cold, _, _ = self.start()
        self.finish(cold)
        committed = self.commit(cold)
        old = tuple(r.raw() for r in cold.outputs)
        carried, _, _ = self.start(2)
        self.until(carried, self.final_write)
        carried.tick(ack_error=True)
        self.finish(carried)
        self.assertIs(self.fence.state, committed)
        self.assertEqual(tuple(r.raw() for r in cold.outputs), old)
        self.assertTrue(all(r.published for r in cold.outputs))
        self.assertFalse(any(r.published for r in carried.outputs))

    def test_abort_and_reset_drain_read_and_write_before_failed_terminal(self):
        for action in ('abort', 'reset'):
            for write in (False, True):
                with self.subTest(action=action, write=write):
                    self.setUp()
                    driver, _, _ = self.start()
                    self.until(driver, lambda d: d.pending is not None and d.owner.request.write is write)
                    request = self.owner.request
                    driver.tick(**{action: True, 'memory_response_ready': False})
                    self.assertEqual(self.owner.state, 'drain')
                    self.assertIs(self.owner.request, request)
                    self.assertIsNone(self.owner.ports()['response'])
                    with self.assertRaisesRegex(ValueError, 'drained transport'):
                        self.owner.reset()
                    driver.tick(response_ready=False)
                    self.assertEqual(self.owner.state, 'finish')
                    self.finish(driver)
                    self.assertEqual(driver.response.status, 'Aborted')
                    self.assertIsNone(self.memory.pending)
                    self.assertFalse(any(r.published for r in driver.outputs))
                    self.assertEqual(self.owner.state, 'locked')
                    self.owner.reset()
                    self.assertTrue(self.owner.ports()['job_ready'])

    def test_abort_cancels_held_success_even_with_ready_and_reset_cannot_erase(self):
        driver, _, _ = self.start()
        self.until(driver, lambda d: d.owner.state == 'finish', lambda *_: dict(response_ready=False))
        with self.assertRaisesRegex(ValueError, 'held completion'):
            driver.tick(reset=True)
        event = driver.tick(abort=True, response_ready=True)
        self.assertFalse(event['response_fire'])
        self.finish(driver)
        self.assertEqual(driver.response.status, 'Aborted')
        self.assertFalse(any(r.published for r in driver.outputs))

    def test_abort_before_first_transfer_requires_new_staging_even_with_zero_writes(self):
        driver, _, _ = self.start()
        driver.tick(abort=True)
        self.finish(driver)
        self.assertEqual(driver.counts['memory_requests'], 0)
        self.owner.reset()
        with self.assertRaisesRegex(ValueError, 'fresh staging'):
            TypedKvCacheDriver(self.owner, self.memory, driver.job, self.fence)

    def test_source_integrity_failure_abort_drains_read_write_and_held_success_then_fresh_retry(self):
        for phase in ('read', 'write', 'held'):
            for detect_first in (False, True):
                for corrupt_guard in (False, True):
                    with self.subTest(phase=phase, detect_first=detect_first, guard=corrupt_guard):
                        self.setUp()
                        cold, old_k, old_v = self.start()
                        self.finish(cold)
                        committed = self.commit(cold)
                        driver, _, _ = self.start()
                        if phase == 'held':
                            self.until(driver, lambda d: d.owner.state == 'finish',
                                       lambda *_: dict(response_ready=False))
                        else:
                            address = (driver.job.new_k if phase == 'read' else
                                       driver.job.staging_k + driver.job.previous_tokens * 1024)
                            self.until(driver, lambda d: d.pending is not None and
                                       d.owner.request.address == address and
                                       d.owner.request.write is (phase == 'write'))
                        input_region = self.memory.regions[driver.job.new_k]
                        input_region.storage[0 if corrupt_guard else 64] ^= 1
                        request, pending, physical = self.owner.request, driver.pending, self.memory.pending
                        responses_before = driver.counts['memory_responses']
                        requests_before = driver.counts['memory_requests']
                        if detect_first:
                            with self.assertRaisesRegex(ValueError, 'source bytes or producer coverage changed'):
                                driver.tick(memory_response_ready=False, response_ready=False)
                            self.assertTrue(self.owner.poison)
                        driver.tick(abort=True, memory_response_ready=False)
                        self.assertTrue(self.owner.poison)
                        self.assertFalse(any(r.published for r in driver.outputs))
                        if phase != 'held':
                            self.assertEqual(self.owner.state, 'drain')
                            self.assertIs(self.owner.request, request)
                            self.assertIs(driver.pending, pending)
                            self.assertIs(self.memory.pending, physical)
                            driver.tick(memory_response_ready=False)
                            self.assertEqual(driver.counts['memory_responses'], responses_before)
                            driver.tick(response_ready=False)
                        self.finish(driver)
                        self.assertEqual(driver.response.status, 'Aborted')
                        self.assertEqual(driver.counts['memory_requests'], requests_before)
                        self.assertEqual(driver.counts['memory_responses'], responses_before + (phase != 'held'))
                        self.assertEqual(self.owner.counts['owner_results'], 1)
                        self.assertEqual(driver.report()['integrity_errors'],
                                         ['published source bytes or producer coverage changed'])
                        self.assertTrue(self.owner.poison)
                        self.assertIsNone(self.memory.pending)
                        self.assertIsNone(self.fence.pending_receipt)
                        self.assertIs(self.fence.state, committed)
                        self.assertEqual([r.raw() for r in cold.outputs], [old_k, old_v])
                        self.owner.reset()
                        retry, new_k, new_v = self.start()
                        self.finish(retry)
                        self.assertEqual([r.raw() for r in retry.outputs], [old_k + new_k, old_v + new_v])
                        self.assertNotEqual(retry.job.staging_k, driver.job.staging_k)
                        self.assertEqual(driver.report()['owner']['status'], 'Aborted')
                        self.assertEqual(driver.report()['owner']['accepted']['owner_results'], 1)

    def test_source_integrity_failure_reset_drains_inflight_read_and_write(self):
        for write in (False, True):
            with self.subTest(write=write):
                self.setUp()
                driver, _, _ = self.start()
                self.until(driver, lambda d: d.pending is not None and d.owner.request.write is write)
                driver.inputs[0].storage[64] ^= 1
                driver.tick(reset=True, memory_response_ready=False)
                self.assertEqual(self.owner.state, 'drain')
                self.finish(driver)
                self.assertEqual(driver.response.status, 'Aborted')
                self.assertTrue(driver.report()['integrity_errors'])
                self.assertIsNone(self.memory.pending)
                self.assertFalse(any(r.published for r in driver.outputs))
                self.owner.reset()
                retry, _, _ = self.start()
                self.finish(retry)

    def test_restoring_corrupt_bytes_does_not_clear_latched_failure(self):
        driver, _, _ = self.start()
        driver.tick()
        driver.inputs[0].storage[64] ^= 1
        with self.assertRaisesRegex(ValueError, 'source bytes or producer coverage changed'):
            driver.tick()
        driver.inputs[0].storage[64] ^= 1
        with self.assertRaisesRegex(ValueError, 'latched integrity failure'):
            driver.tick()
        self.assertTrue(self.owner.poison)
        driver.tick(abort=True)
        self.finish(driver)
        self.assertEqual(driver.response.status, 'Aborted')

    def test_integrity_cancellation_still_rejects_replaced_inflight_obligation(self):
        driver, _, _ = self.start()
        self.until(driver, lambda d: d.pending is not None and d.owner.request.write)
        original = driver.pending
        driver.inputs[0].storage[64] ^= 1
        driver.pending = replace(original, tag=original.tag + 1)
        with self.assertRaisesRegex(ValueError, 'transport obligation replaced'):
            driver.tick(abort=True)
        self.assertIsNotNone(self.memory.pending)
        driver.pending = original
        driver.tick(abort=True)
        self.finish(driver)
        self.assertEqual(driver.response.status, 'Aborted')
        self.assertIsNone(self.memory.pending)

    def test_read_error_has_no_output_and_releases_no_external_generation(self):
        driver, _, _ = self.start()
        driver.tick()
        driver.tick(read_error=True)
        self.finish(driver)
        self.assertEqual(driver.response.status, 'Memory')
        self.assertEqual(driver.counts['write_bytes'], 0)
        self.assertEqual(self.fence.state.generation, 0)
        self.assertIsNone(driver.receipt)

    def test_invalid_descriptor_rejected_before_any_owner_dma(self):
        good, _, _ = self.new_job()
        defects = ({'tag': -1}, {'tag': 1 << 32}, {'tag': True}, {'tokens': 0}, {'tokens': True},
                   {'tokens': 129}, {'capacity': 255}, {'capacity': True}, {'dtype': 'fp16'},
                   {'dtype': b'bf16'}, {'new_k': good.new_k + 2}, {'new_v': good.new_k},
                   {'staging_k': good.new_k}, {'staging_k': (1 << 56) - 64},
                   {'new_k': 1 << 56}, {'previous_k': 64}, {'previous_v': 64},
                   {'previous_tokens': -1}, {'expected_generation': 1}, {'current_generation': -1},
                   {'current_generation': True}, {'expected_generation': True},
                   {'expected_generation': (1 << 64) - 1, 'current_generation': (1 << 64) - 1})
        with patch.object(self.memory, 'read64', wraps=self.memory.read64) as read:
            with patch.object(self.memory, 'begin_write', wraps=self.memory.begin_write) as write:
                for defect in defects:
                    with self.subTest(defect=defect), self.assertRaises(ValueError):
                        TypedKvCacheDriver(self.owner, self.memory, replace(good, **defect), self.fence)
                self.assertEqual(read.call_count, 0)
                self.assertEqual(write.call_count, 0)
        self.assertIsNone(self.owner.job)
        with self.assertRaises(FrozenInstanceError):
            good.tag = 2

    def test_carried_capacity_overflow_and_previous_reservation_alias(self):
        base = o.KvCacheJob(1, 0x400000, 0x440000, 128,
                            0x1000000, 0x2000000, 0x3000000, 128, 1, 1)
        for defect in ({'previous_tokens': 129}, {'previous_v': 0x450000},
                       {'previous_k': (1 << 56) - 0x40000, 'previous_v': 1 << 56},
                       {'staging_k': 0x420000}, {'new_k': 0x430000}):
            with self.subTest(defect=defect), self.assertRaises(ValueError):
                replace(base, **defect).validate()

    def test_unpublished_readonly_and_wrong_extent_inputs_rejected(self):
        for defect in ('unpublished', 'readonly', 'coverage', 'extent'):
            with self.subTest(defect=defect):
                self.setUp()
                job, _, _ = self.new_job()
                region = self.memory.regions[job.new_k]
                if defect == 'unpublished': region.published = False
                elif defect == 'readonly': region.readonly = True
                elif defect == 'coverage': region.written.remove(0)
                else: region.extent += 64
                with self.assertRaises(ValueError):
                    TypedKvCacheDriver(self.owner, self.memory, job, self.fence)
                self.assertIsNone(self.owner.job)

    def test_lying_nonempty_source_coverage_rejected_at_admission_and_during_job(self):
        for moment in ('admission', 'active'):
            for field in ('written', 'acknowledged'):
                with self.subTest(moment=moment, field=field):
                    self.setUp()
                    job, _, _ = self.new_job()
                    region = self.memory.regions[job.new_k]
                    self.assertEqual(len(getattr(region, field)), 16)
                    driver = None if moment == 'admission' else TypedKvCacheDriver(
                        self.owner, self.memory, job, self.fence)
                    setattr(region, field, LyingCoverage())
                    self.assertTrue(getattr(region, field) == set(range(0, 1024, 64)))
                    self.assertEqual(frozenset(getattr(region, field)), frozenset())
                    with self.assertRaisesRegex(ValueError, 'producer data/ACK|producer coverage changed'):
                        if driver is None:
                            TypedKvCacheDriver(self.owner, self.memory, job, self.fence)
                        else:
                            driver.tick()
                    self.assertEqual(self.owner.counts['read_requests'], 0)
                    self.assertIsNone(self.memory.pending)

    def test_lying_coverage_rejected_for_staged_final_and_committed_fence_spans(self):
        for target in ('staged', 'final', 'committed'):
            for field in ('written', 'acknowledged'):
                with self.subTest(target=target, field=field):
                    self.setUp()
                    driver, _, _ = self.start()
                    self.finish(driver)
                    terminal = self.synthetic_downstream(driver)
                    region = (self.memory.regions[terminal.final_output_root] if target == 'final'
                              else driver.outputs[0])
                    if target == 'committed':
                        self.fence.commit_after_fullblock(driver.receipt, terminal)
                        next_job, _, _ = self.new_job()
                    old_state = self.fence.state
                    self.assertTrue(getattr(region, field))
                    setattr(region, field, LyingCoverage())
                    with self.assertRaisesRegex(ValueError, 'staging changed|residual producer|committed prefix changed'):
                        if target == 'committed':
                            TypedKvCacheDriver(self.owner, self.memory, next_job, self.fence)
                        else:
                            self.fence.commit_after_fullblock(driver.receipt, terminal)
                    self.assertIs(self.fence.state, old_state)

    def test_coverage_requires_exact_integer_offsets(self):
        for value in (False, OffsetImpostor(0)):
            for target in ('source', 'staged', 'final'):
                with self.subTest(value=type(value).__name__, target=target):
                    self.setUp()
                    if target == 'source':
                        job, _, _ = self.new_job()
                        region = self.memory.regions[job.new_k]
                    else:
                        driver, _, _ = self.start()
                        self.finish(driver)
                        terminal = self.synthetic_downstream(driver)
                        region = (driver.outputs[0] if target == 'staged'
                                  else self.memory.regions[terminal.final_output_root])
                    region.acknowledged.remove(0)
                    region.acknowledged.add(value)
                    self.assertEqual(region.acknowledged, set(range(0, region.extent, 64)))
                    with self.assertRaisesRegex(ValueError, 'producer data/ACK|staging changed'):
                        if target == 'source':
                            TypedKvCacheDriver(self.owner, self.memory, job, self.fence)
                        else:
                            self.fence.commit_after_fullblock(driver.receipt, terminal)

    def test_tampered_job_source_request_or_pending_identity_rejected(self):
        for defect in ('job', 'source', 'request', 'pending'):
            with self.subTest(defect=defect):
                self.setUp()
                driver, _, _ = self.start()
                if defect == 'job': object.__setattr__(driver.job, 'tag', 20)
                elif defect == 'source': driver.inputs[0].storage[64] ^= 1
                elif defect == 'request':
                    self.owner.request = replace(self.owner.request, address=driver.job.new_v)
                else:
                    driver.tick()
                    driver.pending = replace(driver.pending, tag=3)
                with self.assertRaises(ValueError):
                    driver.tick()
                self.assertFalse(any(r.published for r in driver.outputs))

    def test_output_data_tamper_during_held_terminal_prevents_publication(self):
        driver, _, _ = self.start()
        self.until(driver, lambda d: d.owner.state == 'finish', lambda *_: dict(response_ready=False))
        driver.outputs[1].storage[64] ^= 1
        with self.assertRaisesRegex(ValueError, 'actual accepted write data'):
            driver.tick()
        self.assertFalse(any(r.published for r in driver.outputs))
        self.assertEqual(self.owner.state, 'finish')
        self.assertEqual(self.owner.counts['owner_results'], 0)
        driver.tick(abort=True)
        self.finish(driver)
        self.assertEqual(driver.response.status, 'Aborted')
        self.owner.reset()
        retry, _, _ = self.start()
        self.finish(retry)

    def test_fence_requires_exact_accepted_fullblock_evidence_and_ack_coverage(self):
        driver, _, _ = self.start()
        self.finish(driver)
        receipt = driver.receipt
        terminal = self.synthetic_downstream(driver)
        initial = self.fence.state
        with self.assertRaises(ValueError):
            self.fence.commit_after_fullblock(receipt, True)
        for defect in ({'tag': driver.job.tag + 1}, {'expected_generation': 1}, {'accepted': False},
                       {'accepted': 1}, {'status': 'Memory'}, {'final_write_bytes': 0},
                       {'kv_receipt': replace(receipt)}, {'final_output_root': receipt.k_root},
                       {'final_owner_tag': True}, {'final_output_bytes': 128}):
            with self.subTest(defect=defect), self.assertRaises(ValueError):
                self.fence.commit_after_fullblock(receipt, replace(terminal, **defect))
            self.assertIs(self.fence.state, initial)
        for region in driver.outputs:
            region.acknowledged.remove(0)
            with self.assertRaises(ValueError):
                self.fence.commit_after_fullblock(receipt, terminal)
            self.assertIs(self.fence.state, initial)
            region.acknowledged.add(0)
        with self.assertRaises(ValueError):
            self.fence.commit_after_fullblock(replace(receipt), terminal)
        self.fence.commit_after_fullblock(receipt, terminal)
        with self.assertRaisesRegex(ValueError, 'stale, duplicate'):
            self.fence.commit_after_fullblock(receipt, terminal)

    def test_downstream_failure_discards_staging_without_changing_committed_state(self):
        cold, _, _ = self.start()
        self.finish(cold)
        state = self.commit(cold)
        carried, _, _ = self.start(2)
        self.finish(carried)
        failure = self.synthetic_downstream(carried, status='Memory')
        with self.assertRaises(ValueError):
            self.fence.commit_after_fullblock(carried.receipt, failure)
        self.assertIs(self.fence.discard_after_fullblock(carried.receipt, failure), state)
        self.assertIs(self.fence.state, state)
        self.assertTrue(all(r.published for r in carried.outputs))
        self.assertNotEqual(self.fence.state.k_root, carried.job.staging_k)
        retry, _, _ = self.start(2)
        self.finish(retry)
        self.assertEqual(retry.job.previous_k, cold.job.staging_k)

    def test_failed_downstream_terminal_cannot_discard_undrained_write(self):
        driver, _, _ = self.start()
        self.finish(driver)
        terminal = self.synthetic_downstream(driver, status='Aborted')
        self.memory.allocate_output(0x400000000, 64)
        self.memory.begin_write(WriteCommand(0x400000000, 1, 777))
        self.memory.write_data((0,) * 32, True)
        with self.assertRaisesRegex(ValueError, 'before write drain'):
            self.fence.discard_after_fullblock(driver.receipt, terminal)
        self.assertIs(self.fence.pending_receipt, driver.receipt)
        self.memory.acknowledge(WriteAck(777, True, 64))
        self.fence.discard_after_fullblock(driver.receipt, terminal)
        self.assertIsNone(self.fence.pending_receipt)

    def test_old_prefix_tampering_is_rejected_between_jobs_and_before_commit_or_discard(self):
        for moment in ('between_jobs', 'commit', 'discard'):
            with self.subTest(moment=moment):
                self.setUp()
                cold, _, _ = self.start()
                self.finish(cold)
                state = self.commit(cold)
                if moment == 'between_jobs':
                    job, _, _ = self.new_job()
                    cold.outputs[0].storage[64] ^= 1
                    with self.assertRaisesRegex(ValueError, 'committed prefix changed'):
                        TypedKvCacheDriver(self.owner, self.memory, job, self.fence)
                else:
                    carried, _, _ = self.start()
                    self.finish(carried)
                    terminal = self.synthetic_downstream(carried, status='Aborted' if moment == 'discard' else None)
                    cold.outputs[0].storage[64] ^= 1
                    action = self.fence.discard_after_fullblock if moment == 'discard' else self.fence.commit_after_fullblock
                    with self.assertRaisesRegex(ValueError, 'committed prefix changed'):
                        action(carried.receipt, terminal)
                self.assertIs(self.fence.state, state)

    def test_preexisting_upstream_span_cannot_masquerade_as_final_output(self):
        driver, _, _ = self.start()
        self.finish(driver)
        terminal = self.synthetic_downstream(driver)
        fake = replace(terminal, final_output_root=driver.job.new_k,
                       final_output_bytes=1024, final_write_bytes=1024)
        with self.assertRaisesRegex(ValueError, 'already published before'):
            self.fence.commit_after_fullblock(driver.receipt, fake)

    def test_source_identity_separate_and_unchanged_before_publication(self):
        driver, _, _ = self.start()
        self.assertEqual(set(driver.identity['source_sha256']), set(o.NEW_SOURCES))
        self.until(driver, lambda d: d.owner.state == 'finish', lambda *_: dict(response_ready=False))
        with patch('candidates.qwen35_attention_prefill.kv_cache.driver.source_identity', return_value={}):
            with self.assertRaisesRegex(ValueError, 'source identity changed'):
                driver.tick()
        self.assertFalse(any(r.published for r in driver.outputs))

    def test_reported_source_identity_cannot_rewrite_admission_snapshot(self):
        for drift in (False, True):
            with self.subTest(drift=drift):
                self.setUp()
                driver, _, _ = self.start()
                admitted = deepcopy(driver.identity)
                self.assertIsNot(driver.identity, driver._identity)
                self.assertIsNot(driver.identity['source_sha256'], driver._identity['source_sha256'])
                self.until(driver, lambda d: d.owner.state == 'finish', lambda *_: dict(response_ready=False))
                changed = deepcopy(admitted)
                changed['source_sha256'][o.NEW_SOURCES[1]] = '0' * 64
                driver.identity['source_sha256'][o.NEW_SOURCES[1]] = '0' * 64
                with patch('candidates.qwen35_attention_prefill.kv_cache.driver.source_identity',
                           return_value=changed if drift else admitted):
                    with self.assertRaisesRegex(ValueError, 'source identity changed'):
                        driver.tick()
                    self.assertEqual(self.owner.state, 'finish')
                    self.assertEqual(self.owner.counts['owner_results'], 0)
                    self.assertEqual(driver._identity, admitted)
                    self.assertEqual(driver.report()['identity'], admitted)
                    driver.tick(abort=True)
                    self.finish(driver)
                self.assertEqual(driver.response.status, 'Aborted')
                self.assertFalse(any(r.published for r in driver.outputs))

    def test_changed_receipt_or_committed_state_cannot_be_promoted(self):
        for target, field, value in (('receipt', 'tag', 999), ('receipt', 'write_bytes', 64),
                                     ('state', 'generation', 999)):
            with self.subTest(target=target, field=field):
                self.setUp()
                driver, _, _ = self.start()
                self.finish(driver)
                terminal = self.synthetic_downstream(driver)
                obj = driver.receipt if target == 'receipt' else self.fence.state
                object.__setattr__(obj, field, value)
                with self.assertRaisesRegex(ValueError, 'descriptor changed|receipt changed'):
                    self.fence.commit_after_fullblock(driver.receipt, terminal)

    def test_second_job_rejected_until_block_success_or_failure_retires(self):
        first, _, _ = self.start()
        self.finish(first)
        job, _, _ = self.new_job()
        with self.assertRaisesRegex(ValueError, 'has not retired'):
            TypedKvCacheDriver(self.owner, self.memory, job, self.fence)
        self.assertEqual(self.fence.state.generation, 0)

    def test_stale_generation_and_wrong_committed_prefix_rejected_before_dma(self):
        cold, _, _ = self.start()
        self.finish(cold)
        self.commit(cold)
        good, _, _ = self.new_job()
        for defect in ({'current_generation': 0, 'expected_generation': 0},
                       {'previous_k': 0, 'previous_v': 0, 'previous_tokens': 0},
                       {'previous_tokens': 2}):
            with self.subTest(defect=defect), self.assertRaisesRegex(ValueError, 'committed prefix/generation'):
                TypedKvCacheDriver(self.owner, self.memory, replace(good, **defect), self.fence)


class KvOwnerProtocolTests(unittest.TestCase):
    def setUp(self):
        self.owner = o.KvCacheOwner()
        self.job = o.KvCacheJob(7, 0, 0, 0, 0x10000, 0x20000, 0x100000, 1, 0, 0)
        self.owner.tick(job=self.job)

    def test_held_request_is_stable_and_full_address_is_not_truncated(self):
        request = self.owner.ports()['memory']
        for _ in range(4):
            event = self.owner.tick(memory_ready=False)
            self.assertIs(event['memory'], request)
            self.assertFalse(event['memory_fire'])
        self.assertEqual(request.tag, 7 << 32)
        self.assertEqual(request.nbytes, 64)

    def test_bad_read_tag_count_type_and_data_fail_once_and_lock(self):
        for defect in ('tag', 'nbytes', 'data', 'error_type', 'wrong_type'):
            with self.subTest(defect=defect):
                self.setUp()
                request = self.owner.ports()['memory']
                self.owner.tick(memory_ready=True)
                response = o.MemoryResponse(request.tag, bytes(64))
                if defect == 'tag': response = replace(response, tag=request.tag + 1)
                elif defect == 'nbytes': response = replace(response, nbytes=32)
                elif defect == 'data': response = replace(response, data=bytes(63))
                elif defect == 'error_type': response = replace(response, error=0)
                else: response = object()
                event = self.owner.tick(memory_response=response)
                self.assertTrue(event['memory_response_fire'])
                held = self.owner.ports()['response']
                self.assertEqual(held.status, 'Protocol')
                self.owner.tick(response_ready=False)
                self.assertIs(self.owner.ports()['response'], held)
                self.owner.tick(response_ready=True)
                self.assertEqual(self.owner.state, 'locked')
                self.assertEqual(self.owner.counts['owner_results'], 1)

    def test_bad_write_ack_drains_and_prevents_more_dma(self):
        request = self.owner.ports()['memory']
        self.owner.tick(memory_ready=True)
        self.owner.tick(memory_response=o.MemoryResponse(request.tag, bytes(range(64))))
        write = self.owner.ports()['memory']
        self.assertEqual(write.data, bytes(range(64)))
        self.assertEqual(write.mask, (1 << 64) - 1)
        self.owner.tick(memory_ready=True)
        self.owner.tick(memory_response=o.MemoryResponse(write.tag + 1))
        self.assertIsNone(self.owner.ports()['memory'])
        self.assertEqual(self.owner.ports()['response'].status, 'Protocol')
        self.assertEqual(self.owner.ack_bytes, 0)


if __name__ == '__main__':
    unittest.main()
