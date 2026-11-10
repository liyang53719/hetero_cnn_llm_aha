"""TEMP independent real-weight producer chain; no hardware acceptance.
RMS index/order follows original GdnRuntimeRmsNormOwnerV3, not ascending sum.
Matrix bit candidate and NumPy scalar flags remain unqualified.
"""
from pathlib import Path
import numpy as np,json,hashlib,time
from candidate import dense
from original_prep_reference import fp,bf16,add,mul,div,recipe
from conv_reference import conv4
R=Path(__file__).resolve().parent
ROOT=R.parents[1]
def sha(b):return hashlib.sha256(b).hexdigest()
def rms(x,w):
 x=fp(x);w=fp(w);m,h=x.shape
 if h not in (1024,2048):raise ValueError('original width')
 partial=np.zeros((m,32),dtype='<f4')
 for base in range(0,h,512):
  acc=np.zeros_like(partial)
  for term in range(16):
   indices=base+term*32+np.array([(i%4)*8+i//4 for i in range(32)])
   acc=add(acc,mul(x[:,indices],x[:,indices]))
  partial=add(partial,acc)
 lanes=np.zeros((m,8),dtype='<f4')
 for residue in range(4):lanes=add(lanes,partial[:,np.arange(8)*4+residue])
 total=np.zeros((m,1),dtype='<f4')
 for lane in range(8):total=add(total,lanes[:,lane:lane+1])
 inv=div(np.float32(1),np.sqrt(add(mul(total,np.float32(1/h)),np.float32(1e-6)),dtype=np.float32))
 return bf16(mul(mul(x,inv),add(np.float32(1),w)))
def run(profile,path):
 manifest=json.loads((path/'BINDING.json').read_text());data={}
 for s in manifest['segments']:
  raw=(path/s['file']).read_bytes()
  if sha(raw)!=s['sha256'] or len(raw)!=s['bytes']:raise ValueError('payload drift '+s['name'])
  data[s['name']]=np.frombuffer(raw,dtype='<u2' if s['dtype']==5 else '<f4').reshape(s['dims'])
 out=R/('profile'+str(profile)+'_local');out.mkdir(exist_ok=True);stages=[]
 def keep(name,x,t):
  raw=x.tobytes();(out/(name+'.bin')).write_bytes(raw)
  stages.append(dict(name=name,shape=list(x.shape),dtype=str(x.dtype),sha256=sha(raw),seconds=time.monotonic()-t))
  (R/('profile'+str(profile)+'_progress.json')).write_text(json.dumps(stages,indent=2));return x
 t=time.monotonic();norm=keep('input_norm',rms(data['input'],data['input_gamma']),t)
 for name in (['qkv','z','ab'] if profile==1 else ['q','k','v']):
  t=time.monotonic();words=dense(norm.astype('<u4')<<16,data[name+'_weight'].astype('<u4')<<16)
  data[name]=keep(name,bf16(words.view('<f4')),t)
 if profile==1:
  t=time.monotonic();conv,hist=conv4(data['qkv'],data['conv_weight']);keep('conv',conv,t);keep('history_out',hist,t)
  t=time.monotonic();rows=[]
  for token in range(128):
   q,k,v=conv[token].reshape(3,16,128);ab=data['ab'][token]
   outputs=recipe(q,k,v,ab[:16],ab[16:],data['a_log'].reshape(16),data['dt_bias'].reshape(16),recurrent_mode=False)
   rows.append(np.concatenate([x.reshape(-1) for x in outputs]))
  keep('prepared',np.stack(rows),t)
 return dict(profile=profile,status='CANDIDATE_REFERENCE_PRODUCERS_EXECUTED',tokens=128,input_origin='existing bound caller hidden input; not claimed official model embedding',matrix_flags='NOT_QUALIFIED',scalar_flags='NOT_QUALIFIED',hardware_executed=False,full_block_pass=False,stages=stages)
if __name__=='__main__':
 result=[]
 for p,n in [(1,'profile1_real_host_payload'),(2,'l3_full_host_torch210_payload')]:
  try:result.append(run(p,ROOT/'round_20261110T0833'/n))
  except Exception as e:result.append(dict(profile=p,status='FAIL_REFERENCE',error=repr(e)))
  (R/'RESULT.json').write_text(json.dumps(result,indent=2))
 print(json.dumps(result,indent=2))
