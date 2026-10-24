"""Opt-in real native single-head M128 two-chunk staging qualification.

Unchanged Prep and ChunkOwner arithmetic/control; synthetic raw inputs, R2
Vector16 host_batch, explicit fatal30. Independent boundary words, not all
arithmetic intermediates/flags, official model, full block or RTL qualification.
"""
from collections import Counter
import json
import os
import time
import unittest

import numpy as np

from candidates.qwen35_gdn_prefill.chunk import model as chunk
from candidates.qwen35_gdn_prefill.prep import model as prep
from candidates.qwen35_gdn_prefill.prep.test_model import oracle_row
from .real_producer_slice import make_prep
from .test_native_producer_slice import make_native_chunk
from candidates.qwen35_gdn_prefill.chunk import vector as native
from .test_real_chunk_continuation import reference_chunk, bf16_reference


def expected_work():
    """Analytical row/beat/ascending-K budget, independent of observed counts."""
    traffic, arithmetic = Counter(), Counter()
    traffic[(None, 'initial_state', 'write')] = 128 * 8
    for cid in range(2):
        def phase(name, reads=0, writes=0, mul=0, add=0):
            for direction, count in (('read', reads), ('write', writes)):
                if count:
                    traffic[(cid, name, direction)] = count
            for operation, count in (('mul', mul), ('add', add)):
                if count:
                    arithmetic[(cid, name, operation)] = count

        phase('load_prep_and_cumsum', 64 * 25, 64 * 25, add=64)
        phase('cumulative_and_remaining_decay', 64, add=64)
        phase('prepare_key_query_products', 64 * 8 * 2, 64 * 8 * 4, mul=64 * 128 * 4)
        phase('prepare_vbeta', 64 * 8, 64 * 8, mul=64 * 128)
        phase('pairwise_decay', 64 * 65 // 2, 64 * 4, add=64 * 65 // 2)
        phase('transpose_k', 64 * 8, 128 * 4)
        phase('transpose_decayed_k', 64 * 8, 128 * 4)
        for name, rows, inner, cols, factor in (
                ('ut_matmul', 64, 128, 64, True),
                ('intra_matmul', 64, 128, 64, True),
                ('predict_matmul', 64, 128, 128, False),
                ('inter_matmul', 64, 128, 128, False),
                ('local_matmul', 64, 64, 128, False),
                ('state_update_matmul', 128, 64, 128, False)):
            outputs = rows * cols
            beats = outputs // 16
            phase(name, beats * (inner // 16 + inner + int(factor)), beats,
                  mul=outputs * (inner + int(factor)), add=outputs * inner)
        for name in ('solve_v', 'solve_k'):
            preceding = sum(range(64))
            coeff_beats = sum((row + 15) // 16 for row in range(64))
            phase(name, 8 * (coeff_beats + preceding + 64), 64 * 8,
                  mul=preceding * 128, add=(preceding + 64) * 128)
        for name, words in (('vnew_subtract', 64 * 128),
                            ('output_add', 64 * 128), ('state_add', 128 * 128)):
            phase(name, words // 8, words // 16, add=words)
        phase('state_decay', 128 * 8, 128 * 8, mul=128 * 128)
        phase('output_bf16_materialization', 64 * 8, 64 * 4)
    traffic[(1, 'state_staging_write', 'read')] = 128 * 8
    traffic[(1, 'state_staging_write', 'write')] = 128 * 8
    return traffic, arithmetic


class NativeM128SingleHeadTests(unittest.TestCase):
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

    def test_two_complete_chunk64_stages_with_actual_carry_and_final_acks(self):
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
        reference1 = reference_chunk(core[64:], reference0['next_state'], tail=True)
        references = (reference0, reference1)
        for array in (reference0['next_state'], reference1['pred'], reference1['inter'],
                      reference1['decay_state'], reference1['next_state']):
            self.assertTrue(np.any(array.view(np.uint32) & 0x7fffffff))
        self.assertFalse(np.array_equal(reference0['next_state'], reference1['next_state']))

        observed, transactions, carry_reads, staging_reads = (Counter() for _ in range(4))
        d = make_native_chunk(p, self.library)
        arithmetic = d.owner.vector
        identity = arithmetic.arithmetic_identity()
        self.assertTrue(d.owner.host_batch)
        self.assertEqual(arithmetic.fatal_mask, 30)
        self.assertEqual(arithmetic.exception_policy, native.LEGACY_POLICY)
        self.assertIs(arithmetic.op.__func__, native.Vector16.op)
        self.assertIs(arithmetic.mul_add.__func__, native.Vector16.mul_add)
        self.assertFalse(set(arithmetic.__dict__) & {'op', 'mul_add'})
        plan = chunk.ScratchPlan(d.job)
        self.assertEqual((d.job.tokens, d.job.chunks, d.owner.geometry), (128, 2, (1, 128, 128)))
        self.assertIs(d.input, p.output)
        self.assertIs(d.owner.scalar, p.owner.scalar)
        for name in ('_compute', '_op', '_solve', '_binary', '_matmul', '_mul_add', '_read',
                     '_write', '_transpose', '_exp', '_cumsum_add', '_advance', '_finish', 'tick'):
            self.assertIs(getattr(d.owner, name).__func__, getattr(chunk.ChunkOwner, name))
        self.assertIs(d.tick.__func__, chunk.TypedChunkDriver.tick)
        self.assertFalse(set(d.owner.__dict__) & {'_compute', '_op', '_exp', '_mul_add'})
        accepted_sequence = 0

        def tick(**kwargs):
            nonlocal accepted_sequence
            context = dict(d.owner.context)
            before_ops = arithmetic.lane_ops.copy()
            event = d.tick(response_ready=False, **kwargs)
            for operation, count in (arithmetic.lane_ops - before_ops).items():
                observed[(context['chunk'], context['phase'], operation)] += count
            if event['memory_fire']:
                request = event['memory']
                self.assertEqual(request.tag, (d.job.tag << 32) | accepted_sequence)
                accepted_sequence += 1
                transactions[(context['chunk'], context['phase'], 'write' if request.write else 'read')] += 1
                self.assertEqual(context['head'], 0)
                if context['chunk'] == 1 and not request.write:
                    previous = plan.chunks[0][0]['next_state']
                    if previous.base <= request.address < previous.base + 65536:
                        carry_reads[(context['phase'], request.address)] += 1
                    final = plan.chunks[0][1]['next_state']
                    if final.base <= request.address < final.base + 65536:
                        staging_reads[(context['phase'], request.address)] += 1
            return event

        def until(predicate):
            for _ in range(1000000):
                if predicate():
                    return
                self.assertIsNone(d.owner.result, 'unexpected terminal: ' + str(d.owner.first_numerical_failure))
                tick()
            self.fail('bounded phase request budget exhausted')

        def at_phase(cid, phase):
            return d.owner.context['chunk'] == cid and d.owner.context['phase'] == phase

        compared = Counter()
        def check_matrix(cid, name, array):
            matrix = plan.chunks[0][cid][name]
            self.assertEqual(array.shape, (matrix.rows, matrix.cols))
            expected = np.ascontiguousarray(array, dtype='<f4').tobytes()
            start = matrix.base - d.scratch.base
            self.assertEqual(d.scratch.raw()[start:start + len(expected)], expected, (cid, name))
            beats = set(range(start, start + len(expected), 64))
            self.assertTrue(beats <= d.scratch.written and beats <= d.scratch.acknowledged)
            self.assertFalse(d.scratch.published)
            compared[cid] += len(expected) // 4

        def checkpoint(name):
            print(json.dumps(dict(checkpoint=name, seconds=round(time.monotonic() - started, 3),
                chunk=d.owner.context['chunk'], phase=d.owner.context['phase'],
                reads=d.owner.counts['read_requests'], writes=d.owner.counts['write_requests'],
                native_lane_operations=sum(arithmetic.lane_ops.values()))), flush=True)

        def hold_final_ack(region, address, chunks_completed):
            until(lambda: d.pending_request is not None and d.pending_request.address == address)
            accepted, physical = d.pending_request, d.memory.pending
            self.assertTrue(accepted.write)
            before, before_counts = arithmetic.lane_ops.copy(), d.owner.counts.copy()
            for _ in range(3):
                event = tick(memory_response_ready=False)
                self.assertFalse(event['memory_fire'] or event['memory_response_fire'] or event['response_fire'])
                self.assertIs(d.pending_request, accepted)
                self.assertIs(d.memory.pending, physical)
                self.assertIsNone(d.owner.result)
                self.assertEqual(d.owner.counts, before_counts)
                self.assertEqual(d.owner.counts['chunks_completed'], chunks_completed)
                self.assertNotIn(address - region.base, region.acknowledged)
                self.assertIn(address - region.base, region.written)
                self.assertFalse(d.output.published or d.state_out.published or d.scratch.published)
                self.assertFalse(d.owner.ports()['job_ready'])
                self.assertEqual(arithmetic.lane_ops, before)
                self.assertIs(d.owner.scalar.client, d.owner)
                self.assertIs(d.owner.vector.client, d.owner)
            self.assertTrue(tick()['memory_response_fire'])
            self.assertIn(address - region.base, region.acknowledged)

        producers = ('gates', 'q', 'k', 'v', 'kb', 'vb', 'kbg', 'qg', 'ke', 'kt', 'ket', 'pair')
        stages = (('intra_matmul', 'ut'), ('solve_v', 'intra'), ('solve_k', 'solvev'),
                  ('predict_matmul', 'solvek'), ('vnew_subtract', 'pred'),
                  ('inter_matmul', 'vnew'), ('local_matmul', 'inter'),
                  ('output_add', 'local'), ('state_update_matmul', 'out'),
                  ('state_decay', 'state_update'), ('state_add', 'decay_state'),
                  ('output_bf16_materialization', 'next_state'))
        for cid, reference in enumerate(references):
            until(lambda: at_phase(cid, 'ut_matmul'))
            if cid == 0:
                initial_start = plan.initial[0].base - d.scratch.base
                self.assertEqual(d.scratch.raw()[initial_start:initial_start + 65536], bytes(65536))
                self.assertTrue(set(range(initial_start, initial_start + 65536, 64)) <= d.scratch.acknowledged)
            for name in producers:
                check_matrix(cid, name, reference[name])
            checkpoint(f'chunk{cid}_all_producers_verified')
            for next_phase, name in stages:
                until(lambda: at_phase(cid, next_phase))
                check_matrix(cid, name, reference[name])
                checkpoint(f'chunk{cid}_{name}_verified')
            hold_final_ack(d.output, d.job.output + (cid + 1) * 64 * 128 * 2 - 64, cid)
            self.assertEqual(d.owner.counts['chunks_completed'], cid + 1)
            expected_prefix = b''.join(bf16_reference(r['out']) for r in references[:cid + 1])
            self.assertEqual(d.output.raw()[:len(expected_prefix)], expected_prefix)
            self.assertEqual(d.output.written, set(range(0, len(expected_prefix), 64)))
            self.assertEqual(d.output.written, d.output.acknowledged)
            self.assertFalse(d.output.published or d.state_out.written or d.state_out.acknowledged)
            checkpoint(f'chunk{cid}_complete_output_ACKed_not_published')

        self.assertTrue(at_phase(1, 'state_staging_write'))
        expected_carry = Counter({(phase, plan.chunks[0][0]['next_state'].base + offset): count
            for phase, count in (('predict_matmul', 64), ('inter_matmul', 64), ('state_decay', 1))
            for offset in range(0, 65536, 64)})
        self.assertEqual(carry_reads, expected_carry)
        final_state = d.job.state_out + d.job.state_bytes - 64
        until(lambda: d.pending_request is not None and d.pending_request.address == final_state)
        self.assertEqual(d.owner.ack_bytes, d.job.write_bytes - 64)
        self.assertEqual(d.state_out.acknowledged, set(range(0, d.job.state_bytes - 64, 64)))
        hold_final_ack(d.state_out, final_state, 2)
        result = d.owner.result
        self.assertIsNotNone(result)
        self.assertIsNone(result.status)
        self.assertTrue(result.staging_complete)
        self.assertEqual(result.write_bytes, 98304)
        self.assertEqual((result.output, result.state_out, result.output_bytes, result.state_bytes,
                          result.expected_generation),
                         (d.job.output, d.job.state_out, 32768, 65536, 0))
        self.assertFalse(result.state_committed or result.history_committed or result.generation_advanced)
        self.assertIsNone(d.pending)
        self.assertIsNone(d.memory.pending)
        self.assertIsNone(d.owner.scalar.client)
        self.assertIsNone(d.owner.vector.client)
        before = arithmetic.lane_ops.copy()
        for _ in range(3):
            event = tick()
            self.assertIs(d.owner.result, result)
            self.assertFalse(event['memory_fire'] or event['response_fire'])
            self.assertEqual(d.owner.counts['owner_results'], 0)
            self.assertFalse(d.owner.ports()['job_ready'])
            self.assertEqual(arithmetic.lane_ops, before)
        event = d.tick()
        self.assertTrue(event['response_fire'])
        self.assertIs(d.response, result)
        self.assertEqual(d.owner.state, 'idle')
        self.assertTrue(d.owner.ports()['job_ready'])
        self.assertFalse(d.owner.poison)
        self.assertEqual(d.owner.counts['owner_results'], 1)
        with self.assertRaisesRegex(ValueError, 'already retired'):
            d.tick()

        expected_traffic, expected_arithmetic = expected_work()
        self.assertEqual(transactions, expected_traffic)
        self.assertEqual(observed, expected_arithmetic)
        self.assertEqual(accepted_sequence, 724160 + 27776)
        self.assertEqual(d.owner.counts['read_requests'], 724160)
        self.assertEqual(d.owner.counts['write_requests'], 27776)
        self.assertEqual(d.owner.counts['write_acks'], 27776)
        self.assertEqual(d.owner.counts['memory_responses'], 724160 + 27776)
        self.assertEqual(d.owner.counts['scratch_ack_bytes'], 1679360)
        self.assertEqual(d.owner.counts['chunks_started'], 2)
        self.assertEqual(d.owner.counts['chunks_completed'], 2)
        self.assertEqual(d.owner.counts['cumsum_terms'], 128)
        self.assertEqual(d.owner.counts['cumsum_add_issues'], 128)
        self.assertEqual(d.owner.counts['upper_triangle_masked'], 4032)
        self.assertEqual(arithmetic.lane_ops, Counter(mul=10600448, add=10572096))
        self.assertEqual(arithmetic.calls, Counter(mul=662528, add=664896))
        self.assertEqual(sum(arithmetic.flags.values()), sum(arithmetic.calls.values()))
        self.assertTrue(set(arithmetic.flags) <= {0, 1})
        self.assertEqual(arithmetic.host_calls['mul_add'], 654336)
        self.assertEqual(arithmetic.host_calls['single'], 18752)
        self.assertEqual(arithmetic.arithmetic_identity(), identity)
        self.assertEqual(d.counts['source_read_bytes'], 204800)
        self.assertEqual(d.counts['scratch_read_bytes'], (724160 - 3200) * 64)
        self.assertEqual(d.counts['write_bytes'], 27776 * 64)
        self.assertEqual(d.owner.scalar_counts, Counter(exp_negative=4418))
        self.assertEqual(d.owner.exp_stats['calls'], 4418)
        self.assertEqual(d.owner.exp_stats['zero_outputs'], 0)
        self.assertEqual(d.owner.exp_stats['saturated_abs_ge_80'], 0)
        self.assertEqual(compared, Counter({0: 201728, 1: 201728}))
        self.assertEqual(staging_reads, Counter({('state_staging_write',
            plan.chunks[0][1]['next_state'].base + offset): 1 for offset in range(0, 65536, 64)}))
        self.assertEqual(d.state_out.raw(), np.ascontiguousarray(reference1['next_state'], dtype='<f4').tobytes())
        self.assertEqual(d.output.raw(), b''.join(bf16_reference(r['out']) for r in references))
        for region in (d.scratch, d.output, d.state_out):
            self.assertEqual(region.written, set(range(0, region.extent, 64)))
            self.assertEqual(region.written, region.acknowledged)
            self.assertFalse(region.published)
            with self.assertRaises(ValueError):
                d.memory.exact(region.base, region.extent, readable=True)
            with self.assertRaisesRegex(ValueError, 'read before producer terminal'):
                d.memory.read64(region.base)
            region.check()
        self.assertEqual(d.owner.vector.fatal_mask, 30)
        self.assertEqual(p.output.raw(), expected_core)
        self.assertEqual(source, tuple(region.raw() for region in p.sources))
        report = d.report()
        self.assertTrue(report['complete'] and report['staging_complete'])
        self.assertFalse(report['output_published'] or report['state_published'] or
                         report['state_committed'] or report['history_committed'] or report['generation_advanced'])
        print(json.dumps(dict(checkpoint='validated_native_m128_single_head_staging_only',
            seconds=round(time.monotonic() - started, 3), accepted=dict(d.owner.counts),
            native_lane_operations=dict(arithmetic.lane_ops), native_flags=dict(arithmetic.flags),
            native_host_calls=dict(arithmetic.host_calls),
            compared_matrix_words=dict(compared), carried_state_read_beats=sum(carry_reads.values()),
            state_staging_read_beats=sum(staging_reads.values()), prep_reference_words=len(expected_core) // 4,
            output_bf16_words=d.job.output_bytes // 2, state_fp32_words=d.job.state_bytes // 4,
            scalar_calls=dict(d.owner.scalar_counts), termination=result.status,
            staging_complete=result.staging_complete, output_published=d.output.published,
            state_published=d.state_out.published)), flush=True)
        d.owner.reset()
        self.assertTrue(d.owner.ports()['job_ready'])
        self.assertIs(d.owner._compute.__func__, chunk.ChunkOwner._compute)
        self.assertIs(d.owner._op.__func__, chunk.ChunkOwner._op)


if __name__ == '__main__':
    unittest.main()
