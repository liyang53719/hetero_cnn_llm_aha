"""Real candidate verifier + real stage document; synthetic file evidence only, no admission."""
import importlib.util,pathlib,shutil,sys,unittest
from unittest.mock import patch
import test_stage_coverage as fixture_stage
D=fixture_stage.D
class Proposal(unittest.TestCase):
 def setUp(self):
  self.s=fixture_stage.Stage();self.s.setUp();self.addCleanup(self.s.tearDown)
  s=self.s;n=D/'numeric';shutil.copyfile(n/'candidate_admission.py',s.e/'numeric/candidate_admission.py')
  def load(name,path):
   spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
  self.helper=load('real_stage_candidate',n/'candidate_admission.py')
  with patch.dict(sys.modules,{'candidate_admission':self.helper}):fixture=load('real_stage_candidate_fixture',n/'test_candidate_admission.py')
  self.f=fixture.Test();self.f.setUp();self.addCleanup(self.f.doCleanups)
  f=self.f;rp=f.write('review.json',f.r);self.review=self.helper.verify_review(rp,f.fp,f.identity)
  s.b.update(artifact_manifest=f.fp,model_candidate_review=rp)
  for k,v in [('artifact_manifest_sha256',f.fp['sha256']),('model_candidate_review_sha256',rp['sha256'])]:s.stage[k]=v;s.summary[k]=v
  s.stage['basis']['calibration_summary']=s.h.put('cal',s.summary)
  s.reapprove();s.b['pins'][str(s.e/'numeric/candidate_admission.py')]=s.mode.sha(s.e/'numeric/candidate_admission.py')
  del s.b['execution_approval'];del s.b['cloud_budget']
 def test_real_offline_review_and_document_without_authority(self):
  out=self.s.mode.stage_document(self.s.b,self.review)
  self.assertEqual(out['mode'],self.s.mode.STAGE);self.assertEqual(out['profile_seconds']['0'],601)
 def test_production_stage_still_rejects_missing_authority(self):
  with self.assertRaises((KeyError,ValueError)):self.s.mode.stage_admission(self.s.b)
  with self.assertRaises((KeyError,ValueError)):self.s.mode.admit(self.s.b)
 def test_offline_doc_still_rejects_review_drift(self):
  with self.assertRaises(ValueError):self.s.mode.stage_document(self.s.b,dict(self.review,artifact_manifest_sha256='0'*64))
if __name__=='__main__':unittest.main()
