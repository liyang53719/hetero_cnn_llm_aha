"""Supplemental abort proof contracts; actual wrapper execution uses the runner."""
from copy import deepcopy
import gzip
import json
from pathlib import Path
import sys
import numpy as np
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
import run_matrix_read_lookahead_edges as runner
import verify_matrix_read_lookahead_edges as v


def begin(reset=False):
    return dict(event='begin',transaction=1,kind='reset' if reset else 'fault',
        name='reset_lookahead_A2' if reset else 'lookahead_A2_error',checking=1,case=8,role=1,start_token=0,token_count=1,
        packed_base=0x40000,norm_base=0x60000,rope_base=0x80000,gamma_base=0x2000,trig_base=0x3000,act_base=0x10000,wgt_base=0x20000)

def oracle():
    return {8:dict(activation=np.zeros(1024,dtype=np.uint16),weight=np.zeros(1024*256,dtype=np.uint16),steps=np.zeros((8192,32),dtype=np.uint32))}

def events(reset=False):
    rows=[]
    def add(event,cycle=None,**fields):
        rows.append(dict(event=event,transaction=1,**({} if cycle is None else dict(cycle=cycle)),**fields))
    def req(i,cycle):
        k,part=divmod(i,2);address=(0x10000 if not part else 0x20000)+k*64
        add('l2_read',cycle,region=5+part,byte_address=address)
    def rsp(i,cycle,error=0):
        k,part=divmod(i,2);address=(0x10000 if not part else 0x20000)+k*64
        data=bytearray(64) if part else bytearray(0xa5^(((address//64)*17+b*13)&255) for b in range(64))
        if not part:data[:2]=b'\0\0'
        add('l2_response',cycle,byte_address=address,error=error,data=f'{int.from_bytes(data,"little"):0128x}')
    def inp(i,cycle):
        add('matrix_input',cycle,index=i,tile=0,head=0,batch_start=0,context=0,rows=1,clear=int(i==0),last=0,a='0'*64,b='0'*128)
    def edge(phase,cycle,inputs=1,outputs=0,**kw):
        values=dict(k=1,next_a_pending=0,read_owner=0,response_valid=0,response_ready=0,matrix_valid=1,matrix_ready=0)
        values.update(kw);add('lookahead_edge',cycle,phase=phase,inputs=inputs,outputs=outputs,**values)
    add('accepted_start',1)
    for i,data in enumerate(v._descriptors(1,''),1):
        add('descriptor_request',i*2,index=i);add('descriptor',i*2+1,index=i,data=f'{data:032x}',error=0)
    add('dma',14,index=0,kind=1,source=f'{0x100000000:016x}',destination=f'{0x10000:016x}',row_bytes=2,rows=1024,source_stride=2,destination_stride=64)
    add('dma_ack',15,index=0,error=0);add('projection_begin',16,head=0,batch_start=0,rows=1)
    add('dma',16,index=1,kind=1,source=f'{0x200000000:016x}',destination=f'{0x20000:016x}',row_bytes=64,rows=1024,source_stride=1024,destination_stride=64)
    add('dma_ack',17,index=1,error=0)
    req(0,18);rsp(0,19);req(1,20);rsp(1,21);req(2,22);inp(0,22);rsp(2,23);req(3,24);rsp(3,25);req(4,26)
    edge('request',26);edge('held',26,next_a_pending=1,read_owner=1,response_valid=1,matrix_ready=1)
    if reset:add('reset_flush',stage=8)
    else:
        inp(1,27);add('matrix',27,index=0,tile=0,head=0,batch_start=0,context=0,rows=1,last=0,fp32_rows='0'*4096)
        rsp(4,28,1);edge('error',28,inputs=2,outputs=1,k=2,read_owner=1,response_valid=1,response_ready=1,matrix_valid=0)
        edge('done',29,inputs=2,outputs=1,k=0,matrix_valid=0)
        add('done',29,status=8)
        add('terminal',status=8,matrix_inputs=2,matrix_outputs=1,matrix_steps=2,dma_count=2,write_requests=0,write_acks=0,
            completed_heads=0,completed_tokens=0,ddr_write_bytes=0,ddr_read_bytes=67584,command_cycles=29,total_tiles=16,flags=0)
    return rows

def consume(rows,reset=False):
    checker=v.Abort(begin(reset),oracle())
    for row in rows:checker.consume(row)
    return checker

@pytest.mark.parametrize('reset',[False,True])
def test_exact_aborted_inventory(reset):
    checker=consume(events(reset),reset)
    assert checker.counts['matrix_input']-checker.counts['matrix']==1
    assert checker.counts['l2_read']-checker.counts['l2_response']==int(reset)

@pytest.mark.parametrize('change',['wrong_A2','first_A_error','request_not_blocked','response_not_held','early_error',
    'missing_hold','wrong_input','wrong_output','wrong_status','invented_output','write_after_error','lost_read'])
def test_abort_tamper_rejected(change):
    rows=events()
    if change=='wrong_A2':next(r for r in rows if r['event']=='l2_read' and r['byte_address']==0x10080)['byte_address']+=64
    elif change=='first_A_error':next(r for r in rows if r['event']=='l2_response')['error']=1
    elif change=='request_not_blocked':next(r for r in rows if r.get('phase')=='request')['matrix_ready']=1
    elif change=='response_not_held':next(r for r in rows if r.get('phase')=='held')['response_ready']=1
    elif change=='early_error':next(r for r in rows if r['event']=='l2_response' and r['error']==1)['cycle']=27
    elif change=='missing_hold':rows=[r for r in rows if r.get('phase')!='held']
    elif change=='wrong_input':next(r for r in rows if r['event']=='matrix_input')['a']='1'+'0'*63
    elif change=='wrong_output':next(r for r in rows if r['event']=='matrix')['fp32_rows']='1'+'0'*4095
    elif change=='wrong_status':next(r for r in rows if r['event']=='done')['status']=0
    elif change=='invented_output':rows[-1]['matrix_outputs']=2
    elif change=='write_after_error':rows.insert(-1,dict(event='l2_write',transaction=1,cycle=30))
    elif change=='lost_read':rows=[r for r in rows if not(r['event']=='l2_read' and r['byte_address']==0x10080)]
    with pytest.raises((ValueError,KeyError)):consume(rows)


def test_reset_requires_pending_read_and_exact_target():
    rows=events(True);rows[-1]['stage']=2
    with pytest.raises(ValueError):consume(rows,True)


def test_original_scoreboards_and_frozen_source_preserved():
    original=(ROOT/runner.BENCH).read_bytes();text=runner.make_bench()
    assert (ROOT/runner.BENCH).read_bytes()==original
    for phrase in ('independent per-K all512 Matrix mismatch','Matrix actual activation row mismatch',
                   'Matrix actual weight column mismatch','edge_read_request(addr,regid);','edge_read_response();',
                   'edge_fault_case();good_case(1,0,1);edge_reset_case();good_case(1,0,1);'):
        assert phrase in text
    assert 'READ_LOOKAHEAD||fabric_profile!=FAB_UNSTALLED' in text
    assert 'fault_read_region==regid&&(!edge_fault||addr==act_base+128)' in text


def test_patch_anchor_fails_closed():
    with pytest.raises(ValueError):runner.replace_once('same same','same','different')
    with pytest.raises(ValueError):runner.replace_once('absent','same','different')


def test_source_receipt_is_not_an_arbitrary_cli_digest():
    source=(ROOT/'scripts/run_matrix_read_lookahead_edges.py').read_text()
    assert "primary.read_contract()['cached_fixture_receipt_sha256']" in source
    assert '--trusted-summary' not in source and '--digest' not in source
    assert source.count('verify_materialized(args.vectors,trusted_summary_sha256=trusted_summary_sha256)')==2
    assert "'-j','2'" in source


def test_stream_rejects_incomplete_valid_abort_inventory(tmp_path,monkeypatch):
    monkeypatch.setattr(v,'Cases',lambda _:oracle())
    path=tmp_path/'partial.gz'
    with gzip.open(path,'wt') as f:
        for row in [begin(),*events()]:f.write(json.dumps(row)+'\n')
    with pytest.raises(ValueError,match='EOF/inventory'):v.verify_trace(path,'unused')

@pytest.mark.parametrize('change',['missing_start','missing_descriptors','descriptor_with_dma_owner',
                                  'projection_before_activation_ack','missing_projection','fast_input','fast_output'])
def test_abort_start_order_and_latency_rejected(change):
    rows=events(True if change=='missing_start' else False)
    if change=='missing_start':rows=[r for r in rows if r['event']!='accepted_start']
    elif change=='missing_descriptors':rows=[r for r in rows if not r['event'].startswith('descriptor')]
    elif change=='descriptor_with_dma_owner':
        # Even a syntactically next descriptor cannot acquire an active DMA owner.
        checker=v.Abort(begin(),oracle());checker.started=1
        checker.pending['dma']=dict(index=0);checker.counts['descriptor_request']=0
        with pytest.raises(ValueError):checker.consume(dict(event='descriptor_request',transaction=1,cycle=2,index=1))
        return
    elif change=='projection_before_activation_ack':
        proj=next(r for r in rows if r['event']=='projection_begin');rows.remove(proj)
        where=next(i for i,r in enumerate(rows) if r['event']=='dma_ack')
        rows.insert(where,proj)
    elif change=='missing_projection':rows=[r for r in rows if r['event']!='projection_begin']
    elif change=='fast_input':next(r for r in rows if r['event']=='matrix_input' and r['index']==1)['cycle']=26
    elif change=='fast_output':next(r for r in rows if r['event']=='matrix')['cycle']=26
    with pytest.raises((ValueError,KeyError)):consume(rows,change=='missing_start')


def test_derived_harness_hash_is_bound_before_and_after_execution():
    source=(ROOT/'scripts/run_matrix_read_lookahead_edges.py').read_text()
    assert 'bench_hash=primary.sha256(bench)' in source
    assert 'primary.sha256(bench)==bench_hash and bench.read_text()==make_bench()' in source
    assert source.index('bench_hash=primary.sha256(bench)')<source.index('run_logged(command')
