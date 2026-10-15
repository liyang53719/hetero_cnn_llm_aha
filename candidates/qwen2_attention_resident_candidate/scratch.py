"""Finite 256-KiB FP32 KV lease in the existing 16-bank 688-KiB A budget.

This is a new software route, not an existing connected Chisel cache port.
Each 64-byte access uses one 256-bit access on each of two distinct banks.
The route has one outstanding request and a held response/consume ACK.
"""
from builtins import ValueError
from dataclasses import dataclass
from collections import Counter
import struct

BANKS,DEPTH,WORD_BYTES=16,1376,32
CACHE_LINES=4096

class CacheFault(ValueError):pass

def need(ok,message):
    if not ok:raise CacheFault(message)

def natural(x):return type(x) is int and 0<=x<1<<64

@dataclass(frozen=True)
class ReadonlyKVIdentity:
    allocation_k:int
    allocation_v:int
    producer_k:int
    producer_v:int
    def validate(self):
        need(all(natural(x) for x in (self.allocation_k,self.allocation_v,self.producer_k,self.producer_v)), 'KV allocation/generation domain')

@dataclass(frozen=True)
class LocalRequest:
    epoch:int
    serial:int
    address:int
    line:int
    data:bytes|None=None
    @property
    def write(self):return self.data is not None

@dataclass(frozen=True)
class LocalResponse:
    epoch:int
    serial:int
    address:int
    line:int
    data:bytes|None
    nbytes:int=64

