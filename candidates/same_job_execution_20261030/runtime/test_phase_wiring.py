import ast,pathlib,unittest
D=pathlib.Path(__file__).resolve().parent
class T(unittest.TestCase):
 def test_no_nested_session(self):
  for p in [D/'runtime_phase.py',*list((D/'source').rglob('*.py'))]:
   tree=ast.parse(p.read_text())
   for x in ast.walk(tree):
    if isinstance(x,ast.Call):
     self.assertFalse(isinstance(x.func,ast.Attribute)and x.func.attr in ('setsid','setpgid'),str(p))
     self.assertFalse(any(k.arg=='start_new_session'and isinstance(k.value,ast.Constant)and k.value.value is True for k in x.keywords),str(p))
 def test_phase_original_calls(self):
  tree=ast.parse((D/'runtime_phase.py').read_text());calls=[x.func.attr for x in ast.walk(tree)if isinstance(x,ast.Call)and isinstance(x.func,ast.Attribute)]
  for name in ('artifacts','qwen2_install','qwen35_install','derive','verify_sidecar'):self.assertIn(name,calls)
  self.assertNotIn('acquire',calls);self.assertNotIn('Popen',calls)
 def test_no_model_import(self):
  for p in (D/'runtime_phase.py',D/'install_job.py'):
   t=ast.parse(p.read_text());mods=[x.name for n in ast.walk(t)if isinstance(n,ast.Import)for x in n.names]
   self.assertNotIn('torch',mods);self.assertNotIn('transformers',mods)
 def test_cleanup_none_is_not_pass(self):
  import install_job
  self.assertFalse(install_job.complete({'cleanup_proof':None,'log_capture':None}))
if __name__=='__main__':unittest.main()
