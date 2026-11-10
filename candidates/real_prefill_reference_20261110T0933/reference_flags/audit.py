"""Independent finite BF16*BF16+FP32 RNE/tininess-after flag oracle.
Integer dyadics; never invokes hardware/candidate to derive expected values.
Flags [invalid,div0,overflow,underflow,inexact]. Nonfinite rejected.
"""
import struct

def dyadic(u):
 u=int(u);e=(u>>23)&255;m=u&0x7fffff
 if e==255:raise ValueError('finite only')
 return (-1 if u>>31 else 1)*(m+(1<<23) if e else m), e-150 if e else -149

def rne(n,shift):
 if shift<=0:return n<<-shift,False
 q,r=divmod(n,1<<shift);h=1<<(shift-1)
 return q+(r>h or (r==h and q&1)),bool(r)

def fma(a,b,c):
 if (int(a)|int(b))&65535:raise ValueError('BF16 lifted words required')
 am,ae=dyadic(a);bm,be=dyadic(b);cm,ce=dyadic(c)
 pe=ae+be;base=min(pe,ce);n=(am*bm<<pe-base)+(cm<<ce-base)
 if not n:
  neg=(not am or not bm) and ((int(a)^int(b))>>31) and int(c)==0x80000000
  return 0x80000000 if neg else 0,0
 sign=0x80000000 if n<0 else 0;n=abs(n);exp=n.bit_length()-1+base
 if exp < -126:
  sig,inx=rne(n,-149-base);word=sign|sig
 else:
  sig,inx=rne(n,exp-23-base)
  if sig==1<<24:sig>>=1;exp+=1
  if exp>127:return sign|0x7f800000,5
  word=sign|((exp+127)<<23)|(sig-(1<<23))
 # Underflow only tiny AFTER rounding and inexact; exact subnormal is legal.
 flags=int(inx)|(2 if inx and word&0x7f800000==0 else 0)
 return word,flags
