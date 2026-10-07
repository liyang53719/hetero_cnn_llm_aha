#!/usr/bin/env python3
"""Independent BF16 review via nearest-neighbor search over exact dyadic values.

No production/candidate rounding helper is reused by the reference. Every finite
binary32 is represented as an integer number of min-FP32-subnormal units. The
reference searches the complete finite positive BF16 representable-value table;
it does not use a bias-add/mask/shift rounding shortcut. Only the final comparison
imports the candidate. Run from any directory; emits a small JSON review result.
"""
from bisect import bisect_left
from pathlib import Path
import hashlib
import json
import random
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
from heteronpu.rope_bf16_candidate import bf16_convert


def magnitude_units(word):
    exponent, fraction = (word >> 23) & 255, word & 0x7fffff
    return fraction if exponent == 0 else (0x800000 + fraction) << (exponent - 1)


VALUES = [magnitude_units(index << 16) for index in range(0x7f80)]
OVERFLOW_MIDPOINT = VALUES[-1] + (VALUES[-1] - VALUES[-2]) // 2


def nearest_neighbor_reference(word):
    sign = word >> 31
    magnitude_word = word & 0x7fffffff
    if magnitude_word > 0x7f800000:
        return 0x7fc00000, 16 if magnitude_word < 0x7fc00000 else 0
    if magnitude_word == 0x7f800000:
        return word, 0
    exact = magnitude_units(word)
    if exact >= OVERFLOW_MIDPOINT:
        return (sign << 31) | 0x7f800000, 5
    upper = bisect_left(VALUES, exact)
    if upper == len(VALUES):
        selected = upper - 1
    elif VALUES[upper] == exact:
        selected = upper
    else:
        lower = upper - 1
        low_error, high_error = exact - VALUES[lower], VALUES[upper] - exact
        selected = lower if low_error < high_error or (low_error == high_error and not lower & 1) else upper
    inexact = VALUES[selected] != exact
    flags = int(inexact) | (2 if inexact and selected < 128 else 0)
    return ((sign << 15) | selected) << 16, flags


def main():
    count = 0
    digest = hashlib.sha256()
    def check(word):
        nonlocal count
        observed, expected = bf16_convert(word), nearest_neighbor_reference(word)
        if observed != expected:
            raise ValueError((f'{word:08x}', observed, expected))
        digest.update(word.to_bytes(4, 'little'))
        digest.update(expected[0].to_bytes(4, 'little'))
        digest.update(expected[1].to_bytes(1, 'little'))
        count += 1
    for high in range(65536):
        for low in (0, 0x7fff, 0x8000, 0x8001, 0xffff):
            check((high << 16) | low)
    boundary_count = count
    # Exhaust the discarded field around signed zero, subnormal/normal,
    # finite/infinity and signaling/quiet-NaN boundaries, plus odd/even ties.
    high_words = (0x0000,0x0001,0x007f,0x0080,0x3f80,0x3f81,0x7f7f,0x7f80,0x7fbf,0x7fc0,
                  0x8000,0x8001,0x807f,0x8080,0xbf80,0xbf81,0xff7f,0xff80,0xffbf,0xffc0)
    for high in high_words:
        for low in range(65536):
            check((high << 16) | low)
    rng = random.Random(0x20261007)
    for _ in range(65536):
        check(rng.getrandbits(32))
    report = {
      'status':'PASS_INDEPENDENT_EXACT_DYADIC_NEAREST_NEIGHBOR_CONVERTER_REVIEW',
      'total_checks':count, 'all_upper_words_boundary_checks':boundary_count,
      'selected_upper_words_exhaustive_lower_field':list(map(lambda x: f'{x:04x}', high_words)),
      'selected_upper_words_exhaustive_checks':len(high_words)*65536,
      'independent_random_checks':65536, 'mismatches':0,
      'checked_triples_sha256':digest.hexdigest(),
      'reference_implementation':'Exact integer dyadics, complete positive finite BF16 value table, bisect and exact nearest-neighbor distances; canonical NaN and declared flag contract',
      'reference_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
      'candidate_source_sha256':hashlib.sha256((ROOT/'src/heteronpu/rope_bf16_candidate.py').read_bytes()).hexdigest(),
      'RTL_claim':'None from this script alone; cross-check the end-to-end candidate result separately.',
      'PPA_claim':False,
    }
    output = Path(__file__).with_name('independent_converter_review.json')
    output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
