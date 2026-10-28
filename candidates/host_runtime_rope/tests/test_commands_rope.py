"""Local decoder/publication contract model only, not Scala/Chisel/DUT.
Full Host/txn64/epoch/owner correlation is the real Guard/Prefix responsibility;
this model deliberately does NOT claim to execute that path.
"""
from dataclasses import dataclass,replace
import unittest

@dataclass(frozen=True)
class Tensor:
 address:int;rows:int;width:int;dtype:int=5;rank:int=2;extra_padding:int=0
 @property
 def payload(self):return self.rows*self.width*2
 @property
 def end(self):return self.address+self.payload+self.extra_padding

def overlap(a,b):return a.address<b.end and b.address<a.end

@dataclass(frozen=True)
class Command:
 profile:int=4;role:int=0;rows:int=128;base:int=0;count:int=128;position:int=0;policy:int=0xb1
 cold:bool=True;generation:int=0;cache:bool=False;trig_rows:int=128;trig_width:int=64
 readonly_trig:bool=True;writable_output:bool=True;distinct:bool=True;input_live:bool=True;fresh:bool=True
 @property
 def heads(self):return (8 if self.profile==2 else 16) if self.role==0 else 2
 @property
 def input(self):return Tensor(0x1000000+self.role*0x200000,self.rows,self.heads*256)
 @property
 def trig(self):return Tensor(0x4000000,self.trig_rows,self.trig_width)
 @property
 def output(self):return Tensor(0x5000000+self.role*0x200000,self.rows,self.heads*256)
 @property
 def write_bytes(self):return self.count*self.heads*512

class Ledger:
 def __init__(self):
  self.norm=[None,None];self.rotated=[None,None];self.positions=[None,None];self.trig=None
 def normalized(self,c):self.norm[c.role]=c.input
 def eligible(self,c,input_override=None,output_override=None):
  inp=input_override or c.input;out=output_override or c.output
  geometry=(c.profile in (2,4) and c.role in (0,1) and 1<=c.rows<=128 and c.base==0 and c.count==c.rows and
            c.cold and c.generation==0 and not c.cache and c.policy==0xb1 and c.trig_width==64 and
            c.trig_rows>0 and c.position+c.count<=c.trig_rows and c.position==0)
  provenance=(all(x is not None for x in self.norm) and self.norm[c.role]==inp and self.rotated[c.role] is None and
              ((self.rotated[1] is None) if c.role==0 else (self.rotated[0] is not None and self.positions[0]==c.position)))
  source=(c.readonly_trig and (self.trig is None or self.trig==c.trig))
  bounds=c.distinct and c.input_live and c.fresh and c.writable_output
  disjoint=not overlap(inp,c.trig) and not overlap(inp,out) and not overlap(c.trig,out)
  return geometry and provenance and source and bounds and disjoint
 def publish(self,c,tag=37,expected_tag=37,status=0,ack=None,completion=True,fault=False):
  # Models only Commands publication gates, not a fabricated hardware receipt.
  good=tag==expected_tag and status==0 and (c.write_bytes if ack is None else ack)==c.write_bytes and completion and not fault
  if good:self.rotated[c.role]=c.output;self.positions[c.role]=c.position;self.trig=c.trig
  return good

class CommandsRope(unittest.TestCase):
 def setUp(self):
  self.q=Command();self.k=replace(self.q,role=1);self.l=Ledger();self.l.normalized(self.q);self.l.normalized(self.k)
 def test_q_then_k_actual_publication(self):
  self.assertTrue(self.l.eligible(self.q));self.assertFalse(self.l.eligible(self.k))
  self.assertTrue(self.l.publish(self.q));self.assertTrue(self.l.eligible(self.k));self.assertTrue(self.l.publish(self.k))
 def test_requires_both_norm_producers(self):
  self.l.norm[1]=None;self.assertFalse(self.l.eligible(self.q))
 def test_preloaded_same_shape_not_producer(self):
  self.l.norm=[None,None];self.assertFalse(self.l.eligible(self.q))
 def test_typed_norm_not_address_only(self):
  self.assertFalse(self.l.eligible(self.q,input_override=replace(self.q.input,extra_padding=64)))
 def test_wrong_norm_shape(self):self.assertFalse(self.l.eligible(self.q,input_override=replace(self.q.input,width=2048)))
 def test_no_repeat_q(self):self.l.publish(self.q);self.assertFalse(self.l.eligible(self.q))
 def test_no_repeat_k(self):self.l.publish(self.q);self.l.publish(self.k);self.assertFalse(self.l.eligible(self.k))
 def test_geometry_no_fake_success(self):
  for x in (dict(rows=0,count=0),dict(rows=129,count=129),dict(base=1),dict(count=127),dict(profile=0),dict(policy=0xc1),dict(trig_width=32),dict(trig_rows=127),dict(position=1),dict(cold=False),dict(generation=1),dict(cache=True)):
   self.assertFalse(self.l.eligible(replace(self.q,**x)),x)
 def test_alias_rejected(self):self.assertFalse(self.l.eligible(self.q,output_override=replace(self.q.output,address=self.q.input.address)))
 def test_trig_rebind_rejected(self):
  self.l.publish(self.q);self.assertFalse(self.l.eligible(replace(self.k,trig_rows=256)))
 def test_permission_dependency_and_distinct(self):
  for x in ('readonly_trig','writable_output','distinct','input_live','fresh'):
   self.assertFalse(self.l.eligible(replace(self.q,**{x:False})),x)
 def test_write_ack_short_fails(self):self.assertFalse(self.l.publish(self.q,ack=self.q.write_bytes-64));self.assertIsNone(self.l.rotated[0])
 def test_write_ack_excess_fails(self):self.assertFalse(self.l.publish(self.q,ack=self.q.write_bytes+64))
 def test_mismatched_tag_fails(self):self.assertFalse(self.l.publish(self.q,tag=38))
 def test_failed_status_not_success(self):self.assertFalse(self.l.publish(self.q,status=1))
 def test_completion_not_fired_no_publication(self):self.assertFalse(self.l.publish(self.q,completion=False))
 def test_late_fault_no_publication(self):self.assertFalse(self.l.publish(self.q,fault=True));self.assertFalse(self.l.eligible(self.k))
 def test_fixed_resources_all_geometry(self):
  for profile in (2,4):
   for rows in (1,16,128):
    q=Command(profile=profile,rows=rows,count=rows);k=replace(q,role=1);l=Ledger();l.normalized(q);l.normalized(k)
    self.assertTrue(l.eligible(q));self.assertTrue(l.publish(q));self.assertTrue(l.eligible(k))
    for c in (q,k):self.assertEqual(c.write_bytes,c.rows*c.heads*8*64);self.assertLessEqual(c.rows*c.heads*32*6,393216)

if __name__=='__main__':unittest.main()
