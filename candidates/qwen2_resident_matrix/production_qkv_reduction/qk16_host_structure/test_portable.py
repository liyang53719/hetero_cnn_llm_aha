import ast,hashlib,json,tempfile,unittest
from pathlib import Path
import prepare_generation
P=Path(__file__).resolve().parent
class Portable(unittest.TestCase):
 def test_pins(self):
  for n,h in json.loads((P/'OPERATIONAL_PINS.json').read_text()).items():self.assertEqual(hashlib.sha256((P/n).read_bytes()).hexdigest(),h,n)
 def test_source_and_class_closure(self):
  b=json.loads((P/'BASELINE_CLASS_PINS.json').read_text());c=json.loads((P/'ACTUAL_CLASS_PINS.json').read_text());self.assertEqual(len(b['classes']),550);self.assertEqual(len(c),553);self.assertEqual(len(json.loads((P/'SOURCE_PINS.json').read_text())),93)
  self.assertTrue(all(c[n]==h for n,h in b['classes'].items()))
 def test_safe_projection(self):
  r=json.loads((P/'SAFE_EVIDENCE.json').read_text());self.assertEqual(r['original_attempt']['status'],'FAIL');self.assertEqual(r['original_attempt']['driver_exit'],1);self.assertTrue(r['offline_review']['original_attempt_remains_failed']);self.assertFalse(r['offline_review']['java_rerun']);self.assertEqual(r['packed_connection_count'],4407)
  for key in ['"parent_pid"','"boot_id"','"owner_identity"','"session"','"stop"']:self.assertNotIn(key,(P/'SAFE_EVIDENCE.json').read_text())
 def test_no_binary_or_host_paths(self):
  for p in P.rglob('*'):
   if not p.is_file():continue
   self.assertNotIn(p.suffix,['.fir','.class','.jar','.sv','.bin','.log']);s=p.read_text();self.assertNotIn('/'+'workspace'+'/',s);self.assertNotIn('/'+'home'+'/'+'agent'+'/',s)
 def test_historical_prepare(self):
  with tempfile.TemporaryDirectory() as d:
   out=Path(d)/'generated';prepare_generation.prepare(out);self.assertEqual((out/'check_packed.py').read_bytes(),(P/'historical_v3_check_packed.py').read_bytes());self.assertEqual((out/'run_structure.py').read_bytes(),(P/'run_structure.py').read_bytes())
   with self.assertRaises(ValueError):prepare_generation.prepare(out)
 def test_parse(self):
  for p in P.glob('*.py'):ast.parse(p.read_text())
if __name__=='__main__':unittest.main()
