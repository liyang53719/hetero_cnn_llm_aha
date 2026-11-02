import ast,pathlib,types,unittest
import os
P=pathlib.Path;D=P(os.environ.get('FIRST_FAULT_LEGACY_TEST_SOURCE',str(P(__file__).resolve().parent))).resolve()
class Tests(unittest.TestCase):
 def setUp(self):
  self.tree=ast.parse((D/'summarize_cloud_execution.py').read_text());self.mode=types.SimpleNamespace(FIRST_FAULT='P0_FIRST_FAULT_DIAGNOSTIC',STAGE='STAGE_COVERAGE_DIAGNOSTIC',FULL='FULL_BLOCK_ACCEPTANCE',CALIBRATION='BOUNDED_CALIBRATION')
 def run_budget(self,mode,full,stage,flowpin=None):
  nodes=[n for n in ast.walk(self.tree)if isinstance(n,ast.If)and ast.unparse(n.test)=="admission['mode'] == mode.STAGE"and any(isinstance(x,ast.Constant)and x.value=='stage budget domain binding'for x in ast.walk(n))];self.assertEqual(len(nodes),1)
  def need(v,m):
   if not v:raise ValueError(m)
  pin={'sha256':'a'*64};ns=dict(first_fault=False,mode=self.mode,admission={'mode':mode,'reviewed_budget_sha256':'a'*64},flow={'stage_coverage_budget':pin if flowpin is None else flowpin},b={'stage_coverage_budget':pin},numeric={'full_budget_sha256':full,'stage_budget_sha256':stage},need=need)
  exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),'actual_summary_branch','exec'),ns)
 def test_stage_exact(self):self.run_budget(self.mode.STAGE,None,'a'*64)
 def test_stage_no_full_alias(self):
  with self.assertRaises(ValueError):self.run_budget(self.mode.STAGE,'a'*64,None)
 def test_stage_bad_flow_pin(self):
  with self.assertRaises(ValueError):self.run_budget(self.mode.STAGE,None,'a'*64,{'sha256':'b'*64})
 def test_full_legacy(self):self.run_budget(self.mode.FULL,'a'*64,None)
 def test_legacy_stage_injection(self):
  with self.assertRaises(ValueError):self.run_budget(self.mode.FULL,'a'*64,'a'*64)
 def test_scope_exact_three(self):
  nodes=[n for n in ast.walk(self.tree)if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='scope'for t in n.targets)and isinstance(n.value,ast.Subscript)and isinstance(n.value.value,ast.Dict)];self.assertEqual(len(nodes),1)
  for mode,want in [(self.mode.STAGE,'STAGE_COVERAGE_DIAGNOSTIC_NOT_FULL_ACCEPTANCE'),(self.mode.FULL,'FULL_BLOCK_ACCEPTANCE_REQUIRED_TERMINAL_AND_REFERENCE'),(self.mode.CALIBRATION,'CALIBRATION_SAME_FULL_M128_STIMULUS')]:
   ns=dict(first_fault=False,mode=self.mode,admission={'mode':mode});exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),'scope','exec'),ns);self.assertEqual(ns['scope'],want)
 def test_post_cleanup_targets_known_and_unknown_not_numeric(self):
  nodes=[n for n in ast.walk(self.tree)if isinstance(n,ast.If)and ast.unparse(n.test)=="admission['mode'] == mode.STAGE"and any(isinstance(x,ast.Constant)and x.value=='POST_CLEANUP_COMMAND_RETIREMENT_ONLY_NOT_NUMERICAL_PASS'for x in ast.walk(n))];self.assertEqual(len(nodes),1)
  progress=types.SimpleNamespace(project=lambda *a:{'profiles':[{'profile':0,'last':{'completions':2}},{'profile':1,'last':None}]})
  result={'numerical_pass':False};D=P('/synthetic');path=D/'summary_progress.py'
  ns=dict(first_fault=False,mode=self.mode,admission={'mode':self.mode.STAGE,'reviewed_budget_sha256':'a'*64},D=D,b={'pins':{str(path):'h'},'stage_coverage_budget':{}},sha=lambda p:'h',need=lambda ok,m:self.assertTrue(ok,m),load=lambda *a:progress,job=None,builder=None,checked=lambda x:x,read=lambda p:{'profiles':{'0':{'target_completed_commands':2},'1':{'target_completed_commands':2}}},result=result)
  exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),'post_cleanup','exec'),ns)
  self.assertTrue(result['stage_coverage_observations'][0]['target_observed']);self.assertIsNone(result['stage_coverage_observations'][1]['target_observed']);self.assertFalse(result['numerical_pass']);self.assertFalse(result['full_acceptance_mode'])
if __name__=='__main__':unittest.main()
