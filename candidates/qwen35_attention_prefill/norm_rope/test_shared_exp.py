"""The same scalar serves Norm/RoPE and GQA; public flags remain distinct."""
from collections import Counter
import math
import random
import unittest

from .scalar import NormRopeScalar, OPCODES
from ...qwen35_gdn_prefill.rms_owner import ArithmeticFault, word
from ...qwen2_resident_matrix.ffn_public.test_prefix_owners import exact, ref_add, ref_mul


def reference_exp(a):
    magnitude = a & 0x7fffffff
    if exact(magnitude) >= 80:
        return 0
    z = ref_mul(magnitude, word(1 / math.log(2)))
    k = int(exact(z))
    fraction = ref_add(z, word(float(k)) ^ 0x80000000)
    coefficients = [word((-math.log(2)) ** i / math.factorial(i)) for i in range(8)]
    result = coefficients[-1]
    for coefficient in reversed(coefficients[:-1]):
        result = ref_add(ref_mul(result, fraction), coefficient)
    return ref_mul(result, (127 - k) << 23)


class SharedExpTests(unittest.TestCase):
    def test_existing_exp_recipe_integer_oracle_and_internal_counts(self):
        s, owner = NormRopeScalar(), object()
        self.assertTrue(s.acquire(owner))
        rng = random.Random(91)
        inputs = [0, 0x80000000, 1, 0x80000001, word(79.5), word(80)]
        inputs += [word(rng.uniform(-79, 79)) for _ in range(24)]
        for a in inputs:
            self.assertEqual(s.op(owner, 'exp_negative', a), reference_exp(a))
        self.assertEqual(OPCODES['exp_negative'], 4)
        self.assertEqual(s.calls, Counter(exp_negative=30))
        self.assertEqual(s.internal_calls, Counter(mul=29 * 9 + 1, add=29 * 8))
        s.release(owner)

    def test_raw_mul_flags_and_ieee_mul_stay_distinct_after_exp(self):
        s, owner = NormRopeScalar(), object(); s.acquire(owner)
        self.assertEqual(s.op(owner, 'exp_negative', 0), word(1))
        a, b = 0x83d70000, 0x02200000
        result = s.raw_op(owner, 'mul', a, b)
        self.assertEqual((result.bits, result.flags, result.error), (0x80000000, 3, True))
        with self.assertRaises(ArithmeticFault):
            s.op(owner, 'mul', a, b)
        self.assertEqual(s.op(owner, 'mul_ieee_rne', a, b), 0x80000000)
        self.assertEqual(s.op(owner, 'sqrt', word(4)), word(2))
        self.assertEqual(s.op(owner, 'div', word(1), word(2)), word(.5))
        self.assertEqual(s.calls, Counter(mul=2, exp_negative=1, mul_ieee_rne=1, sqrt=1, div=1))
        s.release(owner)

    def test_exclusive_client_and_nonfinite_errors_are_preserved(self):
        s, first, second = NormRopeScalar(), object(), object()
        self.assertTrue(s.acquire(first)); self.assertFalse(s.acquire(second))
        with self.assertRaises(ValueError):
            s.op(second, 'exp_negative', 0)
        self.assertFalse(s.calls)
        for a in (0x7f800000, 0xff800000, 0x7fc00001):
            with self.assertRaises(ArithmeticFault):
                s.op(first, 'exp_negative', a)
        s.release(first); self.assertTrue(s.acquire(second))
        self.assertEqual(s.op(second, 'exp_negative', 0x80000000), word(1))
        s.release(second)


if __name__ == '__main__':
    unittest.main()
