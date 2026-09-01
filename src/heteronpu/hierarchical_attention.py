"""FP32 online-softmax and universal block-128 reference models."""
from __future__ import annotations
from dataclasses import dataclass
import math, struct
from typing import Sequence
from .fp32_exp2_ext32_pwl_table import EXP2_PWL_COEFF

def f32(x: float) -> float:return struct.unpack('<f',struct.pack('<f',float(x)))[0]
LOG2E=f32(math.log2(math.e))
@dataclass(frozen=True)
class Summary:
    m:float;l:float;o:tuple[float,...]
    def __post_init__(self):object.__setattr__(self,'m',f32(self.m));object.__setattr__(self,'l',f32(self.l));object.__setattr__(self,'o',tuple(f32(x) for x in self.o))
    @classmethod
    def empty(cls,lanes):
        if lanes<0:raise ValueError('lanes')
        return cls(float('-inf'),0.0,(0.0,)*lanes)
    @property
    def is_empty(self):return self.l==0.0
def exp2_pwl_rtl(x):
    x=f32(x)
    if math.isnan(x) or x<-32.0:return 0.0
    if x>=0.0:return 1.0
    idx=math.floor(x*16.0)+512;coeff=EXP2_PWL_COEFF[idx];m=struct.unpack('<f',struct.pack('<I',coeff>>32))[0];b=struct.unpack('<f',struct.pack('<I',coeff&0xffffffff))[0];return f32(f32(m*x)+b)
def exp_rtl(x):return exp2_pwl_rtl(f32(f32(x)*LOG2E))
def _update(s,score,value,exp_fn):
    if len(value)!=len(s.o):raise ValueError('width')
    score=f32(score)
    if s.is_empty:return Summary(score,1.0,tuple(value))
    m=f32(max(s.m,score));a=f32(exp_fn(f32(s.m-m)));b=f32(exp_fn(f32(score-m)))
    return Summary(m,f32(f32(s.l*a)+b),tuple(f32(f32(x*a)+f32(y*b)) for x,y in zip(s.o,value,strict=True)))
def update(s,score,value):return _update(s,score,value,math.exp)
def update_rtl(s,score,value):return _update(s,score,value,exp_rtl)
def _merge(a,b,exp_fn):
    if len(a.o)!=len(b.o):raise ValueError('width')
    if a.is_empty:return b
    if b.is_empty:return a
    m=f32(max(a.m,b.m));aa=f32(exp_fn(f32(a.m-m)));bb=f32(exp_fn(f32(b.m-m)))
    return Summary(m,f32(f32(a.l*aa)+f32(b.l*bb)),tuple(f32(f32(x*aa)+f32(y*bb)) for x,y in zip(a.o,b.o,strict=True)))
def merge(a,b):return _merge(a,b,math.exp)
def merge_rtl_pwl(a,b):return _merge(a,b,exp_rtl)
def summarize(scores,values,rtl=False):
    if len(scores)!=len(values):raise ValueError('length')
    s=Summary.empty(len(values[0]) if values else 0);fn=update_rtl if rtl else update
    for score,value in zip(scores,values,strict=True):s=fn(s,score,value)
    return s
def blockwise(scores,values,block_size=128,rtl=False):
    if block_size<=0:raise ValueError('block_size')
    result=Summary.empty(len(values[0]) if values else 0);mf=merge_rtl_pwl if rtl else merge
    for i in range(0,len(scores),block_size):result=mf(result,summarize(scores[i:i+block_size],values[i:i+block_size],rtl))
    return result
def normalized(s):
    if s.is_empty:raise ValueError('empty')
    return tuple(f32(x/s.l) for x in s.o)
def causal_merge_count(sequence,heads,block_size=128):
    if min(sequence,heads)<0 or block_size<=0:raise ValueError('arguments')
    return heads*sum(i//block_size for i in range(sequence))
@dataclass(frozen=True)
class BlockedAttentionGeometry:
    sequence:int;heads:int;head_dim:int;q_tile:int=16;k_tile:int=32;block_tokens:int=128
    @property
    def score_tile_bytes(self):return self.q_tile*self.k_tile*4
    @property
    def summary_merges(self):return causal_merge_count(self.sequence,self.heads,self.block_tokens)
    @property
    def live_set_bytes(self):
        summary=(self.head_dim+2)*4
        return self.q_tile*self.head_dim*2+2*self.k_tile*self.head_dim*2+self.score_tile_bytes+self.q_tile*self.k_tile*2+2*self.q_tile*summary
