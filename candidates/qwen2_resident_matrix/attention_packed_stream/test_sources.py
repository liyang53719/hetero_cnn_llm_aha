import tempfile,unittest
from pathlib import Path
from . import prepare as p
class Tests(unittest.TestCase):
 def test_zero_fuzz_and_default_projection(self):
  with tempfile.TemporaryDirectory() as d:
   base=p.baseline(Path(d)/'base');out=p.compose(Path(d)/'out')
   actual=(out/p.TARGET).read_text()
   actual=actual.replace(',enablePackedDrainStatus:Boolean=false','')
   actual=actual.replace('    val packedStepsDrained=if(enablePackedDrainStatus)Some(Output(Bool()))else None\n','')
   actual=actual.replace('  // Existing metadata owns retirement; no new debt counter or payload.\n','')
   actual=actual.replace('  if(enablePackedDrainStatus){io.packedStepsDrained.get:=work && !tags.io.deq.valid && !io.port.step.valid && !poison}\n','')
   self.assertEqual(actual,(base/p.TARGET).read_text())
   self.assertIn('val storage=Reg(Vec(2,new MatrixStreamResult(returnTagBits)))',actual)
 def test_no_client_payload_or_arithmetic_modules(self):
  s=(p.HERE/'PackedAttentionStreamClient.scala').read_text()
  self.assertNotIn('Module(new',s);self.assertNotIn('Reg(new MatrixStreamResult',s);self.assertNotIn('Reg(Vec',s)
  self.assertIn('io.result.bits:=io.port.result.bits',s)
  self.assertIn('enabled:Boolean=false',s)
  self.assertEqual(s.count('=Reg'),4)
 def test_real_seed_endpoint_closure(self):
  with tempfile.TemporaryDirectory() as d:
   out=p.compose(Path(d)/'out');endpoint=(out/(p.SCALA+'RetainedMatrix.scala')).read_text()
   self.assertIn('enableAccumulatorSeed:Boolean=false',endpoint)
   self.assertIn('seed',endpoint)
   for name in p.BASE:self.assertTrue((out/name).is_file())
 def test_exact_source_check(self):self.assertEqual(len(p.check()['generated']),11)
if __name__=='__main__':unittest.main()
