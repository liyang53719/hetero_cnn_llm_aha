import struct
def source_file(b):
 p=8
 def u2():
  nonlocal p
  n=struct.unpack_from('>H',b,p)[0];p+=2;return n
 def u4():
  nonlocal p
  n=struct.unpack_from('>I',b,p)[0];p+=4;return n
 count=u2();cp={};i=1
 while i<count:
  tag=b[p];p+=1
  if tag==1:
   n=u2();cp[i]=b[p:p+n].decode('utf8',errors='replace');p+=n
  elif tag in [3,4]:p+=4
  elif tag in [5,6]:p+=8;i+=1
  elif tag in [7,8,16,19,20]:p+=2
  elif tag in [9,10,11,12,17,18]:p+=4
  elif tag==15:p+=3
  else:raise ValueError(tag)
  i+=1
 p+=6
 for _ in range(u2()):p+=2
 for kind in range(2):
  for _ in range(u2()):
   p+=6
   for _ in range(u2()):
    u2();n=u4();p+=n
 source=None
 for _ in range(u2()):
  name=cp[u2()];n=u4()
  if name=='SourceFile':source=cp[struct.unpack_from('>H',b,p)[0]]
  p+=n
 if p!=len(b):raise ValueError('trailing')
 return source
