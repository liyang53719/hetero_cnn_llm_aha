#!/usr/bin/env python3
import argparse,ctypes,hashlib,json,random,struct
from pathlib import Path
def f32(bits):return struct.unpack('<f',struct.pack('<I',bits))[0]
def bits(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def main():
 p=argparse.ArgumentParser();p.add_argument('--count',type=int,default=10000);p.add_argument('--output',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True);a=p.parse_args()
 libm=ctypes.CDLL('libm.so.6');fma=libm.fmaf;fma.argtypes=[ctypes.c_float]*3;fma.restype=ctypes.c_float;r=random.Random(0x5bf16f32);lines=[]
 directed=[(0x3f80,0x4000,0x40400000),(0xbf80,0x4000,0x40400000),(0x0001,0x3f80,0),(0x7f7f,0x3f80,0)]
 for av,bv,cv in directed:
  out=bits(fma(ctypes.c_float(f32(av<<16)),ctypes.c_float(f32(bv<<16)),ctypes.c_float(f32(cv))));lines.append(f'{1:01x}{out:08x}{cv:08x}{bv:04x}{av:04x}')
 while len(lines)<a.count:
  av=(r.randrange(2)<<15)|(r.randrange(1,255)<<7)|r.randrange(128);bv=(r.randrange(2)<<15)|(r.randrange(1,255)<<7)|r.randrange(128)
  cv=(r.randrange(2)<<31)|(r.randrange(1,255)<<23)|r.randrange(1<<23);out=bits(fma(ctypes.c_float(f32(av<<16)),ctypes.c_float(f32(bv<<16)),ctypes.c_float(f32(cv))))
  lines.append(f'{1:01x}{out:08x}{cv:08x}{bv:04x}{av:04x}')
 data=('\n'.join(lines)+'\n').encode();a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(data)
 a.manifest.write_text(json.dumps({'count':len(lines),'seed':'0x5bf16f32','oracle':'libm.so.6 fmaf','sha256':hashlib.sha256(data).hexdigest()},indent=2)+'\n')
 print(f'BF16_FMA_VECTORS_PASS count={len(lines)} sha256={hashlib.sha256(data).hexdigest()}')
if __name__=='__main__':main()
