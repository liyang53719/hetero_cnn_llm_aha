#!/usr/bin/env python3
"""Independent causal delay schedule and actual endpoint counter reconciliation."""
from __future__ import annotations
import json
import re
from pathlib import Path
from functools import lru_cache
from heteronpu.model_geometry import require
from verify_matrix_norm_rope_trace import _unique_object
CHANNELS=('descriptor','dma','read','write')
CHANNEL_KEYS=set('requests responses request_stall_cycles response_hold_cycles pending_cycles latency_count latency_sum latency_max admission_budget_sum response_budget_sum schedule_hash'.split())
NESTED={'operand_wait_cycles':set('arq arp wrq wrp'.split()),'matrix_input_ii':set('count sum min max'.split()),
        'scheduler_stall_cycles':set('endpoint_inactive context_busy fifo_full array_admission'.split()),
        'overlap_cycles':set('matrix_stall_read_pending matrix_input_read_pending read_request_matrix_input read_response_matrix_output read_pending_context_busy'.split())}
TOP=set('event schema_version transaction name kind fabric read_lookahead replay_schedule_version replay_salt completed status start_cycle end_cycle command_cycles matrix_input_fires matrix_input_stall_cycles prefetch_occupancy_cycles prefetch_accepts context_busy_raw_cycles fabric_read_response_hold_cycles read_artificial_response_hold_cycles same_cycle_write_acks channels'.split())|set(NESTED)
STRINGS=set('event name kind fabric replay_salt'.split())

def uints(mapping,keys):
    require(set(mapping)==set(keys),'metric field inventory drift')
    require(all(type(v) is int and v>=0 for v in mapping.values()),'metric nonnegative integer type drift')

def replay_hash(ordinal,channel,domain):
    mask=(1<<32)-1
    h=(ordinal^0x3c6ef372^((channel+1)*0x9e3779b9)^((domain+1)*0x85ebca6b))&mask
    h=((h^(h>>16))*0x7feb352d)&mask
    h=((h^(h>>15))*0x846ca68b)&mask
    return h^(h>>16)

@lru_cache(maxsize=64)
def schedule(fabric,channel,count):
    require(fabric in ('unstalled','replay'),'random delays do not define a causal paired schedule')
    a_sum=r_sum=same=0;digest=0xcbf29ce484222325
    for i in range(count):
        admission=0 if fabric=='unstalled' else replay_hash(i,channel,0)%4
        response=0
        if fabric=='replay':
            response=replay_hash(i,channel,1)%((8,16,8,26)[channel])+(channel==3)
            if channel==3 and replay_hash(i,channel,2)&1:response=0
        if channel==3 and response==0:same+=1
        a_sum+=admission;r_sum+=response
        word=(i<<32)|(admission<<16)|response
        digest=((digest^word)*0x100000001b3)&((1<<64)-1)
    return {'admission_budget_sum':a_sum,'response_budget_sum':r_sum,'schedule_hash':f'{digest:016x}','same_cycle_write_acks':same}

