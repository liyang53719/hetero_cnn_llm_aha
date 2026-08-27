#!/usr/bin/env python3
import math,random,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/"tests"/"vectors";OUT.mkdir(parents=True,exist_ok=True)
def f32(v):return struct.unpack("<f",struct.pack("<f",float(v)))[0]
def bits(v):return struct.unpack("<I",struct.pack("<f",f32(v)))[0]
def expected(op,x,y):
 r=f32(x)*f32(y) if op=="mul" else f32(x)+f32(y)
 if not math.isfinite(r) or abs(r)>3.3e38:raise OverflowError
 return f32(r)
def make(op,count,seed):
 rng=random.Random(seed);values=[0.,-0.,1.,-1.,.5,-.5,2.,-2.,2**-126,-2**-126,2**-20,-2**-20,2**20,-2**20,3.1415927,-2.7182818];out=[]
 for x in values:
  for y in values:
   try:out.append((bits(x),bits(y),bits(expected(op,x,y))))
   except OverflowError:pass
   if len(out)==count:return out
 while len(out)<count:
  x=math.ldexp(rng.uniform(-1.999,1.999),rng.randint(-40,40));y=math.ldexp(rng.uniform(-1.999,1.999),rng.randint(-40,40))
  try:r=expected(op,x,y)
  except OverflowError:continue
  out.append((bits(x),bits(y),bits(r)))
 return out
for op,seed in (("mul",5001),("add",5002)):
 p=OUT/f"fp32_{op}_pipe_vectors.txt";p.write_text("".join(f"{x:08x} {y:08x} {r:08x}\n" for x,y,r in make(op,512,seed)));print(op,p)
