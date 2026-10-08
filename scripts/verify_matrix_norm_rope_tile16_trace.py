#!/usr/bin/env python3
"""Independent fail-closed full512-lane tile16 event/counter consumer.

Every arithmetic lane and raw fabric store is checked against source-bound
integer/C vectors. Accepted command to done cycles retain all waiting and
serial Norm/RoPE time; this candidate-only interval is never a fullblock metric.
"""
from __future__ import annotations
from collections import Counter, OrderedDict, deque
from contextlib import nullcontext
import gzip
import json
from os import PathLike
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from verify_matrix_norm_rope_tensor_trace import REJECTS as OLD_REJECTS, SCHEMA as OLD_SCHEMA, _descriptors
from verify_matrix_norm_rope_trace import (BASE_FIELDS,L2_BYTES,STRING_FIELDS,_hex,_packed,_unique_object,
    require,head_trace,bf16_convert,pair_trace)
REJECTS={**OLD_REJECTS,'tile16_requires_tensor_mode':4,'tile16_packed_full_stride_bounds':5,
         'tile16_packed_tail_alias':5,'tile16_future_trig_activation_alias':5,'tile16_last_row_norm_alias':5}
MAIN=(('cold_Q',0,0,0,16),('cold_K',8,1,0,16),('carried_Q',160,0,112,16),('carried_K',168,1,112,16))
SCHEMA={k:set(v) for k,v in OLD_SCHEMA.items()}
SCHEMA['accepted_start']={'cycle'}
SCHEMA['head_begin']|={'row'}; SCHEMA['head_done']|={'row'}
SCHEMA['projection_begin']={'cycle','head','batch_start','rows'}
SCHEMA['projection_done']=SCHEMA['projection_begin']|{'matrix_inputs','matrix_outputs','write_acks'}
SCHEMA['matrix']={'cycle','head','batch_start','rows','tile','index','last','context','fp32_rows'}
SCHEMA['matrix_input']={'cycle','head','batch_start','rows','tile','index','last','context','clear','a','b'}
SCHEMA['terminal']|={'ddr_read_bytes','ddr_write_bytes','matrix_steps','command_cycles'}
STRINGS=STRING_FIELDS|{'fp32_rows','a','b'}


def _stats():return {'count':0,'sum':0,'min':None,'max':None}


def _sample(stats,value):
    stats['count']+=1;stats['sum']+=value
    stats['min']=value if stats['min'] is None else min(stats['min'],value)
    stats['max']=value if stats['max'] is None else max(stats['max'],value)


def _record(line):
    require(line.endswith('\n'),'truncated trace record')
    r=json.loads(line,object_pairs_hook=_unique_object)
    require(type(r) is dict and type(r.get('event')) is str,'bad trace event')
    event=r['event'];require(event in SCHEMA,'unknown trace event: '+event)
    require(set(r)==SCHEMA[event]|{'event','transaction'},'trace field inventory drift: '+event)
    for key,value in r.items():
        if key in STRINGS or(key=='kind' and event=='begin'):
            require(type(value) is str,'trace string type drift: '+key)
        else:require(type(value) is int and value>=0,'trace integer type/range drift: '+key)
    if 'error' in r:require(r['error'] in (0,1),'invalid error bit')
    return r


def _case_id(role,token,head):
    require(role in (0,1) and 0<=head<(8 if role==0 else 2),'head/role identity drift')
    if token==16 and role==1:return 320+head
    require(token in tuple(range(16))+tuple(range(112,128)),'token oracle identity drift')
    return (token if token<16 else token-96)*10+(0 if role==0 else 8)+head


