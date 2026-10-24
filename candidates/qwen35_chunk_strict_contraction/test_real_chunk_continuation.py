"""Actual M128 Prep -> complete chunk0 -> chunk1 first carried-state row.

The original owner generator is never replaced and no reference tensor is
written to its memory. The existing strict Add/Mul hook and original scalar
are retained. This is a bounded one-head software diagnostic, NOT full M128,
full-block, native Vector16, Chisel, RTL, or hardware-performance acceptance.
"""
from collections import Counter
import json
import time
import unittest

import numpy as np

from candidates.qwen35_gdn_prefill.chunk import model as chunk
from candidates.qwen35_gdn_prefill.prep import model as prep
from candidates.qwen35_gdn_prefill.prep.test_model import oracle_row, reference_exp
from .real_producer_slice import make_prep, make_chunk


def separate_matmul(a, b):
    """Independent full-plane NumPy schedule; no owner helper is called."""
    out = np.zeros((a.shape[0], b.shape[1]), np.float32)
    for k in range(a.shape[1]):
        product = np.multiply(a[:, k, None], b[k, None, :], dtype=np.float32)
        out = np.add(out, product, dtype=np.float32)
    return out


def sign_flip(a):
    return np.bitwise_xor(a.view(np.uint32), np.uint32(0x80000000)).view(np.float32)


def unit_lower_solve(lower, rhs):
    """Independent triangular reference; stored diagonal is never divided."""
    solved = np.zeros_like(rhs)
    for row in range(64):
        total = np.zeros(rhs.shape[1], np.float32)
        for col in range(row):
            product = np.multiply(lower[row, col], solved[col], dtype=np.float32)
            total = np.add(total, product, dtype=np.float32)
        solved[row] = np.add(rhs[row], sign_flip(total), dtype=np.float32)
    return solved


def reference_chunk(core, previous, *, tail):
    """Assemble independent expected arrays from Fraction-checked Prep only."""
    gate = core[:, 6144:6160].copy()
    cumulative = np.float32(0)
    for row in range(64):
        cumulative = np.add(cumulative, gate[row, 0], dtype=np.float32)
        gate[row, 0] = cumulative

    def exp_array(values):
        flat = np.ascontiguousarray(values, dtype=np.float32).reshape(-1)
        return np.asarray([reference_exp(int(x)) for x in flat.view(np.uint32)],
                          np.uint32).view(np.float32).reshape(values.shape)

    exp_g = exp_array(gate[:, 0])
    remaining = np.add(cumulative, sign_flip(gate[:, 0].copy()), dtype=np.float32)
    exp_remaining = exp_array(remaining)
    pair = np.zeros((64, 64), np.float32)
    for row in range(64):
        diff = np.add(gate[row, 0], sign_flip(gate[:row + 1, 0].copy()), dtype=np.float32)
        pair[row, :row + 1] = exp_array(diff)
    q, k, v = (core[:, offset:offset + 128].copy() for offset in (0, 2048, 4096))
    kb = np.multiply(k, gate[:, 1, None], dtype=np.float32)
    ke = np.multiply(k, exp_remaining[:, None], dtype=np.float32)
    result = dict(gates=gate, q=q, k=k, v=v, kb=kb,
        vb=np.multiply(v, gate[:, 1, None], dtype=np.float32),
        kbg=np.multiply(kb, exp_g[:, None], dtype=np.float32),
        qg=np.multiply(q, exp_g[:, None], dtype=np.float32), ke=ke,
        kt=k.T.copy(), ket=ke.T.copy(), pair=pair)
    result['ut'] = np.multiply(separate_matmul(kb, k.T), pair, dtype=np.float32)
    result['intra'] = np.multiply(separate_matmul(q, k.T), pair, dtype=np.float32)
    result['solvev'] = unit_lower_solve(result['ut'], result['vb'])
    result['solvek'] = unit_lower_solve(result['ut'], result['kbg'])
    result['pred'] = separate_matmul(result['solvek'], previous)
    if not tail:
        return result
    result['vnew'] = np.add(result['solvev'], sign_flip(result['pred']), dtype=np.float32)
    result['inter'] = separate_matmul(result['qg'], previous)
    result['local'] = separate_matmul(result['intra'], result['vnew'])
    result['out'] = np.add(result['inter'], result['local'], dtype=np.float32)
    result['state_update'] = separate_matmul(result['ket'], result['vnew'])
    decay = exp_array(np.asarray(cumulative, dtype=np.float32))
    result['decay_state'] = np.multiply(previous, decay, dtype=np.float32)
    result['next_state'] = np.add(result['decay_state'], result['state_update'], dtype=np.float32)
    return result


