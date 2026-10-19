"""Small, pure-integer oracle. No full-matrix execution or numerical imports."""
from fractions import Fraction


class Rejected(ValueError):
    pass


def require(ok, code):
    if not ok:
        raise Rejected(code)


def decode(bits, width=32):
    require(width in (16, 32, 64), 'FORMAT')
    frac, ebits, bias = {16: (7, 8, 127), 32: (23, 8, 127), 64: (52, 11, 1023)}[width]
    require(type(bits) is int and 0 <= bits < (1 << width), 'BITS')
    exp = (bits >> frac) & ((1 << ebits) - 1)
    require(exp != (1 << ebits) - 1, 'NONFINITE')
    significand = bits & ((1 << frac) - 1)
    if exp:
        significand |= 1 << frac
    power = (exp if exp else 1) - bias - frac
    value = Fraction(significand << max(power, 0), 1 << max(-power, 0))
    return -value if bits >> (width - 1) else value


def _round_ratio(n, d):
    q, r = divmod(n, d)
    return q + (2 * r > d or (2 * r == d and q % 2 == 1))


def encode(value, width=32, zero_sign=0):
    """Exact round-to-nearest, ties-to-even; finite overflow is rejected."""
    require(width in (16, 32, 64), 'FORMAT')
    frac, ebits, bias = {16: (7, 8, 127), 32: (23, 8, 127), 64: (52, 11, 1023)}[width]
    value = Fraction(value)
    if value == 0:
        return int(bool(zero_sign)) << (width - 1)
    sign = int(value < 0)
    n, d = abs(value.numerator), value.denominator
    e = n.bit_length() - d.bit_length()
    if (n < d << e) if e >= 0 else (n << -e < d):
        e -= 1
    emin, emax = 1 - bias, bias
    step = max(e, emin) - frac
    q = _round_ratio(n, d << step) if step >= 0 else _round_ratio(n << -step, d)
    if q == 1 << (frac + 1):
        q >>= 1
        e += 1
    require(e <= emax, 'OVERFLOW')
    exp = max(e + bias, 1) if q >= 1 << frac else 0
    return (sign << (width - 1)) | (exp << frac) | (q & ((1 << frac) - 1))


def add32(a, b):
    value = decode(a) + decode(b)
    return encode(value, zero_sign=(a == b == 0x80000000))


def mul32(a, b):
    return encode(decode(a) * decode(b), zero_sign=(a ^ b) >> 31)


def fma32(a, b, c):
    value = decode(a) * decode(b) + decode(c)
    # RN cancellation has +0; two negative zero terms retain -0.
    product_negative = bool((a ^ b) >> 31)
    negative_zero = decode(a) * decode(b) == 0 and c == 0x80000000 and product_negative
    return encode(value, zero_sign=negative_zero)


def math_dot(a, b):
    require(len(a) == len(b) and 0 < len(a) <= 1536, 'DOT_SHAPE')
    return sum((decode(x) * decode(y) for x, y in zip(a, b)), Fraction())


def typed_dot(a, b, blocks=(1024, 512), high_first=True, fused=True):
    """Oracle only; parameters expose deliberately wrong micro-models to tests."""
    require(len(a) == len(b) == sum(blocks), 'DOT_SHAPE')
    require(all(type(n) is int and n > 0 and n % 2 == 0 for n in blocks), 'BLOCKS')
    partials, start = [], 0
    for size in blocks:
        acc = 0
        for i in range(size):
            k = start + (i ^ 1 if high_first else i)
            acc = fma32(a[k], b[k], acc) if fused else add32(mul32(a[k], b[k]), acc)
        partials.append(acc)
        start += size
    result = partials[0]
    for p in partials[1:]:
        result = add32(p, result)
    return result


def bf16_product_units(a, b):
    """Signed exact product in units 2^-266; bounded by 522 magnitude bits."""
    value = decode(a, 16) * decode(b, 16) * (1 << 266)
    require(value.denominator == 1, 'NOT_DYADIC')
    return value.numerator


def ulp_distance(a, b):
    decode(a)
    decode(b)
    def ordered(x):
        return 0x80000000 - (x & 0x7fffffff) if x >> 31 else 0x80000000 + x
    return abs(ordered(a) - ordered(b))
