"""Actual M128 L3 arithmetic audit; no hardware execution and no norm rerun."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
from pathlib import Path
import json,hashlib,time,sys,resource,collections,ctypes,functools
resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3));resource.setrlimit(resource.RLIMIT_CPU,(590,590))
import numpy as np
from exact import value,rounded,div
R=Path(__file__).resolve().parent;ROOT=R.parents[1];D=ROOT/'round_20261110T0933/dense_real_reference';L=ROOT/'round_20261110T0933/l3_full';P=ROOT/'round_20261110T0833/l3_full_host_torch210_payload'
counts=collections.Counter();reports=[];pins={}
def sha(b):return hashlib.sha256(b).hexdigest()
def load(p,shape,dtype,expected):
 raw=p.read_bytes()
 if sha(raw)!=expected:raise ValueError('input pin '+str(p))
 pins[str(p.relative_to(ROOT))]=expected;return np.frombuffer(raw,dtype=dtype).reshape(shape)
m={s['name']:s for s in json.loads((P/'BINDING.json').read_text())['segments']};early={s['name']:s for s in json.loads((D/'RESULT.json').read_text())[1]['stages']};early.update({s['name']:s for s in json.loads((D/'QKNORM_RESULT.json').read_text())['stages']});late={s['name']:s for s in json.loads((L/'RESULT.json').read_text())['stages']}
def data(n):
 s=m[n];return load(P/s['file'],s['dims'],'<u2',s['sha256'])
def arr(n):
 if n in late:s=late[n];p=L/'local'/(n+'.bin')
 else:s=early[n];p=D/'profile2_local'/(n+'.bin')
 return load(p,s['shape'],np.dtype(s.get('dtype','uint16')),s['sha256'])
def fp(a):return (np.asarray(a,dtype='<u2').astype('<u4')<<16).view('<f4')
def bf(a):
 u=np.asarray(a,dtype='<f4').view('<u4');return ((u+0x7fff+((u>>16)&1))>>16).astype('<u2')
def same(name,y,expected):
 if not np.array_equal(y,expected):raise ValueError('output differs '+name)
 reports.append(dict(stage=name,outputs=int(y.size),sha256=sha(y.tobytes())));(R/'PROGRESS.json').write_text(json.dumps(reports,indent=2))
def dense(name,a,w,expected,scale=False):
 a=fp(a).astype(np.float64);w=fp(w).astype(np.float64)
 if not np.isfinite(a).all() or not np.isfinite(w).all():raise ValueError('nonfinite matrix input')
 acc=np.zeros((len(a),w.shape[1]),np.float32);c=collections.Counter();t=time.monotonic()
 for k in range(a.shape[1]):
  prod=a[:,k,None]*w[k,None,:];old=acc.astype(np.float64);s=prod+old;b=s-prod;e=(prod-(s-b))+(old-b)
  out=s.astype(np.float32);nx=(out.astype(np.float64)!=s)|(e!=0);uf=nx&(np.abs(out)<np.float32(2**-126));of=~np.isfinite(out)
  c['0']+=int(np.count_nonzero(~nx));c['1']+=int(np.count_nonzero(nx&~uf&~of));c['3']+=int(np.count_nonzero(uf));c['5']+=int(np.count_nonzero(of))
  if of.any():raise ValueError('nonfinite matrix '+name)
  acc=out
 y=bf(acc)
 if scale:y=bf(op(fp(y),np.float32(1/16),'mul'))
 same(name,y,expected);reports[-1].update(fma_steps=int(a.shape[0]*a.shape[1]*w.shape[1]),flag_counts=dict(c),seconds=time.monotonic()-t)
 return y
@functools.lru_cache(maxsize=200000)
def primitive(u,v,kind):
 if kind=='div':return div(u,v)
 x=value(u)+value(v) if kind=='add' else value(u)*value(v)
 neg=(u==0x80000000 and v==0x80000000) if kind=='add' else bool((u^v)>>31)
 return rounded(x,neg)
def op(a,b,kind):
 a,b=np.broadcast_arrays(np.asarray(a,dtype='<f4'),np.asarray(b,dtype='<f4'));out=np.empty(a.shape,dtype='<u4')
 for i,(u,v) in enumerate(zip(a.view('<u4').flat,b.view('<u4').flat)):
  y,f=primitive(int(u),int(v),kind);out.flat[i]=y;counts[kind+'_nodes']+=1;counts[kind+'_flag_'+str(f)]+=1
  if f&6:raise ValueError(('fatal scalar',kind,hex(int(u)),hex(int(v)),hex(y),f))
 return out.view('<f4')
CO=(0x3f800000,0xbf317218,0x3e75fdf0,0xbd635847,0x3c1d955b,0xbaaec3ff,0x39218489,0xb77fe5fe)
@functools.lru_cache(maxsize=65536)
def exp_one(u):
 mag=u&0x7fffffff
 if mag>=0x42a00000:return 0,()
 flags=[]
 def node(a,b,k):
  y,f=primitive(a,b,k);flags.append((k,f))
  if f&6:raise ValueError(('fatal exp',hex(u),k,f))
  return y
 z=node(mag,0x3fb8aa3b,'mul');k=int(value(z));negk=rounded(-value(rounded(k)[0]))[0];f=node(z,negk,'add');y=CO[-1]
 for c in reversed(CO[:-1]):y=node(node(y,f,'mul'),c,'add')
 return node(y,(127-k)<<23,'mul'),tuple(flags)
def exp_all(x):
 x=np.asarray(x,dtype='<f4');out=np.empty(x.shape,dtype='<u4')
 unique,inverse,mults=np.unique(x.view('<u4'),return_inverse=True,return_counts=True);vals=[]
 for u,n in zip(unique,mults):
  y,flags=exp_one(int(u));vals.append(y)
  for k,f in flags:counts[k+'_nodes']+=int(n);counts[k+'_flag_'+str(f)]+=int(n)
 out=np.array(vals,dtype='<u4')[inverse].reshape(x.shape);return out.view('<f4')
def sigmoid(g):
 x=fp(g)
 if np.any(x<=-80):raise ValueError('negative gate domain')
 e=exp_all(x);return op(op(np.float32(1),op(np.float32(1),e,'add'),'div'),np.where(np.signbit(x),e,np.float32(1)),'mul')
def main():
 lib=ctypes.CDLL('libm.so.6')
 if lib.fegetround()!=0:raise ValueError('RNE required')
 for n in ['q','k','v']:dense(n,arr('input_norm'),data(n+'_weight'),arr(n))
 for h in range(8):dense('qk'+str(h),arr('qr')[:,h],arr('kr')[:,h//4].T.copy(),arr('scaled_qk')[:,h],True)
 scores=arr('scaled_qk');allowed=np.arange(128)[None,None,:]<=np.arange(128)[:,None,None];mask=np.where(allowed,np.float32(0),np.array([0xff7f0000],'<u4').view('<f4')[0]);masked=bf(op(fp(scores),mask,'add'));same('mask',masked,arr('masked_score'));mx=np.max(fp(masked),axis=-1,keepdims=True);delta=op(fp(masked),-mx,'add');same('delta',delta.view('<u4'),arr('delta').view('<u4'))
 sentinel=(delta.view('<u4')==0xff7f0000)&~np.broadcast_to(allowed,delta.shape)
 if np.any((delta<=-80)&~sentinel):raise ValueError('non-sentinel exp domain')
 ex=exp_all(delta);same('exp',ex.view('<u4'),arr('exp').view('<u4'));total=np.zeros((128,8),'<f4')
 for key in range(128):total=op(total,ex[:,:,key],'add')
 prob=bf(op(ex,total[:,:,None],'div'));same('prob',prob,arr('prob'))
 for h in range(8):dense('pv'+str(h),prob[:,h],arr('v').reshape(128,2,256)[:,h//4],arr('context')[:,h])
 gate=arr('q').reshape(128,8,512)[...,256:];gated=bf(op(fp(bf(sigmoid(gate))),fp(arr('context')),'mul'));same('gated_context',gated,arr('gated_context'))
 dense('o',gated.reshape(128,2048),data('o_weight'),arr('o'));same('residual1',bf(op(fp(data('input')),fp(arr('o')),'add')),arr('residual1'))
 for n in ['gate','up']:dense(n,arr('post_norm'),data(n+'_weight'),arr(n))
 act=bf(op(sigmoid(arr('gate')),fp(arr('gate')),'mul'));silu=bf(op(fp(act),fp(arr('up')),'mul'));same('silu_mul',silu,arr('silu_mul'));dense('down',silu,data('down_weight'),arr('down'));same('output',bf(op(fp(arr('residual1')),fp(arr('down')),'add')),arr('output'))
 if lib.fegetround()!=0:raise ValueError('fenv changed')
 return dict(status='PASS_ACTUAL_L3_MATRIX_SOFTMAX_ELEMENTWISE_M128_MATH_ONLY',reports=reports,scalar_nodes_flags=dict(counts),verified_inputs=pins,limitations=['No hardware execution','Norm stages separately audited, not repeated','BF16 conversion exception flags not qualified','RoPE previously sampled only, not covered here','No NaN/Inf domain'])
if __name__=='__main__':
 t=time.monotonic()
 try:r=main()
 except Exception as e:r=dict(status='FAIL_OR_INCOMPLETE',error=repr(e),reports=reports,scalar_nodes_flags=dict(counts));raise
 finally:
  if 'r' in locals():r['seconds']=time.monotonic()-t;(R/'RESULT.json').write_text(json.dumps(r,indent=2));print(json.dumps(r),flush=True)
