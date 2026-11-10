"""Full actual Dense ordered-K audit. FP64 TwoSum recovers exact rounding error.
No BLAS, no new hardware, no changed arithmetic or weights. See PROOF_CN.md.
"""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
import resource
resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3));resource.setrlimit(resource.RLIMIT_CPU,(590,590))
from pathlib import Path
import sys,json,hashlib,time,ctypes
import numpy as np
R=Path(__file__).resolve().parents[2];O=Path(__file__).parent
p=R/'round_20261110T0833/numpy_fma_candidate';payload=R/'round_20261110T0733/qwen2_host_payload'
sys.path.insert(0,str(p));from candidate import bf16_words
bindings=json.loads((payload/'REAL_INPUT_BINDING.json').read_text());pins={payload/(x['name']+'.f32le'):x['sha256'] for x in bindings['records']}
prior=json.loads((p/'REAL_Q_RESULT.json').read_text());pins[p/'norm0.local.f32']=prior['norm_sha256'];pins[p/'q0.local.f32']=prior['q_sha256']
for x in json.loads((p/'full_m128/RESULT.json').read_text())['progress']:
 if x.get('stage') and x['status']=='CANDIDATE_REFERENCE_STAGE_ONLY' and len(x['sha256'])==1:pins[p/'full_m128'/(x['buffer']+'.local.f32')]=x['sha256'][0]
for x in json.loads((p/'resume_m128/RESULT.json').read_text())['progress']:
 f=p/'resume_m128'/(x['buffer']+'.local.f32')
 if f.exists():pins[f]=x['sha256']
verified={}
def load(f,shape):
 actual=hashlib.sha256(f.read_bytes()).hexdigest()
 if actual!=pins[f]:raise ValueError('hash '+str(f))
 verified[str(f.relative_to(R))]=actual
 return np.memmap(f,dtype='<u4',mode='r',shape=shape)
def locate(n):
 for d in [p,p/'full_m128',p/'resume_m128']:
  f=d/(n+'.local.f32')
  if f.exists():return f
 raise ValueError(n)
def two_sum(a,b):
 s=a+b;bb=s-a
 err=(a-(s-bb))+(b-bb)
 return s,err
stages=[('q','norm0','wq','q0',1536,1536),('k','norm0','wk','k0',1536,256),('v','norm0','wv','v0',1536,256),('out','att','wo','proj',1536,1536),('gate','norm1','wg','gate',1536,8960),('up','norm1','wu','up',1536,8960),('down','act','wd','down',8960,1536)]
def main():
 reports=[];begin=time.monotonic()
 libm=ctypes.CDLL("libm.so.6");libm.fegetround.restype=ctypes.c_int
 if libm.fegetround()!=0:raise ValueError("Requires verified glibc FE_TONEAREST=0, no fenv mutation")
 from integer_oracle import fma
 from fractions import Fraction
 import struct
 witnesses=[]
 for name,an,wn,on,k,n in stages:
  av=bf16_words(load(locate(an),(128,k))).view('<f4').astype(np.float64);wv=bf16_words(load(payload/(wn+'.f32le'),(k,n))).view('<f4').astype(np.float64);expected=load(locate(on),(128,n))
  acc=np.zeros((128,n),np.float32);counts=np.zeros(32,dtype=np.int64);residuals=0;t=time.monotonic()
  for j in range(k):
   prod=av[:,j,None]*wv[j,None,:]
   total,err=two_sum(prod,acc.astype(np.float64))
   with np.errstate(over='ignore',under='ignore'):out=total.astype(np.float32)
   nx=(out.astype(np.float64)!=total)|(err!=0)
   uf=nx&(np.abs(out)<np.float32(2.0**-126));ov=~np.isfinite(out)
   counts[0]+=np.count_nonzero(~nx);counts[1]+=np.count_nonzero(nx&~uf&~ov);counts[3]+=np.count_nonzero(uf);counts[5]+=np.count_nonzero(ov)
   residuals+=int(np.count_nonzero(err))
   hit=(err!=0)&(out.astype(np.float64)==total)
   if hit.any() and not witnesses:
    r,c=map(int,np.argwhere(hit)[0]);aa=int(bf16_words(load(locate(an),(128,k)))[r,j]);bb=int(bf16_words(load(payload/(wn+'.f32le'),(k,n)))[j,c]);cc=int(acc.view('<u4')[r,c]);value,flags=fma(aa,bb,cc)
    got=int(out.view('<u4')[r,c]);observed=int(nx[r,c])|(2 if uf[r,c] else 0)|(4 if ov[r,c] else 0)
    if (got,observed)!=(value,flags):raise ValueError('exact witness mismatch')
    fp=lambda u:struct.unpack('<f',struct.pack('<I',u))[0]
    exact=Fraction(fp(aa))*Fraction(fp(bb))+Fraction(fp(cc))
    if Fraction(float(total[r,c]))+Fraction(float(err[r,c]))!=exact:raise ValueError('witness residual mismatch')
    witnesses.append(dict(stage=name,row=r,column=c,k=j,a=f'{aa:08x}',b=f'{bb:08x}',c=f'{cc:08x}',output=f'{got:08x}',flags=flags,naive_fp64_compare_inexact=False,exact_residual_hex=float(err[r,c]).hex(),independent_integer_and_fraction_verified=True))
   if ov.any():raise ValueError('nonfinite actual accumulator '+name+':'+str(j))
   acc=out
  if not np.array_equal(acc.view('<u4'),expected):raise ValueError('full output mismatch '+name)
  report=dict(stage=name,steps=128*k*n,outputs=128*n,flag_counts={str(i):int(c) for i,c in enumerate(counts) if c},fp64_nonzero_residuals=residuals,seconds=time.monotonic()-t,status='FULL_ORDERED_DENSE_VALUE_FLAGS_AUDITED_NO_HARDWARE')
  reports.append(report);(O/'PROGRESS.json').write_text(json.dumps(reports,indent=2));print(json.dumps(report),flush=True)
 if libm.fegetround()!=0:raise ValueError('rounding mode changed')
 result=dict(rounding_mode='glibc FE_TONEAREST=0 checked before/after, unchanged',actual_missed_inexact_witnesses=witnesses,status='FULL_SEVEN_DENSE_VALUE_FLAGS_AUDITED_NO_HARDWARE',reports=reports,verified_inputs=verified,seconds=time.monotonic()-begin,scope='Only seven Dense matrices; no QK/PV or scalar flags; mathematical proof and independent exact tests, no Chisel/RTL comparison')
 (O/'RESULT.json').write_text(json.dumps(result,indent=2))
if __name__=='__main__':main()
