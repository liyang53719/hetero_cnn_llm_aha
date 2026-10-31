"""AST-extracted actual argv generation and dispatch mocks; no process execution."""
import ast,pathlib,types,unittest,sys
from unittest.mock import patch
from test_lifecycle import m,D

class Tests(unittest.TestCase):
 def args(self):
  return types.SimpleNamespace(artifact_manifest=pathlib.Path('/fixture/manifest'),artifact_manifest_sha256='a'*64,expected_run_id=123,expected_launch_commit='b'*40,expected_source_commit='c'*40,local_runtime_abi_sha256='d'*64,owned_environment=pathlib.Path('/fixture/env'),owned_environment_sha256='e'*64,profile=1,local_build_result=None,local_build_result_sha256=None,builder_handoff=pathlib.Path('/fixture/handoff'),builder_handoff_sha256='f'*64,executor_identity=pathlib.Path('/fixture/executor'),executor_identity_sha256='1'*64)
 def argv(self,split):
  tree=ast.parse((D/'connect_owned.py').read_text());function=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and any(isinstance(x,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='argv'for t in x.targets)for x in n.body))
  start=next(i for i,x in enumerate(function.body)if isinstance(x,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='argv'for t in x.targets));selected=function.body[start:start+3]
  self.assertEqual([type(x).__name__ for x in selected],['Assign','If','AugAssign'])
  consumer=types.SimpleNamespace(executor_context=lambda args:{}if split else None)
  env=dict(args=self.args(),consumer=consumer,sys=sys,HERE=D,abi_copy=pathlib.Path('/fixture/abi'),final=pathlib.Path('/fixture/bundle'),out=pathlib.Path('/fixture/out'))
  exec(compile(ast.Module(body=selected,type_ignores=[]),'actual_connect_argv','exec'),env);return env['argv']
 def test_split_cli_has_only_handoff_not_samejob_result(self):
  a=self.argv(True)
  for flag in ('--builder-handoff','--builder-handoff-sha256','--executor-identity','--executor-identity-sha256','--strict-outer-supervised'):self.assertIn(flag,a)
  self.assertNotIn('--local-build-result',a);self.assertNotIn('--local-build-result-sha256',a)
 def test_original_cli_does_not_inject_cloud(self):
  a=self.argv(False);self.assertIn('--local-build-result',a);self.assertIn('--local-build-result-sha256',a);self.assertNotIn('--executor-identity',a);self.assertNotIn('--builder-handoff',a)
 def test_mixed_retained_and_imported_rejected_before_loading(self):
  for field in ('local_build_result','local_build_result_sha256'):
   a=self.args();setattr(a,field,'unexpected')
   with patch.object(m,'executor_context',return_value={'source_commit':a.expected_source_commit}),patch.object(m.subprocess,'Popen',side_effect=AssertionError('no execution')):
    with self.assertRaisesRegex(ValueError,'not same-job'):m.verify_local_build(a,{})
 def test_unpaired_executor_and_handoff_rejected(self):
  a=self.args();a.executor_identity=None
  with self.assertRaisesRegex(ValueError,'paired'):m.executor_context(a)
  a.executor_identity_sha256=None
  with self.assertRaisesRegex(ValueError,'paired'):m.executor_context(a)
 def test_original_unpaired_handoff_digest_rejected(self):
  a=self.args()
  with patch.object(m,'executor_context',return_value=None):
   with self.assertRaisesRegex(ValueError,'unpaired'):m.verify_local_build(a,{})
if __name__=='__main__':unittest.main()
