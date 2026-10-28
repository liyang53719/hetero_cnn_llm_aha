"""Independent finite Commands postNorm contract models. Not Scala/Chisel/RTL/DUT execution."""
from dataclasses import dataclass,replace
import unittest
S=(1<<24)-1
@dataclass(frozen=True)
class Host:
 profile:int=4;epoch:int=19;command_base:int=0x1000;descriptor_base:int=0x2000;region_limit:int=1<<40
@dataclass(frozen=True)
class Tensor:
 base:int;rows:int;width:int;dtype:int=5;rank:int=2;tail:int=S;prefix:tuple=(1,2,3);extent:int=0;count_delta:int=0
 @property
 def count(self):return self.rows*self.width+self.count_delta
 @property
 def bytes(self):return self.count*2
 @property
 def end(self):return self.base+self.bytes+self.extent
 @property
 def allocation(self):return (self.base,self.rank,self.dtype,self.rows,self.width,self.count,self.bytes,self.end)
 def legal(self):return self.dtype==5 and self.rank==2 and 0<=self.base<1<<56 and self.base%64==0 and self.end<=1<<56 and self.extent==0 and self.count_delta==0
@dataclass(frozen=True)
class Job:
 tag:int;a:int;b:int;dst:int;m:int;n:int;write_bytes:int;kind:str='rms';role:int=3;cold:bool=True;generation:int=0;dtype:int=5
@dataclass(frozen=True)
class Result:
 tag:int;write_bytes:int;cycles:int=777;status:int=0;committed:bool=True;ack_bytes:int=0;drained:bool=True
@dataclass(frozen=True)
class Residual:
 host:Host;txn:int;job:Job;result:Result
@dataclass(frozen=True)
class Proof:
 host:Host;txn:int;job:Job;logical:Job;result:Result;residual:Residual

def overlap(a,b):return a.base<b.end and b.base<a.end
def policy(role=1,cold=1,generation=0):return 0x21|(S<<32)|(3<<56)|(8<<64)|(cold<<80)|((not cold)<<81)|(role<<82)|(generation<<88)
def fields(v,h,l):return (v>>l)&((1<<(h-l+1))-1)
def policy_ok(v):
 return fields(v,7,0)==0x21 and fields(v,31,8)==0 and fields(v,55,32)==S and fields(v,63,56)==3 and fields(v,71,64)==8 and fields(v,79,72)==0 and fields(v,80,80)==1 and fields(v,81,81)==0 and fields(v,84,82)==1 and fields(v,87,85)==0 and fields(v,119,88)==0 and fields(v,127,120)==0

