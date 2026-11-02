"""Real E mode/cloud join, synthetic pinned N authority. No execution or actual approval."""
import copy,json,pathlib,unittest
import test_stage_coverage as stage
D=pathlib.Path(__file__).resolve().parent
class FirstFault(unittest.TestCase):
 def setUp(self):
  self.s=stage.Stage();self.s.setUp();self.addCleanup(self.s.tearDown)
  s=self.s;self.b=s.b;self.doc=s.doc;self.ap=s.ap
  for obj,key in ((self.b,'stage_coverage_budget'),(self.doc,'stage_coverage_budget'),(self.ap,'stage_coverage_budget_sha256')):obj.pop(key)
  art=s.h.put('ff_artifact',dict(schema=s.cloud.FIRST_FAULT_SCHEMA,status='UNREVIEWED_MODEL_BUILD'))
  rev=s.h.put('ff_review',dict(schema='MODEL_CANDIDATE_FIRST_FAULT_REVIEW_V1',synthetic=True))
  self.b.update(execution_mode=s.mode.FIRST_FAULT,artifact_manifest=art,model_candidate_review=rev,profiles=list(range(5)))
  self.doc.update(execution_mode=s.mode.FIRST_FAULT,artifact_manifest_sha256=art['sha256'],model_candidate_review=rev,resource_scope='CURRENT_HOST_P0_FIRST_FAULT_DIAGNOSTIC',runtime_mode='IMPORT_EXISTING_PINNED_RUNTIME',archive_mode='READ_EXISTING_PINNED_ARCHIVES',runtime_reuse_manifest=s.h.put('reuse',{'synthetic':True}))
  self.ap.update(purpose=s.mode.FIRST_FAULT,artifact_manifest_sha256=art['sha256'],model_candidate_review_sha256=rev['sha256'])
  helper=s.e/'numeric/candidate_admission.py';helper.write_text("def verify(p,b):\n if not b.get('execution_approval'):raise ValueError('authority')\n return dict(scope='P0_FIRST_FAULT_READONLY_SAME_FULL_M128_STIMULUS_NOT_NUMERICAL_ACCEPTANCE',artifact_manifest_sha256=b['artifact_manifest']['sha256'])\n")
  contract=s.e/'numeric/p0_first_fault_contract.py';contract.write_text("# SYNTHETIC AUTHORITY DOUBLE, not the real N verifier\nimport json\ndef verify_document(b,r):\n return dict(doc_sha='d'*64,watchdog=b['synthetic_watchdog'],diagnostic_profiles=[0],scope='P0_FIRST_FAULT_READONLY_SAME_FULL_M128_STIMULUS_NOT_NUMERICAL_ACCEPTANCE')\ndef admit(b):\n if not b.get('execution_approval') or not b.get('cloud_budget'):raise ValueError('authority')\n return verify_document(b,{})\n")
  self.b['synthetic_watchdog']=dict(wall_seconds=1001,max_active_cycles=123456)
  self.b['pins']={str(p):s.mode.sha(p)for p in s.e.rglob('*.py')};s.h.reapprove()
 def test_actual_E_join_selected0_not_legacy_placeholder(self):
  s=self.s;a=s.mode.admit(self.b)
  self.assertEqual(a,dict(mode=s.mode.FIRST_FAULT,profile_seconds={'0':1001},profile_max_active_cycles={'0':123456},reviewed_budget_sha256='d'*64,diagnostic_profiles=[0]))
  self.assertEqual(s.cloud.admit(self.b)['diagnostic_profiles'],[0]);self.assertEqual(s.mode.transport_exit(s.mode.FIRST_FAULT,dict(numerical_pass=True)),2)
  for i in (1,2,3,4,True,False,'0'):
   with self.subTest(profile=i),self.assertRaises((ValueError,KeyError)):s.mode.consumer_limits(dict(wall_seconds=18000,max_active_cycles=10**9),a,i)
  self.assertEqual(s.mode.consumer_limits(dict(wall_seconds=18000,max_active_cycles=10**9),a,0),dict(wall_seconds=1001,max_active_cycles=123456))
 def test_no_budget_defaults_and_original_caps(self):
  for k,v in [('wall_seconds',None),('wall_seconds',True),('wall_seconds',0),('wall_seconds',18001),('max_active_cycles',10**9+1)]:
   old=self.b['synthetic_watchdog'][k];self.b['synthetic_watchdog'][k]=v
   with self.subTest(k=k,v=v),self.assertRaises(ValueError):self.s.mode.admit(self.b)
   self.b['synthetic_watchdog'][k]=old
 def test_reject_other_registered_or_selected(self):
  for v in ([False],[1],[0,0],[0,1],[]):
   self.b['diagnostic_profiles']=v
   with self.subTest(v=v),self.assertRaises(ValueError):self.s.mode.admit(self.b)
  self.b.pop('diagnostic_profiles');self.b['profiles']=[0]
  with self.assertRaises(ValueError):self.s.mode.admit(self.b)
 def test_first_fault_missing_real_authority_rejected_pure_separate(self):
  del self.b['execution_approval']
  with self.assertRaises(ValueError):self.s.mode.admit(self.b)
  with self.assertRaises(ValueError):self.s.mode.first_fault_admission(self.b)
  self.assertEqual(self.s.mode.first_fault_document(self.b,{'synthetic_pure':True})['diagnostic_profiles'],[0])
 def test_old_artifact_or_review_cannot_authorize(self):
  for field,doc in [('artifact_manifest',dict(schema=self.s.cloud.MODEL_SCHEMA,status='UNREVIEWED_MODEL_BUILD')),('model_candidate_review',dict(schema='MODEL_CANDIDATE_REVIEW_V1'))]:
   old=self.b[field];self.b[field]=self.s.h.put('wrong_'+field,doc)
   with self.subTest(field=field),self.assertRaises(ValueError):self.s.cloud.admit(self.b)
   self.b[field]=old
 def test_new_artifact_cannot_enter_old_modes(self):
  for mode in (self.s.mode.CALIBRATION,self.s.mode.STAGE,self.s.mode.FULL):
   self.b['execution_mode']=mode
   with self.subTest(mode=mode),self.assertRaises(ValueError):self.s.cloud.admit(self.b)
 def test_no_fresh_download_path(self):
  self.doc.update(runtime_mode='FRESH_ORIGINAL_RUNTIME_INSTALL',archive_mode='DOWNLOAD_ORIGINAL_ARCHIVES',runtime_reuse_manifest=None);self.s.h.reapprove()
  with self.assertRaisesRegex(ValueError,'first fault requires original'):self.s.cloud.admit(self.b)
 def test_new_mode_same_two_reuse_approval_and_cap(self):
  for k in ('p0_provider_reuse','reference_data_reuse'):
   row=self.s.h.put(k,{'synthetic':True});self.b[k]=row;self.doc[k]=row;self.ap[k+'_sha256']=row['sha256']
  self.doc['aggregate_tree_cap_bytes']=12037043872;self.s.h.reapprove()
  a=self.s.cloud.admit(self.b);self.assertEqual(a['aggregate_tree_cap_bytes'],12037043872)
  self.ap['reference_data_reuse_sha256']='0'*64;self.s.h.reapprove()
  with self.assertRaises(ValueError):self.s.cloud.admit(self.b)
 def test_mode_purpose_resource_scope_and_reservations(self):
  for key,value in [('execution_mode',self.s.mode.CALIBRATION),('resource_scope','CURRENT_HOST_STAGE_COVERAGE_DIAGNOSTIC'),('reserved_other_owner_bytes',0),('dut_rss_bytes',3<<30)]:
   original=self.doc[key];self.doc[key]=value;self.s.h.reapprove()
   with self.subTest(key=key),self.assertRaises(ValueError):self.s.cloud.admit(self.b)
   self.doc[key]=original;self.s.h.reapprove()
 def test_no_full_or_stage_budget(self):
  for k,v in [('full_block_budget',{}),('stage_coverage_budget',None)]:
   self.b[k]=v
   with self.subTest(k=k),self.assertRaises(ValueError):self.s.cloud.admit(self.b)
   self.b.pop(k)
 def test_source_lock_not_bypassable(self):
  for p in (self.s.e/'execution_mode.py',self.s.e/'numeric/p0_first_fault_contract.py',self.s.e/'profile_policy.py'):
   old=self.b['pins'][str(p)];self.b['pins'][str(p)]='0'*64
   with self.subTest(p=p.name),self.assertRaises(ValueError):self.s.mode.admit(self.b)
   self.b['pins'][str(p)]=old
if __name__=='__main__':unittest.main()
