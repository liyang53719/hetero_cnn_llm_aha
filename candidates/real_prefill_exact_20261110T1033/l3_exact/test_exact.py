from exact import *
cases=[('sqrt',0x40800000,None,0x40000000,0),('sqrt',0x80000000,None,0x80000000,0),('sqrt',0x40000000,None,0x3fb504f3,1),('div',0x3f800000,0x40000000,0x3f000000,0),('div',0x3f800000,0x40400000,0x3eaaaaab,1),('div',1,0x40000000,0,3),('div',0x7f7fffff,0x3f000000,0x7f800000,5)]
for op,a,b,u,f in cases:
 actual=sqrt(a) if op=='sqrt' else div(a,b)
 if actual!=(u,f):raise RuntimeError((op,actual,u,f))
for fn,arg in [(sqrt,0xbf800000),(sqrt,0x7f800000)]:
 try:fn(arg)
 except ValueError:pass
 else:raise RuntimeError('missing rejection')
print('PASS 7 fixed exact sqrt/div/flags cases + 2 rejection cases')
