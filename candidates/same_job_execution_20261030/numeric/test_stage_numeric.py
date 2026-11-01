"""Synthetic wiring tests, not model admission, ABI, arithmetic, or DUT execution."""
import ast,hashlib,importlib.util,json,pathlib,tempfile,types,unittest
from unittest import mock
D=pathlib.Path(__file__).resolve().parent
CAL='BOUNDED_CALIBRATION';FULL='FULL_BLOCK_ACCEPTANCE';STAGE='STAGE_COVERAGE_DIAGNOSTIC'
def need(value,message):
 if not value:raise ValueError(message)
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def extract(file,names,namespace):
 tree=ast.parse((D/file).read_text());nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name in names]
 if len(nodes)!=len(names):raise ValueError('unique real function set')
 exec(compile(ast.Module(body=nodes,type_ignores=[]),str(D/file),'exec'),namespace);return namespace
class StageNumericTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.root=pathlib.Path(self.t.name).resolve()
  self.mode=types.SimpleNamespace(CALIBRATION=CAL,FULL=FULL,STAGE=STAGE)
  self.n=extract('numeric_tail.py',{'execution_command','mode_budget_fields'},{'D':D,'need':need,'execution_mode':self.mode,'material':types.SimpleNamespace(checked=lambda p:p)})
  self.admit=dict(mode=STAGE,profile_seconds={str(i):1000+i for i in range(5)},profile_max_active_cycles={str(i):10000 for i in range(5)},reviewed_budget_sha256='e'*64)
  self.b=dict(execution_context='CLOUD_EXECUTOR_V1',full_block_budget=None,stage_coverage_budget=dict(path=str(self.root/'stage.json'),sha256='e'*64),controller_binding=dict(path=str(self.root/'binding.json'),sha256='c'*64))
  self.generated=['python',str(D/'consumer_owned.py')]
 def test_stage_command_exact_paired_budget_no_old_flags(self):
  for i in range(5):
   argv,seconds=self.n['execution_command'](self.generated,self.b,self.admit,i)
   self.assertEqual(seconds,1030+i);self.assertNotIn('--calibration-wall-seconds',argv);self.assertNotIn('--full-block-budget',argv)
   self.assertEqual(argv[argv.index('--stage-coverage-budget')+1],self.b['stage_coverage_budget']['path'])
   self.assertEqual(argv[argv.index('--stage-coverage-budget-sha256')+1],'e'*64)
 def test_stage_rejects_noncloud_full_budget_and_stale_flags(self):
  for changes in ({'execution_context':'SAME_JOB'},{'full_block_budget':{'path':'bad'}}):
   with self.subTest(changes=changes),self.assertRaises(ValueError):self.n['execution_command'](self.generated,dict(self.b,**changes),self.admit,0)
  for flag in ('--execution-mode','--calibration-wall-seconds','--full-block-budget','--full-block-budget-sha256','--stage-coverage-budget','--stage-coverage-budget-sha256'):
   with self.subTest(flag=flag),self.assertRaises(ValueError):self.n['execution_command'](self.generated+[flag,'x'],self.b,self.admit,0)
 def test_budget_metadata_does_not_alias_full(self):
  self.assertEqual(self.n['mode_budget_fields'](self.admit),dict(full_budget_sha256=None,stage_budget_sha256='e'*64))
  for mode in (CAL,FULL):self.assertEqual(self.n['mode_budget_fields'](dict(self.admit,mode=mode)),dict(full_budget_sha256='e'*64))
 def test_original_cal_full_commands(self):
  b=dict(self.b,full_block_budget={'path':'full','sha256':'f'*64});a=dict(self.admit,mode=FULL)
  argv,_=self.n['execution_command'](self.generated,b,a,0);self.assertIn('--full-block-budget',argv);self.assertNotIn('--stage-coverage-budget',argv)
  argv,_=self.n['execution_command'](self.generated,self.b,dict(self.admit,mode=CAL),0);self.assertIn('--calibration-wall-seconds',argv);self.assertNotIn('--stage-coverage-budget',argv)
 def consumer(self,mode=STAGE,cloud=True,**updates):
  binding=self.root/'binding.json';helper=D.parent/'cloud_budget.py'
  doc=dict(execution_context='CLOUD_EXECUTOR_V1',executor_identity={'source_commit':'a'*40},artifact_manifest={'sha256':'a'*64},builder_handoff={'sha256':'b'*64},execution_mode=mode,pins={str(helper):'helperhash'},stage_coverage_budget=self.b['stage_coverage_budget'])
  binding.write_text(json.dumps(doc))
  args=types.SimpleNamespace(execution_mode=mode,cloud_binding=binding if cloud else None,cloud_binding_sha256=sha(binding)if cloud else None,artifact_manifest_sha256='a'*64,builder_handoff_sha256='b'*64,expected_source_commit='s',profile=0,calibration_wall_seconds=None,full_block_budget=None,full_block_budget_sha256=None,stage_coverage_budget=pathlib.Path(self.b['stage_coverage_budget']['path']),stage_coverage_budget_sha256='e'*64,validate_only=True)
  for key,value in updates.items():setattr(args,key,value)
  actual=extract('consumer_owned.py',{'explicit_execution_admission'},{'__file__':str(D/'consumer_owned.py'),'pathlib':pathlib,'json':json,'need':need,'sha':lambda p:'helperhash'if p==helper else sha(p),'executor_context':lambda args:doc['executor_identity']if cloud else None})
  mode_module=types.SimpleNamespace(CALIBRATION=CAL,FULL=FULL,STAGE=STAGE,admit=lambda b:dict(self.admit,mode=mode))
  cloud_module=types.SimpleNamespace(admit=lambda b:b)
  spec=lambda name,path:types.SimpleNamespace(loader=types.SimpleNamespace(exec_module=lambda m:None),name=name,path=path)
  with mock.patch.object(importlib.util,'spec_from_file_location',side_effect=spec),mock.patch.object(importlib.util,'module_from_spec',side_effect=lambda s:mode_module if s.name=='owned_execution_mode'else cloud_module):
   return actual['explicit_execution_admission'](args)
 def test_cloud_stage_flags_reach_exact_admission(self):self.assertEqual(self.consumer()[1]['mode'],STAGE)
 def test_stage_bad_flags_rejected(self):
  for fields in ({'calibration_wall_seconds':300},{'full_block_budget':pathlib.Path('/full')},{'full_block_budget_sha256':'f'*64},{'stage_coverage_budget':None},{'stage_coverage_budget_sha256':None},{'stage_coverage_budget':pathlib.Path('/other')},{'stage_coverage_budget_sha256':'f'*64}):
   with self.subTest(fields=fields),self.assertRaises(ValueError):self.consumer(**fields)
 def test_stage_noncloud_rejected_even_validate_only(self):
  with self.assertRaisesRegex(ValueError,'requires actual cloud'):self.consumer(cloud=False)
 def test_legacy_modes_reject_stage_flags(self):
  for mode in(CAL,FULL):
   with self.subTest(mode=mode),self.assertRaisesRegex(ValueError,'forbidden in other modes'):self.consumer(mode=mode)
 def test_stage_scope_and_cli_declared_exactly(self):
  t=ast.parse((D/'consumer_owned.py').read_text());main=next(n for n in t.body if isinstance(n,ast.FunctionDef)and n.name=='main')
  assignments=[n for n in ast.walk(main)if isinstance(n,ast.Assign)and ast.unparse(n.targets[0])=="summary['execution_admission']"]
  self.assertEqual(len(assignments),1);value=assignments[0].value;scope=value.values[[k.value for k in value.keys].index('scope')]
  for selected,expected in((CAL,'CALIBRATION_SAME_FULL_M128_STIMULUS'),(FULL,'FULL_BLOCK_ACCEPTANCE_REQUIRED_TERMINAL_AND_REFERENCE'),(STAGE,'STAGE_COVERAGE_DIAGNOSTIC_NOT_FULL_ACCEPTANCE')):
   self.assertEqual(eval(compile(ast.Expression(scope),'scope','eval'),dict(admission={'mode':selected},mode=self.mode)),expected)
  choices=[n.keywords for n in ast.walk(main)if isinstance(n,ast.Call)and n.args and isinstance(n.args[0],ast.Constant)and n.args[0].value=='--execution-mode'][0]
  self.assertEqual(ast.literal_eval(next(k.value for k in choices if k.arg=='choices')),(CAL,FULL,STAGE))
 def test_published_process_and_cleanup_bodies_unchanged(self):
  expected=BASELINE_FUNCTIONS
  for file,rows in expected.items():
   tree=ast.parse((D/file).read_text());functions={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
   for name,digest in rows.items():self.assertEqual(hashlib.sha256(ast.dump(functions[name],include_attributes=False).encode()).hexdigest(),digest,(file,name))
BASELINE_FUNCTIONS={'numeric_tail.py': {'complete': 'c0929df3a177afaef70f513f23312ce71be8c3e52e4a6c7b1888bd988579c892', 'prelaunch_rejection': 'acec9864ec03bf1111edc9077eb09df0e1b42ef1522f6b9c473033ff4ab70fa3', 'require_cleanup': 'c19273c256f5c7963198cb5dab03252fc1dbd9a426bca067feb97451dc9e77fe', 'owned_environment': '79b68726e3fd6ae271b5e6b4e208994c5cb997272acac267e384b768b44ed775'}, 'consumer_owned.py': {'execute': '002a96fc052bc186a0d5d6e900ea3a067dfc0d93400e3c31bc6118e31a406149', 'owned_execution_limits': '46dfe9b85cc94c67efb8ce89a52ede6e9d40f034aba3eea9408f2362e908f692', 'require_outer_context': 'cfd3497252bbb153ad83ed6f58daacc82fca3677c7d80edde44ac4a1d5f1ff2f'}}
if __name__=='__main__':unittest.main()
