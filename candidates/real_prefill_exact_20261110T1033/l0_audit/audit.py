"""Exact dependency cones from frozen Conv/AB boundaries to L0 failing nodes.
No inferred full-model/hardware PASS. Fraction arithmetic, every FP32 node RNE.
"""
from pathlib import Path
import sys,json,hashlib,struct,resource,time
from fractions import Fraction
R=Path(__file__).resolve().parent;ROOT=R.parents[1]
sys.path.insert(0,str(ROOT/'round_20261110T0833/legacy_python'))
from rational_oracle import round_fraction
from legacy_reference import fraction,Budget
from operators import sqrt as exact_sqrt
import numpy as np
resource.setrlimit(resource.RLIMIT_AS,(2<<30,2<<30));resource.setrlimit(resource.RLIMIT_CPU,(590,590))
B=Budget(1000000);nodes=0
W=lambda f:struct.unpack('<I',struct.pack('<f',float(f)))[0]
def op(a,b,kind):
 global nodes;nodes+=1;x=fraction(a);y=fraction(b)
 z=x*y if kind=='mul' else x/y if kind=='div' else x+y
 return round_fraction(z)
def add(a,b):return op(a,b,'add')
def mul(a,b):return op(a,b,'mul')
def div(a,b):return op(a,b,'div')
def neg(a):return a^0x80000000
C=[0x3f800000,0xbf317218,0x3e75fdf0,0xbd635847,0x3c1d955b,0xbaaec3ff,0x39218489,0xb77fe5fe]
def exp(a):
 a&=0x7fffffff
 if fraction(a)>=80:return 0
 z=mul(a,0x3fb8aa3b);k=int(fraction(z));f=add(z,neg(W(k)));y=C[7]
 for c in reversed(C[:7]):y=add(mul(y,f),c)
 return mul(y,(127-k)<<23)
def bf(a):return ((a+0x7fff+((a>>16)&1))>>16)<<16
def soft(a):
 if fraction(a)>20:return a
 e=exp(a);y=div(e,add(W(2),e));s=mul(y,y);h=W(1/15)
 for n in [13,11,9,7,5,3,1]:h=add(mul(h,s),W(1/n))
 return add(a if fraction(a)>0 else 0,mul(mul(W(2),y),h))
def norm(row,scale=False):
 acc=0
 for v in row:acc=add(acc,mul(int(v),int(v)))
 inv=div(W(1),exact_sqrt(add(acc,W(1e-6)),B));out=[mul(int(v),inv) for v in row]
 return [mul(x,W(1/(128**0.5))) for x in out] if scale else out
pins={}
def raw(p,expected=None):
 p=Path(p);b=p.read_bytes();h=hashlib.sha256(b).hexdigest();pins[str(p.relative_to(ROOT))]=h
 if expected and h!=expected:raise ValueError('pin mismatch '+str(p))
 return b
D=ROOT/'round_20261110T0933/dense_real_reference';stage={x['name']:x['sha256'] for x in json.loads(raw(D/'profile1_progress.json'))}
conv=np.frombuffer(raw(D/'profile1_local/conv.bin',stage['conv']),dtype='<u2').astype('<u4').reshape(128,3,16,128)<<16
ab=np.frombuffer(raw(D/'profile1_local/ab.bin',stage['ab']),dtype='<u2').astype('<u4').reshape(128,32)<<16
prep=np.frombuffer(raw(D/'profile1_local/prepared.bin',stage['prepared']),dtype='<u4').reshape(128,6400)
P=ROOT/'round_20261110T0833/profile1_real_host_payload';manifest=json.loads(raw(P/'BINDING.json'));data={}
for s in manifest['segments']:
 if s['name'] in ['a_log','dt_bias']:
  b=raw(P/s['file'],s['sha256']);data[s['name']]=np.frombuffer(b,dtype='<u4' if s['name']=='a_log' else '<u2').astype('<u4').reshape(16)
results=[];start=time.monotonic()
for head,row,col,phase in [(0,52,28,'6_intra'),(3,16,25,'2_derived'),(11,24,0,'2_derived'),(13,25,0,'2_derived')]:
 # For heads11/13 use the actual failure coordinate from frozen result.
 recorded=next(x for x in json.loads(raw(ROOT/'round_20261110T0933/l0_full/RESULT.json'))['results'] if x['head']==head)['detail']
 row,col=recorded['index'];cum=[];acc=0;decays=[]
 for t in range(row+1):
  al=int(data['a_log'][head]);e=exp(al);ae=e if al>>31 else div(W(1),e)
  g=mul(neg(ae),soft(add(int(ab[t,head]),int(data['dt_bias'][head])<<16)))
  if g!=int(prep[t,6144+head*16]):raise ValueError('prepared decay mismatch')
  decays.append(g);acc=add(acc,g);cum.append(acc)
 if phase=='6_intra':
  q=norm(conv[row,0,head],True);k=norm(conv[col,1,head]);dot=0
  if q!=list(map(int,prep[row,head*128:(head+1)*128])):raise ValueError('prepared Q mismatch')
  if k!=list(map(int,prep[col,2048+head*128:2048+(head+1)*128])):raise ValueError('prepared K mismatch')
  for x,y in zip(q,k):dot=add(dot,mul(x,y))
  aa=dot;bb=exp(add(cum[row],neg(cum[col])))
 else:
  k=norm(conv[row,1,head]);b=int(ab[row,16+head]);e=exp(b);beta=bf(mul(div(W(1),add(W(1),e)),e if b>>31 else W(1)))
  if beta!=int(prep[row,6144+head*16+1]) or k!=list(map(int,prep[row,2048+head*128:2048+(head+1)*128])):raise ValueError('prepared K/beta mismatch')
  aa=mul(k[col],beta);bb=exp(cum[row])
 result=mul(aa,bb);exact=fraction(aa)*fraction(bb);tiny=abs(fraction(result))<Fraction(1,2**126);inx=exact!=fraction(result)
 for key,v in [('a',aa),('b',bb),('result',result)]:
  if f'{v:08x}'!=recorded[key]:raise ValueError('failure cone mismatch '+key)
 if not tiny or not inx:raise ValueError('not underflow')
 results.append(dict(head=head,row=row,col=col,phase=phase,operand_a=f'{aa:08x}',operand_b=f'{bb:08x}',result=f'{result:08x}',tiny_after=True,inexact=True,scope='EXACT_FROM_FROZEN_CONV_AB_BOUNDARIES',decay_rows_verified=len(decays),qk_full128_verified=True))
out=dict(status='PASS_EXACT_CONE_REPRODUCES_CANDIDATE_FAILURE',nodes=nodes,seconds=time.monotonic()-start,results=results,full_model_pass=False,hardware_executed=False,upstream_dense_conv_flags='NOT_QUALIFIED')
(R/'RESULT.json').write_text(json.dumps(out,indent=2));(R/'PINS.json').write_text(json.dumps(pins,indent=2));print(json.dumps(out,indent=2))
