"""Explicit H2048 Add profile, actual beat transport, independent integer oracle."""
from dataclasses import replace
import struct, unittest
from ..qwen35_gdn_prefill.elementwise import model as e
from ..qwen35_gdn_prefill.elementwise.test_model import produced, oracle
from ..qwen35_gdn_prefill.conv.scalar import ConvScalar

class ResidualTests(unittest.TestCase):
 def setup_driver(self, tokens=1):
  scalar=ConvScalar();owner=e.ElementwiseOwner(scalar,hidden_width=2048,profile=e.RESIDUAL_35B_PROFILE)
  memory=e.TypedMemory()
  # tie-even, cancellation, signed zero, tiny exact normal/subnormal additions.
  av=[0x3f80,0x3f81,0xbf80,0x8000,0x0001,0x0080,0x7f00,0]
  bv=[0x3b80,0x3b80,0x3f80,0,0x0001,0x0001,0xff00,0x8000]
  a=struct.pack('<8H',*av)*(2048*tokens//8);b=struct.pack('<8H',*bv)*(2048*tokens//8)
  memory.add_readonly(0x100000,a);produced(memory,0x200000,b)
  memory.allocate_output(0x300000,len(a))
  job=e.ElementwiseJob(93,0x100000,0x200000,0x300000,tokens,row_width=2048,profile=e.RESIDUAL_35B_PROFILE)
  return e.TypedElementwiseDriver(owner,memory,job),a,b
 def finish(self,d,**opts):
  for _ in range(100000):
   d.tick(**opts)
   if d.response is not None:return
  self.fail('bounded transport')
 def test_h2048_actual_add_and_no_tensor_buffer(self):
  d,a,b=self.setup_driver(2);self.finish(d)
  self.assertIsNone(d.response.status);self.assertEqual(d.output.raw(),oracle(a,b,e.ElementwiseOp.Add))
  r=d.report();self.assertTrue(d.output.published);self.assertEqual(d.counts['ack_bytes'],8192)
  self.assertEqual(d.owner.scalar_counts['add'],4096)
  self.assertEqual(d.owner.identity['profile'],e.RESIDUAL_35B_PROFILE)
  self.assertFalse(d.owner.report()['production_chisel_binding'])
  self.assertEqual(d.owner.report()['retained_a_elements'],32)
 def test_explicit_profile_only_add_legacy_unchanged(self):
  with self.assertRaises(ValueError):e.ElementwiseOwner(ConvScalar(),hidden_width=2048)
  d,_,_=self.setup_driver();j=d.job
  with self.assertRaises(ValueError):replace(j,profile=e.LEGACY_PROFILE).validate(hidden_width=2048,profile=e.RESIDUAL_35B_PROFILE)
  with self.assertRaises(ValueError):replace(j,op=e.ElementwiseOp.SiluMul).validate(hidden_width=2048,profile=e.RESIDUAL_35B_PROFILE)
  with self.assertRaises(ValueError):e.ElementwiseOwner(ConvScalar(),hidden_width=2048,profile=e.RESIDUAL_35B_PROFILE,enable_attention_sigmoid_mul=True)
 def test_held_success_abort_and_reset_preserve_profile(self):
  d,_,_=self.setup_driver()
  for _ in range(20000):
   d.tick(response_ready=False)
   if d.owner.ports()['response'] is not None:break
  self.assertFalse(d.output.published);self.assertIsNone(d.owner.ports()['response'].status)
  d.tick(abort=True);self.finish(d)
  self.assertEqual(d.response.status,'Aborted');self.assertFalse(d.output.published)
  d.owner.reset();self.assertEqual(d.owner.profile,e.RESIDUAL_35B_PROFILE);self.assertEqual(d.owner.hidden_width,2048)
 def test_last_ack_error_and_profile_tamper_fail_closed(self):
  d,_,_=self.setup_driver()
  for _ in range(20000):
   opts={'ack_error':True} if d.pending_write is not None and d.counts['write_bytes']==4096 else {}
   d.tick(**opts)
   if d.response is not None:break
  self.assertEqual(d.response.status,'Memory');self.assertFalse(d.output.published)
  d,_,_=self.setup_driver();d.owner.profile=e.LEGACY_PROFILE
  with self.assertRaisesRegex(ValueError,'parameters changed'):d.tick()
  self.assertFalse(d.output.published)
if __name__=='__main__':unittest.main()
