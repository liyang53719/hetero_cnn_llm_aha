"""Fullshape transport failure boundaries; numerical chunk acceptance absent."""
import os,tempfile,time,unittest
from pathlib import Path
from . import chunk_stage as s
from .chunk_budget import closed_counts
from ..qwen35_gdn_prefill.chunk.test_model import produced
from ..qwen35_gdn_prefill.chunk.vector import Vector16,IEEE_POLICY,build_library
from ..qwen35_35b_exp.gate_scalar import GateScalar

class ChunkStageTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.lib=Path(os.environ['GDN_VECTOR16_LIBRARY']) if os.environ.get('GDN_VECTOR16_LIBRARY') else build_library(cls.tmp.name)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def resources(self):
  memory=s.c.TypedMemory();produced(memory,0x100000,bytes(16*51200));producer=memory.exact(0x100000,16*51200,readable=True)
  cursor=0x1000000
  def allocate(*,size):
   nonlocal cursor
   address=cursor;cursor+=size+64;memory.allocate_output(address,size);return address
  scalar=GateScalar(enable_softplus=True,enable_ieee_exp=True,enable_gate_softplus=True)
  vector=Vector16(self.lib,exception_policy=IEEE_POLICY)
  return memory,scalar,vector,producer,allocate
 def test_fullshape_predictions(self):
  for m,r,w,t in [(16,11552256,471040,24046593),(128,23173120,888832,48123905)]:
   c=closed_counts(m,128,128);self.assertEqual((c['read_requests'],c['write_requests'],c['driver_ticks_no_stall']),(r,w,t))
   self.assertEqual(c['state_bytes'],2097152)
 def test_row4_fullshape_prediction_and_unknown_policy(self):
  for tokens in (16,128):
   old=closed_counts(tokens,128,128);new=closed_counts(tokens,128,128,matmul_policy=s.c.ROW4_MATMUL)
   saved=452984832*((tokens+63)//64)
   self.assertEqual(old["read_bytes"]-new["read_bytes"],saved)
   self.assertEqual(old["driver_ticks_no_stall"]-new["driver_ticks_no_stall"],2*saved//64)
   for key in ("write_bytes","source_read_bytes","vector_add_issues","vector_mul_issues","scratch_ddr_bytes"):
    self.assertEqual(old[key],new[key],key)
  with self.assertRaises(ValueError):closed_counts(128,128,128,matmul_policy="unknown")
 def test_actual_first_ack_error_drains_and_stages(self):
  args=self.resources();d,r=s.execute_chunk(*args,tokens=16,deadline=time.monotonic()+20,
    controls=lambda stage,tick,d:{'ack_error':True})
  self.assertIsNotNone(d.response.status);self.assertIsNone(args[0].pending)
  self.assertIsNone(args[1].client);self.assertIsNone(args[2].client)
  self.assertFalse(d.output.published or d.state_out.published or d.scratch.published)
  self.assertEqual(d.counts['write_bytes'],64)
 def test_interruption_retains_physical_pending_write(self):
  args=self.resources();cancelled=[]
  def hook(stage,tick,d):
   if d.memory.pending is not None:raise TimeoutError('test wall boundary')
   return {}
  with self.assertRaises(s.ChunkInterrupted) as result:
   s.execute_chunk(*args,tokens=16,deadline=time.monotonic()+20,controls=hook,on_interrupt=lambda:cancelled.append(True))
  self.assertEqual(cancelled,[True])
  e=result.exception;self.assertTrue(e.snapshot['physical_write_pending'])
  self.assertFalse(e.snapshot['automatically_drained']);self.assertFalse(e.snapshot['resumable_checkpoint'])
  self.assertEqual(e.snapshot['span_coverage']['scratch']['written_beats'],1)
  self.assertEqual(e.snapshot['span_coverage']['scratch']['acknowledged_beats'],0)
  self.assertIsNotNone(args[0].pending);self.assertIsNotNone(args[1].client)
  self.assertEqual(len(e.raw['state_out']),2097152)
 def test_interruption_retains_pending_read_identity(self):
  args=self.resources()
  def hook(stage,tick,d):
   if d.pending_request is not None and not d.pending_request.write:raise TimeoutError('test read boundary')
   return {}
  with self.assertRaises(s.ChunkInterrupted) as result:
   s.execute_chunk(*args,tokens=16,deadline=time.monotonic()+20,controls=hook)
  e=result.exception;self.assertTrue(e.snapshot['pending_response'])
  self.assertFalse(e.snapshot['physical_write_pending']);self.assertEqual(e.snapshot['accepted_request']['data_bytes'],0)
  self.assertEqual(e.snapshot['accepted_request']['address'],args[3].base+12288*4)
  self.assertFalse(e.snapshot['accepted_request']['write']);self.assertIsNotNone(args[1].client)
 def test_abort_pending_write_drains_without_publication(self):
  args=self.resources()
  d,r=s.execute_chunk(*args,tokens=16,deadline=time.monotonic()+20,
    controls=lambda stage,tick,d:{'abort':d.memory.pending is not None})
  self.assertIsNotNone(d.response.status);self.assertIsNone(args[0].pending)
  self.assertIsNone(args[1].client);self.assertIsNone(args[2].client)
  self.assertFalse(d.output.published or d.state_out.published or d.scratch.published)
 def test_readonly_or_unacknowledged_input_rejected(self):
  args=list(self.resources());args[3].published=False
  with self.assertRaises(ValueError):s.execute_chunk(*args,tokens=16,deadline=time.monotonic()+20)

if __name__=='__main__':unittest.main()
