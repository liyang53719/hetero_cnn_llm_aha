"""Restricted reference checks: Fraction arithmetic only, no native service."""
import ast
from fractions import Fraction
import math
from pathlib import Path
import struct
import time
import unittest
from unittest.mock import patch
import numpy as np

from . import reference_profile as r
from candidates.qwen2_resident_matrix.official_bf16 import test_owners as original
from candidates.qwen2_resident_matrix.ffn_public.test_prefix_owners import (
    exact, rn, ref_add, ref_mul, ref_div, ref_bf)


def fraction_exp(bits):
    """Independent exact-rational copy of the published scalar polynomial graph.

    No candidate coefficient table, ScalarService or reference-profile operation
    is consulted. Every source multiplication and addition rounds independently.
    """
    def word(value):
        return struct.unpack('<I', struct.pack('<f', value))[0]
    magnitude = bits & 0x7fffffff
    if exact(magnitude) >= 80:
        return 0
    z = ref_mul(magnitude, word(1 / math.log(2)))
    integer = int(exact(z))
    fraction = ref_add(z, rn(Fraction(integer)) ^ 0x80000000)
    coefficients = [word(math.pow(-math.log(2), i) / math.factorial(i)) for i in range(8)]
    result = coefficients[-1]
    for coefficient in reversed(coefficients[:-1]):
        result = ref_add(ref_mul(result, fraction), coefficient)
    return ref_mul(result, (127 - integer) << 23)


