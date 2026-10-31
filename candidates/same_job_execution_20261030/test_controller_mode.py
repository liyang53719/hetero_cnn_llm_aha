"""Source-only controller admission tests; no native runtime or DUT."""
import importlib.util,pathlib,tempfile,types,unittest,json,hashlib
D=pathlib.Path(__file__).parent
spec=importlib.util.spec_from_file_location('prepare',D/'prepare_and_run.py');p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
class Tests(unittest.TestCase):
 def test_calibration_default(self):self.assertEqual(p.execution_request(types.SimpleNamespace()),{'execution_mode':'BOUNDED_CALIBRATION'})
 def test_full_missing_never_defaults300(self):
  with self.assertRaises(ValueError):p.execution_request(types.SimpleNamespace(execution_mode='FULL_BLOCK_ACCEPTANCE'))
 def test_calibration_rejects_full_budget(self):
  with self.assertRaises(ValueError):p.execution_request(types.SimpleNamespace(full_block_budget=pathlib.Path('/tmp/no-file')))
 def test_pinned_input_not_approval(self):
  with tempfile.TemporaryDirectory()as t:
   q=pathlib.Path(t)/'budget.json';q.write_text('{"reviewed":false}')
   a=types.SimpleNamespace(execution_mode='FULL_BLOCK_ACCEPTANCE',full_block_budget=q,full_block_budget_sha256=hashlib.sha256(q.read_bytes()).hexdigest())
   r=p.execution_request(a);self.assertEqual(r['full_block_budget']['sha256'],a.full_block_budget_sha256) # only pinned input; admission must reject unreviewed data
   a.full_block_budget_sha256='a'*64
   with self.assertRaises(ValueError):p.execution_request(a)
 def test_symlink_rejected(self):
  with tempfile.TemporaryDirectory()as t:
   q=pathlib.Path(t)/'real';q.write_text('{}');link=pathlib.Path(t)/'link';link.symlink_to(q)
   with self.assertRaises(ValueError):p.execution_request(types.SimpleNamespace(execution_mode='FULL_BLOCK_ACCEPTANCE',full_block_budget=link,full_block_budget_sha256=hashlib.sha256(q.read_bytes()).hexdigest()))
spec=importlib.util.spec_from_file_location('flow',D/'controller/flow.py');flow=importlib.util.module_from_spec(spec);spec.loader.exec_module(flow)
class FlowTests(unittest.TestCase):
 def test_transport_not_qualification_from_exit(self):
  self.assertEqual(flow.transport_code('FULL_BLOCK_ACCEPTANCE',{'status':'INCOMPLETE','numerical_pass':False}),2)
  self.assertEqual(flow.transport_code('FULL_BLOCK_ACCEPTANCE',{'status':'FAIL_EXACT_REFERENCE','numerical_pass':False}),1)
  self.assertEqual(flow.transport_code('FULL_BLOCK_ACCEPTANCE',{'status':'PASS_FIVE_FULL128_EXACT_REFERENCE','numerical_pass':True}),0)
  self.assertEqual(flow.transport_code('BOUNDED_CALIBRATION',{'status':'PASS_FIVE_FULL128_EXACT_REFERENCE','numerical_pass':True}),2)
  with self.assertRaises(ValueError):flow.transport_code('FULL_BLOCK_ACCEPTANCE',{'status':'INCOMPLETE','numerical_pass':True})
 def test_exact_whole_job_limit_no_hidden300(self):
  q=dict(archives=600,weights=3600,install=180,owner_bind=120,reference=180,provider=180,build=7200,parent=600,calibration_seconds={str(i):300 for i in range(5)})
  admission={'profile_seconds':{str(i):600 for i in range(5)}}
  self.assertEqual(flow.reservations({'budgets':q},admission)[2],21000)
  admission['profile_seconds']['4']=601
  with self.assertRaises(ValueError):flow.reservations({'budgets':q},admission)
if __name__=='__main__':unittest.main()
