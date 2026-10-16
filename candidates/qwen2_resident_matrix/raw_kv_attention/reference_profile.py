"""Independent restricted-fixture Attention oracle; never a candidate service.

Only independent heads, keys, stripe lanes and output columns are vectorized.
QK depth, the sixteen-stripe fold, softmax summation and PV keys keep the
original order. Every scalar node is a separate binary32 NumPy operation.

This is NOT a general double-based FMA implementation. Runtime bit checks prove
both exact product and exact addition before each double expression. Q/K are
on the 2^-6 grid and bounded by 2^-4, so QK stripe sums are on 2^-12. Actual
normalized BF16 probabilities are checked in [2^-8,1] (grid 2^-15). V is on
2^-3, so PV products and partial sums are on 2^-18, bounded by 128. Their
integer-grid magnitudes need at most 26 bits, below binary64's 53. Signed-zero
and exact cancellation results are checked explicitly. Out-of-domain input is
rejected rather than silently treated as a general numerical reference.

Results are comparison-only. There is no Bus, ScalarService, MatrixService,
CDLL, candidate import, compilation, or candidate-output injection here.
"""
from dataclasses import dataclass
import math
import struct
import numpy as np

MAX_TOKENS = 128
QK_PALETTE = (0x00000000, 0x3c800000, 0xbc800000, 0x3d000000,
              0xbd000000, 0x3d800000, 0xbd800000)
V_PALETTE = (0x00000000, 0x3e000000, 0xbe000000, 0x3e800000,
             0xbe800000, 0x3f000000, 0xbf000000, 0x3f800000, 0xbf800000)
SCALE_WORD = 0x3db504f3


def need(ok, reason):
    if not bool(ok):
        raise ValueError(reason)


def _tokens(tokens):
    need(type(tokens) is int and 1 <= tokens <= MAX_TOKENS, 'reference supports M1..M128 only')


