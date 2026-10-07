"""Experimental all-products-BF16 RoPE candidate, separate from production.

The integer oracle accepts every binary32 bit pattern. Each multiply and add
rounds independently to binary32 RNE (no FMA). All four products and both final
sums then undergo a real BF16 conversion, returned in zero-extended binary32
containers. This candidate does not redefine the frozen production contract.

Flags are NV,DZ,OF,UF,NX in bits 4..0. Binary32 uses HardFloat's after-rounding
precision/unbounded-exponent tininess rule. The BF16 converter intentionally
uses destination-encoding tininess: UF iff inexact and the rounded BF16
exponent is zero. These two policies differ at some min-normal boundaries.
"""
from __future__ import annotations

import random

from .model_geometry import require

SIGN = 0x80000000
EXPONENT = 0x7F800000
FRACTION = 0x007FFFFF
QUIET_NAN = 0x7FC00000
NV, DZ, OF, UF, NX = 16, 8, 4, 2, 1

COLUMNS = (
    'ec_fp32', 'os_fp32', 'es_fp32', 'oc_fp32',
    'ec_flags', 'os_flags', 'es_flags', 'oc_flags',
    'ec_bf16', 'os_bf16', 'es_bf16', 'oc_bf16',
    'ec_bf16_flags', 'os_bf16_flags', 'es_bf16_flags', 'oc_bf16_flags',
    'even_sum_fp32', 'odd_sum_fp32', 'even_sum_flags', 'odd_sum_flags',
    'even_bf16', 'odd_bf16', 'even_bf16_flags', 'odd_bf16_flags',
    'aggregate_flags',
)

# Remote real carried-Q: token110/head4/channel50, absolute position238.
NATIVE_WITNESS = (0xBF920000, 0xC1100000, 0x3F800000, 0x3CE10000)


def _validate_word(word: int) -> None:
    require(type(word) is int and 0 <= word <= 0xFFFFFFFF, 'expected uint32 bit word')


def _is_nan(word: int) -> bool:
    return word & EXPONENT == EXPONENT and bool(word & FRACTION)


def _is_snan(word: int) -> bool:
    return _is_nan(word) and not (word & 0x00400000)


def _is_inf(word: int) -> bool:
    return word & ~SIGN == EXPONENT


def _decode_finite(word: int) -> tuple[int, int, int]:
    exponent, fraction = (word >> 23) & 255, word & FRACTION
    return word >> 31, fraction | (0x800000 if exponent else 0), (exponent - 150 if exponent else -149)


def _round_finite(sign: int, magnitude: int, exponent: int) -> tuple[int, int]:
    """Exact integer dyadic -> binary32, including finite overflow.

    This extends the frozen finite oracle's algorithm without changing it.
    The unrestricted-exponent precision rounding below is essential: using
    only the final encoding's exponent would lose HardFloat's UF at the
    00800000 * 3f7fffff midpoint.
    """
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
    if quantum > 104:
        return (sign << 31) | EXPONENT, OF | NX
    normal = rounded >= 1 << 23
    exponent_bits = quantum + 150 if normal else 0
    word = (sign << 31) | (exponent_bits << 23) | (rounded & FRACTION)
    unbounded_shift = magnitude.bit_length() - 24
    if unbounded_shift > 0:
        ub, rem = divmod(magnitude, 1 << unbounded_shift)
        half = 1 << (unbounded_shift - 1)
        ub += rem > half or (rem == half and (ub & 1))
    else:
        ub = magnitude << -unbounded_shift
    tiny = exponent + unbounded_shift + ub.bit_length() - 1 < -126
    flags = (NX if remainder else 0) | (UF if remainder and tiny else 0)
    return word, flags


def mul_rne(a: int, b: int) -> tuple[int, int]:
    """Independent binary32 RNE multiplication with canonical NaN results."""
    _validate_word(a)
    _validate_word(b)
    if _is_nan(a) or _is_nan(b):
        return QUIET_NAN, NV if _is_snan(a) or _is_snan(b) else 0
    if _is_inf(a) or _is_inf(b):
        if not (a & ~SIGN) or not (b & ~SIGN):
            return QUIET_NAN, NV
        return ((a ^ b) & SIGN) | EXPONENT, 0
    sa, ma, ea = _decode_finite(a)
    sb, mb, eb = _decode_finite(b)
    return _round_finite(sa ^ sb, ma * mb, ea + eb)


def add_rne(a: int, b: int) -> tuple[int, int]:
    """Independent binary32 RNE addition, with signed zero and NaNs."""
    _validate_word(a)
    _validate_word(b)
    if _is_nan(a) or _is_nan(b):
        return QUIET_NAN, NV if _is_snan(a) or _is_snan(b) else 0
    if _is_inf(a) or _is_inf(b):
        if _is_inf(a) and _is_inf(b) and (a ^ b) & SIGN:
            return QUIET_NAN, NV
        return a if _is_inf(a) else b, 0
    sa, ma, ea = _decode_finite(a)
    sb, mb, eb = _decode_finite(b)
    exponent = min(ea, eb)
    total = (-1 if sa else 1) * (ma << (ea - exponent)) + (-1 if sb else 1) * (mb << (eb - exponent))
    # Exact RNE cancellation yields +0; two negative zeros preserve -0.
    sign = int(total < 0) if total else sa & sb
    return _round_finite(sign, abs(total), exponent)


