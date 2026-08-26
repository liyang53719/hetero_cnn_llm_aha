#!/usr/bin/env python3
import argparse,json,math,random,struct
from pathlib import Path
import numpy as np
def f(b):return struct.unpack('<f',struct.pack('<I',b))[0]
def bits(x):return struct.unpack('<I',struct.pack('<f',float(np.float32(x))))[0]
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--count',type=int,default=10000);a=p.parse_args();r=random.Random(0x72656369);xs=[0,0x7f800000,0xbf800000,0x7fc00001,0x00800000]
 while len(xs)<a.count:xs.append((r.randrange(2,254)<<23)|r.randrange(1<<23))
 lines=[];mr=0.
 for xb in xs[:a.count]:
  e=(xb>>23)&255;frac=xb&0x7fffff;domain=0
  if xb==0:out=0x7f800000
  elif xb==0x7f800000:out=0
  elif xb>>31 or not(2<=e<=253):out=0x7fc00000;domain=1
  else:
   norm=np.float32(f((127<<23)|frac));idx=frac>>19;x0=1+idx/16;x1=x0+1/16;m=np.float32(((1/x1)-(1/x0))/(1/16));b=np.float32(1/x0-float(m)*x0)
   y0=np.float32(np.float32(m*norm)+b);t=np.float32(norm*y0);u=np.float32(np.float32(2)-t);y1=np.float32(y0*u);scale=np.float32(f((254-e)<<23));got=np.float32(y1*scale);out=bits(got);mr=max(mr,abs(float(got)-1/f(xb))/(1/f(xb)))
  lines.append(f'{domain:01x}{out:08x}{xb:08x}')
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text('\n'.join(lines)+'\n');q={'count':len(lines),'max_relative_error_random':mr,'relative_threshold':2e-6,'threshold_pass':mr<=2e-6};a.manifest.write_text(json.dumps(q,indent=2)+'\n');
 if not q['threshold_pass']:raise SystemExit(f'RECIP_VECTOR_FAIL {q}')
 print(f'RECIP_VECTORS_PASS count={len(lines)} max_rel={mr:.9g}')
if __name__=='__main__':main()
