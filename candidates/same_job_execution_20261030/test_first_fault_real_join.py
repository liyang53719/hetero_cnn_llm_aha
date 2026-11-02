"""Real E+N functions and real driver/source bytes; all invocation metadata synthetic.
No mock validators, owner, native execution, or actual admission is claimed.
"""
import copy,importlib.util,json,os,pathlib,shutil,tempfile,unittest
import test_cloud_budget as old
D=pathlib.Path(__file__).resolve().parent
class RealJoin(unittest.TestCase):
 def setUp(self):
  support=pathlib.Path(os.environ.get('FIRST_FAULT_NUMERIC_FIXTURE',str(D/'numeric/test_support_first_fault.py')))
  spec=importlib.util.spec_from_file_location('real_first_fault_fixture',support);self.n=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.n)
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.f=self.n.build(pathlib.Path(self.tmp.name).resolve())
  f=self.f;self.b=f['binding'];e=f['repo']/'candidates/same_job_execution_20261030'
  for name in ('execution_mode.py','cloud_budget.py','profile_policy.py'):shutil.copyfile(D/name,e/name)
  files=[dict(self.n.pin(p),path=str(p.relative_to(f['repo'])))for p in sorted(f['repo'].rglob('*'))if p.is_file()]
  self.b['source_pins']=self.n.put(f['control']/'catalog.json',dict(schema='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1',files=files));self.b['pins']={str(f['repo']/r['path']):r['sha256']for r in files}
  self.mode=self.n.module(e/'execution_mode.py');self.cloud=self.n.module(e/'cloud_budget.py')
  self.h=old.Budget();self.h.setUp();self.addCleanup(self.h.tearDown)
  self.b['identity'].update(boot_id='b',started_monotonic=2,host_identity_sha256=self.h.host['sha256'])
  self.b['profiles']=list(range(5));self.doc=copy.deepcopy(self.h.doc)
  self.doc.update(source_commit=self.b['identity']['source_commit'],host_identity=self.h.host,artifact_manifest_sha256=self.b['artifact_manifest']['sha256'],model_candidate_review=self.b['model_candidate_review'],retained_materials=self.b['retained_materials'],execution_mode=self.mode.FIRST_FAULT,resource_scope='CURRENT_HOST_P0_FIRST_FAULT_DIAGNOSTIC',runtime_mode='IMPORT_EXISTING_PINNED_RUNTIME',archive_mode='READ_EXISTING_PINNED_ARCHIVES',runtime_reuse_manifest=self.h.put('runtime_import',{'synthetic':True}))
  self.ap=copy.deepcopy(self.h.ap);self.ap.update(source_commit=self.b['identity']['source_commit'],execution_id=self.b['identity']['execution_id'],host_identity_sha256=self.b['identity']['host_identity_sha256'],artifact_manifest_sha256=self.b['artifact_manifest']['sha256'],model_candidate_review_sha256=self.b['model_candidate_review']['sha256'],retained_materials_sha256=self.b['retained_materials']['sha256'],purpose=self.mode.FIRST_FAULT)
  self.approve()
 def approve(self):
  self.b['cloud_budget']=self.n.put(self.f['control']/'complete_cloud_budget.json',self.doc);self.ap['budget_sha256']=self.b['cloud_budget']['sha256'];self.b['execution_approval']=self.n.put(self.f['control']/'complete_approval.json',self.ap)
 def test_real_E_N_approved_chain_no_mock(self):
  actual=self.mode.admit(self.b)
  self.assertEqual(actual['profile_seconds'],{'0':self.f['doc']['watchdog']['wall_seconds']});self.assertEqual(actual['profile_max_active_cycles'],{'0':self.f['doc']['watchdog']['max_active_cycles']});self.assertEqual(actual['diagnostic_profiles'],[0]);self.assertEqual(actual['reviewed_budget_sha256'],self.f['review']['first_fault_diagnostic']['sha256'])
  self.assertEqual(self.cloud.admit(self.b)['diagnostic_profiles'],[0])
 def test_real_pure_proposal_and_production_authority_separate(self):
  f=self.f;review=f['gate'].verify_review(self.b['model_candidate_review'],self.b['artifact_manifest'],f['artifact']['artifact_identity'],repo=self.b['repo'],current_source_pins_pin=self.b['source_pins']);del self.b['execution_approval'];del self.b['cloud_budget']
  self.assertEqual(self.mode.first_fault_document(self.b,review)['diagnostic_profiles'],[0])
  with self.assertRaises((ValueError,KeyError)):self.mode.admit(self.b)
  with self.assertRaises((ValueError,KeyError)):self.mode.first_fault_admission(self.b)
 def test_real_driver_byte_drift_rejected(self):
  p=self.f['out']/'driver.cpp';p.write_bytes(p.read_bytes()+b'\n')
  with self.assertRaises(ValueError):self.mode.admit(self.b)
 def test_real_historical_stage_not_new_calibration(self):
  f=self.f;summary=json.loads((f['control']/'old_summary.json').read_text());summary['execution_mode']='BOUNDED_CALIBRATION';f['doc']['basis']['historical_stage_summary']=self.n.put(f['control']/'old_summary.json',summary);f['review']['first_fault_diagnostic']=self.n.put(f['control']/'diagnostic.json',f['doc']);self.b['model_candidate_review']=self.n.put(f['control']/'review.json',f['review']);self.doc['model_candidate_review']=self.b['model_candidate_review'];self.ap['model_candidate_review_sha256']=self.b['model_candidate_review']['sha256'];self.approve()
  with self.assertRaises(ValueError):self.mode.admit(self.b)
 def test_real_two_reuses_retained_full_resource_envelope(self):
  for key in ('p0_provider_reuse','reference_data_reuse'):
   row=self.h.put(key,{'synthetic_input_only':True});self.b[key]=row;self.doc[key]=row;self.ap[key+'_sha256']=row['sha256']
  self.doc['aggregate_tree_cap_bytes']=12037043872;self.approve()
  self.assertEqual(self.mode.admit(self.b)['diagnostic_profiles'],[0]);self.assertEqual(self.cloud.admit(self.b)['aggregate_tree_cap_bytes'],12037043872)
  self.doc['aggregate_tree_cap_bytes']+=1;self.approve()
  with self.assertRaises(ValueError):self.mode.admit(self.b)
if __name__=='__main__':unittest.main()
