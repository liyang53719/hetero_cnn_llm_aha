"""Bounded independent postNorm provenance/lease model, NOT a Chisel simulation."""
from dataclasses import dataclass,replace
import unittest
@dataclass(frozen=True)
class Host:
 profile:int=1;epoch:int=99;program:int=4096
 regions:tuple=((0,1<<56,True,True),)
@dataclass(frozen=True)
class Job:
 kind:str='norm';tag:int=20;m:int=128;n:int=1024;k:int=1024
 a:int=0x400000;b:int=0x800000;dst:int=0x1000000
 phase:int=3;op:int=0;cold:bool=True;generation:int=0
 bf16:tuple=(True,True,True);recipe:int=1
@dataclass(frozen=True)
class Residual:
 job:Job;host:Host;transaction:int=(1<<52)+41
 result_tag:int=19;status:int=0;write_bytes:int=262144;valid:bool=True
@dataclass(frozen=True)
class Specialized:
 accepted:Job;tag:int=20;status:int=0;write_bytes:int=262144;cycles:int=100
 scalar_accepted:int=669184;scalar_returned:int=669184
 format_accepted:int=131072;format_returned:int=131072
 memory_accepted:int=16384;memory_returned:int=16384
 ack:int=262144;committed:bool=True;drained:bool=True

