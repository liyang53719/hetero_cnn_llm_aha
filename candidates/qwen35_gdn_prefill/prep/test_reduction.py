"""Fixed-resource serialized FP32 order, owner identity and lifecycle tests."""
import unittest,random
from collections import Counter
from dataclasses import replace
from . import model as m
from .reduction import sum_squares128
from .test_model import ref_add,ref_mul
from . import test_grouped_layout as grouped
from .scalar import PrepScalar
from ..rms_owner import word

class ReductionTests(unittest.TestCase):
 def test_independent_four_by_eight_tree_counts_cache_immutable(self):
  rng=random.Random(350128)
  for _ in range(12):
   cache=[word(rng.uniform(-3,3))&0xffff0000 for i in range(128)];before=cache.copy();count=Counter()
   def op(n,a,b):
    count[n]+=1
    return ref_mul(a,b) if n=='mul_ieee_rne' else ref_add(a,b)
   partial=[[0]*8 for _ in range(4)]
   for t in range(4):
    for g in range(4):
     for lane in range(8):
      x=cache[t*32+g*8+lane];partial[g][lane]=ref_add(partial[g][lane],ref_mul(x,x))
   total=0
   for lane in range(8):
    v=partial[0][lane]
    for g in range(1,4):v=ref_add(v,partial[g][lane])
    total=ref_add(total,v)
   self.assertEqual(sum_squares128(cache,op),total);self.assertEqual(cache,before)
   self.assertEqual(count,{'mul_ieee_rne':128,'add':127})
 def driver(self,owner=None,first=None):
  from .test_model import bf,produced
  import struct
  mem=m.TypedMemory()
  vectors=[]
  for role,count in ((0,16),(1,16),(2,32)):
   for h in range(count):vectors += [.125*(h+1),(-.25 if h%2 else .25)]+[0.]*126
  if first is not None:vectors[0]=first
  produced(mem,0x100000,bf(vectors));produced(mem,0x400000,bf([h/64-.2 for h in range(32)]+[h/32-.4 for h in range(32)]))
  mem.add_readonly(0x410000,struct.pack('<32f',*[h/64-.25 for h in range(32)]));mem.add_readonly(0x420000,bf([h/128-.1 for h in range(32)]));mem.allocate_output(0x800000,51200)
  if owner is None:owner=m.InputPrepOwner(PrepScalar(enable_softplus=True),heads=32,layout=m.GROUPED_35B,reduction_policy=m.CPU_DEFAULT_35B)
  job=m.InputPrepJob(3581,0x100000,0x400000,0x410000,0x420000,0x800000,1,32,m.GROUPED_35B,m.LEGACY_GATE,m.CPU_DEFAULT_35B)
  return m.TypedInputPrepDriver(owner,mem,job)
 def finish(self,d,hook=None):return grouped.GroupedLayoutTests().finish(d,hook)
 def test_real_owner_no_extra_reads_and_counts(self):
  old=grouped.GroupedLayoutTests().setup_driver(1);new=self.driver()
  self.finish(old);self.finish(new)
  self.assertIsNone(new.response.status)
  self.assertEqual(old.report()['counts'],new.report()['counts'])
  a,b=old.owner.report()['scalar_calls'],new.owner.report()['scalar_calls']
  self.assertEqual(a['add']-b['add'],64)
  self.assertEqual(a['mul_ieee_rne'],b['mul_ieee_rne'])
  self.assertEqual(old.output.raw(),new.output.raw())
  self.assertEqual(new.owner.report()['retained_fp32_head_capacity'],128)
 def test_policy_mismatch_and_reset_preserve_explicit_identity(self):
  with self.assertRaises(ValueError):m.InputPrepOwner(PrepScalar(),reduction_policy=m.CPU_DEFAULT_35B)
  d=self.driver()
  with self.assertRaises(ValueError):replace(d.job,reduction_policy=m.ASCENDING).validate(32,m.GROUPED_35B,m.LEGACY_GATE,m.CPU_DEFAULT_35B)
  self.finish(d);d.owner.reset();self.assertEqual(d.owner.reduction_policy,m.CPU_DEFAULT_35B)
  self.assertIsNone(d.owner.scalar.client)
 def test_read_fault_and_abort_do_not_publish_or_pollute_next_owner(self):
  for abort in (False,True):
   d=self.driver();sent=False
   def hook(x,i):
    nonlocal sent
    if not sent and x.owner.state=='wait':
     sent=True;return {'abort':True} if abort else {'read_error':True}
    return {}
   self.finish(d,hook)
   self.assertIsNotNone(d.response.status);self.assertFalse(d.output.published)
   self.assertIsNone(d.owner.scalar.client);d.owner.reset()
   fresh=self.driver(owner=d.owner);self.finish(fresh)
   self.assertIsNone(fresh.response.status)
 def test_new_policy_arithmetic_fault_closes_owner(self):
  for first in (float('inf'),3e38):
   d=self.driver(first=first);self.finish(d)
   self.assertEqual(d.response.status,'Numerical');self.assertFalse(d.output.published)
   self.assertIsNone(d.owner.scalar.client)
if __name__=='__main__':unittest.main()
