import importlib.util
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('qwen2_bound',ROOT/'scripts/qwen2_prefill_traffic_bound.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_m128_source_bound_does_not_claim_simulated_cycles():
    r=m.report(ROOT,128)
    assert r['total_useful_macs']==6014828544
    assert r['weight_ingress_bytes']==242221056
    assert r['weight_read_cycles_lower_bound']==3784704
    assert r['fixed_resources']['a_allocated_bytes']==704512
    assert r['fixed_resources']['b_ping_pong_allocated_bytes']==81920
    assert r['useful_utilization_upper_bound']<0.4
    assert r['predicted_full_block_cycles'] is None
    assert r['rtl_measured_utilization'] is None
    assert not any(r['scope'].values())


def test_more_tokens_do_not_invent_weight_residency():
    r=m.calculate(1024)
    assert [p['weight_full_reads'] for p in r['dense_phases']]==[13]*6+[32]
    assert r['weight_read_cycles_lower_bound']>r['target_cycle_budgets']['80_percent']
    fp=m.calculate(128,'FP32')
    bf=m.calculate(128,'BF16')
    assert fp['weight_ingress_bytes']==2*bf['weight_ingress_bytes']
    assert fp['useful_utilization_upper_bound']==bf['useful_utilization_upper_bound']/2


@pytest.mark.parametrize('tokens,dtype',[(1,'BF16'),(128.0,'BF16'),(True,'BF16'),(128,'INT8')])
def test_unsupported_workload_cannot_reuse_bound(tokens,dtype):
    with pytest.raises(ValueError):m.calculate(tokens,dtype)


def test_source_drift_and_missing_source_fail_closed(tmp_path):
    with pytest.raises(ValueError,match='source changed'):m.report(tmp_path,128)
    for name in m.SOURCE_PINS:
        dst=tmp_path/name;dst.parent.mkdir(parents=True,exist_ok=True)
        dst.write_bytes((ROOT/name).read_bytes())
    (tmp_path/next(iter(m.SOURCE_PINS))).write_text('// changed control\n')
    with pytest.raises(ValueError,match='source changed'):m.report(tmp_path,128)


@pytest.mark.parametrize('tokens', [128, 1024])
def test_host_attention_requests_cover_every_causal_pair(tokens):
    r=m.host_schedule_report(ROOT,tokens)
    # Independently count the loop nest rather than copying the closed formula.
    pairs=sum(query+1 for query in range(tokens))*12
    qk=sum(128//16 for _ in range(pairs))
    pv=sum(128//16 for _ in range(pairs))
    assert r['issue_counts']['qk_matrix_requests']==qk
    assert r['issue_counts']['pv_matrix_requests']==pv
    assert (qk+pv)*16==m.calculate(tokens)['qk_pv_useful_macs']
    assert r['matrix_only_utilization_upper_bound']<0.5
    assert r['ideal_dense_whole_block_utilization_upper_bound']<0.22
    assert r['useful_utilization_upper_bound']<r['ideal_dense_whole_block_utilization_upper_bound']
    assert r['predicted_full_block_cycles'] is None and r['rtl_measured_cycles'] is None
    assert len(r['source_sha256'])==len(m.SOURCE_PINS)+len(m.HOST_SOURCE_PINS)==27


def test_host_bound_uses_vector_silu_and_keeps_transport_precision_separate():
    r=m.host_schedule_report(ROOT,128)
    c=r['issue_counts']
    assert c['silu_16_lane_primitive_issue_cycles']==6*(128*8960//16)
    assert r['non_dense_cycles_lower_bound']==5342720
    assert r['matrix_only_cycles_lower_bound']==3047424
    assert r['whole_block_cycles_lower_bound']==9127424
    fp=m.host_schedule_report(ROOT,128,'FP32')
    assert fp['issue_counts']==c
    assert fp['current_dense_cycles_lower_bound']==2*r['current_dense_cycles_lower_bound']
    assert fp['useful_utilization_upper_bound']<r['useful_utilization_upper_bound']


def test_host_only_sources_must_be_present_and_unchanged(tmp_path):
    for name in m.SOURCE_PINS:
        dst=tmp_path/name;dst.parent.mkdir(parents=True,exist_ok=True)
        dst.write_bytes((ROOT/name).read_bytes())
    assert m.report(tmp_path,128)['source_sha256']==m.SOURCE_PINS
    with pytest.raises(ValueError,match='Host bound'):m.host_schedule_report(tmp_path,128)
    for name in m.HOST_SOURCE_PINS:
        dst=tmp_path/name;dst.write_bytes((ROOT/name).read_bytes())
    name=next(iter(m.HOST_SOURCE_PINS));(tmp_path/name).write_text('// alternate dispatch\n')
    with pytest.raises(ValueError,match='Host bound'):m.host_schedule_report(tmp_path,128)
