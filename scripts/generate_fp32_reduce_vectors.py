#!/usr/bin/env python3
import argparse,random,struct
from pathlib import Path
def f(b):return struct.unpack('<f',struct.pack('<I',b))[0]
def bits(x):return struct.unpack('<I',struct.pack('<f',x))[0]
def add(a,b):
 try:return bits(f(a)+f(b))
 except OverflowError:return ((a&b)&0x80000000)|0x7f800000
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--count',type=int,default=10000);a=p.parse_args();r=random.Random(0x16add016);lines=[]
 for _ in range(a.count):
  v=[(r.randrange(2)<<31)|(r.randrange(110,145)<<23)|r.randrange(1<<23) for _ in range(16)];x=v
  while len(x)>1:x=[add(x[i],x[i+1]) for i in range(0,len(x),2)]
  lines.append(f'{x[0]:08x}'+''.join(f'{z:08x}' for z in reversed(v)))
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text('\n'.join(lines)+'\n');print(f'FP32_REDUCE_VECTORS_PASS count={len(lines)}')
if __name__=='__main__':main()
