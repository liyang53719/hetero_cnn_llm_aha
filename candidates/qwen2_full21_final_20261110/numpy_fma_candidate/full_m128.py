"""CANDIDATE_REFERENCE dependency scheduler, resumes validated RMS/Q checkpoints.
Stops unresolved RoPE table identity, never substitutes newly invented tables.
"""
import os,sys,pathlib,json,hashlib,time,resource
resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
resource.setrlimit(resource.RLIMIT_CPU,(1800,1800))
import numpy as np
p=pathlib.Path(__file__).resolve().parent;root=p.parents[1]
sys.path.insert(0,str(p.parent/'legacy_python'))
import legacy_reference as ref
from candidate import dense
out=p/'full_m128';out.mkdir(exist_ok=True)
(out/'IDENTITY.json').write_text(json.dumps(dict(pid=os.getpid(),boot=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),start_ticks=pathlib.Path('/proc/self/stat').read_text().split()[21],cpu_limit_s=1800,address_space_limit_bytes=2*1024**3)))
previous=json.loads((p/'REAL_Q_RESULT.json').read_text());payload=root/'round_20261110T0733/qwen2_host_payload';binding=json.loads((payload/'REAL_INPUT_BINDING.json').read_text());buffers={};progress=[]
shapes={'wq':(1536,1536),'wk':(1536,256),'wv':(1536,256),'wo':(1536,1536),'wg':(1536,8960),'wu':(1536,8960),'wd':(8960,1536),'x':(128,1536),'gamma0':(1536,),'gamma1':(1536,),'bq':(1536,),'bk':(256,),'bv':(256,)}
for entry in binding['records']:
 name=entry['name'];f=payload/(name+'.f32le')
 if hashlib.sha256(f.read_bytes()).hexdigest()!=entry['sha256']:raise ValueError('payload pin '+name)
 buffers[name]=np.memmap(f,dtype='<u4',mode='r',shape=shapes[name])
for name,file,sha in [('norm0','norm0.local.f32',previous['norm_sha256']),('q0','q0.local.f32',previous['q_sha256'])]:
 f=p/file
 if hashlib.sha256(f.read_bytes()).hexdigest()!=sha:raise ValueError('checkpoint '+name)
 buffers[name]=np.memmap(f,dtype='<u4',mode='r',shape=(128,1536));progress.append(dict(buffer=name,status='RESUMED_HASH_VERIFIED',sha256=sha))

import operators as ops
# Resume all independently finished pre-RoPE branches, with exact stored hash.
old=json.loads((p/'resume_m128/RESULT.json').read_text())
for r in old['progress']:
 if r['buffer'] in buffers:continue
 f=p/'resume_m128'/(r['buffer']+'.local.f32')
 if hashlib.sha256(f.read_bytes()).hexdigest()!=r['sha256']:raise ValueError('branch checkpoint '+r['buffer'])
 buffers[r['buffer']]=np.memmap(f,dtype='<u4',mode='r',shape=tuple(r['shape']))
 progress.append(dict(r,status='RESUMED_HASH_VERIFIED'))
trig=json.loads((p/'TRIG_MANIFEST.json').read_text())
for name in ['cos','sin']:
 f=p/(name+'.local.f32')
 if hashlib.sha256(f.read_bytes()).hexdigest()!=trig['sha256'][str(f)]:raise ValueError('trig pin')
 buffers[name]=np.memmap(f,dtype='<u4',mode='r',shape=(1024,64))[:128]
budget=ref.Budget(100000000)
for name,op,args,dst in ref.SCHEDULE:
 if dst in buffers:continue
 (out/'ACTIVE_STAGE.json').write_text(json.dumps(dict(stage=name,op=op,classification='CANDIDATE_REFERENCE',matrix_status_flags='NOT_QUALIFIED')))
 t=time.monotonic()
 try:
  values=[buffers[x] for x in args]
  if op=='dense':value=dense(*values)
  elif op=='add':value=ref.binary_add(*values,budget)
  elif op=='rope':
   a,c,s=values;value=ref.rope(a.reshape(128,-1,128),c,s,budget).reshape(a.shape)
  elif op=='append':value=tuple(x.copy() for x in values)
  elif op in ('qk','pv'):value=getattr(ops,op)(*values,budget,head_dim=128)
  else:value=getattr(ops,op)(*values,budget)
  arrays=value if isinstance(value,tuple) else (value,)
  hashes=[]
  for i,a in enumerate(arrays):
   f=out/(dst+('.'+str(i) if len(arrays)>1 else '')+'.local.f32');a.astype('<u4').tofile(f);hashes.append(hashlib.sha256(f.read_bytes()).hexdigest())
  buffers[dst]=value
  progress.append(dict(stage=name,buffer=dst,status='CANDIDATE_REFERENCE_STAGE_ONLY',seconds=time.monotonic()-t,sha256=hashes))
  (out/'PROGRESS.json').write_text(json.dumps(progress,indent=2));print(json.dumps(progress[-1]),flush=True)
 except Exception as exc:
  report=dict(status='FAIL_OR_INCOMPLETE_REFERENCE_STAGE',classification='CANDIDATE_REFERENCE',stage=name,error_type=type(exc).__name__,error=str(exc),progress=progress,full21_completed=False,hardware_pass=0)
  (out/'RESULT.json').write_text(json.dumps(report,indent=2));raise
report=dict(status='CANDIDATE_REFERENCE_FULL21_EXECUTED',classification='CANDIDATE_REFERENCE',tokens=128,progress=progress,full21_completed=True,matrix_status_flags='NOT_QUALIFIED',all_outputs_fraction_verified=False,hardware_pass=0)
(out/'RESULT.json').write_text(json.dumps(report,indent=2));print(report['status'],flush=True)
