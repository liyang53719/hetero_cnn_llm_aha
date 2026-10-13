"""Explicit existing-Scalar exp routing and real reduced owner transactions."""
import os,json,tempfile,time,unittest
from pathlib import Path
from dataclasses import replace
import numpy as np
from . import model as m,exp_policy as ep
from .cumsum import GUARDED_CUMSUM
from .vector import Vector16,IEEE_POLICY,build_library
from .test_model import produced
from ..prep.scalar import PrepScalar
from ...qwen35_35b_exp.gate_scalar import GateScalar
from ...qwen35_35b_exp.scalar import OPERATION

class ChunkExpTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.library=Path(os.environ['GDN_VECTOR16_LIBRARY']) if os.environ.get('GDN_VECTOR16_LIBRARY') else build_library(cls.tmp.name)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def resources(self):
  s=GateScalar(enable_softplus=True,enable_ieee_exp=True,enable_gate_softplus=True)
  v=Vector16(self.library,exception_policy=IEEE_POLICY)
  return s,v
 def owner(self,s=None,v=None):
  if s is None:s,v=self.resources()
  return m.ChunkOwner(s,v,heads=32,key_dim=16,value_dim=32,host_batch=True,layout=m.GROUPED_35B,
      cumsum_policy=GUARDED_CUMSUM,exp_policy=ep.IEEE_EXP)
 def test_actual_exp_method_keeps_subnormal_and_original_default(self):
  o=self.owner();self.assertTrue(o.scalar.acquire(o))
  for x,y in [(0xc2aeac50,0x007fffe6),(0xc2b72752,0x0001d7fd),(0xc2cff1b4,1),(0xc2cff1b5,0),(0xff7fffff,0)]:
   self.assertEqual(o._exp(x),y)
  self.assertEqual(o.exp_stats['saturated_abs_ge_80'],0)
  self.assertEqual(o.exp_stats['subnormal_outputs'],3)
  self.assertEqual(o.scalar.calls[OPERATION],5);self.assertEqual(o.scalar.calls['exp_negative'],0)
  o.scalar.release(o)
  legacy=m.ChunkOwner(PrepScalar(),Vector16(self.library));legacy.scalar.acquire(legacy)
  self.assertEqual(legacy._exp(0xc2b72752),0);self.assertEqual(legacy.exp_stats['saturated_abs_ge_80'],1)
  legacy.scalar.release(legacy)
 def test_policy_layout_enabled_scalar_and_vector_are_explicit(self):
  s,v=self.resources()
  with self.assertRaises(ValueError):m.ChunkOwner(s,v,exp_policy=ep.IEEE_EXP)
  with self.assertRaises(ValueError):self.owner(PrepScalar(),v)
  with self.assertRaises(ValueError):self.owner(s,Vector16(self.library))
  s.enable_ieee_exp=False
  with self.assertRaises(ValueError):self.owner(s,v)
 def driver(self):
  s,v=self.resources();prior=object();self.assertTrue(s.acquire(prior));s.op(prior,OPERATION,0xc2b72752);s.release(prior)
  owner=self.owner(s,v);mem=m.TypedMemory()
  job=m.ChunkJob(353,0x100000,0x800000,0x900000,0xa00000,0x1000000,1,heads=32,key_dim=16,value_dim=32,
      layout=m.GROUPED_35B,cumsum_policy=GUARDED_CUMSUM,exp_policy=ep.IEEE_EXP)
  data=np.zeros((1,12800),'<u4');data[:,12289::16]=0x3f000000;data[0,12288]=0xc2b72752
  produced(mem,job.input,data.tobytes())
  for base,size in ((job.output,job.output_bytes),(job.state_out,job.state_bytes),(job.scratch,job.scratch_bytes)):mem.allocate_output(base,size)
  return m.TypedChunkDriver(owner,mem,job)
 def finish(self,d,hook=None):
  deadline=time.monotonic()+100
  while d.response is None:
   self.assertLess(time.monotonic(),deadline);d.tick(**({} if hook is None else hook(d)))
 def test_real32head_small_owner_uses_same_scalar_and_reports_delta(self):
  d=self.driver();sid=id(d.owner.scalar);vid=id(d.owner.vector);self.finish(d)
  self.assertIsNone(d.response.status);r=d.report();self.assertEqual(id(d.owner.scalar),sid);self.assertEqual(id(d.owner.vector),vid)
  self.assertEqual(r['owner']['scalar_calls'],{OPERATION:70688})
  self.assertEqual(r['owner']['exp']['subnormal_outputs'],65)
  self.assertEqual(r['owner']['exp']['saturated_abs_ge_80'],0)
  self.assertTrue(r['owner']['decay_internal_calls'])
  self.assertEqual(d.output.raw(),bytes(d.job.output_bytes));self.assertEqual(d.state_out.raw(),bytes(d.job.state_bytes))
  self.assertFalse(d.output.published or d.state_out.published or d.scratch.published)
  print('IEEE_CHUNK_EXP_OWNER '+json.dumps(r,sort_keys=True))
  old=dict(d.owner.decay_counts);d.owner.reset();self.assertEqual(d.owner.exp_policy,ep.IEEE_EXP)
  self.assertFalse(d.owner.decay_counts);self.assertTrue(old)
 def test_policy_drift_and_read_fault_never_publish(self):
  d=self.driver();d.owner.scalar.enable_ieee_exp=False
  with self.assertRaises(ValueError):d.tick()
  d=self.driver();self.finish(d,lambda x:{'read_error':True} if x.pending_request is not None and not x.pending_request.write else {})
  self.assertIsNotNone(d.response.status);self.assertIsNone(d.owner.scalar.client);self.assertIsNone(d.owner.vector.client)
  self.assertFalse(d.output.published or d.state_out.published)
  with self.assertRaises(ValueError):replace(d.job,exp_policy=ep.LEGACY_EXP).validate(d.owner.geometry,m.GROUPED_35B,GUARDED_CUMSUM,ep.IEEE_EXP)

if __name__=='__main__':unittest.main()
