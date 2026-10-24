"""Opt-in real native M128 cumulative-decay crossing, software staging only.

One exact shared DecayScalar, unchanged Prep/Chunk/native R2 callables, and two
actual chunk64 stages. Independent P7 recipe words and Decimal diagnostics are
not official numerical acceptance, a complete flags oracle, full block or RTL.
The old default/legacy native M128 test and all production code stay unchanged.
"""
from collections import Counter
import json
import os
import struct
import time
import unittest

import numpy as np

from candidates.qwen35_gdn_prefill.chunk import model as chunk
from candidates.qwen35_gdn_prefill.prep import model as prep
from candidates.qwen35_gdn_prefill.prep.test_model import oracle_row, reference_exp
from candidates.qwen35_gdn_prefill.rms_owner import word
from candidates.qwen35_gdn_prefill.chunk import vector as native
from candidates.qwen35_35b_exp.scalar import DecayScalar, OPERATION
from .real_producer_slice import write_raw_fixture
from .test_native_m128_single_head import expected_work
from .test_real_chunk_continuation import bf16_reference
from .decay_crossing_reference import (
    exact, rn, reference_chunk, mathematical_diagnostics, p7_reference)


def crossing_raw_inputs():
    """M128 raw BF16 boundary, not output from an executed convolution.

    Q=K=e[row mod 64]; V=e[row] in chunk0 and zero in chunk1. Each chunk
    has A[1]=40, A[2]=41, other A=-8. A_log, dt_bias and B are zero.
    Every single g is in (-80,0]; only cumulative/pairwise decays cross 80.
    """
    conv, ab = bytearray(), bytearray()
    for token in range(128):
        row = token % 64
        values = [0] * 6144
        values[row] = values[2048 + row] = 0x3f80
        if token < 64:
            values[4096 + row] = 0x3f80
        conv.extend(struct.pack('<6144H', *values))
        gates = [0] * 32
        gates[0] = word(40 if row == 1 else 41 if row == 2 else -8) >> 16
        ab.extend(struct.pack('<32H', *gates))
    return bytes(conv), bytes(ab), bytes(64), bytes(64)


def make_crossing_prep():
    memory = chunk.TypedMemory()
    scalar = DecayScalar(enable_softplus=True, enable_ieee_exp=True)
    job = prep.InputPrepJob(71, 0x100000, 0x300000, 0x310000, 0x320000,
                            0x400000, 128, heads=1)
    raw = crossing_raw_inputs()
    write_raw_fixture(memory, job.conv, raw[0], 1)
    write_raw_fixture(memory, job.ab, raw[1], 2)
    memory.add_readonly(job.a_log, raw[2])
    memory.add_readonly(job.dt_bias, raw[3])
    memory.allocate_output(job.output, job.write_bytes)
    return prep.TypedInputPrepDriver(prep.InputPrepOwner(scalar, heads=1), memory, job)


def make_crossing_chunk(p, library):
    chunk.require(p.response is not None and p.response.status is None and
                  p.output.published, 'actual successful Prep publication required')
    vector = native.Vector16(library, exception_policy=native.IEEE_POLICY,
                             arithmetic_backend=native.FINITE_MUL_UF_BACKEND)
    policy = chunk.ep.EQUAL_HEADS_EXPERIMENTAL_EXP
    job = chunk.ChunkJob(72, p.job.output, 0x800000, 0x810000, 0x820000,
                         0x900000, 128, heads=1, exp_policy=policy)
    for base, size in ((job.output, job.output_bytes), (job.state_out, job.state_bytes),
                       (job.scratch, job.scratch_bytes)):
        p.memory.allocate_output(base, size)
    owner = chunk.ChunkOwner(p.scalar_resource, vector, heads=1, host_batch=True,
                             exp_policy=policy)
    return chunk.TypedChunkDriver(owner, p.memory, job)


