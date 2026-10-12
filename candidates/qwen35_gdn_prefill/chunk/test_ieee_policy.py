"""Explicit candidate exception control; no current Chisel binding claimed."""
import tempfile
import unittest

import numpy as np

from .vector import Vector16, VectorArithmeticFault, build_library, LEGACY_POLICY, IEEE_POLICY
from . import model as m, reference as ref
from .test_model import fixture, produced
from ..prep.scalar import PrepScalar


class IeeePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='gdn-vector-ieee-')
        cls.library = build_library(cls.temp.name)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def vector(self, policy):
        vector = Vector16(self.library, exception_policy=policy)
        client = object()
        self.assertTrue(vector.acquire(client))
        return vector, client

    def test_actual_m128_failure_and_ties_gradual_subnormal_without_ftz(self):
        # Constants from independent integer FP32 RNE, including retained
        # actual head0/chunk0/row18/lane4 failure, not native tensor injection.
        cases = [(0xb7ae8141, 0x07dd24d3, 0x804b5f58, 3),
                 (0x00810000, 0x34810000, 0x00000002, 3),
                 (0x83d70000, 0x02200000, 0x80000000, 3),
                 (1, 0x3f000000, 0, 3), (3, 0x3f000000, 2, 3),
                 (0x00800000, 0x3f000000, 0x00400000, 0)]
        for a, b, expected, flags in cases:
            with self.subTest(a=hex(a), b=hex(b)):
                ieee, client = self.vector(IEEE_POLICY)
                self.assertEqual(ieee.op(client, 'mul', [a], [b]), [expected])
                self.assertEqual(dict(ieee.flags), {flags: 1})
                aa, bb = np.array([a], '<u4').view('<f4'), np.array([b], '<u4').view('<f4')
                got = ref._node('mul', aa, bb, allow_gradual_underflow=True)
                self.assertEqual(int(got.view('<u4')[0]), expected)
                legacy, old = self.vector(LEGACY_POLICY)
                if flags & 2:
                    with self.assertRaises(VectorArithmeticFault) as caught:
                        legacy.op(old, 'mul', [a], [b])
                    self.assertEqual(caught.exception.diagnostic['exception_flags'], flags)
                    self.assertEqual(caught.exception.diagnostic['result_words'][0], expected)
                    with self.assertRaises(ValueError): ref._node('mul', aa, bb)
                else:
                    self.assertEqual(legacy.op(old, 'mul', [a], [b]), [expected])

    def test_batch_still_two_rounded_issues_and_flags_after_underflow(self):
        for total in (0, 0x80000000, 0x00800000, 0x3f800000):
            one, a = self.vector(IEEE_POLICY)
            two, b = self.vector(IEEE_POLICY)
            product = one.op(a, 'mul', [0xb7ae8141], [0x07dd24d3])
            expected = one.op(a, 'add', [total], product)
            self.assertEqual(two.mul_add(b, [0xb7ae8141], [0x07dd24d3], [total]), expected)
            self.assertEqual(one.calls, two.calls)
            self.assertEqual(one.flags, two.flags)
            self.assertEqual(one.lane_ops, two.lane_ops)
        legacy, client = self.vector(LEGACY_POLICY)
        with self.assertRaises(VectorArithmeticFault):
            legacy.mul_add(client, [1], [0x3f000000], [0x3f800000])
        self.assertEqual(dict(legacy.calls), {'mul': 1})

    def test_nonfinite_overflow_and_invalid_still_rejected(self):
        for policy in (LEGACY_POLICY, IEEE_POLICY):
            for operation, a, b in [('mul',0x7f7fffff,0x40000000),
                                    ('add',0x7f7fffff,0x7f7fffff),
                                    ('mul',0x7f800000,0),('add',0x7fc00001,0)]:
                v, client = self.vector(policy)
                with self.assertRaises(VectorArithmeticFault): v.op(client,operation,[a],[b])
            v, client = self.vector(policy)
            with self.assertRaises(VectorArithmeticFault) as caught:
                v.mul_add(client,[0x7f7fffff],[0x40000000],[0])
            self.assertEqual(dict(v.calls), {'mul': 1})
            self.assertEqual(caught.exception.diagnostic['exception_flags'], 5)
        with self.assertRaises(ValueError): Vector16(self.library, exception_policy='ignore_errors')

    def test_identity_explicitly_discloses_unbound_chisel_policy(self):
        self.assertEqual(Vector16(self.library).exception_policy, LEGACY_POLICY)
        self.assertTrue(m.source_identity()['vector_exception_control_chisel_bound'])
        identity = m.source_identity(IEEE_POLICY)
        self.assertFalse(identity['vector_exception_control_chisel_bound'])
        self.assertEqual(identity['vector_underflow_policy'], IEEE_POLICY)
        self.assertIn('flags[4:1]', identity['ieee_mode_integration_gap'])

    def test_complete_small_chunk_underflow_profile_and_batch_equivalence(self):
        data = np.frombuffer(fixture(32), '<f4').reshape(32, 6400).copy()
        data[:, 6144] = np.float32(-4.25)
        # Materialize the prepared V contract; no owner-produced result is
        # replaced by the independent oracle.
        words = data[:, 4096:4128].view('<u4')
        words[:] = ((words + np.uint32(0x7fff) + ((words >> 16) & 1)) >> 16) << 16
        raw = data.tobytes()
        gold, gold_state, _ = ref.fixed_chunk(raw, 32, heads=1, key_dim=16,
            value_dim=32, exception_policy=IEEE_POLICY)
        results = []
        for policy, batched in ((LEGACY_POLICY, False), (IEEE_POLICY, False), (IEEE_POLICY, True)):
            memory = m.TypedMemory()
            produced(memory, 0x100000, raw)
            owner = m.ChunkOwner(PrepScalar(), Vector16(self.library, exception_policy=policy),
                heads=1, key_dim=16, value_dim=32, host_batch=batched)
            job = m.ChunkJob(1, 0x100000, 0x400000, 0x500000, 0x600000, 0x1000000,
                             32, True, 0, 1, 16, 32)
            for base, extent in ((job.state_in,job.state_bytes),(job.state_out,job.state_bytes),
                                 (job.output,job.output_bytes),(job.scratch,job.scratch_bytes)):
                memory.allocate_output(base, extent)
            driver = m.TypedChunkDriver(owner,memory,job)
            for _ in range(1000000):
                driver.tick()
                if driver.response is not None: break
            self.assertIsNotNone(driver.response)
            self.assertFalse(driver.output.published or driver.state_out.published)
            if policy == LEGACY_POLICY:
                self.assertEqual(driver.response.status, 'Numerical')
                self.assertEqual(owner.first_numerical_failure['diagnostic']['exception_flags'], 3)
            else:
                self.assertIsNone(driver.response.status)
                self.assertEqual(driver.output.raw(), gold)
                self.assertEqual(driver.state_out.raw(), gold_state)
                self.assertGreater(owner.flag_counts[3], 0)
                results.append((driver.output.raw(),driver.state_out.raw(),driver.scratch.raw(),
                                owner.vector_counts,owner.flag_counts,dict(driver.counts)))
        self.assertEqual(results[0],results[1])


if __name__ == '__main__':
    unittest.main()
