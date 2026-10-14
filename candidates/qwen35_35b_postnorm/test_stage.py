"""Real residual/ACK to strict RMS admission; full O handled by actual chain."""
from dataclasses import replace
import struct,unittest
from . import stage as s
from . import test_residual as fixture_module
from ..qwen35_35b_rms import formula

class StageTests(unittest.TestCase):
 def setup(self,accept=True):
  fixture=fixture_module.ResidualTests();d,_,_=fixture.setup_driver()
  for _ in range(30000):
   d.tick(response_ready=accept)
   if d.response is not None or not accept and d.owner.state=='finish':break
  self.d=d;self.scalar=d.owner.scalar;self.memory=d.memory
  self.owner=s.rms.RmsOwner(self.scalar)
  self.memory.add_readonly(0x400000,bytes(4096));self.memory.allocate_output(0x500000,4096)
 def prepare(self):return s.prepare_postnorm(self.d,self.owner,self.memory,self.scalar,0x400000,0x500000)
 def test_real_residual_to_same_scalar_rms(self):
  self.setup();r=self.prepare();banks=tuple(map(id,(self.owner.row_bank,self.owner.weight_bank,self.owner.output_bank)))
  for _ in range(10000):
   r.tick()
   if r.response is not None:break
  self.assertIsNone(r.response.status);self.assertIs(r.input,self.d.output)
  self.assertEqual(r.output.raw(),formula.formula(self.d.output.raw(),bytes(4096),1)['output'])
  self.assertEqual(banks,tuple(map(id,(self.owner.row_bank,self.owner.weight_bank,self.owner.output_bank))))
 def test_held_terminal_and_source_tamper_rejected(self):
  self.setup(False)
  with self.assertRaises(ValueError):self.prepare()
  self.setup();self.d.a.storage[64]^=1
  with self.assertRaisesRegex(ValueError,'source identities'):self.prepare()
 def test_actual_residual_data_or_scalar_substitution_rejected(self):
  self.setup();self.d.output.storage[64]^=1
  with self.assertRaisesRegex(ValueError,'actual residual'):self.prepare()
  self.setup();other=s.e.ConvScalar()
  with self.assertRaises(ValueError):s.prepare_postnorm(self.d,self.owner,self.memory,other,0x400000,0x500000)
 def test_postnorm_last_ack_failure_does_not_publish(self):
  self.setup();r=self.prepare()
  for _ in range(10000):
   last=r.pending is not None and self.owner.request.write and r.counts['write_bytes']==4096
   r.tick(ack_error=bool(last))
   if r.response is not None:break
  self.assertEqual(r.response.status,'Memory');self.assertFalse(r.output.published)
  self.assertTrue(self.d.output.published)
if __name__=='__main__':unittest.main()
