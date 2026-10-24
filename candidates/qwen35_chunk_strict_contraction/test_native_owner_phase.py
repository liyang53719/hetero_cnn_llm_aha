"""Opt-in real native Vector16 + original ChunkOwner host_batch phase test.

Only _compute is explicitly injected with synthetic operand writes and one UT
phase. No prep producer, complete chunk, M128, full block or RTL is qualified.
The unchanged owner must terminate Protocol because output/state are unwritten.
No automatic build: supply GDN_VECTOR16_FINITE_MUL_UF_LIBRARY explicitly.
"""
from collections import Counter
import os
from functools import reduce
from unittest.mock import patch
import unittest

import numpy as np

from candidates.qwen35_gdn_prefill.chunk import model as upstream
from candidates.qwen35_gdn_prefill.chunk import vector as native
from candidates.qwen35_gdn_prefill.prep.scalar import PrepScalar
from candidates.qwen2_resident_matrix.transposed_down.model import WriteCommand, WriteAck
from candidates.qwen35_strict_fp32_lane import lane_model as strict


class NativeOwnerPhaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = os.environ.get('GDN_VECTOR16_FINITE_MUL_UF_LIBRARY')
        if not cls.library:
            raise unittest.SkipTest('explicit receipt-bound R2 native library required')
        cls.identity = native.verify_library(cls.library,
            arithmetic_backend=native.FINITE_MUL_UF_BACKEND)[2]

    @classmethod
    def tearDownClass(cls):
        if native.verify_library(cls.library,
                arithmetic_backend=native.FINITE_MUL_UF_BACKEND)[2] != cls.identity:
            raise AssertionError('native source or library changed')

    def fixture(self, underflow=False):
        rng = np.random.default_rng(905)
        a = rng.uniform(-.2, .2, (64, 128)).astype('<f4')
        kt = rng.uniform(-.3, .3, (128, 64)).astype('<f4')
        pair = np.tril(rng.uniform(.3, 1., (64, 64)).astype('<f4'))
        np.fill_diagonal(pair, 1.)
        if underflow:
            a.view(np.uint32)[0, 0] = 0x00800000
            kt.view(np.uint32)[0, :16] = 0x3f7fffff
        vector = native.Vector16(self.library, arithmetic_backend=native.FINITE_MUL_UF_BACKEND)
        self.assertEqual(vector.fatal_mask, 30)
        self.assertEqual(vector.exception_policy, native.LEGACY_POLICY)
        vector.arithmetic_identity()
        owner = upstream.ChunkOwner(PrepScalar(enable_softplus=True), vector, heads=1, host_batch=True)
        job = upstream.ChunkJob(46, 0x100000, 0x500000, 0x510000,
                                0x520000, 0x600000, 64, heads=1)
        mats = upstream.ScratchPlan(job).chunks[0][0]
        memory = upstream.TypedMemory()
        # Synthetic admission input, ACKed and published but NOT computed Prep.
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
        progress = dict(fixture_writes=0, phase_exhausted=False)
        def compute(actual_job):
            self.assertIs(actual_job, job)
            owner.context = dict(phase='synthetic_native_fixture', head=0, chunk=0)
            for name, values in zip(('kb', 'kt', 'pair'), (a, kt, pair)):
                raw = values.tobytes()
                for offset in range(0, len(raw), 64):
                    yield mats[name].base + offset, raw[offset:offset + 64]
                    progress['fixture_writes'] += 1
            owner._phase('ut_matmul')
            yield from owner._matmul(mats['kb'], mats['kt'], mats['ut'], factor=mats['pair'])
            progress['phase_exhausted'] = True
        owner._compute = compute
        for name in ('_op', '_mul_add', '_matmul', 'tick', '_advance', '_finish'):
            self.assertIs(getattr(owner, name).__func__, getattr(upstream.ChunkOwner, name))
        driver = upstream.TypedChunkDriver(owner, memory, job)
        return driver, mats, progress, (a, kt, pair)

    def until(self, driver, predicate, observe=None):
        for _ in range(80000):
            if predicate():
                return
            self.assertIsNone(driver.response, 'unexpected early retirement')
            position_before = dict(driver.owner.position)
            before = driver.owner.vector.host_calls['mul_add']
            driver.tick(response_ready=False)
            after = driver.owner.vector.host_calls['mul_add']
            self.assertIn(after - before, (0, 1))
            if observe and after != before:
                observe(position_before)
        self.fail('bounded phase target not reached')

    def retire(self, driver, status):
        owner, vector = driver.owner, driver.owner.vector
        self.assertEqual(owner.state, 'finish')
        result = owner.result
        self.assertEqual(result.status, status)
        self.assertFalse(result.staging_complete)
        self.assertEqual(result.write_bytes, 0)
        self.assertFalse(result.state_committed or result.history_committed or result.generation_advanced)
        self.assertIsNone(driver.pending)
        self.assertIsNone(driver.memory.pending)
        self.assertIsNone(vector.client)
        self.assertIsNone(owner.scalar.client)
        self.assertFalse(driver.output.written or driver.state_out.written)
        for region in (driver.output, driver.state_out, driver.scratch):
            self.assertFalse(region.published)
        for _ in range(3):
            driver.tick(response_ready=False)
            self.assertIs(owner.result, result)
        driver.tick()
        self.assertIs(driver.response, result)
        self.assertEqual(owner.counts['owner_results'], 1)
        vector.arithmetic_identity()

    def test_full_native_host_batch_ut_and_final_ack(self):
        driver, mats, progress, (a, kt, pair) = self.fixture()
        vector = driver.owner.vector
        expected = np.zeros((64, 64), dtype=np.float32)
        for k in range(128):
            product = np.multiply(a[:, k, None], kt[None, k, :], dtype=np.float32)
            expected = np.add(expected, product, dtype=np.float32)
        expected = np.multiply(expected, pair, dtype=np.float32)
        sampled = 0
        expected_total = [0] * 16
        def observe(p):
            nonlocal sampled
            if p.get('row') != 15 or p.get('column') != 0:
                return
            k = p['reduction_k']
            mul_flags, add_flags = [], []
            for lane in range(16):
                product, mf = strict.mul(int(a.view(np.uint32)[15, k]), int(kt.view(np.uint32)[k, lane]))
                self.assertEqual(int(vector.total[lane]), expected_total[lane])
                total, af = strict.add(expected_total[lane], product)
                expected_total[lane] = total
                self.assertEqual(int(vector.b[lane]), product)
                self.assertEqual(int(vector.output[lane]), total)
                self.assertEqual(int(vector.lane_flags[lane]), af)
                mul_flags.append(mf); add_flags.append(af)
                sampled += 2
            aggregate = lambda flags: reduce(int.__or__, flags, 0)
            self.assertEqual(list(vector.issue_flags), [aggregate(mul_flags), aggregate(add_flags)])
        last_address = mats['ut'].base + 16384 - 64
        self.until(driver, lambda: driver.pending is not None and
                   driver.pending_request.address == last_address, observe)
        self.assertEqual(sampled, 4096)
        self.assertEqual(progress['fixture_writes'], 1280)
        self.assertTrue(driver.pending_request.write)
        physical = driver.memory.pending
        for _ in range(3):
            driver.tick(memory_response_ready=False, response_ready=False)
            self.assertIs(driver.memory.pending, physical)
            self.assertIs(vector.client, driver.owner)
            self.assertFalse(progress['phase_exhausted'])
            self.assertIsNone(driver.owner.result)
        driver.tick(response_ready=False)
        self.assertTrue(progress['phase_exhausted'])
        offset = mats['ut'].base - driver.scratch.base
        self.assertEqual(driver.scratch.raw()[offset:offset + 16384], expected.tobytes())
        self.assertTrue(set(range(offset, offset + 16384, 64)) <= driver.scratch.acknowledged)
        self.assertEqual(vector.host_calls, Counter(mul_add=32768, single=256))
        self.assertEqual(vector.calls, Counter(mul=33024, add=32768))
        self.assertEqual(vector.lane_ops, Counter(mul=528384, add=524288))
        self.assertEqual(driver.owner.counts['read_requests'], 35072)
        self.assertEqual(driver.owner.counts['write_acks'], 1536)
        self.retire(driver, 'Protocol')

    def test_wrong_backend_receipt_rejected_without_loading(self):
        with patch.object(native.C, 'CDLL', side_effect=AssertionError('must not load')):
            with self.assertRaises(ValueError):
                native.Vector16(self.library, arithmetic_backend=native.LEGACY_BACKEND)

    def test_native_underflow_stops_before_add(self):
        driver, mats, progress, _ = self.fixture(underflow=True)
        self.until(driver, lambda: driver.owner.state == 'finish')
        vector = driver.owner.vector
        self.assertEqual(vector.host_calls, Counter(mul_add=1))
        self.assertEqual(vector.calls, Counter(mul=1))
        self.assertEqual(list(vector.issue_flags)[0], 3)
        diagnostic = driver.owner.first_numerical_failure['diagnostic']
        self.assertEqual(diagnostic['operation'], 'mul')
        self.assertEqual(diagnostic['exception_flags'], 3)
        self.assertEqual(diagnostic['result_words'], [0x00800000] * 16)
        self.assertEqual(diagnostic['lane_exception_flags'], [3] * 16)
        self.assertFalse(progress['phase_exhausted'])
        self.assertEqual(driver.owner.counts['write_acks'], 1280)
        self.retire(driver, 'Numerical')

    def test_actual_native_phase_abort_drains_accepted_write(self):
        driver, mats, progress, _ = self.fixture()
        self.until(driver, lambda: driver.pending is not None and
                   driver.pending_request.address == mats['ut'].base)
        self.assertTrue(driver.pending_request.write)
        vector, physical = driver.owner.vector, driver.memory.pending
        calls = vector.host_calls.copy()
        for step in range(3):
            driver.tick(abort=step == 0, memory_response_ready=False, response_ready=False)
            self.assertEqual(driver.owner.state, 'drain')
            self.assertIs(driver.memory.pending, physical)
            self.assertIs(vector.client, driver.owner)
            self.assertEqual(vector.host_calls, calls)
        driver.tick(response_ready=False)
        self.assertIn(mats['ut'].base - driver.scratch.base, driver.scratch.acknowledged)
        self.assertFalse(progress['phase_exhausted'])
        self.retire(driver, 'Aborted')


class NativeOwnerColdTests(unittest.TestCase):
    def test_missing_library_rejected_without_loading(self):
        with patch.object(native.C, 'CDLL', side_effect=AssertionError('must not load')):
            with self.assertRaises(FileNotFoundError):
                native.Vector16('/no-such-native-owner-qualification-library.so',
                                arithmetic_backend=native.FINITE_MUL_UF_BACKEND)


if __name__ == '__main__':
    unittest.main()
