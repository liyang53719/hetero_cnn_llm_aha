"""Small real-owner checks for the isolated official-BF16 arithmetic policy.

References use exact integer/rational FP32 RNE and a fixed-order NumPy RMS
reduction. The bus and Matrix service are the existing owner protocol harness.
Attention requires MATRIX_SERVICE_LIBRARY plus its adjacent compile.json;
the receipt, sources and library are verified before loading. Never compile,
run public M16/M128 payloads, or claim RTL/physical timing acceptance here.
"""
import ctypes
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import random
import struct
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from candidates.qwen2_resident_matrix.ffn_public import prefix_arithmetic as a
from candidates.qwen2_resident_matrix.ffn_public import prefix_owners as p
from candidates.qwen2_resident_matrix.ffn_public.test_prefix_owners import (
    Harness, exact, rn, ref_add, ref_mul, ref_div, ref_bf)
from candidates.qwen2_resident_matrix.ffn_attention.attention_owner import AttentionOwner
from candidates.qwen2_resident_matrix.ffn_attention import matrix_service as m
from candidates.qwen2_resident_matrix.ffn_attention.test_scalar_recipe import reference_exp
from candidates.qwen2_resident_matrix.official_bf16.owners import (
    OfficialPrefixOwner, OfficialAttentionOwner)


