#!/usr/bin/env python3
"""Specialized abort-owner proof plus unchanged full recovery trace verification.

The primary suite verifier is not weakened. Aborted commands explicitly account
for flushed Matrix inputs and the reset-discarded read; complete recoveries use
its original Transaction checker, including every input and all512 output lanes.
"""
from __future__ import annotations
from collections import Counter, deque
import gzip
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from heteronpu.model_geometry import require
from verify_matrix_norm_rope_tile16_trace import Cases, Transaction, _record, _hex, _packed, _descriptors, _unique_object

EDGE_FIELDS={'event','transaction','cycle','phase','inputs','outputs','k','next_a_pending','read_owner',
             'response_valid','response_ready','matrix_valid','matrix_ready'}
INVENTORY=[('fault','lookahead_A2_error'),('recovery','recovery_after_fault_or_reset'),
           ('reset','reset_lookahead_A2'),('recovery','recovery_after_fault_or_reset')]

class Abort:
    def __init__(self,begin,cases):
        self.b=begin;self.ex=cases[8];self.counts=Counter();self.pending={k:None for k in ('descriptor','dma','read')}
        self.inputs=deque();self.input_cycles=[];self.phases=[];self.started=None;self.done=None;self.error=False
        self.reset=begin['kind']=='reset';self.last_by_event={};self.descriptors=_descriptors(1,'')
        require(begin['checking']==1 and begin['case']==8 and begin['role']==1 and begin['start_token']==0 and begin['token_count']==1,'abort geometry drift')
        require({k:begin[k] for k in ('packed_base','norm_base','rope_base','gamma_base','trig_base','act_base','wgt_base')}==dict(
            packed_base=0x40000,norm_base=0x60000,rope_base=0x80000,gamma_base=0x2000,trig_base=0x3000,act_base=0x10000,wgt_base=0x20000),'abort base drift')
    def consume(self,r):
        e=r['event'];n=self.counts
        require(r['transaction']==self.b['transaction'],'abort owner drift')
        if 'cycle' in r:
            require(r['cycle']>self.last_by_event.get(e,-1) or e=='lookahead_edge','duplicate channel transfer')
            self.last_by_event[e]=r['cycle']
        if e!='accepted_start':require(self.started is not None,'traffic before accepted start')
        if self.done is not None:require(e=='terminal','activity after done')
        if self.error:require(e in ('lookahead_edge','done','terminal'),'activity after fatal read error')
        if e=='lookahead_edge':
            p=r['phase'];want=['request','held'] if self.reset else ['request','held','error','done']
            require(len(self.phases)<len(want) and p==want[len(self.phases)],'edge phase inventory/order')
            require(r['inputs']==n['matrix_input'] and r['outputs']==n['matrix'],'edge counter mismatch')
            if p=='request':
                require(n['l2_read']==5 and self.pending['read'] is not None and r['k']==1 and r['inputs']==1 and r['outputs']==0,
                        'request did not target A2 while Matrix1 pending')
                require(r['matrix_valid']==1 and r['matrix_ready']==0 and r['next_a_pending']==0 and r['read_owner']==0,'request was not accepted under Matrix backpressure')
            elif p=='held':
                require(r['k']==1 and r['inputs']==1 and r['outputs']==0 and self.pending['read'] is not None and n['l2_response']==4,'held response target drift')
                require(r['next_a_pending']==r['read_owner']==r['response_valid']==r['matrix_valid']==1 and r['response_ready']==0,'response not actually held')
            elif p=='error':
                require(self.error and n['l2_response']==5 and r['inputs']==2 and r['outputs']==1 and r['k']==2,'error release/order drift')
            else:require(self.done is None and self.error and r['next_a_pending']==r['read_owner']==0,'fault done did not drain')
            self.phases.append(dict(r))
        elif e=='accepted_start':
            require(self.started is None and not n,'late/duplicate start');self.started=r['cycle']
        elif e=='descriptor_request':
            require(all(q is None for q in self.pending.values()) and r['index']==n[e]+1<=6,'descriptor owner/order')
            self.pending['descriptor']=r
        elif e=='descriptor':
            q=self.pending['descriptor'];require(q is not None and r['index']==q['index'] and r['cycle']>q['cycle'] and r['error']==0,'descriptor response owner')
            require(_hex(r['data'],32)==self.descriptors[r['index']-1],'descriptor snapshot drift');self.pending['descriptor']=None
        elif e=='projection_begin':
            require(n[e]==0 and n['dma']==n['dma_ack']==1 and all(q is None for q in self.pending.values()) and (r['head'],r['batch_start'],r['rows'])==(0,0,1),'abort projection geometry/order')
        elif e=='dma':
            require(all(v is None for v in self.pending.values()) and n[e]<2 and n['descriptor']==6 and n['projection_begin']==n[e],'DMA owner/order')
            expected=[(1,0x100000000,0x10000,2,1024,2,64),(1,0x200000000,0x20000,64,1024,1024,64)][n[e]]
            actual=(r['kind'],_hex(r['source'],16),_hex(r['destination'],16),r['row_bytes'],r['rows'],r['source_stride'],r['destination_stride'])
            require(r['index']==n[e] and actual==expected,'abort DMA source geometry');self.pending['dma']=r
        elif e=='dma_ack':
            q=self.pending['dma'];require(q is not None and r['index']==q['index'] and r['cycle']>q['cycle'] and r['error']==0,'DMA ACK owner');self.pending['dma']=None
        elif e=='l2_read':
            require(all(v is None for v in self.pending.values()) and n['dma_ack']==2 and n[e]<5,'read owner or scope')
            k,part=divmod(n[e],2);address=self.b['act_base' if part==0 else 'wgt_base']+k*64
            require(r['region']==5+part and r['byte_address']==address,'A/W request order');self.pending['read']=r
        elif e=='l2_response':
            q=self.pending['read'];require(q is not None and r['byte_address']==q['byte_address'] and r['cycle']>q['cycle'],'read response owner')
            k,part=divmod(n[e],2)
            if part:
                want=_packed(self.ex['weight'][k*256:k*256+32])
            else:
                beat=q['byte_address']//64;raw=bytearray(0xa5^((beat*17+b*13)&255) for b in range(64))
                raw[:2]=int(self.ex['activation'][k]).to_bytes(2,'little');want=int.from_bytes(raw,'little')
            require(_hex(r['data'],128)==want,'abort raw operand source mismatch')
            bad=not self.reset and k==2 and part==0
            require(r['error']==int(bad),'wrong error target')
            if bad:
                require([x['phase'] for x in self.phases]==['request','held'] and n['matrix_input']==2 and n['matrix']==1,'error before operand release')
                require(r['cycle']>self.input_cycles[1]>self.phases[1]['cycle'],'error/Matrix/held ordering')
                self.error=True
            self.pending['read']=None
        elif e=='matrix_input':
            i=n[e];require(i<2 and r['index']==i and r['tile']==0 and r['head']==r['batch_start']==r['context']==0 and r['rows']==1,'input identity')
            require(r['clear']==int(i==0) and r['last']==0 and n['l2_response']==2*(i+1),'input before operands')
            require(_hex(r['a'],64)==int(self.ex['activation'][i]) and _hex(r['b'],128)==_packed(self.ex['weight'][i*256:i*256+32]),'input source arithmetic operands')
            if i:require(r['cycle']-self.input_cycles[-1]>=5,'Matrix input violates context II5')
            self.inputs.append(r['cycle']);self.input_cycles.append(r['cycle'])
        elif e=='matrix':
            i=n[e];require(i==0 and self.inputs and r['cycle']>=self.inputs[0]+5 and r['index']==i and r['tile']==0 and r['head']==r['batch_start']==r['context']==0 and r['rows']==1 and r['last']==0,'aborted output identity')
            require(_hex(r['fp32_rows'],4096)==_packed(self.ex['steps'][i],4),'abort all512 output arithmetic')
            self.inputs.popleft()
        elif e=='done':
            require(not self.reset and self.error and r['status']==8 and all(v is None for v in self.pending.values()) and n['matrix_input']==2 and n['matrix']==1,'fault done ownership')
            self.done=r
        elif e=='terminal':
            require(self.done is not None and r['status']==8 and r['matrix_inputs']==r['matrix_steps']==2 and r['matrix_outputs']==1 and r['dma_count']==2,'fault terminal counts')
            require(r['write_requests']==r['write_acks']==r['completed_heads']==r['completed_tokens']==r['ddr_write_bytes']==0 and r['ddr_read_bytes']==67584,'fault side effects')
            require(r['command_cycles']==self.done['cycle']-self.started+1,'fault cycle denominator')
            require(n['l2_read']==n['l2_response']==5 and len(self.inputs)==1 and len(self.phases)==4,'fault exact drain/abort inventory')
        elif e=='reset_flush':
            require(self.reset and r['stage']==8 and n['matrix_input']==1 and n['matrix']==0 and n['l2_read']==5 and n['l2_response']==4 and len(self.phases)==2,'reset missed early owner')
            require(self.pending['read'] is not None and self.pending['descriptor'] is self.pending['dma'] is None and len(self.inputs)==1,'reset discarded-owner inventory')
        else:raise ValueError('unexpected aborted-command event: '+e)
        if e!='lookahead_edge':n[e]+=1


