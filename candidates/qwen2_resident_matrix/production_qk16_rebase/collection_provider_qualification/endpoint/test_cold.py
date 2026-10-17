import ast,json,unittest,hashlib
from pathlib import Path
import run_lint,owned_compile
P=Path(__file__).resolve().parent
class Cold(unittest.TestCase):
 def test_no_execute(self):
  class A:execute=False
  with self.assertRaises(ValueError):run_lint.run(A())
 def test_syntax(self):
  for f in P.glob('*.py'):ast.parse(f.read_text())
  ast.parse(owned_compile.CHILD)
 def test_composition(self):
  c=json.loads((P/'COMPOSITION.json').read_text());self.assertEqual(len(c['sources_ordered']),14);self.assertEqual(len(c['definitions']),76);self.assertEqual(len(c['excluded_exact_standalone_fma']),4);self.assertEqual(len(c['include_directories_ordered']),0)
  self.assertEqual(c['top'],'qwen2_matrix_command_endpoint');self.assertEqual(set(c['initial_defines']),{'TARGET_ASIC','TARGET_RTL','TARGET_SYNTHESIS','TARGET_VERILATOR'})
 def test_pins(self):
  c=json.loads((P/'COMPOSITION.json').read_text());p=json.loads((P/'INPUT_PINS.json').read_text())
  for r in c['sources_ordered']:self.assertEqual(p[r['path']],r['sha256'])
 def test_limits(self):
  self.assertIn('(4294967296,4294967296)',owned_compile.CHILD);self.assertIn('(16777216,16777216)',owned_compile.CHILD);self.assertIn('sched_setaffinity',owned_compile.CHILD)
 def test_no_warning_suppression(self):
  s=(P/'run_lint.py').read_text();self.assertIn("'--lint-only'",s);self.assertIn("'--top-module','qwen2_matrix_command_endpoint'",s)
  for x in ['-Wno','--build','--bbox','--cc','--exe','--binary']:self.assertNotIn(repr(x),s)
 def test_exact_parameter_and_units(self):
  s=(P/'run_lint.py').read_text();self.assertIn("-GENABLE_ACCUMULATOR_SEED=1'b1",s);self.assertIn("'--timescale','1ns/1ps'",s);self.assertNotIn('--timescale-override',s);self.assertIn('generated_file_limit_bytes=16777216',(P/'owned_compile.py').read_text())
 def test_identity_cleanup(self):
  self.assertEqual(hashlib.sha256((P/'strict_cleanup.py').read_bytes()).hexdigest(),owned_compile.HELPER_SHA);self.assertIn('os.WNOWAIT',(P/'owned_compile.py').read_text());self.assertIn("'VERILATOR_ROOT':str(Path(argv[0]).resolve().parent.parent/'share/verilator')",(P/'owned_compile.py').read_text())
if __name__=='__main__':unittest.main()
