"""Commands-only executable contract model; NOT Chisel, RTL or DUT execution.
The original Guard/Prefix, not this model, owns full Host/txn64/physical P<C.
"""
from dataclasses import dataclass, replace
import unittest

SENTINEL=(1<<24)-1

def fld(v,h,l):return (v>>l)&((1<<(h-l+1))-1)

def records(rows):
 return 0x24|(23<<32)|(2<<56)|(rows<<100), 0x26|(SENTINEL<<32)|(2<<56)|(128<<64)|(1<<123)|(1<<124)

def records_ok(cp,cx,rows):
 return (fld(cp,7,0)==0x24 and fld(cp,31,8)==0 and fld(cp,55,32)!=SENTINEL and fld(cp,63,56)==2 and
         fld(cp,67,64)==0 and fld(cp,99,68)==0 and fld(cp,107,100)==rows and 1<=rows<=128 and
         fld(cp,127,108)==0 and fld(cx,7,0)==0x26 and fld(cx,31,8)==0 and fld(cx,55,32)==SENTINEL and
         fld(cx,63,56)==2 and fld(cx,72,64)==128 and fld(cx,81,73)==0 and fld(cx,90,82)==0 and
         fld(cx,122,91)==0 and fld(cx,123,123)==1 and fld(cx,124,124)==1 and fld(cx,127,125)==0)

@dataclass(frozen=True)
class Tensor:
 address:int;dims:tuple;dtype:int=5;rank:int=2;extra_padding:int=0
 @property
 def elements(self):
  v=1
  for d in self.dims:v*=d
  return v
 @property
 def payload(self):return self.elements*2
 @property
 def end(self):return self.address+self.payload+self.extra_padding

def overlaps(a,b):return a.address<b.end and b.address<a.end

def legal(t):return t.address>=0 and t.address%64==0 and t.end<=1<<56 and t.payload>0 and t.extra_padding==0

@dataclass(frozen=True)
class Command:
 profile:int=4;rows:int=128;opcode:int=0x41;engine:int=4
 cold:bool=True;generation:int=0;cache:bool=False;group:int=0
 input_live:bool=True;fresh:bool=True;readwrite:bool=True;distinct:bool=True
 @property
 def key(self):return Tensor(0x1000000,(self.rows,512,1,1))
 @property
 def value(self):return Tensor(0x1200000,(self.rows,512,1,1))
 @property
 def output(self):return Tensor(0x1400000,(2,128,512,1),rank=3)
 @property
 def write_bytes(self):return self.rows<<11

class Ledger:
 def __init__(self,c):
  self.rows=[c.rows]*3;self.bases=[0]*3;self.counts=[c.rows]*3
  self.projected=[True]*3;self.normalized=[True]*2;self.rotated=[True]*2
  self.positions=[0,0];self.key=c.key;self.value=c.value
  self.pending=None;self.pending_gqa=False
  self.published_cache=None;self.published_length=0;self.published_generation=0
  self.live_cache=False;self.produced_count=9;self.sources=[]
 def eligible(self,c,cp=None,cx=None,key=None,value=None,output=None):
  p,x=records(c.rows);p=p if cp is None else cp;x=x if cx is None else cx
  a=key or c.key;b=value or c.value;d=output or c.output
  return (c.profile in (2,4) and c.opcode==0x41 and c.engine==4 and c.group==0 and
   c.cold and c.generation==0 and not c.cache and records_ok(p,x,c.rows) and
   a==self.key and b==self.value and a.dims==(c.rows,512,1,1) and b.dims==(c.rows,512,1,1) and
   d.dims==(2,128,512,1) and d.rank==3 and a.rank==2 and b.rank==2 and
   all(t.dtype==5 and legal(t) for t in (a,b,d)) and
   all(self.projected) and all(self.normalized) and all(self.rotated) and self.positions==[0,0] and
   all(self.rows[i]==c.rows and self.bases[i]==0 and self.counts[i]==c.rows for i in range(3)) and
   self.pending is None and not self.pending_gqa and c.input_live and c.fresh and c.readwrite and c.distinct and
   not overlaps(a,b) and not overlaps(a,d) and not overlaps(b,d) and all(not overlaps(s,d) for s in self.sources))
 def complete(self,c,tag=73,expected_tag=73,status=0,ack=None,done_fire=True,completion_fire=True,fault=False):
  good=(done_fire and tag==expected_tag and status==0 and (c.write_bytes if ack is None else ack)==c.write_bytes and completion_fire and not fault)
  if good:self.pending=(c.output,c.rows,0,0,True)
  return good
 def fresh_after(self,t):return self.pending is None or not overlaps(t,self.pending[0])
 def launch(self):self.pending=None;self.pending_gqa=False;self.projected=[False]*3;self.normalized=[False]*2;self.rotated=[False]*2

