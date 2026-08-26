#!/usr/bin/env python3
import argparse,json,math,struct
from pathlib import Path
import numpy as np
def bits(x):return struct.unpack('<I',struct.pack('<f',float(np.float32(x))))[0]
def main():
 p=argparse.ArgumentParser();p.add_argument('--svh',type=Path,required=True);p.add_argument('--json',type=Path,required=True);a=p.parse_args();co=[];mr=0.;ma=0.;worst=0.
 for bank in range(2):
  lo,step=(1.,1/16)if bank==0 else(2.,1/8)
  for i in range(16):
   x0=lo+i*step;x1=x0+step;y0=1/math.sqrt(x0);y1=1/math.sqrt(x1);m=np.float32((y1-y0)/step);b=np.float32(y0-float(m)*x0);co.append((m,b));x=np.linspace(x0,x1,65537,dtype=np.float32)
   y=np.float32(np.float32(m*x)+b);y2=np.float32(y*y);xy2=np.float32(x*y2);half=np.float32(np.float32(.5)*xy2);term=np.float32(np.float32(1.5)-half);got=np.float32(y*term);ref=1/np.sqrt(x.astype(np.float64));ae=np.abs(got.astype(np.float64)-ref);re=ae/ref;j=int(np.argmax(re));
   if float(re[j])>mr:mr=float(re[j]);worst=float(x[j]);ma=max(ma,float(np.max(ae)))
 lines=['// Generated rsqrt mantissa coefficients','function automatic logic[63:0] rsqrt_pwl_coeff(input logic[4:0]index);','case(index)']
 for i,(m,b) in enumerate(co):lines.append(f"5'd{i}:rsqrt_pwl_coeff=64'h{bits(m):08x}{bits(b):08x};")
 lines+=['default:rsqrt_pwl_coeff=64\'d0;','endcase','endfunction'];a.svh.parent.mkdir(parents=True,exist_ok=True);a.svh.write_text('\n'.join(lines)+'\n')
 q={'segments':32,'mantissa_banks':[[1,2],[2,4]],'newton_iterations':1,'max_relative_error_dense':mr,'max_absolute_error_dense':ma,'worst_x':worst,'relative_threshold':2e-6,'threshold_pass':mr<=2e-6};a.json.parent.mkdir(parents=True,exist_ok=True);a.json.write_text(json.dumps(q,indent=2)+'\n')
 if not q['threshold_pass']:raise SystemExit(f'RSQRT_COEFF_FAIL {q}')
 print(f'RSQRT_COEFF_PASS max_rel={mr:.9g} max_abs={ma:.9g}')
if __name__=='__main__':main()
