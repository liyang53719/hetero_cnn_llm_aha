"""Independent finite FP32 Fraction RNE division and squared-midpoint sqrt.
Flags HardFloat order NV,DZ,OF,UF,NX; only finite supported domain is accepted.
"""
from fractions import Fraction as F

def value(u):
 u=int(u);e=(u>>23)&255;m=u&0x7fffff
 if e==255:raise ValueError('nonfinite')
 if e:m|=1<<23
 p=e-150 if e else -149
 return (-1 if u>>31 else 1)*F(m<<p,1) if p>=0 else (-1 if u>>31 else 1)*F(m,1<<-p)

def rounded(x,negative_zero=False):
 if not x:return (0x80000000 if negative_zero else 0),0
 sign=0x80000000 if x<0 else 0;x=abs(x);n,d=x.numerator,x.denominator
 e=n.bit_length()-d.bit_length()
 if (n<d<<e if e>=0 else n<<-e<d):e-=1
 shift=max(e-23,-149)
 nn,dd=(n,d<<shift) if shift>=0 else (n<<-shift,d)
 q,r=divmod(nn,dd)
 if 2*r>dd or (2*r==dd and q&1):q+=1
 if q>=1<<24:q>>=1;shift+=1
 if shift>104:return sign|0x7f800000,5
 if q<1<<23:u=q
 else:u=((shift+150)<<23)|(q-(1<<23))
 flags=int(bool(r)) | (2 if r and u<0x800000 else 0)
 return sign|u,flags

def div(a,b):
 x,y=value(a),value(b)
 if not y:raise ValueError('zero denominator')
 return rounded(x/y,bool((int(a)^int(b))>>31))

def sqrt(a):
 x=value(a)
 if x<0:raise ValueError('negative sqrt')
 if not x:return int(a),0
 lo,hi=0,0x7f7fffff
 while lo<hi:
  m=(lo+hi+1)//2
  if value(m)**2<=x:lo=m
  else:hi=m-1
 if value(lo)**2==x:return lo,0
 upper=lo+1;mid=(value(lo)+value(upper))/2
 u=upper if x>mid*mid or (x==mid*mid and lo&1) else lo
 return u,1|(2 if u<0x800000 else 0)
