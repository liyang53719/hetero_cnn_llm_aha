"""Source-order GDN scalar arithmetic; no claim of Chisel/RTL execution.

Prepared inputs are FP32 Q (already normalized/scaled), K, V, beta, log-decay.
The default production kernel requires M128/chunk64/K128/V128 for one head.
The separately named chunk_once function also supports small arithmetic tests.
"""
import hashlib
import math
import struct
from decimal import Decimal, localcontext
from functools import lru_cache

_F = struct.Struct('<f')
_U = struct.Struct('<I')

def f32(x):
    return _F.unpack(_F.pack(x))[0]

def bits(x):
    return _U.unpack(_F.pack(x))[0]

def word(x):
    return _F.unpack(_U.pack(x))[0]

def add(a, b):
    return f32(a + b)

def mul(a, b):
    return f32(a * b)

def sub(a, b):
    return add(a, -b)

def bf16_bits(x):
    u = bits(x)
    if (u & 0x7f800000) == 0x7f800000:
        return (u >> 16) | (0x40 if u & 0x7fffff else 0)
    return ((u + 0x7fff + ((u >> 16) & 1)) >> 16) & 0xffff

def bf16(x):
    return word(bf16_bits(x) << 16)

# F32.lit rounds these Scala/Java Double literals once. The coefficient bits
# are also independently checked using 100-digit Decimal ln(2) in test_core.
EXP_COEFF = tuple(f32((-math.log(2.0)) ** i / math.factorial(i)) for i in range(8))
LOG2E = word(0x3fb8aa3b)
LN2_HI = word(0x3f317200)
LN2_LO = word(0x35bfbe8e)

@lru_cache(maxsize=16384)
def exp_negative(x, policy):
    """BlockScalarFloatPolicyV2 ExpNegative data path, policies 0 and 1.

    Finite nonpositive input only. No libm exponential is used. Exponent
    reduction, Horner products/adds, and scale operations round separately.
    Flags/transport are not simulated. Tests stay in the legal finite domain.
    """
    assert math.isfinite(x) and x <= 0 and policy in (0, 1)
    a = abs(x)
    if a >= (80.0 if policy == 0 else 104.0):
        return 0.0
    scaled = mul(a, LOG2E)
    k = math.trunc(scaled) if policy == 0 else round(scaled)
    if policy == 0:
        frac = sub(scaled, float(k))
    else:
        reduced = sub(a, mul(float(k), LN2_HI))
        reduced = sub(reduced, mul(float(k), LN2_LO))
        frac = mul(reduced, LOG2E)
    h = EXP_COEFF[7]
    for i in range(6, -1, -1):
        h = add(mul(h, frac), EXP_COEFF[i])
    if policy == 1 and k > 126:
        return mul(mul(h, word((253-k) << 23)), word(0x00800000))
    return mul(h, word((127-k) << 23))

@lru_cache(maxsize=16384)
def decimal_exp_negative(x, policy):
    """Explicit diagnostic replacement, NOT the hardware exp oracle.

    100-digit Decimal exp plus exact integer RNE, avoiding Double conversion.
    Policy is intentionally unused: this reports source approximation error.
    """
    from rational_oracle import round_fraction
    from fractions import Fraction
    with localcontext() as context:
        context.prec = 100
        e = Decimal.from_float(x).exp()
    return word(round_fraction(Fraction(e)))

def two_sum(a, b):
    s = add(a, b)
    bp = sub(s, a)
    ap = sub(s, bp)
    br = sub(b, bp)
    ar = sub(a, ap)
    return s, add(ar, br)

def cumulative(g, policy):
    assert policy in (0, 1)
    hi = lo = 0.0
    out = []
    exponents = []
    for x in g:
        assert math.isfinite(x) and x <= 0
        if policy == 0:
            hi = add(hi, x)
            out.append(hi)
        else:
            u = bits(x)
            if u & 0x7fffffff:
                exponent = (u >> 23) & 255
                assert 1 <= exponent <= 247
                exponents.append(exponent)
                assert max(exponents)-min(exponents) <= 18
            high, residual = two_sum(hi, x)
            lo, discarded = two_sum(lo, residual)
            assert discarded == 0.0, 'guarded cumulative residual is not zero'
            hi = high
            out.append(add(hi, lo))
    return out

def transpose(a):
    return [list(row) for row in zip(*a)]

def dot(a, b):
    total = 0.0
    for k in range(len(a)):
        total = add(total, mul(a[k], b[k]))
    return total

def matmul(a, b):
    bt = transpose(b)
    return [[dot(row, col) for col in bt] for row in a]

def pointwise(a, b, operation):
    return [[operation(x, y) for x, y in zip(ar, br)] for ar, br in zip(a, b)]

def scale_rows(a, b):
    return [[mul(x, b[r]) for x in row] for r, row in enumerate(a)]

