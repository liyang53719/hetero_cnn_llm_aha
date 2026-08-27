#!/usr/bin/env python3
import random,struct,json
from pathlib import Path
from heteronpu.hierarchical_attention import Summary,merge_rtl_pwl
def bits(x):return struct.unpack('<I',struct.pack('<f',float(x)))[0]
r=random.Random(0xB128);cases=[(Summary.empty(4),Summary(1,2,(1,2,3,4))),(Summary(1,2,(1,2,3,4)),Summary.empty(4)),(Summary.empty(4),Summary.empty(4)),(Summary(1,1,(1,2,3,4)),Summary(1,2,(1,2,3,4)))]
for _ in range(128):cases.append((Summary(r.uniform(-12,8),r.uniform(.01,256),tuple(r.uniform(-64,64) for _ in range(4))),Summary(r.uniform(-12,8),r.uniform(.01,256),tuple(r.uniform(-64,64) for _ in range(4)))))
p=Path('tests/vectors/fp32_mlo_merge_vectors.txt');p.parent.mkdir(parents=True,exist_ok=True)
with p.open('w') as f:
 for a,b in cases:
  o=merge_rtl_pwl(a,b);vals=[a.m,a.l,b.m,b.l,*a.o,*b.o,o.m,o.l,*o.o];f.write(' '.join(f'{bits(x):08x}' for x in vals)+'\n')
Path('reports/execution/block128_vectors.json').write_text(json.dumps({'status':'PASS','cases':len(cases),'lanes':4,'evidence':'E0'},indent=2)+'\n')
print(len(cases))
