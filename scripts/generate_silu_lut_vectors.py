#!/usr/bin/env python3
from __future__ import annotations
import argparse,random,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from heteronpu.silu_lut_rtl_contract import bf16_bits,fused
p=argparse.ArgumentParser();p.add_argument('--cases',type=int,default=4096);p.add_argument('--output',type=Path,default=ROOT/'tests/vectors/bf16_silu_mul_lut_vectors.txt');a=p.parse_args();rng=random.Random(0x51A9);a.output.parent.mkdir(parents=True,exist_ok=True);edges=[-16,-8,-7.9375,-1,-0.0,0.0,.125,1,7.9375,8,16]
with a.output.open('w') as f:
 f.write('# tag last gate0 up0 expected0 gate1 up1 expected1\n')
 for case in range(a.cases):
  values=[]
  for lane in range(2):
   if case<len(edges):g=edges[(case+lane)%len(edges)];u=[-4,-1,0,1,4][(case+2*lane)%5]
   else:g=max(-16,min(16,rng.gauss(0,2.5)));u=max(-4,min(4,rng.gauss(0,1.25)))
   values.extend([bf16_bits(g),bf16_bits(u),bf16_bits(fused(g,u))])
  f.write(f'{case&0xfff:03x} {1 if case+1==a.cases else 0} '+' '.join(f'{v:04x}' for v in values)+'\n')
print(a.output)
