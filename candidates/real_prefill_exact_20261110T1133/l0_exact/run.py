"""Real M128 L0 upstream value/flags audit; no DUT or fatal-policy alteration."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
from pathlib import Path
import sys,json,time,hashlib,collections,ctypes,math,resource
resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3));resource.setrlimit(resource.RLIMIT_CPU,(590,590))
import numpy as np
import norm_audit as norm
from exact import div
R=Path(__file__).parent;ROOT=R.parents[1];D=ROOT/'round_20261110T0933/dense_real_reference';P=ROOT/'round_20261110T0833/profile1_real_host_payload'
sys.path.insert(0,str(D));from original_prep_reference import fp,bf16
counts=collections.Counter();verified={};reports=[];witnesses=[]
def sha(b):return hashlib.sha256(b).hexdigest()
def checked(p,shape,pin,dtype='<u2'):
 b=p.read_bytes()
 if sha(b)!=pin:raise ValueError('hash drift '+str(p))
 verified[str(p.relative_to(ROOT))]=pin
 return np.frombuffer(b,dtype=dtype).reshape(shape)
def two(a,b):
 s=a+b;bb=s-a;return s,(a-(s-bb))+(b-bb)
def flags(out,total,err=0,name='',allow_underflow=False):
 nx=(out.astype(np.float64)!=total)|(np.asarray(err)!=0);uf=nx&(np.abs(out)<np.float32(2**-126));ov=~np.isfinite(out)
 counts[name+'_0']+=int(np.count_nonzero(~nx));counts[name+'_1']+=int(np.count_nonzero(nx&~uf&~ov));counts[name+'_3']+=int(np.count_nonzero(uf));counts[name+'_5']+=int(np.count_nonzero(ov))
 if uf.any() and not witnesses: witnesses.append(dict(stage=name,allow_underflow=allow_underflow,first_output_word=hex(int(out.view('<u4')[tuple(np.argwhere(uf)[0])])),count=int(np.count_nonzero(uf))))
 if (ov|(uf if not allow_underflow else False)).any():raise ValueError('fatal arithmetic '+name)
 return out
# Exact binary32 multiplication product <=48bits. Addition uses exact TwoSum
# and binary32+binary32 double-round value theorem (same exponent split proof).
def mul(a,b,allow_underflow=False):
 a,b=np.broadcast_arrays(np.asarray(a,np.float32),np.asarray(b,np.float32));z=a.astype(np.float64)*b.astype(np.float64)
 return flags(z.astype(np.float32),z,name='conv_tap_mul_ieee' if allow_underflow else 'scalar_mul',allow_underflow=allow_underflow)
def add(a,b):
 a,b=np.broadcast_arrays(np.asarray(a,np.float32),np.asarray(b,np.float32));z,e=two(a.astype(np.float64),b.astype(np.float64))
 return flags(z.astype(np.float32),z,e,'scalar_add')
def dense(x,w,expected,name):
 a=fp(x).astype(np.float64);b=fp(w).astype(np.float64);acc=np.zeros(expected.shape,np.float32);t=time.monotonic()
 for k in range(a.shape[1]):
  z,e=two(a[:,k,None]*b[k,None,:],acc.astype(np.float64));acc=flags(z.astype(np.float32),z,e,'fma_'+name)
 if not np.array_equal(bf16(acc),expected):raise ValueError('Dense mismatch '+name)
 reports.append(dict(stage=name,ordered_fma_steps=x.shape[0]*w.shape[0]*w.shape[1],outputs=expected.size,output_sha256=sha(expected.tobytes()),seconds=time.monotonic()-t));save_progress()
def expneg(x):
 if np.any(np.abs(x)>=80):raise ValueError('exp saturation requires separate original-domain audit')
 t=mul(np.abs(x),np.float32(1/math.log(2)));k=t.astype(np.int32);f=add(t,-k.astype(np.float32));c=[np.float32((-math.log(2))**i/math.factorial(i)) for i in range(8)];y=np.full(x.shape,c[7],np.float32)
 for i in range(6,-1,-1):y=add(mul(y,f),c[i])
 return mul(y,((127-k).astype('<u4')<<23).view('<f4'))
def reciprocal(a):
 u,inv=np.unique(a.view('<u4'),return_inverse=True);v=[]
 for x in u:
  val,flag=div(0x3f800000,int(x));counts['scalar_div_'+str(flag)]+=int(np.count_nonzero(inv==len(v)));v.append(val)
 y=np.array(v,dtype='<u4')[inv].reshape(a.shape).view('<f4')
 if not np.array_equal(y.view('<u4'),np.divide(np.float32(1),a,dtype=np.float32).view('<u4')):raise ValueError('Div candidate mismatch')
 return y,len(u)
def save_progress(): (R/'PROGRESS.json').write_text(json.dumps(reports,indent=2))
def main():
 lib=ctypes.CDLL('libm.so.6');lib.fegetround.restype=ctypes.c_int
 if lib.fegetround()!=0:raise ValueError('requires RNE')
 seg={s['name']:s for s in json.loads((P/'BINDING.json').read_text())['segments']};old={s['name']:s for s in json.loads((D/'RESULT.json').read_text())[0]['stages']}
 def data(n):s=seg[n];return checked(P/s['file'],s['dims'],s['sha256'],'<u2' if s['dtype']==5 else '<f4')
 def olddata(n):s=old[n];return checked(D/'profile1_local'/(n+'.bin'),s['shape'],s['sha256'])
 norm.norm('L0_input_rms',data('input'),data('input_gamma'),olddata('input_norm'));reports.append(dict(stage='input_rms',exact_stages=norm.stages,exact_nodes=dict(norm.counts)));save_progress()
 x=olddata('input_norm')
 for n in ['qkv','z','ab']:dense(x,data(n+'_weight'),olddata(n),n)
 qkv=olddata('qkv');w=fp(data('conv_weight'));hist=np.zeros((6144,4),dtype='<u2');out=[];unique_divs=0
 for token,raw in enumerate(qkv):
  acc=np.zeros(6144,np.float32)
  for tap in range(4):acc=add(acc,mul(fp(raw if tap==3 else hist[:,tap+1]),w[:,tap],allow_underflow=True))
  conv=fp(bf16(acc));e=expneg(conv);inv,n=reciprocal(add(np.float32(1),e));unique_divs+=n
  activation=mul(mul(inv,np.where(conv<0,e,np.float32(1))),conv);out.append(bf16(activation));hist[:,:3]=hist[:,1:].copy();hist[:,3]=raw
 y=np.stack(out)
 if not np.array_equal(y,olddata('conv')) or not np.array_equal(hist,olddata('history_out')):raise ValueError('Conv output/history mismatch')
 reports.append(dict(stage='conv4_silu',tokens=128,channels=6144,outputs=y.size,unique_div_inputs_per_token_total=unique_divs,output_sha256=sha(y.tobytes()),history_sha256=sha(hist.tobytes())));save_progress()
 if lib.fegetround()!=0:raise ValueError('RNE changed')
 return dict(status='PASS_REAL_M128_L0_UPSTREAM_MATH_AUDIT',reports=reports,flags=dict(counts),underflow_witnesses=witnesses,verified_inputs=verified,scope='RMS exact Fraction; QKV/Z/AB ordered FMA; Conv4 separate mul/add and original polynomial/sigmoid with exact Div; no hardware; BF16 conversion flags excluded',hardware=False,full_block_pass=False,underflow_downstream_unchanged=True)
if __name__=='__main__':
 t=time.monotonic()
 try:r=main()
 except Exception as e:r=dict(status='FAIL_AUDIT',error=repr(e),reports=reports,flags=dict(counts))
 r['seconds']=time.monotonic()-t;(R/'RESULT.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2));sys.exit(0 if r['status'].startswith('PASS') else 1)