class Commands:
 def __init__(self,profile=4,rows=128):
  self.host=Host(profile);self.txn=(1<<63)+123;self.h=1024 if profile in (1,2) else 2048;self.rows=rows
  self.residual=Tensor(0x1000000,rows,self.h);self.gamma=Tensor(0x2000000,1,self.h,prefix=(4,5,6));self.output=Tensor(0x3000000,rows,self.h,prefix=(7,8,9))
  self.a=replace(self.residual,tail=40,prefix=(10,11,12));self.b=self.gamma;self.d=self.output
  self.residual_ack=True;self.attention_ack=True;self.readwrite_input=True;self.readonly_gamma=True;self.fresh_output=True;self.same_context=True;self.checkpoint=False;self.cold=True;self.generation=0;self.enabled=True;self.gamma_bound=None
  self.fault=False;self.bound=None;self.bound_metadata=None;self.done_pending=False;self.committed=False;self.accepted=True;self.receipt=None;self.result=None;self.published=False;self.global_root=False;self.completion_payload=None
 def accept(self):
  if self.bound or self.committed or self.done_pending or self.fault or not self.accepted:return False
  if self.host.profile not in (1,2,3,4) or not self.enabled or not self.same_context or self.checkpoint or not self.cold or self.generation!=0:return False
  if not self.residual_ack or self.a.allocation!=self.residual.allocation or not self.readwrite_input:return False
  if self.host.profile in (2,4) and not self.attention_ack:return False
  if not (1<=self.rows<=128) or any(not t.legal() for t in (self.a,self.b,self.d)):return False
  if self.a.rows!=self.rows or self.a.width!=self.h or self.b.rows!=1 or self.b.width!=self.h or self.d.rows!=self.rows or self.d.width!=self.h:return False
  if self.b.tail!=S or self.d.tail!=S or not self.readonly_gamma or not self.fresh_output:return False
  if self.gamma_bound is not None and self.b.allocation!=self.gamma_bound.allocation:return False
  ids=self.a.prefix+self.b.prefix+self.d.prefix+(40,41)
  if len(ids)!=len(set(ids)):return False
  if any(overlap(x,y) for x,y in ((self.a,self.b),(self.a,self.d),(self.b,self.d))):return False
  self.bound=Job((self.host.epoch<<16)|17,self.a.base,self.b.base,self.d.base,self.rows,self.h,self.d.bytes)
  self.bound_metadata=(self.host,self.txn,self.a,self.b,self.d)
  return True
 def proof(self):
  j=replace(self.bound,tag=100);rjob=Job(99,0,0,self.a.base,self.rows,self.h,self.d.bytes,kind='residual',role=0)
  residual=Residual(self.host,self.txn,rjob,Result(99,rjob.write_bytes,ack_bytes=rjob.write_bytes))
  return Proof(self.host,self.txn,j,self.bound,Result(j.tag,j.write_bytes,ack_bytes=j.write_bytes),residual)
 def identity(self):return self.accepted and self.bound_metadata==(self.host,self.txn,self.a,self.b,self.d) and self.bound and self.bound.role==3 and self.bound.cold and self.bound.generation==0 and self.bound.dtype==5
 def proof_ok(self,p):
  if p is None or not self.bound:return False
  j=self.bound;r=p.residual
  return (p.host==self.host and p.txn==self.txn and p.logical==j and p.job==replace(j,tag=p.job.tag) and p.job.tag!=0xffffffff and
   p.result.tag==p.job.tag and p.result.status==0 and p.result.committed and p.result.drained and p.result.write_bytes==j.write_bytes and p.result.ack_bytes==j.write_bytes and
   r.host==self.host and r.txn==self.txn and r.job.kind=='residual' and r.job.dst==j.a and r.job.m==j.m and r.job.n==j.n and r.job.write_bytes==j.write_bytes and
   r.job.tag<p.job.tag and r.job.tag!=0xffffffff and r.result.tag==r.job.tag and r.result.status==0 and r.result.write_bytes==j.write_bytes)
 def done(self,p=None,result=None,fire=True,receipt_valid=True):
  if not self.bound or not fire:return False
  p=self.proof() if p is None else p;result=Result(self.bound.tag,self.bound.write_bytes,ack_bytes=self.bound.write_bytes) if result is None else result
  ok=not self.fault and self.identity() and receipt_valid and self.proof_ok(p) and result.tag==self.bound.tag and result.status==0 and result.write_bytes==self.bound.write_bytes and result.cycles==p.result.cycles
  self.done_pending=ok;self.receipt=p if ok else None;self.result=result;self.completion_payload=(self.bound.tag,0 if ok else 1)
  if not ok:self.fault=True
  return ok
 def completion(self,ready=True,p=None,receipt_valid=True):
  if self.completion_payload is None:return None
  held=self.completion_payload
  if not ready:return held
  p=self.receipt if p is None else p
  ok=not self.fault and self.done_pending and self.identity() and receipt_valid and self.proof_ok(p) and p==self.receipt
  self.committed=ok;self.published=ok;self.done_pending=False
  if not ok:self.fault=True
  self.completion_payload=None
  return held
 def current_receipt(self):return self.committed and self.accepted and not self.fault and self.receipt.host==self.host and self.receipt.txn==self.txn