class SharedAScratch:
    def __init__(self):
        self.storage=bytearray(BANKS*DEPTH*WORD_BYTES)
        self.valid=bytearray(CACHE_LINES//8)
        self.owner=None;self.epoch=0;self.binding=None;self.identity=None
        self.pending=None;self.held=None;self.ready_at=0;self.clock=0
        self.revoked=False;self.counts=Counter();self.accepted_at=0;self.last_serial=0
    @staticmethod
    def cells(line):
        need(type(line) is int and 0<=line<CACHE_LINES,'fixed cache line range')
        return ((2*(line%8),line//8),(2*(line%8)+1,line//8))
    @staticmethod
    def offset(bank,word):return (bank*DEPTH+word)*WORD_BYTES
    def acquire(self,owner,job,identity):
        need(type(identity) is ReadonlyKVIdentity,'explicit readonly allocation/generation identity')
        identity.validate()
        need(self.owner is None and self.pending is None and self.held is None,'A lease or local debt busy')
        need(type(job.m) is int and 1<=job.m<=128,'resident capacity M1..128')
        size=job.m*1024;extent=job.m*6144
        need(natural(job.tag) and job.tag<1<<32 and job.write_bytes==extent,'job tag/output extent')
        spans=((job.b,size),(job.c,size),(job.dst,extent))
        need(all(natural(a) and a%64==0 and a+n<=1<<64 for a,n in spans),'aligned nonoverflowing lease spans')
        need(all(a+na<=b or b+nb<=a for i,(a,na) in enumerate(spans) for b,nb in spans[:i]),'KV/output lease alias')
        self.epoch+=1;need(self.epoch<1<<64,'cache epoch exhausted')
        self.owner=owner;self.identity=identity
        self.binding=(job.tag,job.b,job.c,job.m*256*4,job.m,job.dst,job.write_bytes)
        self.valid[:]=bytes(len(self.valid));self.revoked=False;self.counts=Counter(leases=1);self.last_serial=0
    def reserve_external(self,owner):
        need(self.owner is None and self.pending is None,'A already leased')
        self.owner=owner;self.binding=None;self.identity=None
    def release_external(self,owner):
        need(self.owner is owner and self.binding is None and self.pending is None,'external lease mismatch/debt')
        self.owner=None
    def check(self,owner):
        need(self.owner is owner and self.binding is not None and not self.revoked,'resident lease revoked or not owned')
    def line(self,address):
        need(self.binding is not None and type(address) is int and address%64==0,'aligned bound cache address')
        _,k,v,size,*_=self.binding
        if k<=address<k+size:return (address-k)//64
        if v<=address<v+size:return 2048+(address-v)//64
        return None
    def present(self,line):return bool(self.valid[line//8]&(1<<(line%8)))
    def make_request(self,owner,address,serial,data=None):
        self.check(owner);line=self.line(address)
        need(line is not None and natural(serial),'cache request identity')
        need(data is None or type(data) is bytes and len(data)==64,'raw 64-byte fill')
        need(not self.present(line) if data is not None else self.present(line),'fill/hit validity')
        return LocalRequest(self.epoch,serial,address,line,data)
    def accept(self,owner,request):
        self.check(owner);need(type(request) is LocalRequest,'typed local request')
        need(all(natural(x) for x in (request.epoch,request.serial,request.address,request.line)), 'canonical nonbool local identity')
        need(request.address%64==0 and request.line<CACHE_LINES,'canonical local address/line')
        need(request.data is None or type(request.data) is bytes and len(request.data)==64,'canonical raw fill packet')
        need(self.pending is None and self.held is None,'one outstanding local request')
        need(request.epoch==self.epoch and request.line==self.line(request.address),'request binding drift')
        need(request.serial>self.last_serial,'stale/replayed local request serial')
        need(request.write!=self.present(request.line),'cache fill/read validity drift')
        cells=self.cells(request.line);data=bytearray()
        for i,(bank,word) in enumerate(cells):
            at=self.offset(bank,word)
            if request.write:self.storage[at:at+32]=request.data[i*32:(i+1)*32]
            else:data.extend(self.storage[at:at+32])
        self.pending=request;self.last_serial=request.serial;self.accepted_at=self.clock;self.ready_at=self.clock+1
        self.held=LocalResponse(request.epoch,request.serial,request.address,request.line,None if request.write else bytes(data))
        self.counts['fill_requests' if request.write else 'read_requests']+=1
        self.counts['bank_write_accesses' if request.write else 'bank_read_accesses']+=2
    def response(self):return self.held if self.held is not None and self.clock>=self.ready_at else None
    def consume(self,owner,*,abort=False):
        need(self.owner is owner and self.response() is not None,'local response not ready/owned')
        request,response=self.pending,self.held
        need(self.clock>self.accepted_at,'cache access has positive response latency')
        if request.write and not abort and not self.revoked:
            self.valid[request.line//8]|=1<<(request.line%8);self.counts['fill_commits']+=1
        self.counts['consume_acks']+=1;self.counts['response_latency_edges']+=self.clock-self.accepted_at
        self.pending=self.held=None
        return response
    def revoke(self):
        self.revoked=True;self.valid[:]=bytes(len(self.valid));self.counts['revocations']+=1
    def notify_write(self,address,nbytes):
        need(type(address) is int and type(nbytes) is int and nbytes>0,'write notification')
        if self.binding is not None:
            _,k,v,size,*_=self.binding
            if any(address<base+size and base<address+nbytes for base in (k,v)):self.revoke()
    def producer_changed(self,identity):
        need(type(identity) is ReadonlyKVIdentity,'producer identity type');identity.validate()
        if self.binding is not None and identity!=self.identity:self.revoke()
    def release(self,owner):
        need(self.owner is owner and self.pending is None and self.held is None,'release before consume ACK')
        self.valid[:]=bytes(len(self.valid));self.owner=self.binding=self.identity=None
    def report(self):
        return dict(capacity_bytes=len(self.storage),kv_reserved_bytes=262144,valid_metadata_bytes=len(self.valid),
          local_packet_bytes=64,outstanding_limit=1,bank_word_bits=256,banks_per_packet=2,
          minimum_response_edges=1,counts=dict(self.counts),outstanding=int(self.pending is not None),
          valid_lines=sum(x.bit_count() for x in self.valid),epoch=self.epoch,
          route='NEW_SOFTWARE_A_LEASE_NOT_CONNECTED_CHISEL',model_edges_are_hardware_cycles=False)
