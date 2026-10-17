"""Read structural JVM ABI without executing class code (all members retained)."""
import struct
def abi(b):
 p=0
 def take(n):
  nonlocal p
  if p+n>len(b):raise ValueError('truncated class')
  v=b[p:p+n];p+=n;return v
 def u1():return take(1)[0]
 def u2():return struct.unpack('>H',take(2))[0]
 def u4():return struct.unpack('>I',take(4))[0]
 if take(4)!=b'\xca\xfe\xba\xbe':raise ValueError('magic')
 version=(u2(),u2());cp={};i=1;count=u2()
 while i<count:
  t=u1()
  if t==1:cp[i]=('utf',take(u2()))
  elif t in (7,8,16,19,20):cp[i]=(t,u2())
  elif t in (3,4):take(4)
  elif t in (5,6):take(8);i+=1
  elif t in (9,10,11,12,17,18):take(4)
  elif t==15:take(3)
  else:raise ValueError('constant tag')
  i+=1
 def utf(i):
  if cp[i][0]!='utf':raise ValueError('expected utf')
  return cp[i][1].hex() # lossless modified UTF8, no decoder normalization
 def cls(i):return utf(cp[i][1]) if i else None
 def attrs():
  result=[]
  for _ in range(u2()):
   name=u2();n=u4();data=take(n)
   if cp[name][1]==b'Signature':
    if n!=2:raise ValueError('signature length')
    result.append(('Signature',utf(struct.unpack('>H',data)[0])))
  return sorted(result)
 flags=u2();this=cls(u2());superclass=cls(u2());interfaces=[cls(u2()) for _ in range(u2())]
 members=[]
 for kind in ('field','method'):
  for _ in range(u2()):
   access=u2();name=utf(u2());desc=utf(u2());members.append((kind,access,name,desc,attrs()))
 attributes=attrs()
 if p!=len(b):raise ValueError('trailing')
 return dict(version=version,flags=flags,this=this,superclass=superclass,interfaces=interfaces,members=sorted(members),signature=attributes)
