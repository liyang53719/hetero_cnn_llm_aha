"""Full actual VectorSilu six-stage value/flags audit, exact per-denominator division."""
from softmax import *

def main_silu():
 gate=load('gate',(128,8960)).view('<f4');up=load('up',(128,8960)).view('<f4');a=np.abs(gate);active=a<80
 z=mul(a,np.array([0x3fb8aa3b],dtype='<u4').view('<f4')[0],active,'compound_exp_scale');k=z.astype(np.int64);f=add(z,-k.astype(np.float32),active,'compound_exp_fraction');h=np.full_like(f,np.array([COEFF[7]],dtype='<u4').view('<f4')[0])
 for i in range(6,-1,-1):h=add(mul(h,f,active,'compound_exp_horner_mul'),np.array([COEFF[i]],dtype='<u4').view('<f4')[0],active,'compound_exp_horner_add')
 scale=((127-np.clip(k,0,126)).astype('<u4')<<23).view('<f4');e=mul(h,scale,active,'compound_exp_pow2_mul');e=np.where(active,e,np.float32(0));den=add(np.float32(1),e,True,'silu_denominator')
 # Cache repeated input words, not approximated reciprocals. Every distinct
 # denominator is independently divided as an exact rational and RNE rounded.
 words,inverse=np.unique(den.view('<u4'),return_inverse=True);invwords=np.empty_like(words);flagwords=np.empty(len(words),np.uint8)
 for i,w in enumerate(words):
  exact=Fraction(1)/ref.fraction(int(w));v=ref.rounded(exact);nx=ref.fraction(v)!=exact;uf=nx and v&0x7f800000==0
  if uf:raise ValueError('fatal division underflow')
  invwords[i]=v;flagwords[i]=int(nx)
 inv=invwords[inverse].reshape(gate.shape).view('<f4');ff=flagwords[inverse];counts['silu_div']=dict(steps=int(ff.size),flags={str(int(f)):int(n) for f,n in zip(*np.unique(ff,return_counts=True))},exact_distinct_denominators=int(words.size))
 signed=mul(inv,np.where(np.signbit(gate),e,np.float32(1)),True,'silu_signed');value=mul(signed,gate,True,'silu_gate');out=mul(value,up,True,'silu_up')
 if not np.array_equal(out.view('<u4'),load('act',(128,8960))):raise ValueError('SiLU full output mismatch')
 for n in ['silu_denominator','silu_signed','silu_gate','silu_up']:
  if any(int(f)&6 for f in counts[n]['flags']):raise ValueError('fatal scalar flags '+n)
 check_environment()
 result=dict(status='PASS_FULL_M128_SILU_REFERENCE_SCALAR_NODE_FLAGS',counts=counts,verified_inputs=verified,scope='Original six-stage FP32 order, exact rational reciprocal for every distinct actual denominator; compound exp internal flags are diagnostics only, no hardware aggregate status asserted',hardware=False)
 (O/'SILU_RESULT.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main_silu()
