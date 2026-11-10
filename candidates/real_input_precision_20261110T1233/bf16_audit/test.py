from convert import *
points=[0,0x80000000,1,0x80000001,0x007f0000,0x007f7fff,0x007f8000,0x007fffff,0x00800000,0x3f808000,0x3f818000,0x7f7f7fff,0x7f7f8000,0x7f800000,0xff800000,0x7f800001,0xff800001,0xffc00000]
for u in points:
 r,f=reference(u)
 if (r,f)!=rope_source(u):raise ValueError(hex(u))
 expected=r|((u>>16)&0x8000) if ((u>>23)&255)==255 and u&0x7fffff else r
 if tensor_source(u)!=expected:raise ValueError('TensorMath '+hex(u))
# Every BF16 upper word, seven low-word boundary choices, covering normal,
# subnormal, sign, ties, carry, infinity, quiet/signaling NaN.
n=0
for hi in range(65536):
 for lo in (0,1,32767,32768,32769,65534,65535):
  u=(hi<<16)|lo
  if reference(u)!=rope_source(u):raise ValueError(hex(u))
  n+=1
print('PASS integer source-contract checks',n,'boundary points',len(points),'explicit cases; no hardware')
