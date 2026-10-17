import json,unittest
from pathlib import Path
import validate as v
P=Path(__file__).resolve().parent;ROOT=P.parent
class Cold(unittest.TestCase):
 def test_eight_targets(self):self.assertEqual(len(v.validate(ROOT)),8)
 def test_preserved_six(self):
  a=(ROOT/'idma_wrapper_lint_runner_v3_20261017/structural_hints.vlt').read_text();self.assertTrue((P/'structural_hints.vlt').read_text().startswith(a))
 def test_no_waiver(self):self.assertNotIn('lint_off',(P/'structural_hints.vlt').read_text())
 def test_extra_reject(self):
  with self.assertRaises(ValueError):v.validate(ROOT,(P/'structural_hints.vlt').read_text()+'lint_off -rule UNOPTFLAT\n')
 def test_missing_reject(self):
  with self.assertRaises(ValueError):v.validate(ROOT,(P/'structural_hints.vlt').read_text().replace('read_rsp_i','wrong'))
 def test_hash_reject(self):
  t=json.loads((P/'TARGETS.json').read_text());t[-1]['sha256']='0'*64
  with self.assertRaisesRegex(ValueError,'hash'):v.validate(ROOT,targets=t)
 def test_declaration_reject(self):
  t=json.loads((P/'TARGETS.json').read_text());t[-1]['declaration_regex']='nonexistent'
  with self.assertRaisesRegex(ValueError,'declaration'):v.validate(ROOT,targets=t)
 def test_original_pins(self):
  import hashlib
  for n,h in json.loads((P/'SOURCE_PINS.json').read_text()).items():self.assertEqual(hashlib.sha256((ROOT/n).read_bytes()).hexdigest(),h)
 def test_original_context_not_public(self):
  a=json.loads((ROOT/'production_seed_begin_full_bench_noinline_attempt_v1_20261017/argv.json').read_text());self.assertEqual(a[a.index('--top-module')+1],'ProductionQk16KernelBench');self.assertFalse(any(x.startswith('--public') for x in a))
  for x in json.loads((P/'TARGETS.json').read_text())[-2:]:self.assertNotIn('/*verilator public',(ROOT/x['path']).read_text())
 def test_bad_preserved(self):
  p=next(n for n in json.loads((P/'SOURCE_PINS.json').read_text()) if n.endswith('IdmaWeightBurst.scala'));s=(ROOT/p).read_text();self.assertIn('rs.r.resp := Mux(bad, 3.U, io.axi.r.bits.resp)',s);self.assertIn('rs.r.last := last',s)
if __name__=='__main__':unittest.main()
