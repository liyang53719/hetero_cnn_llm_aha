"""Opt-in native real-Prep/producer -> UT/QK slice, then real abort/drain.

Synthetic raw Conv/AB boundary, actual full M128 Prep and original chunk0
_compute. No arithmetic hooks or injected matrices. Complete Prep and producer
matrices plus UT/QK words checked independently; no all-intermediate or complete
flags oracle. Not complete chunk/M128/block or hardware simulation.
"""
from collections import Counter
import os
import unittest

import numpy as np

from candidates.qwen35_gdn_prefill.chunk import model as chunk
from candidates.qwen35_gdn_prefill.prep import model as prep
from candidates.qwen35_gdn_prefill.prep.test_model import oracle_row, reference_exp
from candidates.qwen35_gdn_prefill.rms_owner import word
from .real_producer_slice import make_prep
from candidates.qwen35_gdn_prefill.chunk import vector as native


def make_native_chunk(p, library):
    chunk.require(p.response is not None and p.response.status is None and
                  p.output.published, 'actual successful Prep publication required')
    vector = native.Vector16(library, arithmetic_backend=native.FINITE_MUL_UF_BACKEND)
    job = chunk.ChunkJob(72, p.job.output, 0x800000, 0x810000, 0x820000,
                         0x900000, 128, heads=1)
    for base, size in ((job.output, job.output_bytes), (job.state_out, job.state_bytes),
                       (job.scratch, job.scratch_bytes)):
        p.memory.allocate_output(base, size)
    owner = chunk.ChunkOwner(p.scalar_resource, vector, heads=1, host_batch=True)
    return chunk.TypedChunkDriver(owner, p.memory, job)


class NativeProducerSliceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = os.environ.get('GDN_VECTOR16_FINITE_MUL_UF_LIBRARY')
        if not cls.library:
            raise unittest.SkipTest('explicit receipt-bound R2 library required')
        cls.identity = native.verify_library(cls.library,
            arithmetic_backend=native.FINITE_MUL_UF_BACKEND)[2]

    @classmethod
    def tearDownClass(cls):
        if native.verify_library(cls.library,
                arithmetic_backend=native.FINITE_MUL_UF_BACKEND)[2] != cls.identity:
            raise AssertionError('native source or library changed')

    def until(self, driver, predicate, limit=200000, monitor=None):
        for _ in range(limit):
            if predicate():
                return
            self.assertIsNone(driver.response, 'unexpected retired terminal')
            if driver.owner.result is not None:
                self.fail('unexpected held terminal: ' + str(driver.owner.report()))
            phase = driver.owner.context.get('phase') if hasattr(driver.owner, 'context') else None
            event = driver.tick(response_ready=False)
            if monitor is not None:
                monitor(phase, event)
        self.fail('bounded diagnostic request budget exhausted')

    def test_real_raw_prep_to_qk_full_slice_then_actual_abort_drain(self):
        p = make_prep()
        # Original Python owner/driver and scalar; no Prep method hook.
        self.assertIs(p.owner._compute.__func__, prep.InputPrepOwner._compute)
        self.assertIs(p.tick.__func__, prep.TypedInputPrepDriver.tick)
        self.assertNotIn('_op', p.owner.__dict__)
        source = tuple(region.raw() for region in p.sources)
        self.assertEqual(len({source[0][i * 12288:(i + 1) * 12288] for i in range(128)}), 128)
        final_prep = p.job.output + p.job.write_bytes - 64
        self.until(p, lambda: p.pending is not None and p.owner.request.address == final_prep)
        for _ in range(3):
            p.tick(memory_response_ready=False, response_ready=False)
            self.assertFalse(p.output.published)
            self.assertEqual(p.owner.ack_bytes, p.job.write_bytes - 64)
        p.tick(response_ready=False)
        self.assertTrue(p.owner.result.staging_complete)
        self.assertFalse(p.output.published)
        with self.assertRaisesRegex(ValueError, 'successful Prep publication'):
            make_native_chunk(p, self.library)
        for _ in range(3):
            p.tick(response_ready=False)
            self.assertFalse(p.output.published)
        p.tick()
        self.assertIsNone(p.response.status)
        self.assertTrue(p.output.published)
        self.assertEqual(p.output.written, p.output.acknowledged)
        self.assertEqual(len(p.output.acknowledged), 51200)
        self.assertEqual(p.response.write_bytes, 3276800)
        self.assertEqual(p.counts['read_bytes'], 1666 * 64)
        self.assertIsNone(p.owner.scalar.client)
        self.assertEqual(source, tuple(region.raw() for region in p.sources))
        # Every role/gate/padding word of every distinct row. This independent
        # Fraction/RNE oracle is not a provider of any actual producer byte.
        expected_core = b''.join(oracle_row(source[0][i * 12288:(i + 1) * 12288],
            source[1][i * 64:(i + 1) * 64], source[2], source[3], 1) for i in range(128))
        actual_core = p.output.raw()
        self.assertEqual(actual_core, expected_core)
        core = np.frombuffer(expected_core, '<f4').reshape(128, 6400)
        self.assertEqual(len({actual_core[i * 25600:(i + 1) * 25600] for i in range(128)}), 128)

        d = make_native_chunk(p, self.library)
        vector = d.owner.vector
        identity = vector.arithmetic_identity()
        self.assertEqual(vector.fatal_mask, 30)
        self.assertEqual(vector.exception_policy, native.LEGACY_POLICY)
        self.assertTrue(d.owner.host_batch)
        self.assertIs(vector.op.__func__, native.Vector16.op)
        self.assertIs(vector.mul_add.__func__, native.Vector16.mul_add)
        self.assertFalse(set(vector.__dict__) & {'op', 'mul_add'})
        self.assertIs(d.owner.scalar, p.owner.scalar)
        self.assertIs(d.input, p.output)
        self.assertEqual(d.job.scratch_bytes, 1679360)
        for name in ('_compute', '_op', '_matmul', '_mul_add', '_read', '_write', '_transpose',
                     '_exp', '_cumsum_add', '_advance', '_finish', 'tick'):
            self.assertIs(getattr(d.owner, name).__func__, getattr(chunk.ChunkOwner, name))
        self.assertIs(d.tick.__func__, chunk.TypedChunkDriver.tick)
        self.assertFalse(set(d.owner.__dict__) & {'_compute', '_op', '_mul_add', '_exp'})
        mats = chunk.ScratchPlan(d.job).chunks[0][0]
        transactions = Counter()
        def monitor(phase, event):
            if event['memory_fire']:
                q = event['memory']
                transactions[(phase, 'write' if q.write else 'read')] += 1
                if not q.write and d.job.input <= q.address < d.job.input + d.job.input_bytes:
                    self.assertLess((q.address - d.job.input) // 25600, 64)
                self.assertEqual(d.owner.context['head'], 0)
                self.assertIn(d.owner.context['chunk'], (None, 0))

        self.until(d, lambda: d.owner.context['phase'] == 'ut_matmul', monitor=monitor)
        # Complete intermediate arrays from the true producer, not synthetic
        # phase-boundary operands, and no test writes to Chunk scratch.
        gate = core[:64, 6144:6160].copy()
        cumulative = np.float32(0)
        for row in range(64):
            cumulative = np.add(cumulative, gate[row, 0], dtype=np.float32)
            gate[row, 0] = cumulative
        exp_g = np.asarray([reference_exp(int(x)) for x in gate[:, 0].view(np.uint32)],
                           dtype=np.uint32).view(np.float32)
        remaining = np.subtract(cumulative, gate[:, 0], dtype=np.float32)
        exp_rem = np.asarray([reference_exp(int(x)) for x in remaining.view(np.uint32)],
                             dtype=np.uint32).view(np.float32)
        pair = np.zeros((64, 64), dtype=np.float32)
        for row in range(64):
            for col in range(row + 1):
                diff = np.subtract(gate[row, 0], gate[col, 0], dtype=np.float32)
                pair.view(np.uint32)[row, col] = reference_exp(word(diff))
        q, k, v = (core[:64, offset:offset + 128].copy() for offset in (0, 2048, 4096))
        kb = np.multiply(k, gate[:, 1, None], dtype=np.float32)
        ke = np.multiply(k, exp_rem[:, None], dtype=np.float32)
        expected = dict(gates=gate, q=q, k=k, v=v, kb=kb,
            vb=np.multiply(v, gate[:, 1, None], dtype=np.float32),
            kbg=np.multiply(kb, exp_g[:, None], dtype=np.float32),
            qg=np.multiply(q, exp_g[:, None], dtype=np.float32), ke=ke,
            kt=k.T.copy(), ket=ke.T.copy(), pair=pair)
        self.assertTrue(np.all(pair[np.tril_indices(64)] > .5))
        self.assertTrue(np.array_equal(np.diag(pair), np.ones(64, np.float32)))
        self.assertEqual(np.count_nonzero(pair[np.triu_indices(64, 1)]), 0)
        self.assertEqual(d.owner.exp_stats['calls'], 2209)
        self.assertEqual(d.owner.exp_stats['saturated_abs_ge_80'], 0)
        self.assertEqual(d.owner.exp_stats['zero_outputs'], 0)
        self.assertEqual(d.owner.counts['cumsum_terms'], 64)
        self.assertEqual(d.owner.counts['upper_triangle_masked'], 2016)

        def check_matrix(name, array):
            matrix = mats[name]
            start = matrix.base - d.scratch.base
            nbytes = matrix.rows * matrix.cols * 4
            self.assertEqual(d.scratch.raw()[start:start + nbytes], array.astype('<f4').tobytes(), name)
            beats = set(range(start, start + nbytes, 64))
            self.assertTrue(beats <= d.scratch.written and beats <= d.scratch.acknowledged, name)
            self.assertFalse(d.scratch.published)

        for name, array in expected.items():
            check_matrix(name, array)
        self.assertEqual(sum(expected[name].size for name in expected), 87040)
        self.assertEqual(sum(v for (phase, kind), v in transactions.items() if kind == 'read'), 6304)
        self.assertEqual(sum(v for (phase, kind), v in transactions.items() if kind == 'write'), 6464)
        for phase, left, name in (('ut_matmul', kb, 'ut'), ('intra_matmul', q, 'intra')):
            phase_calls = vector.host_calls.copy()
            total = np.zeros((64, 64), np.float32)
            for reduction_k in range(128):
                product = np.multiply(left[:, reduction_k, None], k[:, reduction_k][None, :], dtype=np.float32)
                total = np.add(total, product, dtype=np.float32)
            total = np.multiply(total, pair, dtype=np.float32)
            final_address = mats[name].base + 16384 - 64
            self.until(d, lambda: d.pending is not None and d.pending_request.address == final_address,
                       monitor=monitor)
            self.assertEqual(d.owner.context['phase'], phase)
            final_write = d.memory.pending
            before = vector.lane_ops.copy()
            for _ in range(3):
                d.tick(memory_response_ready=False, response_ready=False)
                self.assertIs(d.memory.pending, final_write)
                self.assertIs(d.owner.scalar.client, d.owner)
                self.assertIs(d.owner.vector.client, d.owner)
                self.assertEqual(vector.lane_ops, before)
                self.assertNotIn(final_address - d.scratch.base, d.scratch.acknowledged)
            event = d.tick(response_ready=False)
            self.assertTrue(event['memory_response_fire'])
            check_matrix(name, total)
            self.assertEqual(transactions[(phase, 'read')], 35072)
            self.assertEqual(transactions[(phase, 'write')], 256)
            self.assertEqual(vector.host_calls - phase_calls, Counter(mul_add=32768, single=256))

        # Final QK ACK has now arrived. The original generator has only issued
        # the first solve_v RHS read. Accept it, then real abort/drain without
        # ever resuming the generator with its data or doing solve arithmetic.
        self.assertEqual(d.owner.context['phase'], 'solve_v')
        self.assertEqual(d.owner.request.address, mats['vb'].base)
        self.assertFalse(d.owner.request.write)
        event = d.tick(response_ready=False)
        monitor('solve_v', event)
        self.assertTrue(event['memory_fire'])
        accepted = d.pending_request
        before = vector.lane_ops.copy()
        for step in range(3):
            event = d.tick(abort=step == 0, memory_response_ready=False, response_ready=False)
            self.assertFalse(event['memory_response_fire'] or event['memory_fire'])
            self.assertEqual(d.owner.state, 'drain')
            self.assertIs(d.pending_request, accepted)
            self.assertIs(d.owner.scalar.client, d.owner)
            self.assertIs(d.owner.vector.client, d.owner)
            self.assertEqual(vector.lane_ops, before)
        event = d.tick(response_ready=False)
        self.assertTrue(event['memory_response_fire'])
        self.assertFalse(event['memory_fire'])
        result = d.owner.result
        self.assertEqual(result.status, 'Aborted')
        self.assertFalse(result.staging_complete)
        self.assertEqual(result.write_bytes, 0)
        self.assertIsNone(d.pending)
        self.assertIsNone(d.memory.pending)
        self.assertIsNone(d.owner.scalar.client)
        self.assertIsNone(d.owner.vector.client)
        self.assertEqual(vector.lane_ops, before)
        for _ in range(3):
            d.tick(response_ready=False)
            self.assertIs(d.owner.result, result)
        d.tick()
        self.assertIs(d.response, result)
        self.assertEqual(d.owner.state, 'locked')
        self.assertEqual(d.owner.counts['owner_results'], 1)
        self.assertEqual(d.owner.counts['chunks_started'], 1)
        self.assertEqual(d.owner.counts['chunks_completed'], 0)
        self.assertEqual(d.owner.counts['read_requests'], 76449)
        self.assertEqual(d.owner.counts['write_requests'], 6976)
        self.assertEqual(d.owner.counts['write_acks'], 6976)
        self.assertEqual(d.owner.counts['scratch_ack_bytes'], 446464)
        self.assertEqual(len(d.scratch.written), 6976)
        self.assertEqual(d.scratch.written, d.scratch.acknowledged)
        self.assertEqual(vector.lane_ops, Counter(mul=1097728, add=1050784))
        self.assertEqual(vector.calls, Counter(mul=68608, add=67744))
        self.assertEqual(vector.host_calls, Counter(mul_add=65536, single=5280))
        self.assertEqual(sum(vector.flags.values()), sum(vector.calls.values()))
        self.assertTrue(set(vector.flags) <= {0, 1})
        self.assertEqual(d.owner.scalar_counts, Counter(exp_negative=2209))
        self.assertEqual(vector.arithmetic_identity(), identity)
        for region in (d.output, d.state_out):
            self.assertFalse(region.published or region.written or region.acknowledged)
        self.assertFalse(d.scratch.published)
        self.assertFalse(result.state_committed or result.history_committed or result.generation_advanced)
        self.assertEqual(p.output.raw(), expected_core)
        d.owner.reset()
        self.assertTrue(d.owner.ports()['job_ready'])
        self.assertIs(d.owner._compute.__func__, chunk.ChunkOwner._compute)
        self.assertIs(d.owner._op.__func__, chunk.ChunkOwner._op)


if __name__ == "__main__":
    unittest.main()
