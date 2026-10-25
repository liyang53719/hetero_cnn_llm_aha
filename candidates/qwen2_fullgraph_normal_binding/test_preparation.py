"""Static actual source/DT_NEEDED preparation and negative tests, no target import."""
import argparse,ast,copy,hashlib,importlib.util,json
from pathlib import Path
import sys,tempfile,unittest
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import adapter
if Path(adapter.__file__).resolve()!=HERE/'adapter.py':raise RuntimeError('foreign adapter')
p=argparse.ArgumentParser(add_help=False);p.add_argument('--config',type=Path,required=True);args,remaining=p.parse_known_args();sys.argv=[sys.argv[0],*remaining]
CONFIG=json.loads(args.config.read_text());root=Path(CONFIG['cold_helper_root']);spec=importlib.util.spec_from_file_location('reviewed_runtime_closure',root/'runtime_closure.py');closure=importlib.util.module_from_spec(spec);spec.loader.exec_module(closure)
class Tests(unittest.TestCase):
 def test_exact_runtime_graph(self):self.assertTrue(closure.verify_graph(CONFIG['runtime_graph'],CONFIG['files']))
 def test_missing_needed_edge(self):
  graph=copy.deepcopy(CONFIG['runtime_graph']);graph['edges'].pop()
  with self.assertRaisesRegex(ValueError,'incomplete'):closure.verify_graph(graph,CONFIG['files'])
 def test_wrong_node_pin(self):
  graph=copy.deepcopy(CONFIG['runtime_graph']);graph['files'][graph['roots'][-1]]['sha256']='0'*64
  with self.assertRaisesRegex(ValueError,'pin mismatch'):closure.verify_graph(graph,CONFIG['files'])
 def test_unreachable_root_injected(self):
  graph=copy.deepcopy(CONFIG['runtime_graph']);graph['roots'].remove(next(p for p in graph['roots'] if '/yaml/' in p))
  with self.assertRaisesRegex(ValueError,'unreachable'):closure.verify_graph(graph,CONFIG['files'])
 def test_no_task_or_compiler_graph_root(self):
  roots=CONFIG['runtime_graph']['roots'];self.assertEqual(len(roots),4)
  self.assertNotIn(CONFIG['elf'],roots);self.assertNotIn('/usr/bin/git',roots)
  self.assertTrue(all(not p.endswith(('g++','gcc','clang')) for p in roots))
 def test_fixture_transitive_hashes(self):
  proof=json.loads((HERE/'FIXTURE_IMPORT_PINS.json').read_text());self.assertEqual(len(proof['source_files']),18);self.assertEqual(proof['external_top_level'],['numpy','yaml'])
  for rel,pin in proof['source_files'].items():
   raw=(Path(CONFIG['source_root'])/rel).read_bytes();self.assertEqual(len(raw),pin['bytes']);self.assertEqual(hashlib.sha256(raw).hexdigest(),pin['sha256'])
 def test_fixture_transitive_import_statements(self):
  proof=json.loads((HERE/'FIXTURE_IMPORT_PINS.json').read_text());trees={p:ast.parse((Path(CONFIG['source_root'])/p).read_bytes()) for p in proof['source_files']}
  expected={(p,n.lineno,ast.unparse(n)) for p,t in trees.items() for n in ast.walk(t) if isinstance(n,(ast.Import,ast.ImportFrom))}
  actual={(e['source'],e['line'],e['statement']) for e in proof['edges']}
  self.assertEqual(actual,expected)
 def test_config_byte_change_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'config.json';path.write_text('{}');sha=hashlib.sha256(path.read_bytes()).hexdigest();path.write_text('{} ');out=Path(tmp)/'out'
   with self.assertRaisesRegex(ValueError,'config hash'):adapter.main(['--config',str(path),'--config-sha',sha,'--output',str(out)])
   self.assertFalse(out.exists())
 def test_no_direct_library_or_task_calls(self):
  tree=ast.parse((HERE/'adapter.py').read_text());names={n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)}
  self.assertFalse(names & {'CDLL','configure_library','td_reset','sf_reset','make_qwen2_21_fixture','execute_public_prefix','execute_public_suffix'})
 def test_private_dependency_root_extent(self):
  root=Path(CONFIG['yaml_root']);files=list(p for p in root.rglob('*') if p.is_file());self.assertEqual(len(files),18)
  self.assertTrue(all(p.parent==root/'yaml' for p in files));self.assertNotIn('site-packages',str(root))
if __name__=='__main__':unittest.main()
