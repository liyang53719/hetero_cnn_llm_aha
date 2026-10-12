"""Bounded, synthetic memory/Matrix/scalar Attention checks, never RTL.

MATRIX_SERVICE_LIBRARY reuses the parent's combined host library. Otherwise a
single tiny host-only library is compiled in /tmp. The test bus writes only on
matching accepted ACKs and publishes only after the accepted owner terminal.
The independent arithmetic oracle uses exact integer/rational FP32 RNE.
"""
import ctypes as C
from dataclasses import replace
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from candidates.qwen2_resident_matrix.ffn_public import prefix_arithmetic as arithmetic
from candidates.qwen2_resident_matrix.ffn_public import prefix_owners as p
from candidates.qwen2_resident_matrix.ffn_public.test_prefix_owners import (
    Bus, Harness, exact, rn, ref_add, ref_mul, ref_div, ref_bf)
from candidates.qwen2_resident_matrix.ffn_attention import matrix_service as m
from candidates.qwen2_resident_matrix.ffn_attention.attention_owner import AttentionOwner
from candidates.qwen2_resident_matrix.ffn_attention.test_scalar_recipe import reference_exp

LIB = None
TEMP = None


def setUpModule():
    global LIB, TEMP
    path = os.environ.get('MATRIX_SERVICE_LIBRARY') or os.environ.get('MATRIX_TEST_LIBRARY')
    if path is None:
        TEMP = tempfile.TemporaryDirectory(prefix='qwen2_attention_owner_')
        path = str(Path(TEMP.name) / 'matrix_numeric.so')
        source = Path(__file__).with_name('matrix_numeric.cpp')
        subprocess.run(['g++', '-shared', '-fPIC', '-O2', '-ffp-contract=off',
                        '-fno-fast-math', str(source), '-o', path], check=True, timeout=30)
    LIB = m.configure_library(C.CDLL(path))


def tearDownModule():
    if TEMP is not None:
        TEMP.cleanup()


def service():
    assert LIB.td_reset() == 0
    return m.MatrixService(LIB)


def make_job(tokens=1, **changes):
    job = p.Job('Attention', (9 << 16) | 12, 0x100000, 0x200000, 0x400000,
                tokens, 1536, 128, tokens * 1536 * 4, c=0x200000 + tokens * 256 * 4)
    return replace(job, **changes)


def make_harness(tokens=1, *, q=None, k=None, v=None, **job_changes):
    j = make_job(tokens, **job_changes)
    owner = AttentionOwner(service(), arithmetic.ScalarService())
    h = Harness(owner)
    q = q if q is not None else tuple(arithmetic.word((i % 17 - 8) / 32) for i in range(tokens * 1536))
    k = k if k is not None else tuple(arithmetic.word((i % 13 - 6) / 32) for i in range(tokens * 256))
    v = v if v is not None else tuple(arithmetic.word((i % 19 - 9) / 32) for i in range(tokens * 256))
    h.bus.input(j.a, q)
    h.bus.input(j.b, k)
    h.bus.input(j.c, v)
    h.bus.output(j.dst, j.write_bytes)
    return h, j, (q, k, v)


def reference_attention(tokens, q, k, v):
    """Independent exact-rational reference, no Matrix/scalar candidate helper."""
    output = []
    for token in range(tokens):
        for head in range(12):
            kv_head = head // 6
            scores = []
            for key in range(token + 1):
                lanes = [0] * 16
                for depth in range(128):
                    x = ref_bf(q[token * 1536 + head * 128 + depth])
                    y = ref_bf(k[key * 256 + kv_head * 128 + depth])
                    lane = depth % 16
                    lanes[lane] = rn(exact(x) * exact(y) + exact(lanes[lane]))
                total = 0
                for lane in lanes:
                    total = ref_add(total, lane)
                scores.append(ref_mul(total, 0x3db504f3))
            maximum = max(scores, key=exact)
            probabilities, total = [], 0
            for score in scores:
                probability = reference_exp(ref_add(score, maximum ^ 0x80000000))
                probabilities.append(probability)
                total = ref_add(total, probability)
            inverse = ref_div(0x3f800000, total)
            for col in range(128):
                accumulator = 0
                for key, probability in enumerate(probabilities):
                    probability = ref_bf(ref_mul(probability, inverse))
                    value = ref_bf(v[key * 256 + kv_head * 128 + col])
                    accumulator = rn(exact(probability) * exact(value) + exact(accumulator))
                output.append(accumulator)
    return tuple(output)


