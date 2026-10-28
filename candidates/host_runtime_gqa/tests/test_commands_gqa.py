"""Independent Commands protocol model. Not Scala/Chisel/RTL/numerical execution."""
from dataclasses import dataclass, replace
import unittest
S=(1<<24)-1

def field(v,h,l):return (v>>l)&((1<<(h-l+1))-1)
def record(op,heads):
 cp=0x24|(23<<32)|(2<<56)|(op<<64)|(128<<100)|(0xa1<<108)
 cx=0x26|(S<<32)|(2<<56)|(128<<64)|(1<<123)|(1<<124)
 return cp,cx

def policy_ok(op,cp,cx):
 return (field(cp,7,0)==0x24 and field(cp,31,8)==0 and field(cp,55,32)!=S and field(cp,63,56)==2 and
  field(cp,67,64)==op and field(cp,99,68)==0 and field(cp,107,100)==128 and field(cp,115,108)==0xa1 and field(cp,127,116)==0 and
  field(cx,7,0)==0x26 and field(cx,31,8)==0 and field(cx,55,32)==S and field(cx,63,56)==2 and field(cx,72,64)==128 and
  field(cx,81,73)==0 and field(cx,90,82)==0 and field(cx,122,91)==0 and field(cx,123,123)==1 and field(cx,124,124)==1 and field(cx,127,125)==0)
@dataclass(frozen=True)
class Tensor:
 address:int;dims:tuple;rank:int;dtype:int=5;padding:int=0
 @property
 def payload(self):
  n=2
  for d in self.dims:n*=d
  return n
 @property
 def end(self):return self.address+self.payload+self.padding

def legal(t):return t.address>=0 and t.address%64==0 and t.end<=1<<56 and t.dtype==5 and not t.padding
def overlap(a,b):return a.address<b.end and b.address<a.end
@dataclass(frozen=True)
class Command:
 op:int;opcode:int;engine:int;signal:int;wait:int;a:Tensor;b:Tensor|None;d:Tensor;cp:int;cx:int

def commands(profile):
 h={2:8,4:16}[profile]
 q=Tensor(0x100000,(128,h*256,1,1),2);cache=Tensor(0x300000,(2,128,512,1),3)
 score=Tensor(0x400000,(h,128,128,1),3);prob=Tensor(0x500000,(h,128,128,1),3);out=Tensor(0x600000,(128,h*256,1,1),2)
 return [Command(1,0x23,2,31,30,q,cache,score,*record(1,h)),Command(2,0x33,3,32,31,score,None,prob,*record(2,h)),Command(3,0x24,2,33,32,prob,cache,out,*record(3,h))]

