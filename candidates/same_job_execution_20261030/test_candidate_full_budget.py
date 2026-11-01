"""ALL_SYNTHETIC watchdog tests. Cloud resource admission is mocked explicitly;
candidate review/approval/artifact verifier and original full budget gates are real.
No live identity, calibration result, hardware execution or permission is produced.
"""
import ast,copy,hashlib,importlib.machinery,importlib.util,json,pathlib,sys,tempfile,unittest
from unittest.mock import patch
import execution_mode as mode
E=pathlib.Path(mode.D)
sys.path.insert(0,str(E/'numeric'))
from test_candidate_admission import Test as ReviewFixture
import profile_policy
class CandidateBudgetTests(unittest.TestCase):
 def setUp(self):
  self.fixture=ReviewFixture();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
  f=self.fixture;self.rp=f.write('review.json',f.r)
  self.b=dict(execution_context='CLOUD_EXECUTOR_V1',execution_mode=mode.FULL,execution_policy=profile_policy.policy(),model_candidate_review=self.rp,artifact_manifest=f.fp,identity=dict(source_commit='d'*40,execution_id='ALL_SYNTHETIC'),pins={str(E/'cloud_budget.py'):mode.sha(E/'cloud_budget.py'),str(E/'numeric/candidate_admission.py'):mode.sha(E/'numeric/candidate_admission.py')})
  self.b['cloud_budget']=f.write('cloud.json',dict(model_candidate_review=self.rp))
  self.approval=dict(schema='OPERATOR_REVIEWED_CLOUD_INVOCATION_V1',approved=True,authority='USER_AUTHORIZED_OPERATOR_REVIEW',model_candidate_review_sha256=self.rp['sha256'],budget_sha256=self.b['cloud_budget']['sha256'],source_commit='d'*40,execution_id='ALL_SYNTHETIC',artifact_manifest_sha256=f.fp['sha256'])
  self.b['execution_approval']=f.write('approval.json',self.approval)
  evidence=f.write('basis.json',{'ALL_SYNTHETIC':True,'artifact_manifest_sha256':f.fp['sha256'],'model_candidate_review_sha256':self.rp['sha256'],'candidate_scope':'MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL'})
  self.doc=dict(schema='MODEL_CANDIDATE_FIVE_M128_FULL_EXECUTION_BUDGET_V1',ready=True,scope='WATCHDOG_ADMISSION_ONLY_NOT_NUMERICAL_ACCEPTANCE',tokens=128,matrix_macs=4096,vector_lanes=32,artifact_manifest_sha256=f.fp['sha256'],model_candidate_review_sha256=self.rp['sha256'],driver_sha256=mode.sha(E.parent/'moe_router_score_observation_20261030/driver/host_axi_driver_non_dpi.cpp'),basis=dict(calibration_summary=evidence,independent_budget_review=evidence),profiles={str(i):dict(wall_seconds=500,max_active_cycles=100000,estimated_complete_active_cycles=90000,estimated_required_wall_seconds=450)for i in range(5)})
 def admit(self,doc=None):
  self.b['full_block_budget']=self.fixture.write('full.json',doc or self.doc)
  original=importlib.machinery.SourceFileLoader.exec_module
  def load(loader,module):
   original(loader,module)
   if pathlib.Path(module.__file__).resolve()==(E/'cloud_budget.py').resolve():
    module.admit=lambda binding:dict(execution_mode=mode.FULL,full_block_budget=binding['full_block_budget'])
  with patch.object(importlib.machinery.SourceFileLoader,'exec_module',load):return mode.admit(self.b)
 def test_adapter_only_nine_reviewed_exact_allowlist_additions(self):
  tree=ast.parse((E/'executor_adaptation.py').read_text())
  assignments=[n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name)and t.id=='ALLOWED_PATHS'for t in n.targets)]
  self.assertEqual(len(assignments),1)
  added={'execution_mode.py','test_candidate_full_budget.py','test_disk_receipt.py','numeric/test_contract_domains.py','evidence/contract_domain_20261101/ACTUAL_PURE_CHAIN_SAFE_RESULT.json','evidence/contract_domain_20261101/PURE_CHAIN_README.md','evidence/contract_domain_20261101/reproduce_pure_chain.py','numeric/candidate_observation_contract.py','numeric/test_candidate_observation_contract.py'}
  tuples=[n for n in ast.walk(assignments[0])if isinstance(n,ast.Tuple)and added <= {x.value for x in n.elts if isinstance(x,ast.Constant)}]
  self.assertEqual(len(tuples),1)
  for value in added:self.assertEqual(sum(isinstance(n,ast.Constant)and n.value==value for n in tuples[0].elts),1)
  tuples[0].elts=[n for n in tuples[0].elts if not(isinstance(n,ast.Constant)and n.value in added)]
  self.assertEqual(hashlib.sha256(ast.dump(tree,include_attributes=False).encode()).hexdigest(),'81c08ee3bc416eb53e3997933461c99639c500681002b9096a4b4e4368479bff')
  tuples[0].elts.append(ast.Constant(value='UNREVIEWED_EXTRA_ALLOWED_PATH.py'))
  self.assertNotEqual(hashlib.sha256(ast.dump(tree,include_attributes=False).encode()).hexdigest(),'81c08ee3bc416eb53e3997933461c99639c500681002b9096a4b4e4368479bff')
 def test_real_candidate_review_join(self):
  out=self.admit();self.assertEqual(out['profile_seconds'],dict.fromkeys(map(str,range(5)),500));self.assertEqual(set(out),{'mode','profile_seconds','profile_max_active_cycles','reviewed_budget_sha256'});self.assertIsNone(mode.ACCEPTED_FULL_ADMISSION_SHA256)
 def test_legacy_baseline_cannot_authorize_candidate(self):
  d=copy.deepcopy(self.doc);d['schema']='FIVE_M128_FULL_EXECUTION_BUDGET_V1';del d['artifact_manifest_sha256'];del d['model_candidate_review_sha256'];d['hardware_baseline_sha256']=mode.sha(E.parent/'ci_frontend_materialization_r2_20261029/OBSERVER_BASELINE_ACCEPTANCE.json')
  with self.assertRaisesRegex(ValueError,'no legacy baseline'):self.admit(d)
 def test_artifact_and_review_cross_join(self):
  for key in ('artifact_manifest_sha256','model_candidate_review_sha256'):
   with self.subTest(key=key):
    d=copy.deepcopy(self.doc);d[key]='0'*64
    with self.assertRaises(ValueError):self.admit(d)
 def test_real_approval_and_review_checked(self):
  self.approval['model_candidate_review_sha256']='0'*64;self.b['execution_approval']=self.fixture.write('approval.json',self.approval)
  with self.assertRaisesRegex(ValueError,'review independently pinned'):self.admit()
 def test_missing_review_rejects(self):
  del self.b['model_candidate_review']
  with self.assertRaises((ValueError,KeyError,TypeError)):self.admit()
 def test_verifier_pin_mismatch(self):
  self.b['pins'][str(E/'numeric/candidate_admission.py')]='0'*64
  with self.assertRaisesRegex(ValueError,'verifier source pin'):self.admit()
 def test_real_review_artifact_byte_drift(self):
  pathlib.Path(self.fixture.cp['path']).write_text('{}')
  with self.assertRaises(ValueError):self.admit()
 def test_unchanged_limits_and_allfive(self):
  for field,value in [('wall_seconds',18001),('max_active_cycles',1000000001),('estimated_complete_active_cycles',100001),('wall_seconds',True)]:
   d=copy.deepcopy(self.doc);d['profiles']['4'][field]=value
   with self.subTest(field=field),self.assertRaises(ValueError):self.admit(d)
  d=copy.deepcopy(self.doc);del d['profiles']['4']
  with self.assertRaises(ValueError):self.admit(d)
 def test_old_calibration_or_wrong_scope_not_new_rate_evidence(self):
  for key,value in [('artifact_manifest_sha256','0'*64),('model_candidate_review_sha256','0'*64),('candidate_scope','LEGACY')]:
   original=json.loads(pathlib.Path(self.doc['basis']['calibration_summary']['path']).read_text());original[key]=value
   d=copy.deepcopy(self.doc);d['basis']['calibration_summary']=self.fixture.write('wrong_basis.json',original)
   with self.subTest(key=key),self.assertRaisesRegex(ValueError,'calibration provenance'):self.admit(d)
 def test_new_schema_cannot_run_samejob(self):
  self.b.pop('execution_context');self.b['full_block_budget']=self.fixture.write('full.json',self.doc)
  with self.assertRaisesRegex(ValueError,'PENDING'):mode.admit(self.b)
 def test_candidate_looks_legacy_but_review_exists_rejected(self):
  self.b['artifact_manifest']=self.fixture.write('legacy.json',{'schema':'FROZEN_FIVE_PROFILE_DUT_ARTIFACT_V2'})
  with self.assertRaisesRegex(ValueError,'cannot use legacy'):self.admit()
if __name__=='__main__':unittest.main()