class AttentionArithmeticTests(unittest.TestCase):
    def test_exact_original_recipe_and_causal_gqa_mapping_from_read_responses(self):
        h, j, inputs = make_harness(2)
        result = h.run(j)
        self.assertIsNone(result.status)
        expected = reference_attention(2, *inputs)
        self.assertEqual(h.bus.raw(j.dst), struct.pack('<3072I', *expected))
        report = h.owner.report()
        self.assertTrue(report['synthetic_shape'])
        self.assertIsNone(report['fullgraph_profile'])
        self.assertEqual(report['peak_row_buffer_words'], 128)
        self.assertEqual(report['peak_score_buffer_words'], 2)
        self.assertEqual(report['peak_probability_buffer_words'], 2)
        self.assertEqual(report['accepted']['read_requests'], 12 * (2 * 8 + 3 * 16))
        self.assertEqual(report['accepted']['matrix_requests'], 12 * 3 * 16)
        self.assertEqual(report['accepted']['matrix_results'], report['accepted']['matrix_requests'])
        self.assertEqual(result.executed_macs, report['matrix_normal_fma_calls'])
        self.assertEqual(result.executed_macs, report['accepted']['matrix_results'] * 512)
        self.assertEqual(result.useful_macs, report['accepted']['matrix_results'] * 16)
        self.assertEqual(report['accepted']['write_acks'] * 64, j.write_bytes)
        self.assertFalse(report['model_ticks_are_hardware_cycles'])
        self.assertFalse(report['hardware_simulation'])

    def test_returned_memory_data_changes_output_and_future_token_is_never_read(self):
        h, j, inputs = make_harness(2, q=(0,) * 3072, k=(0,) * 512,
                                      v=tuple(arithmetic.word((i // 128 + 1) / 8) for i in range(512)))
        h.tick(job=j)
        h.until(lambda: h.owner.ports()['memory'] is not None and h.owner.ports()['memory'].write)
        before = list(h.bus.reads)
        self.assertTrue(all(not (j.b + 256 * 4 <= a < j.b + 512 * 4) for a in before))
        self.assertTrue(all(not (j.c + 256 * 4 <= a < j.c + 512 * 4) for a in before))
        h.until(lambda: h.owner.ports()['response'] is not None)
        h.tick(response_ready=True)
        actual = struct.unpack('<3072I', h.bus.raw(j.dst))
        self.assertEqual(actual[:6 * 128], (arithmetic.word(1 / 8),) * (6 * 128))
        self.assertEqual(actual[6 * 128:1536], (arithmetic.word(2 / 8),) * (6 * 128))
        self.assertEqual(actual[1536:1536 + 6 * 128], (arithmetic.word(2 / 8),) * (6 * 128))
        self.assertEqual(actual[1536 + 6 * 128:], (arithmetic.word(3 / 8),) * (6 * 128))
        # The second run changes accepted response words, not a candidate tensor.
        h, j, _ = make_harness(1, q=(0,) * 1536, k=(0,) * 256, v=(0,) * 256)
        h.tick(job=j)
        h.until(lambda: h.bus.pending is not None and h.bus.pending.address == j.c)
        replacement = (arithmetic.word(0.75),) * 16
        h.tick(response=p.MemoryResponse(h.bus.pending.tag, replacement))
        h.until(lambda: h.owner.ports()['response'] is not None)
        self.assertEqual(h.bus.words[j.dst], struct.pack('<16I', *replacement))

    def test_generic_tag_and_disjoint_kv_views_are_not_private_host_conventions(self):
        h, j, _ = make_harness(1, tag=0x12345678, c=0x300000)
        self.assertIsNone(h.run(j).status)
        self.assertEqual(h.owner.job.tag, 0x12345678)

    def test_attention_score_underflow_is_fatal_after_real_matrix_results(self):
        q, k = (0x00010000,) + (0,) * 1535, (0x3f800000,) + (0,) * 255
        h, j, _ = make_harness(q=q, k=k)
        result = h.run(j, publish=False)
        self.assertEqual(result.status, 'Numerical')
        self.assertIn('underflow', h.owner.detail)
        self.assertEqual(h.owner.counts['matrix_results'], 8)
        self.assertEqual(h.owner.report()['matrix_normal_fma_calls'], 8 * 512)
        self.assertEqual(h.bus.writes, [])

    def test_finite_cross_product_overflow_is_ignored_outside_selected_diagonal(self):
        # All QK diagonal products are exactly zero. The cross product
        # row0/column1 overflows from two finite BF16 operands (2**127).
        # Matrix arithmetic flags are not a protocol error in the source.
        q, k = (0x7f000000,) + (0,) * 1535, (0, 0x7f000000) + (0,) * 254
        h, j, _ = make_harness(q=q, k=k, v=(0x3e000000,) * 256)
        h.tick(job=j)
        h.until(lambda: h.owner.matrix.result is not None, service_result_ready=False)
        matrix_result = h.owner.matrix.result
        self.assertFalse(matrix_result.error)
        self.assertEqual(matrix_result.value[0][1], 0x7f800000)
        self.assertEqual(tuple(matrix_result.value[i][i] for i in range(16)), (0,) * 16)
        self.assertEqual(h.owner.matrix.report()['normal_fma_calls'], 512)
        h.until(lambda: h.owner.ports()['response'] is not None)
        result = h.owner.ports()['response']
        self.assertIsNone(result.status)
        self.assertEqual(result.executed_macs, 192 * 512)
        self.assertEqual(result.useful_macs, 192 * 16)
        h.tick(response_ready=True)
        h.bus.publish(h.owner, j)
        self.assertEqual(h.bus.raw(j.dst), struct.pack('<1536I', *((0x3e000000,) * 1536)))

    def test_selected_qk_and_pv_inf_nan_are_numerical_after_all_physical_fmas(self):
        for operation in ('qk', 'pv'):
            for nonfinite in ('inf', 'nan'):
                with self.subTest(operation=operation, nonfinite=nonfinite):
                    q, k, v = [0] * 1536, [0] * 256, [0] * 256
                    if operation == 'qk':
                        # Infinity is generated by finite operands; NaN is
                        # an accepted memory operand propagated by the FMA.
                        q[0] = 0x7f000000 if nonfinite == 'inf' else 0x7fc10000
                        k[0] = 0x7f000000 if nonfinite == 'inf' else 0x3f800000
                    else:
                        v[0] = 0x7f800000 if nonfinite == 'inf' else 0x7fc10000
                    h, j, _ = make_harness(q=tuple(q), k=tuple(k), v=tuple(v))
                    result = h.run(j, publish=False)
                    packets = 1 if operation == 'qk' else 9
                    self.assertEqual(result.status, 'Numerical')
                    self.assertIn('nonfinite legacy Matrix output lane', h.owner.detail)
                    self.assertEqual(result.executed_macs, packets * 512)
                    self.assertEqual(result.useful_macs, packets * 16)
                    self.assertEqual(h.owner.counts['matrix_results'], packets)
                    self.assertEqual(result.write_bytes, 0)
                    self.assertEqual(h.bus.writes, [])
                    self.assertFalse(h.bus.readable.intersection(h.bus.outputs[j.dst]))
                    self.assertIsNone(h.owner.matrix.owner)


class AttentionProtocolTests(unittest.TestCase):
    def test_request_and_matrix_result_stalls_hold_payload(self):
        h, j, _ = make_harness()
        h.tick(job=j)
        held = h.owner.ports()['memory']
        for _ in range(3):
            h.tick(memory_ready=False)
            self.assertEqual(h.owner.ports()['memory'], held)
        h.until(lambda: h.owner.ports()['matrix'] is not None)
        held = h.owner.ports()['matrix']
        for _ in range(3):
            h.tick(matrix_request_ready=False)
            self.assertEqual(h.owner.ports()['matrix'], held)
        h.until(lambda: h.owner.matrix.result is not None, service_result_ready=False)
        held = h.owner.matrix.result
        for _ in range(3):
            h.tick(service_result_ready=False)
            self.assertIs(h.owner.matrix.result, held)
            self.assertEqual(h.bus.writes, [])
        h.until(lambda: h.owner.matrix_client.ports()['result'] is not None, matrix_result_ready=False)
        held = h.owner.matrix_client.ports()['result']
        for _ in range(3):
            h.tick(matrix_result_ready=False)
            self.assertIs(h.owner.matrix_client.ports()['result'], held)
        h.until(lambda: h.owner.ports()['response'] is not None)
        h.tick(response_ready=True)

    def test_final_matrix_done_and_final_write_ack_gate_terminal_and_publication(self):
        h, j, _ = make_harness()
        h.tick(job=j)
        h.until(lambda: h.owner.matrix_client.state == 'wait_done', service_done_ready=False)
        done = h.owner.matrix.done
        for _ in range(3):
            h.tick(service_done_ready=False)
            self.assertIs(h.owner.matrix.done, done)
            self.assertIsNone(h.owner.ports()['response'])
            self.assertEqual(h.bus.writes, [])
        h.until(lambda: h.bus.pending is not None and h.bus.pending.write
                and h.owner.ack_bytes == j.write_bytes - 64)
        for _ in range(3):
            h.tick(respond=False)
            self.assertEqual(h.owner.ack_bytes, j.write_bytes - 64)
            self.assertIsNone(h.owner.ports()['response'])
            self.assertIs(h.owner.matrix.owner, h.owner)
            self.assertFalse(h.bus.readable.intersection(h.bus.outputs[j.dst]))
        h.tick()
        terminal = h.owner.ports()['response']
        self.assertIsNone(terminal.status)
        self.assertEqual(terminal.write_bytes, j.write_bytes)
        for _ in range(3):
            h.tick()
            self.assertIs(h.owner.ports()['response'], terminal)
            self.assertIs(h.owner.matrix.owner, h.owner)
        h.tick(response_ready=True)
        self.assertIsNone(h.owner.matrix.owner)
        h.bus.publish(h.owner, j)

    def test_memory_tag_error_short_and_nonfinite_never_publish(self):
        for mode in ('tag', 'error', 'length', 'short', 'nonfinite'):
            with self.subTest(mode=mode):
                h, j, _ = make_harness()
                h.tick(job=j)
                h.until(lambda: h.bus.pending is not None)
                response = h.bus.response()
                if mode == 'tag':
                    response = replace(response, tag=response.tag + 1)
                elif mode == 'error':
                    response = replace(response, error=True)
                elif mode == 'length':
                    response = replace(response, nbytes=32)
                elif mode == 'short':
                    response = replace(response, data=bytes(32))
                else:
                    response = replace(response, data=(0x7f800000,) + (0,) * 15)
                h.tick(response=response)
                h.until(lambda: h.owner.ports()['response'] is not None)
                result = h.owner.ports()['response']
                self.assertEqual(result.status, 'Memory' if mode == 'error'
                                 else 'Numerical' if mode == 'nonfinite' else 'Protocol')
                self.assertEqual(result.write_bytes, 0)
                self.assertFalse(h.bus.readable.intersection(h.bus.outputs[j.dst]))
                h.tick(response_ready=True)
                self.assertEqual(h.owner.state, 'locked')
                self.assertIsNone(h.owner.matrix.owner)

    def test_wrong_matrix_done_tag_faults_and_retires_before_error_terminal(self):
        h, j, _ = make_harness()
        h.tick(job=j)
        h.until(lambda: h.owner.matrix_client.state == 'wait_done', service_done_ready=False)
        done = h.owner.matrix.done
        h.tick(done_override=replace(done, tag=done.tag + 1))
        h.until(lambda: h.owner.ports()['response'] is not None)
        self.assertEqual(h.owner.ports()['response'].status, 'Protocol')
        self.assertEqual(h.owner.ack_bytes, 0)
        h.tick(response_ready=True)
        self.assertIsNone(h.owner.matrix.owner)
        self.assertTrue(h.owner.matrix.reset_required)

    def test_reset_between_matrix_packets_drains_memory_and_done_without_publish(self):
        for write in (False, True):
            h, j, _ = make_harness()
            h.tick(job=j)
            h.until(lambda: h.bus.pending is not None and h.bus.pending.write == write
                    and (write or h.owner.counts['matrix_results'] == 1))
            h.tick(local_reset=True, respond=False, service_done_ready=False)
            for _ in range(3):
                h.tick(respond=False, service_done_ready=False)
                self.assertIsNone(h.owner.ports()['response'])
            h.tick(service_done_ready=False)
            if not write:
                self.assertIsNone(h.owner.ports()['response'])
            h.until(lambda: h.owner.ports()['response'] is not None)
            self.assertEqual(h.owner.ports()['response'].status, 'Protocol')
            self.assertEqual(h.owner.ack_bytes, 64 if write else 0)
            h.tick(response_ready=True)
            self.assertFalse(h.owner.ports()['job_ready'])
            h.owner.matrix.reset()
            h.tick(reset=True)
            self.assertTrue(h.owner.ports()['job_ready'])

    def test_reset_on_each_matrix_stage_drains_accepted_obligations(self):
        for state in ('begin', 'issue', 'wait_result', 'reply', 'wait_done'):
            with self.subTest(state=state):
                h, j, _ = make_harness()
                h.tick(job=j)
                h.until(lambda: h.owner.matrix_client.state == state)
                h.tick(reset=True)
                h.until(lambda: h.owner.ports()['response'] is not None)
                self.assertEqual(h.owner.ports()['response'].status, 'Protocol')
                h.tick(response_ready=True)
                self.assertIsNone(h.owner.matrix.owner)
                self.assertEqual(h.bus.writes, [])

    def test_final_write_error_and_reset_on_held_terminal_keep_unpublished(self):
        for mode in ('error', 'reset'):
            h, j, _ = make_harness()
            h.tick(job=j)
            if mode == 'error':
                h.until(lambda: h.bus.pending is not None and h.bus.pending.write
                        and h.owner.ack_bytes == j.write_bytes - 64)
                h.tick(response=replace(h.bus.response(), error=True))
            else:
                h.until(lambda: h.owner.ports()['response'] is not None)
                edge = h.tick(local_reset=True, response_ready=True)
                self.assertFalse(edge['response_fire'])
            h.until(lambda: h.owner.ports()['response'] is not None)
            self.assertEqual(h.owner.ports()['response'].status, 'Memory' if mode == 'error' else 'Protocol')
            h.tick(response_ready=True)
            self.assertFalse(h.bus.readable.intersection(h.bus.outputs[j.dst]))

    def test_shared_scalar_and_matrix_prevent_concurrent_owners(self):
        matrix, scalar = service(), arithmetic.ScalarService()
        one, two = AttentionOwner(matrix, scalar), AttentionOwner(matrix, scalar)
        prefix = p.PrefixOwner(scalar)
        self.assertTrue(one.tick(job=make_job())['job_fire'])
        self.assertFalse(two.tick(job=make_job())['job_fire'])
        bias = p.Job('Bias', 10, 0x100000, 0x200000, 0x300000, 1, 256, 256, 1024)
        self.assertFalse(prefix.tick(job=bias)['job_fire'])
        one.tick(local_reset=True)
        self.assertIsNone(scalar.client)
        self.assertFalse(two.ports()['job_ready'])
        self.assertIs(matrix.owner, one)
        one.tick(response_ready=True)
        self.assertIsNone(matrix.owner)

    def test_external_matrix_abort_during_read_drains_and_does_not_hang(self):
        h, j, _ = make_harness()
        h.tick(job=j)
        h.until(lambda: h.bus.pending is not None and h.owner.counts['matrix_results'] == 1)
        h.owner.matrix.abort(h.owner)
        h.tick(respond=False, service_done_ready=False)
        self.assertIsNone(h.owner.ports()['response'])
        h.until(lambda: h.owner.ports()['response'] is not None)
        self.assertEqual(h.owner.ports()['response'].status, 'Protocol')
        h.tick(response_ready=True)
        self.assertIsNone(h.owner.matrix.owner)
        self.assertEqual(h.bus.writes, [])

    def test_observed_report_is_frozen_across_subsequent_shared_service_use(self):
        h, j, inputs = make_harness()
        self.assertIsNone(h.run(j).status)
        expected = h.owner.report()
        second = Harness(AttentionOwner(h.owner.matrix, h.owner.scalar))
        for base, values in zip((j.a, j.b, j.c), inputs):
            second.bus.input(base, values)
        second.bus.output(j.dst, j.write_bytes)
        self.assertIsNone(second.run(j).status)
        self.assertEqual(h.owner.report(), expected)

    def test_reset_on_admission_and_after_success_never_repeats_a_terminal(self):
        h, j, _ = make_harness()
        edge = h.tick(job=j, local_reset=True)
        self.assertFalse(edge['job_fire'])
        self.assertIsNone(h.owner.ports()['response'])
        self.assertIsNone(h.owner.matrix.owner)
        h.tick(reset=True)
        self.assertIsNone(h.run(j).status)
        h.tick(local_reset=True)
        self.assertEqual(h.owner.state, 'locked')
        self.assertIsNone(h.owner.ports()['response'])

    def test_bounds_and_alias_fail_before_io(self):
        j = make_job()
        for changes in ({'kind': 'Dense'}, {'n': 256}, {'k': 16}, {'m': 0},
                        {'m': 1025}, {'write_bytes': 64}, {'tag': 1 << 32},
                        {'dst': j.a}, {'c': j.b}, {'b': j.a}, {'a': j.a + 4},
                        {'output_bf16': True}):
            owner = AttentionOwner(service())
            self.assertTrue(owner.tick(job=replace(j, **changes))['job_fire'])
            self.assertIsNotNone(owner.ports()['response'].status)
            self.assertIsNone(owner.ports()['memory'])
            self.assertIsNone(owner.matrix.owner)
            self.assertIsNone(owner.scalar.client)


if __name__ == '__main__':
    unittest.main()
