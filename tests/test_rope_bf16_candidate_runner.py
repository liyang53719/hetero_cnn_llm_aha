"""Fail-closed plumbing of the separately named candidate gate."""
import importlib.util
from pathlib import Path
import numpy as np
import pytest
ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('candidate_runner',ROOT/'scripts/run_rope_bf16_candidate.py')
r=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(r)


def test_contract_keeps_production_and_full_block_open():
    c=r.contract()
    assert c['production_policy_changed'] is False
    assert 'memory packing or store integration' in c['non_goals']
    assert c['BF16_conversion']['underflow'].startswith('Inexact and rounded BF16 exponent')


@pytest.mark.parametrize('text,rows,cols',[
    ('00000000\n',2,1),('00000000\n00000000\n',1,1),('0\n',1,1),
    ('0000000A\n',1,1),('00000000 garbage\n',1,2),('00000000\n',1,2),
    ('00000000\n\n',1,1),
])
def test_trace_parser_rejects_missing_extra_and_malformed(text,rows,cols):
    with pytest.raises(ValueError):r.parse_trace(text,rows,cols)


def test_vector_word_order(tmp_path):
    x=np.array([[1,0xdeadbeef,3]],dtype=np.uint32)
    p=tmp_path/'v';r.write_vectors(p,x)
    assert p.read_text()=='00000003deadbeef00000001\n'


def trace():
    return np.array([r.pair_trace(0x00800000,0,0x3f7fffff,0)],dtype=np.uint32)


def test_narrow_host_tininess_allowance():
    expected=trace();actual=expected.copy()
    assert expected[0,0]==0x00800000 and expected[0,4]==3
    actual[0,4]=1;actual[:,24]=r.flag_aggregate(actual)
    differences=r.compare_c(actual,expected)
    assert len(differences)==1 and differences[0]['pair']==0


@pytest.mark.parametrize('column,mask',[(0,1),(4,4),(8,1),(12,2),(16,1),(18,2),(20,1),(22,2),(24,16)])
def test_c_reference_mismatch_rejected(column,mask):
    expected=trace();actual=expected.copy();actual[0,column]^=mask
    if column != 24:actual[:,24]=r.flag_aggregate(actual)
    with pytest.raises(ValueError):r.compare_c(actual,expected)


def test_float_vector_dtype_rejected(tmp_path):
    with pytest.raises(ValueError):r.write_vectors(tmp_path/'bad',np.zeros((1,3),dtype=np.float32))
