"""Experimental software-only RoPE product-rounding policies, never production.

Each trace retains four FP32 products/flags, selected products, two FP32
sums/flags, and the software terminal BF16 projection. Flags describe FP32
operations only; BF16 conversion exceptions have no hardware policy here.
"""
from __future__ import annotations

import numpy as np

from .model_geometry import require
from .qwen35_bf16_reference import producer_compare
from .rope_hardware_oracle import SIGN, mul_rne, add_rne, bf16_rne_word

VARIANTS = ('fp32_all', 'cos_bf16_only', 'sin_bf16_only', 'both_bf16')
COLUMNS = ('ec_fp32', 'os_fp32', 'es_fp32', 'oc_fp32',
           'ec_flags', 'os_flags', 'es_flags', 'oc_flags',
           'ec_selected', 'os_selected', 'es_selected', 'oc_selected',
           'even_sum_fp32', 'odd_sum_fp32', 'even_sum_flags', 'odd_sum_flags',
           'even_bf16', 'odd_bf16')


def trace_pair(even: int, odd: int, cos: int, sin: int, variant: str):
    require(variant in VARIANTS, 'unknown experimental rounding variant')
    operations = [mul_rne(even, cos), mul_rne(odd, sin),
                  mul_rne(even, sin), mul_rne(odd, cos)]
    raw = [x[0] for x in operations]
    selected = raw.copy()
    indices = {'fp32_all': (), 'cos_bf16_only': (0, 3),
               'sin_bf16_only': (1, 2), 'both_bf16': (0, 1, 2, 3)}[variant]
    for index in indices:
        selected[index] = bf16_rne_word(raw[index])
    sums = (add_rne(selected[0], selected[1] ^ SIGN),
            add_rne(selected[2], selected[3]))
    return (*raw, *(x[1] for x in operations), *selected,
            *(x[0] for x in sums), *(x[1] for x in sums),
            *(bf16_rne_word(x[0]) for x in sums))


def compare_words(actual, expected, *, bf16: bool):
    """Ordered representable-value distance, with signed zeros coalesced.

    ULP here means intervening representable FP32/BF16 bins, not error divided
    by one fixed spacing. Abs metrics retain the unchanged operator limits.
    """
    a, b = np.asarray(actual), np.asarray(expected)
    require(a.dtype == b.dtype == np.uint32 and a.shape == b.shape, 'word shape/dtype mismatch')
    require(a.size > 0, 'empty word comparison')
    if bf16:
        require(not np.any((a | b) & 0xFFFF), 'BF16 comparison contains FP32 bits')
    af, bf = a.view(np.float32), b.view(np.float32)
    result = producer_compare(af, bf)
    error = np.abs(af.astype(np.float64) - bf.astype(np.float64))
    def ordered(words):
        magnitude = (words & 0x7FFFFFFF).astype(np.int64)
        if bf16: magnitude >>= 16
        return np.where(words & SIGN, -magnitude, magnitude)
    distance = np.abs(ordered(a) - ordered(b))
    result.update({'ulp_definition': 'ordered_BF16_bins_signed_zero_coalesced' if bf16 else 'ordered_FP32_bins_signed_zero_coalesced',
                   'max_ulp': int(distance.max()), 'mean_ulp': float(distance.mean()),
                   'ulp_histogram': {label: int(np.count_nonzero((distance >= low) & (distance <= high))) for label,low,high in (('0',0,0),('1',1,1),('2_to_4',2,4),('5_to_16',5,16),('17_to_256',17,256),('257_to_65536',257,65536),('over_65536',65537,2**32))},
                   'ulp_quantiles': {str(q): float(np.quantile(distance,q)) for q in (0.5,0.9,0.99,1)},
                   'abs_error_quantiles': {str(q): float(np.quantile(error, q)) for q in (0.5, 0.9, 0.99, 1)},
                   'signed_zero_only_differences': int(np.count_nonzero((a != b) & (af == bf))),
                   'actual_above_expected': int(np.count_nonzero(af > bf)),
                   'actual_below_expected': int(np.count_nonzero(af < bf))})
    return result
