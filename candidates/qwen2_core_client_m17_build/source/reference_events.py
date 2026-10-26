"""Independent fixed-M17 causal zero-score reference; no DUT/stimulus imports.
Iterator loop nests describe memory/protocol order, not physical tensors.
"""
from fractions import Fraction
Q,K,V,DST=0x100000,0x200000,0x300000,0x400000
M=17;HEADS=12;CHUNK=16

def counts():
 groups=sum((n+15)//16 for n in range(1,18))*12
 return dict(groups=groups,results=groups,dones=groups,qkAcceptedSteps=8*groups,pvRequests=14688,pvReturns=14688,accounting512Steps=28512,scoreWrites=1836,memoryAccepted=32640,memoryReturned=32640,outputBytes=104448,uniqueOutputBeats=1632,observations=8964,ownerAccepts=1,checkedGroups=groups)

def group_events():
 for token in range(M):
  for head in range(HEADS):
   for base in range(0,token+1,CHUNK):
    yield dict(token=token,head=head,base=base,count=min(CHUNK,token+1-base))

def vector_events():
 # Deliberately does not call group_events or any driver lookup.
 for token in range(M):
  for head in range(HEADS):
   for base in range(0,token+1,CHUNK):
    old_max=0xff800000 if base==0 else 0
    for phase in (1,2):
     for lane in range(16):yield dict(token=token,head=head,keyBase=base,phase=phase,lane=lane,selected=0,scoreWrite=False,scoreIndex=0,maxScore=old_max)
    yield dict(token=token,head=head,keyBase=base,phase=3,lane=15,selected=0,scoreWrite=False,scoreIndex=0,maxScore=old_max)
    for global_key in range(base,min(base+CHUNK,token+1)):
     yield dict(token=token,head=head,keyBase=base,phase=4,lane=15,selected=global_key-base,scoreWrite=True,scoreIndex=global_key,scoreData=0,maxScore=0xff800000 if global_key==0 else 0)

def memory_events():
 for token in range(M):
  for head in range(HEADS):
   kv_head=head//6
   for depth in range(0,128,16):yield dict(kind='Q',write=False,address=Q+4*(1536*token+128*head+depth))
   # Actual K feed is chunk-major, then depth-major, then causal key.
   for first_key in range(0,token+1,16):
    for depth in range(0,128,16):
     for global_key in range(first_key,min(first_key+16,token+1)):
      yield dict(kind='K',write=False,address=K+4*(256*global_key+128*kv_head+depth))
   for col in range(0,128,16):
    for global_key in range(token+1):yield dict(kind='V',write=False,address=V+4*(256*global_key+128*kv_head+col))
    yield dict(kind='OUTPUT',write=True,address=DST+4*(1536*token+128*head+col))

def rational_f32_rne(value):
 if not isinstance(value,Fraction) or not Fraction(1,17)<=value<=1:raise ValueError('fixed uniform1..17 normal domain only')
 exponent=0
 while value<1:value*=2;exponent-=1
 n,d=(value*(1<<23)).as_integer_ratio();q,r=divmod(n,d)
 if 2*r>d or (2*r==d and q&1):q+=1
 if q==(1<<24):q>>=1;exponent+=1
 return ((exponent+127)<<23)|(q-(1<<23))

def uniform_bf16(key_count):
 if type(key_count) is not int or not 1<=key_count<=17:raise ValueError('fixed uniform1..17')
 bits=rational_f32_rne(Fraction(1,key_count))
 return ((bits+0x7fff+((bits>>16)&1))>>16)&0xffff

def pv_events():
 for token in range(M):
  for head in range(HEADS):
   for output_chunk in range(8):
    for global_key in range(token+1):
     yield dict(token=token,head=head,outputChunk=output_chunk,key=global_key,opcode=0x24,sliceMask=1,clear=global_key==0,last=global_key==token,a0=uniform_bf16(token+1),other_a_zero=True,all_b_zero=True)