class ReferenceProfileTests(unittest.TestCase):
    def test_m1_m2_m4_every_boundary_matches_original_fraction_oracle(self):
        # These fail loudly if an import/refactor accidentally starts a service.
        with patch.object(original.a, 'ScalarService', side_effect=AssertionError('no scalar service')), \
             patch.object(original.m, 'MatrixService', side_effect=AssertionError('no Matrix service')), \
             patch.object(original.ctypes, 'CDLL', side_effect=AssertionError('no native library')):
            for tokens in (1, 2, 4):
                with self.subTest(tokens=tokens):
                    q, k, v = r.fixture(tokens)
                    actual = r.reference(tokens, q, k, v)
                    expected_output, expected_dots, expected_scores = original.reference_attention(
                        tokens, q.tolist(), k.tolist(), v.tolist())
                    self.assertEqual(actual.output.tolist(), list(expected_output))
                    self.assertEqual([int(x) for row in actual.dots for x in row.flat], expected_dots)
                    self.assertEqual([int(x) for row in actual.scores for x in row.flat], expected_scores)
                    offset = 0
                    for token in range(tokens):
                        for head in range(12):
                            count = token + 1
                            dots = expected_dots[offset:offset + count]
                            scores = expected_scores[offset:offset + count]
                            offset += count
                            self.assertEqual(actual.materialized_dots[token][head].tolist(), [ref_bf(x) for x in dots])
                            maximum = max(scores, key=exact)
                            self.assertEqual(int(actual.maxima[token, head]), maximum)
                            weights = [fraction_exp(ref_add(score, maximum ^ 0x80000000)) for score in scores]
                            self.assertEqual(actual.weights[token][head].tolist(), weights)
                            total, prefixes = 0, []
                            for weight in weights:
                                total = ref_add(total, weight); prefixes.append(total)
                            self.assertEqual(actual.prefix_totals[token][head].tolist(), prefixes)
                            self.assertEqual(int(actual.totals[token, head]), total)
                            inverse = ref_div(0x3f800000, total)
                            self.assertEqual(int(actual.inverses[token, head]), inverse)
                            normalized = [ref_mul(weight, inverse) for weight in weights]
                            self.assertEqual(actual.normalized_fp32[token][head].tolist(), normalized)
                            probabilities = [ref_bf(x) for x in normalized]
                            self.assertEqual(actual.normalized[token][head].tolist(), probabilities)
                            # The original public oracle only exposes post-BF
                            # output. Independently check the final pre-BF PV
                            # accumulator too, at each preserved key step.
                            for col in range(128):
                                accumulator = 0
                                for key, probability in enumerate(probabilities):
                                    value = int(v[key * 256 + (head // 6) * 128 + col])
                                    accumulator = rn(exact(probability) * exact(value) + exact(accumulator))
                                self.assertEqual(int(actual.pv[token, head, col]), accumulator)
                    self.assertFalse(actual.output.flags.writeable)
                    self.assertEqual(actual.pv.shape, (tokens, 12, 128))
                    self.assertEqual([ref_bf(int(x)) for x in actual.pv.flat], actual.output.tolist())

    def test_fma_exact_grid_signed_zeros_and_cancellation(self):
        q = r._float(np.array([0x80000000, 0x80000000, 0x3d800000, 0xbd800000, 0x3c800000], dtype=np.uint32))
        k = r._float(np.array([0x3d800000, 0x3d800000, 0x3d800000, 0xbd800000, 0xbc800000], dtype=np.uint32))
        acc = r._float(np.array([0x80000000, 0, 0xbb800000, 0xbb800000, 0x39800000], dtype=np.uint32))
        actual = r._words(r._fma_checked(q, k, acc, kind='qk', step=2))
        expected = []
        for x, y, a in zip(r._words(q), r._words(k), r._words(acc)):
            x, y, a = int(x), int(y), int(a)
            negative_zero = exact(x) * exact(y) == 0 and exact(a) == 0 and bool((x ^ y) >> 31) and bool(a >> 31)
            expected.append(rn(exact(x) * exact(y) + exact(a), negative_zero))
        self.assertEqual(actual.tolist(), expected)
        self.assertEqual(actual.tolist(), [0x80000000, 0, 0, 0, 0])
        probability = np.array([1 / 256, 1, 1 / 256], dtype=np.float32)
        values = r._float(np.array([0x80000000, 0xbf800000, 0xbe000000], dtype=np.uint32))
        accumulators = r._float(np.array([0x80000000, 0x3f800000, 0x3a000000], dtype=np.uint32))
        result = r._words(r._fma_checked(probability, values, accumulators, kind='pv', step=2))
        self.assertEqual(result.tolist(), [0x80000000, 0, 0])

    def test_probability_grid_boundaries_and_all_pv_steps(self):
        # 128 synthetic scalar operation checks, not an M128 Attention run.
        probability = np.array([1 / 256, 1, 127 / 128], dtype=np.float32)
        values = np.array([1 / 8, -1, 1 / 2], dtype=np.float32)
        accumulator = np.zeros(3, dtype=np.float32)
        expected = [0] * 3
        for step in range(1, 129):
            accumulator = r._fma_checked(probability, values, accumulator, kind='pv', step=step)
            for i, (p, v) in enumerate(zip(r._words(probability), r._words(values))):
                expected[i] = rn(exact(int(p)) * exact(int(v)) + exact(expected[i]))
            self.assertEqual(r._words(accumulator).tolist(), expected)

    def test_exp_unfused_nodes_and_bf16_ties_match_fraction(self):
        inputs = [rn(Fraction(-i, 2048)) for i in range(257)]
        actual = r._words(r._exp_negative(r._float(np.asarray(inputs, dtype=np.uint32))))
        self.assertEqual(actual.tolist(), [fraction_exp(word) for word in inputs])
        ties = np.array([0, 0x80000000, 0x3f008000, 0x3f018000, 0xbf008000,
                         0xbf018000, 0x3eff8000, 0xbeff8000], dtype=np.uint32)
        self.assertEqual(r._words(r._bf(r._float(ties))).tolist(), [ref_bf(int(word)) for word in ties])

    def test_out_of_domain_guards_survive_optimization(self):
        q, k, v = r.fixture(1)
        for index, replacement in ((0, 0x7fc00000), (0, 1), (0, 0x3d800001),
                                   (0, 0x3e000000), (2, 0x3d800000)):
            values = [q.copy(), k.copy(), v.copy()]
            values[index][0] = replacement
            with self.subTest(index=index, replacement=replacement), self.assertRaises(ValueError):
                r.reference(1, *values)
        for count in (0, 129, True, 1.0):
            with self.subTest(count=count), self.assertRaises(ValueError):
                r.fixture(count)
        with self.assertRaises(ValueError):
            r._grid(np.array([2 ** -19], dtype=np.float32), -18, 1)
        with self.assertRaises(ValueError):
            r._fma_checked(np.array([1 / 512], dtype=np.float32), np.array([1.], dtype=np.float32),
                           np.zeros(1, dtype=np.float32), kind='pv', step=1)
        with self.assertRaises(ValueError):
            r._fma_checked(np.array([1.], dtype=np.float32), np.array([1.], dtype=np.float32),
                           np.ones(1, dtype=np.float32), kind='pv', step=1)

    def test_fixture_repeatability_packed_storage_and_no_candidate_imports(self):
        for first, second, palette in zip(r.fixture(4), r.fixture(4), (r.QK_PALETTE, r.QK_PALETTE, r.V_PALETTE)):
            np.testing.assert_array_equal(first, second)
            self.assertEqual(set(first.tolist()), set(palette))
            self.assertFalse(first.flags.writeable)
        result = r.reference(2, *r.fixture(2))
        expected_bytes = 7 * 12 * (2 * 3 // 2) * 4 + 3 * 2 * 12 * 4 + 2 * 2 * 1536 * 4
        self.assertEqual(result.nbytes, expected_bytes)
        maximum_bytes = 7 * 12 * (128 * 129 // 2) * 4 + 3 * 128 * 12 * 4 + 2 * 128 * 1536 * 4
        self.assertLess(maximum_bytes, 5 * 1024 * 1024)
        for name in ('dots', 'scores', 'weights', 'normalized', 'prefix_totals'):
            self.assertEqual([a.shape for a in getattr(result, name)], [(12, 1), (12, 2)])
            self.assertTrue(all(not a.flags.writeable for a in getattr(result, name)))
        tree = ast.parse(Path(r.__file__).read_text())
        self.assertFalse(any(isinstance(node, ast.Assert) for node in ast.walk(tree)))
        imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        self.assertEqual(imports, ['dataclasses'])
        forbidden = {'sum', 'dot', 'exp', 'matmul', 'einsum', 'CDLL', 'ScalarService', 'MatrixService'}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                self.assertNotIn(node.func.attr, forbidden)


if __name__ == '__main__':
    unittest.main()
