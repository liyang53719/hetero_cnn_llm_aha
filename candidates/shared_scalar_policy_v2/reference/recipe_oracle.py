"""Pure rational interpretation of the pinned P7 NODE recipe, not exp oracle.
Not Chisel execution or official-Torch equivalence. Every FP32 node uses exact
rational arithmetic followed by nearest-even binary32 materialization.
"""
from fractions import Fraction as F
from pathlib import Path
import json, hashlib
C=(0x3f800000,0xbf317218,0x3e75fdf0,0xbd635847,0x3c1d955b,0xbaaec3ff,0x39218489,0xb77fe5fe)
S=(0x3f800000,0x3eaaaaab,0x3e4ccccd,0x3e124925,0x3de38e39,0x3dba2e8c,0x3d9d89d9,0x3d888889)
def val(x):
 e=(x>>23)&255; f=x&0x7fffff
 if e==255: raise ValueError('finite only')
 m=(0x800000|f) if e else f; p=e-150 if e else -149
 v=F(m*(1<<p),1) if p>=0 else F(m,1<<-p)
 return -v if x>>31 else v
def rnei(x):
 n,r=divmod(x.numerator,x.denominator)
 return n+(2*r>x.denominator or (2*r==x.denominator and bool(n&1)))
def rnd(v):
 neg=v<0;v=abs(v)
 if not v:return 0
 e=v.numerator.bit_length()-v.denominator.bit_length()
 if v<F(2)**e:e-=1
 if e<-126:return (int(neg)<<31)|rnei(v*F(2)**149)
 n=rnei(v*F(2)**(23-e))
 if n==1<<24:n>>=1;e+=1
 if e>127:raise ValueError('overflow')
 return (int(neg)<<31)|((e+127)<<23)|(n-(1<<23))
def node(trace,op,a,b):
 v={'mul':lambda:val(a)*val(b),'add':lambda:val(a)+val(b),'div':lambda:val(a)/val(b)}[op]()
 y=rnd(v)
 # exact cancellation uses +zero under RNE; product/div exact zero keep sign.
 if y==0 and op in ('mul','div'):y=(a^b)&0x80000000
 trace.append(dict(op=op,a=f'{a:08x}',b=f'{b:08x}',out=f'{y:08x}'))
 return y
def decay(a,t,legacy=False):
 mag=a&0x7fffffff
 if not legacy and mag>=0x42d00000:
  t.append(dict(op='proven_zero_guard',a=f'{a:08x}',out='00000000'));return 0
 z=node(t,'mul',mag,0x3fb8aa3b)
 if legacy and mag>=0x42a00000:return 0
 k=int(val(z)) if legacy else rnei(val(z));kf=rnd(F(k))
 t.append(dict(op='integer_trunc' if legacy else 'integer_rne',a=f'{z:08x}',out=k))
 if legacy:f=node(t,'add',z,kf^0x80000000)
 else:
  hi=node(t,'mul',kf,0x3f317200);r=node(t,'add',mag,hi^0x80000000)
  lo=node(t,'mul',kf,0x35bfbe8e);r=node(t,'add',r,lo^0x80000000)
  f=node(t,'mul',r,0x3fb8aa3b)
 p=C[7]
 for c in C[:7][::-1]:p=node(t,'add',node(t,'mul',p,f),c)
 if k<=126:return node(t,'mul',p,(127-k)<<23)
 return node(t,'mul',node(t,'mul',p,(253-k)<<23),0x00800000)
def soft(a,t,legacy=False):
 if a>>31 and a&0x7fffffff>=0x42a00000:raise ValueError('same pinned domain x<=-80 unsupported')
 if not a>>31 and a>0x41a00000:return a
 e=decay(a|0x80000000,t,legacy)
 y=node(t,'div',e,node(t,'add',0x40000000,e));z=node(t,'mul',y,y);p=S[7]
 for c in S[:7][::-1]:p=node(t,'add',node(t,'mul',p,z),c)
 return node(t,'add',0 if a>>31 else a,node(t,'mul',node(t,'mul',0x40000000,y),p))
def main():
 expected={0:0x3f800000,0x80000000:0x3f800000,0x80000001:0x3f800000,
 0xc2a00000:0x05bfecba,0xc2aeac4f:0x00800026,0xc2aeac50:0x007fffe6,
 0xc2aeac51:0x007fffa6,0xc2b72752:0x0001d7fd,0xc2b72754:0x0001d7fb,
 0xc2ce8ed0:1,0xc2cff1b3:1,0xc2cff1b4:1,0xc2cff1b5:0,0xff7fffff:0,
 0xc2a00001:0x05bfec5b}
 rows=[]
 for x,y in expected.items():
  t=[];out=decay(x,t)
  if out!=y:raise RuntimeError((hex(x),hex(out),hex(y)))
  rows.append(dict(policy=1,op=4,a=f'{x:08x}',out=f'{out:08x}',nodes=t,scope='archived candidate recipe literal; not general exp equality'))
 for x in [0xc29e0000,0xc1200000,0xc0880000,0xbdcccccd,0x80000000,0,0x3dcccccd,0x3f800000,0x41a00000,0x41a40000]:
  for p in (0,2):
   t=[];out=soft(x,t,p==0)
   if x==0xc0880000 and p==2 and out!=0x3c680dd6:raise RuntimeError('archived Softplus witness')
   rows.append(dict(policy=p,op=7,a=f'{x:08x}',out=f'{out:08x}',nodes=t,scope='node recipe exact-rational expected only'))
 for x in [0,0xbf800000,0xc29f0000,0xc2a00000,0xc2b72752,0x40000000]:
  t=[];out=decay(x,t,True);rows.append(dict(policy=0,op=4,a=f'{x:08x}',out=f'{out:08x}',nodes=t,scope='unchanged legacy recipe'))
 result={'status':'SOFTWARE_RECIPE_LITERAL_CROSSCHECK_ONLY','not_target_or_official_reference_run':True,'known_torch_difference':{'a':'c2a00001','candidate':'05bfec5b','archived_torch':'05bfec5a'},'cases':rows}
 path=Path(__file__).with_name('RECIPE_FIXTURE.json');path.write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({'cases':len(rows),'nodes':sum(len(x['nodes']) for x in rows),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}))
if __name__=='__main__':main()
