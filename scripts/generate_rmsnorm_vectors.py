#!/usr/bin/env python3
import argparse,json,math,random,struct
from pathlib import Path
import numpy as np
def bits(x):return struct.unpack('<I',struct.pack('<f',float(np.float32(x))))[0]
def f(b):return struct.unpack('<f',struct.pack('<I',b))[0]
def rsqrt_alg(x):
 xb=bits(x);E=(xb>>23)&255;fr=xb&0x7fffff;e=E-127;odd=e&1;ee=e-1 if odd else e;norm=np.float32(f(((128 if odd else 127)<<23)|fr));idx=(odd<<4)|(fr>>19);lo,step=(1.,1/16)if not odd else(2.,1/8);x0=lo+(idx&15)*step;x1=x0+step;m=np.float32(((1/math.sqrt(x1))-(1/math.sqrt(x0)))/step);b=np.float32(1/math.sqrt(x0)-float(m)*x0);y=np.float32(np.float32(m*norm)+b);y2=np.float32(y*y);xy=np.float32(norm*y2);term=np.float32(np.float32(1.5)-np.float32(np.float32(.5)*xy));return np.float32(np.float32(y*term)*np.float32(f((127-ee//2)<<23)))
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--count',type=int,default=10000);a=p.parse_args();r=random.Random(0x726d736e);lines=[];ma=0.
 for n in range(a.count):
  if n==0:x=np.zeros(16,dtype=np.float32)
  elif n==1:x=np.full(16,np.float32(0.001))
  elif n==2:x=np.array([(-1)**i*32 for i in range(16)],dtype=np.float32)
  else:x=np.array([r.uniform(-8,8) for _ in range(16)],dtype=np.float32)
  w=np.array([r.uniform(.5,1.5) for _ in range(16)],dtype=np.float32);eps=np.float32(1e-5);sq=np.array([np.float32(z*z) for z in x],dtype=np.float32);q=sq
  while len(q)>1:q=np.array([np.float32(q[i]+q[i+1]) for i in range(0,len(q),2)],dtype=np.float32)
  mean=np.float32(q[0]*np.float32(1/16));me=np.float32(mean+eps);inv=rsqrt_alg(me);y=np.array([np.float32(np.float32(x[i]*inv)*w[i]) for i in range(16)],dtype=np.float32)
  ref=x.astype(np.float64)*w.astype(np.float64)/math.sqrt(float(np.mean(x.astype(np.float64)**2))+float(eps));ma=max(ma,float(np.max(np.abs(y.astype(np.float64)-ref))))
  rec=0
  for i,z in enumerate(x):rec|=bits(z)<<(32*i)
  for i,z in enumerate(w):rec|=bits(z)<<(512+32*i)
  rec|=bits(eps)<<1024
  for i,z in enumerate(y):rec|=bits(z)<<(1056+32*i)
  lines.append(f'{rec:0392x}')
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text('\n'.join(lines)+'\n');q={'count':len(lines),'lanes':16,'max_absolute_error':ma,'threshold':2e-5,'threshold_pass':ma<=2e-5};a.manifest.write_text(json.dumps(q,indent=2)+'\n');
 if not q['threshold_pass']:raise SystemExit(f'RMSNORM_VECTOR_FAIL {q}')
 print(f'RMSNORM_VECTORS_PASS count={len(lines)} max_abs={ma:.9g}')
if __name__=='__main__':main()
