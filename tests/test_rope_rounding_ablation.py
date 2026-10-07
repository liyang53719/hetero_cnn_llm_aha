import importlib.util
from pathlib import Path
import random
import subprocess

import numpy as np
import pytest

from heteronpu.rope_hardware_oracle import pair_rne,bf16_rne_word
from heteronpu.rope_rounding_ablation import VARIANTS,COLUMNS,trace_pair,compare_words

ROOT=Path(__file__).resolve().parents[1]


def runner():
    spec=importlib.util.spec_from_file_location('rope_ablation_test',ROOT/'scripts/run_rope_rounding_ablation.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


@pytest.mark.parametrize('variant',VARIANTS)
def test_permanent_witness_and_complete_trace(variant):
    row=trace_pair(0xBF920000,0xC1100000,0x3F800000,0x3CE10000,variant)
    assert len(row)==len(COLUMNS)==18
    assert row[:4]==(0xBF920000,0xBE7D2000,0xBD005200,0xC1100000)
    expected=0xC1100000 if variant in ('sin_bf16_only','both_bf16') else 0xC1110000
    assert row[-2:]==(0xBF650000,expected)
    assert row[10]==(0xBD000000 if variant in ('sin_bf16_only','both_bf16') else 0xBD005200)


@pytest.mark.parametrize('variant',VARIANTS)
@pytest.mark.parametrize('inputs,expected',[
    ((0x80000000,0,0x3F800000,0x3F800000),(0x80000000,0)),
    ((0,0x80000000,0x3F800000,0x3F800000),(0,0)),
    ((0x3F800000,0x3F800000,0x3F800000,0x3F800000),(0,0x40000000)),
    ((1,3,0x3F000000,0x3F000000),(0x80000000,0)),
])
def test_signed_zero_cancellation_and_subnormal(variant,inputs,expected):
    actual=trace_pair(*inputs,variant)
    # Product-BF16 policies can remove the tiny negative even difference.
    if inputs[0]==1 and variant!='fp32_all':
        expected=(0,0) if variant=='both_bf16' else (0x80000000,0) if variant=='cos_bf16_only' else (0,0)
    assert actual[-2:]==expected


@pytest.mark.parametrize('word',[0x7F800000,0xFF800000,0x7FC00000,0x7F800001,-1,2**32,True,1.0])
def test_invalid_inputs_rejected(word):
    for v in VARIANTS:
        with pytest.raises((ValueError,TypeError)):trace_pair(word,0,0x3F800000,0,v)


@pytest.mark.parametrize('inputs',[(0x7F7FFFFF,0,0x40000000,0),(0x7F7FFFFF,0,0x3F800000,0),(0x7F7F0000,0x7F7F0000,0x3F800000,0xBF800000)])
def test_intermediate_or_projection_overflow_rejected(inputs):
    for v in VARIANTS:
        with pytest.raises(ValueError,match='overflow'):trace_pair(*inputs,v)


def test_unknown_variant_rejected():
    with pytest.raises(ValueError,match='variant'):trace_pair(0,0,0,0,'implicit-production')


def test_non_bf16_inputs_are_honestly_arithmetic_only():
    t=trace_pair(0x3F800001,0x3F800000,0x3F7FFFFE,0x3F800000,'fp32_all')
    assert t[12]==0  # Separate product RNE, not a fused exact difference.
    assert t[:4]==(0x3F800000,0x3F800000,0x3F800001,0x3F7FFFFE)


def test_fp32_baseline_matches_original_but_does_not_modify_it():
    r=random.Random(441)
    for _ in range(200):
        inp=tuple((r.randrange(2)<<31)|(r.randrange(80,160)<<23)|r.randrange(1<<23) for _ in range(4))
        t=trace_pair(*inp,'fp32_all');old=pair_rne(*inp)
        assert t[12:14]==old[:2]
        assert np.bitwise_or.reduce(t[4:8]+t[14:16])==old[2]
        assert t[-2:]==tuple(bf16_rne_word(x) for x in old[:2])


def test_ulp_distance_and_unchanged_limits():
    a=np.array([0x80000000,0,0x3F810000,0xC1110000],dtype=np.uint32)
    b=np.array([0,0x80000000,0x3F800000,0xC1100000],dtype=np.uint32)
    m=compare_words(a,b,bf16=True)
    assert m['bit_different']==4 and m['signed_zero_only_differences']==2
    assert m['max_ulp']==1 and m['mean_ulp']==0.5
    assert m['max_abs_limit']==0.03125 and m['mean_abs_limit']==0.005
    assert m['mismatches_over_max']==1 and m['pass'] is False


@pytest.mark.parametrize('kind',['empty','nonfinite','unrounded','shape','dtype'])
def test_malformed_comparison_rejected(kind):
    a=np.array([0],dtype=np.uint32);b=a.copy()
    if kind=='empty':a=b=np.array([],dtype=np.uint32)
    if kind=='nonfinite':a[0]=0x7F800000
    if kind=='unrounded':a[0]=1
    if kind=='shape':b=np.array([0,0],dtype=np.uint32)
    if kind=='dtype':b=b.astype(np.int64)
    with pytest.raises(ValueError):compare_words(a,b,bf16=True)


@pytest.mark.parametrize('name',['local','remote'])
def test_frozen_real_native_products_and_outputs(name):
    data,p=runner().load_corpus(name)
    assert p['arithmetic_recomputed_when_freezing'] is False
    assert [g['pairs'] for g in p['groups']]==[32768,8192,32768,8192]
    chosen=sorted(set([0,32767,32768,40959,40960,69266,81919]+[random.Random(i).randrange(81920) for i in range(100)]))
    for i in chosen:
        t=trace_pair(*(int(x) for x in data['inputs'][i]),'both_bf16')
        assert t[8:12]==tuple(data['native_products'][i])
        assert t[-2:]==tuple(data['native_outputs'][i])


def test_frozen_corruption_rejected_before_numpy_load(tmp_path,monkeypatch):
    m=runner()
    for name in m.FIXTURE_PINS:(tmp_path/name).write_bytes(b'untrusted')
    monkeypatch.setattr(np,'load',lambda *a,**k:pytest.fail('read untrusted array'))
    with pytest.raises(ValueError,match='digest drift'):m.load_corpus('local',tmp_path)


def test_corpus_identity_not_cli_chosen():
    with pytest.raises(ValueError,match='unknown'):runner().load_corpus('regenerated')


def test_existing_production_contract_still_exact():
    spec=importlib.util.spec_from_file_location('existing_rope',ROOT/'scripts/run_rope_hardware_oracle.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    assert m.contract()['arithmetic'].startswith('four independent FP32 RNE')


def test_independent_c_all_intermediates_and_rejections(tmp_path):
    m=runner();executable,info=m.compile_reference(tmp_path,'gcc')
    rows=m.synthetic_inputs()[:7]
    traces=m.calculate(rows)
    result=m.independent_check(executable,rows,traces,tmp_path,'test',allow_tininess_difference=True)
    assert result['intermediate_value_mismatches']==0
    assert result['unexplained_flag_mismatches']==0
    assert len(m.rejected_cases(executable))==7
    bad=traces.copy();bad[0,0,8]^=1
    with pytest.raises(ValueError,match='value mismatch'):m.independent_check(executable,rows,bad,tmp_path,'mutated',allow_tininess_difference=True)
    p=subprocess.run([str(executable)],input='00000000 00000000 3f800000\n',capture_output=True,text=True)
    assert p.returncode and not p.stdout.strip()


def test_exact_min_normal_cannot_waive_injected_underflow(tmp_path):
    m=runner();executable,_=m.compile_reference(tmp_path,'gcc')
    rows=np.array([[0x00800000,0,0x3F800000,0]],dtype=np.uint32)
    trace=m.calculate(rows);trace[0,0,4]^=2
    with pytest.raises(ValueError,match='requires inexact'):
        m.independent_check(executable,rows,trace,tmp_path,'bad_uf',allow_tininess_difference=True)
