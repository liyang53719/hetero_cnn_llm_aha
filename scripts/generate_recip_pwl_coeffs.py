#!/usr/bin/env python3
import argparse,json,struct
from pathlib import Path
import numpy as np
def bits(x):return struct.unpack('<I',struct.pack('<f',float(np.float32(x))))[0]
def main():
 p=argparse.ArgumentParser();p.add_argument('--svh',type=Path,required=True);p.add_argument('--json',type=Path,required=True);a=p.parse_args();co=[];mr=0.;ma=0.;worst=0.
 for i in range(16):
  x0=1+i/16;x1=x0+1/16;y0=1/x0;y1=1/x1;m=np.float32((y1-y0)/(x1-x0));b=np.float32(y0-float(m)*x0);co.append((m,b))
  x=np.linspace(x0,x1,65537,dtype=np.float32);y=np.float32(np.float32(m*x)+b);t=np.float32(x*y);u=np.float32(np.float32(2.0)-t);got=np.float32(y*u);ref=1/x.astype(np.float64);ae=np.abs(got.astype(np.float64)-ref);re=ae/ref;j=int(np.argmax(re));
  if float(re[j])>mr:mr=float(re[j]);worst=float(x[j]);ma=max(ma,float(np.max(ae)))
 lines=['// Generated reciprocal mantissa coefficients','function automatic logic[63:0] recip_pwl_coeff(input logic[3:0]index);','case(index)']
 for i,(m,b) in enumerate(co):lines.append(f"4'd{i}:recip_pwl_coeff=64'h{bits(m):08x}{bits(b):08x};")
 lines+=['default:recip_pwl_coeff=64\'d0;','endcase','endfunction'];a.svh.parent.mkdir(parents=True,exist_ok=True);a.svh.write_text('\n'.join(lines)+'\n')
 q={'segments':16,'mantissa_range':[1.0,2.0],'newton_iterations':1,'max_relative_error_dense':mr,'max_absolute_error_dense':ma,'worst_x':worst,'relative_threshold':2e-6,'threshold_pass':mr<=2e-6};a.json.parent.mkdir(parents=True,exist_ok=True);a.json.write_text(json.dumps(q,indent=2)+'\n')
 if not q['threshold_pass']:raise SystemExit(f'RECIP_COEFF_FAIL {q}')
 print(f'RECIP_COEFF_PASS max_rel={mr:.9g} max_abs={ma:.9g}')
if __name__=='__main__':main()
