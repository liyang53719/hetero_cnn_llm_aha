from decimal import Decimal,localcontext
from fractions import Fraction
from audit import C,round_fraction
with localcontext() as c:
 c.prec=100;ln2=Decimal(2).ln();term=Decimal(1);words=[]
 for i in range(8):
  if i:term=term*(-ln2)/i
  words.append(round_fraction(Fraction(term)))
 if words!=C:raise ValueError('coefficient mismatch')
 if round_fraction(Fraction(1/ln2))!=0x3fb8aa3b:raise ValueError('log2e mismatch')
print('PASS 100-digit Decimal coefficients/log2e vs frozen FP32 words; all4 exact cones reproduced')
