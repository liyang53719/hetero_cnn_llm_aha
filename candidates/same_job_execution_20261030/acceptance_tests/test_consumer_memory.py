"""All resource calls mocked. Never changes this test process's actual limits."""
import importlib.util,pathlib,tempfile,types,unittest
from unittest.mock import patch
from test_lifecycle import m,D
spec=importlib.util.spec_from_file_location('test_memory',D/'consumer_memory.py');cm=importlib.util.module_from_spec(spec);spec.loader.exec_module(cm)
class Tests(unittest.TestCase):
 def setUp(self):cm._ACTIVE=None
 def test_soft_then_hard_and_child_ceiling(self):
  with patch.object(cm.resource,'getrlimit',return_value=(4<<30,4<<30)),patch.object(cm.resource,'setrlimit')as setter,patch.object(cm,'virtual_bytes',return_value=100<<20):
   r=cm.prepare(512<<20,2<<30);setter.assert_called_once_with(cm.resource.RLIMIT_AS,(512<<20,2<<30));cm.after_popen();self.assertEqual(setter.call_args.args,(cm.resource.RLIMIT_AS,(512<<20,512<<20)));self.assertIs(r['group_rss_is_sampled'],True)
 def test_preparation_already_large_or_insufficient_hard(self):
  for current,hard in [(512<<20,4<<30),(513<<20,4<<30),(100<<20,1<<30)]:
   with patch.object(cm.resource,'getrlimit',return_value=(hard,hard)),patch.object(cm.resource,'setrlimit')as setter,patch.object(cm,'virtual_bytes',return_value=current):
    with self.assertRaises(ValueError):cm.prepare(512<<20,2<<30)
    setter.assert_not_called()
 def test_legacy_no_active_memory_no_limit_change(self):
  with patch.object(cm.resource,'setrlimit')as setter:cm.after_popen();setter.assert_not_called()
 def test_duplicate_prepare_refused(self):
  with patch.object(cm.resource,'getrlimit',return_value=(-1,-1)),patch.object(cm.resource,'setrlimit'),patch.object(cm,'virtual_bytes',return_value=100<<20):
   cm.prepare(512<<20,2<<30)
   with self.assertRaises(ValueError):cm.prepare(512<<20,2<<30)
 def test_popen_failure_still_tightens_cloud_parent(self):
  for active in (None,types.SimpleNamespace(after_popen=unittest.mock.Mock())):
   with tempfile.TemporaryDirectory()as t,patch.object(m,'CLOUD_MEMORY',active),patch.object(m,'sha',return_value='a'*64),patch.object(m.subprocess,'Popen',side_effect=OSError('synthetic failed fork')),patch.object(m,'runtime_abi_module',return_value=types.SimpleNamespace(clean_env=lambda:{})):
    with self.assertRaises(OSError):m.execute(pathlib.Path('/synthetic'),pathlib.Path('/runtime'),pathlib.Path('/out'),pathlib.Path(t)/'log',{'max_active_cycles':1})
    if active is not None:active.after_popen.assert_called_once_with()
 def test_successful_popen_tightening_error_still_reaps(self):
  proc=types.SimpleNamespace(pid=71,poll=lambda:None,kill=unittest.mock.Mock(),wait=unittest.mock.Mock())
  memory=types.SimpleNamespace(after_popen=unittest.mock.Mock(side_effect=OSError('synthetic setrlimit failure')))
  with tempfile.TemporaryDirectory()as t,patch.object(m,'CLOUD_MEMORY',memory),patch.object(m,'sha',return_value='a'*64),patch.object(m.subprocess,'Popen',return_value=proc),patch.object(m,'runtime_abi_module',return_value=types.SimpleNamespace(clean_env=lambda:{})):
   with self.assertRaisesRegex(OSError,'setrlimit'):m.execute(pathlib.Path('/synthetic'),pathlib.Path('/runtime'),pathlib.Path('/out'),pathlib.Path(t)/'log',{'max_active_cycles':1})
   memory.after_popen.assert_called_once_with();proc.kill.assert_called_once_with();proc.wait.assert_called_once_with()
if __name__=='__main__':unittest.main()