class Ledger:
 def __init__(self,profile=4):
  self.profile=profile;self.h={2:8,4:16}.get(profile,0);self.g=0;self.prev=30;self.events={30};self.virtual=[];self.captured=[]
  self.projected=[True]*3;self.normalized=[True]*2;self.rotated=[True]*2;self.positions=[0,0];self.rows=[128]*3;self.counts=[128]*3;self.bases=[0]*3
  self.pending=True;self.pending_gqa=False;self.cold=True;self.gen=0;self.global_cache=False
  self.cache=commands(4)[0].b;self.q=commands(profile if profile in (2,4) else 4)[0].a
  self.job=None;self.done=False;self.idx=0;self.produced=0;self.ack_events=[];self.fault=False;self.policy_order=1
 def accept(self,c):
  if self.profile not in (2,4) or self.global_cache or not self.cold or self.gen or not self.pending or self.pending_gqa or self.fault:return False
  if c.op!=self.g+1 or (c.opcode,c.engine)!={1:(0x23,2),2:(0x33,3),3:(0x24,2)}[c.op] or not policy_ok(c.op,c.cp,c.cx):return False
  expected=self.prev if self.g==0 else self.captured[-1].signal
  if c.wait!=expected or c.signal<=0 or c.signal>=256 or c.signal in self.events or c.signal==c.wait or any(c.signal==x.signal for x in self.captured):return False
  if not all(legal(t) for t in (c.a,c.d)+((c.b,) if c.b else ())):return False
  if c.b and (overlap(c.a,c.b) or overlap(c.d,c.b)):return False
  if overlap(c.d,c.a) or any(overlap(c.d,v) for v in self.virtual):return False
  if overlap(c.d,self.q) or overlap(c.d,self.cache):return False
  score_dims=(self.h,128,128,1);query_dims=(128,self.h*256,1,1)
  if c.op==1:
   good=(all(self.projected) and all(self.normalized) and all(self.rotated) and self.positions==[0,0] and self.rows==[128]*3 and self.counts==[128]*3 and self.bases==[0]*3 and c.a==self.q and c.b==self.cache and c.d.dims==score_dims and c.d.rank==3)
  elif c.op==2:good=c.a==self.captured[0].d and c.b is None and c.d.dims==score_dims and c.d.rank==3
  else:good=c.a==self.captured[1].d and c.b==self.cache and c.d.dims==query_dims and c.d.rank==2
  if not good:return False
  self.captured.append(c)
  if c.op<3:self.virtual.append(c.d);self.g+=1
  else:
   self.job=dict(m=128,n=self.h*256,k=256,a=self.q.address,b=self.cache.address,dst=c.d.address,capacity=128,length=128,expected_length=0,position=0,expected_gen=0,current_gen=0,cold=True,order=1)
  return True
 def return_done(self,tag=73,expected=73,status=0,bytes_=None,macs=None,fire=True):
  if not self.job or not fire:return False
  n=self.job['n'];good=(tag==expected and status==0 and (128*n*2 if bytes_ is None else bytes_)==128*n*2 and (2*128*128*n if macs is None else macs)==2*128*128*n)
  self.done=good
  if not good:self.fault=True
  return good
 def completion(self,ready=True,fault=False):
  if not self.done:return None
  payload=self.captured[self.idx].signal
  if not ready:return payload
  if fault or self.fault:self.fault=True;self.done=False;return payload
  self.events.add(payload);self.ack_events.append(payload);self.prev=payload
  if self.idx<2:self.idx+=1
  else:self.pending_gqa=True;self.produced+=1;self.done=False;self.g=0
  return payload

