#!/usr/bin/env python3
import argparse,json,math,random,struct
from pathlib import Path
import numpy as np
def bits(x):return struct.unpack('<I',struct.pack('<f',float(np.float32(x))))[0]
def f(b):return struct.unpack('<f',struct.pack('<I',b))[0]
def exp2p(x):
 x=np.float32(x)
 if x< -16:return np.float32(0)
 if x>=0:return np.float32(1)
 i=max(0,min(255,math.floor(float(x)*16)+256));x0=np.float32(1*i/16-16);x1=np.float32(x0+np.float32(1/16));y0=np.float32(np.exp2(x0));y1=np.float32(np.exp2(x1));m=np.float32((np.float64(y1)-np.float64(y0))/(1/16));b=np.float32(np.float64(y0)-np.float64(m)*np.float64(x0));return np.float32(np.float32(m*x)+b)
def recip(x):
 xb=bits(x);E=(xb>>23)&255;fr=xb&0x7fffff;norm=np.float32(f((127<<23)|fr));i=fr>>19;x0=1+i/16;x1=x0+1/16;m=np.float32(((1/x1)-(1/x0))/(1/16));b=np.float32(1/x0-float(m)*x0);y=np.float32(np.float32(m*norm)+b);t=np.float32(norm*y);u=np.float32(np.float32(2)-t);y=np.float32(y*u);return np.float32(y*np.float32(f((254-E)<<23)))
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--count',type=int,default=10000);a=p.parse_args();r=random.Random(0x73696c75);xs=[-16.,-8.,-1.,0.,1.,8.,16.]
 while len(xs)<a.count:xs.append(r.uniform(-16,16))
 lines=[];ma=0.
 for x in xs[:a.count]:
  x=np.float32(x);z=np.float32(np.float32(-abs(float(x)))*np.float32(1.4426950408889634));e=exp2p(z);d=np.float32(np.float32(1)+e);ri=recip(d);base=np.float32(x*ri);got=np.float32(base*e)if x<0 else base;ref=float(x)/(1+math.exp(-float(x)));ma=max(ma,abs(float(got)-ref));lines.append(f'{bits(got):08x}{bits(x):08x}')
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text('\n'.join(lines)+'\n');q={'count':len(lines),'range':[-16,16],'max_absolute_error':ma,'threshold':0.002,'threshold_pass':ma<=0.002};a.manifest.write_text(json.dumps(q,indent=2)+'\n');
 if not q['threshold_pass']:raise SystemExit(f'SILU_VECTOR_FAIL {q}')
 print(f'SILU_VECTORS_PASS count={len(lines)} max_abs={ma:.9g}')
if __name__=='__main__':main()
