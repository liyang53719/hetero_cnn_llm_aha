"""Real mode/cloud join with synthetic signed files and mock review authority; no execution."""
import copy,importlib.util,json,pathlib,shutil,unittest
from unittest.mock import patch
import test_cloud_budget as old
D=pathlib.Path(__file__).resolve().parent
class Stage(unittest.TestCase):
 def setUp(self):
  self.h=old.Budget();self.h.setUp();self.b=self.h.b;self.doc=self.h.doc;self.ap=self.h.ap
  self.e=self.h.d/'candidates/E';self.e.mkdir(parents=True);(self.e/'numeric').mkdir()
  for n in ('execution_mode.py','cloud_budget.py','profile_policy.py'):shutil.copyfile(D/n,self.e/n)
  helper=self.e/'numeric/candidate_admission.py';helper.write_text("def verify(p,b):\n if p.get('sha256')!=b['model_candidate_review']['sha256']:raise ValueError('review')\n return dict(scope='MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL',artifact_manifest_sha256=b['artifact_manifest']['sha256'])\n")
  driver=self.e.parent/'moe_router_score_observation_20261030/driver/host_axi_driver_non_dpi.cpp';driver.parent.mkdir(parents=True);driver.write_text('synthetic driver')
  self.mode=self.load('execution_mode.py');self.cloud=self.load('cloud_budget.py')
  art=self.h.put('artifact',dict(schema='MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1',status='UNREVIEWED_MODEL_BUILD'))
  rev=self.h.put('candidate_review',{'synthetic_mock_authority':True});ev=self.h.put('budget_review',{'synthetic_mock_authority':True})
  self.b.update(execution_mode=self.mode.STAGE,artifact_manifest=art,model_candidate_review=rev,full_block_budget=None,pins={str(p):self.mode.sha(p)for p in self.e.rglob('*.py')})
  self.doc.update(execution_mode=self.mode.STAGE,artifact_manifest_sha256=art['sha256'],model_candidate_review=rev,resource_scope='CURRENT_HOST_STAGE_COVERAGE_DIAGNOSTIC')
  self.ap.update(purpose=self.mode.STAGE,artifact_manifest_sha256=art['sha256'],model_candidate_review_sha256=rev['sha256'])
  self.summary=dict(schema='CLOUD_EXECUTION_SAFE_SUMMARY_V1',status='VERIFIED_REAGGREGATED',execution_mode='BOUNDED_CALIBRATION',transport_exit_code=2,profiles=[{'profile':i,'state':'STARTED_TIMEOUT_INCOMPLETE'}for i in range(5)],artifact_manifest_sha256=art['sha256'],model_candidate_review_sha256=rev['sha256'],candidate_scope='MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL')
  self.stage=dict(schema='MODEL_CANDIDATE_STAGE_COVERAGE_BUDGET_V1',ready=True,scope=self.mode.STAGE_SCOPE,tokens=128,matrix_macs=4096,vector_lanes=32,driver_sha256=self.mode.sha(driver),artifact_manifest_sha256=art['sha256'],model_candidate_review_sha256=rev['sha256'],basis=dict(calibration_summary=self.h.put('cal',self.summary),independent_budget_review=ev),profiles={str(i):dict(wall_seconds=601+i,max_active_cycles=100000+i,target_completed_commands=1)for i in range(5)})
  self.reapprove()
 def load(self,n):
  spec=importlib.util.spec_from_file_location('synthetic_'+n,self.e/n);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
 def reapprove(self):
  row=self.h.put('stage_budget',self.stage);self.b['stage_coverage_budget']=row;self.doc['stage_coverage_budget']=row;self.ap['stage_coverage_budget_sha256']=row['sha256'];self.h.reapprove()
 def tearDown(self):self.h.tearDown()
 def test_real_join(self):
  a=self.mode.admit(self.b);self.assertEqual(a['profile_seconds']['4'],605);self.assertEqual(self.cloud.admit(self.b)['stage_coverage_budget'],self.b['stage_coverage_budget'])
  self.assertEqual(self.mode.transport_exit(self.mode.STAGE,{'numerical_pass':True}),2)
  self.assertEqual(self.mode.consumer_limits(dict(wall_seconds=20000,max_active_cycles=10**9),a,0),dict(wall_seconds=601,max_active_cycles=100000))
 def test_targets_windows_cycles_exact(self):
  original=copy.deepcopy(self.stage)
  for k,v in [('wall_seconds',18001),('wall_seconds',True),('max_active_cycles',10**9+1),('target_completed_commands',257),('target_completed_commands',0)]:
   self.stage=copy.deepcopy(original);self.stage['profiles']['0'][k]=v;self.reapprove()
   with self.subTest(k=k,v=v),self.assertRaises(ValueError):self.mode.admit(self.b)
 def test_missing_profile_or_full_estimate(self):
  del self.stage['profiles']['4'];self.reapprove()
  with self.assertRaises(ValueError):self.mode.admit(self.b)
  self.stage['profiles']['4']=dict(self.stage['profiles']['0'],estimated_complete_active_cycles=1);self.reapprove()
  with self.assertRaises(ValueError):self.mode.admit(self.b)
 def test_wrong_review_artifact_driver_or_scope(self):
  original=copy.deepcopy(self.stage)
  for k in ('model_candidate_review_sha256','artifact_manifest_sha256','driver_sha256','scope'):
   self.stage=copy.deepcopy(original);self.stage[k]='wrong';self.reapprove()
   with self.subTest(k=k),self.assertRaises(ValueError):self.mode.admit(self.b)
 def test_no_legacy_or_noncloud_fallback(self):
  self.b['execution_context']='CI'
  with self.assertRaises(ValueError):self.mode.admit(self.b)
  self.b['execution_context']='CLOUD_EXECUTOR_V1';self.b['execution_mode']=self.mode.CALIBRATION
  with self.assertRaises(ValueError):self.mode.admit(self.b)
 def test_approval_and_resource_caps(self):
  self.ap['stage_coverage_budget_sha256']='0'*64;self.h.reapprove()
  with self.assertRaises(ValueError):self.mode.admit(self.b)
  self.reapprove();self.doc['stage_resources']['install']['rss_bytes']=3<<30;self.h.reapprove()
  with self.assertRaises(ValueError):self.mode.admit(self.b)
 def test_unverified_or_partial_calibration(self):
  self.summary['profiles'].pop();self.stage['basis']['calibration_summary']=self.h.put('cal',self.summary);self.reapprove()
  with self.assertRaises(ValueError):self.mode.admit(self.b)
 def test_no_full_budget_or_missing_stage(self):
  self.b['full_block_budget']={}
  with self.assertRaises(ValueError):self.mode.admit(self.b)
  self.b['full_block_budget']=None;del self.b['stage_coverage_budget']
  with self.assertRaises((ValueError,KeyError)):self.mode.admit(self.b)
 def test_legacy_mode_windows_and_full_pending_unchanged(self):
  cal=self.mode.admit(dict(calibration_seconds={str(i):300 for i in range(5)}))
  self.assertEqual(cal['mode'],self.mode.CALIBRATION);self.assertIsNone(cal['reviewed_budget_sha256'])
  self.assertEqual(self.mode.transport_exit(self.mode.CALIBRATION,{}),2)
  for value in (0,True,20001):
   with self.assertRaises(ValueError):self.mode.admit(dict(calibration_seconds={str(i):value for i in range(5)}))
  with self.assertRaises(ValueError):self.mode.admit(dict(execution_mode=self.mode.FULL))
 def test_legacy_cloud_301_still_rejected(self):
  h=old.Budget();h.setUp()
  try:
   h.doc['budgets']['calibration_seconds']['0']=301;h.reapprove()
   with self.assertRaisesRegex(ValueError,'up-to300'):self.cloud.admit(h.b)
  finally:h.tearDown()
 def test_source_pin_drift(self):
  self.b['pins'][str(self.e/'execution_mode.py')]='0'*64
  with self.assertRaisesRegex(ValueError,'source pin'):self.mode.admit(self.b)
 def test_wrong_purpose_scope_and_dut_caps(self):
  self.ap['purpose']='FULL_BLOCK_ACCEPTANCE';self.h.reapprove()
  with self.assertRaises(ValueError):self.mode.admit(self.b)
  self.ap['purpose']=self.mode.STAGE;self.doc['resource_scope']='FULL_BLOCK_MEASURED_RESOURCE_PLAN';self.h.reapprove()
  with self.assertRaises(ValueError):self.mode.admit(self.b)
  self.doc['resource_scope']='CURRENT_HOST_STAGE_COVERAGE_DIAGNOSTIC';self.doc['dut_rss_bytes']=3<<30;self.h.reapprove()
  with self.assertRaises(ValueError):self.mode.admit(self.b)
 def test_effective_original_limits_not_expanded(self):
  a=self.mode.admit(self.b)
  for original in (dict(wall_seconds=600,max_active_cycles=10**9),dict(wall_seconds=20000,max_active_cycles=99999)):
   with self.assertRaises(ValueError):self.mode.consumer_limits(original,a,0)
 def test_calibration_must_be_closed_and_original_mode(self):
  original=copy.deepcopy(self.summary)
  for state in ('UNAVAILABLE','NOT_STARTED','RUNNING','STARTED_OBSERVATION_INCOMPLETE',None):
   self.summary=copy.deepcopy(original);self.summary['profiles'][0]['state']=state
   self.stage['basis']['calibration_summary']=self.h.put('cal',self.summary);self.reapprove()
   with self.subTest(state=state),self.assertRaisesRegex(ValueError,'closed terminal'):self.mode.admit(self.b)
  self.summary=copy.deepcopy(original);self.summary['execution_mode']=self.mode.STAGE
  self.stage['basis']['calibration_summary']=self.h.put('cal',self.summary);self.reapprove()
  with self.assertRaisesRegex(ValueError,'original bounded calibration'):self.mode.admit(self.b)
 def test_five_profile_policy_and_source_required(self):
  policy=self.load('profile_policy.py');self.b['execution_policy']=policy.policy(policy.DEFER)
  with self.assertRaisesRegex(ValueError,'all five original-host'):self.mode.admit(self.b)
  self.b['execution_policy']=policy.policy();self.b['pins'][str(self.e/'profile_policy.py')]='0'*64
  with self.assertRaisesRegex(ValueError,'policy source pin'):self.mode.admit(self.b)
 def test_p0_reuse_pin_exact_stage_only(self):
  row=self.h.put('p0_reuse',{'synthetic_metadata_only':True});self.b['p0_provider_reuse']=row;self.doc['p0_provider_reuse']=row;self.ap['p0_provider_reuse_sha256']=row['sha256'];self.reapprove()
  self.assertEqual(self.cloud.admit(self.b)['p0_provider_reuse'],row)
  self.ap['p0_provider_reuse_sha256']='0'*64;self.h.reapprove()
  with self.assertRaisesRegex(ValueError,'approved exact p0_provider_reuse'):self.mode.admit(self.b)
 def test_p0_reuse_legacy_rejected(self):
  h=old.Budget();h.setUp()
  try:
   h.b['p0_provider_reuse']=h.put('p0',{})
   with self.assertRaisesRegex(ValueError,'P0 provider reuse requires stage'):self.cloud.admit(h.b)
  finally:h.tearDown()
if __name__=='__main__':unittest.main()
