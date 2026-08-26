#!/usr/bin/env python3
import argparse,struct
from pathlib import Path
def bits(v):return struct.unpack('<I',struct.pack('<f',float(v)))[0]
def av(i,k):return i%5-2+k%3-1
def bv(j,k):return j%7-3+(k&1)
def main():
 p=argparse.ArgumentParser();p.add_argument('--rows',type=int,required=True);p.add_argument('--cols',type=int,required=True);p.add_argument('--steps',type=int,default=4);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 vals=[]
 for i in range(a.rows):
  for j in range(a.cols):vals.append(bits(sum(av(i,k)*bv(j,k) for k in range(a.steps))))
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text('\n'.join(f'{v:08x}' for v in vals)+'\n')
 print(f'BF16_ARRAY_EXPECTED_PASS rows={a.rows} cols={a.cols} steps={a.steps}')
if __name__=='__main__':main()