def load_case(root,case_id,weights):
    require(type(case_id) is int and 0<=case_id<322,'case identity drift')
    p=Path(root)/f'case{case_id}';columns=512 if case_id<320 and case_id%10<8 else 256
    role=0 if columns==512 else 1;head=case_id%10 if role==0 else (case_id%10-8 if case_id<320 else case_id-320)
    schema={'projected_fp32':(columns,8),'projected':(columns,4),'norm':(256,4),'rope':(256,4),
            'activation':(1024,4),'norm_weight':(256,4),'trig':(64,4)}
    values={}
    for name,(count,digits) in schema.items():
        raw=(p/(name+'.memh')).read_text();lines=raw.splitlines()
        require(raw.endswith('\n') and len(lines)==count,'vector extent drift: '+name)
        values[name]=np.asarray([_hex(word,digits) for word in lines],dtype=np.uint32)
    key=(role,head)
    if key not in weights:
        raw=(p/'weight.memh').read_text();lines=raw.splitlines()
        require(raw.endswith('\n') and len(lines)==1024*columns,'weight extent drift')
        weights[key]=np.asarray([_hex(word,4) for word in lines],dtype=np.uint16)
    values['weight']=weights[key]
    require((p/'projected_steps.bin').stat().st_size==1024*columns*4,'binary steps extent drift')
    values['steps']=np.memmap(p/'projected_steps.bin',dtype='<u4',mode='r',shape=(1024*columns//32,32))
    values['columns']=columns
    final=values['steps'][1023::1024].reshape(-1)
    require(np.array_equal(final,values['projected_fp32']),'final sequential-FMA link drift')
    require([bf16_convert(int(v))[0]>>16 for v in final]==values['projected'].tolist(),'BF16 conversion drift')
    n=head_trace(tuple(int(v)<<16 for v in values['projected'][:256]),tuple(int(v)<<16 for v in values['norm_weight']))
    require([v>>16 for v in n['output_bf16']]==values['norm'].tolist(),'Norm arithmetic drift')
    values['norm_trace']=n;r=list(n['output_bf16']);values['rope_flags']=0
    for i in range(32):
        result=pair_trace(r[i],r[i+32],int(values['trig'][i])<<16,int(values['trig'][i+32])<<16)
        r[i],r[i+32]=result[20:22];values['rope_flags']|=result[24]
    require([v>>16 for v in r]==values['rope'].tolist(),'RoPE arithmetic drift')
    return values


class Cases:
    def __init__(self,root):self.root=root;self.cache=OrderedDict();self.weights={}
    def __getitem__(self,key):
        if key not in self.cache:
            self.cache[key]=load_case(self.root,key,self.weights)
            if len(self.cache)>40:self.cache.popitem(last=False)
        self.cache.move_to_end(key)
        return self.cache[key]


def _suite_sequence(suite):
    require(suite in ('main','negative','fault','reset','boundary','tail','all'),'unknown trace suite')
    result=[]
    if suite in ('main','all'):result.extend(('main',name,case) for name,case,*_ in MAIN)
    if suite in ('negative','all'):result.extend(('reject',name,8) for name in REJECTS)
    if suite in ('fault','all'):
        result.extend(('fault',name,8) for name in ('last_row_last_head_DMA_error','token_count128_admitted'))
        result.append(('recovery','recovery_after_fault_or_reset',8))
    if suite in ('reset','all'):
        result.extend(('reset',name,8) for name in ('reset_late_row','reset_late_head'))
        result.append(('recovery','recovery_after_fault_or_reset',8))
    if suite in ('boundary','all'):result.append(('boundary','legal_exact_1p5MiB_end',8))
    if suite in ('tail','all'):result.extend(('main','tail_'+str(n),8) for n in (1,3,17))
    return result


def _bases(start,boundary):
    out=dict(zip(BASE_FIELDS,(0x40000,0x60000,0x80000,0x2000,0x3000+start*128,0x10000,0x20000)))
    if boundary:out.update(packed_base=L2_BYTES-8192,norm_base=L2_BYTES-9216,rope_base=L2_BYTES-8704)
    return out


def _dma_plan(b):
    n=b['token_count'];heads,tiles=(8,16) if b['role']==0 else (2,8)
    ps,ns=(8192,4096) if b['role']==0 else (1024,1024)
    nd,rd=((1<<56)-2048,(1<<56)-1024) if b['kind']=='boundary' else (0x400000000,0x500000000)
    result=[]
    for batch in range(b['start_token'],b['start_token']+n,16):
        rows=min(16,b['start_token']+n-batch)
        for row in range(rows):
            result.append(('act',batch,row,0,(1,0x100000000+(batch+row)*2048,b['act_base']+row*2,2,1024,2,64)))
        for head in range(heads):
            for tile in range(tiles):
                result.append(('weight',batch,head,tile,(1,0x200000000+head*tiles*64+tile*64,b['wgt_base'],64,1024,ps,64)))
                result.append(('packed',batch,head,tile,(3,b['packed_base']+tile*1024,0x300000000+batch*ps+head*tiles*64+tile*64,64,rows,64,ps)))
            for row in range(rows):
                for name,local,ddr in [('norm','norm_base',nd),('rope','rope_base',rd)]:
                    result.append((name,batch,head,row,(3,b[local],ddr+(batch+row)*ns+head*512,64,8,64,64)))
    return result


class Transaction:
    def __init__(self,b,cases,*,require_inputs=False):
        require(type(require_inputs) is bool,'require_inputs must be boolean')
        # Old lossless output-only traces remain readable explicitly. Once an
        # input event is observed, inputs are mandatory for this transaction;
        # a partial/mixed input inventory can never fall back to legacy mode.
        self.input_mode=True if require_inputs else None
        self.operands={5:None,6:None};self.read_owner=None
        self.input_queue=deque();self.last_input_cycle=-1
        self.first_input_cycle=None;self.input_ii=_stats();self.read_latency=_stats()
        self.b=b;self.cases=cases;self.kind=b['kind'];self.name=b['name'];self.role=b['role']
        self.heads,self.tiles=(8,16) if self.role==0 else (2,8)
        self.pending=dict.fromkeys(('descriptor','dma','read','write'))
        self.counts=Counter();self.local=Counter();self.writes=Counter();self.acks=Counter()
        self.errors=[];self.done=None;self.started=None;self.p=None;self.row=None;self.event_cycles={}
        self.projections=0;self.completed_heads=0;self.completed_tokens=0;self.flags=0
        self.act_rows={};self.weight_tile=-1;self.dma_beats=0;self.read_bytes=0;self.write_bytes=0
        self.descriptors=_descriptors(self.role,self.name)
        self.desc_limit={'bad_command':0,'malformed_descriptor':1,'unsupported_FP32_output':5}.get(self.name,6)
        self.status=REJECTS[self.name] if self.kind=='reject' else 6 if self.kind=='fault' else 0
        require(self.role in (0,1) and b['checking']==1,'disabled arithmetic/role drift')
        require(all(b[k]==v for k,v in _bases(b['start_token'],self.kind=='boundary').items()),'staging base drift')
        if self.name in [x[0] for x in MAIN]:
            expected=next(x for x in MAIN if x[0]==self.name)
            require(self.kind=='main' and (b['case'],self.role,b['start_token'],b['token_count'])==expected[1:],'main geometry drift')
        else:
            n=int(self.name[5:]) if self.name.startswith('tail_') else 128 if self.name=='token_count128_admitted' else 16 if self.kind in ('fault','reset') else 1
            require(b['case']==8 and self.role==1 and b['start_token']==0 and b['token_count']==n,'auxiliary geometry drift')
        self.plan=_dma_plan(b)

    def idle(self):require(all(v is None for v in self.pending.values()),'advance before owner response/ACK')
    def case(self,token,head):return self.cases[_case_id(self.role,token,head)]
    def error(self,event,index,r):
        wanted=self.kind=='fault' and event=='dma_ack' and index==(0 if self.name=='token_count128_admitted' else 111)
        require(r['error']==int(wanted),'missing/spurious/misrouted error')
        if wanted:self.errors.append((event,index))
    def matrix_owner(self):
        require(self.p is not None and self.row is None,'Matrix outside projection')
        require(all(self.pending[k] is None for k in ('descriptor','dma','write')),
                'Matrix before non-read owner response/ACK')
    def read_admission(self,r,reg,tile,k):
        if self.input_mode is not True or tile is None:return
        i=tile*1024+k;n=self.local['matrix_input']
        if reg==5:
            require(i==n or (i==n+1 and i//1024==n//1024),
                    'Matrix activation lookahead order/tile boundary')
            if i==n+1:
                require(all(self.operands[p] is not None and self.operands[p]['index']==n
                            for p in (5,6)), 'activation lookahead before current operands')
                require(r['cycle']>self.operands[6]['cycle'],'activation lookahead before weight response')
        else:
            a=self.operands[5]
            require(i==n and a is not None and a['index']==i and self.operands[6] is None,
                    'Matrix weight before activation response/input release')
            require(r['cycle']>a['cycle'],'Matrix weight before activation response')
    def read_coord(self,index):
        if index<self.tiles*2048:
            tile,step=divmod(index,2048);k,part=divmod(step,2)
            return 5+part,self.b['act_base' if part==0 else 'wgt_base']+k*64,tile,k,None
        offset=index-self.tiles*2048;row,offset=divmod(offset,self.tiles+18)
        require(row<self.p['rows'],'extra row read')
        for region,count,base in ((0,self.tiles,'packed_base'),(3,8,'gamma_base'),(1,8,'norm_base'),(4,2,'trig_base')):
            if offset<count:
                address=self.b[base]+(offset*1024+row*64 if region==0 else offset*64)
                if region==4:address+=(self.p['batch_start']+row-self.b['start_token'])*128
                return region,address,None,offset*32,row
            offset-=count
        raise ValueError('extra L2 read')
    def write_coord(self,index):
        if index<self.tiles*self.p['rows']:
            tile,row=divmod(index,self.p['rows']);return 0,self.b['packed_base']+tile*1024+row*64,tile*32,row
        row,offset=divmod(index-self.tiles*self.p['rows'],16)
        require(row<self.p['rows'],'extra row write');region=1 if offset<8 else 2
        offset%=8;return region,self.b['norm_base' if region==1 else 'rope_base']+offset*64,offset*32,row
    def consume(self,r):
        event=r['event']
        if 'cycle' in r:
            require(r['cycle']>self.event_cycles.get(event,-1),'multiple transfers on one channel/cycle')
            self.event_cycles[event]=r['cycle']
        require(self.done is None or event=='terminal','activity after done')
        require(not self.errors or event in ('done','terminal'),'activity after fatal error')
        if self.kind=='reject':require(event in ('accepted_start','descriptor_request','descriptor','done','terminal'),'reject side effects')
        if event=='accepted_start':
            require(self.started is None and not self.counts,'duplicate/late start');self.started=r['cycle']
        else:require(self.started is not None,'traffic before accepted start')
        if event=='projection_begin':
            self.idle();require(self.p is None,'overlapping projection')
            batch=self.b['start_token']+(self.projections//self.heads)*16;head=self.projections%self.heads
            rows=min(16,self.b['start_token']+self.b['token_count']-batch)
            require(rows>0 and (r['head'],r['batch_start'],r['rows'])==(head,batch,rows),'projection identity/order drift')
            require(all(self.act_rows.get(row)==batch+row for row in range(rows)),'projection before activation ACKs')
            self.p=r;self.local=Counter();self.writes=Counter();self.acks=Counter();self.weight_tile=-1
            self.operands={5:None,6:None};self.input_queue.clear()
        elif event=='projection_done':
            self.idle();require(self.p is not None and self.row is None,'projection done without owner')
            require(all(r[k]==self.p[k] for k in ('head','batch_start','rows')),'projection done identity')
            rows=self.p['rows'];want=self.tiles*1024
            require(r['matrix_inputs']==r['matrix_outputs']==self.local['matrix']==want,'projection Matrix count')
            if self.input_mode is True:
                require(self.local['matrix_input']==want and not self.input_queue and
                        all(v is None for v in self.operands.values()),'projection Matrix input inventory')
            require(r['write_acks']==self.local['l2_write']==self.local['l2_ack']==rows*(self.tiles+16),'projection ACK count')
            require(self.local['head_done']==rows and self.local['norm']==rows and self.local['l2_read']==self.local['l2_response']==2*want+rows*(self.tiles+18),'projection row/transport count')
            require(self.local['dma']==self.local['dma_ack']==2*self.tiles+2*rows,'projection DMA count')
            self.projections+=1;self.p=None
        elif event=='head_begin':
            self.idle();require(self.p is not None and self.row is None,'overlapping head row')
            row=self.local['head_done'];token=self.p['batch_start']+row;head=self.p['head']
            require(row<self.p['rows'] and (r['case'],r['head'],r['token'],r['row'])==(_case_id(self.role,token,head),head,token,row),'row identity/order drift')
            require(self.local['matrix']==self.tiles*1024 and self.acks[0]==self.tiles*self.p['rows'],'head row before projection ACKs')
            self.row=r
        elif event=='head_done':
            self.idle();require(self.row is not None and all(r[k]==self.row[k] for k in ('case','head','token','row')),'head done identity')
            rows=self.local['head_done']+1
            require(self.acks[1]==self.acks[2]==rows*8 and self.local['norm']==rows,'head before complete Norm/RoPE ACKs')
            require(self.local['dma_ack']==2*self.tiles+rows*2,'head before final DDR ACK')
            require(r['flags']==self.flags,'head flags mismatch');self.completed_heads+=1
            if self.row['head']==self.heads-1 and rows==self.p['rows']:self.completed_tokens+=rows
            self.row=None
        elif event=='descriptor_request':
            self.idle();index=self.counts[event]+1
            require(index<=self.desc_limit and r['index']==index,'descriptor order/count');self.pending['descriptor']=r
        elif event=='descriptor':
            q=self.pending['descriptor'];require(q is not None and r['index']==q['index'],'descriptor owner')
            require(r['cycle']>q['cycle'],'descriptor response before request')
            require(_hex(r['data'],32)==self.descriptors[r['index']-1],'descriptor bytes drift')
            self.error(event,r['index'],r);self.pending['descriptor']=None
        elif event=='dma':
            self.idle();index=self.counts[event]
            require(index<len(self.plan) and r['index']==index and self.counts['descriptor']==6,'DMA count/order/snapshot')
            name,batch,head,offset,want=self.plan[index]
            got=(r['kind'],_hex(r['source'],16),_hex(r['destination'],16),r['row_bytes'],r['rows'],r['source_stride'],r['destination_stride'])
            require(got==want,'DMA address/geometry mismatch')
            if name=='act':require(self.p is None,'activation reuse overwritten before projection completion')
            else:
                require(self.p is not None and (self.p['batch_start'],self.p['head'])==(batch,head),'DMA projection owner')
                if name=='weight':require(self.local['matrix']==offset*1024 and self.acks[0]==offset*self.p['rows'],'weight before previous tile ACK')
                elif name=='packed':require(self.local['matrix']==(offset+1)*1024 and self.acks[0]==(offset+1)*self.p['rows'],'DDR packed store before allproducer ACKs')
                else:
                    require(self.row is not None and self.row['row']==offset,'DDR store row owner')
                    require(self.acks[1 if name=='norm' else 2]==(offset+1)*8,'DDR store before Norm/RoPE ACK')
            self.pending['dma']=r;self.dma_beats=0
        elif event=='dma_data':
            q=self.pending['dma'];require(q is not None and q['kind']==3 and r['index']==q['index'],'DMA data owner')
            name,batch,head,offset,want=self.plan[q['index']];beat=self.dma_beats
            require(beat<q['rows'] and _hex(r['source'],16)==want[1]+beat*want[5] and _hex(r['destination'],16)==want[2]+beat*want[6],'DMA data geometry/order')
            ex=self.case(batch+beat if name=='packed' else batch+offset,head)
            name2,off=('projected',offset*32) if name=='packed' else (name,beat*32)
            require(_hex(r['data'],128)==_packed(ex[name2][off:off+32]),'raw fabric DDR store data mismatch');self.dma_beats+=1
        elif event=='dma_ack':
            q=self.pending['dma'];require(q is not None and r['index']==q['index'],'DMA ACK owner')
            require(r['cycle']>q['cycle'],'DMA response before request')
            self.error(event,r['index'],r);name,batch,head,offset,want=self.plan[q['index']]
            if not r['error']:
                require(self.dma_beats==(q['rows'] if q['kind']==3 else 0),'DMA ACK incomplete data')
                if q['kind']==3:self.write_bytes+=q['rows']*q['row_bytes']
                else:self.read_bytes+=q['rows']*q['row_bytes']
                if name=='act':self.act_rows[head]=batch+head
                if name=='weight':self.weight_tile=offset
            self.pending['dma']=None
        elif event=='l2_read':
            self.idle();require(self.p is not None,'L2 read outside projection')
            reg,address,tile,k,row=self.read_coord(self.local[event])
            require(r['region']==reg and r['byte_address']==address and 0<=address<=L2_BYTES-64 and address%64==0,'L2 read order/address/aperture')
            if tile is not None:require(self.weight_tile==tile,'Matrix before weight ACK')
            else:
                require(self.row is not None and self.row['row']==row,'L2 read row owner')
                if reg in (1,4):require(self.acks[1]==(row+1)*8,'RoPE before Norm ACKs')
            self.read_admission(r,reg,tile,k)
            self.pending['read']=r;self.read_owner=(reg,address,tile,k,row)
        elif event=='l2_response':
            q=self.pending['read'];require(q is not None and r['byte_address']==q['byte_address'],'L2 response owner')
            require(r['cycle']>q['cycle'],'L2 response before request')
            _sample(self.read_latency,r['cycle']-q['cycle'])
            reg,address,tile,offset,row=self.read_coord(self.local[event])
            require(self.read_owner==(reg,address,tile,offset,row) and q['region']==reg,
                    'L2 response coordinate owner')
            if tile is not None and self.input_mode is True:
                require(tile*1024+offset==self.local['matrix_input'] and self.operands[reg] is None,
                        'Matrix response overwrites unconsumed operands')
                require(r['cycle']>self.last_input_cycle,'Matrix response before input release')
            if reg==5:
                beat=address//64;raw=bytearray((0xa5^((beat*17+b*13)&255)) for b in range(64))
                for lane,token in self.act_rows.items():raw[lane*2:lane*2+2]=int(self.case(token,0)['activation'][offset]).to_bytes(2,'little')
                want=int.from_bytes(raw,'little')
            elif reg==6:
                ex=self.case(self.p['batch_start'],self.p['head']);start=offset*ex['columns']+tile*32
                want=_packed(ex['weight'][start:start+32])
            else:
                ex=self.case(self.p['batch_start']+row,self.p['head']);name={0:'projected',1:'norm',3:'norm_weight',4:'trig'}[reg]
                want=_packed(ex[name][offset:offset+32])
            require(_hex(r['data'],128)==want,'independent L2 source/producer mismatch')
            if tile is not None:
                self.operands[reg]={'index':tile*1024+offset,'data':want,'cycle':r['cycle']}
            self.error(event,reg,r);self.pending['read']=None;self.read_owner=None
        elif event=='matrix_input':
            self.matrix_owner();require(self.input_mode is not False,'mixed legacy/actual Matrix inputs')
            self.input_mode=True;i=self.local[event];k=i%1024
            require(i<self.tiles*1024 and r['index']==i and r['tile']==i//1024 and
                    r['context']==0 and r['clear']==int(k==0) and r['last']==int(k==1023),
                    'Matrix input order/context/clear/last')
            require(all(r[key]==self.p[key] for key in ('head','batch_start','rows')),
                    'Matrix input projection identity')
            require(self.weight_tile==i//1024 and all(self.operands[p] is not None and
                    self.operands[p]['index']==i for p in (5,6)), 'Matrix input before operand responses')
            require(all(r['cycle']>self.operands[p]['cycle'] for p in (5,6)),
                    'Matrix input before registered operand responses')
            if k:
                require(r['cycle']-self.last_input_cycle>=5,'Matrix input violates context recurrence II')
                _sample(self.input_ii,r['cycle']-self.last_input_cycle)
            rows=self.p['rows'];head=self.p['head'];batch=self.p['batch_start']
            a=_packed([self.case(batch+row,head)['activation'][k] if row<rows else 0 for row in range(16)])
            ex=self.case(batch,head);offset=k*ex['columns']+(i//1024)*32
            b=_packed(ex['weight'][offset:offset+32])
            require(_hex(r['a'],64)==a and _hex(r['b'],128)==b,
                    'independent Matrix input operand mismatch')
            require((self.operands[5]['data']&((1<<(rows*16))-1))==a and self.operands[6]['data']==b,
                    'Matrix input operand response binding')
            if self.pending['read'] is not None:
                reg,_,tile,offset,_=self.read_owner
                require(reg==5 and tile==i//1024 and tile*1024+offset==i+1,
                        'Matrix input pending lookahead owner')
            if self.first_input_cycle is None:self.first_input_cycle=r['cycle']
            self.operands={5:None,6:None};self.last_input_cycle=r['cycle'];self.input_queue.append(r['cycle'])
        elif event=='matrix':
            require(self.p is not None,'Matrix outside projection');i=self.local[event]
            require(i<self.tiles*1024 and r['index']==i and r['tile']==i//1024 and r['context']==0 and r['last']==int(i%1024==1023),'Matrix order/context/last')
            require(all(r[k]==self.p[k] for k in ('head','batch_start','rows')),'Matrix projection identity')
            require(self.weight_tile==i//1024 and self.local['l2_response']>=2*(i+1),'Matrix before operands')
            if self.input_mode is None:self.input_mode=False
            if self.input_mode is True:
                self.matrix_owner()
                require(self.local['matrix_input']>i and self.input_queue,'Matrix output before actual input')
                require(r['cycle']>self.input_queue[0],'Matrix output before input pipeline latency')
                self.input_queue.popleft()
            actual=_hex(r['fp32_rows'],4096);rows=self.p['rows']
            for row in range(16):
                got=(actual>>(row*1024))&((1<<1024)-1)
                want=_packed(self.case(self.p['batch_start']+row,self.p['head'])['steps'][i],4) if row<rows else 0
                require(got==want,'independent sequential-FMA active/inactive row mismatch')
        elif event=='norm':
            self.idle();require(self.row is not None,'Norm without row');row=self.row['row'];ex=self.cases[self.row['case']];n=ex['norm_trace']
            require(self.local[event]==row and self.local['l2_response']==self.tiles*2048+row*(self.tiles+18)+self.tiles+8,'duplicate/premature Norm')
            require(r['status']==0 and _hex(r['mean_eps'],8)==n['mean_eps'] and _hex(r['inv'],8)==n['inverse'] and r['flags']==n['aggregate_flags'],'Norm intermediate/status/flags')
            require(_hex(r['norm'],1024)==_packed(ex['norm']),'Norm result mismatch')
            require(_hex(r['gate'],1024)==(_packed(ex['projected'][256:]) if self.role==0 else 0),'raw Q/K gate mismatch')
            self.flags|=n['aggregate_flags']
        elif event=='l2_write':
            self.idle();require(self.p is not None,'L2 write outside projection')
            reg,address,offset,row=self.write_coord(self.local[event]);ex=self.case(self.p['batch_start']+row,self.p['head'])
            name=('projected','norm','rope')[reg]
            require(r['region']==reg and r['byte_address']==address and 0<=address<=L2_BYTES-64 and address%64==0,'producer write order/address/aperture')
            require(_hex(r['mask'],16)==(1<<64)-1 and _hex(r['data'],128)==_packed(ex[name][offset:offset+32]),'producer mask/data mismatch')
            if reg==0:require(self.local['matrix']==(offset//32+1)*1024,'packed before Matrix final')
            else:
                require(self.row is not None and self.row['row']==row and self.local['norm']==row+1,'Norm/RoPE write without row result')
                if reg==2:require(self.local['l2_response']==self.tiles*2048+(row+1)*(self.tiles+18),'RoPE before inputs')
            self.writes[reg]+=1;self.pending['write']=r
        elif event=='l2_ack':
            q=self.pending['write'];require(q is not None and r['byte_address']==q['byte_address'],'L2 ACK owner')
            require(r['cycle']>=q['cycle'],'L2 ACK before request')
            self.error(event,q['region'],r);self.acks[q['region']]+=1;self.pending['write']=None
            if q['region']==2 and self.acks[2]%8==0:self.flags|=self.cases[self.row['case']]['rope_flags']
        elif event=='done':
            require(self.kind!='reset','reset completed before target');self.idle()
            require(r['status']==self.status and self.counts['descriptor']==self.desc_limit,'done status/descriptor inventory')
            require(self.counts['l2_read']==self.counts['l2_response'] and self.counts['l2_write']==self.counts['l2_ack'] and self.counts['dma']==self.counts['dma_ack'],'done before all ACKs')
            require(len(self.errors)==int(self.kind=='fault'),'missing expected fault')
            if self.input_mode is True:
                require(self.counts['matrix_input']==self.counts['matrix'] and not self.input_queue,
                        'done before Matrix input/output drain')
            if not self.status:require(self.p is None and self.completed_heads==self.heads*self.b['token_count'] and self.completed_tokens==self.b['token_count'] and self.counts['dma']==len(self.plan),'missing complete successful inventory')
            require(r['cycle']-self.started+1>=5*self.counts['matrix'],'impossible serial payload issue-cycle budget')
            self.done=r
        elif event=='terminal':
            require(self.done is not None and r['status']==self.done['status'],'terminal without actual done')
            require(r['command_cycles']==self.done['cycle']-self.started+1,'accepted-to-done cycle denominator drift')
            require(r['matrix_inputs']==r['matrix_outputs']==r['matrix_steps']==self.counts['matrix'] and r['dma_count']==self.counts['dma'] and r['write_requests']==self.counts['l2_write'] and r['write_acks']==self.counts['l2_ack'],'terminal counters differ from events')
            if self.input_mode is True:require(r['matrix_inputs']==self.counts['matrix_input'],'terminal Matrix input inventory')
            require(r['completed_heads']==self.completed_heads and r['completed_tokens']==self.completed_tokens,'terminal completion counters')
            require(r['ddr_read_bytes']==self.read_bytes and r['ddr_write_bytes']==self.write_bytes,'terminal successful DDR ACK bytes')
            require(r['total_tiles']==(self.heads*self.tiles if self.counts['dma'] else 0) and r['flags']==self.flags,'terminal shape/flags')
        elif event=='reset_flush':
            require(self.kind=='reset' and self.row is not None,'unsolicited reset')
            head=0 if self.name=='reset_late_row' else 1;q=self.pending['dma']
            require(r['stage']==head and self.row['head']==head and self.row['row']==15 and self.completed_heads==head*16+15 and self.completed_tokens==0 and q is not None and q['index']==(63 if head==0 else 111) and _hex(q['source'],16)==self.b['rope_base'],'reset target/owner not reached')
        self.counts[event]+=1
        if self.p is not None or event=='projection_done':self.local[event]+=1


def verify_trace(path,vectors,*,suite='main',required_main=None,require_inputs=False):
    """Verify a filename or caller-owned iterable text stream through EOF.

    Set require_inputs=True for new runs. The explicit default preserves the
    historical output-only trace format without claiming checked input fires.
    """
    require(type(require_inputs) is bool,'require_inputs must be boolean')
    sequence=_suite_sequence(suite);inventory=Counter(sequence);expected_main=4 if suite in ('main','all') else 0
    require(required_main is None or(type(required_main) is int and required_main==expected_main),'required_main cannot weaken suite')
    cases=Cases(vectors);active=None;seen=0;previous_cycle=-1;counts=Counter();completed=Counter();terminals=[]
    opener=gzip.open if str(path).endswith('.gz') else open
    with opener(path,'rt') if isinstance(path,(str,bytes,PathLike)) else nullcontext(path) as f:
        for lineno,line in enumerate(f,1):
            try:
                r=_record(line);event=r['event']
                if 'cycle' in r:require(r['cycle']>=previous_cycle,'trace time went backwards');previous_cycle=r['cycle']
                if event=='begin':
                    require(active is None and r['transaction']==seen+1,'unterminated/duplicate transaction')
                    key=(r['kind'],r['name'],r['case']);require(seen<len(sequence) and key==sequence[seen],'suite identity/order drift')
                    active=Transaction(r,cases,require_inputs=require_inputs);seen+=1
                else:
                    require(active is not None and r['transaction']==active.b['transaction'],'event wrong/outside transaction')
                    active.consume(r)
                    if event in ('terminal','reset_flush'):
                        completed[(active.kind,active.name,active.b['case'])]+=1
                        item={'kind':active.kind,'name':active.name,'case':active.b['case'],'status':r.get('status'),
                              'matrix_packets':active.counts['matrix'],'completed_heads':active.completed_heads,
                              'matrix_input_packets':active.counts['matrix_input'],
                              'event_counts':dict(active.counts),'input_ii':dict(active.input_ii),
                              'read_latency':dict(active.read_latency),'first_input_cycle':active.first_input_cycle,
                              'last_input_cycle':active.last_input_cycle if active.last_input_cycle>=0 else None,
                              'completed_tokens':active.completed_tokens,'ddr_read_bytes':active.read_bytes,'ddr_write_bytes':active.write_bytes}
                        if active.done is not None:
                            cycles=active.done['cycle']-active.started+1;require(cycles>0,'invalid command cycle interval')
                            item.update(accepted_to_done_cycles=cycles,fixed_matrix_lanes=512)
                            if active.status==0:
                                useful=active.b['token_count']*active.heads*active.tiles*1024*32
                                item.update(useful_fma=useful,candidate_useful_wall_fraction=useful/(512*cycles),whole_block_metric=False)
                        terminals.append(item);active=None
                counts[event]+=1
            except (ValueError,KeyError,TypeError,IndexError) as exc:raise ValueError(f'trace line {lineno}: {exc}') from exc
    require(active is None and completed==inventory,'missing complete suite inventory')
    return {'suite':suite,'events':dict(counts),'transactions':seen,'primary_commands':expected_main,
            'bitexact_matrix_packets':counts['matrix'],'matrix_lanes_checked_per_packet':512,'terminals':terminals,
            'require_inputs':require_inputs,'bitexact_matrix_input_packets':counts['matrix_input'],
            'actual_matrix_inputs_checked':require_inputs or counts['matrix_input']==counts['matrix']>0,
            'missing_extra_reordered_oracle_values':0,'actual_done_before_ack_checked':True,
            'raw_fabric_ddr_store_data_checked':True,'cumulative_arithmetic_flags_checked':True,
            'fabric_guard_readback_in_trace':False,'whole_block_MAC90_claimed':False}
