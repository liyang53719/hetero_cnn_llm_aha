"""Independent, finite-input binary32 RNE reference using exact Fractions.

Scope: software mathematics for the proposed strict two-pass numerical
contract, not HardFloat execution, hardware measurements, or old-CPP fatal
equivalence. No BF16 behavior, NaN payload propagation, infinity-input
arithmetic, protocol timing, or resource claim is made here.

Rounding searches adjacent positive finite binary32 encodings and compares
exact rational distances. It does not use Python float, a significand-rounding
implementation, or the companion integer model. The flags are NV=16, DZ=8,
OF=4, UF=2, NX=1. With finite inputs, these operations never generate NV or DZ.

The chosen tininess-after rule first rounds to 24-bit precision with an
unbounded exponent range. For an inexact binary32 delivery, UF therefore uses
the exact-magnitude boundary 2**-126 - 2**-151, not the delivered exponent.
Equality is not tiny because the unbounded-range tie rounds to even minnormal.

mul(), add(), fma(), and round_fraction() return (uint32_bits, flags).
strict() performs separately rounded Mul and Add with fatal mask 30. Its
unexecuted Add fields are zero placeholders when attempted=1 and status=4;
they must not be interpreted as an executed Add result. All three strict
inputs are checked before either pass. Nonfinite inputs raise ValueError,
rather than fabricating an arithmetic flag or an admission-oracle result.

This source was authored without executing, importing, compiling, or testing
it. The neighboring directed table is mathematical derivation, not a run log.
"""

from fractions import Fraction


NV = 16
DZ = 8
OF = 4
UF = 2
NX = 1
FATAL_MASK = NV | DZ | OF | UF

SIGN_MASK = 0x80000000
EXP_MASK = 0x7F800000
FRAC_MASK = 0x007FFFFF
MAX_FINITE = 0x7F7FFFFF
POS_INF = 0x7F800000
NEG_ZERO = 0x80000000

# Halfway between maxfinite and the next value in unbounded-exponent RNE.
OVERFLOW_THRESHOLD = Fraction((1 << 128) - (1 << 103))

# Halfway between minnormal and its predecessor at unbounded-exponent p=24.
TINY_AFTER_THRESHOLD = Fraction(1, 1 << 126) - Fraction(1, 1 << 151)


def decode(u: int) -> Fraction:
    """Decode one finite uint32 binary32 encoding into an exact rational.

    Both signed zeros decode to Fraction(0); callers preserve their signs
    separately. All infinity and NaN encodings, malformed integers, and
    non-integer values are refused.
    """
    if isinstance(u, bool) or not isinstance(u, int) or not 0 <= u <= 0xFFFFFFFF:
        raise ValueError("binary32 input must be an integer in [0, 2**32 - 1]")

    exponent = (u >> 23) & 0xFF
    if exponent == 0xFF:
        raise ValueError("finite-input reference refuses NaN and infinity")

    fraction = u & FRAC_MASK
    if exponent == 0:
        magnitude = Fraction(fraction, 1 << 149)
    else:
        significand = (1 << 23) + fraction
        power = exponent - 150
        if power >= 0:
            magnitude = Fraction(significand * (1 << power))
        else:
            magnitude = Fraction(significand, 1 << -power)

    return -magnitude if u & SIGN_MASK else magnitude


