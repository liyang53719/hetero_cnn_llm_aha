#!/usr/bin/env python3
import ctypes,hashlib,json,math,struct,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from heteronpu.hierarchical_attention import Summary,merge_rtl_pwl,f32
D=ROOT/'work/results/qwen2_q1024_full28_backend/layer5';OUT=ROOT/'work/results/qwen2_layer5_critical_summary';OUT.mkdir(parents=True,exist_ok=True);QUERY=848;HEAD=2;KVHEAD=0;DIM=128
lib=ctypes.CDLL('libm.so.6');fmaf=lib.fmaf;fmaf.argtypes=[ctypes.c_float]*3;fmaf.restype=ctypes.c_float
def bits(x):return struct.unpack('<I',struct.pack('<f',float(x)))[0]
def word(x):return struct.unpack('<f',struct.pack('<I',x))[0]
def add(a,b):return f32(f32(a)+f32(b))
def mul(a,b):return f32(f32(a)*f32(b))
def bf16(x):w=bits(x);return word((((w+0x7fff+((w>>16)&1))&0xffffffff)>>16)<<16)
def exp2p(x):
 x=f32(x)
 if x < -32:return 0.0
 if x >= 0:return 1.0
 i=max(0,min(511,math.floor(x*16)+512));x0=f32(i/16-32);x1=f32(x0+1/16);y0=f32(2**x0);y1=f32(2**x1);m=f32((float(y1)-float(y0))/(1/16));return add(mul(m,x),f32(float(y0)-float(m)*float(x0)))
def reduce32(values):
 values=list(values)+[0.0]*(32-len(values))
 while len(values)>1:values=[add(values[i],values[i+1])for i in range(0,len(values),2)]
 return values[0]
def bf(path,shape):x=np.fromfile(path,np.uint16).reshape(shape);return(x.astype(np.uint32)<<16).view(np.float32)
q=bf(D/'q_rope.bin',(1024,12,128));k=bf(D/'k_rope.bin',(1024,2,128));v=bf(D/'v_bias.bin',(1024,2,128));scale=word(0x3db504f3);log2e=word(0x3fb8aa3b);tiles=[]
for start in range(0,QUERY+1,32):
 end=min(QUERY+1,start+32);scores=[]
 for key in range(start,end):
  acc=0.0
  for d in range(DIM):acc=fmaf(float(q[QUERY,HEAD,d]),float(k[key,KVHEAD,d]),float(acc))
  scores.append(mul(acc,scale))
 m=max(scores);weights=[exp2p(mul(add(score,-m),log2e))for score in scores];l=reduce32(weights);o=[]
 for d in range(DIM):
  acc=0.0
  for i,w in enumerate(weights):acc=fmaf(float(bf16(w)),float(v[start+i,KVHEAD,d]),float(acc))
  for i,w in enumerate(weights):acc=fmaf(float(bf16(add(w,-bf16(w)))),float(v[start+i,KVHEAD,d]),float(acc))
  o.append(acc)
 tiles.append(Summary(m,l,tuple(o)))
blocks=[]
for start in range(0,len(tiles),4):
 values=tiles[start:start+4]
 while len(values)>1:values=[merge_rtl_pwl(values[i],values[i+1])if i+1<len(values)else values[i]for i in range(0,len(values),2)]
 blocks.append(values[0])
values=list(blocks)
while len(values)>1:values=[merge_rtl_pwl(values[i],values[i+1])if i+1<len(values)else values[i]for i in range(0,len(values),2)]
expected=values[0]
def write(path,lines):path.write_text('\n'.join(lines)+'\n');return hashlib.sha256(path.read_bytes()).hexdigest()
hashes={'headers':write(OUT/'headers.memh',[f'{bits(s.l):08x}{bits(s.m):08x}'for s in blocks]),'beats':write(OUT/'beats.memh',[f'{sum(bits(s.o[b*4+i])<<(32*i)for i in range(4)):032x}'for s in blocks for b in range(32)]),'expected_header':write(OUT/'expected_header.memh',[f'{bits(expected.l):08x}{bits(expected.m):08x}']),'expected_beats':write(OUT/'expected_beats.memh',[f'{sum(bits(expected.o[b*4+i])<<(32*i)for i in range(4)):032x}'for b in range(32)])}
r={'schema_version':1,'status':'PASS','layer':5,'query':QUERY,'q_head':HEAD,'kv_head':KVHEAD,'tiles':len(tiles),'blocks':len(blocks),'expected_merges':len(blocks)-1,'hashes':hashes};(OUT/'manifest.json').write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(f'QWEN2_LAYER5_CRITICAL_SUMMARY_VECTORS_PASS query={QUERY} head={HEAD} tiles={len(tiles)} blocks={len(blocks)} merges={len(blocks)-1}')
