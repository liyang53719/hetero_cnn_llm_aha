"""Hash-only equivalence; never imports/executes supervisor machinery."""
import ast,hashlib,pathlib,tempfile,unittest
D=pathlib.Path(__file__).resolve().parent;P=D.parents[1]/'ci_frontend_pipeline_r2_20261029/supervise_multiroot.py'
class Stream(unittest.TestCase):
 def test_all_other_ast_unchanged(self):
  old=ast.parse((D/'fixtures/supervisor_sha_base.py.txt').read_text());new=ast.parse(P.read_text())
  for tree in(old,new):tree.body=[n for n in tree.body if not(isinstance(n,ast.FunctionDef)and n.name=='sha')]
  self.assertEqual(ast.dump(old),ast.dump(new))
 def test_real_file_hashes(self):
  tree=ast.parse(P.read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='sha');space={'Path':pathlib.Path,'hashlib':hashlib};exec(compile(ast.Module(body=[fn],type_ignores=[]),'hash_only','exec'),space)
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t)/'bytes';p.write_bytes(bytes(range(256))*4096)
   for target in(P,p,D/'fixtures/supervisor_sha_base.py.txt'):
    self.assertEqual(space['sha'](target),hashlib.sha256(target.read_bytes()).hexdigest())
if __name__=='__main__':unittest.main()