def counts(j):return (j.m*(5*j.n+j.n//16+44),j.m*j.n,j.m*j.n//8,2*j.m*j.n)
def fixture(p=1,m=128):
 h=Host(p);n=1024 if p<=2 else 2048;j=Job(m=m,n=n,k=n)
 rj=replace(j,kind='residual',tag=19,a=0x100000,b=0x200000,dst=j.a,phase=0)
 r=Residual(rj,h,write_bytes=2*m*n)
 return j,r,h

def shape(j,h):return h.profile in (1,2,3,4) and 1<=j.m<=128 and j.n==(1024 if h.profile<=2 else 2048) and j.k==j.n and j.phase in (0,3) and j.kind=='norm' and j.bf16==(True,True,True) and j.cold and j.generation==0 and j.recipe==1

def admit(j,r,h,t=(1<<52)+41,post_validated=True,previous=None,physical=True,fault=False):
 if fault or not shape(j,h) or post_validated!=(j.phase==3):return False
 if j.phase==0:return True
 p=r.job
 if not r.valid or r.host!=h or r.transaction!=t or r.status or r.result_tag!=p.tag or r.write_bytes!=2*j.m*j.n:return False
 if p.kind!='residual' or p.op!=0 or p.bf16!=(True,True,True) or not p.cold or p.generation or p.dst!=j.a or (p.m,p.n,p.k)!=(j.m,j.n,j.k):return False
 if not (j.m in ((16,128) if h.profile in (1,3) else (128,))):return False
 if p.tag>=0xffffffff or p.tag<0:return False
 if previous is not None and (t<previous[0] or (t==previous[0] and p.tag<=previous[1])):return False
 return not physical or p.tag<j.tag<0xffffffff

def event(j):
 s,f,m,b=counts(j)
 return Specialized(j,j.tag,write_bytes=b,scalar_accepted=s,scalar_returned=s,format_accepted=f,format_returned=f,memory_accepted=m,memory_returned=m,ack=b)
def leases(j,transaction=(1<<52)+41):
 s,f,_,_=counts(j)
 return [dict(slot=slot,kind=1,stage=69,txn=transaction,owner=j.tag,epoch=99,allocation=False,allocation_seq=0,expected=n,accepted=n,issued=n,returned=n,drained=True) for slot,n in [(8,s),(9,f)]]
def terminal(j,e,ls,t=(1<<52)+41,generic=None,event_valid=True,owned=True,fault=False):
 if fault or not owned or not event_valid or e.accepted!=j or e.tag!=j.tag or e.status or not e.committed or not e.drained:return False
 s,f,m,b=counts(j)
 if (e.scalar_accepted,e.scalar_returned,e.format_accepted,e.format_returned,e.memory_accepted,e.memory_returned,e.ack,e.write_bytes)!=(s,s,f,f,m,m,b,b):return False
 if ls!=leases(j,t):return False
 return generic is None or generic==(e.tag,e.status,e.write_bytes,e.cycles)
class Registry:
 def __init__(self):self.receipt=None;self.residual=None;self.active=False;self.retire=False;self.consumed=None
 def complete(self,j,r,h,e,ls,fault=False):
  if admit(j,r,h,previous=self.consumed) and terminal(j,e,ls,fault=fault):
   self.receipt=(h,r.transaction,j,e,r);self.consumed=(r.transaction,r.job.tag);self.retire=True
 def eligible(self,h,t):return self.receipt is not None and self.receipt[0]==h and self.receipt[1]==t
 def replace_or_fault(self):self.receipt=None
 def acquire_next(self):return not self.active and not self.retire
class PostnormTests(unittest.TestCase):
 def test_profiles_and_rows(self):
  for p in (1,2,3,4):
   for m in ((16,128) if p in (1,3) else (128,)):
    j,r,h=fixture(p,m);self.assertTrue(admit(j,r,h));self.assertTrue(terminal(j,event(j),leases(j)))
 def test_input_norm_not_postnorm(self):
  j,r,h=fixture();self.assertFalse(admit(replace(j,phase=0),r,h));self.assertTrue(admit(replace(j,phase=0),r,h,post_validated=False))
 def test_no_input_norm_producer_alias(self):
  j,r,h=fixture();self.assertFalse(admit(j,replace(r,job=replace(r.job,kind='norm')),h))
 def test_no_dense_or_gate_producer_alias(self):
  j,r,h=fixture()
  for kind in ('dense','gate','gated_norm'):self.assertFalse(admit(j,replace(r,job=replace(r.job,kind=kind)),h))
 def test_postnorm_real_ack(self):
  j,r,h=fixture()
  for key,value in [('valid',False),('status',7),('write_bytes',r.write_bytes-64),('result_tag',j.tag)]:self.assertFalse(admit(j,replace(r,**{key:value}),h))
 def test_full_host_lifetime(self):
  j,r,h=fixture()
  for changed in [replace(h,epoch=100),replace(h,program=8192),replace(h,profile=2),replace(h,regions=((0,1<<55,True,True),))]:self.assertFalse(admit(j,replace(r,host=changed),h))
 def test_transaction_64_not_lowbits(self):
  j,r,h=fixture();self.assertFalse(admit(j,replace(r,transaction=41),h))
 def test_physical_sequence_strict(self):
  j,r,h=fixture()
  for tag in (20,21,0xffffffff,0x100000013):self.assertFalse(admit(j,replace(r,job=replace(r.job,tag=tag),result_tag=tag),h))
 def test_consumer_sentinel(self):
  j,r,h=fixture();self.assertFalse(admit(replace(j,tag=0xffffffff),r,h))
 def test_replay(self):
  j,r,h=fixture()
  for previous in [(r.transaction,r.job.tag),(r.transaction,r.job.tag+1),(r.transaction+1,0)]:self.assertFalse(admit(j,r,h,previous=previous))
  self.assertTrue(admit(j,r,h,previous=(r.transaction-1,999)))
 def test_logical_no_predicted_sequence(self):
  j,r,h=fixture();self.assertTrue(admit(replace(j,tag=0),r,h,physical=False));self.assertFalse(admit(replace(j,a=0),r,h,physical=False))
 def test_semantic_shape(self):
  j,r,h=fixture()
  for key,value in [('n',2048),('m',0),('k',1023),('phase',2),('cold',False),('generation',1),('bf16',(True,False,True)),('recipe',0)]:self.assertFalse(admit(replace(j,**{key:value}),r,h))
 def test_rows_never_fake_success(self):
  for p in (1,2,3,4):
   j,r,h=fixture(p,1);self.assertFalse(admit(j,r,h))
 def test_accept_payload_exact(self):
  j,r,h=fixture();e=event(j)
  for key,value in [('b',j.b+64),('a',j.a+64),('phase',0),('recipe',0),('tag',j.tag+1)]:self.assertFalse(terminal(j,replace(e,accepted=replace(j,**{key:value})),leases(j)))
 def test_event_all_counters(self):
  j,r,h=fixture();e=event(j)
  for key in ('scalar_accepted','scalar_returned','format_accepted','format_returned','memory_accepted','memory_returned','ack','write_bytes','tag','status'):
   self.assertFalse(terminal(j,replace(e,**{key:getattr(e,key)+1}),leases(j)),key)
  for key in ('committed','drained'):self.assertFalse(terminal(j,replace(e,**{key:False}),leases(j)))
 def test_adapter_all_identity_and_counts(self):
  j,r,h=fixture();ls=leases(j)
  for index in (0,1):
   for key,value in ls[index].items():
    changed=[dict(x) for x in ls];changed[index][key]=(not value if isinstance(value,bool) else value+1)
    self.assertFalse(terminal(j,event(j),changed),(index,key))
 def test_generic_matches_specialized(self):
  j,r,h=fixture();e=event(j);g=(e.tag,e.status,e.write_bytes,e.cycles);self.assertTrue(terminal(j,e,leases(j),generic=g))
  for i in range(4):bad=list(g);bad[i]+=1;self.assertFalse(terminal(j,e,leases(j),generic=tuple(bad)))
 def test_no_missing_or_unowned_event(self):
  j,r,h=fixture()
  for key in ('event_valid','owned'):self.assertFalse(terminal(j,event(j),leases(j),**{key:False}))
 def test_current_fault_veto(self):
  j,r,h=fixture();self.assertFalse(admit(j,r,h,fault=True));self.assertFalse(terminal(j,event(j),leases(j),fault=True))
 def test_counts_reduction_schedule(self):
  for h in (1024,2048):
   scalar=0
   for chunk in range(h//1024):
    for lane in range(8):
     for residue in range(4):
      for block in range(2):
       for term in range(16):scalar+=2
       scalar+=1
   for lane in range(8):
    for residue in range(4):scalar+=1
    scalar+=1
   scalar+=4
   for i in range(h):scalar+=3
   self.assertEqual(scalar,5*h+h//16+44)
 def test_exact_max_contract(self):
  self.assertEqual(counts(fixture(1)[0]),(669184,131072,16384,262144))
  self.assertEqual(counts(fixture(3)[0]),(1332736,262144,32768,524288))
 def test_staging_is_not_retired_lease(self):
  j,r,h=fixture();a=Registry();a.complete(j,r,h,event(j),leases(j));self.assertTrue(a.eligible(h,r.transaction));self.assertFalse(a.acquire_next());a.retire=False;self.assertTrue(a.acquire_next())
 def test_replacement_and_epoch_invalidate(self):
  j,r,h=fixture();a=Registry();a.complete(j,r,h,event(j),leases(j));self.assertFalse(a.eligible(replace(h,epoch=100),r.transaction));self.assertFalse(a.eligible(h,41));a.replace_or_fault();self.assertFalse(a.eligible(h,r.transaction))
 def test_phase_zero_receipt_never_promoted(self):
  j,r,h=fixture();a=Registry();a.complete(replace(j,phase=0),r,h,event(replace(j,phase=0)),leases(replace(j,phase=0)));self.assertIsNone(a.receipt)
if __name__=='__main__':unittest.main(verbosity=2)
