"""Cold-only package checks. No compiler, emitter, tool or network execution."""
import ast,hashlib,json,unittest,tempfile
from pathlib import Path
import native_tools,incremental_classes
P=Path(__file__).parent
class Cold(unittest.TestCase):
 def test_python_parse(self):
  for f in P.glob('*.py'):ast.parse(f.read_text())
 def test_sources_pinned(self):
  j=json.loads((P/'SOURCE_CLOSURE.json').read_text())
  self.assertEqual(len(j['production']),91);self.assertEqual(len(j['harness']),3)
  for n,h in j['harness'].items():self.assertEqual(hashlib.sha256((P/n).read_bytes()).hexdigest(),h)
 def test_sourceonly_fixtures(self):
  pins=json.loads((P/'FIXTURE_PINS.json').read_text());self.assertEqual(len(pins),10)
  actual={str(f.relative_to(P/'fixtures')):hashlib.sha256(f.read_bytes()).hexdigest() for f in (P/'fixtures').rglob('*') if f.is_file()}
  self.assertEqual(actual,{n:h for n,h in pins.items() if not n.endswith('.bin')})
 def test_dependency_transition(self):
  incremental_classes.verify_dependency_transition(json.loads((P/'dependency-lock.json').read_text()),json.loads((P/'JDK_PINS.json').read_text()))
 def test_projection_scope(self):
  p=json.loads((P/'CONTROL_PASS_PROJECTION.json').read_text());self.assertEqual(p['status'],'PASS_CONTROL_ONLY');self.assertFalse(p['production_kernel']);self.assertFalse(p['arithmetic']);self.assertFalse(p['m128_numerical'])
  self.assertEqual(len(p['final_class_hashes']),555);self.assertEqual(len(p['added_class_sourcefiles']),10)
  for s in p['stages']:self.assertTrue(s['cleanup']['absence_barrier_before_reap'])
 def test_projection_no_host_identity(self):
  t=(P/'CONTROL_PASS_PROJECTION.json').read_text()
  for s in ['boot_id','parent_pid','owner_identity','/workspace/','session','start_ticks']:self.assertNotIn(s,t)
 def test_no_wrapper_stdout(self):
  t=ast.parse((P/'native_wrapper.py').read_text());self.assertFalse(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='print' for n in ast.walk(t)))
 def test_override_reject(self):
  for op in ['=',':=','::=',':::=','+=','?=','!=']:
   rows=[dict(tool=t,argv=[t,'-j1','VM_PARALLEL_BUILDS=0','VM_PARALLEL_BUILDS'+op+'1'] if t=='make' else [t],as_limit=[2147483648]*2,affinity=[0]) for t in ['make','g++','verilator']]
   with tempfile.TemporaryDirectory() as d:
    f=Path(d)/'audit';f.write_text('\n'.join(map(json.dumps,rows)))
    with self.assertRaises(ValueError):native_tools.validate_audit(f)
if __name__=='__main__':unittest.main(verbosity=2)
