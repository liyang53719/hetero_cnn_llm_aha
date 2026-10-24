"""Independent references for the opt-in native cumulative-decay fixture.

Fraction/integer RNE checks the specified FP32 P7 recipe, not exp accuracy.
NumPy full-plane ascending-K Mul then Add checks stored chunk boundaries.
Decimal.exp is a separate mathematical diagnostic, with no acceptance gate.
Nothing in this file calls a candidate scalar evaluator or writes owner data.
"""
from collections import Counter
from decimal import Decimal, localcontext
from fractions import Fraction
from functools import lru_cache

import numpy as np

from candidates.qwen2_resident_matrix.ffn_public.test_prefix_owners import (
    exact, rn, ref_add, ref_mul)
from candidates.qwen35_gdn_prefill.prep.test_model import reference_exp
from .test_real_chunk_continuation import (
    separate_matmul, sign_flip, unit_lower_solve)


# Specification constants copied as literal FP32 words, never imported from
# the implementation under test. The rational operations round every node.
COEFFICIENTS = (0x3f800000, 0xbf317218, 0x3e75fdf0, 0xbd635847,
                0x3c1d955b, 0xbaaec3ff, 0x39218489, 0xb77fe5fe)
RECIP_LN2, LN2_HI, LN2_LO = 0x3fb8aa3b, 0x3f317200, 0x35bfbe8e


@lru_cache(maxsize=4096)
def p7_reference(raw):
    """Finite nonpositive FP32 -> split-ln2 P7 via exact rational RNE."""
    value = exact(raw)
    if value > 0:
        raise ValueError('nonpositive reference input required')
    magnitude = raw & 0x7fffffff
    if exact(magnitude) >= 104:
        return 0
    scaled = exact(ref_mul(magnitude, RECIP_LN2))
    quotient, remainder = divmod(scaled.numerator, scaled.denominator)
    k = quotient + (2 * remainder > scaled.denominator or
                    (2 * remainder == scaled.denominator and quotient & 1))
    k_word = rn(k)
    reduced = ref_add(magnitude, ref_mul(k_word, LN2_HI) ^ 0x80000000)
    reduced = ref_add(reduced, ref_mul(k_word, LN2_LO) ^ 0x80000000)
    fraction = ref_mul(reduced, RECIP_LN2)
    polynomial = COEFFICIENTS[-1]
    for coefficient in reversed(COEFFICIENTS[:-1]):
        polynomial = ref_add(ref_mul(polynomial, fraction), coefficient)
    if k <= 126:
        return ref_mul(polynomial, (127 - k) << 23)
    return ref_mul(ref_mul(polynomial, (253 - k) << 23), 0x00800000)


def reference_chunk(core, previous, *, exp_word=p7_reference, exp_inputs=None):
    """Independent boundary recipe, never used as an actual operand source.

    Every exp input is derived by Fraction/RNE Add, independent of native
    cumsum/subtraction. Other matrices use separate FP32 Mul/Add NumPy planes.
    """
    gate = core[:, 6144:6160].copy()
    raw = gate.view(np.uint32)
    cumulative = 0
    for row in range(64):
        cumulative = ref_add(cumulative, int(raw[row, 0]))
        raw[row, 0] = cumulative

    def exp(raw_input, role):
        raw_input = int(raw_input)
        if exp_inputs is not None:
            exp_inputs[(role, raw_input)] += 1
        return exp_word(raw_input)

    # Explicit call order/roles mirror the mathematical recipe, not any owner
    # helper: one total, 64 cumulative, 64 remaining, 2080 pairwise inputs.
    decay_word = exp(cumulative, 'chunk_decay')
    exp_g = np.empty(64, np.uint32)
    exp_rem = np.empty(64, np.uint32)
    pair = np.zeros((64, 64), np.uint32)
    for row in range(64):
        cum = int(raw[row, 0])
        exp_g[row] = exp(cum, 'cumulative')
        exp_rem[row] = exp(ref_add(cumulative, cum ^ 0x80000000), 'remaining')
        for col in range(row + 1):
            pair[row, col] = exp(ref_add(cum, int(raw[col, 0]) ^ 0x80000000), 'pairwise')
    exp_g, exp_rem, pair = (a.view(np.float32) for a in (exp_g, exp_rem, pair))
    q, k, v = (core[:, offset:offset + 128].copy() for offset in (0, 2048, 4096))
    with np.errstate(all='ignore'):
        kb = np.multiply(k, gate[:, 1, None], dtype=np.float32)
        ke = np.multiply(k, exp_rem[:, None], dtype=np.float32)
        result = dict(gates=gate, q=q, k=k, v=v, kb=kb,
            vb=np.multiply(v, gate[:, 1, None], dtype=np.float32),
            kbg=np.multiply(kb, exp_g[:, None], dtype=np.float32),
            qg=np.multiply(q, exp_g[:, None], dtype=np.float32), ke=ke,
            kt=k.T.copy(), ket=ke.T.copy(), pair=pair)
        result['ut'] = np.multiply(separate_matmul(kb, k.T), pair, dtype=np.float32)
        result['intra'] = np.multiply(separate_matmul(q, k.T), pair, dtype=np.float32)
        result['solvev'] = unit_lower_solve(result['ut'], result['vb'])
        result['solvek'] = unit_lower_solve(result['ut'], result['kbg'])
        result['pred'] = separate_matmul(result['solvek'], previous)
        result['vnew'] = np.add(result['solvev'], sign_flip(result['pred']), dtype=np.float32)
        result['inter'] = separate_matmul(result['qg'], previous)
        result['local'] = separate_matmul(result['intra'], result['vnew'])
        result['out'] = np.add(result['inter'], result['local'], dtype=np.float32)
        result['state_update'] = separate_matmul(result['ket'], result['vnew'])
        decay = np.asarray(decay_word, np.uint32).view(np.float32)
        result['decay_state'] = np.multiply(previous, decay, dtype=np.float32)
        result['next_state'] = np.add(result['decay_state'], result['state_update'], dtype=np.float32)
    return result


def mathematical_diagnostics(exp_inputs):
    """All distinct derived inputs, Decimal at 100/180 digits, no threshold."""
    by_input = Counter()
    for (_, raw), count in exp_inputs.items():
        by_input[raw] += count
    records = []
    for raw, count in sorted(by_input.items()):
        rounded = []
        value = exact(raw)
        for precision in (100, 180):
            with localcontext() as context:
                context.prec = precision
                mathematical = (Decimal(value.numerator) / Decimal(value.denominator)).exp()
            rounded.append(rn(Fraction(mathematical)))
        at100, at180 = rounded
        if at100 != at180:
            raise AssertionError('Decimal reference precision instability')
        recipe = p7_reference(raw)
        records.append(dict(input_word=f'{raw:08x}', calls=count,
            recipe_word=f'{recipe:08x}', decimal_reference_word=f'{at180:08x}',
            ulp_distance=abs(recipe - at180),
            legacy_counterfactual_word=f'{reference_exp(raw):08x}'))
    return dict(scope='SYNTHETIC_DERIVED_EXP_INPUTS_MATH_DIAGNOSTIC_ONLY',
        calls=sum(by_input.values()), distinct_inputs=len(records),
        oracle='Decimal.exp at 100/180 digits plus exact integer FP32 RNE',
        precision_stability_is_not_interval_proof=True, numerical_acceptance=None,
        thresholds=None, globally_correctly_rounded_claim=False,
        maximum_observed_ulp_distance=max(r['ulp_distance'] for r in records),
        records=records)