def verify_trace(path,vectors):
    cases=Cases(vectors);active=None;index=0;previous=-1;proof=[];events=Counter();digest=hashlib.sha256();records=0
    with gzip.open(path,'rt',encoding='utf-8',newline='') as stream:
        for line in stream:
            digest.update(line.encode());records+=1
            raw=json.loads(line,object_pairs_hook=_unique_object)
            if raw.get('event')=='lookahead_edge':
                require(line.endswith('\n') and set(raw)==EDGE_FIELDS,'edge schema/truncation')
                require(type(raw['phase']) is str and all(type(v) is int and v>=0 for k,v in raw.items() if k not in ('event','phase')),'edge field type')
                r=raw
            else:r=_record(line)
            if 'cycle' in r:require(r['cycle']>=previous,'trace time reversed');previous=r['cycle']
            e=r['event'];events[e]+=1
            if e=='begin':
                require(active is None and index<len(INVENTORY) and r['transaction']==index+1 and (r['kind'],r['name'])==INVENTORY[index],'supplemental command inventory')
                active=Transaction(r,cases,require_inputs=True) if r['kind']=='recovery' else Abort(r,cases);index+=1
            else:
                require(active is not None and r['transaction']==index,'event outside supplemental owner')
                active.consume(r)
                if e in ('terminal','reset_flush'):
                    count=active.counts
                    if isinstance(active,Abort):
                        proof.append(dict(kind=active.b['kind'],matrix_inputs=count['matrix_input'],matrix_outputs=count['matrix'],
                                          aborted_inflight=count['matrix_input']-count['matrix'],read_requests=count['l2_read'],
                                          read_responses=count['l2_response'],reset_discarded_reads=count['l2_read']-count['l2_response'],
                                          edge_phases=active.phases,status=r.get('status')))
                    else:
                        require(count['matrix_input']==count['matrix']==16384 and r['status']==0,'incomplete real K one-token recovery')
                        proof.append(dict(kind='recovery',matrix_inputs=count['matrix_input'],matrix_outputs=count['matrix'],
                                          completed_heads=active.completed_heads,completed_tokens=active.completed_tokens,status=0))
                    active=None
    require(active is None and index==4,'missing supplemental EOF/inventory')
    return dict(status='PASS_ACTUAL_WRAPPER_LOOKAHEAD_ERROR_RESET',commands=proof,events=dict(events),trace_records=records,
                raw_trace_sha256=digest.hexdigest(),actual_Matrix512_and_SharedL2=True,
                original_full512_scoreboard_preserved=True,independent_all512_stream_check=True,
                primary_full_suite_verifier_weakened=False,full_primary_AB_or_CI_claimed=False)
