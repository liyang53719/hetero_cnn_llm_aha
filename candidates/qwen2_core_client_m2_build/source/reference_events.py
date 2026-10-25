"""Independent closed-form M1/M2/M3 zero-input expectations; no DUT imports/run.
Events are reference descriptors, not implemented SRAM/DDR/repeat/mask tensors.
"""
from fractions import Fraction
Q,K,V,DST=0x100000,0x200000,0x300000,0x400000

def checked_m(m):
 if type(m) is not int or m not in (1,2,3):raise ValueError('only source-reviewed normal M1/M2/M3')
 return m

def counts(m):
 checked_m(m)
 return dict(groups=12*m,qkAcceptedSteps=96*m,pvRequests=48*m*(m+1),pvReturns=48*m*(m+1),accounting512Steps=768*m+48*m*(m+1),scoreWrites=6*m*(m+1),memoryAccepted=96*m*(m+3),memoryReturned=96*m*(m+3),outputBytes=6144*m,uniqueOutputBeats=96*m,observations=408*m+6*m*(m-1),ownerAccepts=1,results=12*m,dones=12*m)

def vector_events(m):
 checked_m(m)
 for token in range(m):
  for head in range(12):
   for phase in (1,2):
    for lane in range(16):
     yield dict(token=token,head=head,phase=phase,lane=lane,selected=0,scoreWrite=False,maxScore=0xff800000)
   yield dict(token=token,head=head,phase=3,lane=15,selected=0,scoreWrite=False,maxScore=0xff800000)
   for key in range(token+1):
    yield dict(token=token,head=head,phase=4,lane=15,selected=key,scoreWrite=True,scoreIndex=key,scoreData=0,maxScore=0xff800000 if key==0 else 0)

def memory_events(m):
 checked_m(m)
 for token in range(m):
  for head in range(12):
   kv_head=0 if head<6 else 1
   for lane_base in range(0,128,16):
    yield dict(kind='Q',write=False,address=Q+4*(1536*token+128*head+lane_base))
   for lane_base in range(0,128,16):
    for causal_key in range(token+1):
     yield dict(kind='K',write=False,address=K+4*(256*causal_key+128*kv_head+lane_base))
   for lane_base in range(0,128,16):
    for causal_key in range(token+1):
     yield dict(kind='V',write=False,address=V+4*(256*causal_key+128*kv_head+lane_base))
    yield dict(kind='OUTPUT',write=True,address=DST+4*(1536*token+128*head+lane_base))

def rational_f32_rne(value):
 """Exact integer-rational rounding, only positive normal values needed here."""
 if not isinstance(value,Fraction) or not Fraction(1,3)<=value<=1:raise ValueError('restricted uniform probability domain')
 exponent=0
 while value<1:value*=2;exponent-=1
 n,d=(value*(1<<23)).as_integer_ratio();q,r=divmod(n,d)
 if 2*r>d or (2*r==d and q&1):q+=1
 if q==(1<<24):q>>=1;exponent+=1
 return ((exponent+127)<<23)|(q-(1<<23))

def uniform_bf16(key_count):
 if type(key_count) is not int or key_count not in (1,2,3):raise ValueError('only uniform1/2/3')
 bits=rational_f32_rne(Fraction(1,key_count))
 return ((bits+0x7fff+((bits>>16)&1))>>16)&0xffff

def pv_events(m):
 checked_m(m)
 for token in range(m):
  for head in range(12):
   for output_chunk in range(8):
    for causal_key in range(token+1):
     yield dict(token=token,head=head,outputChunk=output_chunk,key=causal_key,opcode=0x24,sliceMask=1,clear=causal_key==0,last=causal_key==token,a0=uniform_bf16(token+1),other_a_zero=True,all_b_zero=True)
