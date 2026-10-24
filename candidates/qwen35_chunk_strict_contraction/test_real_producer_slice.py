"""Full M128 Prep, real chunk0 producers/UT/QK, intentional actual abort.

No reference bytes enter the actual data path. NumPy checks every strict
Add/Mul result; the existing independent Fraction Prep oracle checks the
complete 128-token output and existing exp oracle checks all producer decays.
These are software comparisons, not execution of Scala, Chisel or RTL.
"""
from collections import Counter
import struct
import unittest

import numpy as np

from candidates.qwen35_gdn_prefill.chunk import model as chunk
from candidates.qwen35_gdn_prefill.prep import model as prep
from candidates.qwen35_gdn_prefill.prep.test_model import oracle_row, reference_exp
from candidates.qwen35_gdn_prefill.rms_owner import ArithmeticFault, word
from .real_producer_slice import StrictProducerArithmetic, lease_shell, make_prep, make_chunk
from candidates.qwen35_gdn_prefill.prep.scalar import PrepScalar


class RealProducerSliceTests(unittest.TestCase):
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
        # Native owner/driver and original shared scalar, no Prep method hook.
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
            make_chunk(p)
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

        observed, phases = Counter(), Counter()
        def observe(context, position, operation, a, b, words, flags):
            av, bv = (np.asarray(x, dtype=np.uint32).view(np.float32) for x in (a, b))
            expected = (np.add if operation == 'add' else np.multiply)(av, bv, dtype=np.float32)
            self.assertTrue(np.array_equal(expected.view(np.uint32), words),
                            (context, position, operation))
            self.assertTrue(all(flag in (0, 1) for flag in flags), 'warm-range fatal/unexpected flags')
            observed['words'] += len(words)
            observed[operation] += len(words)
            observed['width' + str(len(words))] += 1
            phases[context['phase']] += 1

        d, arithmetic = make_chunk(p, observe)
        self.assertIs(d.owner.scalar, p.owner.scalar)
        self.assertIs(d.input, p.output)
        self.assertEqual(d.job.scratch_bytes, 1679360)
        for name in ('_compute', '_matmul', '_mul_add', '_read', '_write', '_transpose',
                     '_exp', '_cumsum_add', '_advance', '_finish', 'tick'):
            self.assertIs(getattr(d.owner, name).__func__, getattr(chunk.ChunkOwner, name))
        self.assertIs(d.tick.__func__, chunk.TypedChunkDriver.tick)
        self.assertEqual(set(d.owner.__dict__) & {'_compute', '_op', '_exp'}, {'_op'})
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
            before = arithmetic.lane_ops.copy()
            for _ in range(3):
                d.tick(memory_response_ready=False, response_ready=False)
                self.assertIs(d.memory.pending, final_write)
                self.assertIs(d.owner.scalar.client, d.owner)
                self.assertIs(d.owner.vector.client, d.owner)
                self.assertEqual(arithmetic.lane_ops, before)
                self.assertNotIn(final_address - d.scratch.base, d.scratch.acknowledged)
            event = d.tick(response_ready=False)
            self.assertTrue(event['memory_response_fire'])
            check_matrix(name, total)
            self.assertEqual(transactions[(phase, 'read')], 35072)
            self.assertEqual(transactions[(phase, 'write')], 256)

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
        before = arithmetic.lane_ops.copy()
        for step in range(3):
            event = d.tick(abort=step == 0, memory_response_ready=False, response_ready=False)
            self.assertFalse(event['memory_response_fire'] or event['memory_fire'])
            self.assertEqual(d.owner.state, 'drain')
            self.assertIs(d.pending_request, accepted)
            self.assertIs(d.owner.scalar.client, d.owner)
            self.assertIs(d.owner.vector.client, d.owner)
            self.assertEqual(arithmetic.lane_ops, before)
            with self.assertRaisesRegex(ValueError, 'drained retired'):
                arithmetic.detach()
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
        self.assertEqual(arithmetic.lane_ops, before)
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
        self.assertEqual(observed['words'], 2148512)
        self.assertEqual(arithmetic.lane_ops, Counter(mul=1097728, add=1050784))
        self.assertEqual(observed['width1'], 2208)
        self.assertNotIn('solve_v', phases)
        self.assertEqual(d.owner.scalar_counts, Counter(exp_negative=2209))
        self.assertFalse(d.owner.vector.calls or d.owner.vector.lane_ops or d.owner.vector.host_calls)
        for region in (d.output, d.state_out):
            self.assertFalse(region.published or region.written or region.acknowledged)
        self.assertFalse(d.scratch.published)
        self.assertFalse(result.state_committed or result.history_committed or result.generation_advanced)
        self.assertEqual(p.output.raw(), expected_core)
        arithmetic.detach()
        d.owner.reset()
        self.assertTrue(d.owner.ports()['job_ready'])
        self.assertIs(d.owner._compute.__func__, chunk.ChunkOwner._compute)
        self.assertIs(d.owner._op.__func__, chunk.ChunkOwner._op)

    def test_active_lane_contract_and_safe_fault_context(self):
        owner = chunk.ChunkOwner(PrepScalar(enable_softplus=True), lease_shell(), heads=1)
        hook = StrictProducerArithmetic(owner)
        self.assertTrue(owner.scalar.acquire(owner) and owner.vector.acquire(owner))
        owner.context, owner.position = dict(phase='producer_unit'), {}
        for width in range(1, 17):
            self.assertEqual(hook._op('add', [word(1)] * width, [word(.5)] * width), [word(1.5)] * width)
        for a, b in (([], []), ([0] * 17, [0] * 17), ([0], [0, 0])):
            with self.assertRaisesRegex(ValueError, '1..16'):
                hook._op('add', a, b)
        with self.assertRaisesRegex(ValueError, 'uint32'):
            hook._op('mul', [-1], [0])
        # No row/column/K keys are present. Fatal mask30 still rejects the
        # strict flags3 minnormal result, not KeyError or legacy flags1 success.
        with self.assertRaises(ArithmeticFault) as caught:
            hook._op('mul', [0x00800000], [0x3f7fffff])
        diagnostic = caught.exception.diagnostic
        self.assertEqual(diagnostic['exception_flags'], 3)
        self.assertEqual(diagnostic['result_word'], 0x00800000)
        self.assertIsNone(diagnostic['reduction_k'])
        self.assertEqual(owner.first_numerical_failure['phase'], 'producer_unit')
        self.assertEqual(owner.first_numerical_failure['diagnostic'], diagnostic)
        owner.first_numerical_failure = None
        with self.assertRaisesRegex(ArithmeticFault, 'nonfinite'):
            hook._op('add', [0x7fc00000], [0])
        self.assertIsNone(owner.first_numerical_failure['diagnostic']['exception_flags'])
        owner.scalar.release(owner)
        owner.vector.release(owner)
        hook.detach()


if __name__ == '__main__':
    unittest.main()
