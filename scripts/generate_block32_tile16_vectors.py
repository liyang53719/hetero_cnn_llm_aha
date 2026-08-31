#!/usr/bin/env python3
from __future__ import annotations
import argparse,random,struct
from pathlib import Path
from heteronpu.hierarchical_attention import exp_rtl,f32
def bits(x):return struct.unpack('<I',struct.pack('<f',f32(x)))[0]
def pack(values):return sum(bits(v)<<(32*i) for i,v in enumerate(values))
def reduce32(values):
 x=[f32(v) for v in values]
 while len(x)>1:x=[f32(x[i]+x[i+1]) for i in range(0,len(x),2)]
 return x[0]
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--cases',type=int,default=16);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True);rng=random.Random(0xB3216)
scores=[];masks=[];ms=[];ls=[];weights=[]
for case in range(a.cases):
 tile=[[0.0]*16 for _ in range(32)];mask=[]
 limits=list(range(16)) if case==0 else [rng.randrange(32) for _ in range(16)]
 for col in range(32):
  mask.append(sum((col>limits[row])<<row for row in range(16)))
  for row in range(16):tile[col][row]=f32(0.0 if case==0 else rng.uniform(-3.5,3.5))
 maxima=[];row_weights=[];sums=[]
 for row in range(16):
  valid=[tile[col][row] for col in range(limits[row]+1)];maximum=max(valid);w=[exp_rtl(f32(tile[col][row]-maximum)) if col<=limits[row] else f32(0.0) for col in range(32)];maxima.append(maximum);row_weights.append(w);sums.append(reduce32(w))
 scores.extend(pack(tile[col]) for col in range(32));masks.extend(mask);ms.append(pack(maxima));ls.append(pack(sums));weights.extend(pack([row_weights[row][col] for row in range(16)]) for col in range(32))
def write(name,values,width): (a.out/name).write_text(''.join(f'{v:0{width}x}\n' for v in values))
write('scores.memh',scores,128);write('masks.memh',masks,4);write('m.memh',ms,128);write('l.memh',ls,128);write('weights.memh',weights,128);(a.out/'count.txt').write_text(f'{a.cases}\n');print(f'BLOCK32_TILE16_VECTOR_GENERATE_PASS cases={a.cases}')
