import random,struct,json,time
import numpy as np
from fractions import Fraction
from integer_oracle import fma
from full_audit import two_sum
from pathlib import Path
R=Path(__file__).parent
fp=lambda u:struct.unpack('<f',struct.pack('<I',u))[0]
word=lambda f:struct.unpack('<I',struct.pack('<f',f))[0]
r=random.Random(411);cases=[]
# All finite BF16 exponent pairs; fixed extreme mantissas and signs, accumulator
# exponent cycling exercises cancellation, dominant addend, and boundary gaps.
for ea in range(255):
 for eb in range(255):
  a=(ea<<23)|(127<<16);b=(eb<<23)|(1<<16)
  ec=(ea+eb+29)%255;c=(ec<<23)|0x7fffff
  cases.append((a,b,c))
for _ in range(20000):
 a=r.randrange(65536)<<16;b=r.randrange(65536)<<16;c=r.randrange(1<<32)
 if all(x&0x7f800000!=0x7f800000 for x in [a,b,c]):cases.append((a,b,c))
cases += [(0x26800000,0x26800000,0x3f800000),(0x80000000,0x3f800000,0x80000000),(0,0x3f800000,0x80000000),(0x3f800000,0x3f800000,0xbf800000),(0x00800000,0x3f000000,0),(0x00010000,0x00010000,0),(0x7f7f0000,0x40000000,0)]
t=time.monotonic();resid=0
for a,b,c in cases:
 product=np.float64(fp(a))*np.float64(fp(b));s,e=two_sum(product,np.float64(fp(c)))
 exact=Fraction(fp(a))*Fraction(fp(b))+Fraction(fp(c))
 if Fraction(float(s))+Fraction(float(e))!=exact:raise ValueError('TwoSum exact residual')
 with np.errstate(over='ignore',under='ignore'):out=np.float32(s)
 nx=bool(np.float64(out)!=s or e!=0);uf=nx and abs(float(out))<2**-126;ov=not np.isfinite(out)
 flags=(1 if nx else 0)|(2 if uf else 0)|(4 if ov else 0)
 wanted=fma(a,b,c)
 if (word(out),flags)!=wanted:raise ValueError((hex(a),hex(b),hex(c),(hex(word(out)),flags),wanted))
 resid+=bool(e)
result=dict(status='PASS_EXACT_RESIDUAL_VALUE_FLAGS_TESTS',cases=len(cases),nonzero_residuals=resid,seconds=time.monotonic()-t)
(R/'TEST_RESULT.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
