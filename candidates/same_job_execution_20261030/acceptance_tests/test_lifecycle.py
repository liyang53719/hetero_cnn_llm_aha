import argparse,ast,importlib.util,json,pathlib,tempfile,types,unittest
from unittest.mock import patch
D=pathlib.Path(__file__).resolve().parents[1]/'numeric'
import sys
sys.path.insert(0,str(D))
spec=importlib.util.spec_from_file_location('owned',D/'consumer_owned.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
BASE=D.parent/'acceptance_tests/fixtures/consumer_r2_baseline.py.txt'
class Tests(unittest.TestCase):
 def test_original_functions_ast(self):
  old={n.name:ast.dump(n,include_attributes=False) for n in ast.parse(BASE.read_text().replace('ffb1c043cc1e21912a6ee6f11c7222e0885ebe89a38e68efce0027129e12617b','1bdc7fe9f8d4c1af3d39652f2f6a9d81f8ce0001a90b1ac3956f6ba590e9b523')).body if isinstance(n,ast.FunctionDef)}
  new={n.name:ast.dump(n,include_attributes=False) for n in ast.parse((D/'consumer_owned.py').read_text()).body if isinstance(n,ast.FunctionDef)}
  for name in old:
   if name not in ('main','compare','router_compare','classify_observed_profile'):self.assertEqual(old[name],new[name],name)
 def test_limits_only_wall_copy(self):
  original=dict(wall_seconds=20000,cpu_seconds=18000,address_space_bytes=12*1024**3,file_bytes=64*1024**2,max_active_cycles=1000000000)
  actual=m.owned_execution_limits(original,120)
  self.assertEqual(actual,dict(original,wall_seconds=120));self.assertEqual(original['wall_seconds'],20000)
  self.assertEqual(m.owned_execution_limits(original,None),original)
 def test_wall_reject(self):
  for value in (0,-1,20001,True,1.5):
   with self.assertRaises(ValueError):m.owned_execution_limits({'wall_seconds':20000},value)
 def test_outer_context(self):
  with patch.object(m.os,'getpid',return_value=5),patch.object(m.os,'getpgrp',return_value=5),patch.object(m.os,'getsid',return_value=5):
   m.require_outer_context(True)
   with self.assertRaises(ValueError):m.require_outer_context(False)
  with patch.object(m.os,'getpid',return_value=5),patch.object(m.os,'getpgrp',return_value=4),patch.object(m.os,'getsid',return_value=4):
   with self.assertRaises(ValueError):m.require_outer_context(True)
 def invoke(self,timeout=False):
  proc=types.SimpleNamespace(pid=71,poll=lambda:None,kill=unittest.mock.Mock(),wait=unittest.mock.Mock())
  state=None if timeout else types.SimpleNamespace(si_status=0,si_code=m.os.CLD_EXITED)
  with patch.object(m,'sha',return_value='a'*64),tempfile.TemporaryDirectory() as t,patch.object(m.subprocess,'Popen',return_value=proc) as popen,patch.object(m.os,'waitid',return_value=state),patch.object(m.os,'killpg') as killpg,patch.object(m.time,'monotonic',side_effect=[0,2] if timeout else [0]),patch.object(m,'runtime_abi_module',return_value=types.SimpleNamespace(clean_env=lambda:{'LANG':'C'})):
   limits={'address_space_bytes':1024**3,'cpu_seconds':1,'file_bytes':1024,'max_active_cycles':123,'wall_seconds':1}
   if timeout:
    with self.assertRaises(TimeoutError):m.execute(pathlib.Path('/fake/dut'),pathlib.Path('/fake/runtime'),pathlib.Path('/fake/output'),pathlib.Path(t)/'log',limits)
   else:self.assertEqual(m.execute(pathlib.Path('/fake/dut'),pathlib.Path('/fake/runtime'),pathlib.Path('/fake/output'),pathlib.Path(t)/'log',limits),0)
   self.assertNotIn('start_new_session',popen.call_args.kwargs);self.assertNotIn('process_group',popen.call_args.kwargs)
   killpg.assert_not_called();proc.kill.assert_called_once();proc.wait.assert_called_once()
   self.assertEqual(popen.call_args.args[0],['/fake/dut','/fake/runtime','/fake/output','123'])
 def test_normal_inherits_group(self):self.invoke()
 def test_timeout_inherits_group_cleanup(self):self.invoke(True)
 def test_inner_never_self_approves_outer_cleanup(self):
  tree=ast.parse((D/'consumer_owned.py').read_text());main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
  self.assertTrue(any(isinstance(n,ast.Raise) and ast.unparse(n.exc)=="SystemExit(1 if summary['status'] == 'FAIL_EXACT_REFERENCE' else 2)" for n in ast.walk(main)))
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--baseline',type=pathlib.Path,required=True);args,rest=parser.parse_known_args();BASE=args.baseline
 unittest.main(argv=[__file__]+rest)
