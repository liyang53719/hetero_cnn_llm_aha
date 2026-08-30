"""Unified operand-frontend reference for GGML Q8_0/Q6_K/Q3_K and FP16.

Storage-format-specific decode emits 16-value beats for one shared physical
dot-product array. Integer formats carry signed operands, one block FP16 scale,
and one signed subscale; FP16 uses the same multiplier fabric in floating mode.
This is E0/source contract, not llama.cpp parity, RTL E1, or mapped PPA.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import IntEnum
import hashlib, math, random, struct
from typing import Sequence

class StorageFormat(IntEnum):
    FP16=0; Q8_0=1; Q6_K=2; Q3_K=3
FORMAT_BYTES={StorageFormat.Q8_0:34,StorageFormat.Q6_K:210,StorageFormat.Q3_K:110}
FORMAT_VALUES={StorageFormat.Q8_0:32,StorageFormat.Q6_K:256,StorageFormat.Q3_K:256}
GROUP_VALUES=16; FP16_ONE=0x3C00

def _fp16(bits:int)->float:return struct.unpack('<e',int(bits&0xffff).to_bytes(2,'little'))[0]
def _fp16_bits(v:float)->int:return int.from_bytes(struct.pack('<e',float(v)),'little')
def _s8(v:int)->int:v&=0xff;return v-256 if v>=128 else v

def _q3_scale(payload:bytes,index:int)->int:
    if not 0<=index<16:raise ValueError('Q3_K scale index')
    s=payload[96:108]
    if len(s)!=12:raise ValueError('Q3_K scale payload')
    if index<4:j=index;lo=s[j]&15;hi=(s[8+j]>>4)&3
    elif index<8:j=index-4;lo=s[4+j]&15;hi=(s[8+j]>>6)&3
    elif index<12:j=index-8;lo=(s[j]>>4)&15;hi=s[8+j]&3
    else:j=index-12;lo=(s[4+j]>>4)&15;hi=(s[8+j]>>2)&3
    return ((hi<<4)|lo)-32

def _q6_quant(payload:bytes,index:int)->tuple[int,int]:
    half,rem=divmod(index,128);g,lane=divmod(rem,32);ql=half*64;qh=128+half*32;h=payload[qh+lane]
    if g==0:q=(payload[ql+lane]&15)|(((h>>0)&3)<<4)
    elif g==1:q=(payload[ql+lane+32]&15)|(((h>>2)&3)<<4)
    elif g==2:q=(payload[ql+lane]>>4)|(((h>>4)&3)<<4)
    else:q=(payload[ql+lane+32]>>4)|(((h>>6)&3)<<4)
    si=half*8+lane//16+2*g
    return q-32,_s8(payload[192+si])

def _q3_quant(payload:bytes,index:int)->tuple[int,int]:
    half,rem=divmod(index,128);g,lane=divmod(rem,32);packed=payload[32+half*32+lane];lo=(packed>>(2*g))&3
    q=lo if payload[lane]&(1<<(half*4+g)) else lo-4
    return q,_q3_scale(payload,half*8+lane//16+2*g)

@dataclass(frozen=True)
class OperandBeat:
    storage_format:StorageFormat;group_index:int;offset:int;valid_count:int
    integer_quants:tuple[int,...];fp16_bits:tuple[int,...]
    block_scale_fp16:int;subscale_s8:int;last:bool
    def __post_init__(self):
        if len(self.integer_quants)!=16 or len(self.fp16_bits)!=16:raise ValueError('beat width')
        if not 0<self.valid_count<=16:raise ValueError('valid count')
        if any(q<-128 or q>127 for q in self.integer_quants):raise ValueError('quant width')
        if not -128<=self.subscale_s8<=127:raise ValueError('subscale')
    @property
    def integer_mode(self)->bool:return self.storage_format is not StorageFormat.FP16
    def scaled_dot(self,activations:Sequence[float])->float:
        if len(activations)!=self.valid_count:raise ValueError('activation beat')
        if self.integer_mode:
            raw=sum(self.integer_quants[i]*float(activations[i]) for i in range(self.valid_count))
            return _fp16(self.block_scale_fp16)*self.subscale_s8*raw
        return sum(_fp16(self.fp16_bits[i])*float(activations[i]) for i in range(self.valid_count))

def decode_group(fmt:StorageFormat,payload:bytes,group_index:int,*,fp16_element_count:int|None=None)->OperandBeat:
    fmt=StorageFormat(fmt)
    if group_index<0:raise ValueError('group index')
    iq=[0]*16;fb=[0]*16
    if fmt is StorageFormat.FP16:
        if len(payload)%2:raise ValueError('FP16 alignment')
        count=len(payload)//2 if fp16_element_count is None else fp16_element_count
        if not 0<count<=len(payload)//2:raise ValueError('FP16 count')
        groups=math.ceil(count/16)
        if group_index>=groups:raise ValueError('FP16 group')
        off=group_index*16;valid=min(16,count-off)
        for lane in range(valid):fb[lane]=int.from_bytes(payload[2*(off+lane):2*(off+lane)+2],'little')
        return OperandBeat(fmt,group_index,off,valid,tuple(iq),tuple(fb),FP16_ONE,1,group_index+1==groups)
    if len(payload)!=FORMAT_BYTES[fmt]:raise ValueError(f'{fmt.name} block size')
    groups=FORMAT_VALUES[fmt]//16
    if group_index>=groups:raise ValueError('quant group')
    off=group_index*16
    if fmt is StorageFormat.Q8_0:
        for lane in range(16):iq[lane]=_s8(payload[2+off+lane])
        scale=int.from_bytes(payload[:2],'little');sub=1
    elif fmt is StorageFormat.Q6_K:
        ss=set()
        for lane in range(16):iq[lane],s=_q6_quant(payload,off+lane);ss.add(s)
        if len(ss)!=1:raise AssertionError('Q6 subscale')
        sub=ss.pop();scale=int.from_bytes(payload[208:210],'little')
    else:
        ss=set()
        for lane in range(16):iq[lane],s=_q3_quant(payload,off+lane);ss.add(s)
        if len(ss)!=1:raise AssertionError('Q3 subscale')
        sub=ss.pop();scale=int.from_bytes(payload[108:110],'little')
    return OperandBeat(fmt,group_index,off,16,tuple(iq),tuple(fb),scale,sub,group_index+1==groups)

def decode_block(fmt:StorageFormat,payload:bytes,*,fp16_element_count:int|None=None)->tuple[OperandBeat,...]:
    fmt=StorageFormat(fmt);count=(len(payload)//2 if fp16_element_count is None else fp16_element_count) if fmt is StorageFormat.FP16 else FORMAT_VALUES[fmt]
    groups=math.ceil(count/16)
    beats=tuple(decode_group(fmt,payload,i,fp16_element_count=fp16_element_count) for i in range(groups))
    if sum(b.last for b in beats)!=1 or not beats[-1].last:raise AssertionError('last')
    return beats

def frontend_dot(fmt:StorageFormat,payload:bytes,activations:Sequence[float],*,fp16_element_count:int|None=None)->float:
    beats=decode_block(fmt,payload,fp16_element_count=fp16_element_count)
    if sum(b.valid_count for b in beats)!=len(activations):raise ValueError('activation length')
    return sum(b.scaled_dot(activations[b.offset:b.offset+b.valid_count]) for b in beats)

def _reference_values(fmt:StorageFormat,payload:bytes,count:int|None=None)->tuple[float,...]:
    fmt=StorageFormat(fmt)
    if fmt is StorageFormat.FP16:
        v=tuple(_fp16(int.from_bytes(payload[i:i+2],'little')) for i in range(0,len(payload),2));return v if count is None else v[:count]
    if fmt is StorageFormat.Q8_0:
        d=_fp16(int.from_bytes(payload[:2],'little'));return tuple(d*_s8(x) for x in payload[2:34])
    d=_fp16(int.from_bytes(payload[208:210] if fmt is StorageFormat.Q6_K else payload[108:110],'little'));out=[]
    for i in range(256):q,s=_q6_quant(payload,i) if fmt is StorageFormat.Q6_K else _q3_quant(payload,i);out.append(d*s*q)
    return tuple(out)

def _random_payload(fmt:StorageFormat,rng:random.Random)->tuple[bytes,int|None]:
    if fmt is StorageFormat.FP16:
        n=rng.randint(1,97);return b''.join(struct.pack('<e',max(-16,min(16,rng.gauss(0,2)))) for _ in range(n)),n
    if fmt is StorageFormat.Q8_0:return _fp16_bits(rng.uniform(.0005,.25)).to_bytes(2,'little')+bytes(rng.randrange(256) for _ in range(32)),None
    size=FORMAT_BYTES[fmt];p=bytearray(rng.randrange(256) for _ in range(size));off=208 if fmt is StorageFormat.Q6_K else 108;p[off:off+2]=_fp16_bits(rng.uniform(.0001,.1)).to_bytes(2,'little');return bytes(p),None

def frontend_self_test(cases_per_format:int=1000,*,seed:int=0xF00D)->dict[str,object]:
    rng=random.Random(seed);mx=0.;digest=hashlib.sha256();beats={}
    for fmt in StorageFormat:
        total=0
        for case in range(cases_per_format):
            p,n=_random_payload(fmt,rng);ref=_reference_values(fmt,p,n);a=[math.sin((case+1)*(i+3)*.0007) for i in range(len(ref))]
            exp=sum(x*y for x,y in zip(ref,a));got=frontend_dot(fmt,p,a,fp16_element_count=n);mx=max(mx,abs(exp-got));bs=decode_block(fmt,p,fp16_element_count=n);total+=len(bs);digest.update(bytes([int(fmt)])+p+struct.pack('<d',got))
        beats[fmt.name]=total
    if mx>1e-9:raise AssertionError(mx)
    return {'schema_version':1,'status':'PASS','evidence_class':'unified_operand_frontend_E0_not_RTL_E1_or_llama_cpp_parity','cases_per_format':cases_per_format,'maximum_dot_difference':mx,'beat_counts':beats,'sha256':digest.hexdigest(),'contract':{'beat_values':16,'shared_integer_dot_lanes':True,'shared_fp_multiplier_array_mode':True,'format_specific_multiplier_array':False,'Q8_0_groups':2,'Q6_K_groups':16,'Q3_K_groups':16,'K_tail_supported_for_FP16':True,'integer_post_dot_scale':'FP16_block_scale_times_signed_subscale'},'remaining_local_gates':['RTL_group_decoder_E1','pinned_llama_cpp_10000_block_parity','shared_dot_array_integration_E1','1GHz_PPA']}
