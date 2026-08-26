#!/usr/bin/env python3
import argparse,json,math,random,struct
from pathlib import Path
import numpy as np
def f(b):return struct.unpack('<f',struct.pack('<I',b))[0]
def bits(x):return struct.unpack('<I',struct.pack('<f',float(np.float32(x))))[0]
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--count',type=int,default=10000);a=p.parse_args();r=random.Random(0x72737172);xs=[0,0x7f800000,0xbf800000,0x7fc00001,0x00800000]
 while len(xs)<a.count:xs.append((r.randrange(2,254)<<23)|r.randrange(1<<23))
 lines=[];mr=0.
 for xb in xs[:a.count]:
  E=(xb>>23)&255;fr=xb&0x7fffff;domain=0
  if xb==0:out=0x7f800000
  elif xb==0x7f800000:out=0
  elif xb>>31 or not(2<=E<=253):out=0x7fc00000;domain=1
  else:
   e=E-127;odd=e&1;ee=e-1 if odd else e;norm=np.float32(f(((128 if odd else 127)<<23)|fr));idx=(odd<<4)|(fr>>19);lo,step=(1.,1/16)if not odd else(2.,1/8);x0=lo+(idx&15)*step;x1=x0+step;m=np.float32(((1/math.sqrt(x1))-(1/math.sqrt(x0)))/step);b=np.float32(1/math.sqrt(x0)-float(m)*x0)
   y0=np.float32(np.float32(m*norm)+b);y2=np.float32(y0*y0);xy2=np.float32(norm*y2);half=np.float32(np.float32(.5)*xy2);term=np.float32(np.float32(1.5)-half);y1=np.float32(y0*term);scale=np.float32(f((127-ee//2)<<23));got=np.float32(y1*scale);out=bits(got);mr=max(mr,abs(float(got)-1/math.sqrt(f(xb)))/(1/math.sqrt(f(xb))))
  lines.append(f'{domain:01x}{out:08x}{xb:08x}')
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text('\n'.join(lines)+'\n');q={'count':len(lines),'max_relative_error_random':mr,'relative_threshold':2e-6,'threshold_pass':mr<=2e-6};a.manifest.write_text(json.dumps(q,indent=2)+'\n');
 if not q['threshold_pass']:raise SystemExit(f'RSQRT_VECTOR_FAIL {q}')
 print(f'RSQRT_VECTORS_PASS count={len(lines)} max_rel={mr:.9g}')
if __name__=='__main__':main()
