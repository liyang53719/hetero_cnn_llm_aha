"""Fail-closed source-only tests for complete paired streaming gate."""
from copy import deepcopy
from io import StringIO
import hashlib
import json
from pathlib import Path
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
import run_matrix_read_lookahead as runner
import verify_matrix_read_lookahead_stream as stream

def runs():
    result=[]
    for source in ('baseline','avx2'):
        for fabric in ('unstalled','replay'):
            for flag in (0,1):
                result.append(dict(source=source,fabric=fabric,lookahead=flag,suite='main',
                    command_metrics=[dict(name=str(i),kind='main',fabric=fabric,replay_schedule_version=1,replay_salt='3c6ef372',matrix_input_fires=0,completed=1,status=0,read_lookahead=flag,channels={ch:dict(requests=0,responses=0,admission_budget_sum=0,response_budget_sum=0,schedule_hash='0') for ch in ('descriptor','dma','read','write')}) for i in range(4)],
                    command_counters=[dict(cycles=1000000-flag*10000,matrix_steps=x) for x in (131072,16384,131072,16384)]))
    result.append(dict(source='baseline',fabric='random',lookahead=1,suite='all'))
    return result

def test_exact_pair_geometry_and_fixed_denominator():
    out=runner.compare_runs(runs())
    assert len(out)==4
    for r in out:
        assert r['cycles_saved']==40000 and r['fixed_matrix_lanes']==512
        assert r['lookahead_candidate_useful_wall_fraction']==294912/3960000
        assert r['whole_block_metric'] is False

@pytest.mark.parametrize('change',('missing','duplicate','step','no_improvement','wrong_source','wrong_stress'))
def test_pair_inventory_or_workload_drift_rejected(change):
    r=runs()
    if change=='missing':r.pop()
    elif change=='duplicate':r[0]=deepcopy(r[1])
    elif change=='step':r[0]['command_counters'][0]['matrix_steps']-=1
    elif change=='no_improvement':r[1]['command_counters'][0]['cycles']+=50000
    elif change=='wrong_stress':r[-1]['source']='avx2'
    else:r[0]['source']='other'
    with pytest.raises((ValueError,KeyError)):runner.compare_runs(r)

def test_pinned_cache_is_published_and_not_cli_digest():
    c=runner.read_contract()
    assert c['cached_fixture_receipt_sha256']=='045bf413457edea83fa23036f46330d3cdcd07ad9303ce1e0d6c717eea17bd70'
    source=(ROOT/'scripts/run_matrix_read_lookahead.py').read_text()
    assert '--trusted-summary' not in source and '--digest' not in source
    assert 'verify_materialized(args.cached_vectors,trusted_summary_sha256=digest)' in source
    assert 'verify_materialized(vectors,trusted_summary_sha256=receipt)' in source

def test_stream_digest_full_inventory(monkeypatch):
    text='one\ntwo\n'
    def fake(records,vectors,**kwargs):
        assert kwargs==dict(suite='main',require_inputs=True)
        assert list(records)==['one\n','two\n']
        return {'complete':True}
    monkeypatch.setattr(stream,'verify_trace',fake)
    r=stream.verify_stream(StringIO(text),Path('unused'),suite='main')
    assert r['trace_records']==2 and r['trace_bytes']==len(text)
    assert r['trace_sha256']==hashlib.sha256(text.encode()).hexdigest()
    assert r['raw_trace_retained'] is False and r['replay_requires_regeneration'] is True

def test_stream_failure_not_converted_to_success(monkeypatch):
    def fail(records,*args,**kwargs):
        next(records)
        raise ValueError('bad lane511')
    monkeypatch.setattr(stream,'verify_trace',fail)
    with pytest.raises(ValueError,match='bad lane511'):
        stream.verify_stream(StringIO('bad\n'),Path('unused'),suite='main')

def test_unstalled_log_preserves_counts_but_does_not_invent_stalls():
    from test_matrix_norm_rope_tile16_runner import log_text,metrics
    m=metrics()
    for k in ('read_stall_cycles','write_stall_cycles','dma_stall_cycles','delayed_ACK_cycles','same_cycle_ACKs'):m[k]=0
    log=log_text(totals=m)
    assert runner.tile16.verify_log(log,'main',require_stalls=False)[0]==m
    with pytest.raises(ValueError):runner.tile16.verify_log(log,'main')
    m['actual_matrix_inputs']=0
    with pytest.raises(ValueError):runner.tile16.verify_log(log_text(totals=m),'main',require_stalls=False)


def test_unstalled_equality_is_valid_under_context0_recurrence_floor():
    r=runs()
    for row in r:
        if row['suite']=='main' and row['fabric']=='unstalled' and row['lookahead']==1:
            for cmd in row['command_counters']:cmd['cycles']+=10000
    comparisons=runner.compare_runs(r)
    assert all(x['cycles_saved']==0 for x in comparisons if x['fabric']=='unstalled')

def test_replay_equality_does_not_claim_measured_improvement():
    r=runs()
    for row in r:
        if row['suite']=='main' and row['fabric']=='replay' and row['lookahead']==1:
            for cmd in row['command_counters']:cmd['cycles']+=10000
    with pytest.raises(ValueError,match='did not reduce deterministic'):
        runner.compare_runs(r)
