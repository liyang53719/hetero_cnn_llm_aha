"""Exact finite BF16 decoding for materialized prefill tensor comparisons.

This is a comparison domain, not an execution arithmetic or tolerance policy.
The legacy Matrix/Norm/RoPE operand checker intentionally remains normal-only.
Every finite BF16 word is exactly representable as a *normal* binary64 value
apart from signed zero; decoding directly to binary64 avoids a host FP32
subnormal conversion being affected by FTZ/DAZ. No input word is rewritten.
"""
from __future__ import annotations

import hashlib

import numpy as np

DOMAIN = 'finite_bf16_materialized_prefill_v1'


def decode_finite(words):
    """Raw little-endian uint16 BF16 to exact binary64, including signed zero."""
    if not isinstance(words, np.ndarray) or words.dtype != np.dtype('<u2') or not words.size:
        raise ValueError('prefill BF16: nonempty little-endian uint16 words required')
    exponent = ((words >> 7) & 255).astype(np.int32)
    if np.any(exponent == 255):
        raise ValueError('prefill BF16: nonfinite word')
    fraction = (words & 127).astype(np.int32)
    significand = np.where(exponent == 0, fraction, 128 + fraction)
    power = np.where(exponent == 0, -133, exponent - 134)
    magnitude = np.ldexp(significand.astype(np.float64), power)
    return np.copysign(magnitude, np.where(words & 0x8000, -1.0, 1.0))


def compare_finite_bf16(actual, expected):
    """Finite, same-shape byte tensors; return metrics without assigning a gate."""
    if (type(actual) is not bytes or type(expected) is not bytes or not actual or
            len(actual) != len(expected) or len(actual) % 2):
        raise ValueError('prefill BF16: same complete nonempty byte shape required')
    a, b = np.frombuffer(actual, '<u2'), np.frombuffer(expected, '<u2')
    af, bf = decode_finite(a), decode_finite(b)

    def ordered(words):
        value = words.astype(np.int32)
        return np.where(value & 0x8000, 0x8000 - (value & 0x7fff), 0x8000 + value)

    def subnormals(words):
        return int(np.count_nonzero(((words & 0x7f80) == 0) & ((words & 0x7f) != 0)))

    ulp, delta, different = np.abs(ordered(a) - ordered(b)), np.abs(af - bf), a != b
    return dict(comparison_domain=DOMAIN, elements=int(a.size),
        bit_mismatches=int(np.count_nonzero(different)),
        numerical_mismatches=int(np.count_nonzero(ulp)), max_bf16_ulp=int(ulp.max()),
        max_abs=float(delta.max()), mean_abs=float(delta.mean()),
        signed_zero_only_mismatches=int(np.count_nonzero(different & (ulp == 0))),
        first_bit_mismatch=int(np.flatnonzero(different)[0]) if different.any() else None,
        actual_subnormal_count=subnormals(a), native_subnormal_count=subnormals(b),
        actual_sha256=hashlib.sha256(actual).hexdigest(),
        expected_sha256=hashlib.sha256(expected).hexdigest())
