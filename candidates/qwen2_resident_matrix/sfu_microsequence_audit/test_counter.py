import pytest
from candidates.qwen2_resident_matrix.sfu_microsequence_audit.counter import (
    HERE, Counter, bounds, check_sources, exp_horner_interval, silu_division_class, trace)


def test_exact_upstream_blob_and_no_remainder_exit_in_recurrence():
    assert check_sources() == '7f65d667a13a0cfb3b2bab15413cb5e71e176f2b'
    src=(HERE/'DivSqrtRecFN_small.scala').read_text()
    recurrence=src.split('def computeCycleNum')[1].split('io.inReady :=')[0]
    assert 'rem' not in recurrence and 'sigWidth + 2' in recurrence
    assert 'f(cycleNum - Mux(processTwoBits, 2.U, 1.U))' in recurrence
    assert 'Mux(skipCycle2, f(1.U), 0.U)' in recurrence


@pytest.mark.parametrize('denominator,expected', [
    (0x3f800000,25), (0x40000000,25), (0x3fc00000,26),
    (0x3f800001,26), (0x3fffffff,26)])
def test_successful_silu_denominators_include_exact_reciprocals(denominator,expected):
    result=trace(**silu_division_class(denominator))
    assert result[0]['accepted'] and result[0]['next_count']==26
    assert result[-1]['edge']==expected
    assert result[-1]['result'] and result[-1]['accepted']
    assert not any(x['accepted'] or x['result'] for x in result[1:-1])


def test_special_one_cycle_path_is_excluded_by_silu_recipe():
    assert trace(normal=False)[-1]['edge']==1
    for word in (0,0x80000000,0x7f800000,0xff800000,0x7fc00000):
        with pytest.raises(ValueError): silu_division_class(word)


def test_same_edge_output_and_new_input_already_credited():
    c=Counter();accepted=[];returned=[]
    for edge in range(101):
        out=c.tick(valid=True,normal=True,quotient_leading_one=True)
        if out['accepted']: accepted.append(edge)
        if out['result']: returned.append(edge)
    assert accepted==[0,25,50,75,100]
    assert returned==[25,50,75,100]


def test_two_bit_option_is_separate_configuration():
    for leading in (False,True):
        assert trace(two_bits=True,leading=leading)[-1]['edge']==14
    assert bounds()['two_bit_option_value']==16
    assert 'def divSqrtOpt_twoBitsPerCycle     = 16' in (HERE/'common.scala').read_text()


def test_rounded_exp_positive_interval_excludes_special_division():
    low, high=exp_horner_interval()[-1]
    assert 0 < low <= high == 1
    # Exp's final multiplier is2**(-k), k>=0, so rounded exp remains[0,1].
    # RNE(1+exp) is therefore[1,2]; both divider inputs are finite/nonzero.


def test_divider_bound_rejects90_even_with_perfect_overlap():
    r=bounds()
    assert r['silu_divider_service_floor']==1792000
    assert r['all_26_cycle_vector_case']==1863680
    assert 80 < r['ideal_perfect_overlap_utilization_ceiling_percent'] < 82
    assert r['unchanged_dividers_can_reach90'] is False
    assert r['physical_1ghz_timing_verified'] is False
    assert r['actual_hardware_cycles'] is None


def test_invalid_controls_fail_closed():
    with pytest.raises(ValueError): Counter(two_bits=16)
    with pytest.raises(ValueError): Counter().tick(normal=1)
    with pytest.raises(ValueError): silu_division_class(True)
