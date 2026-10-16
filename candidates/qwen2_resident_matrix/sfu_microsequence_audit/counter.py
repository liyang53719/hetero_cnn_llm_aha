"""Pinned divider CONTROL recurrence only. No arithmetic or measured RTL timing."""
from fractions import Fraction
import ast
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


class Counter:
    """Exact division-only cycleNum recurrence, sigWidth=24; rising-edge interface.

    tick() reports pre-edge ready/result, then applies the source's register
    update. A result and the next input may share one edge. No wrapper bubble
    is added. quotient_leading_one stands for sigX_Z(25), not a zero-remainder
    test. Data-path correctness is not simulated here.
    """
    def __init__(self, *, two_bits=False):
        if type(two_bits) is not bool:
            raise ValueError('canonical option')
        self.two_bits, self.count, self.leading = two_bits, 0, False

    def tick(self, *, valid=False, normal=True, quotient_leading_one=False):
        if any(type(x) is not bool for x in (valid, normal, quotient_leading_one)):
            raise ValueError('canonical control')
        ready, result = self.count <= 1, self.count == 1
        accepted = ready and valid
        skip = self.count == 3 and self.leading and not self.two_bits
        if accepted:
            self.count = 26 if normal else 1
            self.leading = quotient_leading_one
        elif self.count:
            self.count = 1 if skip else self.count - (2 if self.two_bits and self.count >= 3 else 1)
        return dict(ready=ready, result=result, accepted=accepted, next_count=self.count)


def trace(*, two_bits=False, normal=True, leading=False):
    counter = Counter(two_bits=two_bits)
    observations = []
    for edge in range(30):
        result = counter.tick(valid=True, normal=normal, quotient_leading_one=leading)
        observations.append(dict(edge=edge, **result))
        if edge and result['accepted']:
            return observations
    raise ValueError('counter did not release')


def silu_division_class(denominator):
    """All finite successful 1/(1+exp(-abs(x))) inputs lie in [1,2].

    The numerator is exactly1.0. A normalized denominator significand of1.0
    gives the leading quotient bit. No remainder-based early exit exists.
    """
    if type(denominator) is not int or not 0x3f800000 <= denominator <= 0x40000000:
        raise ValueError('finite SiLU denominator in [1,2] required')
    return dict(normal=True, leading=(denominator & 0x7fffff) == 0)


def f32_fraction(word):
    exponent, significand = (word >> 23) & 255, word & 0x7fffff
    if exponent == 255:
        raise ValueError('finite word required')
    if exponent:
        significand |= 1 << 23
    shift = (exponent - 127 - 23) if exponent else -149
    value = Fraction(significand) * (Fraction(2) ** shift)
    return -value if word >> 31 else value


def rne_fraction(value):
    """Exact rational nearest/even rounding for this small finite interval proof."""
    negative = value < 0
    value = abs(value)
    low, high = 0, 0x7f7fffff
    while low < high:
        middle = (low + high) // 2
        if f32_fraction(middle) < value:
            low = middle + 1
        else:
            high = middle
    upper = f32_fraction(low)
    if not low or upper == value:
        rounded = upper
    else:
        lower = f32_fraction(low - 1)
        dl, du = value - lower, upper - value
        rounded = lower if dl < du or (dl == du and (low - 1) % 2 == 0) else upper
    return -rounded if negative else rounded


def exp_horner_interval():
    """Enclose all fractions in[0,1] through the exact pinned rounded recipe.

    Using independent interval bounds is conservative. Each product by a
    fraction in[0,1] lies between0 and the accumulator bound; RNE is monotone.
    No assumption about actual checkpoint inputs or exp-branch frequency.
    """
    recipe = ROOT/'candidates/qwen2_resident_matrix/ffn_attention/scalar_recipe.py'
    assignment = next(node for node in ast.parse(recipe.read_text()).body
                      if isinstance(node, ast.Assign) and any(
                          isinstance(target, ast.Name) and target.id == 'EXP_COEFFICIENTS'
                          for target in node.targets))
    coefficients = ast.literal_eval(assignment.value)
    low = high = f32_fraction(coefficients[7])
    stages = []
    for index in range(6, -1, -1):
        low, high = rne_fraction(min(0, low)), rne_fraction(max(0, high))
        coefficient = f32_fraction(coefficients[index])
        low, high = rne_fraction(low + coefficient), rne_fraction(high + coefficient)
        stages.append((low, high))
    return tuple(stages)


def bounds():
    vectors, ideal = 71680, 1468464
    shortest = trace(leading=True)[-1]['edge']
    longest = trace(leading=False)[-1]['edge']
    two = trace(two_bits=True)[-1]['edge']
    floor = shortest * vectors
    return dict(scope='SOURCE_COUNTER_NECESSARY_BOUND_NOT_ARITHMETIC_OR_RTL',
        silu_elements=128*8960, silu_vectors=vectors, existing_dividers=16,
        one_bit_normal_min_spacing=shortest, one_bit_normal_max_spacing=longest,
        two_bit_normal_spacing=two, two_bit_option_value=16,
        silu_divider_service_floor=floor,
        ideal_perfect_overlap_utilization_ceiling_percent=float(Fraction(100*ideal, floor)),
        all_26_cycle_vector_case=longest*vectors,
        full_exp_rounded_fp32_alu_nodes=17, full_exp_floor_conversion_states=1,
        full_silu_nondivision_microsequence_states=22,
        full_silu_single_context_no_wrapper_bubbles_min_cycles=47,
        two_bit_divider_service_floor=two*vectors,
        target80_total_cycle_budget=int(Fraction(ideal*5, 4)),
        target90_total_cycle_budget_exact=str(Fraction(ideal*10, 9)),
        unchanged_dividers_can_reach90=False, actual_hardware_cycles=None,
        physical_1ghz_timing_verified=False, arithmetic_equivalence_verified=False)


def check_sources():
    pins=json.loads((HERE/'source_pins.json').read_text())
    payload=(HERE/'DivSqrtRecFN_small.scala').read_bytes()
    git_blob=hashlib.sha1(b'blob '+str(len(payload)).encode()+b'\0'+payload).hexdigest()
    if git_blob != pins['upstream']['git_blob_sha1']:
        raise ValueError('upstream Git blob mismatch')
    common=(HERE/'common.scala').read_bytes()
    if hashlib.sha1(b'blob '+str(len(common)).encode()+b'\0'+common).hexdigest() != pins['upstream_common']['git_blob_sha1']:
        raise ValueError('upstream common Git blob mismatch')
    for name, sha in pins['sources'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != sha:
            raise ValueError('source changed: '+name)
    return git_blob


if __name__ == '__main__':
    check_sources()
    print(json.dumps(bounds(),indent=2,sort_keys=True))
