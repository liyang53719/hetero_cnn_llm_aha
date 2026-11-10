from run import *
from integer_oracle import fma
from fractions import Fraction
sys.path.insert(0,str(R/'round_20261110T0833/legacy_python'))
import legacy_reference as ref

def scalar(a,b,op):
 exact=ref.fraction(a)+ref.fraction(b) if op=='add' else ref.fraction(a)*ref.fraction(b)
 neg=(a==b==0x80000000) if op=='add' else bool((a^b)>>31)
 w=ref.rounded(exact,neg);nx=ref.fraction(w)!=exact;return w,int(nx)|(2 if nx and w&0x7f800000==0 else 0)
def test():
 q=bf16_words(load('q',(128,12,128)));k=bf16_words(load('k',(128,2,128)));v=bf16_words(load('kv.1',(128,2,128)));p=bf16_words(load('prob',(12,128,128)));scores=load('scores',(12,128,128));att=load('att',(128,12,128));n=0
 for h,t,key in [(0,0,0),(5,63,17),(6,127,126),(11,127,127)]:
  lanes=[0]*16
  for d in range(128):lanes[d%16],fl=fma(int(q[t,h,d]),int(k[key,h//6,d]),lanes[d%16]);n+=1
  total=0
  for l in lanes:total,fl=scalar(total,l,'add')
  total,fl=scalar(total,0x3db504f3,'mul')
  if total!=int(scores[h,t,key]):raise ValueError('exact QK sample')
 for h,t,c in [(0,0,0),(5,63,61),(6,127,64),(11,127,127)]:
  acc=0
  for key in range(t+1):acc,fl=fma(int(p[h,t,key]),int(v[key,h//6,c]),acc);n+=1
  if acc!=int(att[t,h,c]):raise ValueError('exact PV sample')
 rng=np.random.default_rng(1133);cases=0
 for _ in range(3000):
  a=int(rng.integers(0,2**32,dtype=np.uint64));b=int(rng.integers(0,2**32,dtype=np.uint64))
  if (a&0x7f800000)==0x7f800000 or (b&0x7f800000)==0x7f800000:continue
  for op in ['add','mul']:
   aa=np.array([a],dtype='<u4').view('<f4').astype(np.float64);bb=np.array([b],dtype='<u4').view('<f4').astype(np.float64)
   s,e=two(aa,bb) if op=='add' else (aa*bb,0)
   with np.errstate(over='ignore',under='ignore'):out=s.astype(np.float32)
   if not np.isfinite(out).all():continue
   nx=(out.astype(np.float64)!=s)|(e!=0);flags=int(nx[0])|(2 if nx[0] and abs(out[0])<np.float32(2**-126) else 0)
   expected=scalar(a,b,op)
   if (int(out.view('<u4')[0]),flags)!=expected:raise ValueError((op,a,b,expected))
   cases+=1
 result=dict(status='PASS_EXACT_REAL_QK_PV_COORDINATES_AND_SCALAR_ROUND_FLAGS',sample_fma_steps=n,qk_outputs=4,pv_outputs=4,scalar_cases=cases)
 (O/'TEST_RESULT.json').write_text(json.dumps(result,indent=2));print(result)
if __name__=='__main__':test()
