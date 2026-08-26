#!/usr/bin/env python3
import argparse,math,random,struct
from pathlib import Path
import numpy as np
def bits(x):return struct.unpack('<I',struct.pack('<f',float(np.float32(x))))[0]
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--count',type=int,default=10000);a=p.parse_args();r=random.Random(0x726f7065);lines=[]
 directed=[(1.,2.,1.,0.),(1.,2.,0.,1.),(-3.,4.,-1.,0.),(0.,0.,0.70710677,0.70710677)]
 while len(directed)<a.count:
  ang=r.uniform(-20,20);directed.append((r.uniform(-16,16),r.uniform(-16,16),math.cos(ang),math.sin(ang)))
 for e,o,c,s in directed[:a.count]:
  e=np.float32(e);o=np.float32(o);c=np.float32(c);s=np.float32(s)
  er=np.float32(np.float32(e*c)-np.float32(o*s));orr=np.float32(np.float32(e*s)+np.float32(o*c))
  lines.append(f'{bits(orr):08x}{bits(er):08x}{bits(s):08x}{bits(c):08x}{bits(o):08x}{bits(e):08x}')
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text('\n'.join(lines)+'\n');print(f'FP32_ROPE_VECTORS_PASS count={len(lines)}')
if __name__=='__main__':main()
