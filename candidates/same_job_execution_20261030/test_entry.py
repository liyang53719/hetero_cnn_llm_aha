import importlib.util,json,pathlib,tempfile,unittest
P=pathlib.Path;D=P(__file__).resolve().parent
def module(n):
 s=importlib.util.spec_from_file_location(n,D/(n+'.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
m=module('summarize_same_job')
class T(unittest.TestCase):
 def test_absent_is_incomplete(self):
  with tempfile.TemporaryDirectory()as d:
   r=m.summarize(P(d)/'work',{});self.assertFalse(r['numeric_pass']);self.assertEqual(r['actual_dut_reports'],[]);self.assertLess(len(m.encode(r).encode()),65536)
 def test_no_go_reason(self):
  with tempfile.TemporaryDirectory()as d:
   p=P(d);(p/'work-CONTROLLER_FAILURE.json').write_text(json.dumps({'reason_code':'CPU_AVX512'}));self.assertEqual(m.summarize(p/'work',{})['failure_reason'],'CPU_AVX512')
 def test_no_path_or_pid_echo(self):
  with tempfile.TemporaryDirectory()as d:
   p=P(d)/'work/materials/numeric/runs/p0_dut';p.mkdir(parents=True);(p/'RESULT.json').write_text(json.dumps({'native_exit':2,'errors':[],'argv':['/private/secret'],'owner_identity':{'pid':4321},'cleanup_proof':None,'log_capture':None,'elapsed_seconds':1}));r=m.summarize(P(d)/'work',{});s=m.encode(r);self.assertNotIn('/private',s);self.assertNotIn('4321',s);self.assertFalse(r['stages'][0]['cleanup_complete'])
 def test_unverified_start_not_claimed(self):
  with tempfile.TemporaryDirectory()as d:
   p=P(d)/'work/materials/numeric';p.mkdir(parents=True);(p/'PROFILE_0_DIAGNOSTIC.json').write_text(json.dumps({'profile':0,'state':'arbitrary','numerical_pass':False}));self.assertEqual(m.summarize(P(d)/'work',{})['actual_dut_reports'],[])
 def test_budget_real_algorithm(self):
  s=importlib.util.spec_from_file_location('flow_entry',D/'controller/flow.py');f=importlib.util.module_from_spec(s);s.loader.exec_module(f);self.assertEqual(f.reservations({'budgets':json.loads((D/'BUDGETS.json').read_text())}),(6090,6210,19500))
 def test_materializer_is_directory(self):
  s=(D/'prepare_and_run.py').read_text();self.assertIn("materializer=str(repo/'candidates/same_job_materialization_20261029')",s);self.assertNotIn("materializer=str(repo/'candidates/same_job_materialization_20261029/prepare.py')",s)
if __name__=='__main__':unittest.main()
