from audit import fma
cases=[
 # exact subnormal, tiny-inexact to zero, min-normal boundary after rounding
 (0x00010000,0x37800000,0,0x00000001,0),
 (0x00010000,0x37000000,0,0,3),
 (0x80010000,0x37000000,0x00800000,0x00800000,1),
 (0x7f7f0000,0x40000000,0,0x7f800000,5),
 (0x80000000,0x3f800000,0x80000000,0x80000000,0),
 (0x3f800000,0x3f800000,0xbf800000,0,0),
 (0x3f800000,0x3f800000,0x33800000,0x3f800000,1),
 (0x3f800000,0x3f800000,0x34400000,0x3f800002,1)]
for a,b,c,w,f in cases:
 if fma(a,b,c)!=(w,f):raise RuntimeError((a,b,c,fma(a,b,c),w,f))
for a,b,c in [(0x7f800000,0,0),(0,0,0x7fc00000),(0x3f800001,0,0)]:
 try:fma(a,b,c)
 except ValueError:pass
 else:raise RuntimeError('invalid input accepted')
print('PASS 8 directed flags/value cases and 3 fail-closed input cases')
