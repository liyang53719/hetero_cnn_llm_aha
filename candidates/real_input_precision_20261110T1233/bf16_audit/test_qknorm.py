from convert import reference,qknorm_finite_source
n=0
for hi in range(65536):
 if (hi&0x7f80)==0x7f80:continue
 for lo in (0,1,32767,32768,32769,65534,65535):
  u=hi*65536+lo
  if reference(u)!=qknorm_finite_source(u):raise ValueError(hex(u))
  n+=1
print('PASS QkNorm finite source-contract boundary points',n,'no hardware')
