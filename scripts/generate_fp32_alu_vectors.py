#!/usr/bin/env python3
import argparse,hashlib,json,random,struct
from pathlib import Path
def f(b):return struct.unpack('<f',struct.pack('<I',b))[0]
def bits(x):return struct.unpack('<I',struct.pack('<f',x))[0]
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--count',type=int,default=10000);a=p.parse_args();r=random.Random(0x32add001);lines=[]
 while len(lines)<a.count:
  x=(r.randrange(2)<<31)|(r.randrange(1,255)<<23)|r.randrange(1<<23);y=(r.randrange(2)<<31)|(r.randrange(1,255)<<23)|r.randrange(1<<23);op=len(lines)&1
  try:o=bits(f(x)*f(y) if op else f(x)+f(y))
  except OverflowError:o=((x^y)&0x80000000)|0x7f800000
  lines.append(f'{op:01x}{o:08x}{y:08x}{x:08x}')
 data=('\n'.join(lines)+'\n').encode();a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(data);a.manifest.write_text(json.dumps({'count':len(lines),'seed':'0x32add001','sha256':hashlib.sha256(data).hexdigest()},indent=2)+'\n');print(f'FP32_ALU_VECTORS_PASS count={len(lines)} sha256={hashlib.sha256(data).hexdigest()}')
if __name__=='__main__':main()
