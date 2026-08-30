#!/usr/bin/env python3
import argparse,math,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from heteronpu.ggml_quant import dot_groups,random_q3_k,random_q6_k,random_q8_0
p=argparse.ArgumentParser();p.add_argument('--cases',type=int,default=128);p.add_argument('--output',type=Path,default=ROOT/'tests/vectors/ggml_quant_vectors.txt');a=p.parse_args();lines=['# format case_id payload_hex expected_dot']
for name,factory in [('Q8_0',random_q8_0),('Q6_K',random_q6_k),('Q3_K',random_q3_k)]:
 for case in range(a.cases):
  b=factory(case);acts=[math.sin((case+1)*(j+3)*.001) for j in range(len(b.dequantize()))];lines.append(f'{name} {case} {b.pack().hex()} {dot_groups(b.groups(),acts):.17g}')
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text('\n'.join(lines)+'\n');print(f'GGML_QUANT_VECTORS_PASS cases={a.cases*3}')
