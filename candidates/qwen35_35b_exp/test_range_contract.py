"""Directed range diagnostics and existing admission gates, not exp acceptance.

Requires GDN_VECTOR16_R2_LIBRARY pointing to an already verified R2 build.
Never builds a library, imports Torch, downloads data, or runs a chunk owner.
"""
from decimal import Decimal, localcontext
from fractions import Fraction
import json
import os
from pathlib import Path
import unittest

from .scalar import DecayScalar, OPERATION, ArithmeticFault
from ..qwen35_gdn_prefill.chunk import exp_policy as ep
from ..qwen35_gdn_prefill.chunk.vector import (
    Vector16, VectorArithmeticFault, IEEE_POLICY, FINITE_MUL_UF_BACKEND,
)
from ..qwen35_gdn_prefill.prep.layout import EQUAL_HEADS, GROUPED_35B


def exact_word(raw):
    """Exact finite FP32 input as rational; no float/libm conversion."""
    exponent = (raw >> 23) & 255
    if exponent == 255:
        raise ValueError('finite input required')
    significand = (raw & 0x7fffff) | (0x800000 if exponent else 0)
    power = (exponent if exponent else 1) - 150
    value = Fraction(significand) * Fraction(2) ** power
    return -value if raw >> 31 else value


def rne_integer(numerator, denominator):
    quotient, remainder = divmod(numerator, denominator)
    return quotient + (2 * remainder > denominator or
                       (2 * remainder == denominator and quotient & 1))


def positive_fraction_to_fp32(value):
    """Integer round-to-nearest-even, including subnormal/carry boundaries."""
    if value < 0 or value > 1:
        raise ValueError('exp diagnostic output must be in [0,1]')
    if not value:
        return 0
    n, d = value.numerator, value.denominator
    exponent = n.bit_length() - d.bit_length()
    if value < Fraction(2) ** exponent:
        exponent -= 1
    shift = 149 if exponent < -126 else 23 - exponent
    significand = rne_integer(n << shift, d) if shift >= 0 else rne_integer(n, d << -shift)
    if exponent < -126:
        return significand  # Includes rounding into the smallest normal.
    if significand == 1 << 24:
        exponent += 1
        significand >>= 1
    return ((exponent + 127) << 23) | (significand - (1 << 23))


def decimal_reference(raw, precision):
    x = exact_word(raw)
    with localcontext() as context:
        context.prec = precision
        result = (Decimal(x.numerator) / Decimal(x.denominator)).exp()
    return positive_fraction_to_fp32(Fraction(result))


class RangeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Missing input is an error, not a skip or an implicit compilation.
        cls.library = Path(os.environ['GDN_VECTOR16_R2_LIBRARY']).resolve(strict=True)

    def scalar(self, enabled=True):
        scalar = DecayScalar(enable_ieee_exp=enabled)
        client = object()
        self.assertTrue(scalar.acquire(client))
        return scalar, client

    def vector(self, **kwargs):
        return Vector16(self.library, arithmetic_backend=FINITE_MUL_UF_BACKEND, **kwargs)

    def test_integer_rounder_ties_and_normal_carry(self):
        self.assertEqual(positive_fraction_to_fp32(Fraction(2) ** -150), 0)
        self.assertEqual(positive_fraction_to_fp32(3 * Fraction(2) ** -150), 2)
        self.assertEqual(positive_fraction_to_fp32(Fraction(2) ** -126 - Fraction(2) ** -150), 0x00800000)
        self.assertEqual(positive_fraction_to_fp32(Fraction(1)), 0x3f800000)

    def test_directed_decimal_diagnostics_without_acceptance_threshold(self):
        centers = (0xc2a00000, 0xc2aeac50, 0xc2cff1b4, 0xc2d00000)
        inputs = [0, 0x80000000, 0x80000001] + [x + delta for x in centers for delta in (-1, 0, 1)]
        scalar, client = self.scalar()
        records = []
        for raw in inputs:
            reference = decimal_reference(raw, 100)
            self.assertEqual(reference, decimal_reference(raw, 180), 'reference precision stability')
            candidate = scalar.op(client, OPERATION, raw)
            legacy = scalar.op(client, 'exp_negative', raw)
            records.append(dict(input=f'{raw:08x}', decimal_reference=f'{reference:08x}',
                                candidate=f'{candidate:08x}', legacy=f'{legacy:08x}',
                                ulp_distance=abs(candidate-reference),
                                candidate_zero_when_reference_positive=candidate == 0 < reference,
                                passed=None, thresholds=None))
        at80 = next(r for r in records if r['input'] == 'c2a00000')
        self.assertGreaterEqual(int(at80['decimal_reference'], 16), 0x00800000)
        self.assertEqual(at80['legacy'], '00000000')
        print('EXP_RANGE_DIAGNOSTICS ' + json.dumps(dict(
            scope='DIRECTED_DECIMAL_REFERENCE_NOT_OFFICIAL_TORCH_NOT_FULLBLOCK',
            oracle='Decimal.exp at 100/180 digits plus exact integer FP32 RNE',
            global_correct_rounding_claim=False, numerical_acceptance=None,
            precision_stability_is_not_interval_proof=True, cases=records), sort_keys=True))

    def test_existing_layout_enable_and_exception_policy_guards(self):
        scalar, client = self.scalar()
        ieee = self.vector(exception_policy=IEEE_POLICY)
        legacy = self.vector()
        self.assertEqual(legacy.fatal_mask, 30)
        self.assertEqual(ieee.fatal_mask, 28)
        ep.validate_policy(ep.IEEE_EXP, GROUPED_35B, scalar, ieee)
        for layout, s, v in ((EQUAL_HEADS, scalar, ieee),
                             (GROUPED_35B, scalar, legacy),
                             (GROUPED_35B, self.scalar(False)[0], ieee)):
            with self.assertRaises(ValueError):
                ep.validate_policy(ep.IEEE_EXP, layout, s, v)
        self.assertEqual(scalar.op(client, 'exp_negative', 0xc2a00000), 0)
        disabled, owner = self.scalar(False)
        with self.assertRaises(ArithmeticFault):
            disabled.op(owner, OPERATION, 0xc2a00000)

    def test_r2_real_underflow_still_rejected_by_default30(self):
        # Exact half-minsub tie rounds to zero and necessarily raises UF|NX.
        for policy in (None, IEEE_POLICY):
            vector = self.vector(**({} if policy is None else {'exception_policy': policy}))
            owner = object()
            self.assertTrue(vector.acquire(owner))
            if policy is None:
                with self.assertRaises(VectorArithmeticFault) as caught:
                    vector.op(owner, 'mul', [1], [0x3f000000])
                self.assertEqual(caught.exception.diagnostic['exception_flags'], 3)
                self.assertEqual(caught.exception.diagnostic['result_words'][0], 0)
            else:
                self.assertEqual(vector.op(owner, 'mul', [1], [0x3f000000]), [0])
                self.assertEqual(vector.flags[3], 1)
            vector.release(owner)


if __name__ == '__main__':
    unittest.main()
