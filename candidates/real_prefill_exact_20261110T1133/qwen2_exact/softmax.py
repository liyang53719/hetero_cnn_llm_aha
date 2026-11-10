"""Full actual softmax with original exp polynomial and exact scalar division."""
from run import *
from fractions import Fraction
sys.path.insert(0,str(R/'round_20261110T0833/legacy_python'))
import legacy_reference as ref
from operators import COEFF

def add(a,b,valid,stage):
 s,e=two(np.asarray(a,np.float64),np.asarray(b,np.float64));return round_flags(s,e,valid,stage)
def mul(a,b,valid,stage):return round_flags(np.asarray(a,np.float64)*np.asarray(b,np.float64),0,valid,stage)
def main_softmax():
 mask=np.arange(128)[None,:,None]>=np.arange(128)[None,None,:];x=load('scores',(12,128,128)).view('<f4');maximum=np.max(np.where(mask,x,-np.inf),axis=2,keepdims=True)
 delta=add(x,-maximum,mask,'softmax_subtract');a=np.abs(delta);active=mask&(a<80)
 z=mul(a,np.array([0x3fb8aa3b],dtype='<u4').view('<f4')[0],active,'compound_exp_scale');k=z.astype(np.int64);f=add(z,-k.astype(np.float32),active,'compound_exp_fraction');h=np.full_like(f,np.array([COEFF[7]],dtype='<u4').view('<f4')[0])
 for i in range(6,-1,-1):h=add(mul(h,f,active,'compound_exp_horner_mul'),np.array([COEFF[i]],dtype='<u4').view('<f4')[0],active,'compound_exp_horner_add')
 scale=((127-np.clip(k,0,126)).astype('<u4')<<23).view('<f4');e=mul(h,scale,active,'compound_exp_pow2_mul');e=np.where(active,e,np.float32(0))
 sums=np.zeros((12,128),np.float32)
 for key in range(128):
  valid=np.arange(128)[None,:]>=key;new=add(sums,e[:,:,key],valid,'softmax_sum');sums=np.where(valid,new,sums)
 inv=np.empty_like(sums);flags={}
 for idx in np.ndindex(sums.shape):
  den=ref.fraction(int(sums.view('<u4')[idx]));exact=Fraction(1)/den;word=ref.rounded(exact);nx=ref.fraction(word)!=exact;uf=nx and word&0x7f800000==0;flag=int(nx)|(2 if uf else 0)
  if uf:raise ValueError('fatal scalar division underflow')
  inv.view('<u4')[idx]=word;flags[str(flag)]=flags.get(str(flag),0)+1
 counts['softmax_div']=dict(steps=1536,flags=flags,method='independent Fraction RNE per actual denominator')
 out=mul(e,inv[:,:,None],mask,'softmax_probability_mul');out=np.where(mask,out,np.float32(0));expected=load('prob',(12,128,128))
 if not np.array_equal(out.view('<u4'),expected):raise ValueError('softmax output mismatch')
 for name in ['softmax_subtract','softmax_sum','softmax_probability_mul']:
  if any(int(f)&6 for f in counts[name]['flags']):raise ValueError('fatal scalar flags '+name)
 check_environment()
 result=dict(status='PASS_FULL_M128_SOFTMAX_VALUE_AND_SCALAR_NODE_FLAGS_REFERENCE_ONLY',counts=counts,verified_inputs=verified,scope='Full original polynomial and scalar order; compound_exp flags are internal node diagnostics, not invented aggregate hardware status; no input format flags/hardware/fullblock acceptance',hardware=False)
 (O/'SOFTMAX_RESULT.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main_softmax()
