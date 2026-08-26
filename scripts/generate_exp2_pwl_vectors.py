#!/usr/bin/env python3
import argparse,json,math,random,struct
from pathlib import Path
import numpy as np
def bits(x):return struct.unpack('<I',struct.pack('<f',float(np.float32(x))))[0]
def f(b):return struct.unpack('<f',struct.pack('<I',b))[0]
def main():
 p=argparse.ArgumentParser();p.add_argument('--coeff-json',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--count',type=int,default=10000);a=p.parse_args();cfg=json.loads(a.coeff_json.read_text());r=random.Random(0x65787032);xs=[-18.,-16.,-15.999,-1.,-0.5,-1e-6,0.,1.,float('inf'),float('-inf'),float('nan')]
 while len(xs)<a.count:xs.append(r.uniform(-18,2));lines=[];maxa=0.;maxr=0.
 for x in xs[:a.count]:
  xb=bits(x);xf=f(xb)
  if math.isnan(xf):got=np.float32(0)
  elif math.isinf(xf):got=np.float32(0 if xf<0 else 1)
  elif xf< -16:got=np.float32(0)
  elif xf>=0:got=np.float32(1)
  else:
   idx=max(0,min(255,math.floor(xf*16)+256));x0=np.float32(-16+idx/16);x1=np.float32(x0+np.float32(1/16));y0=np.float32(np.exp2(x0));y1=np.float32(np.exp2(x1));m=np.float32((np.float64(y1)-np.float64(y0))/(1/16));b=np.float32(np.float64(y0)-np.float64(m)*np.float64(x0));got=np.float32(np.float32(m*np.float32(xf))+b)
   ref=math.exp2(xf);ae=abs(float(got)-ref);maxa=max(maxa,ae);maxr=max(maxr,ae/ref)
  lines.append(f'{bits(got):08x}{xb:08x}')
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text('\n'.join(lines)+'\n');res={'count':len(lines),'max_absolute_error':maxa,'max_relative_error':maxr,'threshold_pass':maxa<=cfg['absolute_threshold'] and maxr<=cfg['relative_threshold']};a.manifest.write_text(json.dumps(res,indent=2)+'\n');
 if not res['threshold_pass']:raise SystemExit(f'EXP2_VECTOR_FAIL {res}')
 print(f'EXP2_PWL_VECTORS_PASS count={len(lines)} max_abs={maxa:.9g} max_rel={maxr:.9g}')
if __name__=='__main__':main()
