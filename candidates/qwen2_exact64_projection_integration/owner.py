"""Accepted-byte exact64 diagnostic projection owner, bounded serial storage.

This owner does not implement MatrixStream/Chisel scheduling. All arithmetic
operands come from consumed MemoryResponse bytes. Public integration reserves
(but never pretends to execute arithmetic on) the original shared Matrix.
"""
from collections import Counter
import struct
from .kernel import Exact64Kernel, need
from candidates.qwen2_resident_matrix.ffn_public.prefix_owners import (
    MemoryRequest, MemoryResponse, OwnerResult, FULL_MASK, LIMIT)

def uint(x,bits):return type(x) is int and 0<=x<1<<bits

class Exact64ProjectionOwner:
    def __init__(self,kernel,*,max_rows=128):
        need(type(kernel) is Exact64Kernel,'actual exact64 native kernel')
        need(type(max_rows) is int and 1<=max_rows<=128,'bounded row domain')
        self.kernel,self.max_rows=kernel,max_rows
        self.state='idle';self.poison=False;self.job=None;self.request=self.result=self.program=None
        self.clock=self.start_clock=self.serial=self.ack_bytes=0;self.counts=Counter()
        self.status=self.detail=None;self.row=bytearray(6144);self.weights=bytearray(128)
        self.peak_row_bytes=0;self.baseline=dict(fmas=0,adds=0);self.tiles_acked=0
    def ports(self):
        return dict(job_ready=self.state=='idle' and not self.poison and self.kernel.state=='idle',
          memory=self.request if self.state=='issue' else None,
          memory_response_ready=self.state in ('wait','drain'),
          response=self.result if self.state=='finish' else None,
          reset_required=self.poison,state=self.state)
    def validate(self,j):
        c=getattr(j,'c',0)  # Original public Dense Job has no third operand.
        need(j.kind=='Dense' and uint(j.tag,32) and type(j.m) is int and 1<=j.m<=self.max_rows and
          type(j.n) is int and j.n in (256,1536) and type(j.k) is int and j.k==1536,'exact Q/K projection geometry')
        need(j.weight_bf16 is True and j.activation_bf16 is False and j.output_bf16 is False and
          type(c) is int and c==0,'raw F32 output / BF16 weight public dtype')
        need(type(j.write_bytes) is int and j.write_bytes==j.m*j.n*4,'exact output extent')
        spans=((j.a,j.m*1536*4),(j.b,1536*j.n*2),(j.dst,j.write_bytes))
        need(all(uint(a,64) and a%64==0 and a+n<=LIMIT for a,n in spans),'aligned bounded address spans')
        need(all(not (a<j.dst+j.write_bytes and j.dst<a+n) for a,n in spans[:2]),'destination aliases operands')
    def _program(self,j):
        for m in range(j.m):
            for offset in range(0,6144,64):
                data=yield j.a+m*6144+offset,None
                self.row[offset:offset+64]=data
            self.peak_row_bytes=6144
            del data
            # Input remains raw materialized BF16 F32; no new rounding.
            need(all((v&0xffff)==0 and (v&0x7f800000)!=0x7f800000 for (v,) in struct.iter_unpack('<I',self.row)),
                 'finite materialized BF16 n0 row')
            for nb in range(0,j.n,64):
                tile=(j.tag,m,nb);self.kernel.begin(tile)
                for k in range(1536):
                    at=j.b+(k*j.n+nb)*2
                    self.weights[:64]=yield at,None
                    self.weights[64:]=yield at+64,None
                    self.kernel.push(k,struct.unpack_from('<I',self.row,k*4)[0],bytes(self.weights))
                output=self.kernel.finish()
                for offset in range(0,256,64):
                    yield j.dst+(m*j.n+nb)*4+offset,output[offset:offset+64]
                # Generator resumes only after the fourth successful physical ACK.
                self.kernel.retire(tile);self.tiles_acked+=1
                del output
    def _finish(self,status=None,detail=None):
        self.status,self.detail=status,detail;self.poison|=status is not None
        if status is not None:self.kernel.abort()
        self.request=self.program=None
        actual=self.kernel.report()['fmas']-self.baseline['fmas']
        self.result=OwnerResult(self.job.tag,status,self.ack_bytes,self.clock-self.start_clock,actual,actual)
        self.state='finish'
    def _advance(self,data=None):
        try:
            address,payload=self.program.send(data)
            need(self.serial<1<<32,'request sequence exhausted')
            self.request=MemoryRequest(address,(self.job.tag<<32)|self.serial,payload is not None,payload,
                FULL_MASK if payload is not None else 0)
            self.serial+=1;self.state='issue'
        except StopIteration:
            expected=self.job.m*self.job.n*1536
            if self.ack_bytes!=self.job.write_bytes or self.kernel.report()['fmas']-self.baseline['fmas']!=expected:
                self._finish('Protocol','terminal before output ACK/arithmetic coverage')
            else:self._finish()
        except ValueError as e:self._finish('Numerical',str(e))
    def tick(self,*,job=None,memory_ready=False,memory_response=None,response_ready=False,abort=False):
        need(all(type(v) is bool for v in (memory_ready,response_ready,abort)),'canonical handshake bits')
        p=self.ports();p.update(job_fire=False,memory_fire=False,memory_response_fire=False,response_fire=False)
        self.clock+=1
        if abort:
            self.poison=True;p['job_ready']=False;p['memory']=None
            if self.state in ('wait','drain'):
                self.state='drain';self.status='Protocol';self.detail='abort with accepted memory debt'
                self.kernel.abort()
            elif self.job is not None and self.state not in ('idle','locked'):
                self._finish('Protocol','abort before owner terminal');p['response']=None
            else:self.state='locked';self.kernel.abort()
        if not abort and job is not None and p['job_ready']:
            p['job_fire']=True;self.job=job;self.start_clock=self.clock
            self.serial=self.ack_bytes=self.tiles_acked=0;self.counts=Counter(job_fire=1)
            self.baseline={k:self.kernel.report()[k] for k in ('fmas','adds')}
            try:self.validate(job);self.program=self._program(job);self._advance()
            except (ValueError,AttributeError) as e:self._finish('Bounds',str(e))
        if not abort and p['memory'] is not None and memory_ready:
            p['memory_fire']=True;self.state='wait'
            self.counts['write_requests' if self.request.write else 'read_requests']+=1
        if p['memory_response_ready'] and memory_response is not None:
            q=self.request;r=memory_response
            # A foreign/malformed tag does not retire the accepted request.
            # Poison and wait for its matching response; do not erase debt.
            match=type(r) is MemoryResponse and uint(r.tag,64) and r.tag==q.tag
            if not match:
                self.poison=True;self.state='drain';self.status='Protocol'
                self.detail='foreign response; original accepted debt retained'
                self.kernel.abort();self.counts['foreign_response_rejected']+=1
            else:
                p['memory_response_fire']=True;self.counts['responses']+=1
                valid=type(r.nbytes) is int and r.nbytes==64 and type(r.error) is bool
                status='Protocol' if not valid else 'Memory' if r.error else None
                if status is None and q.write and r.data is not None:status='Protocol'
                if status is None and not q.write and (type(r.data) is not bytes or len(r.data)!=64):status='Protocol'
                if status is None and q.write:self.ack_bytes+=64;self.counts['write_acks']+=1
                if self.state=='drain':self._finish(self.status,self.detail)
                elif status is not None:self._finish(status,'response type/extent/error')
                else:
                    if not q.write:self.counts['read_responses']+=1
                    self._advance(None if q.write else r.data)
        if p['response'] is not None and response_ready and not abort:
            p['response_fire']=True;self.counts['owner_results']+=1
            self.state='locked' if self.poison else 'idle';self.result=None
        return p
    def report(self):
        current=self.kernel.report()
        return dict(scope='DIAGNOSTIC_SOFTWARE_OWNER',hardware_mapping='NOT_IMPLEMENTED',performance='NO_GO',
          status=self.status,accepted=dict(self.counts),write_bytes=self.ack_bytes,
          kernel_delta={k:current[k]-self.baseline[k] for k in ('fmas','adds')},kernel=current,
          tiles_output_acked=self.tiles_acked,memory=dict(read_bytes=self.counts['read_responses']*64,
          write_bytes=self.ack_bytes,read_requests=self.counts['read_requests'],write_requests=self.counts['write_requests'],acks=self.counts['write_acks']),
          payload_capacity=dict(partial=16384,n0_row=6144,weight_tile=128,sealed_output=256,
              transient_weight_bytes=128,transient_native_weight=128,transient_native_output=256,request_response_hold=128,
              conservative_total=23552),peak_row_bytes=self.peak_row_bytes,model_ticks_are_hardware_cycles=False)
