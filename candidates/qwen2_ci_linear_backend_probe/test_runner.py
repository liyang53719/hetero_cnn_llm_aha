import unittest
from unittest.mock import patch
from . import runner,parser
class SummaryTests(unittest.TestCase):
 def value(self):
  return dict(schema=1,status='OBSERVED',synthetic_only=True,numeric_acceptance_claimed=False,cases=[dict(mode=m,execution='COMPLETED',observation=parser.parse('')) for m in runner.MODES])
 def test_no_log_not_fallback(self):
  r=runner.checked(self.value());self.assertTrue(all(c['observation']['backend']=='UNDETERMINED' for c in r['cases']))
 def test_reject_payload(self):
  r=self.value();r['cases'][0]['observation']['path']='private'
  with self.assertRaises(ValueError):runner.checked(r)
 def test_wrong_mode(self):
  r=self.value();r['cases'][0]['mode']='other'
  with self.assertRaises(ValueError):runner.checked(r)
 def test_wrong_terminal(self):
  r=self.value();r['cases'][0]['execution']='TIMEOUT'
  with self.assertRaises(ValueError):runner.checked(r)
 def test_bool_schema(self):
  r=self.value();r['schema']=True
  with self.assertRaises(ValueError):runner.checked(r)
 def test_no_undeclared_backend_override(self):
  with patch.dict(runner.os.environ,{'MKL_CBWR':'AVX2'}):
   with self.assertRaises(ValueError):runner.run_case('enabled',None)

class ChildTests(unittest.TestCase):
 def run_child(self,code,**limits):
  import tempfile,subprocess
  from pathlib import Path
  original=subprocess.Popen
  def spawn(*args,**kwargs):return original([runner.sys.executable,'-c',code],**kwargs)
  with tempfile.TemporaryDirectory() as d,patch.object(runner.subprocess,'Popen',side_effect=spawn),patch.multiple(runner,STOP=False,**limits):
   return runner.run_case('enabled',Path(d))
 def test_real_fake_success(self):
  r=self.run_child("print('{\"schema\":1,\"status\":\"SYNTHETIC_LINEAR_COMPLETED\",\"mode\":\"enabled\"}')")
  self.assertEqual(r['execution'],'COMPLETED');self.assertEqual(r['observation']['backend'],'UNDETERMINED')
 def test_real_fake_missing_receipt(self):
  self.assertEqual(self.run_child('pass')['execution'],'FAILED')
 def test_real_fake_error(self):
  self.assertEqual(self.run_child('raise SystemExit(2)')['execution'],'FAILED')
 def test_real_fake_timeout(self):
  self.assertEqual(self.run_child('import time;time.sleep(5)',LIMIT_SECONDS=.05)['execution'],'TIMEOUT')
 def test_real_fake_log_limit(self):
  self.assertEqual(self.run_child("print('x'*4096)",MAX_LOG=128)['execution'],'LOG_LIMIT')
