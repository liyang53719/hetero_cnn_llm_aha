"""Actual local Git guard -> prepare -> extracted bootstrap/materialize -> policy.
Tool/resource preparation synthetic; no EDA or execution qualification.
"""
import argparse,ast,sys,unittest
from unittest import mock
import test_first_fault_entry_flow as f
class TerminalFlow(unittest.TestCase):
 def setUp(self):
  self.e=f.EntryFlow(methodName='runTest');self.e.contract_version=2;self.e.setUp();self.addCleanup(self.e.doCleanups)
 def test_actual_guard_and_all_selectors_join(self):
  text=(f.ROOT/'.github/workflows/hetero-five-m128-model-candidate-build.yml').read_text();self.assertIn('paths: ['+f.guard.LAUNCH+']',text);self.assertEqual(text.count('--terminal-finite-readonly'),1)
  argv=self.e.prepare(False,True);self.assertEqual(argv.count('--terminal-finite-readonly'),1);self.assertNotIn('--first-fault-readonly',argv)
  binding,v=self.e.bootstrap_args(argv);self.assertTrue(v.terminal_finite_readonly);self.assertFalse(v.first_fault_readonly);self.assertEqual(binding.count('--terminal-finite-readonly'),1)
  b=self.e.materialize_selector(False,True);d=f.policy.binding_policy(b);self.assertTrue(f.policy.terminal_contract(d));self.assertEqual(b['first_fault_driver_contract']['sha256'],f.policy.TERMINAL_CONTRACT_SHA)
 def test_conflicting_prepare_flags_reject_before_metadata(self):
  m=f.load('_terminal_preflight',f.D/'prepare_model_build.py')
  with self.assertRaisesRegex(ValueError,'one explicit readonly mode'):m.run(argparse.Namespace(first_fault_readonly=True,terminal_finite_readonly=True))
 def test_materializer_conflicting_flags_reject(self):
  fun=f.function(f.D/'materialize_model_binding.py','main');nodes=[]
  for n in fun.body:
   nodes.append(n)
   if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name)and t.id=='v'for t in n.targets):break
  args=sum(([x,'placeholder']for x in ['--repo','--expected-repo-sha','--pipeline','--jdk-inventory','--java','--tools','--idma','--matrix','--binding','--output']),[])
  with mock.patch.object(sys,'argv',['materializer']+args+['--first-fault-readonly','--terminal-finite-readonly']),self.assertRaises(SystemExit):f.execute_nodes(nodes,dict(argparse=argparse,pathlib=f.pathlib))
 def test_wrong_version_with_new_helper_rejects(self):
  # V1 source admission cannot silently accept the changed V2 host helper.
  (self.e.repo/f.policy.CONTRACT_REPO_PATH).write_bytes((f.D/'FIRST_FAULT_DRIVER_CONTRACT.json').read_bytes())
  with self.assertRaisesRegex(ValueError,'host_observer'):f.policy.load_source_contract(self.e.repo)
if __name__=='__main__':unittest.main()
