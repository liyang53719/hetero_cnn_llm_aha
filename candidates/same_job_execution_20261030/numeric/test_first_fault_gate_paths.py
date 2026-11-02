"""Exact driver gate dispatch/data relation and legacy math-preservation tests."""
import copy,hashlib,json,os,pathlib,tempfile,unittest
from test_support_first_fault import build,put,pin,module,N
D=pathlib.Path(__file__).resolve().parent
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.f=build(pathlib.Path(self.tmp.name).resolve())
 def context(self):
  f=self.f;b=f['binding'];return dict(candidate_scope=f['helper'].SCOPE,model_candidate_review=b['model_candidate_review'],artifact_manifest=b['artifact_manifest'],model_source_contract=f['review']['source_contract'],source_manifest_sha256=f['review']['source_manifest_sha256'],builder_identity=f['artifact']['artifact_identity'],repo=b['repo'],current_source_pins_pin=b['source_pins'])
 def test_actual_context_probe_same_driver(self):
  f=self.f;result=f['helper'].require_driver(f['artifact'],self.context(),f['artifact']['common']['driver']);self.assertEqual(result['driver_sha256'],f['artifact']['common']['driver']['sha256'])
 def test_context_missing_wrong_scope_or_actual_driver_rejected(self):
  f=self.f
  for c in(None,dict(self.context(),candidate_scope='MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL')):
   with self.assertRaises(ValueError):f['helper'].require_driver(f['artifact'],c,f['artifact']['common']['driver'])
  with self.assertRaises(ValueError):f['helper'].require_driver(f['artifact'],self.context(),dict(f['artifact']['common']['driver'],sha256=f['helper'].LEGACY_SHA))
 def test_real_first_fault_observer_context(self):
  f=self.f;m=module(f['repo']/N/'first_fault_observation_contract.py');self.assertEqual(m.admitted_context(self.context())['schema'],f['helper'].REVIEW_SCHEMA)
 def test_source_contract_old_eleven_roles_and_corrector_whole_inverse(self):
  base=pathlib.Path(os.environ.get('FIRST_FAULT_TEST_BASE',str(D.parents[2])))/N
  old=json.loads((base/'MODEL_P0_SOURCE_CONTRACT.json').read_text());new=json.loads((D/'MODEL_P0_FIRST_FAULT_SOURCE_CONTRACT.json').read_text());new['schema']=old['schema'];new['sources']['driver']=old['sources']['driver'];self.assertEqual(new,old)
  raw=(D/'correct_first_fault_observation_policy.py').read_text().replace('b31095b3e118fe5a2639886bb3dbe3f6de8067cd886884d898c1220b85f8500f','7b46242a1206f651e8fac111436b6cb515b6a69f981b6f01c1e1f26bd7f51f13').replace('MODEL_P0_FIRST_FAULT_SOURCE_CONTRACT.json','MODEL_P0_SOURCE_CONTRACT.json').replace('MODEL_CANDIDATE_P0_FIRST_FAULT_OBSERVATION_CONTRACT_V1','MODEL_CANDIDATE_P0_OBSERVATION_CONTRACT_V1')
  self.assertEqual(raw.encode(),(base/'correct_model_observation_policy.py').read_bytes())
 def test_data_new_branch_actual_inverse_old_branch_rejects(self):
  f=self.f;b=f['binding'];target=f['repo']/'candidates/same_job_execution_20261030/runtime/retained_materials.py';source=D.parent/'runtime/retained_materials.py';source=source if source.is_file()else D/'retained_materials.py';put(target,source.read_bytes());m=module(target)
  oldroot=f['control']/'legacy_payload';oldroot.mkdir();put(oldroot/'driver.cpp',(f['repo']/f['helper'].ROLES['legacy_driver']).read_bytes());driver=pin(oldroot/'driver.cpp')
  oldartifact=dict(schema='FROZEN_FIVE_PROFILE_DUT_ARTIFACT_V2',profiles=list(range(5)),matrix_macs=4096,moe_reference_contract='ORIGINAL_TORCH_TOPK_PENDING_SMALL_ID_ACCEPTANCE',common={'driver':dict(driver,path='driver.cpp')})
  old=dict(artifact_manifest=put(oldroot/'frozen_artifact.json',oldartifact),source_pins=put(f['control']/'old_catalog.json',{'synthetic':True}))
  data=dict(weights=[{'synthetic_weight':True}],references={'synthetic_reference':True});material=put(f['control']/'synthetic_retained.json',data)
  contract=dict(schema='MODEL_CANDIDATE_DATA_REFERENCE_ONLY_READONLY_DRIVER_V1',scope=m.CANDIDATE_SCOPE,old_artifact_manifest_sha256=old['artifact_manifest']['sha256'],new_artifact_manifest_sha256=b['artifact_manifest']['sha256'],retained_materials_sha256=material['sha256'],old_source_pins_sha256=old['source_pins']['sha256'],reference_sources=[dict(path='synthetic/'+str(i),bytes=1,sha256='a'*64)for i in range(51)],weights_sha256=m.domain_sha(data['weights']),references_sha256=m.domain_sha(data['references']),profiles=list(range(5)),tokens=128,routing='UNMODIFIED_OFFICIAL_TORCH_TOPK',readonly_driver_contract_sha256=f['contract_pin']['sha256'])
  def sign(c):
   f['review']['data_reference_contract']=c;b['model_candidate_review']=put(f['control']/'review.json',f['review']);budget=json.loads(pathlib.Path(b['cloud_budget']['path']).read_text());budget['model_candidate_review']=b['model_candidate_review'];b['cloud_budget']=put(f['control']/'budget.json',budget);approval=json.loads(pathlib.Path(b['execution_approval']['path']).read_text());approval.update(model_candidate_review_sha256=b['model_candidate_review']['sha256'],budget_sha256=b['cloud_budget']['sha256']);b['execution_approval']=put(f['control']/'approval.json',approval)
  sign(contract);self.assertEqual(m.candidate_material_contract(material,data,old,b),contract)
  bad=dict(contract,schema='MODEL_CANDIDATE_DATA_REFERENCE_ONLY_V1');bad.pop('readonly_driver_contract_sha256');sign(bad)
  with self.assertRaises(ValueError):m.candidate_material_contract(material,data,old,b)
  bad=dict(contract,readonly_driver_contract_sha256='0'*64);sign(bad)
  with self.assertRaises(ValueError):m.candidate_material_contract(material,data,old,b)
if __name__=='__main__':unittest.main()
