"""Only parse/hash/check synthetic text; never Java, emitter or interpreter."""
import ast,json,tempfile,unittest,hashlib
from pathlib import Path
import run_protocol as r
HERE=Path(__file__).resolve().parent
class Cold(unittest.TestCase):
 def test_all_python_parses(self):
  for p in HERE.glob('*.py'):ast.parse(p.read_text(),filename=str(p))
 def test_fixture_inventory_external_pin(self):
  p=json.loads((HERE/'FIXTURE_PINS.json').read_text());actual={str(f.relative_to(HERE/'fixtures')):hashlib.sha256(f.read_bytes()).hexdigest() for f in (HERE/'fixtures').rglob('*') if f.is_file()}
  self.assertEqual(actual,p if any(n.endswith('.bin') for n in actual) else {n:h for n,h in p.items() if not n.endswith('.bin')})
  self.assertEqual(sum(n.endswith('.bin') for n in p),6)
  self.assertIn('gate.json',p)
  for n in ('m16','m128','m16_relocated'):
   self.assertIn(n+'/manifest.json',p)
 def test_dependency_explicit_replacement(self):
  d=json.loads((HERE/'dependency-lock.json').read_text())
  self.assertEqual((len(d['jars']),len(d['removed']),len(d['added'])),(106,6,25))
  self.assertFalse(set(d['jars'])&set(d['removed']))
  for n,h in d['added'].items():self.assertEqual(d['jars'][n],h['sha256'])
 def test_structure_rejects_storage_and_backend(self):
  names=['ProductionQkvProtocolHarness','HostBlockCommands','Public21QkvReductionRouter','DenseBlockReductionCoordinator','DenseTileSumBridge','Record128Reader','TypedTensorReader']
  good='\n'.join('  module '+n+' :\n    input clock : Clock' for n in names)
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'fake.fir';p.write_text(good);self.assertEqual(r.structure(p)['memory_declarations'],0)
   for bad in [good+'\n    cmem data : UInt<32>[4]',good+'\n  extmodule Foreign :',good.replace('TypedTensorReader','DenseDownOwner'),good+' '*2097152]:
    p.write_text(bad)
    with self.assertRaises(ValueError):r.structure(p)
 def test_no_execution_default(self):
  class Args:execute=False
  with self.assertRaises(ValueError):r.run(Args())
 def test_source_scope_and_markers(self):
  s=(HERE/'source/ProductionQkvProtocolSpec.scala').read_text()
  self.assertIn('println("QKV_PROTOCOL_SIM_READY")',s)
  self.assertIn('production_kernel_debt_tested=false',s)
  self.assertIn('sentinel(0,i)',s);self.assertIn('sentinel(1,i)',s)
  self.assertIn('Status.Protocol.U',s)
if __name__=='__main__':unittest.main(verbosity=2)
