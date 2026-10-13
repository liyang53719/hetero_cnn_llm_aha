"""One-memory owner admission, counters and abort/reset for explicit dual exp."""
import unittest,struct,time
from dataclasses import replace
from ..qwen35_gdn_prefill.prep import model as m
from ..qwen35_gdn_prefill.prep.test_model import produced,bf
from ..qwen35_35b_exp.gate_scalar import GateScalar,SOFTPLUS_OPERATION
from ..qwen35_35b_exp.scalar import OPERATION

class DualGateTests(unittest.TestCase):
 def driver(self,owner=None,first=0.):
  mem=m.TypedMemory();produced(mem,0x100000,bf([.125]*8192));produced(mem,0x200000,bf([first]+[0.]*63))
  mem.add_readonly(0x300000,bytes(128));mem.add_readonly(0x400000,bytes(64));mem.allocate_output(0x500000,51200)
  if owner is None:owner=m.InputPrepOwner(GateScalar(enable_softplus=True,enable_ieee_exp=True,enable_gate_softplus=True),heads=32,layout=m.GROUPED_35B,gate_policy=m.DUAL_EXP_GATE_35B,reduction_policy=m.CPU_DEFAULT_35B)
  job=m.InputPrepJob(908,0x100000,0x200000,0x300000,0x400000,0x500000,1,32,m.GROUPED_35B,m.DUAL_EXP_GATE_35B,m.CPU_DEFAULT_35B)
  return m.TypedInputPrepDriver(owner,mem,job)
 def finish(self,d,hook=None):
  end=time.monotonic()+15
  while d.response is None:
   self.assertLess(time.monotonic(),end);d.tick(**({} if hook is None else hook(d)))
 def test_actual_compound_counts_and_no_extra_memory(self):
  d=self.driver();self.finish(d);self.assertIsNone(d.response.status);r=d.report()
  self.assertEqual(r['counts']['read_bytes'],25088);self.assertEqual(r['counts']['write_bytes'],51200)
  calls=r['owner']['scalar_calls'];self.assertEqual(calls[OPERATION],32);self.assertEqual(calls[SOFTPLUS_OPERATION],32);self.assertEqual(calls['exp_negative'],32)
  self.assertNotIn('softplus',calls);self.assertEqual(r['owner']['gate_inner_exp_calls'],32)
  self.assertEqual(r['owner']['decay_internal_calls']['integer_rne'],64)
  self.assertTrue(d.output.published);self.assertIsNone(d.owner.scalar.client)
 def test_explicit_only_and_wrong_job_policy(self):
  with self.assertRaises(ValueError):m.InputPrepOwner(GateScalar(),heads=32,layout=m.GROUPED_35B,gate_policy=m.DUAL_EXP_GATE_35B)
  with self.assertRaises(ValueError):m.InputPrepOwner(GateScalar(enable_softplus=True,enable_ieee_exp=True,enable_gate_softplus=True),gate_policy=m.DUAL_EXP_GATE_35B)
  d=self.driver()
  with self.assertRaises(ValueError):replace(d.job,gate_policy=m.FINITE_GATE_35B).validate(32,m.GROUPED_35B,m.DUAL_EXP_GATE_35B,m.CPU_DEFAULT_35B)
 def test_domain_fault_then_same_owner_reset_has_fresh_counters(self):
  d=self.driver(first=-80.);self.finish(d);self.assertEqual(d.response.status,'Numerical');self.assertFalse(d.output.published)
  d.owner.reset();again=self.driver(owner=d.owner);self.finish(again)
  self.assertIsNone(again.response.status);self.assertEqual(again.report()['owner']['gate_inner_exp_calls'],32)
 def test_held_success_abort_no_publish_then_reset_reuse(self):
  d=self.driver()
  while d.owner.state!='finish':d.tick(response_ready=False)
  self.assertFalse(d.output.published);d.tick(abort=True,response_ready=False)
  self.finish(d);self.assertIsNotNone(d.response.status);self.assertFalse(d.output.published)
  d.owner.reset();again=self.driver(owner=d.owner);self.finish(again);self.assertIsNone(again.response.status)
if __name__=='__main__':unittest.main()
