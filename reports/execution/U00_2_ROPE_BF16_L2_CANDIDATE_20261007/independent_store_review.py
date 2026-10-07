#!/usr/bin/env python3
"""Decode actual bus bytes against saved native outputs without new runner helpers."""
import hashlib,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
RUN=ROOT/'work/rope_bf16_l2_candidate_result_final'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
metadata=json.loads((RUN/'transactions.json').read_text())
vector_lines=(RUN/'vectors.memh').read_text().splitlines()
assert len(metadata)==5184 and len(vector_lines)==5184*35
corpora={name:dict(np.load(ROOT/f'tests/fixtures/rope_rounding/{name}.npz',allow_pickle=False)) for name in ('local','remote')}
completed=0;packets=0;total_packets=0;native_values=0;tail_values=0;stored_bytes=0;offsets=set();flag_values=set()
actual=bytearray()
for line in (RUN/'candidate_stores.txt').read_text().splitlines():
 fields=line.split();assert fields[0] in ('W','D')
 tx=int(fields[1])
 if tx<0:continue
 assert tx==completed and tx<len(metadata)
 r=metadata[tx];heads=r['heads'];nbytes=heads*512;destination=r['destination'];first=destination//64
 if fields[0]=='W':
  assert len(fields)==5 and len(fields[3])==16 and len(fields[4])==128
  address=int(fields[2],16);mask=int(fields[3],16);data=int(fields[4],16).to_bytes(64,'little')
  assert address==first+packets
  for b in range(64):
   index=address*64+b-destination
   enabled=0<=index<nbytes
   assert bool(mask&(1<<b))==enabled
   if enabled:
    assert len(actual)==index
    actual.append(data[b]);stored_bytes+=1
   else:assert data[b]==0
  packets+=1;total_packets+=1
 else:
  assert len(fields)==6 and len(actual)==nbytes
  counts=tuple(int(x) for x in fields[2:])
  expected_count=heads*8+int(destination%64!=0)
  assert counts==(heads*8+2,heads*32,expected_count,r['flags']) and packets==expected_count
  tensor=np.frombuffer(actual,dtype='<u2').reshape(heads,256)
  start=r['first_pair'];native=corpora[r['corpus']]['native_outputs'][start:start+heads*32].reshape(heads,32,2)
  assert np.array_equal(tensor[:,:32],native[:,:,0]>>16)
  assert np.array_equal(tensor[:,32:64],native[:,:,1]>>16)
  source_bytes=b''.join(int(vector_lines[tx*35+1+b],16).to_bytes(64,'little') for b in range(heads*8))
  source=np.frombuffer(source_bytes,dtype='<u2').reshape(heads,256)
  assert np.array_equal(tensor[:,64:],source[:,64:])
  # Source head grouping and cos/sin lane order are independently rebound to
  # immutable input arrays; synthetic tails have no source-model attribution.
  old=corpora[r['corpus']]['inputs'][start:start+heads*32].reshape(heads,32,4)
  assert np.array_equal(source[:,:32],old[:,:,0]>>16)
  assert np.array_equal(source[:,32:64],old[:,:,1]>>16)
  for c in range(2):
   coefficients=np.frombuffer(int(vector_lines[tx*35+17+c],16).to_bytes(64,'little'),dtype='<u2')
   for h in range(heads):assert np.array_equal(coefficients,old[h,:,c+2]>>16)
  native_values+=heads*64;tail_values+=heads*192;offsets.add(destination%64);flag_values.add(r['flags'])
  completed+=1;packets=0;actual=bytearray()
assert completed==5184 and packets==0 and not actual
assert offsets==set(range(0,64,2))
result=dict(status='PASS_INDEPENDENT_RAW_BYTE_NATIVE_REVIEW',transactions=completed,physical_write_beats=total_packets,stored_bytes=stored_bytes,native_rotary_values_including_supplemental=native_values,raw_synthetic_tail_values=tail_values,output_byte_offsets=sorted(offsets),aggregate_flags_observed=sorted(flag_values),independence='No import or use of new candidate transport helper, expected_packets, make_records, or verify_store_trace. Actual accepted bytes checked directly against immutable native outputs and source tail bits.',input_sha256={str(p.relative_to(ROOT)):sha(p) for p in [RUN/'transactions.json',RUN/'vectors.memh',RUN/'candidate_stores.txt',ROOT/'tests/fixtures/rope_rounding/local.npz',ROOT/'tests/fixtures/rope_rounding/remote.npz']},script_sha256=sha(Path(__file__)))
(OUT/'independent_store_review.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='input_sha256'},indent=2))