def bf16_reference(array):
    """RNE by retained/remainder comparison, not the owner's bias formula."""
    u = array.view(np.uint32)
    upper, remainder = np.right_shift(u, 16), np.bitwise_and(u, 0xffff)
    increment = (remainder > 0x8000) | ((remainder == 0x8000) & ((upper & 1) != 0))
    return (upper + increment).astype('<u2').tobytes()


class RealChunkContinuationTests(unittest.TestCase):
    def test_complete_chunk0_then_chunk1_actual_carried_state_prediction_row(self):
        started = time.monotonic()
        p = make_prep()
        self.assertIs(p.owner._compute.__func__, prep.InputPrepOwner._compute)
        self.assertNotIn('_op', p.owner.__dict__)
        source = tuple(region.raw() for region in p.sources)
        for _ in range(120000):
            if p.response is not None:
                break
            p.tick()
        self.assertIsNotNone(p.response, 'Prep request budget')
        self.assertIsNone(p.response.status)
        self.assertTrue(p.output.published)
        expected_core = b''.join(oracle_row(source[0][i * 12288:(i + 1) * 12288],
            source[1][i * 64:(i + 1) * 64], source[2], source[3], 1) for i in range(128))
        self.assertEqual(p.output.raw(), expected_core)
        core = np.frombuffer(expected_core, '<f4').reshape(128, 6400)
        reference0 = reference_chunk(core[:64], np.zeros((128, 128), np.float32), tail=True)
        reference1 = reference_chunk(core[64:], reference0['next_state'], tail=False)
        self.assertTrue(np.any(reference0['next_state'].view(np.uint32) & 0x7fffffff))
        self.assertTrue(np.any(reference1['pred'][0].view(np.uint32) & 0x7fffffff))

        observed, transactions, carry_reads = Counter(), Counter(), Counter()
        def observe(context, position, operation, a, b, words, flags):
            av, bv = (np.asarray(x, np.uint32).view(np.float32) for x in (a, b))
            expected = (np.add if operation == 'add' else np.multiply)(av, bv, dtype=np.float32)
            self.assertTrue(np.array_equal(expected.view(np.uint32), words),
                            (context, position, operation))
            self.assertTrue(all(flag in (0, 1) for flag in flags), (context, position, flags))
            observed[operation] += len(words)
            observed[(context['chunk'], context['phase'], operation)] += len(words)

        d, arithmetic = make_chunk(p, observe)
        plan = chunk.ScratchPlan(d.job)
        pristine_output, pristine_state, pristine_scratch = (r.raw() for r in
                                                            (d.output, d.state_out, d.scratch))
        self.assertIs(d.input, p.output)
        self.assertIs(d.owner.scalar, p.owner.scalar)
        for name in ('_compute', '_solve', '_binary', '_matmul', '_mul_add', '_read',
                     '_write', '_transpose', '_exp', '_cumsum_add', '_advance', '_finish', 'tick'):
            self.assertIs(getattr(d.owner, name).__func__, getattr(chunk.ChunkOwner, name))
        self.assertIs(d.tick.__func__, chunk.TypedChunkDriver.tick)
        self.assertEqual(set(d.owner.__dict__) & {'_compute', '_op', '_exp'}, {'_op'})

        def tick(**kwargs):
            context = dict(d.owner.context)
            event = d.tick(response_ready=False, **kwargs)
            if event['memory_fire']:
                request = event['memory']
                transactions[(context['chunk'], context['phase'], 'write' if request.write else 'read')] += 1
                self.assertEqual(context['head'], 0)
                if context['chunk'] == 1 and context['phase'] == 'predict_matmul' and not request.write:
                    previous = plan.chunks[0][0]['next_state']
                    if previous.base <= request.address < previous.base + 65536:
                        carry_reads[request.address] += 1
            return event

        def until(predicate):
            for _ in range(1000000):
                if predicate():
                    return
                self.assertIsNone(d.owner.result, 'unexpected terminal: ' + str(d.owner.first_numerical_failure))
                tick()
            self.fail('bounded continuation request budget exhausted')

        def at_phase(chunk_id, phase):
            return d.owner.context['chunk'] == chunk_id and d.owner.context['phase'] == phase

        compared = Counter()
        def check_matrix(chunk_id, name, array, rows=None):
            matrix = plan.chunks[0][chunk_id][name]
            count = matrix.rows if rows is None else rows
            expected = np.ascontiguousarray(array[:count], dtype='<f4').tobytes()
            start = matrix.base - d.scratch.base
            self.assertEqual(d.scratch.raw()[start:start + len(expected)], expected, (chunk_id, name))
            beats = set(range(start, start + len(expected), 64))
            self.assertTrue(beats <= d.scratch.written and beats <= d.scratch.acknowledged)
            self.assertFalse(d.scratch.published)
            compared[chunk_id] += len(expected) // 4

        def checkpoint(name):
            print(json.dumps(dict(checkpoint=name, seconds=round(time.monotonic() - started, 3),
                chunk=d.owner.context['chunk'], phase=d.owner.context['phase'],
                reads=d.owner.counts['read_requests'], writes=d.owner.counts['write_requests'],
                strict_words=sum(arithmetic.lane_ops.values()))), flush=True)

        producers = ('gates', 'q', 'k', 'v', 'kb', 'vb', 'kbg', 'qg', 'ke', 'kt', 'ket', 'pair')
        stages = (('intra_matmul', 'ut'), ('solve_v', 'intra'), ('solve_k', 'solvev'),
                  ('predict_matmul', 'solvek'), ('vnew_subtract', 'pred'),
                  ('inter_matmul', 'vnew'), ('local_matmul', 'inter'),
                  ('output_add', 'local'), ('state_update_matmul', 'out'),
                  ('state_decay', 'state_update'), ('state_add', 'decay_state'),
                  ('output_bf16_materialization', 'next_state'))
        until(lambda: at_phase(0, 'ut_matmul'))
        initial_start = plan.initial[0].base - d.scratch.base
        self.assertEqual(d.scratch.raw()[initial_start:initial_start + 65536], bytes(65536))
        self.assertTrue(set(range(initial_start, initial_start + 65536, 64)) <= d.scratch.acknowledged)
        for name in producers:
            check_matrix(0, name, reference0[name])
        checkpoint('chunk0_all_producers_verified')
        for next_phase, name in stages:
            until(lambda: at_phase(0, next_phase))
            check_matrix(0, name, reference0[name])
            checkpoint('chunk0_' + name + '_verified')

        # All chunk0 scratch tensors have actual ACKs. BF16 output remains
        # unpublished, and chunks_completed cannot advance ahead of final ACK.
        final_output = d.job.output + 64 * 128 * 2 - 64
        until(lambda: d.pending_request is not None and d.pending_request.address == final_output)
        before = arithmetic.lane_ops.copy()
        for _ in range(3):
            tick(memory_response_ready=False)
            self.assertEqual(d.owner.counts['chunks_completed'], 0)
            self.assertEqual(d.owner.counts['chunks_started'], 1)
            self.assertNotIn(final_output - d.output.base, d.output.acknowledged)
            self.assertFalse(d.output.published or d.state_out.published)
            self.assertEqual(arithmetic.lane_ops, before)
            self.assertIs(d.owner.scalar.client, d.owner)
            self.assertIs(d.owner.vector.client, d.owner)
        tick()
        self.assertTrue(at_phase(1, 'load_prep_and_cumsum'))
        self.assertEqual(d.owner.counts['chunks_completed'], 1)
        self.assertEqual(d.owner.counts['chunks_started'], 2)
        expected_output = bf16_reference(reference0['out'])
        self.assertEqual(d.output.raw()[:len(expected_output)], expected_output)
        self.assertEqual(d.output.written, set(range(0, len(expected_output), 64)))
        self.assertEqual(d.output.written, d.output.acknowledged)
        self.assertFalse(d.output.published or d.state_out.written)
        checkpoint('chunk0_complete_output_ACKed_not_published')

        until(lambda: at_phase(1, 'ut_matmul'))
        for name in producers:
            check_matrix(1, name, reference1[name])
        for next_phase, name in stages[:4]:
            until(lambda: at_phase(1, next_phase))
            check_matrix(1, name, reference1[name])
            checkpoint('chunk1_' + name + '_verified')

        # Execute all 128 output columns of the first genuine chunk1 predict
        # row. Every FP32 element of chunk0 next_state is read once through the
        # actual owner-addressed, ACK-checked scratch transport.
        pred = plan.chunks[0][1]['pred']
        final_pred = pred.address(0, 112)
        until(lambda: d.pending_request is not None and d.pending_request.address == final_pred)
        before = arithmetic.lane_ops.copy()
        for _ in range(3):
            tick(memory_response_ready=False)
            self.assertEqual(arithmetic.lane_ops, before)
            self.assertNotIn(final_pred - d.scratch.base, d.scratch.acknowledged)
        tick()
        check_matrix(1, 'pred', reference1['pred'], rows=1)
        self.assertEqual(carry_reads, Counter({plan.chunks[0][0]['next_state'].base + offset: 1
                                              for offset in range(0, 65536, 64)}))
        self.assertEqual(d.owner.request.address, plan.chunks[0][1]['solvek'].address(1, 0))
        self.assertFalse(d.owner.request.write)
        self.assertEqual(observed[(1, 'predict_matmul', 'mul')], 128 * 128)
        self.assertEqual(observed[(1, 'predict_matmul', 'add')], 128 * 128)
        checkpoint('chunk1_actual_state_carry_first_prediction_row_verified')

        # Real abort/drain of the following outstanding read; no manufactured
        # completion, synthetic terminal, later output/state publication, or
        # alteration of the historical QK-abort test's stopping condition.
        self.assertTrue(tick()['memory_fire'])
        accepted = d.pending_request
        before = arithmetic.lane_ops.copy()
        for step in range(3):
            event = tick(abort=step == 0, memory_response_ready=False)
            self.assertFalse(event['memory_fire'] or event['memory_response_fire'])
            self.assertEqual(d.owner.state, 'drain')
            self.assertIs(d.pending_request, accepted)
            self.assertEqual(arithmetic.lane_ops, before)
            self.assertIs(d.owner.scalar.client, d.owner)
            self.assertIs(d.owner.vector.client, d.owner)
            with self.assertRaisesRegex(ValueError, 'drained retired'):
                arithmetic.detach()
        self.assertTrue(tick()['memory_response_fire'])
        result = d.owner.result
        self.assertEqual(result.status, 'Aborted')
        self.assertFalse(result.staging_complete)
        self.assertEqual(result.write_bytes, len(expected_output))
        self.assertIsNone(d.pending)
        self.assertIsNone(d.memory.pending)
        self.assertIsNone(d.owner.scalar.client)
        self.assertIsNone(d.owner.vector.client)
        self.assertEqual(arithmetic.lane_ops, before)
        for _ in range(3):
            tick()
            self.assertIs(d.owner.result, result)
        d.tick()
        self.assertIs(d.response, result)
        self.assertEqual(d.owner.state, 'locked')
        self.assertEqual(d.owner.counts['chunks_started'], 2)
        self.assertEqual(d.owner.counts['chunks_completed'], 1)
        self.assertEqual(d.owner.counts['owner_results'], 1)
        self.assertEqual(d.owner.counts['read_requests'], 474881)
        self.assertEqual(d.owner.counts['write_requests'], 20872)
        self.assertEqual(d.owner.counts['write_acks'], 20872)
        self.assertEqual(d.owner.counts['memory_responses'], 474881 + 20872)
        self.assertEqual(d.owner.counts['scratch_ack_bytes'], 1319424)
        self.assertEqual(arithmetic.lane_ops, Counter(mul=6930432, add=6885696))
        self.assertEqual(arithmetic.widths, Counter({1: 4416, 16: 863232}))
        self.assertEqual(d.counts['source_read_bytes'], 204800)
        self.assertEqual(d.counts['scratch_read_bytes'], 30187584)
        self.assertEqual(d.owner.scalar_counts, Counter(exp_negative=4418))
        self.assertEqual(d.owner.exp_stats['calls'], 4418)
        self.assertEqual(d.owner.exp_stats['zero_outputs'], 0)
        self.assertEqual(d.owner.exp_stats['saturated_abs_ge_80'], 0)
        self.assertEqual(compared[0], 201728)
        self.assertEqual(compared[1], 111744)
        self.assertEqual(d.scratch.written, d.scratch.acknowledged)
        self.assertEqual(len(d.scratch.acknowledged), 20616)
        untouched = pred.address(1, 0) - d.scratch.base
        self.assertEqual(d.scratch.raw()[untouched:], pristine_scratch[untouched:])
        self.assertEqual(d.output.written, set(range(0, len(expected_output), 64)))
        self.assertEqual(d.output.written, d.output.acknowledged)
        self.assertEqual(d.output.raw()[len(expected_output):], pristine_output[len(expected_output):])
        self.assertEqual(d.state_out.raw(), pristine_state)
        self.assertFalse(d.output.published or d.state_out.published or d.scratch.published)
        self.assertFalse(d.state_out.written or d.state_out.acknowledged)
        self.assertFalse(result.state_committed or result.history_committed or result.generation_advanced)
        self.assertFalse(d.owner.vector.calls or d.owner.vector.lane_ops or d.owner.vector.host_calls)
        self.assertEqual(d.owner.vector.fatal_mask, 30)
        self.assertEqual(p.output.raw(), expected_core)
        self.assertEqual(source, tuple(region.raw() for region in p.sources))
        print(json.dumps(dict(checkpoint='validated_bounded_continuation',
            seconds=round(time.monotonic() - started, 3), accepted=dict(d.owner.counts),
            strict_lane_operations=dict(arithmetic.lane_ops), strict_flags=dict(arithmetic.flags),
            compared_matrix_words=dict(compared), carried_state_read_beats=len(carry_reads),
            prep_reference_words=len(expected_core) // 4, output_bf16_words=len(expected_output) // 2,
            scalar_calls=dict(d.owner.scalar_counts), termination=result.status,
            output_published=d.output.published, state_published=d.state_out.published)), flush=True)
        arithmetic.detach()
        d.owner.reset()
        self.assertTrue(d.owner.ports()['job_ready'])
        self.assertIs(d.owner._compute.__func__, chunk.ChunkOwner._compute)
        self.assertIs(d.owner._op.__func__, chunk.ChunkOwner._op)


if __name__ == '__main__':
    unittest.main()
