import sys,pathlib,random,json,time,hashlib
import numpy as np
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent/'legacy_python'))
from legacy_reference import fraction
from rational_oracle import round_fraction
from candidate import fma_bf16_words,dense

def exact(a,b,c):
    x=fraction(a)*fraction(b)+fraction(c)
    z=round_fraction(x)
    if not x and not ((a&0x7fffffff) and (b&0x7fffffff)) and (a^b)>>31 and c==0x80000000:z=0x80000000
    return z
r=random.Random(0x20261110);cases=[]
# All exponent-pair combinations; mantissas/signs varied, accumulator exponent independently varied.
for ea in range(255):
 for eb in range(255):
  a=(r.randrange(2)<<31)|(ea<<23)|(r.randrange(128)<<16)
  b=(r.randrange(2)<<31)|(eb<<23)|(r.randrange(128)<<16)
  c=(r.randrange(2)<<31)|(r.randrange(255)<<23)|r.randrange(1<<23)
  cases.append((a,b,c))
# Directed zero signs, cancellation, underflow, overflow and exponent gaps.
values=[0,0x80000000,0x00010000,0x80010000,0x007f0000,0x00800000,0x3f000000,0x3f800000,0xbf800000,0x3f810000,0x7f7f0000]
for a in values:
 for b in values:
  for c in [0,0x80000000,1,0x80000001,0x007fffff,0x00800000,0x3f800000,0xbf800000,0x7f7fffff,0xff7fffff]:cases.append((a,b,c))
for _ in range(10000):
 a=(r.randrange(2)<<31)|(r.randrange(255)<<23)|(r.randrange(128)<<16)
 b=(r.randrange(2)<<31)|(r.randrange(255)<<23)|(r.randrange(128)<<16)
 prod=fraction(a)*fraction(b);p=round_fraction(prod)
 if p&0x7f800000!=0x7f800000:
  cases.extend((a,b,c) for c in [p^0x80000000,((p^0x80000000)+1)&0xffffffff,((p^0x80000000)-1)&0xffffffff] if c&0x7f800000!=0x7f800000)
x=np.asarray(cases,dtype=np.uint32);t=time.monotonic();got=fma_bf16_words(x[:,0],x[:,1],x[:,2]);want=np.array([exact(*map(int,row)) for row in x],dtype=np.uint32)
bad=np.flatnonzero(got!=want)
report=dict(status='PASS_BOUNDED_FMA_PARITY' if not len(bad) else 'FAIL',cases=len(cases),mismatches=len(bad),seconds=time.monotonic()-t,seed='0x20261110',case_sha256=hashlib.sha256(x.tobytes()).hexdigest(),output_sha256=hashlib.sha256(got.tobytes()).hexdigest(),scope='finite BF16 operands and finite FP32 accumulator; overflow result bits included, not hardware exception acceptance',first_mismatches=[dict(inputs=list(map(int,x[i])),got=int(got[i]),want=int(want[i])) for i in bad[:8]])
print(json.dumps(report,indent=2))
if len(bad):sys.exit(1)
