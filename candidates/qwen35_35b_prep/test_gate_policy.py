"""Explicit35B output-domain extension, preserving the default source domain."""
import struct,unittest,time
from candidates.qwen35_gdn_prefill.prep import model as m
from candidates.qwen35_gdn_prefill.prep.test_model import bf,produced
from candidates.qwen35_gdn_prefill.prep.scalar import PrepScalar
class GatePolicyTests(unittest.TestCase):
 def driver(self,a,policy):
  mem=m.TypedMemory();produced(mem,0x100000,bf([.125]*8192));produced(mem,0x200000,bf([a]+[0.]*63))
  mem.add_readonly(0x300000,bytes(128));mem.add_readonly(0x400000,bytes(64));mem.allocate_output(0x500000,51200)
  owner=m.InputPrepOwner(PrepScalar(enable_softplus=True),heads=32,layout=m.GROUPED_35B,gate_policy=policy)
  job=m.InputPrepJob(900,0x100000,0x200000,0x300000,0x400000,0x500000,1,32,m.GROUPED_35B,policy)
  return m.TypedInputPrepDriver(owner,mem,job)
 def finish(self,d):
  deadline=time.monotonic()+20
  while d.response is None:
   self.assertLess(time.monotonic(),deadline);d.tick()
 def test_default_boundary_stays_closed(self):
  for a in (80.,80.5,92.):
   d=self.driver(a,m.LEGACY_GATE);self.finish(d)
   self.assertIsNotNone(d.response.status);self.assertFalse(d.output.published)
 def test_new_policy_preserves_unclipped_raw_g(self):
  for a in (79.5,80.,80.5,92.):
   d=self.driver(a,m.FINITE_GATE_35B);self.finish(d)
   self.assertIsNone(d.response.status);self.assertTrue(d.output.published)
   self.assertEqual(d.output.raw()[12288*4:12288*4+4],struct.pack('<f',-a))
   self.assertFalse(d.response.state_committed);self.assertFalse(d.response.history_committed)
 def test_policy_must_be_explicit_and_35b_only(self):
  with self.assertRaises(ValueError):m.InputPrepOwner(PrepScalar(),gate_policy=m.FINITE_GATE_35B)
  d=self.driver(0.,m.LEGACY_GATE)
  from dataclasses import replace
  with self.assertRaises(ValueError):replace(d.job,gate_policy=m.FINITE_GATE_35B).validate(32,m.GROUPED_35B,m.LEGACY_GATE)
 def test_new_policy_nonfinite_input_still_fails(self):
  d=self.driver(float('inf'),m.FINITE_GATE_35B);self.finish(d)
  self.assertIsNotNone(d.response.status);self.assertFalse(d.output.published)
if __name__=='__main__':unittest.main()
