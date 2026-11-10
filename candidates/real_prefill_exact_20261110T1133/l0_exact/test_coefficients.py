from decimal import Decimal,localcontext
import math,struct
from exact import rounded
from fractions import Fraction
bits=lambda f:struct.unpack('<I',struct.pack('<f',f))[0]
with localcontext() as c:
 c.prec=100; ln2=Decimal(2).ln()
 for i in range(8):
  x=(-ln2)**i/Decimal(math.factorial(i));u,_=rounded(Fraction(x))
  if u!=bits((-math.log(2))**i/math.factorial(i)):raise ValueError('coefficient '+str(i))
 u,_=rounded(Fraction(Decimal(1)/ln2))
 if u!=bits(1/math.log(2)):raise ValueError('log2e')
print('PASS original exp eight FP32 coefficients and LOG2E against100-digit Decimal/Fraction')
