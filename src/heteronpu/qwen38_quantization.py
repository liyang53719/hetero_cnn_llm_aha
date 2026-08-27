"""Synthetic numerical-format screening for recurrent and sparse states.

This rejects risky storage formats before RTL implementation; it is not a
substitute for official-weight accuracy or perplexity evaluation.
"""
from __future__ import annotations
from dataclasses import dataclass
import bisect,math,random,struct
from typing import Callable,Sequence
from .qwen38_qsa_streaming import QSAIndexConfig,f32,reference_select
def bf16(value:float)->float:
    bits=struct.unpack("<I",struct.pack("<f",f32(value)))[0]
    if bits&0x7f800000==0x7f800000:return f32(value)
    rounded=bits+0x7fff+((bits>>16)&1);return struct.unpack("<f",struct.pack("<I",rounded&0xffff0000))[0]
def fp16(value:float)->float:return f32(struct.unpack("<e",struct.pack("<e",max(-65504.0,min(65504.0,float(value)))))[0])
def _fp8_values()->tuple[float,...]:
    values={0.0};bias=7
    for sign in (-1.0,1.0):
        for mantissa in range(1,8):values.add(sign*mantissa/8.0*2.0**(1-bias))
        for exponent in range(1,15):
            for mantissa in range(8):values.add(sign*(1.0+mantissa/8.0)*2.0**(exponent-bias))
        for mantissa in range(7):values.add(sign*(1.0+mantissa/8.0)*2.0**(15-bias))
    return tuple(sorted(f32(v) for v in values))
_FP8=_fp8_values()
def fp8_e4m3fn(value:float)->float:
    value=f32(value)
    if math.isnan(value):return value
    if value<=_FP8[0]:return _FP8[0]
    if value>=_FP8[-1]:return _FP8[-1]
    i=bisect.bisect_left(_FP8,value);lo,hi=_FP8[i-1],_FP8[i];return lo if abs(value-lo)<=abs(hi-value) else hi
def int8_vector(values:Sequence[float])->tuple[float,...]:
    peak=max((abs(float(v)) for v in values),default=0.0)
    if peak==0:return tuple(0.0 for _ in values)
    scale=peak/127.0;return tuple(f32(max(-127,min(127,round(float(v)/scale)))*scale) for v in values)
@dataclass(frozen=True)
class Format:
    name:str;scalar:Callable[[float],float]|None
    def vector(self,values:Sequence[float])->tuple[float,...]:
        if self.name=="int8_per_vector":return int8_vector(values)
        assert self.scalar is not None;return tuple(self.scalar(v) for v in values)
FORMATS=(Format("fp32",f32),Format("bf16",bf16),Format("fp16",fp16),Format("fp8_e4m3fn",fp8_e4m3fn),Format("int8_per_vector",None))
def error(reference:Sequence[float],actual:Sequence[float])->dict[str,float]:
    diff=[abs(float(a)-float(b)) for a,b in zip(reference,actual,strict=True)];rn=math.sqrt(sum(float(v)**2 for v in reference));en=math.sqrt(sum(v*v for v in diff));return {"max_abs":max(diff,default=0.0),"mean_abs":sum(diff)/len(diff) if diff else 0.0,"relative_l2":en/max(rn,1e-12)}
def gdn_state_drift(fmt:Format,steps:int=512,width:int=128,seed:int=3812)->dict[str,object]:
    rng=random.Random(seed);reference=[f32(rng.uniform(-.05,.05)) for _ in range(width)];tested=list(reference)
    for _ in range(steps):
        decay=f32(math.exp(-rng.uniform(.001,.08)));key=[f32(rng.uniform(-.2,.2)) for _ in range(width)];value=f32(rng.uniform(-.2,.2));reference=[f32(f32(decay*old)+f32(k*value)) for old,k in zip(reference,key,strict=True)];tested=list(fmt.vector([f32(f32(decay*old)+f32(k*value)) for old,k in zip(tested,key,strict=True)]))
    return {"format":fmt.name,"steps":steps,**error(reference,tested)}
def qsa_selection_screen(fmt:Format,cases:int=200,seed:int=3813)->dict[str,object]:
    rng=random.Random(seed);exact=0;jaccard=0.0
    for _ in range(cases):
        cfg=QSAIndexConfig(16,4,4,32,8,16);length=rng.randrange(33,257);keys=[tuple(f32(rng.gauss(0,.5)) for _ in range(16)) for _ in range(length)];queries=tuple(tuple(f32(rng.gauss(0,.5)) for _ in range(16)) for _ in range(4));ref=reference_select(cfg,queries,keys,length-1);actual=reference_select(cfg,tuple(fmt.vector(q) for q in queries),[fmt.vector(k) for k in keys],length-1);exact+=int(actual==ref);lhs,rhs=set(ref),set(actual);jaccard+=len(lhs&rhs)/len(lhs|rhs) if lhs|rhs else 1.0
    return {"format":fmt.name,"cases":cases,"exact_order_rate":exact/cases,"mean_selected_token_jaccard":jaccard/cases}
def ple_gate_screen(fmt:Format,cases:int=256,width:int=160,seed:int=3814)->dict[str,object]:
    rng=random.Random(seed);reference=[];tested=[]
    for _ in range(cases):
        row=[f32(rng.gauss(0,.08)) for _ in range(width)];query=[f32(rng.gauss(0,.15)) for _ in range(width)];reference.append(f32(sum(f32(x*y) for x,y in zip(row,query,strict=True))/math.sqrt(width)));qrow,qquery=fmt.vector(row),fmt.vector(query);tested.append(f32(sum(f32(x*y) for x,y in zip(qrow,qquery,strict=True))/math.sqrt(width)))
    return {"format":fmt.name,"cases":cases,**error(reference,tested)}
def quantization_screen_report()->dict[str,object]:
    formats={fmt.name:{"gdn_state":gdn_state_drift(fmt),"qsa_selection":qsa_selection_screen(fmt),"ple_gate":ple_gate_screen(fmt)} for fmt in FORMATS}
    return {"schema_version":1,"status":"PASS","evidence_class":"synthetic_format_screen_not_model_accuracy","formats":formats,"decision_rules":{"state_format_requires_official_trace":True,"qsa_format_requires_selected_token_stability":True,"fp32_state_is_reference":True,"mixed_dtype_gather_dequant_required":True}}
