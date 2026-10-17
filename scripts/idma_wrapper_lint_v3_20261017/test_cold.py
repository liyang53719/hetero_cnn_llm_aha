import ast,hashlib,json,signal,unittest
from pathlib import Path
from unittest.mock import patch
import run_lint as r,owned_compile
P=Path(__file__).resolve().parent;ROOT=P.parent
class Cold(unittest.TestCase):
 def test_syntax(self):
  for f in P.glob('*.py'):ast.parse(f.read_text())
  ast.parse(owned_compile.CHILD)
 def test_no_execute(self):
  class A:execute=False
  old=signal.getsignal(signal.SIGALRM)
  with self.assertRaisesRegex(ValueError,'explicit execute'):r.run(A())
  self.assertEqual(signal.getsignal(signal.SIGALRM),old);self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.,0.))
 def test_preexisting_alarm(self):
  signal.setitimer(signal.ITIMER_REAL,60)
  try:
   with self.assertRaisesRegex(ValueError,'preexisting alarm'):r.run(None)
   self.assertGreater(signal.getitimer(signal.ITIMER_REAL)[0],50)
  finally:signal.setitimer(signal.ITIMER_REAL,0)
 def test_preflight_only(self):
  c,p,w=r.prepare(ROOT);self.assertEqual(len(c['source_order']),293);self.assertEqual(w.count('lint_off'),21);self.assertNotIn('PINMISSING',w)
 def test_rule_binding(self):
  rows=json.loads((P/'WARNINGS.json').read_text())['warnings'];pins=json.loads((P/'INPUT_PINS.json').read_text());rows[0]['source_sha256']='0'*64
  with self.assertRaisesRegex(ValueError,'warning source hash'):r.waiver_text(ROOT,rows,pins)
 def test_subset_exact(self):
  c=json.loads((P/'LINT_PLAN_REDUCED.json').read_text());original=json.loads((ROOT/'production_qk16_provider_composition_v1_20261017/COMPOSITION.json').read_text())['sources_ordered']
  wanted=original[:294]+[original[-1]];ex={x['path'] for x in c['excluded_library_candidates_lexical_only']};self.assertEqual(len(ex),2);self.assertEqual(c['source_order'],[x for x in wanted if x['path'] not in ex])
 def test_fixed_params(self):
  self.assertEqual(hashlib.sha256((ROOT/r.WRAP).read_bytes()).hexdigest(),r.WRAP_SHA)
  text=(ROOT/r.WRAP).read_text()
  for term in ['.DataWidth(512)','.AddrWidth(64)','.BufferDepth(3)','.HardwareLegalizer(1)','.RejectZeroTransfers(1)','.EnableCompute(0)']:self.assertIn(term,text)
 def test_no_blanket_suppression(self):
  text=(P/'run_lint.py').read_text()
  constants={n.value for n in ast.walk(ast.parse(text)) if isinstance(n,ast.Constant) and isinstance(n.value,str)}
  for term in ['-Wno','--timescale-override','--build','--bbox','--cc','--exe','--binary']:self.assertNotIn(term,constants)
 def test_native_limits(self):
  for term in ['(4294967296,4294967296)','(16777216,16777216)','sched_setaffinity']:self.assertIn(term,owned_compile.CHILD)
  self.assertEqual(owned_compile.LOG_LIMIT_BYTES,2097152)
 def test_helper_identity(self):
  self.assertEqual(hashlib.sha256((P/'strict_cleanup.py').read_bytes()).hexdigest(),owned_compile.HELPER_SHA)
  self.assertIn('os.WNOWAIT',(P/'owned_compile.py').read_text());self.assertIn('cleanup_owned',(P/'owned_compile.py').read_text())
 def test_helper_no_native_execution(self):
  with patch.object(owned_compile.subprocess,'Popen',side_effect=AssertionError('tool must not run')):
   self.test_preflight_only()
 def test_bad_root(self):
  with self.assertRaisesRegex(ValueError,'unsafe workspace'):r.prepare(Path('/tmp/path with spaces'))
 def test_hint_targets(self):
  c=json.loads((P/'LINT_PLAN_REDUCED.json').read_text());h=(P/'structural_hints.vlt').read_text();m=r.validate_hints(ROOT,c,h);self.assertEqual(len(m),6);self.assertTrue(all(x['declaration_matches']==1 for x in m))
 def test_hint_miss_fails(self):
  c=json.loads((P/'LINT_PLAN_REDUCED.json').read_text());h=(P/'structural_hints.vlt').read_text().replace('first_w','does_not_exist')
  with self.assertRaisesRegex(ValueError,'unmatched or extra'):r.validate_hints(ROOT,c,h)
 def test_hint_ambiguous_fails(self):
  c=json.loads((P/'LINT_PLAN_REDUCED.json').read_text());c['source_order'].append(next(x for x in c['source_order'] if x['path'].endswith('/idma_axi_write.sv')));h=(P/'structural_hints.vlt').read_text()
  with self.assertRaisesRegex(ValueError,'not unique/matched'):r.validate_hints(ROOT,c,h)
if __name__=='__main__':unittest.main()