def bf16_convert(word: int) -> tuple[int, int]:
    """RNE binary32 -> BF16, returning (BF16 widened to binary32, flags).

    NaNs are always positive canonical quiet NaNs; only signaling NaN sets
    NV. Infinities and signed zero are preserved. UF follows rounded BF16
    destination encoding, deliberately distinct from binary32's rule.
    """
    _validate_word(word)
    if _is_nan(word):
        return QUIET_NAN, NV if _is_snan(word) else 0
    if _is_inf(word):
        return word, 0
    result = ((word + 0x7FFF + ((word >> 16) & 1)) >> 16) << 16
    if result & EXPONENT == EXPONENT:
        return result, OF | NX
    inexact = bool(word & 0xFFFF)
    return result, (NX if inexact else 0) | (UF if inexact and not (result & EXPONENT) else 0)


def pair_trace(even: int, odd: int, cos: int, sin: int) -> tuple[int, ...]:
    """Return the complete 25-word trace defined by :data:`COLUMNS`."""
    products = (mul_rne(even, cos), mul_rne(odd, sin),
                mul_rne(even, sin), mul_rne(odd, cos))
    selected = tuple(bf16_convert(value) for value, _ in products)
    sums = (add_rne(selected[0][0], selected[1][0] ^ SIGN),
            add_rne(selected[2][0], selected[3][0]))
    terminal = tuple(bf16_convert(value) for value, _ in sums)
    aggregate = 0
    for _, flags in (*products, *selected, *sums, *terminal):
        aggregate |= flags
    return (*(value for value, _ in products), *(flags for _, flags in products),
            *(value for value, _ in selected), *(flags for _, flags in selected),
            *(value for value, _ in sums), *(flags for _, flags in sums),
            *(value for value, _ in terminal), *(flags for _, flags in terminal),
            aggregate)


def synthetic_pairs() -> tuple[tuple[int, int, int, int], ...]:
    """Directed and deterministic full-exponent BF16/raw-FP32 stress vectors.

    These are arithmetic-only synthetic probes, never a native-source fidelity
    corpus. The native real-prefix witness remains named and included.
    """
    rows = [
        NATIVE_WITNESS,
        (0x3F800001, 0x3F800000, 0x3F7FFFFE, 0x3F800000),  # no FMA
        (0x00800000, 0, 0x3F7FFFFF, 0),  # HardFloat min-normal midpoint
        (0x00800001, 0, 0x3F7FFFFE, 0),  # after-rounding non-tiny
        (0x7F7F7FFF, 0, 0x3F800000, 0),  # below BF16 overflow
        (0x7F7F8000, 0, 0x3F800000, 0),  # BF16 overflow tie
        (0x7F7FFFFF, 0, 0x40000000, 0),  # FP32 overflow
        (0x7F7F0000, 0x7F7F0000, 0x3F800000, 0xBF800000),  # add overflow
        (0x007F7FFF, 0, 0x3F800000, 0),  # BF16 tiny result
        (0x007F8000, 0, 0x3F800000, 0),  # BF16 min-normal tie, no UF
    ]
    directed = (
        0, SIGN, 1, SIGN | 1, 0x00008000, 0x00008001, 0x00010000,
        0x007F7FFF, 0x007F8000, 0x007FFFFF, 0x00800000, 0x00800001,
        0x3F000000, 0x3F7FFFFF, 0x3F800000, 0x3F800001, 0x3F808000,
        0x3F818000, 0xBF800000, 0x40000000, 0x7F7F0000, 0x7F7F7FFF,
        0x7F7F8000, 0x7F7FFFFF, 0xFF7FFFFF,
        EXPONENT, SIGN | EXPONENT, QUIET_NAN, SIGN | QUIET_NAN,
        0x7FFFFFFF, 0x7F800001, 0xFF800001, 0x7FBFFFFF, 0xFFC00001,
    )
    for a in directed:
        for b in directed:
            # a*b and a+b (after product conversions) each appear directly.
            rows.append((a, b, 0x3F800000, 0x3F800000))
            rows.append((a, b, b, a))
    for e in (0, SIGN):
        for o in (0, SIGN):
            for c in (0x3F800000, 0xBF800000):
                for s in (0, SIGN, 0x3F800000, 0xBF800000):
                    rows.append((e, o, c, s))
    rng = random.Random(0xB16CA11)
    # Explicitly cover every exponent and both signs in each input port.
    for exponent in range(256):
        for sign in range(2):
            for port in range(4):
                row = [0x3F800000, 0xBF800000, 0x3F000000, 0x3E800000]
                row[port] = (sign << 31) | (exponent << 23) | rng.getrandbits(23)
                rows.append(tuple(row))
    rows.extend(tuple(rng.getrandbits(16) << 16 for _ in range(4)) for _ in range(4096))
    rows.extend(tuple(rng.getrandbits(32) for _ in range(4)) for _ in range(4096))
    # Tiny raw operands paired with full-range values, including min subnormal.
    rows.extend((rng.getrandbits(23) | (rng.getrandbits(1) << 31),
                 rng.getrandbits(23) | (rng.getrandbits(1) << 31),
                 rng.getrandbits(32), rng.getrandbits(32)) for _ in range(1024))
    return tuple(rows)


def converter_inputs() -> tuple[int, ...]:
    """Every BF16 high word at exact/below/tie/above/end-bin boundaries.

    Full high-word enumeration covers both signs, zero/subnormal/normal/
    infinity encodings and quiet/signaling NaN transitions. Random low words
    supplement boundary enumeration. Order and seed are fixed for replay.
    """
    rows = [(high << 16) | low for high in range(1 << 16)
            for low in (0, 0x7FFF, 0x8000, 0x8001, 0xFFFF)]
    rng = random.Random(0xBF160C)
    rows.extend(rng.getrandbits(32) for _ in range(4096))
    return tuple(rows)
