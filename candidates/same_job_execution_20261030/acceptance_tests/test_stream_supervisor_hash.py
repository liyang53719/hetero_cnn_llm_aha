"""Streaming hash and exact reviewed census transformation; never imports/executes supervisor machinery."""
import ast,hashlib,pathlib,tempfile,unittest
D=pathlib.Path(__file__).resolve().parent;P=D.parents[1]/'ci_frontend_pipeline_r2_20261029/supervise_multiroot.py'
class Stream(unittest.TestCase):
 def test_all_other_ast_unchanged(self):
  old=ast.parse((D/'fixtures/supervisor_sha_base.py.txt').read_text());new=ast.parse(P.read_text())
  for tree in(old,new):tree.body=[n for n in tree.body if not(isinstance(n,ast.FunctionDef)and n.name=='sha')]
  # Only the independently reviewed low-object census transformation is added.
  # Exact AST pair locks prevent excluding arbitrary future sampler changes.
  oldfn=next(n for n in ast.walk(old)if isinstance(n,ast.FunctionDef)and n.name=='output_sample')
  newfn=next(n for n in ast.walk(new)if isinstance(n,ast.FunctionDef)and n.name=='output_sample')
  self.assertEqual(hashlib.sha256(ast.dump(oldfn).encode()).hexdigest(),'97bd93ba06ee696a7941f94dbd46625542c335c34057d7e80246d3b167ee2844')
  self.assertEqual(hashlib.sha256(ast.dump(newfn).encode()).hexdigest(),'3f00fc4665849d7d44a7d7b25f9eca3f97ce9895b9821760de43d04c8ae3c782')
  newfn.body=oldfn.body
  self.assertEqual(ast.dump(old),ast.dump(new))
 def test_real_file_hashes(self):
  tree=ast.parse(P.read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='sha');space={'Path':pathlib.Path,'hashlib':hashlib};exec(compile(ast.Module(body=[fn],type_ignores=[]),'hash_only','exec'),space)
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t)/'bytes';p.write_bytes(bytes(range(256))*4096)
   for target in(P,p,D/'fixtures/supervisor_sha_base.py.txt'):
    self.assertEqual(space['sha'](target),hashlib.sha256(target.read_bytes()).hexdigest())
if __name__=='__main__':unittest.main()