def _word(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def _float(words):
    return np.asarray(words, dtype=np.uint32).view(np.float32)


def _words(values):
    need(np.asarray(values).dtype == np.dtype(np.float32), 'binary32 result required')
    return np.asarray(values).view(np.uint32)


def _bf(values):
    words = _words(values)
    need(np.all((words & 0x7f800000) != 0x7f800000), 'finite BF16 input required')
    # Unsigned RNE, including halfway ties and signed zero.
    rounded = (words.astype(np.uint64) + 0x7fff + ((words >> 16) & 1)) & 0xffff0000
    return rounded.astype(np.uint32).view(np.float32)


def _finite_bf(values):
    words = _words(values)
    need(np.all((words & 0xffff) == 0) and np.all((words & 0x7f800000) != 0x7f800000),
         'exact finite BF16 required')


def _grid(values, exponent, maximum):
    """Decode binary32 bits to signed integers on 2**exponent, without floats."""
    words = _words(values)
    field = ((words >> 23) & 255).astype(np.int64)
    fraction = (words & 0x7fffff).astype(np.int64)
    need(np.all(field != 255), 'finite grid value required')
    need(np.all((field != 0) | (fraction == 0)), 'subnormal outside fixture grid')
    mantissa = np.where(field == 0, 0, fraction | (1 << 23))
    shift = np.where(mantissa == 0, 0, field - 150 - exponent)
    need(np.all((shift >= -23) & (shift <= 29)), 'fixture grid exponent exceeded')
    right = np.maximum(-shift, 0)
    need(np.all((mantissa & ((np.left_shift(np.int64(1), right)) - 1)) == 0),
         'value is not on exact fixture grid')
    magnitude = np.left_shift(np.right_shift(mantissa, right), np.maximum(shift, 0))
    need(np.all(magnitude <= maximum), 'fixture grid magnitude exceeded')
    return np.where((words >> 31) != 0, -magnitude, magnitude)


def _fma_checked(x, y, accumulator, *, kind, step):
    """Single binary32 rounding, only after integer proof of exact binary64 work."""
    need(kind in ('qk', 'pv') and type(step) is int, 'fixture FMA kind/step')
    _finite_bf(x); _finite_bf(y)
    if kind == 'qk':
        need(1 <= step <= 8, 'eight QK depth steps required')
        ix, iy = _grid(x, -6, 4), _grid(y, -6, 4)
        grid, term_bound = -12, 16
    else:
        need(1 <= step <= MAX_TOKENS, 'bounded sequential PV keys required')
        need(np.all((x >= np.float32(1 / 256)) & (x <= np.float32(1))),
             'actual BF16 probability outside proved range')
        ix, iy = _grid(x, -15, 1 << 15), _grid(y, -3, 8)
        grid, term_bound = -18, 1 << 18
    ia = _grid(accumulator, grid, (step - 1) * term_bound)
    # Integer multiplication cannot overflow: the preceding operand bounds
    # make each product at most 2^18 and each partial sum at most 2^25.
    product = ix * iy
    need(np.all(np.abs(product) <= term_bound), 'product bound exceeded')
    need(np.all(np.abs(product) + np.abs(ia) <= (1 << 53) - 1),
         'binary64 exact-add proof failed')
    exact_sum = product + ia
    need(np.all(np.abs(exact_sum) <= step * term_bound), 'sum bound exceeded')
    # Both operations are exact on the checked common grid. This final cast is
    # the only rounding node, matching one binary32 fused multiply-add.
    result = np.add(np.multiply(x.astype(np.float64), y.astype(np.float64)),
                    accumulator.astype(np.float64)).astype(np.float32)
    _grid(result, grid, step * term_bound)
    zero = exact_sum == 0
    negative_zero = ((product == 0) & (ia == 0) &
                     (((_words(x) ^ _words(y)) >> 31) != 0) &
                     ((_words(accumulator) >> 31) != 0))
    expected_zero = np.where(negative_zero, np.uint32(0x80000000), np.uint32(0))
    need(np.all(np.where(zero, _words(result) == expected_zero, True)),
         'signed zero or cancellation changed')
    return result


def _exp_negative(difference):
    """Independent source polynomial; every mul/add separately rounded FP32."""
    magnitude = _float(_words(difference) & np.uint32(0x7fffffff))
    need(np.all(magnitude <= np.float32(1 / 8)), 'score-difference proof exceeded')
    reciprocal = _float(_word(1.0 / math.log(2.0)))
    z = np.multiply(magnitude, reciprocal, dtype=np.float32)
    integer = z.astype(np.int32)  # positive truncation, as in the source recipe
    need(np.all(integer == 0), 'restricted exp exponent proof exceeded')
    fraction = np.add(z, -integer.astype(np.float32), dtype=np.float32)
    coefficients = [_float(_word(math.pow(-math.log(2.0), i) / math.factorial(i)))
                    for i in range(8)]
    result = np.full(z.shape, coefficients[-1], dtype=np.float32)
    for coefficient in reversed(coefficients[:-1]):
        product = np.multiply(result, fraction, dtype=np.float32)
        result = np.add(product, coefficient, dtype=np.float32)
    scale = _float(((127 - integer).astype(np.uint32)) << 23)
    result = np.multiply(result, scale, dtype=np.float32)
    need(np.all(np.isfinite(result)) and np.all((result >= .5) & (result <= 1)),
         'actual exp outside normalization proof')
    return result


def fixture(tokens):
    """Deterministic, exact-BF16, nontrivial small-power Q/K/V word arrays."""
    _tokens(tokens)
    def generate(count, palette, salt):
        index = np.arange(count, dtype=np.uint64)
        mixed = (index + np.uint64(salt)) * np.uint64(0x9e3779b1)
        mixed ^= mixed >> np.uint64(16)
        mixed *= np.uint64(0x85ebca6b)
        mixed ^= mixed >> np.uint64(13)
        result = np.asarray(palette, dtype=np.uint32)[(mixed % len(palette)).astype(np.intp)]
        result.setflags(write=False)
        return result
    return (generate(tokens * 1536, QK_PALETTE, 0x1321),
            generate(tokens * 256, QK_PALETTE, 0x2413),
            generate(tokens * 256, V_PALETTE, 0x3142))


@dataclass(frozen=True)
class ReferenceResult:
    # Each causal tuple entry is [head,key] for one token: no masked/full square.
    dots: tuple
    materialized_dots: tuple
    scores: tuple
    weights: tuple
    prefix_totals: tuple
    normalized_fp32: tuple
    normalized: tuple
    maxima: np.ndarray
    totals: np.ndarray
    inverses: np.ndarray
    pv: np.ndarray
    output: np.ndarray

    @property
    def nbytes(self):
        return sum(a.nbytes for name in ('dots', 'materialized_dots', 'scores', 'weights', 'prefix_totals',
                                         'normalized_fp32', 'normalized') for a in getattr(self, name)) + sum(
            getattr(self, name).nbytes for name in ('maxima', 'totals', 'inverses', 'pv', 'output'))


def reference(tokens, q, k, v):
    """Return comparison-only words in token/head/key or token/head/column order."""
    _tokens(tokens)
    arrays = []
    for source, count, palette in ((q, tokens * 1536, QK_PALETTE),
                                    (k, tokens * 256, QK_PALETTE), (v, tokens * 256, V_PALETTE)):
        need(isinstance(source, np.ndarray) and source.dtype == np.dtype(np.uint32) and
             source.shape == (count,), 'exact flat uint32 fixture shape required')
        need(np.all(np.isin(source, palette)), 'input outside restricted fixture palette')
        arrays.append(source.view(np.float32))
    q, k, v = arrays[0].reshape(tokens, 12, 128), arrays[1].reshape(tokens, 2, 128), arrays[2].reshape(tokens, 2, 128)
    rows = {name: [] for name in ('dots', 'materialized_dots', 'scores', 'weights', 'prefix_totals', 'normalized_fp32', 'normalized')}
    maxima = np.empty((tokens, 12), dtype=np.float32)
    totals = np.empty_like(maxima); inverses = np.empty_like(maxima)
    pv = np.empty((tokens, 12, 128), dtype=np.float32)
    output = np.empty_like(pv)
    heads = np.arange(12) // 6
    for token in range(tokens):
        keys = token + 1
        stripes = np.zeros((12, keys, 16), dtype=np.float32)
        for depth in range(8):
            begin = depth * 16
            x = q[token, :, begin:begin + 16][:, None, :]
            y = k[:keys, heads, begin:begin + 16].transpose(1, 0, 2)
            stripes = _fma_checked(x, y, stripes, kind='qk', step=depth + 1)
        dot = np.zeros((12, keys), dtype=np.float32)
        for lane in range(16):
            dot = np.add(dot, stripes[:, :, lane], dtype=np.float32)
            _grid(dot, -12, (lane + 1) * 128)
        need(np.all(np.abs(dot) <= .5), 'completed QK bound exceeded')
        materialized = _bf(dot)
        scaled = np.multiply(materialized, _float(SCALE_WORD), dtype=np.float32)
        score = _bf(scaled)
        need(np.all(np.abs(score) < np.float32(1 / 16)), 'scaled BF16 score bound exceeded')
        # argmax retains first-key tie behavior of the original reference max.
        maximum = score[np.arange(12), np.argmax(score, axis=1)]
        differences = np.add(score, _float(_words(maximum) ^ np.uint32(0x80000000))[:, None], dtype=np.float32)
        weight = _exp_negative(differences)
        total = np.zeros(12, dtype=np.float32)
        prefix_totals = np.empty_like(weight)
        for key in range(keys):
            total = np.add(total, weight[:, key], dtype=np.float32)
            need(np.all((total >= .5) & (total <= key + 1)), 'sequential normalization bound exceeded')
            prefix_totals[:, key] = total
        inverse = np.divide(np.float32(1), total, dtype=np.float32)
        normalized_fp32 = np.multiply(weight, inverse[:, None], dtype=np.float32)
        normalized = _bf(normalized_fp32)
        _finite_bf(normalized)
        need(np.all((normalized >= np.float32(1 / 256)) & (normalized <= 1)),
             'actual normalized BF16 probability outside proof')
        _grid(normalized, -15, 1 << 15)
        accumulator = np.zeros((12, 128), dtype=np.float32)
        for key in range(keys):
            accumulator = _fma_checked(normalized[:, key, None], v[key, heads, :],
                                       accumulator, kind='pv', step=key + 1)
        for name, value in (('dots', dot), ('materialized_dots', materialized), ('scores', score),
                            ('weights', weight), ('prefix_totals', prefix_totals),
                            ('normalized_fp32', normalized_fp32), ('normalized', normalized)):
            rows[name].append(_words(value))
        maxima[token], totals[token], inverses[token] = maximum, total, inverse
        pv[token], output[token] = accumulator, _bf(accumulator)
    result = ReferenceResult(**{name: tuple(values) for name, values in rows.items()},
        maxima=_words(maxima), totals=_words(totals), inverses=_words(inverses),
        pv=_words(pv), output=_words(output).reshape(-1))
    for values in rows.values():
        for array in values:
            array.setflags(write=False)
    for name in ('maxima', 'totals', 'inverses', 'pv', 'output'):
        getattr(result, name).setflags(write=False)
    need(result.nbytes < 5 * 1024 * 1024, 'reference retention bound exceeded')
    return result
