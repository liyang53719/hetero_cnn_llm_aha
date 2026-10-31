"""Pure command/budget wiring, no provider, compiler or DUT execution."""
import importlib.util,pathlib,sys,unittest,json
D=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(D/'numeric'))
import numeric_tail as tail
import consumer_owned as consumer
spec=importlib.util.spec_from_file_location('full_flow_budget',D/'controller/flow.py');flow=importlib.util.module_from_spec(spec);spec.loader.exec_module(flow)
class Tests(unittest.TestCase):
 def test_five_full_commands_never_inherit_calibration(self):
  b={'full_block_budget':{'path':'/synthetic/budget.json','sha256':'a'*64}}
  admit=dict(mode='FULL_BLOCK_ACCEPTANCE',profile_seconds={str(i):400+i for i in range(5)})
  for i in range(5):
   original=['python',str(tail.D/'consumer_owned.py'),'--profile',str(i)]
   argv,seconds=tail.execution_command(original,b,admit,i)
   self.assertNotIn('--calibration-wall-seconds',argv);self.assertIn('--full-block-budget',argv);self.assertEqual(seconds,430+i);self.assertEqual(original[-2:],['--profile',str(i)])
 def test_calibration_retains_declared_windows(self):
  argv,seconds=tail.execution_command(['python',str(tail.D/'consumer_owned.py')],{},dict(mode='BOUNDED_CALIBRATION',profile_seconds={'0':300}),0)
  self.assertEqual(argv[-2:],['--calibration-wall-seconds','300']);self.assertEqual(seconds,330)
 def test_stale_mode_arguments_rejected(self):
  for flag in ('--execution-mode','--calibration-wall-seconds','--full-block-budget','--full-block-budget-sha256'):
   with self.assertRaises(ValueError):tail.execution_command(['python',str(tail.D/'consumer_owned.py'),flag],{},dict(mode='BOUNDED_CALIBRATION',profile_seconds={'0':300}),0)
 def test_full_windows_must_fit_existing_whole_budget(self):
  b={'budgets':json.loads((D/'BUDGETS.json').read_text())}
  good=dict(mode='FULL_BLOCK_ACCEPTANCE',profile_seconds={str(i):600 for i in range(5)})
  self.assertEqual(flow.reservations(b,good)[2],21000)
  bad=dict(good,profile_seconds={str(i):601 for i in range(5)})
  with self.assertRaises(ValueError):flow.reservations(b,bad)
 def test_actual_consumer_missing_wall_never_implicit20000(self):
  from types import SimpleNamespace
  args=SimpleNamespace(execution_mode='BOUNDED_CALIBRATION',calibration_wall_seconds=None,validate_only=False)
  with self.assertRaisesRegex(ValueError,'explicit calibration'):consumer.explicit_execution_admission(args)
  args.validate_only=True;_,admission=consumer.explicit_execution_admission(args);self.assertIsNone(admission) # read-only validation, not executable
 def test_actual_consumer_full_missing_budget_rejected(self):
  from types import SimpleNamespace
  with self.assertRaisesRegex(ValueError,'explicit reviewed budget'):consumer.explicit_execution_admission(SimpleNamespace(execution_mode='FULL_BLOCK_ACCEPTANCE',calibration_wall_seconds=None))
if __name__=='__main__':unittest.main()
