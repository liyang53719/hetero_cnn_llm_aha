#!/usr/bin/env python3
import json,math,struct
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];SRC=ROOT/'work/results/qwen2_canonical_q_tile16_all';OUT=ROOT/'work/results/qwen2_rope_q1024_repeated';OUT.mkdir(parents=True,exist_ok=True)
def fromword(w):return struct.unpack('<f',struct.pack('<I',int(w)))[0]
def bits(v):return struct.unpack('<I',struct.pack('<f',float(np.float32(v))))[0]
def bf(v):
 w=bits(v);return((w+0x7fff+((w>>16)&1))>>16)&0xffff
def load(path,columns):
 vals=[]
 for line in path.read_text().splitlines():
  w=int(line,16);vals.extend((w>>(16*i))&0xffff for i in range(32))
 return np.asarray(vals,dtype=np.uint16).reshape(16,columns)
def rotate(row,heads,cosine,sine):
 out=np.empty_like(row)
 for h in range(heads):
  for d in range(64):
   e=fromword(int(row[h*128+d])<<16);o=fromword(int(row[h*128+64+d])<<16);c=cosine[d];s=sine[d];out[h*128+d]=bf(np.float32(np.float32(e*c)-np.float32(o*s)));out[h*128+64+d]=bf(np.float32(np.float32(e*s)+np.float32(o*c)))
 return out
def pack(path,vals,width=16):
 n=512//width;path.write_text(''.join(f'{sum(int(v)<<(width*i)for i,v in enumerate(vals[j:j+n])):0128x}\n'for j in range(0,len(vals),n)))
def round_q46(value):return -(((-value)+(1<<45))>>46)if value<0 else(value+(1<<45))>>46
base_angle=np.asarray([1_000_000.0**(-2*d/128)for d in range(64)]);scale=1<<46;base_cos=np.asarray([round(math.cos(a)*scale)for a in base_angle],dtype=object);base_sin=np.asarray([round(math.sin(a)*scale)for a in base_angle],dtype=object);max_error=0.0
for kind,cols,heads in(('q',1536,12),('k',256,2)):
 inp=load(SRC/f'{kind}_biased_token_major.memh',cols);out=[];cosine=np.asarray([scale]*64,dtype=object);sine=np.asarray([0]*64,dtype=object)
 for pos in range(1024):
  row=inp[pos%16];rec_cos=np.asarray([np.float32(c/scale)for c in cosine]);rec_sin=np.asarray([np.float32(s/scale)for s in sine]);rec=rotate(row,heads,rec_cos,rec_sin);direct_cos=np.asarray([np.float32(math.cos(pos*a))for a in base_angle]);direct_sin=np.asarray([np.float32(math.sin(pos*a))for a in base_angle]);direct=rotate(row,heads,direct_cos,direct_sin);rf=np.asarray([fromword(int(v)<<16)for v in rec]);df=np.asarray([fromword(int(v)<<16)for v in direct]);max_error=max(max_error,float(np.max(np.abs(rf-df))));out.extend(rec.tolist());nc=[];ns=[]
  for d in range(64):
   x=cosine[d]*base_cos[d]-sine[d]*base_sin[d];y=cosine[d]*base_sin[d]+sine[d]*base_cos[d];nc.append(round_q46(x));ns.append(round_q46(y))
  cosine,sine=np.asarray(nc,dtype=object),np.asarray(ns,dtype=object)
 pack(OUT/f'{kind}_rope_expected.memh',out)
v_input=load(SRC/'v_biased_token_major.memh',256);pack(OUT/'v_biased_repeated.memh',[int(v)for pos in range(1024)for v in v_input[pos%16]])
pack(OUT/'positions.memh',list(range(1024)),32)
(OUT/'result.json').write_text(json.dumps({'schema_version':1,'status':'PASS'if max_error<=0.002 else'FAIL','positions':1024,'recurrence_vs_direct_max_absolute_error':max_error,'threshold':0.002},indent=2,sort_keys=True)+'\n');print(f'QWEN2_ROPE_Q1024_REPEATED_VECTORS_PASS positions=1024 Q_values=1572864 K_values=262144 theta=1000000 recurrence_direct_max_error={max_error:.9g}')
