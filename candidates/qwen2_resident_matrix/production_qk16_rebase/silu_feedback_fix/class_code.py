import struct

def parse(b):
 p=8;cp={}
 def u2():
  nonlocal p
  v=struct.unpack_from('>H',b,p)[0];p+=2;return v
 def u4():
  nonlocal p
  v=struct.unpack_from('>I',b,p)[0];p+=4;return v
 count=u2();i=1
 while i<count:
  t=b[p];p+=1
  if t==1:n=u2();cp[i]=('utf',b[p:p+n]);p+=n
  elif t in (7,8,16,19,20):cp[i]=(t,u2())
  elif t in (3,4):p+=4
  elif t in (5,6):p+=8;i+=1
  elif t in (9,10,11,12,17,18):cp[i]=(t,u2(),u2())
  elif t==15:cp[i]=(t,b[p],struct.unpack_from('>H',b,p+1)[0]);p+=3
  else:raise ValueError('tag')
  i+=1
 def text(i):return cp[i][1].decode('utf8')
 def expand(i):
  v=cp[i]
  if v[0]=='utf':return v[1].decode('utf8')
  if v[0] in (7,8,16):return (v[0],expand(v[1]))
  if v[0] in (9,10,11,12):return (v[0],expand(v[1]),expand(v[2]))
  return v
 p+=6;n=u2();p+=2*n;methods={}
 for kind in ('field','method'):
  for _ in range(u2()):
   flags=u2();name=text(u2());desc=text(u2());code=None
   for _ in range(u2()):
    an=text(u2());size=u4()
    if an=='Code':
     n=struct.unpack_from('>I',b,p+4)[0];code=b[p+8:p+8+n]
    p+=size
   if kind=='method':methods[(name,desc)]=(flags,code)
 return cp,expand,methods

def instructions(code):
 p=0
 two={16,18,*range(21,26),*range(54,59),169,188}
 three={17,19,20,132,*range(153,169),*range(178,185),187,189,192,193,198,199}
 while p<len(code):
  op=code[p];n=2 if op in two else 3 if op in three else 5 if op in (185,186,200,201) else 4 if op==197 else 1
  if op in (170,171):
   q=(p+4)&~3
   if op==170:
    lo,hi=struct.unpack_from('>ii',code,q+4);n=q-p+12+4*(hi-lo+1)
   else:n=q-p+8+8*struct.unpack_from('>i',code,q+4)[0]
  if op==196:n=6 if code[p+1]==132 else 4
  if op>201 or n<=0 or p+n>len(code):raise ValueError('bad bytecode')
  yield p,op,code[p+1:p+n]
  p+=n
