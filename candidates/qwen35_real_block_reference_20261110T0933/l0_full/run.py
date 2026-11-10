from pathlib import Path
import json,hashlib,time,resource,numpy as np,struct
from fractions import Fraction
from chunk_candidate import Arithmetic,FatalArithmetic
R=Path(__file__).resolve().parent;D=R.parent/'dense_real_reference';resource.setrlimit(resource.RLIMIT_AS,(2<<30,2<<30));resource.setrlimit(resource.RLIMIT_CPU,(600,600))
p=D/'profile1_local/prepared.bin';raw=p.read_bytes();sha=hashlib.sha256(raw).hexdigest();stages=json.loads((D/'profile1_progress.json').read_text());expected=next(x['sha256'] for x in stages if x['name']=='prepared')
if sha!=expected:raise ValueError('prepared hash mismatch')
x=np.frombuffer(raw,dtype='<f4').reshape(128,6400);q,k,v=[x[:,i*2048:(i+1)*2048].reshape(128,16,128) for i in range(3)];gate=x[:,6144:].reshape(128,16,16)
results=[];start=time.monotonic()
for h in range(16):
 a=Arithmetic();state=np.zeros((128,128),np.float32);outputs=[];chunk=0
 try:
  for chunk in range(2):
   s=slice(chunk*64,chunk*64+64);y,state=a.chunk(q[s,h],k[s,h],v[s,h],gate[s,h,0],gate[s,h,1],state);outputs.append(y)
  y=np.concatenate(outputs);u=y.view(np.uint32);y=((u+np.uint32(0x7fff)+((u>>16)&1))>>16).astype('<u2');np.save(R/f'head{h}.local.npy',y);np.save(R/f'state{h}.local.npy',state)
  rec=dict(head=h,status='CANDIDATE_CHUNK64_TWO_CHUNKS_EXECUTED',output_sha256=hashlib.sha256(y.tobytes()).hexdigest(),state_sha256=hashlib.sha256(state.tobytes()).hexdigest(),operations=a.operations)
 except FatalArithmetic as e:
  z=e.detail;flt=lambda u:struct.unpack('<f',bytes.fromhex(u)[::-1])[0];aa=Fraction(flt(z['a']));bb=Fraction(flt(z['b']));exact=aa*bb if z['operation']=='mul' else aa+bb;rr=Fraction(flt(z['result']))
  if z['flag']=='underflow_inexact' and not(abs(rr)<Fraction(1,2**126) and exact!=rr):raise RuntimeError('false underflow')
  rec=dict(head=h,chunk=chunk,status='FAIL_CANDIDATE_ORIGINAL_FATAL_UNDERFLOW' if z['flag']=='underflow_inexact' else 'FAIL_CANDIDATE_ORIGINAL_FATAL_OVERFLOW',detail=z,independent_fraction_tiny_inexact_verified=True)
 results.append(rec)
 (R/'RESULT.json').write_text(json.dumps(dict(status='INCOMPLETE_FULL_BLOCK',prepared_sha256=sha,tokens=128,heads=16,chunk_size=64,results=results,seconds=time.monotonic()-start,hardware_executed=False,full_block_pass=False,policy_changed=False),indent=2))
print(json.dumps(results,indent=2))
