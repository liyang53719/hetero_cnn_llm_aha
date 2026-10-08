"""Independent schedule/counter rejection tests; no synthesis/simulation claims."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
import verify_matrix_read_lookahead_metrics as m

def fixture(fabric='replay',flag=0):
    fields=m.TOP-m.STRINGS-set(m.NESTED)-{'channels'}
    row={k:0 for k in fields}
    row.update(event='command_metrics',schema_version=1,transaction=1,name='fake',kind='reject',fabric=fabric,
               read_lookahead=flag,replay_schedule_version=1,replay_salt='3c6ef372',completed=1,status=4,start_cycle=1,end_cycle=100,command_cycles=100)
    row.update({k:{x:0 for x in keys} for k,keys in m.NESTED.items()})
    row['channels']={}
    for ch,name in enumerate(m.CHANNELS):
        c={k:0 for k in m.CHANNEL_KEYS-{'schedule_hash'}}
        c.update({k:v for k,v in m.schedule(fabric,ch,0).items() if k!='same_cycle_write_acks'})
        row['channels'][name]=c
    t=dict(name='fake',kind='reject',status=4,accepted_to_done_cycles=100,matrix_input_packets=0,
           event_counts={},input_ii=dict(count=0,sum=0,min=None,max=None),read_latency=dict(count=0,sum=0,min=None,max=None))
    return row,dict(transactions=1,terminals=[t])

def verify(tmp_path,row,trace):
    p=tmp_path/'metrics.jsonl';p.write_text(json.dumps(row)+'\n')
    return m.verify_metrics(p,trace,fabric=row['fabric'],lookahead=row['read_lookahead'])

@pytest.mark.parametrize('fabric',('unstalled','replay'))
def test_empty_optional_extrema_reconciled(tmp_path,fabric):
    row,t=fixture(fabric);assert verify(tmp_path,row,t)==[row]

@pytest.mark.parametrize('change',('unknown','missing','bool','cycles','input_count','stall_partition','ii','prefetch','owner','latency','hash','budget','replay','request_count','occupancy'))
def test_counter_tamper_rejected(tmp_path,change):
    row,t=fixture()
    if change=='unknown':row['extra']=0
    elif change=='missing':del row['status']
    elif change=='bool':row['status']=False
    elif change=='cycles':row['command_cycles']+=1
    elif change=='input_count':row['matrix_input_fires']=1
    elif change=='stall_partition':row['matrix_input_stall_cycles']=1
    elif change=='ii':row['matrix_input_ii']['sum']=1
    elif change=='prefetch':row['prefetch_accepts']=1
    elif change=='owner':row['channels']['read']['requests']=2
    elif change=='latency':row['channels']['read']['latency_sum']=1
    elif change=='hash':row['channels']['read']['schedule_hash']='f'*16
    elif change=='budget':row['channels']['read']['admission_budget_sum']=1
    elif change=='replay':row['replay_salt']='00000000'
    elif change=='request_count':row['channels']['descriptor']['requests']=1
    elif change=='occupancy':row['channels']['read']['pending_cycles']=101
    with pytest.raises((ValueError,KeyError)):verify(tmp_path,row,t)

@pytest.mark.parametrize('bad',('', '{', '{}', '{}\n{}\n'))
def test_truncated_or_incomplete_rows(tmp_path,bad):
    row,t=fixture();p=tmp_path/'bad';p.write_text(bad)
    with pytest.raises((ValueError,KeyError)):m.verify_metrics(p,t,fabric='replay',lookahead=0)

def test_known_schedule_and_time_independence():
    # Published algorithm is uint32 avalanche -> per-index delay -> 64-bit fingerprint.
    assert m.replay_hash(0,2,0)==0x2a460f55
    a=m.schedule('replay',2,1000)
    assert a==m.schedule('replay',2,1000)
    assert a['admission_budget_sum']>0 and a['response_budget_sum']>0
    assert m.schedule('unstalled',2,1000)['admission_budget_sum']==0
    assert a!=m.schedule('replay',1,1000)

def test_pair_rejects_global_cycle_lfsr_or_changed_schedule():
    a,_=fixture();b=deepcopy(a);b['read_lookahead']=1
    assert m.verify_pair_metrics([a]*4,[b]*4)
    b['channels']['read']['schedule_hash']='a'*16
    with pytest.raises(ValueError):m.verify_pair_metrics([a]*4,[b]*4)