def lower_solve(u, rhs):
    """Ascending j products/adds from +0 then ONE rhs-minus-total.

    Stored diagonal is ignored. Not in-place repeated rhs subtraction and not
    forming a rounded inverse followed by GEMM.
    """
    out = []
    for r, row in enumerate(rhs):
        values = []
        for c, value in enumerate(row):
            total = 0.0
            for j in range(r):
                total = add(total, mul(u[r][j], out[j][c]))
            values.append(sub(value, total))
        out.append(values)
    return out

def matrix_sha(matrix, dtype='fp32'):
    h = hashlib.sha256()
    for row in matrix:
        for value in row:
            h.update(_F.pack(value) if dtype == 'fp32' else struct.pack('<H', bf16_bits(value)))
    return h.hexdigest()

def chunk_once(q, k, v, g, beta, initial, policy, exponential=exp_negative):
    """Phases1-17 for one chunk; input Q already includes normalization/scale."""
    n = len(q)
    assert n == len(k) == len(v) == len(g) == len(beta)
    assert all(0 <= b <= 1 for b in beta)
    cum = cumulative(g, policy)
    expg = [exponential(x, policy) for x in cum]
    remain = [exponential(sub(cum[-1], x), policy) for x in cum]
    decay = exponential(cum[-1], policy)
    kb = scale_rows(k, beta)
    vb = scale_rows(v, beta)
    kbg = scale_rows(kb, expg)
    qg = scale_rows(q, expg)
    ke = scale_rows(k, remain)
    pair = [[exponential(sub(cum[i], cum[j]), policy) if j <= i else 0.0
             for j in range(n)] for i in range(n)]
    ut = pointwise(matmul(kb, transpose(k)), pair, mul)
    intra = pointwise(matmul(q, transpose(k)), pair, mul)
    solvev = lower_solve(ut, vb)
    solvek = lower_solve(ut, kbg)
    pred = matmul(solvek, initial)
    vnew = pointwise(solvev, pred, sub)
    inter = matmul(qg, initial)
    local = matmul(intra, vnew)
    out = pointwise(inter, local, add)
    update = matmul(transpose(ke), vnew)
    decayed = [[mul(x, decay) for x in row] for row in initial]
    state = pointwise(decayed, update, add)
    phase_matrices = dict(gates=[cum], kb=kb, vb=vb, kbg=kbg, qg=qg, ke=ke,
                          pair=pair, ut=ut, intra=intra, solvev=solvev,
                          solvek=solvek, pred=pred, vnew=vnew, inter=inter,
                          local=local, out=out, state_update=update,
                          decay_state=decayed, next_state=state)
    trace = {name: matrix_sha(matrix) for name, matrix in phase_matrices.items()}
    trace['output_bf16'] = matrix_sha(out, 'bf16')
    trace['decay_bits'] = f'{bits(decay):08x}'
    return [[bf16(x) for x in row] for row in out], state, trace

def production_one_head(q, k, v, g, beta, initial, policy, exponential=exp_negative):
    assert len(q) == len(k) == len(v) == len(g) == len(beta) == 128
    assert len(initial) == 128
    assert all(len(r) == 128 for matrix in (q, k, v, initial) for r in matrix)
    state = [row[:] for row in initial]
    out, traces = [], []
    for start in (0, 64):
        y, state, trace = chunk_once(q[start:start+64], k[start:start+64], v[start:start+64],
                                    g[start:start+64], beta[start:start+64], state,
                                    policy, exponential)
        out.extend(y)
        traces.append(trace)
    return out, state, traces

def fixture():
    q, k, v, g, beta = [], [], [], [], []
    for t in range(128):
        qr, kr = [0.0]*128, [0.0]*128
        # The four active coordinates cross 16/32-lane boundaries.
        coords = (0, 17, 63, 127)
        qr[coords[t % 4]] = f32((3 + t % 5)/64)
        qr[coords[(t+1) % 4]] = f32(-(1 + t % 3)/128)
        kr[coords[t % 4]] = f32((5 + t % 7)/32)
        kr[coords[(t+2) % 4]] = f32((1 + t % 5)/64)
        q.append(qr); k.append(kr)
        v.append([f32(((t*7 + d*3) % 41 - 20)/128) for d in range(128)])
        beta.append(f32((7 + t % 9)/32))
        g.append(f32(-(11+t % 5)/2**25 if t % 7 == 0 else -(17+t % 13)/1024))
    initial = [[f32(((d*13+c*7) % 43 - 21)/4096) for c in range(128)] for d in range(128)]
    return q, k, v, g, beta, initial

def difference(a, b):
    pairs = [(r, c, x, b[r][c]) for r, row in enumerate(a) for c, x in enumerate(row)]
    neq = [(r,c,x,y) for r,c,x,y in pairs if bits(x) != bits(y)]
    return dict(elements=len(pairs), bit_mismatches=len(neq),
                numeric_mismatches=sum(x != y for _,_,x,y in pairs),
                max_abs=max(abs(x-y) for _,_,x,y in pairs),
                first=[dict(row=r, col=c, a=f'{bits(x):08x}', b=f'{bits(y):08x}')
                       for r,c,x,y in neq[:8]])
