"""Bounded ACK/phase wrapper around the frozen rectangular QK payload kernel.

One accepted operation/return at a time. Real byte-array writes happen on
matching successful commit ACKs. This is not the production Matrix service or
a cycle prediction. Input SRAM is explicitly a precommitted test fixture.
"""
from collections import Counter
import ctypes as C
from dataclasses import dataclass
import struct

from candidates.qwen2_exact_tree_scheduler.model import require
from candidates.qwen2_rectangular_qk_payload.model import Scratch, payload
from candidates.qwen2_resident_matrix.ffn_public.prefix_arithmetic import bf


@dataclass(frozen=True)
class Inputs:
    scratch: object
    tokens: int
    qbase: int
    rows: int


def fixture(q,k,*,qbase=0):
    tokens,rows=len(k),len(q)
    require(type(qbase) is int and 0<=qbase<tokens and qbase%16==0 and
            rows==min(16,tokens-qbase),'query tile/tail')
    require(all(len(row)==128 for row in (*q,*k)),'head dimension')
    require(all(type(x) is int and 0<=x<=0xffffffff for row in (*q,*k) for x in row),'FP32 words')
    s=Scratch(tokens)
    for name,data in (('q',q),('k',k)):
        for r,row in enumerate(data):
            for j,x in enumerate(row):s.put(name,r,j,bf(x))
    return Inputs(s,tokens,qbase,rows)


@dataclass(frozen=True)
class Tag:
    epoch: int
    tile: int
    sequence: int
    kind: str
    stripe: int = -1
    context: int = -1
    step: int = -1
    address: tuple = ()  # (bank group, bank, physical word, selected byte)


@dataclass(frozen=True)
class Request:
    tag: Tag
    data: object = None


