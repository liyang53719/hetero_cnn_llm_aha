"""35B32-head BF16 stride and real transport; fixed-recipe synthetic only."""
from dataclasses import replace
import struct,time,unittest
from . import model as m
from .test_model import bf,oracle_head,produced
from ..conv.scalar import ConvScalar
from ..rms_owner import word

class GroupedNormTests(unittest.TestCase):
 def driver(self,tokens=2):
  memory=m.TypedMemory();scalar=ConvScalar();owner=m.GatedNormOwner(scalar,heads=32,layout=m.GROUPED_35B)
  core=bf([((i*19+t*31)%97-48)/32 for t in range(tokens) for i in range(4096)])
  gate=bf([((i*7+t*23)%67-33)/16 for t in range(tokens) for i in range(4096)])
  weights=struct.pack('<128I',*(word(1+(i-64)/257) for i in range(128)))
  produced(memory,0x100000,core);produced(memory,0x200000,gate);memory.add_readonly(0x300000,weights)
  memory.allocate_output(0x400000,tokens*8192)
  job=m.GatedNormJob(35401,0x100000,0x200000,0x300000,0x400000,tokens,32,m.GROUPED_35B)
  return m.TypedGatedNormDriver(owner,memory,job)
 def finish(self,d,hook=None):
  deadline=time.monotonic()+30
  for i in range(100000):
   self.assertLess(time.monotonic(),deadline);d.tick(**({} if hook is None else hook(d,i)))
   if d.response is not None:return
  self.fail('watchdog')
 def test_full32_two_tokens_original_recipe_and_real_bytes(self):
  d=self.driver();core,gate,weight=[x.raw() for x in d.sources]
  expected=b''.join(oracle_head(core[i:i+256],gate[i:i+256],weight) for i in range(0,len(core),256))
  self.finish(d);self.assertIsNone(d.response.status);self.assertTrue(d.output.published)
  self.assertEqual(d.output.raw(),expected);self.assertNotEqual(expected[15*256:16*256],expected[16*256:17*256])
  r=d.report();self.assertEqual(r['owner']['row_bytes'],8192);self.assertEqual(r['owner']['test_only_zero_filled_heads'],0)
  self.assertEqual(d.owner.counts['read_requests']*64,512+2*2*8192)
  self.assertEqual(d.owner.counts['write_acks']*64,2*8192)
  self.assertEqual(d.owner.layout,m.GROUPED_35B);d.owner.reset();self.assertEqual(d.owner.layout,m.GROUPED_35B)
 def test_explicit_job_owner_profile_and_all_heads(self):
  d=self.driver()
  with self.assertRaises(ValueError):replace(d.job,layout=m.EQUAL_HEADS).validate(32,m.GROUPED_35B)
  with self.assertRaises(ValueError):m.GatedNormOwner(ConvScalar(),heads=16,layout=m.GROUPED_35B)
  with self.assertRaises(ValueError):m.GatedNormOwner(ConvScalar(),heads=32)
  d.owner.layout=m.EQUAL_HEADS
  with self.assertRaises(ValueError):d.tick()
 def test_last_ack_error_and_held_success_abort_do_not_publish(self):
  for kind in ('last_ack','held_abort'):
   d=self.driver(tokens=1)
   def hook(x,i):
    if kind=='last_ack':return dict(ack_error=x.pending_request is not None and x.pending_request.write and x.pending_request.address==x.job.output+x.job.write_bytes-64)
    return dict(response_ready=False) if x.owner.state!='finish' else dict(abort=True)
   self.finish(d,hook);self.assertIsNotNone(d.response.status);self.assertFalse(d.output.published)
   self.assertIsNone(d.memory.pending);self.assertIsNone(d.owner.scalar.client)
if __name__=='__main__':unittest.main()
