from full_audit import *
from integer_oracle import fma
from fractions import Fraction
import struct
av=bf16_words(load(locate('norm0'),(128,1536)));wv=bf16_words(load(payload/'wq.f32le',(1536,1536)))
af=av.view('<f4').astype(np.float64);wf=wv.view('<f4').astype(np.float64);acc=np.zeros((128,1536),np.float32)
for k in range(1536):
 s,e=two_sum(af[:,k,None]*wf[k,None,:],acc.astype(np.float64));out=s.astype(np.float32)
 if np.any(e!=0):
  r,c=map(int,np.argwhere(e!=0)[0]);a,b,z=map(int,[av[r,k],wv[k,c],acc.view('<u4')[r,c]])
  got=int(out.view('<u4')[r,c]);value,flags=fma(a,b,z)
  if got!=value:raise ValueError('witness value')
  fp=lambda u:struct.unpack('<f',struct.pack('<I',u))[0]
  exact=Fraction(fp(a))*Fraction(fp(b))+Fraction(fp(z))
  if Fraction(float(s[r,c]))+Fraction(float(e[r,c]))!=exact:raise ValueError('residual')
  result=dict(stage='q',row=r,column=c,k=k,a=f'{a:08x}',b=f'{b:08x}',c=f'{z:08x}',result=f'{got:08x}',exact_flags=flags,fp64_sum_hex=float(s[r,c]).hex(),residual_hex=float(e[r,c]).hex(),naive_compare_inexact=bool(np.float64(out[r,c])!=s[r,c]),exact_oracle_and_fraction_verified=True)
  (O/'FIRST_ACTUAL_RESIDUAL.json').write_text(json.dumps(result,indent=2));print(json.dumps(result));break
 acc=out
else:raise ValueError('expected observed residual not found')
