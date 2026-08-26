#!/usr/bin/env python3
import argparse,ctypes,hashlib,json,random,struct
from pathlib import Path
import numpy as np
libm=ctypes.CDLL('libm.so.6');fmaf=libm.fmaf;fmaf.argtypes=[ctypes.c_float]*3;fmaf.restype=ctypes.c_float
def bits(x):return struct.unpack('<I',struct.pack('<f',float(np.float32(x))))[0]
def f(b):return struct.unpack('<f',struct.pack('<I',b))[0]
def bf(x):u=bits(x);return((u+0x7fff+((u>>16)&1))>>16)&0xffff
def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True);r=random.Random(0x2566e6d)
 x=[bf(r.uniform(-1,1))for _ in range(256)];w=[bf(r.uniform(-.25,.25))for _ in range(256*256)];out=[]
 for j in range(256):
  acc=ctypes.c_float(0)
  for k in range(256):acc=ctypes.c_float(fmaf(ctypes.c_float(f(x[k]<<16)),ctypes.c_float(f(w[k*256+j]<<16)),acc))
  out.append(bits(acc.value))
 (a.out/'x_bf16.memh').write_text('\n'.join(f'{z:04x}'for z in x)+'\n');(a.out/'weights_bf16.memh').write_text('\n'.join(f'{z:04x}'for z in w)+'\n');(a.out/'expected.memh').write_text('\n'.join(f'{z:08x}'for z in out)+'\n')
 q={'hidden':256,'output':256,'column_tiles':8,'k_steps_per_tile':256,'array_steps':2048,'expected_sha256':hashlib.sha256((a.out/'expected.memh').read_bytes()).hexdigest()};(a.out/'manifest.json').write_text(json.dumps(q,indent=2)+'\n');print(f"L5_HIDDEN256_GEMV_VECTORS_PASS steps=2048 expected_sha256={q['expected_sha256']}")
if __name__=='__main__':main()