def words(raw):
    return struct.unpack('<' + str(len(raw) // 4) + 'I', raw)


def prefix_harness(kind='Bias', *, left=None, right=None, width=256, tokens=1):
    j = p.Job(kind, (7 << 16) | 4, 0x100000, 0x200000, 0x300000,
              tokens, width, width, tokens * width * 4 * (2 if kind == 'KvAppend' else 1))
    left = tuple(left if left is not None else [0x3f808000] * (tokens * width))
    right_count = tokens * width if kind in ('Add', 'KvAppend') else width
    right = tuple(right if right is not None else [0x3a800000] * right_count)
    h = Harness(OfficialPrefixOwner())
    h.bus.input(j.a, left)
    h.bus.input(j.b, right)
    h.bus.output(j.dst, j.write_bytes)
    return h, j, left, right


def numpy_norm(row, gamma):
    """Independent vector schedule: residue/block/term then lane fold."""
    x = np.array(row, dtype='<u4').view('<f4')
    g = np.array(gamma, dtype='<u4').view('<f4')
    squares = np.multiply(x, x, dtype=np.float32)
    lanes = np.zeros(8, dtype=np.float32)
    for residue in range(4):
        residue_sum = np.zeros(8, dtype=np.float32)
        for block in range(3):
            partial = np.zeros(8, dtype=np.float32)
            for term in range(16):
                first = block * 512 + term * 32 + residue * 8
                partial = np.add(partial, squares[first:first + 8], dtype=np.float32)
            residue_sum = np.add(residue_sum, partial, dtype=np.float32)
        lanes = np.add(lanes, residue_sum, dtype=np.float32)
    total = np.float32(0)
    for lane in lanes:
        total = np.add(total, lane, dtype=np.float32)
    mean = np.divide(total, np.float32(1536), dtype=np.float32)
    variance = np.add(mean, np.float32(1e-6), dtype=np.float32)
    scale = np.divide(np.float32(1), np.sqrt(variance, dtype=np.float32), dtype=np.float32)
    normalized = np.multiply(x, scale, dtype=np.float32).view('<u4')
    normalized = np.array([ref_bf(int(v)) for v in normalized], dtype='<u4').view('<f4')
    weighted = np.multiply(normalized, g, dtype=np.float32).view('<u4')
    return tuple(ref_bf(int(v)) for v in weighted), a.word(total)


class RecordingScalar(a.ScalarService):
    def __init__(self):
        super().__init__()
        self.trace = []

    def op(self, client, operation, x, y=0, *, policy='vector'):
        result = super().op(client, operation, x, y, policy=policy)
        self.trace.append((operation, x, y, result, policy))
        return result


class PrefixTests(unittest.TestCase):
    def test_only_numerical_generators_are_overridden(self):
        for name in ('__init__', '_append', '_validate', '_read', '_write',
                     '_op', '_finish', '_advance', 'tick', 'ports', 'report'):
            self.assertIs(getattr(OfficialPrefixOwner, name), getattr(p.PrefixOwner, name))
        for name in ('__init__', '_validate', '_read', '_write', '_op', '_matrix_step',
                     '_finish', '_fault', '_advance', 'tick', 'ports', 'report'):
            self.assertIs(getattr(OfficialAttentionOwner, name), getattr(AttentionOwner, name))

    def test_bias_rounds_after_unrounded_fp32_sum_and_retains_stalls(self):
        h, j, left, right = prefix_harness()
        h.tick(job=j)
        request = h.owner.ports()['memory']
        for _ in range(3):
            h.tick(memory_ready=False)
            self.assertEqual(h.owner.ports()['memory'], request)
        h.until(lambda: h.bus.pending is not None and h.bus.pending.write
                and h.owner.ack_bytes == j.write_bytes - 64)
        for _ in range(3):
            h.tick(respond=False)
            self.assertIsNone(h.owner.ports()['response'])
            self.assertFalse(h.bus.outputs[j.dst].intersection(h.bus.readable))
        h.tick()
        terminal = h.owner.ports()['response']
        self.assertIsNone(terminal.status)
        self.assertEqual(terminal.write_bytes, j.write_bytes)
        for _ in range(3):
            h.tick()
            self.assertIs(h.owner.ports()['response'], terminal)
        h.tick(response_ready=True)
        h.bus.publish(h.owner, j)
        expected = tuple(ref_bf(ref_add(x, y)) for x, y in zip(left, right))
        self.assertEqual(words(h.bus.raw(j.dst)), expected)
        self.assertNotEqual(expected[0], ref_bf(ref_add(ref_bf(left[0]), right[0])))
        self.assertEqual(h.owner.scalar_counts, {'add': 256, 'bf': 256})

    def test_norm_fixed_reduction_and_two_bf16_boundaries(self):
        rng = random.Random(1536210)
        row = tuple((rng.randrange(2) << 31) | (rng.randrange(120, 133) << 23)
                    | (rng.randrange(128) << 16) for _ in range(1536))
        gamma = tuple((rng.randrange(126, 130) << 23) | (rng.randrange(128) << 16)
                      for _ in range(1536))
        h, j, _, _ = prefix_harness('Norm', left=row, right=gamma, width=1536)
        scalar = RecordingScalar()
        h.owner = OfficialPrefixOwner(scalar)
        expected, total = numpy_norm(row, gamma)
        self.assertIsNone(h.run(j).status)
        self.assertEqual(words(h.bus.raw(j.dst)), expected)
        divisions = [entry for entry in scalar.trace if entry[0] == 'div']
        self.assertEqual(divisions[0][1:3], (total, 0x44c00000))
        self.assertEqual(len(divisions), 2)
        sequential = 0
        for x in row:
            sequential = ref_add(sequential, ref_mul(x, x))
        self.assertNotEqual(total, sequential)
        self.assertEqual(h.owner.peak_row_words, 1536)
        self.assertEqual(h.owner.row_words, 0)
        self.assertEqual(h.owner.scalar_counts,
                         {'mul': 4608, 'add': 1673, 'div': 2, 'sqrt': 1, 'bf': 3072})
        self.assertEqual(h.owner.counts['read_requests'], 192)
        self.assertEqual(h.owner.counts['write_acks'], 96)

    def test_rope_table_products_and_sum_each_materialize_bf16(self):
        rng = random.Random(128210)
        x = tuple(ref_bf(a.word(rng.uniform(-2, 2))) for _ in range(512))
        cosine = tuple(a.word(rng.uniform(-1, 1)) for _ in range(128))
        sine = tuple(a.word(rng.uniform(-1, 1)) for _ in range(128))
        owner = OfficialPrefixOwner(max_tokens=2)
        j = p.Job('Rope', 7, 0x100000, 0x200000, 0x300000, 2, 256, 256, 2048,
                  c=0x200000 + 2 * 64 * 4)
        h = Harness(owner)
        for base, data in ((j.a, x), (j.b, cosine), (j.c, sine)):
            h.bus.input(base, data)
        h.bus.output(j.dst, j.write_bytes)
        expected = [0] * 512
        controls = []
        for token in range(2):
            for head in range(2):
                for lane in range(64):
                    index = token * 256 + head * 128 + lane
                    left, right = x[index], x[index + 64]
                    c, s = ref_bf(cosine[token * 64 + lane]), ref_bf(sine[token * 64 + lane])
                    expected[index] = ref_bf(ref_add(ref_bf(ref_mul(left, c)),
                                                    ref_bf(ref_mul(right, s)) ^ 0x80000000))
                    expected[index + 64] = ref_bf(ref_add(ref_bf(ref_mul(left, s)),
                                                         ref_bf(ref_mul(right, c))))
                    controls.append(ref_bf(ref_add(ref_mul(left, c), ref_mul(right, s) ^ 0x80000000)))
        self.assertIsNone(h.run(j).status)
        self.assertEqual(words(h.bus.raw(j.dst)), tuple(expected))
        lows = [expected[t * 256 + head * 128 + lane]
                for t in range(2) for head in range(2) for lane in range(64)]
        self.assertNotEqual(lows, controls)
        self.assertEqual(owner.scalar_counts, {'mul': 1024, 'add': 512, 'bf': 2048})

    def test_add_two_tiles_keep_load_compute_store_order(self):
        patterns = ((0x80000000, 0x80000000), (0x3f808000, 0x3a800000),
                    (0x00800000, 0x807fffff), (0x3f800001, 0xbf800000))
        left, right = zip(*(patterns[i % 4] for i in range(1536)))
        h, j, _, _ = prefix_harness('Add', left=left, right=right, width=1536)
        self.assertIsNone(h.run(j).status)
        self.assertEqual(words(h.bus.raw(j.dst)),
                         tuple(ref_bf(ref_add(x, y)) for x, y in zip(left, right)))
        expected = []
        for start, count in ((0, 1024), (1024, 512)):
            for base, write in ((j.a, False), (j.b, False), (j.dst, True)):
                expected.extend((base + 4 * i, write) for i in range(start, start + count, 16))
        self.assertEqual([(q.address, q.write) for q in h.bus.trace], expected)
        self.assertEqual(h.owner.peak_add_words, 3072)

    def test_add_late_fp32_or_bf16_overflow_never_leaks_same_tile(self):
        for lane in (1023, 1535):
            for x, y in ((0x7fc00000, 0), (0x7f7fffff, 0x7f7fffff), (0x7f7fffff, 0)):
                left = [0x3f800000] * 1536
                right = [0] * 1536
                left[lane], right[lane] = x, y  # max finite + zero overflows only on BF16 rounding
                h, j, _, _ = prefix_harness('Add', left=left, right=right, width=1536)
                result = h.run(j, publish=False)
                self.assertEqual(result.status, 'Numerical')
                self.assertEqual(result.write_bytes, 0 if lane == 1023 else 4096)
                self.assertEqual(len(h.bus.writes) * 64, result.write_bytes)
                self.assertFalse(h.bus.outputs[j.dst].intersection(h.bus.readable))

    def test_kv_copy_is_bit_exact_even_for_non_bf16_finite_words(self):
        h, j, left, right = prefix_harness('KvAppend', tokens=5)
        self.assertIsNone(h.run(j).status)
        self.assertEqual(words(h.bus.raw(j.dst)), left + right)
        self.assertEqual(h.owner.scalar_counts, {})
        self.assertEqual(h.owner.peak_copy_words, 1024)

    def test_same_admission_fault_and_reset_contract(self):
        for change in ({'output_bf16': True}, {'activation_bf16': True},
                       {'weight_bf16': True}, {'dst': 0x100000}):
            h, j, _, _ = prefix_harness()
            self.assertIsNotNone(h.run(replace(j, **change), publish=False).status)
            self.assertEqual(h.bus.trace, [])
        h, j, _, _ = prefix_harness()
        h.tick(job=j)
        h.tick()
        h.tick(local_reset=True, respond=False)
        self.assertEqual(h.owner.state, 'drain')
        self.assertIsNone(h.owner.ports()['response'])
        h.tick()
        self.assertEqual(h.owner.ports()['response'].status, 'Protocol')
        h.tick(response_ready=True)
        self.assertEqual(h.owner.state, 'locked')
        h.tick(reset=True)
        self.assertIsInstance(h.owner, OfficialPrefixOwner)
        self.assertTrue(h.owner.ports()['job_ready'])


def reference_attention(tokens, q, k, v):
    output, dots, scores_seen = [], [], []
    for token in range(tokens):
        for head in range(12):
            kv_head, scores = head // 6, []
            for key in range(token + 1):
                stripes = [0] * 16
                for depth in range(128):
                    x = ref_bf(q[token * 1536 + head * 128 + depth])
                    y = ref_bf(k[key * 256 + kv_head * 128 + depth])
                    lane = depth % 16
                    stripes[lane] = rn(exact(x) * exact(y) + exact(stripes[lane]))
                total = 0
                for stripe in stripes:
                    total = ref_add(total, stripe)
                dots.append(total)
                scores.append(ref_bf(ref_mul(ref_bf(total), 0x3db504f3)))
            scores_seen.extend(scores)
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
                output.append(ref_bf(accumulator))
    return tuple(output), dots, scores_seen


def verified_library():
    name = os.environ.get('MATRIX_SERVICE_LIBRARY')
    if name is None:
        raise unittest.SkipTest('MATRIX_SERVICE_LIBRARY and its compile.json receipt are required; no compile fallback')
    path = Path(name).resolve()
    receipt = json.loads(path.with_name('compile.json').read_text())
    if not (receipt['status'] == 'PASS_HOST_BUILD_ONLY' and receipt['returncode'] == 0
            and receipt['sources_before'] == receipt['sources_after']
            and Path(receipt['library']).resolve() == path
            and '-ffp-contract=off' in receipt['argv'] and '-fno-fast-math' in receipt['argv']
            and hashlib.sha256(path.read_bytes()).hexdigest() == receipt['library_sha256']):
        raise AssertionError('host-only library receipt mismatch')
    for relative, digest in receipt['sources_after'].items():
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != digest:
            raise AssertionError('host-only source drift: ' + relative)
    return m.configure_library(ctypes.CDLL(str(path)))


class AttentionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = verified_library()

    def make(self, tokens=1):
        self.assertEqual(self.library.td_reset(), 0)
        scalar = RecordingScalar()
        owner = OfficialAttentionOwner(m.MatrixService(self.library), scalar)
        j = p.Job('Attention', (9 << 16) | 12, 0x100000, 0x200000, 0x400000,
                  tokens, 1536, 128, tokens * 1536 * 4, c=0x200000 + tokens * 256 * 4)
        rng = random.Random(210128)
        q = tuple(ref_bf(a.word(rng.uniform(-1, 1))) for _ in range(tokens * 1536))
        k = tuple(ref_bf(a.word(rng.uniform(-1, 1))) for _ in range(tokens * 256))
        v = tuple(ref_bf(a.word(rng.uniform(-2, 2))) for _ in range(tokens * 256))
        h = Harness(owner)
        for base, data in ((j.a, q), (j.b, k), (j.c, v)):
            h.bus.input(base, data)
        h.bus.output(j.dst, j.write_bytes)
        return h, j, (q, k, v)

    def test_actual_qk_pv_and_scalar_outputs_match_independent_reference(self):
        h, j, data = self.make(2)
        expected, dots, scores = reference_attention(2, *data)
        self.assertIsNone(h.run(j).status)
        self.assertEqual(words(h.bus.raw(j.dst)), expected)
        trace = h.owner.scalar.trace
        actual_dots, actual_scores = [], []
        for i, entry in enumerate(trace):
            if entry[0] == 'mul' and entry[2] == 0x3db504f3:
                self.assertEqual(trace[i - 1][0], 'bf')
                self.assertEqual(entry[1], trace[i - 1][3])
                self.assertEqual(trace[i + 1][:2], ('bf', entry[3]))
                actual_dots.append(trace[i - 1][1])
                actual_scores.append(trace[i + 1][3])
        self.assertEqual(actual_dots, dots)
        self.assertEqual(actual_scores, scores)
        self.assertTrue(any(x != ref_bf(x) for x in dots))
        report = h.owner.report()
        self.assertEqual(report['peak_row_buffer_words'], 128)
        self.assertEqual(report['peak_score_buffer_words'], 2)
        self.assertEqual(report['accepted']['matrix_requests'], 12 * 3 * 16)
        self.assertEqual(report['matrix_normal_fma_calls'], 12 * 3 * 16 * 512)
        self.assertEqual(report['accepted']['exp_negative_requests'], 36)
        # Each unchanged Matrix packet packs 16 A and 16 B operands; the
        # only additional conversions are 2 per completed QK and 1 per PV
        # output lane. No intermediate accumulator conversion is permitted.
        self.assertEqual(report['scalar_primitive_calls']['bf'], 12 * 3 * 16 * 32 + 2 * 36 + 3072)
        self.assertFalse(report['hardware_simulation'])

    def test_shared_services_exclude_other_owners_until_terminal_retirement(self):
        h, j, _ = self.make()
        scalar, matrix = h.owner.scalar, h.owner.matrix
        second = OfficialAttentionOwner(matrix, scalar)
        prefix = OfficialPrefixOwner(scalar)
        bias = p.Job('Bias', 10, 0x100000, 0x200000, 0x300000, 1, 256, 256, 1024)
        self.assertTrue(h.tick(job=j)['job_fire'])
        self.assertFalse(second.tick(job=j)['job_fire'])
        self.assertFalse(prefix.tick(job=bias)['job_fire'])
        h.until(lambda: h.owner.ports()['response'] is not None)
        self.assertFalse(second.ports()['job_ready'])
        self.assertIs(matrix.owner, h.owner)
        h.tick(response_ready=True)
        self.assertTrue(second.ports()['job_ready'])
        self.assertTrue(prefix.ports()['job_ready'])

    def test_causal_reads_and_matrix_done_write_ack_terminal_stalls(self):
        h, j, _ = self.make(2)
        h.tick(job=j)
        h.until(lambda: h.owner.matrix_client.state == 'wait_done', service_done_ready=False)
        done = h.owner.matrix.done
        for _ in range(3):
            h.tick(service_done_ready=False)
            self.assertIs(h.owner.matrix.done, done)
            self.assertEqual(h.bus.writes, [])
        h.until(lambda: h.owner.ports()['memory'] is not None and h.owner.ports()['memory'].write)
        for base in (j.b, j.c):
            self.assertTrue(all(not base + 1024 <= address < base + 2048 for address in h.bus.reads))
        h.until(lambda: h.bus.pending is not None and h.bus.pending.write
                and h.owner.ack_bytes == j.write_bytes - 64)
        for _ in range(3):
            h.tick(respond=False)
            self.assertIsNone(h.owner.ports()['response'])
            self.assertIs(h.owner.matrix.owner, h.owner)
        h.tick()
        terminal = h.owner.ports()['response']
        self.assertIsNone(terminal.status)
        for _ in range(3):
            h.tick()
            self.assertIs(h.owner.ports()['response'], terminal)
            self.assertIs(h.owner.matrix.owner, h.owner)
        self.assertFalse(h.bus.outputs[j.dst].intersection(h.bus.readable))
        h.tick(response_ready=True)
        h.bus.publish(h.owner, j)
        self.assertIsNone(h.owner.matrix.owner)

    def test_reset_and_memory_faults_keep_output_unpublished(self):
        for mode in ('tag', 'error', 'reset'):
            h, j, _ = self.make()
            h.tick(job=j)
            h.until(lambda: h.bus.pending is not None)
            if mode == 'reset':
                h.tick(local_reset=True, respond=False)
                self.assertIsNone(h.owner.ports()['response'])
                h.tick()
            else:
                response = h.bus.response()
                response = replace(response, error=True) if mode == 'error' else replace(response, tag=response.tag + 1)
                h.tick(response=response)
            h.until(lambda: h.owner.ports()['response'] is not None)
            self.assertEqual(h.owner.ports()['response'].status, 'Memory' if mode == 'error' else 'Protocol')
            self.assertFalse(h.bus.outputs[j.dst].intersection(h.bus.readable))
            h.tick(response_ready=True)
            self.assertIsNone(h.owner.matrix.owner)
            h.owner.matrix.reset()
            h.tick(reset=True)
            self.assertIsInstance(h.owner, OfficialAttentionOwner)
            self.assertTrue(h.owner.ports()['job_ready'])


if __name__ == '__main__':
    unittest.main()
