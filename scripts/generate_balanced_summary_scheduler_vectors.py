#!/usr/bin/env python3
import hashlib,json,random,struct
from pathlib import Path
from heteronpu.hierarchical_attention import Summary,merge_rtl_pwl

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'work/results/l5_balanced_summary_scheduler';OUT.mkdir(parents=True,exist_ok=True);rng=random.Random(0xBA1A8CE);counts=(2,3,4,8)
def bits(x):return struct.unpack('<I',struct.pack('<f',float(x)))[0]
def balanced(values):
 values=list(values)
 while len(values)>1:values=[merge_rtl_pwl(values[i],values[i+1])if i+1<len(values)else values[i]for i in range(0,len(values),2)]
 return values[0]
inputs=[];expected=[]
for count in counts:
 values=[Summary(rng.uniform(-20,8),rng.uniform(.25,8),tuple(rng.uniform(-4,4)for _ in range(128)))for _ in range(count)];inputs.extend(values);expected.append(balanced(values))
def write(path,lines):path.write_text('\n'.join(lines)+'\n');return hashlib.sha256(path.read_bytes()).hexdigest()
hashes={}
hashes['counts']=write(OUT/'counts.memh',[f'{x:x}'for x in counts])
hashes['input_headers']=write(OUT/'input_headers.memh',[f'{bits(s.l):08x}{bits(s.m):08x}'for s in inputs])
hashes['input_beats']=write(OUT/'input_beats.memh',[f'{sum(bits(s.o[b*4+i])<<(32*i)for i in range(4)):032x}'for s in inputs for b in range(32)])
hashes['expected_headers']=write(OUT/'expected_headers.memh',[f'{bits(s.l):08x}{bits(s.m):08x}'for s in expected])
hashes['expected_beats']=write(OUT/'expected_beats.memh',[f'{sum(bits(s.o[b*4+i])<<(32*i)for i in range(4)):032x}'for s in expected for b in range(32)])
r={'schema_version':1,'status':'PASS','counts':counts,'cases':len(counts),'input_summaries':sum(counts),'expected_merges':sum(x-1 for x in counts),'beats_per_summary':32,'hashes':hashes};(OUT/'manifest.json').write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print('BALANCED_SUMMARY_VECTORS_PASS cases=4 counts=2,3,4,8 merges=13')
