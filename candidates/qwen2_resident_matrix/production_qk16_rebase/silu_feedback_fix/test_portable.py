import ast,json,tempfile,unittest
from pathlib import Path
import reproduce_sources as r
P=Path(__file__).resolve().parent
class Cold(unittest.TestCase):
 def test_syntax(self):
  for p in P.glob('*.py'):ast.parse(p.read_text())
 def test_exact_repair(self):
  s=(P/'source/FfnTileSiluBridge.scala').read_text();self.assertEqual(s.count('io.tiles.abort:=bad;io.silu.abort:=io.abort || poison'),1)
 def test_source_counts(self):
  self.assertEqual(len(json.loads((P/'PRODUCTION_SOURCE_PINS.json').read_text())),92)
  self.assertEqual(len(json.loads((P/'BASELINE_PINS.json').read_text())['sources']),94)
 def test_failure_scope(self):
  s=json.loads((P/'SAFE_RESULT.json').read_text());self.assertEqual(s['strict_class_attempt']['status'],'NOT_COMPLETED');self.assertTrue(s['offline_compatibility']['pass']);self.assertFalse(s['original_B1']['completed_SV'])
 def test_bad_source_refused(self):
  with tempfile.TemporaryDirectory() as d:
   src=Path(d)/'src';src.mkdir()
   with self.assertRaises(ValueError):r.compose(src,Path(d)/'out')
if __name__=='__main__':unittest.main()