class CommandsKvAppend(unittest.TestCase):
 def setUp(self):self.c=Command();self.l=Ledger(self.c)
 def test_both_profiles_same_cache_capacity(self):
  for p in (2,4):
   for m in (1,16,128):
    c=Command(profile=p,rows=m);l=Ledger(c)
    self.assertTrue(l.eligible(c));self.assertEqual(c.output.payload,262144);self.assertEqual(c.write_bytes,2*m*16*64)
 def test_real_chain_required(self):
  for name in ('projected','normalized','rotated'):
   for i in range(len(getattr(self.l,name))):
    l=Ledger(self.c);getattr(l,name)[i]=False;self.assertFalse(l.eligible(self.c),(name,i))
 def test_typed_identity_not_address_only(self):
  for kw in (dict(extra_padding=64),dict(dtype=7),dict(rank=3),dict(dims=(128,256,2,1)),dict(address=self.c.key.address+64)):
   self.assertFalse(self.l.eligible(self.c,key=replace(self.c.key,**kw)))
 def test_wrong_value_role_or_preloaded_lookalike(self):
  self.l.value=self.c.key;self.assertFalse(self.l.eligible(self.c))
 def test_untouched_cache_is_not_input_provenance(self):
  self.l.rotated=[False,False];self.l.projected=[False]*3;self.assertFalse(self.l.eligible(self.c))
 def test_scope_wrong_mode_profile_cold(self):
  for kw in (dict(profile=0),dict(profile=1),dict(profile=3),dict(rows=0),dict(rows=129),dict(opcode=0x23),dict(opcode=0x24),dict(engine=3),dict(group=1),dict(cold=False),dict(generation=1),dict(cache=True)):
   self.assertFalse(self.l.eligible(replace(self.c,**kw)),kw)
 def test_all_record_bits_rejected_except_pointer(self):
  for m in (1,16,128):
   p,x=records(m);self.assertTrue(records_ok(p,x,m))
   for i in range(128):
    if not 32<=i<=55:self.assertFalse(records_ok(p^(1<<i),x,m),('cp',m,i))
    self.assertFalse(records_ok(p,x^(1<<i),m),('cx',m,i))
 def test_bad_nonterminal_sentinel(self):
  p,x=records(128);p=(p&~(SENTINEL<<32))|(SENTINEL<<32);self.assertFalse(records_ok(p,x,128))
 def test_every_producer_same_window(self):
  for name in ('rows','bases','counts'):
   for i in range(3):
    l=Ledger(self.c);getattr(l,name)[i]+=1;self.assertFalse(l.eligible(self.c))
 def test_position_zero_both(self):
  for i in range(2):
   l=Ledger(self.c);l.positions[i]=1;self.assertFalse(l.eligible(self.c))
 def test_alias_any_plane_or_full_allocation(self):
  for d in (replace(self.c.output,address=self.c.key.address),replace(self.c.output,address=self.c.value.address),replace(self.c.output,address=self.c.key.address-(128<<10))):
   self.assertFalse(self.l.eligible(self.c,output=d))
 def test_unwritten_cache_rows_protect_from_sources(self):
  self.l.sources=[Tensor(self.c.output.address+180000,(1,32,1,1))]
  self.assertFalse(self.l.eligible(self.c))
 def test_complete_cache_descriptor_not_tail_alias(self):
  self.assertFalse(self.l.eligible(self.c,output=replace(self.c.output,dims=(2,16,512,1))))
 def test_aperture_no_wrap(self):
  self.assertFalse(self.l.eligible(self.c,output=replace(self.c.output,address=(1<<56)-64)))
  self.assertFalse(self.l.eligible(self.c,output=replace(self.c.output,address=(1<<64)-64)))
 def test_permissions_metadata_distinct(self):
  for name in ('input_live','fresh','readwrite','distinct'):
   self.assertFalse(self.l.eligible(replace(self.c,**{name:False})))
 def test_ack_short_excess_wrong_tag_status(self):
  for kw in (dict(ack=self.c.write_bytes-64),dict(ack=self.c.write_bytes+64),dict(tag=74),dict(status=1),dict(done_fire=False),dict(completion_fire=False),dict(fault=True)):
   l=Ledger(self.c);self.assertFalse(l.complete(self.c,**kw));self.assertIsNone(l.pending)
 def test_staging_not_publish(self):
  self.assertTrue(self.l.complete(self.c));self.assertIsNotNone(self.l.pending)
  self.assertIsNone(self.l.published_cache);self.assertEqual(self.l.published_length,0);self.assertEqual(self.l.published_generation,0)
  self.assertFalse(self.l.live_cache);self.assertEqual(self.l.produced_count,9)
 def test_replay_after_pending_rejected(self):self.l.complete(self.c);self.assertFalse(self.l.eligible(self.c))
 def test_late_fault_vetoes_pending(self):self.assertFalse(self.l.complete(self.c,fault=True));self.assertIsNone(self.l.pending)
 def test_pending_full_capacity_protected(self):
  c=replace(self.c,rows=16);l=Ledger(c);l.complete(c)
  self.assertFalse(l.fresh_after(Tensor(c.output.address+180000,(1,32,1,1))))
  self.assertTrue(l.fresh_after(Tensor(c.output.end,(1,32,1,1))))
 def test_next_launch_invalidates_old_producers_not_global(self):
  self.l.complete(self.c);self.l.launch();self.assertIsNone(self.l.pending);self.assertFalse(self.l.eligible(self.c));self.assertIsNone(self.l.published_cache)

if __name__=='__main__':unittest.main()
