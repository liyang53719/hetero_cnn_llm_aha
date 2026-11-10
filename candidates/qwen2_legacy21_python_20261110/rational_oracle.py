"""Independent exact rational primitive/recurrence oracle for bounded tests."""
from fractions import Fraction
import struct

def _even(n, d):
    q, r = divmod(n, d)
    return q + (2*r > d or (2*r == d and (q & 1)))

def round_fraction(x):
    """Exact rational -> IEEE binary32 RNE word; canonical +0 on exact zero."""
    x = Fraction(x)
    sign = 0x80000000 if x < 0 else 0
    x = abs(x)
    if not x:
        return sign
    n, d = x.numerator, x.denominator
    e = n.bit_length()-d.bit_length()
    if (n < d << e) if e >= 0 else (n << -e < d):
        e -= 1
    shift = 149 if e < -126 else 23-e
    sig = _even(n << shift, d) if shift >= 0 else _even(n, d << -shift)
    if e < -126:
        return sign | sig
    if sig == 1 << 24:
        sig >>= 1
        e += 1
    if e > 127:
        return sign | 0x7f800000
    return sign | ((e+127) << 23) | (sig-(1 << 23))

def exact_recurrence(q, k, v, beta, initial):
    """Exact GDN recurrence for zero decay, NOT a rounded prefill oracle."""
    q = [[Fraction(x) for x in row] for row in q]
    k = [[Fraction(x) for x in row] for row in k]
    v = [[Fraction(x) for x in row] for row in v]
    state = [[Fraction(x) for x in row] for row in initial]
    ys = []
    for qr, kr, vr, b in zip(q, k, v, beta):
        delta = [(vr[c]-sum(kr[d]*state[d][c] for d in range(len(kr))))*Fraction(b)
                 for c in range(len(vr))]
        state = [[state[d][c]+kr[d]*delta[c] for c in range(len(vr))] for d in range(len(kr))]
        ys.append([sum(qr[d]*state[d][c] for d in range(len(kr))) for c in range(len(vr))])
    return ys, state
