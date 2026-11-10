"""TEMP M128 L3 full block value-path continuation, never hardware qualification."""
from pathlib import Path
import sys,json,hashlib,time,resource
resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3));resource.setrlimit(resource.RLIMIT_CPU,(590,590))
R=Path(__file__).resolve().parent;ROOT=R.parents[1];D=R.parent/'dense_real_reference';sys.path.insert(0,str(D))
import numpy as np
from run import rms
from candidate import dense
from original_prep_reference import fp,bf16,add,mul,div,exp_negative
h=lambda b:hashlib.sha256(b).hexdigest()
local=R/'local';local.mkdir(exist_ok=True);stages=[]
def keep(n,a):
 if not np.isfinite(fp(a) if a.dtype==np.dtype('<u2') else a).all():raise ValueError('nonfinite '+n)
 raw=a.tobytes();(local/(n+'.bin')).write_bytes(raw);stages.append(dict(name=n,sha256=h(raw),shape=list(a.shape),dtype=str(a.dtype)));(R/'PROGRESS.json').write_text(json.dumps(stages,indent=2));return a
def load(n,shape):return np.fromfile(D/'profile2_local'/(n+'.bin'),dtype='<u2').reshape(shape)
def rope(x,trig):
 y=x.copy();a=fp(x[...,:32]);b=fp(x[...,32:64]);c=fp(trig[:,None,:32]);s=fp(trig[:,None,32:]);ec=fp(bf16(mul(a,c)));bs=fp(bf16(mul(b,s)));es=fp(bf16(mul(a,s)));bc=fp(bf16(mul(b,c)))
 y[...,:32]=bf16(add(ec,-bs));y[...,32:64]=bf16(add(es,bc));return y
def project(a,w):return bf16(dense(a.astype('<u4')<<16,w.astype('<u4')<<16).view('<f4'))
def sigmoid(x):
 x=fp(x)
 if np.any(x<=-80):raise ValueError('negative gate outside original exp domain')
 e=exp_negative(x);return mul(div(np.float32(1),add(np.float32(1),e)),np.where(np.signbit(x),e,np.float32(1)))
def main():
 p=ROOT/'round_20261110T0833/l3_full_host_torch210_payload';m=json.loads((p/'BINDING.json').read_text());data={}
 for s in m['segments']:
  raw=(p/s['file']).read_bytes()
  if h(raw)!=s['sha256']:raise ValueError('payload pin')
  data[s['name']]=np.frombuffer(raw,dtype='<u2').reshape(s['dims'])
 # Verify predecessor hashes before consuming computed local outputs.
 expected={s['name']:s['sha256'] for s in json.loads((D/'RESULT.json').read_text())[1]['stages']}
 expected.update({s['name']:s['sha256'] for s in json.loads((D/'QKNORM_RESULT.json').read_text())['stages']})
 for n in ['q','k','v','qn','kn']:
  if h((D/'profile2_local'/(n+'.bin')).read_bytes())!=expected[n]:raise ValueError('predecessor hash '+n)
 q=keep('qr',rope(load('qn',(128,8,256)),data['trig']));k=keep('kr',rope(load('kn',(128,2,256)),data['trig']));v=load('v',(128,2,256));keep('cache',np.stack([k,v]))
 scores=np.empty((128,8,128),dtype='<u2');context=np.empty((128,8,256),dtype='<u2')
 for head in range(8):scores[:,head]=bf16(mul(fp(project(q[:,head],k[:,head//4].T.copy())),np.float32(1/16)))
 keep('scaled_qk',scores);logits=fp(scores);allowed=np.arange(128)[None,None,:]<=np.arange(128)[:,None,None]
 mask=np.where(allowed,np.float32(0),np.array([0xff7f0000],dtype='<u4').view('<f4')[0]); masked=keep('masked_score',bf16(add(logits,mask))); logits=fp(masked); maximum=np.max(logits,axis=-1,keepdims=True);delta=add(logits,-maximum)
 sentinel=(delta.view('<u4')==0xff7f0000)&~np.broadcast_to(allowed,delta.shape)
 if np.any((delta<=-80)&~sentinel):raise ValueError('non-sentinel delta outside original exp domain')
 keep('delta',delta)
 # Original exp recipe rejects nonzero disallowed-domain shifts, not a libm softmax.
 if np.any(np.abs(delta[ np.broadcast_to(allowed,delta.shape)])>=80):raise ValueError('softmax allowed delta outside original domain')
 e=exp_negative(delta);
 if np.any((e==0)&~sentinel):raise ValueError('unexpected zero exp')
 keep('exp',e);total=np.zeros((128,8),dtype='<f4')
 for key in range(128):total=add(total,e[:,:,key])
 prob=keep('prob',bf16(div(e,total[:,:,None])))
 for head in range(8):context[:,head]=project(prob[:,head],v[:,head//4])
 keep('context',context);gate=load('q',(128,8,512))[...,256:];gated=keep('gated_context',bf16(mul(fp(bf16(sigmoid(gate))),fp(context)))).reshape(128,2048)
 o=keep('o',project(gated,data['o_weight']));res=keep('residual1',bf16(add(fp(data['input']),fp(o))));norm=keep('post_norm',rms(res,data['post_gamma']))
 gate=keep('gate',project(norm,data['gate_weight']));up=keep('up',project(norm,data['up_weight']));act=bf16(mul(sigmoid(gate),fp(gate)));silu=keep('silu_mul',bf16(mul(fp(act),fp(up))));down=keep('down',project(silu,data['down_weight']));out=keep('output',bf16(add(fp(res),fp(down))))
 return dict(status='CANDIDATE_FULL_L3_M128_VALUE_PATH_EXECUTED',tokens=128,stages=stages,output_sha256=h(out.tobytes()),flags='NOT_QUALIFIED',hardware=False,full_hardware_pass=False)
if __name__=='__main__':
 t=time.monotonic()
 try:r=main()
 except Exception as e:r=dict(status='FAIL_CANDIDATE',error=repr(e),stages=stages)
 r['seconds']=time.monotonic()-t;(R/'RESULT.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))
