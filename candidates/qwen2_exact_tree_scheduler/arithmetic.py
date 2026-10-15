"""Integer IEEE binary32 RNE arithmetic; finite inputs/intermediates only.

No FP64 accumulator, host multiply/add, BF16 re-rounding, or tolerance compare.
This checks one scalar output at a time; 4096 cells share the same graph.
"""
from .model import program, require


def decode(bits):
    require(type(bits) is int and 0 <= bits <= 0xffffffff, 'binary32 word')
    exponent, fraction = (bits >> 23) & 255, bits & 0x7fffff
    require(exponent != 255, 'nonfinite input/intermediate outside accepted domain')
    magnitude = fraction if exponent == 0 else fraction | 0x800000
    power = -149 if exponent == 0 else exponent - 150
    return (-magnitude if bits >> 31 else magnitude), power


def round_rne(integer, power, negative_zero=False):
    if integer == 0:
        return 0x80000000 if negative_zero else 0
    sign, n = (0x80000000 if integer < 0 else 0), abs(integer)
    exponent = n.bit_length() - 1 + power
    quantum = max(exponent - 23, -149)
    shift = quantum - power
    if shift > 0:
        q, rem = divmod(n, 1 << shift)
        half = 1 << (shift - 1)
        q += rem > half or (rem == half and q & 1)
    else:
        q = n << -shift
    if not q:
        return sign
    if q >= 1 << 24:
        q >>= 1; quantum += 1
    exponent = q.bit_length() - 1 + quantum
    require(exponent <= 127, 'nonfinite result outside accepted domain')
    if exponent < -126:
        return sign | q
    return sign | ((exponent + 127) << 23) | (q & 0x7fffff)


def add(a, b):
    x, ex = decode(a); y, ey = decode(b); common = min(ex, ey)
    return round_rne((x << (ex - common)) + (y << (ey - common)), common,
                     a == b == 0x80000000)


def fma(a, b, c):
    x, ex = decode(a); y, ey = decode(b); z, ez = decode(c)
    common = min(ex + ey, ez)
    total = (x * y << (ex + ey - common)) + (z << (ez - common))
    negative_zero = (x == 0 or y == 0) and z == 0 and bool((a ^ b) >> 31) and bool(c >> 31)
    return round_rne(total, common, negative_zero)


def original_reduce(partials):
    require(len(partials) == 64, '64 original partials required')
    s = [list(partials[8 * r:8 * r + 8]) for r in range(8)]
    for offset in (4, 2, 1):
        for r in range(offset):
            for lane in range(8):
                s[r][lane] = add(s[r][lane], s[r + offset][lane])
    for offset in (4, 2, 1):
        for lane in range(offset):
            s[0][lane] = add(s[0][lane], s[0][lane + offset])
    return add(s[0][0], 0)


def execute(*, partials=None, a=None, b=None):
    """Five words plus two stored words per scalar; plan uses actual contexts.

    partials is a reduction-only diagnostic, never a claim that leaf FMAs ran.
    a/b mode uses every k=64*t+p, t=0..23, and checks BF16 input encodings.
    """
    require((partials is not None) != (a is not None or b is not None), 'select one numeric mode')
    if partials is not None:
        require(len(partials) == 64, '64 partials required')
    else:
        require(a is not None and b is not None and len(a) == len(b) == 1536, 'K1536 input pair')
        require(all((x & 0xffff) == 0 for x in a + b), 'native BF16-encoded binary32 inputs')
    contexts, slots = [None] * 5, [None] * 2
    for op in program():
        if op.kind == 'fma':
            if partials is not None:
                if op.t == 23:
                    contexts[op.dst] = partials[op.p]
            else:
                k = 64 * op.t + op.p
                contexts[op.dst] = fma(a[k], b[k], 0 if op.t == 0 else contexts[op.dst])
        elif op.kind == 'add':
            contexts[op.dst] = add(contexts[op.dst], contexts[op.rhs])
            contexts[op.rhs] = None
        elif op.kind == 'spill':
            slots[op.slot] = contexts[op.dst]; contexts[op.dst] = None
        elif op.kind == 'restore':
            contexts[op.dst] = slots[op.slot]
        elif op.kind == 'zero':
            contexts[op.dst] = add(contexts[op.dst], 0)
        elif op.kind == 'output':
            return contexts[op.dst]
    raise AssertionError('missing raw output')
