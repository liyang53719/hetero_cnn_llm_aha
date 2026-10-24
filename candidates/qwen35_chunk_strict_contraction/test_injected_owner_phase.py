"""Real owner/driver lifecycle, explicitly injected phase, never full-owner PASS."""
from collections import Counter
from dataclasses import replace
import struct
import unittest

import numpy as np

from candidates.qwen35_gdn_prefill.chunk import model as upstream
from candidates.qwen35_gdn_prefill.chunk.vector import Vector16, LEGACY_POLICY
from candidates.qwen35_gdn_prefill.prep.scalar import PrepScalar
from candidates.qwen35_gdn_prefill.rms_owner import MemoryResponse
from candidates.qwen2_resident_matrix.transposed_down.model import WriteCommand, WriteAck
from .injected_owner_phase import InjectedOwnerPhase


class InjectedOwnerPhaseTests(unittest.TestCase):
    def fixture(self, phase=5, *, defect=None, observe=None):
        rng = np.random.default_rng(900 + phase)
        a = rng.uniform(-.2, .2, (64, 128)).astype('<f4')
        kt = rng.uniform(-.3, .3, (128, 64)).astype('<f4')
        pair = np.tril(rng.uniform(.3, 1., (64, 64)).astype('<f4'))
        np.fill_diagonal(pair, 1.)
        if defect == 'underflow':
            a.view(np.uint32)[0, :16] = 0x00800000
            kt.view(np.uint32)[0, :16] = 0x3f7fffff
        elif defect == 'nonfinite':
            a.view(np.uint32)[0, 0] = 0x7fc00000
        # Same explicit noncomputing lease shell used in upstream TransportOnly
        # tests. No native library, fake numerical result or Vector op is used.
        vector = object.__new__(Vector16)
        vector.client, vector.resource_address = None, id(vector)
        vector.exception_policy, vector.fatal_mask = LEGACY_POLICY, 30
        vector.calls, vector.lane_ops, vector.host_calls, vector.flags = (Counter() for _ in range(4))
        scalar = PrepScalar(enable_softplus=True)
        owner = upstream.ChunkOwner(scalar, vector, heads=1)
        job = upstream.ChunkJob(41 + phase, 0x100000, 0x500000, 0x510000,
                                0x520000, 0x600000, 64, heads=1)
        memory = upstream.TypedMemory()
        # Admission-only synthetic input, not a claim that Prep was executed.
        # Real typed writes/ACKs/publish, never direct coverage-set fabrication.
        memory.allocate_output(job.input, job.input_bytes)
        for offset in range(0, job.input_bytes, 1024):
            memory.begin_write(WriteCommand(job.input + offset, 16, offset))
            for beat in range(16):
                memory.write_data((0,) * 32, beat == 15)
            memory.acknowledge(WriteAck(offset, False, 1024))
        memory.publish(job.input, (0, None, job.input_bytes))
        for base, size in ((job.output, job.output_bytes), (job.state_out, job.state_bytes),
                           (job.scratch, job.scratch_bytes)):
            memory.allocate_output(base, size)
        injection = InjectedOwnerPhase(owner, job, phase=phase,
                    operands=tuple(x.tobytes() for x in (a, kt, pair)), observe=observe)
        driver = upstream.TypedChunkDriver(owner, memory, job)
        return driver, injection, (a, kt, pair)

    def until(self, driver, predicate, limit=75000):
        for _ in range(limit):
            if predicate():
                return
            self.assertIsNone(driver.response, 'unexpected early owner terminal')
            driver.tick(response_ready=False)
        self.fail('bounded real owner transport target not reached')

    def phase_read(self, driver, injection):
        self.until(driver, lambda: driver.pending is not None and not driver.pending_request.write)
        self.assertEqual(injection.fixture_write_beats, 1280)

    def phase_write(self, driver, injection, index=0):
        address = injection.matrices[-1].base + 64 * index
        self.until(driver, lambda: driver.pending is not None and driver.pending_request.address == address)
        self.assertTrue(driver.pending_request.write)

    def retire_failure(self, driver, status):
        self.assertEqual(driver.owner.state, 'finish')
        result = driver.owner.result
        self.assertEqual(result.status, status)
        self.assertFalse(result.staging_complete)
        self.assertEqual(result.write_bytes, 0)
        self.assertIsNone(driver.pending)
        self.assertIsNone(driver.memory.pending)
        self.assertIsNone(driver.owner.scalar.client)
        self.assertIsNone(driver.owner.vector.client)
        for _ in range(3):
            driver.tick(response_ready=False)
            self.assertIs(driver.owner.result, result)
        with self.assertRaisesRegex(ValueError, 'retired terminal'):
            driver.owner.reset()
        driver.tick()
        self.assertIs(driver.response, result)
        self.assertEqual(driver.owner.counts['owner_results'], 1)
        self.assertEqual(driver.owner.state, 'locked')
        for region in (driver.output, driver.state_out, driver.scratch):
            self.assertFalse(region.published)
        self.assertFalse(driver.output.written or driver.state_out.written)
        self.assertFalse(result.state_committed or result.history_committed or result.generation_advanced)
        self.assertFalse(driver.owner.vector.calls or driver.owner.vector.lane_ops)

    def test_full_ut_qk_real_driver_exhaustion_is_not_chunk_success(self):
        for phase in (5, 6):
            with self.subTest(phase=phase):
                driver, injection, (a, kt, pair) = self.fixture(phase)
                self.assertIs(type(driver.owner), upstream.ChunkOwner)
                self.assertIs(driver.owner.tick.__func__, upstream.ChunkOwner.tick)
                self.assertIs(driver.tick.__func__, upstream.TypedChunkDriver.tick)
                for name in ('_matmul', '_mul_add', '_read', '_write', '_advance', '_finish'):
                    self.assertIs(getattr(driver.owner, name).__func__, getattr(upstream.ChunkOwner, name))
                # Independent NumPy separate Mul/Add final-word oracle, no BLAS.
                expected = np.zeros((64, 64), np.float32)
                for k in range(128):
                    product = np.multiply(a[:, k, None], kt[None, k, :], dtype=np.float32)
                    expected = np.add(expected, product, dtype=np.float32)
                expected = np.multiply(expected, pair, dtype=np.float32)
                self.phase_write(driver, injection, 255)
                final_write = driver.memory.pending
                for _ in range(3):
                    driver.tick(memory_response_ready=False, response_ready=False)
                    self.assertIs(driver.memory.pending, final_write)
                    self.assertIs(driver.owner.vector.client, driver.owner)
                    self.assertIsNone(driver.owner.result)
                    self.assertFalse(injection.phase_exhausted)
                driver.tick(response_ready=False)
                self.assertTrue(injection.phase_exhausted)
                base = injection.matrices[-1].base - driver.scratch.base
                self.assertEqual(driver.scratch.raw()[base:base + 16384], expected.astype('<f4').tobytes())
                output_beats = set(range(base, base + 16384, 64))
                self.assertTrue(output_beats <= driver.scratch.written)
                self.assertTrue(output_beats <= driver.scratch.acknowledged)
                self.assertEqual(driver.owner.counts['read_requests'], 35072)
                self.assertEqual(driver.owner.counts['write_requests'], 1280 + 256)
                self.assertEqual(driver.owner.counts['write_acks'], 1280 + 256)
                self.assertEqual(driver.owner.counts['memory_responses'], 35072 + 1280 + 256)
                self.assertEqual(injection.strict.counts, Counter(mul_lane_ops=524288,
                    add_lane_ops=524288, pair_lane_ops=4096))
                self.retire_failure(driver, 'Protocol')
                injection.detach()

    def test_read_backpressure_abort_reset_and_actual_drain_hold_leases(self):
        for control in ('abort', 'reset'):
            with self.subTest(control=control):
                driver, injection, _ = self.fixture(6)
                self.phase_read(driver, injection)
                request = driver.pending_request
                before = injection.strict.counts.copy()
                for step in range(4):
                    event = driver.tick(memory_response_ready=False,
                                        **({control: True} if step == 0 else {}))
                    self.assertFalse(event['memory_response_fire'] or event['memory_fire'])
                    self.assertIs(driver.pending_request, request)
                    self.assertEqual(driver.owner.state, 'drain')
                    self.assertIs(driver.owner.scalar.client, driver.owner)
                    self.assertIs(driver.owner.vector.client, driver.owner)
                    self.assertIsNone(driver.owner.result)
                    self.assertEqual(injection.strict.counts, before)
                with self.assertRaises(ValueError):
                    driver.owner.reset()
                with self.assertRaisesRegex(ValueError, 'detach requires drain'):
                    injection.detach()
                event = driver.tick(response_ready=False)
                self.assertTrue(event['memory_response_fire'])
                self.assertFalse(event['memory_fire'])
                with self.assertRaisesRegex(ValueError, 'retired terminal'):
                    injection.detach()
                self.retire_failure(driver, 'Aborted')
                injection.detach()
                driver.owner.reset()
                self.assertTrue(driver.owner.ports()['job_ready'])
                self.assertIs(driver.owner._compute.__func__, upstream.ChunkOwner._compute)
                self.assertIs(driver.owner._op.__func__, upstream.ChunkOwner._op)

    def test_request_stall_and_write_abort_drain_keep_real_obligation(self):
        driver, injection, _ = self.fixture()
        self.phase_read(driver, injection)
        driver.tick()  # A response produces the next actual read request.
        request = driver.owner.request
        for _ in range(3):
            event = driver.tick(memory_ready=False)
            self.assertFalse(event['memory_fire'])
            self.assertIs(driver.owner.request, request)
            self.assertIsNone(driver.pending)
        self.phase_write(driver, injection)
        request, physical = driver.pending_request, driver.memory.pending
        before = injection.strict.counts.copy()
        offset = request.address - driver.scratch.base
        self.assertIn(offset, driver.scratch.written)
        self.assertNotIn(offset, driver.scratch.acknowledged)
        for step in range(4):
            driver.tick(memory_response_ready=False, abort=step == 0)
            self.assertIs(driver.memory.pending, physical)
            self.assertIs(driver.owner.vector.client, driver.owner)
            self.assertEqual(injection.strict.counts, before)
        driver.tick(response_ready=False)
        self.assertIn(offset, driver.scratch.acknowledged)
        self.retire_failure(driver, 'Aborted')
        injection.detach()

    def test_stale_ack_fails_and_drains_second_write_without_credit(self):
        driver, injection, _ = self.fixture()
        self.phase_write(driver, injection)
        old_tag = driver.pending.tag
        driver.tick()
        self.phase_write(driver, injection, 1)
        second = driver.pending_request.address - driver.scratch.base
        prior = driver.scratch.acknowledged.copy()
        count = driver.owner.counts['write_acks']
        event = driver.tick(ack_tag=old_tag, response_ready=False)
        self.assertTrue(event['memory_response_fire'])
        self.assertEqual(driver.scratch.acknowledged, prior)
        self.assertIn(second, driver.scratch.written)
        self.assertNotIn(second, driver.scratch.acknowledged)
        self.assertEqual(driver.owner.counts['write_acks'], count)
        self.retire_failure(driver, 'Protocol')
        # A duplicate response after retirement cannot grant credit/new work.
        event = driver.owner.tick(memory_response=MemoryResponse(old_tag), response_ready=True)
        self.assertFalse(event['memory_response_fire'] or event['response_fire'])
        self.assertEqual(driver.owner.counts['write_acks'], count)
        injection.detach()

    def test_bad_ack_during_reset_drain_never_credits_accepted_write(self):
        for defect in ('nbytes', 'error_type', 'memory'):
            with self.subTest(defect=defect):
                driver, injection, _ = self.fixture(6)
                self.phase_write(driver, injection)
                physical = driver.memory.pending
                prior = driver.scratch.acknowledged.copy()
                count = driver.owner.counts['write_acks']
                driver.tick(reset=True, memory_response_ready=False)
                self.assertEqual(driver.owner.state, 'drain')
                self.assertIs(driver.memory.pending, physical)
                if defect == 'error_type':
                    driver.pending = replace(driver.pending, error=0)
                event = driver.tick(response_ready=False,
                    **({'ack_nbytes': 32} if defect == 'nbytes' else {'ack_error': True}))
                self.assertTrue(event['memory_response_fire'])
                self.assertEqual(driver.scratch.acknowledged, prior)
                self.assertEqual(driver.owner.counts['write_acks'], count)
                self.retire_failure(driver, 'Memory' if defect == 'memory' else 'Protocol')
                injection.detach()

    def test_read_errors_and_strict_fatal_enter_actual_owner_failure_path(self):
        for defect, status in (('underflow', 'Numerical'), ('nonfinite', 'Numerical'),
                               ('tag', 'Protocol'), ('short', 'Protocol'), ('memory', 'Memory')):
            with self.subTest(defect=defect):
                driver, injection, _ = self.fixture(defect=defect)
                self.phase_read(driver, injection)
                if defect == 'tag':
                    driver.tick(read_tag=driver.pending.tag - 1, response_ready=False)
                elif defect == 'short':
                    driver.pending = replace(driver.pending, data=bytes(63))
                    driver.tick(response_ready=False)
                elif defect == 'memory':
                    driver.tick(read_error=True, response_ready=False)
                else:
                    self.until(driver, lambda: driver.owner.result is not None, limit=4)
                self.assertFalse(injection.phase_exhausted)
                self.assertEqual(injection.strict.counts['add_lane_ops'], 0)
                self.assertEqual(injection.strict.counts['pair_lane_ops'], 0)
                if defect == 'underflow':
                    self.assertEqual(injection.strict.counts['mul_lane_ops'], 16)
                    failure = driver.owner.first_numerical_failure
                    self.assertEqual((failure['phase'], failure['reduction_k']), ('ut_matmul', 0))
                    self.assertEqual(failure['diagnostic']['exception_flags'], 3)
                    self.assertEqual(failure['diagnostic']['result_word'], 0x00800000)
                self.retire_failure(driver, status)
                injection.detach()


if __name__ == '__main__':
    unittest.main()
