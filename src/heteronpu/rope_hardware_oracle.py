"""Bit-exact finite-domain oracle for the existing HardFloat RoPE pair RTL.

Integer dyadics round EACH of the four multiplications and two additions to
FP32 RNE. No host BLAS, transcendental evaluation, FMA or ideal FP64 pair is
substituted. This conditional component oracle does not define a block graph.
NaN/infinity inputs and any intermediate overflow are deliberately rejected.
"""
from __future__ import annotations

from .model_geometry import require

SIGN = 0x80000000


def _decode(word: int):
    require(type(word) is int and 0 <= word <= 0xFFFFFFFF, "expected uint32 bit word")
    exponent, fraction = (word >> 23) & 255, word & 0x7FFFFF
    require(exponent != 255, "nonfinite FP32 outside finite oracle scope")
    return word >> 31, fraction | (0x800000 if exponent else 0), (exponent - 150 if exponent else -149)


def _round(sign: int, magnitude: int, exponent: int):
    if not magnitude:
        return sign << 31, 0
    top = magnitude.bit_length() - 1 + exponent
    quantum = max(top - 23, -149)
    shift = quantum - exponent
    remainder = 0
    if shift > 0:
        rounded, remainder = divmod(magnitude, 1 << shift)
        half = 1 << (shift - 1)
        rounded += remainder > half or (remainder == half and (rounded & 1))
    else:
        rounded = magnitude << -shift
    if rounded >= 1 << 24:
        rounded >>= 1
        quantum += 1
    require(quantum <= 104, "intermediate FP32 overflow outside oracle scope")
    normal = rounded >= 1 << 23
    exponent_bits = quantum + 150 if normal else 0
    require(exponent_bits < 255, "intermediate FP32 overflow outside oracle scope")
    word = (sign << 31) | (exponent_bits << 23) | (rounded & 0x7FFFFF)
    # HardFloat after-round tininess uses p=24 precision with an UNBOUNDED
    # exponent, before clamping to the subnormal grid. A rounded encoding of
    # min-normal can still have underflow: 00800000 * 3f7fffff -> 00800000,03.
    unbounded_shift = magnitude.bit_length() - 24
    if unbounded_shift > 0:
        ub, rem = divmod(magnitude, 1 << unbounded_shift)
        half = 1 << (unbounded_shift - 1)
        ub += rem > half or (rem == half and (ub & 1))
    else:
        ub = magnitude << -unbounded_shift
    tiny = exponent + unbounded_shift + ub.bit_length() - 1 < -126
    # HardFloat: [invalid, infinite, overflow, underflow, inexact].
    flags = (1 if remainder else 0) | (2 if remainder and tiny else 0)
    return word, flags


def mul_rne(a: int, b: int):
    sa, ma, ea = _decode(a)
    sb, mb, eb = _decode(b)
    return _round(sa ^ sb, ma * mb, ea + eb)


def add_rne(a: int, b: int):
    sa, ma, ea = _decode(a)
    sb, mb, eb = _decode(b)
    exponent = min(ea, eb)
    total = (-1 if sa else 1) * (ma << (ea-exponent)) + (-1 if sb else 1) * (mb << (eb-exponent))
    # RNE cancellation yields +0; only two negative zeros preserve -0.
    sign = int(total < 0) if total else sa & sb
    return _round(sign, abs(total), exponent)


def pair_rne(even: int, odd: int, cos: int, sin: int):
    ec, f0 = mul_rne(even, cos)
    os, f1 = mul_rne(odd, sin)
    es, f2 = mul_rne(even, sin)
    oc, f3 = mul_rne(odd, cos)
    er, f4 = add_rne(ec, os ^ SIGN)
    out_odd, f5 = add_rne(es, oc)
    return er, out_odd, f0 | f1 | f2 | f3 | f4 | f5


def bf16_rne_word(word: int):
    """Software-only terminal projection; the tested RoPE RTL ports are FP32."""
    _decode(word)
    result = ((word + 0x7FFF + ((word >> 16) & 1)) >> 16) & 0xFFFF
    require(result & 0x7F80 != 0x7F80, "BF16 overflow outside oracle scope")
    return result << 16


def native_bf16_pair(even: int, odd: int, cos: int, sin: int):
    """Source-native two rounded BF16 products, diagnostic only."""
    for word in (even, odd, cos, sin):
        _decode(word)
        require(word & 0xFFFF == 0, "native BF16 pair requires BF16 operands")
    ec = bf16_rne_word(mul_rne(even, cos)[0])
    os = bf16_rne_word(mul_rne(odd ^ SIGN, sin)[0])
    es = bf16_rne_word(mul_rne(even, sin)[0])
    oc = bf16_rne_word(mul_rne(odd, cos)[0])
    return bf16_rne_word(add_rne(ec, os)[0]), bf16_rne_word(add_rne(es, oc)[0])
