import numpy as np
from fractions import Fraction
import run
from exact import value,rounded
pairs=[(0x00000001,0x3f800000),(0x00800000,0x3f800000),(0x3f800000,0x80000000),(0x80000000,0x80000000),(0x7f7fffff,0x00800000),(0x3f000001,0x3f000003),(0x3f800000,0xbf800000),(0x00800000,0x807fffff)]
for u,v in pairs:
 for op in ['add','mul']:
  a=np.array([u],dtype='<u4').view('<f4');b=np.array([v],dtype='<u4').view('<f4');x=value(u)+value(v) if op=='add' else value(u)*value(v);neg=(u==v==0x80000000) if op=='add' else bool((u^v)>>31);expected,flags=rounded(x,neg)
  if flags&6:
   try:getattr(run,op)(a,b)
   except ValueError:continue
   raise ValueError('fatal not rejected')
  got=int(getattr(run,op)(a,b).view('<u4')[0])
  if got!=expected:raise ValueError((op,hex(u),hex(v),hex(got),hex(expected)))
# Existing failure must still be fatal, not relaxed to make a whole-block pass.
u,v=0xb90b2091,0x05d1243c
try:run.mul(np.array([u],'<u4').view('<f4'),np.array([v],'<u4').view('<f4'))
except ValueError:pass
else:raise ValueError('downstream known fatal not rejected')
print('PASS scalar mul/add finite value and fatal rejection:16 nodes plus known tiny-inexact')