class Phase:
    def __init__(self,lib,inputs,*,enabled=False,old_owners_idle=False,epoch=1,tile=0,debug=None):
        require(enabled and old_owners_idle,'default-off profile and exclusive ownership required')
        require(isinstance(inputs,Inputs),'explicit committed input fixture required')
        require(all(type(x) is int and 0<=x<1<<32 for x in (epoch,tile)),'epoch/tile')
        self.lib,self.inputs,self.s=lib,inputs,inputs.scratch
        self.epoch,self.tile,self.debug=epoch,tile,debug
        self.columns=((inputs.qbase+inputs.rows+31)//32)*32
        self.out=(C.c_uint32*4096)()  # the one existing finalValue
        self.slots=[None]*5
        self.contexts=[None]*5
        self.sequence=0
        self.offered=self.pending=self.return_value=None
        self.return_error=False
        self.poisoned=self.done=False
        self.stats=Counter()
        require(lib.reset()==0,'coordinated numeric fixture reset')
        self.stream=self._program()
        self._advance(None,initial=True)

    @property
    def drained(self):return self.pending is None

    def _advance(self,value,*,initial=False):
        try:
            kind,stripe,ctx,t,address,data=(next(self.stream) if initial else self.stream.send(value))
            tag=Tag(self.epoch,self.tile,self.sequence,kind,stripe,ctx,t,address)
            self.sequence+=1
            self.offered=Request(tag,data)
        except StopIteration:
            self.offered=None
            self.done=not self.poisoned

    def offer(self):
        return None if self.poisoned or self.pending is not None else self.offered

    def accept(self,request):
        require(not self.poisoned and self.pending is None and request==self.offered and
                request is not None,'admission identity/credit/poison')
        self.pending,self.offered=request,None
        self.return_value,self.return_error=self._execute(request)
        self.stats['issued:'+request.tag.kind]+=1

    def complete(self,tag,*,error=False):
        if self.pending is None or tag!=self.pending.tag:
            self.abort()
            raise ValueError('response epoch/tile/identity mismatch; original return must drain')
        request=self.pending
        value=self.return_value
        bad=error or self.return_error
        self.pending=self.return_value=None
        self.return_error=False
        if not bad and request.tag.kind in ('b_write','a_write'):
            group,bank,word,_=request.tag.address
            memory=self.s.a if group=='A' else self.s.b
            base=(bank*(1376 if group=='A' else 160)+word)*32
            memory[base:base+32]=request.data
            self.stats['physical_commit:'+request.tag.kind]+=1
        if self.poisoned or bad:
            self.abort()
            return
        self.stats['acked:'+request.tag.kind]+=1
        try:self._advance(value)
        except Exception:
            self.abort()
            raise

    def abort(self):
        self.poisoned,self.done=True,False
        self.offered=None
        # pending request/held return is retained, including an accepted B write.
        self.slots=[None]*5
        self.contexts=[None]*5

    def _execute(self,request):
        tag,data=request.tag,request.data
        if tag.kind=='group_begin':return None,self.lib.begin(data)!=0
        if tag.kind=='matrix':
            a,b,valid=data
            rc=self.lib.step(tag.context,tag.step,self.columns,(C.c_uint16*16)(*a),
                             (C.c_uint16*256)(*b),(C.c_uint32*16)(*valid),self.out)
            self.stats['enabled_cell_fmas']+=16*self.columns
            self.stats['fixed_4096_lane_capacity']+=4096
            self.stats['useful_fmas']+=sum(valid)
            return None,rc!=(1 if tag.step==7 else 0)
        if tag.kind in ('a_read','b_read'):
            group,bank,word,_=tag.address
            memory=self.s.a if group=='A' else self.s.b
            base=(bank*(1376 if group=='A' else 160)+word)*32
            return bytes(memory[base:base+32]),False
        if tag.kind=='scalar_add':
            out=C.c_uint32()
            rc=self.lib.scalar_add(data[0],data[1],C.byref(out))
            return out.value,rc!=0
        if tag.kind=='scalar_scale':
            out=(C.c_uint32*3)()
            rc=self.lib.post_dot(data,out)
            return tuple(out),rc!=0
        return None,False  # write response only commits on matching success

    def _event(self,kind,*,stripe=-1,ctx=-1,t=-1,address=(),data=None):
        return kind,stripe,ctx,t,address,data

    def _address(self,name,row,col):
        from scripts.qwen2_rectangular_attention_model import scratch_address
        return scratch_address(self.s.layout,name,row,col)

    def _read(self,name,row,col,*,stripe,ctx):
        address=self._address(name,row,col)
        block=yield self._event('a_read' if address[0]=='A' else 'b_read',
                               stripe=stripe,ctx=ctx,address=address)
        return struct.unpack_from('<I',block,address[3])[0]

    def _write_score(self,row,key,value,*,stripe,ctx):
        address=self._address('score',row,key)
        old=yield self._event('a_read',stripe=stripe,ctx=ctx,address=address)
        merged=bytearray(old)
        struct.pack_into('<I',merged,address[3],value)
        yield self._event('a_write',stripe=stripe,ctx=ctx,address=address,data=bytes(merged))

    def _program(self):
        qbase,rows,tokens=self.inputs.qbase,self.inputs.rows,self.inputs.tokens
        for sb in (0,5,10,15):
            count=min(5,16-sb)
            require(all(x is None for x in self.slots),'slot reuse before ordered fold/ACK')
            yield self._event('group_begin',stripe=sb,data=count)
            self.contexts=[sb+c if c<count else None for c in range(5)]
            for t in range(8):
                for ctx in range(count):
                    stripe=sb+ctx
                    operands=payload(self.s,qbase,rows,stripe,t,self.columns,tokens)
                    # The source input gathers are recorded work, not free ports.
                    self.stats['input_a_bank_word_reads']+=rows+min(tokens,self.columns)
                    yield self._event('matrix',stripe=stripe,ctx=ctx,t=t,data=operands)
                    if t==7:
                        for r in range(16):
                            for col in range(0,self.columns,8):
                                address=self._address('partial_or_pv_capture',ctx*16+r,col)
                                words=tuple(self.out[r*256+col+i] for i in range(8))
                                yield self._event('b_write',stripe=stripe,ctx=ctx,address=address,
                                                  data=struct.pack('<8I',*words))
                        self.slots[ctx]=stripe
                        self.contexts[ctx]=None
            yield self._event('group_done',stripe=sb)
            for ctx in range(count):
                stripe=sb+ctx
                require(self.slots[ctx]==stripe,'committed partial identity')
                for r in range(rows):
                    for key in range(qbase+r+1):
                        part=yield from self._read('partial_or_pv_capture',ctx*16+r,key,stripe=stripe,ctx=ctx)
                        if self.debug:self.debug('partial',(r,key,stripe),(part,))
                        prior=0 if stripe==0 else (yield from self._read('score',r,key,stripe=stripe,ctx=ctx))
                        value=yield self._event('scalar_add',stripe=stripe,ctx=ctx,data=(prior,part))
                        yield from self._write_score(r,key,value,stripe=stripe,ctx=ctx)
                self.slots[ctx]=None
        for r in range(rows):
            for key in range(qbase+r+1):
                total=yield from self._read('score',r,key,stripe=16,ctx=-1)
                post=yield self._event('scalar_scale',stripe=16,data=total)
                if self.debug:self.debug('dot_score',(r,key),(total,*post))
                yield from self._write_score(r,key,post[2],stripe=16,ctx=-1)
        yield self._event('owner_done')


def drain(e,limit=100000):
    for _ in range(limit):
        if e.done:return e
        require(not e.poisoned,'poisoned run cannot pass')
        req=e.offer()
        require(req is not None,'missing bounded request')
        e.accept(req);e.complete(req.tag)
    raise ValueError('unfinished/deadlock, not PASS')
