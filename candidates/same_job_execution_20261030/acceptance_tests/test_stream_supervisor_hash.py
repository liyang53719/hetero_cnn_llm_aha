"""Streaming hash and exact reviewed census transformation; never imports/executes supervisor machinery."""
import ast,hashlib,pathlib,tempfile,unittest
D=pathlib.Path(__file__).resolve().parent;P=D.parents[1]/'ci_frontend_pipeline_r2_20261029/supervise_multiroot.py'

# Exact independently reviewed V2 telemetry/signals plus producer proc correction.
# No historical fixture or census/hash expectation is replaced.
REVIEWED_HOST_FUNCTION_AST = {'_v2_validate_numeric_caps': '864b27b23cea6d8dd50a3ec0dffe236e275323efe4e921e822fbdf2624948d22', '_v2_set_owned_signal_mask': '130083420d41a1a596ac8d67a3e5f22072e7bf1e0d0d65a062d98b9b405e61a8', '_v2_claim_signal_ownership': 'bbb6cc76839f8769ccb54d29d3b16c8a3814ad284fb725becba57a4aa2858e07', 'execute': '4860080bda644adbb1f539b32745bd41f9e33bcea5b145de0dfc1df9ca205261'}
HISTORICAL_EXECUTE_AST = 'f80d2cf5aa05a801e1d36609cbeb799d0d73746def2bbc6bec12bc230d4bc1b7'
def undo_reviewed_host_delta(test,tree,baseline):
 import copy
 tree=copy.deepcopy(tree)
 def one(root,name):
  rows=[n for n in root.body if isinstance(n,ast.FunctionDef)and n.name==name]
  test.assertEqual(len(rows),1,'one exact reviewed host function: '+name)
  return rows[0]
 def digest(node):return hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest()
 for name,wanted in REVIEWED_HOST_FUNCTION_AST.items():
  node=one(tree,name);test.assertEqual(digest(node),wanted,'exact reviewed host function: '+name)
  if name!='execute':tree.body.remove(node)
 current=one(tree,'execute');historical=copy.deepcopy(one(baseline,'execute'))
 test.assertEqual(digest(historical),HISTORICAL_EXECUTE_AST,'unchanged historical execute AST')
 current_samples=[n for n in ast.walk(current)if isinstance(n,ast.FunctionDef)and n.name=='output_sample']
 old_samples=[n for n in ast.walk(historical)if isinstance(n,ast.FunctionDef)and n.name=='output_sample']
 test.assertEqual((len(current_samples),len(old_samples)),(1,1))
 test.assertEqual(digest(current_samples[0]),'3f00fc4665849d7d44a7d7b25f9eca3f97ce9895b9821760de43d04c8ae3c782')
 test.assertEqual(digest(old_samples[0]),'97bd93ba06ee696a7941f94dbd46625542c335c34057d7e80246d3b167ee2844')
 # Keep the prior reviewed census transformation for its original test below.
 old_samples[0].body=copy.deepcopy(current_samples[0].body)
 tree.body[tree.body.index(current)]=historical
 return tree

class Stream(unittest.TestCase):
 def test_all_other_ast_unchanged(self):
  self.check_original_ast(ast.parse(P.read_text()))
 def check_original_ast(self,new):
  old=ast.parse((D/'fixtures/supervisor_sha_base.py.txt').read_text());new=undo_reviewed_host_delta(self,new,old)
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

 def test_reviewed_host_function_missing_mutated_duplicate_rejected(self):
  import copy
  baseline=ast.parse((D/'fixtures/supervisor_sha_base.py.txt').read_text())
  for name in REVIEWED_HOST_FUNCTION_AST:
   for case in('missing','mutated','duplicate'):
    tree=ast.parse(P.read_text());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name==name)
    if case=='missing':tree.body.remove(node)
    elif case=='duplicate':tree.body.append(copy.deepcopy(node))
    else:
     names=[n for n in ast.walk(node)if isinstance(n,ast.Name)];self.assertTrue(names);names[0].id='UNREVIEWED_HOST_MUTATION'
    with self.subTest(name=name,case=case),self.assertRaises(AssertionError):undo_reviewed_host_delta(self,tree,baseline)
 def test_unrelated_delta_survives_and_fails_historical_baseline(self):
  tree=ast.parse(P.read_text());tree.body.extend(ast.parse('UNREVIEWED_OUTSIDE_DELTA = 1').body)
  before=ast.dump(tree);baseline=ast.parse((D/'fixtures/supervisor_sha_base.py.txt').read_text())
  restored=undo_reviewed_host_delta(self,tree,baseline)
  self.assertEqual(ast.dump(tree),before);self.assertIn('UNREVIEWED_OUTSIDE_DELTA',ast.unparse(restored))
  with self.assertRaises(AssertionError)as caught:self.check_original_ast(tree)
  self.assertNotIn('exact reviewed host function',str(caught.exception))
 def test_historical_fixture_mutation_is_not_accepted(self):
  baseline=ast.parse((D/'fixtures/supervisor_sha_base.py.txt').read_text());node=next(n for n in baseline.body if isinstance(n,ast.FunctionDef)and n.name=='execute');node.body.append(ast.parse('UNREVIEWED_BASELINE = 1').body[0])
  with self.assertRaisesRegex(AssertionError,'unchanged historical execute AST'):undo_reviewed_host_delta(self,ast.parse(P.read_text()),baseline)

if __name__=='__main__':unittest.main()