def round_fraction(q: Fraction, zero_sign: int = 0) -> tuple[int, int]:
    """Round an exact rational to binary32, nearest with ties to even.

    Only Fraction or integer input is accepted, so no host floating-point
    conversion can silently enter the oracle. zero_sign is used only when
    q is exactly zero; a nonzero value rounded to zero retains q's sign.
    """
    if isinstance(q, bool) or not isinstance(q, (Fraction, int)):
        raise TypeError("round_fraction requires Fraction or integer input")
    if isinstance(zero_sign, bool) or not isinstance(zero_sign, int) or zero_sign not in (0, 1):
        raise ValueError("zero_sign must be integer 0 or 1")

    q = Fraction(q)
    if q == 0:
        return zero_sign << 31, 0

    sign = 1 if q < 0 else 0
    magnitude = abs(q)
    if magnitude >= OVERFLOW_THRESHOLD:
        return (sign << 31) | POS_INF, OF | NX

    # Positive finite encodings are monotonically ordered by exact value.
    # Find the floor encoding, returning immediately on exact representability.
    left = 0
    right = MAX_FINITE
    lower = 0
    while left <= right:
        middle = (left + right) // 2
        candidate = decode(middle)
        if candidate == magnitude:
            return (sign << 31) | middle, 0
        if candidate < magnitude:
            lower = middle
            left = middle + 1
        else:
            right = middle - 1

    if lower == MAX_FINITE:
        # Above maxfinite but below the overflow midpoint: maxfinite + NX.
        rounded = MAX_FINITE
    else:
        upper = lower + 1
        distance_to_lower = magnitude - decode(lower)
        distance_to_upper = decode(upper) - magnitude
        if distance_to_lower < distance_to_upper:
            rounded = lower
        elif distance_to_upper < distance_to_lower:
            rounded = upper
        else:
            # The encoding LSB is the significand LSB, including zero and
            # exponent transitions. Select the even endpoint of the tie.
            rounded = lower if (lower & 1) == 0 else upper

    flags = NX
    if magnitude < TINY_AFTER_THRESHOLD:
        flags |= UF
    return (sign << 31) | rounded, flags


def mul(a: int, b: int) -> tuple[int, int]:
    """Finite binary32 multiplication, rounded once; zero sign is a xor b."""
    qa = decode(a)
    qb = decode(b)
    zero_sign = ((a ^ b) >> 31) & 1
    return round_fraction(qa * qb, zero_sign=zero_sign)


def add(a: int, b: int) -> tuple[int, int]:
    """Finite binary32 addition, rounded once; exact cancellation is +0."""
    qa = decode(a)
    qb = decode(b)
    zero_sign = 1 if a == NEG_ZERO and b == NEG_ZERO else 0
    return round_fraction(qa + qb, zero_sign=zero_sign)


def fma(a: int, b: int, c: int) -> tuple[int, int]:
    """Exact rational a*b+c with ONE final rounding, for contrast only.

    There is no rounded or classified intermediate product. Opposite-sign
    exact cancellation yields +0 under RNE. An exact zero product plus -0
    yields -0 only when the product's xor sign is also negative.
    """
    qa = decode(a)
    qb = decode(b)
    qc = decode(c)
    product_is_zero = qa == 0 or qb == 0
    product_is_negative = ((a ^ b) & SIGN_MASK) != 0
    zero_sign = 1 if product_is_zero and product_is_negative and c == NEG_ZERO else 0
    return round_fraction(qa * qb + qc, zero_sign=zero_sign)


def strict(a: int, b: int, acc: int) -> dict[str, int]:
    """Separate Mul-RNE then Add-RNE; status 0=OK, 4=MulFatal, 5=AddFatal.

    attempted counts mathematical arithmetic passes, not measured hardware
    cycles or handshakes. NX alone is nonfatal. A fatal Mul is diagnosed but
    prevents Add; a fatal Add is diagnosed but is not a commit result.
    """
    # Admission is all-or-nothing even if Mul would otherwise terminate early.
    decode(a)
    decode(b)
    decode(acc)

    product, mul_flags = mul(a, b)
    result = {
        "product": product,
        "mul_flags": mul_flags,
        "value": 0,
        "add_flags": 0,
        "attempted": 1,
        "status": 4,
    }
    if (mul_flags & FATAL_MASK) or (product & EXP_MASK) == EXP_MASK:
        return result

    value, add_flags = add(product, acc)
    add_fatal = (add_flags & FATAL_MASK) != 0 or (value & EXP_MASK) == EXP_MASK
    result.update(
        value=value,
        add_flags=add_flags,
        attempted=2,
        status=5 if add_fatal else 0,
    )
    return result
