import copy,json,pathlib,tempfile,unittest
from test_support_first_fault import build,put,pin
class Test(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.f=build(pathlib.Path(self.tmp.name).resolve())
 def verified(self):
  f=self.f;return f['gate'].verify(f['binding']['model_candidate_review'],f['binding'])
 def test_actual_sources_real_inverse_config_and_review(self):
  self.assertEqual(self.verified()['scope'],self.f['helper'].SCOPE)
  result=self.f['mode'].admit(self.f['binding']);self.assertEqual(result['diagnostic_profiles'],[0]);self.assertEqual(result['watchdog'],self.f['doc']['watchdog'])
 def test_missing_approval_rejected_proposal_still_pure(self):
  f=self.f;b=f['binding'];r=f['gate'].verify_review(b['model_candidate_review'],b['artifact_manifest'],f['artifact']['artifact_identity'],repo=b['repo'],current_source_pins_pin=b['source_pins']);self.assertEqual(f['mode'].verify_document(b,r)['diagnostic_profiles'],[0]);del b['execution_approval']
  with self.assertRaises((ValueError,KeyError)):f['mode'].admit(b)
 def test_wrong_probe_independent_hash(self):
  f=self.f;d=copy.deepcopy(f['doc']);d['readonly_probe_evidence_sha256']='0'*64;f['review']['first_fault_diagnostic']=put(f['control']/'diagnostic.json',d);b=f['binding'];b['model_candidate_review']=put(f['control']/'review.json',f['review'])
  with self.assertRaises(ValueError):f['gate'].verify_review(b['model_candidate_review'],b['artifact_manifest'],f['artifact']['artifact_identity'],repo=b['repo'],current_source_pins_pin=b['source_pins'])
 def test_driver_alteration_rejected(self):
  f=self.f;(f['out']/'driver.cpp').write_bytes((f['out']/'driver.cpp').read_bytes()+b'\n')
  with self.assertRaises(ValueError):self.verified()
 def test_role_relocation_or_missing_catalog_rejected(self):
  f=self.f;cat=json.loads(pathlib.Path(f['binding']['source_pins']['path']).read_text());cat['files']=[x for x in cat['files']if not x['path'].endswith('verify_first_fault_driver.py')];f['binding']['source_pins']=put(f['control']/'catalog.json',cat)
  with self.assertRaises(ValueError):self.verified()
 def test_legacy_review_cannot_label_new_artifact(self):
  f=self.f;r=copy.deepcopy(f['review']);r['schema']=f['gate'].REVIEW_SCHEMA;r.pop('first_fault_diagnostic');rp=put(f['control']/'bad_review.json',r)
  with self.assertRaises(ValueError):f['gate'].verify_review(rp,f['binding']['artifact_manifest'],f['artifact']['artifact_identity'])
 def test_new_review_rejects_legacy_evaluation_status(self):
  f=self.f;r=copy.deepcopy(f['review']);r['status']='REVIEWED_FOR_MODEL_NUMERICAL_EVALUATION';rp=put(f['control']/'old_status_review.json',r)
  with self.assertRaises(ValueError):f['gate'].verify_review(rp,f['binding']['artifact_manifest'],f['artifact']['artifact_identity'],repo=f['binding']['repo'],current_source_pins_pin=f['binding']['source_pins'])
 def test_other_mode_rejected(self):
  for mode in ('BOUNDED_CALIBRATION','STAGE_COVERAGE_DIAGNOSTIC','FULL_BLOCK_ACCEPTANCE'):
   self.f['binding']['execution_mode']=mode
   with self.assertRaises(ValueError):self.verified()
 def test_historical_calibration_not_stage(self):
  f=self.f;r=self.verified();p=f['control']/'old_summary.json';s=json.loads(p.read_text());s['execution_mode']='BOUNDED_CALIBRATION';f['doc']['basis']['historical_stage_summary']=put(p,s);f['review']['first_fault_diagnostic']=put(f['control']/'diagnostic.json',f['doc']);f['binding']['model_candidate_review']=put(f['control']/'review.json',f['review']);r=f['gate'].verify_review(f['binding']['model_candidate_review'],f['binding']['artifact_manifest'],f['artifact']['artifact_identity'],repo=f['binding']['repo'],current_source_pins_pin=f['binding']['source_pins'])
  with self.assertRaises(ValueError):f['mode'].verify_document(f['binding'],r)
if __name__=='__main__':unittest.main()
