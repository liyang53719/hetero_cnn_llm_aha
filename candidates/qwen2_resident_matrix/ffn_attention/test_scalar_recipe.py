"""Independent integer-rational checks of the original exp polynomial recipe."""
from collections import Counter
from fractions import Fraction
import math
from pathlib import Path
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from candidates.qwen2_resident_matrix.ffn_public import prefix_arithmetic as a
from candidates.qwen2_resident_matrix.ffn_public.test_prefix_owners import (
    exact, rn, ref_add, ref_mul)
from candidates.qwen2_resident_matrix.ffn_attention import scalar_recipe as s


def reference_exp(bits, *, fused=False):
    """Independent oracle: exact rational RNE at each original source node.

    Constants come directly from the source's Double/libm construction. The
    candidate's coefficient table and scalar arithmetic are never consulted.
    """
    magnitude = bits & 0x7fffffff
    if exact(magnitude) >= 80:
        return 0
    z = ref_mul(magnitude, a.word(1.0 / math.log(2.0)))
    k = int(exact(z))
    frac = ref_add(z, rn(Fraction(k)) ^ 0x80000000)
    coefficients = [a.word(math.pow(-math.log(2.0), i) / math.factorial(i)) for i in range(8)]
    y = coefficients[-1]
    for coefficient in reversed(coefficients[:-1]):
        y = rn(exact(y) * exact(frac) + exact(coefficient)) if fused else ref_add(ref_mul(y, frac), coefficient)
    return ref_mul(y, (127 - k) << 23)


class ScalarRecipeTests(unittest.TestCase):
    def setUp(self):
        self.scalar, self.client = a.ScalarService(), object()
        self.assertTrue(self.scalar.acquire(self.client))

    def test_source_identity_and_constant_rounding(self):
        identity = a.source_identity()
        self.assertIn(a.SCALA_DIR + 'BlockFloat.scala', identity['control_source_sha256'])
        expected = tuple(a.word(math.pow(-math.log(2.0), i) / math.factorial(i)) for i in range(8))
        self.assertEqual(s.EXP_COEFFICIENTS, expected)
        self.assertEqual(s.LOG2_RECIPROCAL, a.word(1 / math.log(2.0)))
        self.assertEqual(identity['native_acceptance'], 'UNCHANGED_FAIL_POLICY_PENDING')

    def test_exp_bits_match_independent_integer_recipe(self):
        rng = random.Random(12017)
        vectors = [0, 0x80000000, 1, 0x80000001, 0x007fffff, 0x00800000,
                   0x3f800000, 0xbf800000, 0x429fffff, 0x42a00000, 0xc2a00000,
                   0x7f7fffff, 0xff7fffff]
        vectors += [a.word(rng.uniform(-80, 80)) for _ in range(100)]
        for bits in vectors:
            with self.subTest(bits=hex(bits)):
                actual = s.exp_negative(self.scalar, self.client, bits)
                self.assertEqual(actual, reference_exp(bits))

    def test_exp_internal_underflow_and_overflow_flags_are_ignored(self):
        self.assertEqual(s.exp_negative(self.scalar, self.client, 1), 0x3f800000)
        self.assertEqual(s.exp_negative(self.scalar, self.client, 0x7f7fffff), 0)
        with self.assertRaises(a.ArithmeticFault):
            self.scalar.op(self.client, 'mul', 1, s.LOG2_RECIPROCAL, policy='legacy_scalar')
        with self.assertRaises(a.ArithmeticFault):
            self.scalar.op(self.client, 'div', 0x00800000, a.word(3), policy='legacy_scalar')
        self.assertEqual(self.scalar.op(self.client, 'mul', 0x00800000,
                                      0x3f000000, policy='legacy_scalar'), 0x00400000)

    def test_exp_finite_admission_including_unused_b_and_ownership(self):
        for bits in (0x7f800000, 0xff800000, 0x7fc00000, 0x7f800001):
            for a_bits, b_bits in ((bits, 0), (0, bits)):
                with self.assertRaises(a.ArithmeticFault):
                    s.exp_negative(self.scalar, self.client, a_bits, b_bits)
        with self.assertRaises(ValueError):
            s.exp_negative(self.scalar, object(), 0)

    def test_separate_rounding_and_observed_primitive_calls(self):
        value = next(a.word(i / 997) for i in range(1, 10000)
                     if reference_exp(a.word(i / 997)) != reference_exp(a.word(i / 997), fused=True))
        actual = s.exp_negative(self.scalar, self.client, value)
        self.assertEqual(actual, reference_exp(value))
        self.assertNotEqual(actual, reference_exp(value, fused=True))
        self.assertEqual(self.scalar.calls, Counter(mul=9, add=8))
        self.assertEqual(s.exp_negative(self.scalar, self.client, a.word(80)), 0)
        self.assertEqual(self.scalar.calls, Counter(mul=10, add=8))


if __name__ == '__main__':
    unittest.main()