class NativeM128DecayCrossingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get('GDN_RUN_NATIVE_M128_DECAY_CROSSING') != '1':
            raise unittest.SkipTest('explicit native cumulative-decay crossing opt-in required')
        cls.library = os.environ['GDN_VECTOR16_FINITE_MUL_UF_LIBRARY']
        cls.identity = native.verify_library(cls.library,
            arithmetic_backend=native.FINITE_MUL_UF_BACKEND)[2]

    @classmethod
    def tearDownClass(cls):
        if native.verify_library(cls.library,
                arithmetic_backend=native.FINITE_MUL_UF_BACKEND)[2] != cls.identity:
            raise AssertionError('native source or library changed')

    def test_actual_m128_cumulative_decay_crossing_and_unpublished_staging(self):
        started = time.monotonic()
        p = make_crossing_prep()
        self.assertIs(type(p.owner.scalar), DecayScalar)
        self.assertIs(p.owner.scalar.enable_softplus, True)
        self.assertIs(p.owner.scalar.enable_ieee_exp, True)
        for name in ('op', '_node', '_evaluate_exp'):
            self.assertIs(getattr(p.owner.scalar, name).__func__, getattr(DecayScalar, name))
        self.assertFalse(set(p.owner.scalar.__dict__) & {'op', '_node', '_evaluate_exp'})
        self.assertIs(p.owner._compute.__func__, prep.InputPrepOwner._compute)
        self.assertIs(p.tick.__func__, prep.TypedInputPrepDriver.tick)
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
        g_words = core[:, 6144].view(np.uint32)
        self.assertTrue(all(-80 < exact(int(g)) <= 0 for g in g_words))
        for base in (0, 64):
            self.assertEqual(exact(int(g_words[base + 1])), -40)
            self.assertEqual(exact(int(g_words[base + 2])), -41)
        self.assertFalse(np.any(core[64:, 4096:4224].view(np.uint32)))
        exp_inputs = Counter()
        reference0 = reference_chunk(core[:64], np.zeros((128, 128), np.float32), exp_inputs=exp_inputs)
        reference1 = reference_chunk(core[64:], reference0['next_state'], exp_inputs=exp_inputs)
        references = (reference0, reference1)
        expected_exp_roles = Counter(chunk_decay=2, cumulative=128, remaining=128, pairwise=4160)
        observed_exp_roles, crossings = Counter(), Counter()
        for (role, raw), count in exp_inputs.items():
            observed_exp_roles[role] += count
            self.assertLessEqual(exact(raw), 0)
            self.assertGreater(exact(raw), -82)
            self.assertGreaterEqual(p7_reference(raw), 0x00800000)
            if exact(raw) <= -80:
                crossings[role] += count
        self.assertEqual(observed_exp_roles, expected_exp_roles)
        self.assertEqual(crossings, Counter(cumulative=124, remaining=2, pairwise=124, chunk_decay=2))
        self.assertEqual(sum(exp_inputs.values()), 4418)
        self.assertEqual(sum(crossings.values()), 252)
        for reference in references:
            cumulative = reference['gates'][:, 0].view(np.uint32)
            self.assertGreater(exact(int(cumulative[1])), -80)
            self.assertLess(exact(int(cumulative[2])), -80)
            self.assertTrue(np.all(reference['ut'][np.tril_indices(64, -1)] == 0))
        diagnostics = mathematical_diagnostics(exp_inputs)
        print('DECAY_CROSSING_MATHEMATICAL_DIAGNOSTIC ' + json.dumps(diagnostics, sort_keys=True), flush=True)

        # This is an independent counterfactual reference, NOT execution of a
        # legacy owner/native job and not evidence that legacy fatal30 passes.
        legacy0 = reference_chunk(core[:64], np.zeros((128, 128), np.float32), exp_word=reference_exp)
        legacy1 = reference_chunk(core[64:], legacy0['next_state'], exp_word=reference_exp)
        diagonal = np.arange(2, 64)
        self.assertTrue(np.all(reference1['out'][diagonal, diagonal] > 0))
        self.assertTrue(np.all(reference1['next_state'][diagonal, diagonal] > 0))
        self.assertTrue(np.all(legacy1['out'][diagonal, diagonal] == 0))
        self.assertTrue(np.all(legacy1['next_state'][diagonal, diagonal] == 0))
        candidate_bf16 = np.frombuffer(bf16_reference(reference1['out']), '<u2').reshape(64, 128)
        legacy_bf16 = np.frombuffer(bf16_reference(legacy1['out']), '<u2').reshape(64, 128)
        self.assertTrue(np.all((candidate_bf16[diagonal, diagonal] > 0) &
                               (candidate_bf16[diagonal, diagonal] < 0x7f80)))
        self.assertTrue(np.all(legacy_bf16[diagonal, diagonal] == 0))
        legacy_comparison = dict(scope='LEGACY_REFERENCE_COUNTERFACTUAL_NOT_ACTUAL_OWNER_RUN',
            chunk1_output_fp32_changed_words=int(np.count_nonzero(
                reference1['out'].view(np.uint32) != legacy1['out'].view(np.uint32))),
            final_state_fp32_changed_words=int(np.count_nonzero(
                reference1['next_state'].view(np.uint32) != legacy1['next_state'].view(np.uint32))),
            carried_only_rows_2_through_63_candidate_positive_legacy_zero=62,
            carried_only_bf16_output_signal_survives_rounding=True)
        del legacy0, legacy1
        for array in (reference0['next_state'], reference1['pred'], reference1['inter'],
                      reference1['decay_state'], reference1['next_state']):
            self.assertTrue(np.any(array.view(np.uint32) & 0x7fffffff))
        self.assertFalse(np.array_equal(reference0['next_state'], reference1['next_state']))

        observed, transactions, carry_reads, staging_reads = (Counter() for _ in range(4))
        d = make_crossing_chunk(p, self.library)
        arithmetic = d.owner.vector
        identity = arithmetic.arithmetic_identity()
        self.assertTrue(d.owner.host_batch)
        self.assertEqual(arithmetic.fatal_mask, 28)
        self.assertEqual(arithmetic.exception_policy, native.IEEE_POLICY)
        self.assertIs(arithmetic.op.__func__, native.Vector16.op)
        self.assertIs(arithmetic.mul_add.__func__, native.Vector16.mul_add)
        self.assertFalse(set(arithmetic.__dict__) & {'op', 'mul_add'})
        plan = chunk.ScratchPlan(d.job)
        self.assertEqual((d.job.tokens, d.job.chunks, d.owner.geometry), (128, 2, (1, 128, 128)))
        self.assertIs(d.input, p.output)
        self.assertIs(d.owner.scalar, p.owner.scalar)
        self.assertIs(d.owner.scalar, p.scalar_resource)
        self.assertEqual(d.owner.exp_policy, chunk.ep.EQUAL_HEADS_EXPERIMENTAL_EXP)
        self.assertEqual(d.job.exp_policy, d.owner.exp_policy)
        self.assertIs(d.owner.layout, chunk.EQUAL_HEADS)
        self.assertEqual(d.owner.matmul_policy, chunk.LEGACY_MATMUL)
        self.assertEqual(d.owner.cumsum_policy, chunk.LEGACY_CUMSUM)
        for name in ('_compute', '_op', '_solve', '_binary', '_matmul', '_mul_add', '_read',
                     '_write', '_transpose', '_exp', '_cumsum_add', '_advance', '_finish', 'tick'):
            self.assertIs(getattr(d.owner, name).__func__, getattr(chunk.ChunkOwner, name))
        self.assertIs(d.tick.__func__, chunk.TypedChunkDriver.tick)
        self.assertFalse(set(d.owner.__dict__) & {'_compute', '_op', '_exp', '_mul_add'})
        accepted_sequence = 0
        selected_underflow = None

        def tick(**kwargs):
            nonlocal accepted_sequence, selected_underflow
            context = dict(d.owner.context)
            position = dict(d.owner.position)
            before_ops = arithmetic.lane_ops.copy()
            capture = (selected_underflow is None and context['chunk'] == 1 and
                       context['phase'] == 'state_decay' and
                       position == dict(row=0, column=0))
            if capture:
                before_calls, before_flags = arithmetic.calls.copy(), arithmetic.flags.copy()
                accepted_read = d.pending_request
            event = d.tick(response_ready=False, **kwargs)
            if capture and event['memory_response_fire'] and arithmetic.calls != before_calls:
                # The original generator resumed exactly one state READ, ran
                # one native Mul, and suspended at the resulting WRITE. No
                # arithmetic method, native binding, or actual operand changed.
                self.assertEqual(arithmetic.calls - before_calls, Counter(mul=1))
                self.assertEqual(arithmetic.lane_ops - before_ops, Counter(mul=16))
                self.assertEqual(arithmetic.flags - before_flags, Counter({3: 1}))
                self.assertIsNotNone(accepted_read)
                self.assertFalse(accepted_read.write)
                self.assertEqual(accepted_read.address, plan.chunks[0][0]['next_state'].address(0, 0))
                request = d.owner.request
                self.assertTrue(request.write)
                self.assertEqual(request.address, plan.chunks[0][1]['decay_state'].address(0, 0))
                a, b, outputs, flags = map(list, (arithmetic.a, arithmetic.b,
                                                arithmetic.output, arithmetic.lane_flags))
                exact_products = [exact(x) * exact(y) for x, y in zip(a, b)]
                expected = [rn(x, bool((av ^ bv) >> 31))
                            for x, av, bv in zip(exact_products, a, b)]
                expected_flags = []
                for product, rounded in zip(exact_products, expected):
                    inexact = exact(rounded) != product
                    expected_flags.append(int(inexact) | (2 if inexact and
                        (rounded & 0x7fffffff) < 0x00800000 else 0))
                self.assertEqual(outputs, expected)
                self.assertEqual(flags, expected_flags)
                self.assertGreater(exact(a[0]), 0)
                self.assertGreater(exact(b[0]), 0)
                self.assertEqual((outputs[0], flags[0]), (0, 3))
                selected_underflow = dict(chunk=1, phase='state_decay', row=0, column=0,
                    observation='after original read response, before generated write acceptance',
                    operation='mul', active_lanes=16, aggregate_exception_flags=3,
                    actual_carried_state_read_address=accepted_read.address,
                    generated_decay_state_write_address=request.address,
                    a_words=[f'{x:08x}' for x in a], b_words=[f'{x:08x}' for x in b],
                    result_words=[f'{x:08x}' for x in outputs], lane_exception_flags=flags,
                    exact_fraction_rne_checked=True, full_flags_oracle=False)
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
        self.assertTrue(set(arithmetic.flags) <= {0, 1, 3})
        self.assertGreater(arithmetic.flags[3], 0)
        self.assertIsNotNone(selected_underflow)
        self.assertEqual(arithmetic.host_calls['mul_add'], 654336)
        self.assertEqual(arithmetic.host_calls['single'], 18752)
        self.assertEqual(arithmetic.arithmetic_identity(), identity)
        self.assertEqual(d.counts['source_read_bytes'], 204800)
        self.assertEqual(d.counts['scratch_read_bytes'], (724160 - 3200) * 64)
        self.assertEqual(d.counts['write_bytes'], 27776 * 64)
        self.assertEqual(d.owner.scalar_counts, Counter({OPERATION: 4418}))
        self.assertEqual(d.owner.exp_stats['calls'], 4418)
        self.assertEqual(d.owner.exp_stats['zero_outputs'], 0)
        self.assertEqual(d.owner.exp_stats['saturated_abs_ge_80'], 0)
        self.assertEqual(d.owner.exp_stats['inputs_abs_ge_80'], 252)
        self.assertEqual(d.owner.exp_stats['subnormal_outputs'], 0)
        self.assertEqual(d.owner.decay_counts, Counter(mul=53016, add=39762, integer_rne=4418))
        self.assertEqual(d.owner.exp_stats['max_abs_input_word'], max(
            raw & 0x7fffffff for _, raw in exp_inputs))
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
        self.assertEqual(d.owner.vector.fatal_mask, 28)
        self.assertEqual(p.output.raw(), expected_core)
        self.assertEqual(source, tuple(region.raw() for region in p.sources))
        for name in ('op', '_node', '_evaluate_exp'):
            self.assertIs(getattr(d.owner.scalar, name).__func__, getattr(DecayScalar, name))
        self.assertFalse(set(d.owner.scalar.__dict__) & {'op', '_node', '_evaluate_exp'})
        report = d.report()
        self.assertTrue(report['complete'] and report['staging_complete'])
        self.assertFalse(report['output_published'] or report['state_published'] or
                         report['state_committed'] or report['history_committed'] or report['generation_advanced'])
        print(json.dumps(dict(checkpoint='validated_native_m128_decay_crossing_staging_only',
            scope='SINGLE_HEAD_SYNTHETIC_M128_NATIVE_SOFTWARE_STAGING_ONLY',
            numerical_acceptance=None, full_block=False, official_weights=False, rtl_executed=False,
            recipe_word_agreement_is_not_mathematical_exp_acceptance=True,
            all_native_intermediates_checked=False, complete_flags_oracle=False,
            seconds=round(time.monotonic() - started, 3), accepted=dict(d.owner.counts),
            native_lane_operations=dict(arithmetic.lane_ops), native_flags=dict(arithmetic.flags),
            native_host_calls=dict(arithmetic.host_calls),
            compared_matrix_words=dict(compared), carried_state_read_beats=sum(carry_reads.values()),
            state_staging_read_beats=sum(staging_reads.values()), prep_reference_words=len(expected_core) // 4,
            output_bf16_words=d.job.output_bytes // 2, state_fp32_words=d.job.state_bytes // 4,
            scalar_calls=dict(d.owner.scalar_counts), termination=result.status,
            exp_stats=dict(d.owner.exp_stats), decay_internal_calls=dict(d.owner.decay_counts),
            independent_exp_input_roles=dict(observed_exp_roles),
            independent_exp_cross80_roles=dict(crossings),
            selected_actual_native_underflow=selected_underflow,
            legacy_reference_counterfactual=legacy_comparison,
            mathematical_diagnostic_max_ulp=diagnostics['maximum_observed_ulp_distance'],
            mathematical_diagnostic_thresholds=None,
            staging_complete=result.staging_complete, output_published=d.output.published,
            state_published=d.state_out.published)), flush=True)
        d.owner.reset()
        self.assertTrue(d.owner.ports()['job_ready'])
        self.assertIs(d.owner._compute.__func__, chunk.ChunkOwner._compute)
        self.assertIs(d.owner._op.__func__, chunk.ChunkOwner._op)


if __name__ == '__main__':
    unittest.main()
