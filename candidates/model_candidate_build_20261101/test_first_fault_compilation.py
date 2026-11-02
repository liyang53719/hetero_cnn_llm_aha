"""Synthetic header/dependency joins, real frozen contract decoder. No EDA."""
import builtins,copy,json,pathlib,tempfile,unittest,sys
from unittest import mock
import first_fault_probe as probe
import first_fault_compilation as check
import first_fault_policy as policy
from test_first_fault_probe import synthetic_header
D=pathlib.Path(__file__).resolve().parent
class Tests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.w=pathlib.Path(self.temp.name).resolve();repo=self.w/'repo';repo.mkdir();obj=self.w/'obj';obj.mkdir()
  self.contractraw=(D/'FIRST_FAULT_DRIVER_CONTRACT.json').read_bytes();self.contract=policy.decode_contract(self.contractraw)
  def sourcefile(role,raw):
   p=repo/self.contract[role]['repo_path'];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw);return p
  schema=sourcefile('probe_schema',(D/'FIXED_NONHIER_SCHEMA.json').read_bytes())
  config=repo/self.contract['probe_config']['repo_path'];config.parent.mkdir(parents=True,exist_ok=True);probe.write_config(schema,config)
  doc,_=probe.load_schema(schema);rh=obj/'VHostBlockTopV4___024root.h';rh.write_bytes(synthetic_header(doc))
  accessor=obj/'readonly_first_fault_access.hpp';evidence=self.w/'actual_evidence.json'
  gen=probe.generate(schema,config,rh,accessor,evidence)
  cp=repo/policy.CONTRACT_REPO_PATH
  cpin={'path':str(cp),'bytes':len(self.contractraw),'sha256':policy.CONTRACT_SHA,'text':self.contractraw.decode()}
  driver=repo/self.contract['diagnostic_driver']['repo_path'];helper=repo/self.contract['host_observer']['repo_path']
  self.dep={'cwd':str(obj),'driver':str(driver),'dependencies':{str(rh):{k:gen['root_header'][k]for k in ('path','bytes','sha256')},str(accessor):{k:gen['accessor'][k]for k in ('path','bytes','sha256')},str(helper):{'path':str(helper),'bytes':self.contract['host_observer']['bytes'],'sha256':self.contract['host_observer']['sha256']}}}
  hierarchy=repo/doc['original_hierarchy_pin']['repo_path']
  pins={str(cp):policy.CONTRACT_SHA,str(schema):probe.SCHEMA_SHA,str(config):gen['config']['sha256'],str(driver):self.contract['diagnostic_driver']['sha256'],str(helper):self.contract['host_observer']['sha256'],str(hierarchy):doc['original_hierarchy_pin']['sha256']}
  self.source={'readonly_probe':{'schema':'FIRST_FAULT_READONLY_BUILD_EVIDENCE_V1','status':'OBSERVED_UNREVIEWED','contract':cpin,'accessor_generation':gen},'generation_input_pins':pins,'derived_generated_pins':{str(rh):gen['root_header']['sha256'],str(accessor):gen['accessor']['sha256']},'physical_closure':{'initial_frontend_argv':['verilator','--hierarchical',str(hierarchy),str(config)]},'driver_sha256':self.contract['diagnostic_driver']['sha256'],'sv_sha256':policy.ORIGINAL_SV_SHA}
  self.manifest={'schema':policy.FIRST_FAULT_MANIFEST_SCHEMA,'scope':policy.FIRST_FAULT_SCOPE,'readonly_probe_contract':{'bytes':len(self.contractraw),'sha256':policy.CONTRACT_SHA},'common':{'driver':{'sha256':self.contract['diagnostic_driver']['sha256']},'sv':{'sha256':policy.ORIGINAL_SV_SHA}}}
  self.receipt={'scope':policy.FIRST_FAULT_SCOPE,'readonly_probe_contract_sha256':policy.CONTRACT_SHA}
 def verify(self):return check.verify_readonly_probe(self.manifest,self.source,self.receipt,self.dep)
 def test_positive_real_contract_synthetic_header(self):
  r=self.verify();self.assertEqual(r['field_count'],114);self.assertFalse(r['numerical_pass'])
 def test_old_exact_no_probe(self):self.assertIsNone(check.verify_readonly_probe({'schema':'MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1'},{},{},{}))
 def test_legacy_pack_and_policy_without_new_imports(self):
  import candidate_dependency_proof as proof
  import test_pack_model_candidate as fixture
  case=fixture.PackTests('test_pack_exact_seven_unreviewed');case.setUp();self.addCleanup(case.doCleanups)
  with mock.patch.object(policy,'expected_driver_sha',return_value=fixture.m.DRIVER_SHA):
   result=case.runpack()
  root=pathlib.Path(result['manifest']['path']).parent
  row={'schema':'ACTUAL_FRESH_DRIVER_DEPENDENCY_V2','cpp_build_policy':proof.CPP_O1_POLICY,'cpp_build_overrides':proof.CPP_O1_OVERRIDES}
  rec=dict(row,schema='MODEL_CANDIDATE_BUILD_RECEIPT_V1',status='UNREVIEWED_MODEL_BUILD')
  banned=('first_fault_policy','first_fault_probe','first_fault_compilation')
  real_import=builtins.__import__
  def checked_import(name,*args,**kwargs):
   if name in banned:raise AssertionError('legacy imported new helper '+name)
   return real_import(name,*args,**kwargs)
  with mock.patch.dict(sys.modules):
   for name in banned:sys.modules.pop(name,None)
   with mock.patch('builtins.__import__',side_effect=checked_import):
    self.assertEqual(fixture.m.validate_export(root)['files'],7)
    self.assertEqual(proof.compilation_policy(row,dict(row),rec)[0],proof.CPP_O1_POLICY)
   self.assertTrue(all(name not in sys.modules for name in banned))
 def test_old_cannot_carry_probe(self):
  self.manifest['schema']='MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1'
  with self.assertRaises(ValueError):self.verify()
 def test_wrong_actual_sv(self):
  self.source['sv_sha256']='0'*64
  with self.assertRaises(ValueError):self.verify()
 def test_contract_drift(self):
  self.source['readonly_probe']['contract']['text']+=' '
  with self.assertRaises(ValueError):self.verify()
 def test_receipt_missing_contract(self):
  del self.receipt['readonly_probe_contract_sha256']
  with self.assertRaises(ValueError):self.verify()
 def test_mapping_changed(self):
  self.source['readonly_probe']['accessor_generation']['mappings'][0]['width_bits']=2
  with self.assertRaises(ValueError):self.verify()
 def test_accessor_changed(self):
  a=self.source['readonly_probe']['accessor_generation']['accessor'];a['text']+='//bad\n';a['bytes']=len(a['text'].encode());a['sha256']=check.sha(a['text'].encode());self.source['derived_generated_pins'][a['path']]=a['sha256'];self.dep['dependencies'][a['path']]={k:a[k]for k in ('path','bytes','sha256')}
  with self.assertRaises(ValueError):self.verify()
 def test_missing_actual_header_dependency(self):
  p=self.source['readonly_probe']['accessor_generation']['root_header']['path'];del self.dep['dependencies'][p]
  with self.assertRaises(ValueError):self.verify()
 def test_root_pin_drift(self):
  p=self.source['readonly_probe']['accessor_generation']['root_header']['path'];self.source['derived_generated_pins'][p]='0'*64
  with self.assertRaises(ValueError):self.verify()
 def test_extra_global_visibility(self):
  self.source['physical_closure']['initial_frontend_argv'].append('--public-flat-rw')
  with self.assertRaises(ValueError):self.verify()
 def test_config_not_in_actual_argv(self):
  self.source['physical_closure']['initial_frontend_argv'].pop()
  with self.assertRaises(ValueError):self.verify()
 def test_second_config(self):
  a=self.source['physical_closure']['initial_frontend_argv'];a.append(a[-1])
  with self.assertRaises(ValueError):self.verify()
 def test_wrong_helper_parent(self):
  p=next(p for p in self.dep['dependencies']if p.endswith('/readonly_first_fault.hpp'));v=self.dep['dependencies'].pop(p);v['path']='/other/readonly_first_fault.hpp';self.dep['dependencies'][v['path']]=v
  with self.assertRaises(ValueError):self.verify()
 def test_conflicting_generation_pin(self):
  p=next(iter(self.source['derived_generated_pins']));self.source['generation_input_pins'][p]='0'*64
  with self.assertRaises(ValueError):self.verify()
if __name__=='__main__':unittest.main()
