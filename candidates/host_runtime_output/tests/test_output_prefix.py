"""Independent bounded output-tail protocol model. NOT Chisel/RTL/DUT proof."""
from dataclasses import dataclass, replace
import unittest

@dataclass(frozen=True)
class Host:
 profile:int=2
 epoch:int=9
 program:int=0x1000
 regions:tuple=((0,1<<56,True,True),)
@dataclass(frozen=True)
class Job:
 kind:str='gate'
 tag:int=14
 m:int=128
 n:int=2048
 k:int=2048
 a:int=0x100000
 b:int=0x200000
 dst:int=0x300000
 op:int=2
 role:int=0
 cold:bool=True
 generation:int=0
 materialize:bool=False
@dataclass(frozen=True)
class Receipt:
 job:Job
 host:Host=Host()
 transaction:int=(1<<50)+7
 status:int=0
 result_tag:int=0
 ack:int=0
 accepted:Job=None
 valid:bool=True
 committed:bool=True
 drained:bool=True

def receipt(j, host=Host(), **kw):
 return Receipt(j,host,result_tag=j.tag,ack=2*j.m*j.n,accepted=j,**kw)
def current(r,h,t):return r.valid and r.host==h and r.transaction==t

def exact(r):
 return r.status==0 and r.committed and r.drained and r.result_tag==r.job.tag and r.accepted==r.job and r.ack==2*r.job.m*r.job.n and 0<=r.job.tag<0xffffffff

def shape(j,h):
 if h.profile not in (1,2,3,4) or not j.cold or j.generation:return False
 hidden=1024 if h.profile<=2 else 2048; context=2*hidden
 rows=j.m in (16,128) if h.profile in (1,3) else j.m==128
 return rows and ((j.kind=='gate' and h.profile in (2,4) and (j.n,j.k,j.op)==(context,context,2)) or
  (j.kind=='dense_o' and not j.materialize and (j.n,j.k,j.role)==(hidden,context,3)) or
  (j.kind=='residual' and (j.n,j.k,j.op)==(hidden,hidden,0)))

def admission(j,a,b,h=Host(),t=(1<<50)+7,previous=None,physical=True,fault=False):
 if fault or not shape(j,h) or not current(a,h,t) or not exact(a):return False
 if b is not None and (not current(b,h,t) or not exact(b)):return False
 producers=[a.job.tag]+([] if b is None else [b.job.tag])
 if physical and not all(p<j.tag<0xffffffff for p in producers):return False
 if previous is not None:
  tx,old=previous
  if t<tx or (t==tx and not all(p>v for p,v in zip(producers,old))):return False
 if j.kind=='gate':
  return a.job.kind=='q_gate' and a.job.dst==j.a and a.job.m==j.m and a.job.n==j.n and b.job.kind=='gqa' and b.job.dst==j.b and (b.job.m,b.job.n)==(j.m,j.n)
 if j.kind=='dense_o':
  return a.job.dst==j.a and a.job.m==j.m and a.job.n==j.k and a.job.kind==('gate' if h.profile in (2,4) else 'gated_norm')
 return a.job.kind=='input_norm' and a.job.role==0 and a.job.a==j.a and (a.job.m,a.job.n)==(j.m,j.n) and b.job.kind=='dense_o' and b.job.role==3 and b.job.dst==j.b and (b.job.m,b.job.n)==(j.m,j.n)