def verify_metrics(path,trace,*,fabric,lookahead):
    lines=Path(path).read_text().splitlines(keepends=True)
    require(len(lines)==trace['transactions']==len(trace['terminals']),'metrics complete transaction inventory mismatch')
    results=[]
    for ordinal,(line,t) in enumerate(zip(lines,trace['terminals']),1):
        require(line.endswith('\n'),'truncated metric record')
        m=json.loads(line,object_pairs_hook=_unique_object)
        require(type(m) is dict and set(m)==TOP,'metric top-level inventory drift')
        require(all(type(m[k]) is str for k in STRINGS),'metric string type drift')
        uints({k:v for k,v in m.items() if k not in STRINGS|set(NESTED)|{'channels'}},TOP-STRINGS-set(NESTED)-{'channels'})
        for key,fields in NESTED.items():uints(m[key],fields)
        require(m['event']=='command_metrics' and m['schema_version']==m['replay_schedule_version']==1 and m['replay_salt']=='3c6ef372','metrics version/salt drift')
        require(m['transaction']==ordinal and m['name']==t['name'] and m['kind']==t['kind'] and m['fabric']==fabric and m['read_lookahead']==lookahead,'metric owner/mode mismatch')
        require(m['completed']==int(t['status'] is not None) and (not m['completed'] or m['status']==t['status']),'metrics terminal status drift')
        require(m['command_cycles']==m['end_cycle']-m['start_cycle']+1,'metric accepted-to-done denominator drift')
        if m['completed']:require(m['command_cycles']==t['accepted_to_done_cycles'],'metric/trace command cycles mismatch')
        require(m['matrix_input_fires']==t['matrix_input_packets'],'metric/trace Matrix input count mismatch')
        require(sum(m['scheduler_stall_cycles'].values())==m['matrix_input_stall_cycles'],'context/fifo/array stall decomposition mismatch')
        require(m['matrix_input_ii']=={k:(0 if v is None else v) for k,v in t['input_ii'].items()},'metric/trace input timestamp II mismatch')
        if m['matrix_input_ii']['count']:require(m['matrix_input_ii']['min']>=5,'context0 II less than5')
        require(set(m['channels'])==set(CHANNELS),'metric channels drift')
        events=t['event_counts']
        for ch,name in enumerate(CHANNELS):
            c=m['channels'][name]
            uints({k:v for k,v in c.items() if k!='schedule_hash'},CHANNEL_KEYS-{'schedule_hash'})
            require(type(c['schedule_hash']) is str and re.fullmatch('[0-9a-f]{16}',c['schedule_hash']) is not None,'metric schedule hash malformed')
            req,rsp=(('descriptor_request','descriptor'),('dma','dma_ack'),('l2_read','l2_response'),('l2_write','l2_ack'))[ch]
            require(c['requests']==events.get(req,0) and c['responses']==events.get(rsp,0),'metric/trace channel event count mismatch')
            require(c['latency_count']==c['responses'] and 0<=c['requests']-c['responses']<=int(not m['completed']),'metric outstanding owner/count mismatch')
            require(c['pending_cycles']<=m['command_cycles'] and c['response_hold_cycles']<=c['pending_cycles'],'metric single-owner occupancy invalid')
            if m['completed']:require(c['latency_sum']==c['pending_cycles'],'metric pending occupancy/latency reconciliation mismatch')
            if ch==2:
                require({k:c['latency_'+k] for k in ('count','sum','max')}=={k:(0 if t['read_latency'][k] is None else t['read_latency'][k]) for k in ('count','sum','max')},'metric/trace read request-response latency mismatch')
            if fabric!='random':
                want=schedule(fabric,ch,c['requests'])
                require(all(c[k]==want[k] for k in ('admission_budget_sum','response_budget_sum','schedule_hash')),'transaction-indexed delay schedule drift')
                if ch==3:require(m['same_cycle_write_acks']==want['same_cycle_write_acks'],'indexed ACK replay mismatch')
        if lookahead==0:require(m['prefetch_accepts']==m['prefetch_occupancy_cycles']==0,'default unexpectedly prefetched')
        require(m['prefetch_accepts']<=m['matrix_input_fires'],'prefetch count exceeds Matrix work')
        require(sum(m['operand_wait_cycles'].values())+m['matrix_input_fires']+m['matrix_input_stall_cycles']<=m['command_cycles'],'payload state accounting exceeds command denominator')
        results.append(m)
    return results

def verify_pair_metrics(default,lookahead):
    require(len(default)==len(lookahead)==4,'causal primary command inventory mismatch')
    for a,b in zip(default,lookahead):
        for key in ('name','kind','fabric','replay_schedule_version','replay_salt','matrix_input_fires','completed','status'):
            require(a[key]==b[key],'A/B command or replay identity mismatch: '+key)
        require(a['read_lookahead']==0 and b['read_lookahead']==1 and a['fabric'] in ('unstalled','replay'),'not a causal A/B pair')
        for channel in CHANNELS:
            for key in ('requests','responses','admission_budget_sum','response_budget_sum','schedule_hash'):
                require(a['channels'][channel][key]==b['channels'][channel][key],'A/B injected delay schedule differs: '+channel+'/'+key)
    return True
