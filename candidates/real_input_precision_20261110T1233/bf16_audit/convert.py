"""Integer-only IEEE binary32 -> bfloat16 nearest-even and after-round flags."""
def reference(u):
 u=int(u);sign=u>>31;ex=(u>>23)&255;frac=u&0x7fffff
 if ex==255:
  if frac:return 0x7fc0,16 if not frac&0x400000 else 0
  return (sign<<15)|0x7f80,0
 # Both formats have the same exponent. Divide the exact integer significand
 # by 2^16, compare its remainder with half, then carry into the exponent.
 sig=frac|(0x800000 if ex else 0);q,r=divmod(sig,65536)
 if r>32768 or (r==32768 and q%2):q+=1
 code=q if ex==0 else ((ex-1)<<7)+q
 nx=int(r!=0);flags=nx|(2 if nx and code<128 else 0)
 if code>=0x7f80:flags=5
 return (sign<<15)|code,flags

def rope_source(u):
 u=int(u);discard=bool(u&65535);inc=bool(u&32768) and bool((u&32767)|(u&65536));r=((u>>16)+inc)&65535
 if (u>>23)&255==255:
  if u&0x7fffff:return 0x7fc0,0 if u&0x400000 else 16
  return (u>>16)&0xff80,0
 f=int(discard)|(2 if discard and ((r>>7)&255)==0 else 0)
 if ((r>>7)&255)==255:f=5
 return r,f

def tensor_source(u):
 u=int(u)
 if ((u>>23)&255)==255:return ((u>>16)&0xff80)|(64 if u&0x7fffff else 0)
 return ((u+32767+((u>>16)&1))>>16)&65535

def qknorm_finite_source(u):
 u=int(u)
 if ((u>>23)&255)==255:raise ValueError('finite input precondition')
 discarded=bool(u&65535);inc=bool(u&32768) and bool((u&32767)|(u&65536));r=((u>>16)+inc)&65535
 overflow=((r>>7)&255)==255;underflow=discarded and ((r>>7)&255)==0
 return r,(4 if overflow else 0)|(2 if underflow and not overflow else 0)|int(discarded or overflow)
