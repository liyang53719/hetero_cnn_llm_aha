"""Real relocation producer, synthetic authority/helpers only; no execution admission/DUT."""
import hashlib,importlib.util,json,os,pathlib,sys,tempfile,types,unittest
from unittest.mock import patch
D=pathlib.Path(__file__).resolve().parent
E=pathlib.Path(os.environ.get('CANDIDATE_EXECUTOR_TEST_SOURCE',str(D)))
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def pin(p):return dict(path=str(p),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
class RelocationProducer(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=pathlib.Path(self.tmp.name);self.n=self.root/'numeric';self.n.mkdir()
  with patch.dict(sys.modules,{'required_acceptance':types.ModuleType('required_acceptance')}):self.c=load('real_relocation_producer',E/'numeric/consumer_owned.py')
  self.c.__file__=str(self.n/'consumer_owned.py')
  def write(p,s):p.write_text(s);return pin(p)
  def doc(name,v):return write(self.root/name,json.dumps(v))
  budget=write(self.root/'cloud_budget.py',"def admit(b):return {'executor_adaptation':b['executor_adaptation']}\n")
  gate=write(self.n/'candidate_admission.py',"def verify(review,b):\n if review!=b['synthetic_approved_review']:raise ValueError('synthetic wrong review')\n return {'scope':'MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL','source_contract':{}}\n")
  contract=write(self.n/'candidate_observation_contract.py',"def relocation_records(manifest,repo,pins,catalog,context):\n if context['source_manifest_sha256']!=catalog['expected_source_sha']:raise ValueError('producer context missing source hash')\n return {'synthetic':True}\n")
  legacy=write(self.n/'observation_contract.py',"def relocation_records(manifest,repo,pins,catalog):return {'legacy':True}\n")
  source=doc('source.json',{'source':'synthetic'});catalog=doc('catalog.json',{'expected_source_sha':source['sha256']});artifact=doc('artifact.json',{});review=doc('review.json',{});binding=doc('binding.json',{})
  self.b=dict(executor_adaptation={'sha256':'a'*64},source_pins=catalog,artifact_manifest=artifact,model_candidate_review=review,synthetic_approved_review=review,repo=str(self.root),pins={r['path']:r['sha256']for r in(budget,gate,contract,legacy)})
  self.f=dict(schema='MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1',artifact_identity={'source_commit':'b'*40},common={'source_manifest':dict(source,path='source.json')})
  self.a=types.SimpleNamespace(profile=0,cloud_binding=pathlib.Path(binding['path']),cloud_binding_sha256=binding['sha256'],artifact_manifest=pathlib.Path(artifact['path']),artifact_manifest_sha256=artifact['sha256'])
  self.proof=dict(executor_identity={'source_commit':'e'*40},executor_adaptation={'executor_source_pins_sha256':catalog['sha256']})
 def call(self):
  with patch.object(self.c,'cloud_invocation',return_value=self.b),patch.object(self.c,'verify_local_build',return_value=self.proof):return self.c.approved_source_relocation(self.a,self.f)
 def test_candidate_all_five_real_producer(self):
  for i in range(5):
   with self.subTest(profile=i):
    self.a.profile=i;r=self.call();self.assertEqual(r['source_manifest_sha256'],self.f['common']['source_manifest']['sha256']);self.assertEqual(r['model_candidate_review'],self.b['model_candidate_review']);self.assertEqual(r['anchors'],{'synthetic':True}if i==0 else {});self.assertEqual(r['controller_binding']['sha256'],self.a.cloud_binding_sha256)
 def test_wrong_review_rejected(self):
  self.b['model_candidate_review']=dict(self.b['model_candidate_review'],sha256='0'*64)
  with self.assertRaisesRegex(ValueError,'wrong review'):self.call()
 def test_source_pin_drift_rejected(self):
  (self.n/'candidate_admission.py').write_text('# drift')
  with self.assertRaisesRegex(ValueError,'candidate admission source pin'):self.call()
 def test_legacy_p0_and_other_profiles_unchanged(self):
  self.f['schema']='FROZEN_FIVE_PROFILE_DUT_ARTIFACT_V2';r=self.call();self.assertEqual(r['anchors'],{'legacy':True});self.assertNotIn('candidate_scope',r);self.assertEqual(r['source_manifest_sha256'],self.f['common']['source_manifest']['sha256'])
  for i in range(1,5):self.a.profile=i;self.assertIsNone(self.call())
if __name__=='__main__':unittest.main()