class GqaCommands(unittest.TestCase):
 def finish(self,profile=4):
  l=Ledger(profile)
  for c in commands(profile):self.assertTrue(l.accept(c))
  return l
 def test_both_profiles_only_runtime_geometry(self):
  for p,h in ((2,8),(4,16)):
   l=self.finish(p);self.assertEqual(l.job['n'],h*256);self.assertEqual(l.job['order'],1);self.assertEqual(l.job['length'],128)
 def test_not_launched_until_all_three_validated(self):
  l=Ledger();cs=commands(4)
  for c in cs[:2]:self.assertTrue(l.accept(c));self.assertIsNone(l.job)
  self.assertTrue(l.accept(cs[2]));self.assertIsNotNone(l.job)
 def test_all_required_producers(self):
  for name in ('projected','normalized','rotated'):
   for i in range(len(getattr(Ledger(),name))):
    l=Ledger();getattr(l,name)[i]=False;self.assertFalse(l.accept(commands(4)[0]))
 def test_no_legacy_profiles(self):
  for p in (0,1,3,5,7):self.assertFalse(Ledger(p).accept(commands(4)[0]))
 def test_cold_context_only(self):
  for attr,val in [('pending',False),('pending_gqa',True),('cold',False),('gen',1),('global_cache',True),('fault',True),('positions',[1,1]),('rows',[16]*3),('counts',[16]*3),('bases',[1]*3)]:
   l=Ledger();setattr(l,attr,val);self.assertFalse(l.accept(commands(4)[0]),attr)
 def test_policy_all_fixed_bits(self):
  for op in (1,2,3):
   cp,cx=record(op,16)
   for bit in list(range(32))+list(range(56,128)):
    self.assertFalse(policy_ok(op,cp^(1<<bit),cx),(op,'cp',bit))
   for bit in range(128):self.assertFalse(policy_ok(op,cp,cx^(1<<bit)),(op,'cx',bit))
 def test_policy_pointer_not_arithmetic_authority(self):
  cp,cx=record(1,16)
  self.assertTrue(policy_ok(1,cp^(1<<32),cx));self.assertFalse(policy_ok(1,(cp&~(S<<32))|(S<<32),cx))
 def test_query_exact_not_lookalike(self):
  c=commands(4)[0]
  for a in (replace(c.a,address=c.a.address+64),replace(c.a,dtype=7),replace(c.a,padding=64),replace(c.a,rank=3),replace(c.a,dims=(128,2048,1,1))):
   self.assertFalse(Ledger().accept(replace(c,a=a)))
 def test_cache_exact_complete_allocation(self):
  c=commands(4)[0]
  for b in (replace(c.b,address=c.b.address+64),replace(c.b,dims=(2,127,512,1)),replace(c.b,padding=64)):
   self.assertFalse(Ledger().accept(replace(c,b=b)))
 def test_group_order_signal_wait(self):
  cs=commands(4)
  for c in (cs[1],cs[2],replace(cs[0],wait=29),replace(cs[0],signal=30),replace(cs[0],signal=256),replace(cs[0],engine=3)):
   self.assertFalse(Ledger().accept(c))
  for mutation in (dict(wait=30),dict(signal=31),dict(signal=0),dict(opcode=0x24)):
   l=Ledger();self.assertTrue(l.accept(cs[0]));self.assertFalse(l.accept(replace(cs[1],**mutation)))
 def test_each_fused_shape_checked(self):
  for stage in range(3):
   cs=commands(4);l=Ledger()
   for c in cs[:stage]:self.assertTrue(l.accept(c))
   self.assertFalse(l.accept(replace(cs[stage],d=replace(cs[stage].d,rank=4))))
 def test_score_probability_never_ddr_producer(self):
  l=self.finish();self.assertEqual(l.produced,0);self.assertEqual(len(l.virtual),2);self.assertFalse(l.pending_gqa)
 def test_ack_bytes_and_logical_macs(self):
  for p in (2,4):
   l=self.finish(p);n=l.job['n'];self.assertTrue(l.return_done(bytes_=128*n*2,macs=2*128*128*n))
  l=self.finish(4);self.assertFalse(l.return_done(macs=128*128<<12))
 def test_q16_exactly_twice_q8_no_uplift_claim(self):self.assertEqual(2*128*128*16*256,2*(2*128*128*8*256))
 def test_done_rejection(self):
  for kw in (dict(tag=74),dict(status=1),dict(bytes_=0),dict(macs=0),dict(fire=False)):
   l=self.finish();self.assertFalse(l.return_done(**kw));self.assertFalse(l.pending_gqa)
 def test_three_ordered_completions_one_publication(self):
  l=self.finish();self.assertTrue(l.return_done())
  for i,event in enumerate((31,32,33)):
   self.assertEqual(l.completion(),event);self.assertEqual(l.produced,int(i==2));self.assertEqual(l.pending_gqa,i==2)
  self.assertEqual(l.ack_events,[31,32,33]);self.assertFalse(l.global_cache);self.assertEqual(l.gen,0)
 def test_completion_backpressure_stable(self):
  l=self.finish();l.return_done()
  for expected in (31,32,33):
   for _ in range(5):self.assertEqual(l.completion(ready=False),expected)
   self.assertEqual(l.completion(),expected)
  self.assertEqual(l.produced,1)
 def test_late_fault_vetoes_every_stage(self):
  for fault_index in range(3):
   l=self.finish();l.return_done()
   for _ in range(fault_index):l.completion()
   self.assertEqual(l.completion(fault=True),31+fault_index);self.assertFalse(l.pending_gqa);self.assertEqual(l.produced,0);self.assertFalse(l.global_cache)
 def test_no_spurious_completion_or_refund(self):
  l=self.finish();self.assertIsNone(l.completion());self.assertFalse(l.pending_gqa);self.assertIsNotNone(l.job)
if __name__=='__main__':unittest.main()
