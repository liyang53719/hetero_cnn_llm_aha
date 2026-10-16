"""Opt-in original-owner generator: tagged physical IO and explicit scratch edges.

M1/M2 preparation only. The 96-word panel and input packet registers remain
proposed resources. There is no full Public profile admission in this slice.
"""
from .protocol import ScratchAction
from .client import PackedRequest,PackedConsumerAck
from ..ffn_attention.scalar_recipe import exp_negative
from ..ffn_public.prefix_owners import PrefixFault

class PackedSchedule:
    def __init__(self):self.serial=0;self.generation=0;self.owner=None
    def bind(self,owner):
        if self.owner is not None and self.owner is not owner:raise ValueError("packed schedule belongs to another owner")
        self.owner=owner
    def scratch(self,op,generation,query,kv_head,line=0,words=()):
        if self.serial==0xffffffff:raise PrefixFault("Protocol","scratch serial exhausted")
        self.serial+=1
        return ScratchAction(self.serial,op,generation,query,kv_head,line,tuple(words))
    def run(self,o,j):
        if j.m not in (1,2):raise PrefixFault('Bounds','packed preparation supports M1/M2 only')
        yield self.scratch('acquire',0,0,0)
        for token in range(j.m):
            for kv in range(2):
                self.generation+=1;generation=self.generation
                yield self.scratch('begin',generation,token,kv)
                maxima=[0xff800000]*6
                for h in range(6):
                    head=kv*6+h;q=[]
                    for d in range(0,128,16):q.extend((yield from o._read(j.a+(token*1536+head*128+d)*4)))
                    o.row_words=128;o.peak_row_words=max(o.peak_row_words,128)
                    for d in range(0,128,16):
                        b=[0]*256
                        for key in range(token+1):
                            words=yield from o._read(j.b+(key*256+kv*128+d)*4)
                            b[16*key:16*key+16]=[o._op('bf',x)>>16 for x in words]
                        final=d==112
                        result=yield PackedRequest(0x23,tuple(o._op('bf',x)>>16 for x in q[d:d+16]),tuple(b),d==0,final,8,255,
                            tuple((r,16*k+r) for k in range(token+1) for r in range(16)) if final else ())
                    lanes=result.selected_words();scores=[]
                    for key in range(token+1):
                        total=0
                        for x in lanes[key*16:(key+1)*16]:total=o._op('add',total,x)
                        score=o._op('bf',o._op('mul',o._op('bf',total),0x3db504f3));scores.append(score)
                        if o._less(maxima[h],score):maxima[h]=score
                    o.useful_macs+=(token+1)*128
                    yield self.scratch('write',generation,token,kv,4096+8*h,tuple(scores)+(0,)*(16-len(scores)))
                    yield PackedConsumerAck(result.tag)
                inverses=[]
                for h in range(6):
                    scores=(yield self.scratch('read',generation,token,kv,4096+8*h)).words
                    weights=[];total=0
                    for score in scores[:token+1]:
                        weight=exp_negative(o.scalar,o,o._op('add',score,maxima[h]^0x80000000));o.counts['exp_negative_requests']+=1
                        weights.append(weight);total=o._op('add',total,weight)
                    yield self.scratch('write',generation,token,kv,4144+8*h,tuple(weights)+(0,)*(16-len(weights)))
                    inverses.append(o._op('div',0x3f800000,total))
                panel=[]
                for h in range(6):panel.append((yield self.scratch('read',generation,token,kv,4144+8*h)).words)
                for key in range(token+1):
                    a=tuple(o._op('bf',o._op('mul',panel[h][key],inverses[h]))>>16 for h in range(6))+(0,)*10
                    b=[]
                    for d in range(0,128,16):b.extend((yield from o._read(j.c+(key*256+kv*128+d)*4)))
                    final=key==token
                    result=yield PackedRequest(0x24,a,tuple(o._op('bf',x)>>16 for x in b)+(0,)*128,key==0,final,token+1,15,
                        tuple((h,c) for h in range(6) for c in range(128)) if final else ())
                # Check every selected final cell before the first output write.
                result.check_selected()
                for h in range(6):
                    for d in range(0,128,16):
                        words=tuple(o._op('bf',result.value[h][c]) for c in range(d,d+16))
                        yield from o._write(j.dst+(token*1536+(kv*6+h)*128+d)*4,words)
                o.useful_macs+=6*(token+1)*128
                yield PackedConsumerAck(result.tag)
                o.row_words=0
        yield self.scratch('release',self.generation,j.m-1,1)