def counts(m,n,op):
 return {'scalar':m*n*(5 if op==2 else 1),'format':m*n*(2 if op==2 else 1),'memory':3*((m*n)//32),'bytes':2*m*n}
def terminal(j,event,scalar,formatter):
 want=counts(j.m,j.n,j.op)
 return event['tag']==j.tag and event['accepted']==j and event['status']==0 and event['committed'] and event['drained'] and all(event[k]==want[v] for k,v in [('scalar_accepted','scalar'),('scalar_returned','scalar'),('format_accepted','format'),('format_returned','format'),('memory_accepted','memory'),('memory_returned','memory'),('ack','bytes'),('bytes','bytes')]) and scalar=={'slot':8,'kind':9,'stage':77,'accepted':want['scalar'],'issued':want['scalar'],'returned':want['scalar'],'drained':True} and formatter=={'slot':9,'kind':9,'stage':77,'accepted':want['format'],'issued':want['format'],'returned':want['format'],'drained':True}

def gate_fixture(profile=2):
 h=Host(profile=profile);n=2048 if profile==2 else 4096
 j=replace(Job(),n=n,k=n)
 a=receipt(Job(kind='q_gate',tag=4,n=n,k=n,dst=j.a),h)
 b=receipt(Job(kind='gqa',tag=13,n=n,k=256,dst=j.b),h)
 return j,a,b,h

def dense_fixture(profile=2,m=128):
 h=Host(profile=profile);n=1024 if profile<=2 else 2048
 j=Job(kind='dense_o',tag=15,m=m,n=n,k=2*n,role=3)
 p=receipt(Job(kind='gate' if profile in (2,4) else 'gated_norm',tag=14,m=m,n=2*n,k=2*n,dst=j.a),h)
 return j,p,h

def residual_fixture(profile=2,m=128):
 h=Host(profile=profile);n=1024 if profile<=2 else 2048
 j=Job(kind='residual',tag=16,m=m,n=n,k=n,op=0)
 a=receipt(Job(kind='input_norm',tag=0,m=m,n=n,k=n,a=j.a),h)
 b=receipt(Job(kind='dense_o',tag=15,m=m,n=n,k=2*n,role=3,dst=j.b),h)
 return j,a,b,h

class OutputPrefixTests(unittest.TestCase):
 def test_two_attention_profiles(self):
  for profile in (2,4):j,a,b,h=gate_fixture(profile);self.assertTrue(admission(j,a,b,h))
 def test_four_o_profiles(self):
  for profile in (1,2,3,4):
   for m in ((16,128) if profile in (1,3) else (128,)):
    j,p,h=dense_fixture(profile,m);self.assertTrue(admission(j,p,None,h))
 def test_four_residual_profiles(self):
  for profile in (1,2,3,4):
   for m in ((16,128) if profile in (1,3) else (128,)):
    j,a,b,h=residual_fixture(profile,m);self.assertTrue(admission(j,a,b,h))
 def test_no_qwen2_profile_or_short_attention(self):
  j,a,b,h=gate_fixture();self.assertFalse(admission(j,a,b,replace(h,profile=0)));self.assertFalse(admission(replace(j,m=16),a,b,h))
 def test_no_silu(self):
  j,a,b,h=gate_fixture();self.assertFalse(admission(replace(j,op=1),a,b,h))
 def test_no_stale_or_fake_flags(self):
  j,a,b,h=gate_fixture()
  for key in ('valid','committed','drained'):
   self.assertFalse(admission(j,replace(a,**{key:False}),b,h));self.assertFalse(admission(j,a,replace(b,**{key:False}),h))
 def test_exact_accepted_payload(self):
  j,a,b,h=gate_fixture();self.assertFalse(admission(j,replace(a,accepted=replace(a.job,a=123)),b,h));self.assertFalse(admission(j,a,replace(b,accepted=replace(b.job,a=123)),h))
 def test_all_ack_bytes(self):
  j,a,b,h=gate_fixture();self.assertFalse(admission(j,replace(a,ack=a.ack-64),b,h));self.assertFalse(admission(j,a,replace(b,ack=b.ack-64),h))
 def test_full_host_and_region(self):
  j,a,b,h=gate_fixture()
  for other in [replace(h,epoch=h.epoch+1),replace(h,program=0x2000),replace(h,regions=((0,1<<56,False,True),))]:
   self.assertFalse(admission(j,replace(a,host=other),b,h));self.assertFalse(admission(j,a,replace(b,host=other),h))
 def test_transaction_high_bits(self):
  j,a,b,h=gate_fixture();self.assertFalse(admission(j,replace(a,transaction=7),b,h));self.assertFalse(admission(j,a,replace(b,transaction=7),h))
 def test_strict_both_producers(self):
  j,a,b,h=gate_fixture()
  for tag in (j.tag,j.tag+1,0xffffffff,0x100000004):
   self.assertFalse(admission(j,receipt(replace(a.job,tag=tag)),b,h));self.assertFalse(admission(j,a,receipt(replace(b.job,tag=tag)),h))
 def test_independent_replay(self):
  j,a,b,h=gate_fixture()
  for previous in [(a.transaction,[a.job.tag,0]),(a.transaction,[0,b.job.tag]),(a.transaction+1,[0,0])]:self.assertFalse(admission(j,a,b,h,previous=previous))
  self.assertTrue(admission(j,a,b,h,previous=(a.transaction-1,[999,999])))
 def test_q_gate_opaque_not_norm_or_silu(self):
  j,a,b,h=gate_fixture()
  for kind in ('q_norm','gated_norm','gate','input_norm'):self.assertFalse(admission(j,receipt(replace(a.job,kind=kind)),b,h))
 def test_dense_must_match_profile_producer(self):
  for profile in (1,2,3,4):
   j,p,h=dense_fixture(profile)
   self.assertFalse(admission(j,receipt(replace(p.job,kind='gated_norm' if p.job.kind=='gate' else 'gate'),h),None,h))
 def test_original_raw_hidden_not_norm_output(self):
  j,a,b,h=residual_fixture();self.assertFalse(admission(replace(j,a=a.job.dst),a,b,h));self.assertFalse(admission(j,receipt(replace(a.job,role=3)),b,h))
 def test_O_ack_before_residual(self):
  j,a,b,h=residual_fixture();self.assertFalse(admission(j,a,replace(b,valid=False),h));self.assertFalse(admission(j,a,receipt(replace(b.job,role=2)),h))
 def test_invalid_shape_and_storage(self):
  j,p,h=dense_fixture()
  for key,val in [('n',2048),('k',4096),('role',2),('cold',False),('generation',1),('materialize',True)]:self.assertFalse(admission(replace(j,**{key:val}),p,None,h))
 def test_logical_pre_veto_does_not_need_future_sequence(self):
  j,p,h=dense_fixture();self.assertTrue(admission(replace(j,tag=0),p,None,h,physical=False));self.assertFalse(admission(replace(j,a=0),p,None,h,physical=False))
 def test_late_fault_never_receipt(self):
  j,p,h=dense_fixture();self.assertTrue(admission(j,p,None,h));self.assertFalse(admission(j,p,None,h,fault=True))
 def test_exact_counts(self):
  for m,n,op in [(16,1024,0),(16,2048,0),(128,1024,0),(128,2048,0),(128,2048,2),(128,4096,2)]:
   actual={'scalar':0,'format':0,'memory':0,'bytes':0}
   for beat in range(m*n//32):
    actual['memory']+=3;actual['bytes']+=64
    for lane in range(32):actual['scalar']+=5 if op==2 else 1;actual['format']+=2 if op==2 else 1
   self.assertEqual(counts(m,n,op),actual)
 def test_caps_not_other_domain(self):
  self.assertEqual(counts(128,4096,2),{'scalar':2621440,'format':1048576,'memory':49152,'bytes':1048576})
 def test_terminal_every_field(self):
  for j in [gate_fixture()[0],residual_fixture()[0]]:
   v=counts(j.m,j.n,j.op)
   event=dict(tag=j.tag,accepted=j,status=0,committed=True,drained=True,scalar_accepted=v['scalar'],scalar_returned=v['scalar'],format_accepted=v['format'],format_returned=v['format'],memory_accepted=v['memory'],memory_returned=v['memory'],ack=v['bytes'],bytes=v['bytes'])
   scalar=dict(slot=8,kind=9,stage=77,accepted=v['scalar'],issued=v['scalar'],returned=v['scalar'],drained=True)
   formatter=dict(slot=9,kind=9,stage=77,accepted=v['format'],issued=v['format'],returned=v['format'],drained=True)
   self.assertTrue(terminal(j,event,scalar,formatter))
   for key,value in event.items():
    wrong=replace(j,a=1) if key=='accepted' else not value if isinstance(value,bool) else value+1
    self.assertFalse(terminal(j,{**event,key:wrong},scalar,formatter),key)
   for packet in ('scalar','formatter'):
    orig=scalar if packet=='scalar' else formatter
    for key,value in orig.items():
     bad={**orig,key:(not value if isinstance(value,bool) else value+1)}
     self.assertFalse(terminal(j,event,bad if packet=='scalar' else scalar,bad if packet=='formatter' else formatter),(packet,key))

if __name__=='__main__':unittest.main(verbosity=2)
