import ast,importlib.util,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
D=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('selected_runtime',D/'prepare_runtimes.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Tests(unittest.TestCase):
 def test_all_five_mappings(self):
  self.assertEqual([m.selected_runtime(i) for i in range(5)],['qwen2','qwen35_08b','qwen35_08b','qwen35_35b','qwen35_35b'])
 def test_unsupported_profiles(self):
  for p in [-1,5,True,False,1.0,'0',None]:
   with self.assertRaises(ValueError):m.selected_runtime(p)
 def test_p0_only_26_wheels_no_archive(self):
  q,s,t=m.artifacts();a=m.selected_artifacts(0,q,s);self.assertIs(a,q);self.assertEqual(len(a),26);self.assertTrue(all(x['filename'].endswith('.whl') for x in a))
 def test_08_only_38_wheels_one_exact_archive(self):
  q,s,t=m.artifacts()
  for p in [1,2]:
   a=m.selected_artifacts(p,q,s);self.assertEqual(len(a),39);self.assertEqual(a[-1]['sha256'],'15a8ff42ef4fba57ff51034e1cd7d3672dec2bf1cf080134eb69d13c69ee6a2d');self.assertNotIn(s['qwen35_35b']['transformers'],a)
 def test_35_only_38_wheels_one_exact_archive(self):
  q,s,t=m.artifacts()
  for p in [3,4]:
   a=m.selected_artifacts(p,q,s);self.assertEqual(len(a),39);self.assertEqual(a[-1]['sha256'],'69273c7d563dd207ad4d6ada4ab16105e7c21366ac4142be1e5f53649b23c5e9');self.assertNotIn(s['qwen35_08b']['transformers'],a)
 def test_all_plans_zero_network_install_or_output(self):
  with tempfile.TemporaryDirectory() as t:
   repo=Path(t)/'repo';(repo/'src/heteronpu').mkdir(parents=True)
   with patch.object(m,'acquire',side_effect=AssertionError('network')),patch.object(m,'qwen2_install',side_effect=AssertionError('install')),patch.object(m,'qwen35_install',side_effect=AssertionError('install')):
    for p in range(5):
     out=Path(t)/str(p);r=m.prepare(repo,out,p);self.assertEqual(r['runtime_keys'],[m.selected_runtime(p)]);self.assertFalse(out.exists())
 def test_installer_dispatch_is_one_selected_entry(self):
  tree=ast.parse((D/'prepare_runtimes.py').read_text());fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='prepare');assign=next(n for n in ast.walk(fn) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='installed' for t in n.targets));self.assertIsInstance(assign.value,ast.Dict);self.assertEqual(len(assign.value.keys),1);self.assertIsInstance(assign.value.values[0],ast.IfExp)
 def test_fixed_sidecar_hashes(self):
  e=json.loads((D/'RUNTIME_CONTRACT.json').read_text())['entries'];self.assertEqual(e['qwen35_35b']['expected_sidecar_sha256'],'79078825f230ffecf33fff9b838d40b155217b025accf26e961927a25a475743');self.assertEqual(len(e),3)
 def test_invalid_plan_rejected_before_side_effects(self):
  with tempfile.TemporaryDirectory() as t:
   with patch.object(m,'artifacts',side_effect=AssertionError('must reject early')):
    with self.assertRaises(ValueError):m.prepare(Path(t),Path(t)/'new',9)
if __name__=='__main__':unittest.main()