class PostnormCommands(unittest.TestCase):
 def test_all_four_actual_chains(self):
  for p in range(1,5):
   for rows in ((16,128) if p in (1,3) else (128,)):
    x=Commands(p,rows);self.assertTrue(x.accept());self.assertTrue(x.done());self.assertFalse(x.current_receipt());x.completion();self.assertTrue(x.current_receipt());self.assertFalse(x.global_root)
 def test_policy_all_bits(self):
  v=policy();self.assertTrue(policy_ok(v))
  for b in range(128):self.assertFalse(policy_ok(v^(1<<b)),b)
 def test_inputnorm_not_postnorm(self):
  self.assertFalse(policy_ok(policy(role=0)))
  x=Commands();x.accept();x.bound=replace(x.bound,role=0);self.assertFalse(x.done())
 def test_requires_actual_residual(self):
  x=Commands();x.residual_ack=False;self.assertFalse(x.accept())
 def test_requires_both_attention_views(self):
  for p in (2,4):
   x=Commands(p);x.attention_ack=False;self.assertFalse(x.accept())
 def test_no_readonly_lookalike(self):
  x=Commands();x.readwrite_input=False;self.assertFalse(x.accept())
 def test_same_allocation_not_policy_tail(self):
  x=Commands();self.assertNotEqual(x.a.tail,x.residual.tail);self.assertNotEqual(x.a.prefix,x.residual.prefix);self.assertTrue(x.accept())
 def test_residual_allocation_fields(self):
  for kw in (dict(base=0x1000040),dict(rows=16),dict(width=1024),dict(dtype=7),dict(rank=3),dict(extent=64),dict(count_delta=1)):
   x=Commands();x.a=replace(x.a,**kw);self.assertFalse(x.accept())
 def test_gamma_exact_dtype_shape(self):
  for kw in (dict(rows=2),dict(width=1024),dict(dtype=7),dict(rank=1),dict(extent=64),dict(count_delta=1),dict(tail=40)):
   x=Commands();x.b=replace(x.b,**kw);self.assertFalse(x.accept())
 def test_gamma_role_replay(self):
  x=Commands();x.gamma_bound=replace(x.b,width=1024);self.assertFalse(x.accept())
 def test_gamma_and_output_permissions(self):
  for attr in ('readonly_gamma','fresh_output'):
   x=Commands();setattr(x,attr,False);self.assertFalse(x.accept())
 def test_bounds_and_disjoint(self):
  for role in ('a','b','d'):
   for base in ((1<<56)-64,0x1000001):
    x=Commands();setattr(x,role,replace(getattr(x,role),base=base));self.assertFalse(x.accept())
  x=Commands();x.d=replace(x.d,base=x.a.base);self.assertFalse(x.accept())
 def test_descriptor_indices_unique(self):
  x=Commands();x.b=replace(x.b,prefix=x.a.prefix);self.assertFalse(x.accept())
 def test_cold_gen0_profile_seal(self):
  for attr,value in [('cold',False),('generation',1),('checkpoint',True),('same_context',False),('enabled',False)]:
   x=Commands();setattr(x,attr,value);self.assertFalse(x.accept())
  for p in (0,5):self.assertFalse(Commands(p).accept())
 def test_full_host_before_done(self):
  for kw in (dict(epoch=20),dict(command_base=0x3000),dict(descriptor_base=0x4000),dict(region_limit=1<<41),dict(profile=3)):
   x=Commands();x.accept();x.host=replace(x.host,**kw);self.assertFalse(x.done())
 def test_txn64_high_bits(self):
  x=Commands();x.accept();x.txn^=1<<63;self.assertFalse(x.done())
 def test_bound_metadata_replay(self):
  for role in ('a','b','d'):
   for kw in (dict(tail=42),dict(prefix=(20,21,22)),dict(base=0x5000000)):
    x=Commands();x.accept();setattr(x,role,replace(getattr(x,role),**kw));self.assertFalse(x.done())
 def test_no_done_no_publish(self):
  x=Commands();x.accept();self.assertIsNone(x.completion());self.assertFalse(x.current_receipt())
 def test_no_fire_no_publish(self):
  x=Commands();x.accept();self.assertFalse(x.done(fire=False));self.assertFalse(x.current_receipt())
 def test_no_private_physical_proof(self):
  x=Commands();x.accept();self.assertFalse(x.done(receipt_valid=False));self.assertFalse(x.current_receipt())
 def test_known_bad_proof_never_offers_success_completion(self):
  x=Commands();x.accept();self.assertFalse(x.done(receipt_valid=False));self.assertEqual(x.completion_payload[1],1)
 def test_restore_logical_tag_not_physical(self):
  x=Commands();x.accept();p=x.proof();self.assertNotEqual(p.job.tag,x.bound.tag);self.assertTrue(x.done(p));x.completion();self.assertTrue(x.current_receipt())
 def test_physical_owner_order(self):
  for tag in (99,98,0xffffffff):
   x=Commands();x.accept();p=x.proof();p=replace(p,job=replace(p.job,tag=tag),result=replace(p.result,tag=tag));self.assertFalse(x.done(p))
 def test_proof_generic_result(self):
  for kw in (dict(tag=101),dict(write_bytes=0),dict(status=1),dict(committed=False),dict(ack_bytes=0),dict(drained=False),dict(cycles=778)):
   x=Commands();x.accept();p=x.proof();self.assertFalse(x.done(replace(p,result=replace(p.result,**kw))))
 def test_proof_residual_identity(self):
  for field,value in [('host',Host(epoch=20)),('txn',1)]:
   x=Commands();x.accept();p=x.proof();self.assertFalse(x.done(replace(p,residual=replace(p.residual,**{field:value}))))
 def test_proof_residual_shape_and_ack(self):
  for kw in (dict(dst=0),dict(m=16),dict(n=1024),dict(write_bytes=0),dict(kind='inputnorm')):
   x=Commands();x.accept();p=x.proof();self.assertFalse(x.done(replace(p,residual=replace(p.residual,job=replace(p.residual.job,**kw)))))
  for kw in (dict(tag=98),dict(status=1),dict(write_bytes=0)):
   x=Commands();x.accept();p=x.proof();self.assertFalse(x.done(replace(p,residual=replace(p.residual,result=replace(p.residual.result,**kw)))))
 def test_generic_guard_done(self):
  for kw in (dict(tag=0),dict(status=1),dict(write_bytes=0),dict(cycles=778)):
   x=Commands();x.accept();r=Result(x.bound.tag,x.bound.write_bytes,ack_bytes=x.bound.write_bytes);self.assertFalse(x.done(result=replace(r,**kw)))
 def test_held_completion_no_early_ffn(self):
  x=Commands();x.accept();x.done();bits=x.completion_payload
  for _ in range(7):self.assertEqual(x.completion(False),bits);self.assertFalse(x.current_receipt());self.assertFalse(x.published)
  self.assertEqual(x.completion(),bits);self.assertTrue(x.current_receipt())
 def test_late_fault_held_bits(self):
  x=Commands();x.accept();x.done();bits=x.completion(False);x.fault=True
  self.assertEqual(x.completion(False),bits);self.assertEqual(x.completion(),bits);self.assertFalse(x.current_receipt());self.assertFalse(x.published)
 def test_proof_replacement_during_completion(self):
  x=Commands();x.accept();x.done();p=replace(x.receipt,result=replace(x.receipt.result,cycles=778));x.completion(p=p);self.assertFalse(x.current_receipt())
 def test_proof_revocation_during_completion(self):
  x=Commands();x.accept();x.done();x.completion(receipt_valid=False);self.assertFalse(x.current_receipt())
 def test_lifetime_change_during_completion(self):
  for attr,value in [('txn',10),('host',Host(epoch=20)),('accepted',False)]:
   x=Commands();x.accept();x.done();setattr(x,attr,value);x.completion();self.assertFalse(x.current_receipt())
 def test_replay_completed_postnorm(self):
  x=Commands();x.accept();x.done();x.completion();x.bound=None;self.assertFalse(x.accept())
 def test_receipt_revoked_after_context(self):
  x=Commands();x.accept();x.done();x.completion();self.assertTrue(x.current_receipt());x.txn+=1;self.assertFalse(x.current_receipt())
 def test_no_root_fence_publish(self):
  x=Commands();x.accept();x.done();x.completion();self.assertTrue(x.current_receipt());self.assertFalse(x.global_root)
 def test_late_fault_preserves_held_moe_structural_intent(self):
  x=Commands();x.accept();x.done();x.completion();self.assertTrue(x.committed)
  held=True;x.fault=True
  self.assertFalse(x.current_receipt())
  self.assertTrue(x.committed and (not x.fault or held))
  self.assertFalse(x.committed and (not x.fault or False))
if __name__=='__main__':unittest.main()
