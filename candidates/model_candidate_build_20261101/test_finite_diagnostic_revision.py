# Only historical source/AST assertions use the exact finite-layer inverse.
# Runtime tests still import and execute the actual candidate implementations.
import pathlib as _finite_pathlib, importlib.util as _finite_importlib
_finite_path=_finite_pathlib.Path(__file__).resolve().parents[2]/'candidates/model_candidate_build_20261101/finite_watchdog_test_inverse.py'
_finite_spec=_finite_importlib.spec_from_file_location('finite_watchdog_test_inverse',_finite_path)
_finite_module=_finite_importlib.module_from_spec(_finite_spec);_finite_spec.loader.exec_module(_finite_module)
prior_text=_finite_module.prior_text;prior_sha=_finite_module.prior_sha
"""Source-only exact producer-revision closure tests, no build/EDA/DUT.
Synthetic catalogs exercise loader integrity, not execution authorization.
"""
import ast,copy,hashlib,importlib.util,json,pathlib,sys,tempfile,unittest
from unittest import mock
D=pathlib.Path(__file__).resolve().parent;R=D.parents[1];P=pathlib.Path
sys.path.insert(0,str(D))
import candidate_dependency_proof as proof
JOB='candidates/model_candidate_build_20261101/one_job_model_candidate.py'
PROOF='candidates/model_candidate_build_20261101/candidate_dependency_proof.py'
GATE='candidates/model_candidate_build_20261101/candidate_generation_gate.py'
PACK='candidates/model_candidate_build_20261101/pack_model_candidate.py'
NEW='ac4ba44560ed7d73d6459fbe237e9cac0de2e3141d1e6a1e86feae130364d58d'
OLD='7e04700f063728cf1df376a563565830f7e1544f8b2e439b507cc649975749ff'
ADDRESS='0a5e09a27a447b028697a631e5207fc0af6cae15d4c324a55524f9d41a46a753'
LEGACY='3354827c1c9d2ac167b3b325dc07acbd50ea663ddd384dddfea1b1d037ae3851'
HISTORICAL_NAMES=('PRODUCER_IMPLEMENTATION_PINS','O1_PRODUCER_IMPLEMENTATION_PINS','CANDIDATE_IMPLEMENTATION_PINS','OLD_CANDIDATE_IMPLEMENTATION_PINS','FIRST_FAULT_IMPLEMENTATION_PINS','TERMINAL_IMPLEMENTATION_PINS','SELECTOR_IMPLEMENTATION_PINS','SELECTOR_DIAGNOSTIC_REVISIONS','SELECTOR_FIRST_FAULT_REVISIONS','SELECTOR_GENERATION_PAIRS')
HISTORICAL_MAPS_SHA256='381cd47282dc0ce1c9dd0de8590e429c0874a10666137dcffb03b5f6fec08737'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def source(new=True,generation=ADDRESS):
 directory,overlay=proof.SELECTOR_GENERATION_PAIRS[generation];prefix='/synthetic/repo/'
 pins={prefix+k:v for k,v in proof.SELECTOR_IMPLEMENTATION_PINS.items()}
 if new:pins[prefix+JOB]=NEW
 pins.update({prefix+directory+'/GENERATION_CONTRACT.json':generation,prefix+directory+'/MODEL_SOURCE_OVERLAY.json':overlay})
 return {'generation_input_pins':pins,'fixed_source_overlay':prefix+directory+'/MODEL_SOURCE_OVERLAY.json','model_candidate_observation':{'source_closure':{'generation_contract_sha256':generation,'source_overlay':{'sha256':overlay},'source_count':159}},'cpp_build_policy':proof.CPP_O1_POLICY,'cpp_build_overrides':list(proof.CPP_O1_OVERRIDES)}

def receipt():
 r={'schema':'ACTUAL_FRESH_DRIVER_DEPENDENCY_V2','cpp_build_policy':proof.CPP_O1_POLICY,'cpp_build_overrides':list(proof.CPP_O1_OVERRIDES)}
 return r,dict(r,schema='MODEL_CANDIDATE_BUILD_RECEIPT_V1',status='UNREVIEWED_MODEL_BUILD')

class Tests(unittest.TestCase):
 def test_exact_new_source_and_minimal_map(self):
  self.assertEqual(proof.FINITE_STAGE_DIAGNOSTIC_REVISION,{JOB:NEW});self.assertEqual(prior_sha(R/JOB),NEW)
  selected=proof.selector_producer_policy(source(),None)
  self.assertEqual({k for k in selected if selected[k]!=proof.SELECTOR_IMPLEMENTATION_PINS[k]},{JOB})
  self.assertEqual(selected[JOB],NEW)
  for k,v in selected.items():self.assertEqual(prior_sha(R/k),v,k)
 def test_all_historical_maps_unchanged(self):
  raw=json.dumps({n:getattr(proof,n)for n in HISTORICAL_NAMES},sort_keys=True,separators=(',',':')).encode()
  self.assertEqual(hashlib.sha256(raw).hexdigest(),HISTORICAL_MAPS_SHA256)
  self.assertEqual(proof.SELECTOR_IMPLEMENTATION_PINS[JOB],OLD);self.assertEqual(proof.TERMINAL_IMPLEMENTATION_PINS[JOB],OLD)
 def test_all_nonselector_proof_ast_unchanged(self):
  tree=ast.parse(prior_text(D/'candidate_dependency_proof.py'))
  tree.body=[n for n in tree.body if not(isinstance(n,ast.FunctionDef)and n.name=='selector_producer_policy'or isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='FINITE_STAGE_DIAGNOSTIC_REVISION'for t in n.targets))]
  self.assertEqual(hashlib.sha256(ast.dump(tree,include_attributes=False).encode()).hexdigest(),'4c08408c5b7fb692aedb3e7f7fff43963380864bcddebd2cdc76898ee834fb55')
 def test_ordinary_corrected_old_variant_retained(self):self.assertEqual(proof.selector_producer_policy(source(False),None),proof.SELECTOR_IMPLEMENTATION_PINS)
 def test_no_new_revision_for_legacy_hardware_or_readonly(self):
  for generation,mode in [(LEGACY,None),(LEGACY,{'schema':'FIRST_FAULT_DRIVER_CONTRACT_V1'}),(LEGACY,{'schema':'FIRST_FAULT_DRIVER_CONTRACT_V2'}),(ADDRESS,{'schema':'FIRST_FAULT_DRIVER_CONTRACT_V1'}),(ADDRESS,{'schema':'FIRST_FAULT_DRIVER_CONTRACT_V2'})]:
   with self.subTest(generation=generation,mode=mode),self.assertRaisesRegex(ValueError,'finite stage diagnostics require corrected ordinary producer'):proof.selector_producer_policy(source(True,generation),mode)
 def test_duplicate_and_foreign_root_reject(self):
  for alter in ('duplicate','foreign'):
   s=source();s['generation_input_pins']['/else/'+JOB]=NEW
   if alter=='foreign':s['generation_input_pins'].pop('/synthetic/repo/'+JOB)
   with self.subTest(alter=alter),self.assertRaisesRegex(ValueError,'one exact finite diagnostic producer root'):proof.selector_producer_policy(s,None)
 def test_no_new_generation_or_overlay_admission(self):
  for key,value in [('generation_contract_sha256','f'*64),('source_overlay',{'sha256':'f'*64}),('source_count',160)]:
   s=source();s['model_candidate_observation']['source_closure'][key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):proof.selector_producer_policy(s,None)
 def test_full_producer_pin_gate_reaches_tool_gate_only_for_exact_variant(self):
  r,b=receipt()
  with self.assertRaisesRegex(ValueError,'actual compiler inventory schema'):proof.verify_compilation_policy(r,source(),b,{'schema':'SYNTHETIC_STOP_AFTER_ALL_PRODUCER_PINS'})
  # This is a prefix proof only, not a complete compilation acceptance.
 def test_mixed_missing_arbitrary_selfhashed_producer_rejected(self):
  for key,how in [(JOB,'unknown'),(PACK,'unknown'),(JOB,'missing'),(GATE,'unknown')]:
   s=source();p='/synthetic/repo/'+key
   if how=='missing':s['generation_input_pins'].pop(p)
   else:s['generation_input_pins'][p]=hashlib.sha256(b'self-authored-unreviewed-source').hexdigest()
   r,b=receipt()
   with self.subTest(key=key,how=how),self.assertRaises(ValueError):proof.verify_compilation_policy(r,s,b,{'schema':'SYNTHETIC_STOP_AFTER_ALL_PRODUCER_PINS'})
 def test_local_pack_pin_unchanged(self):self.assertEqual(proof.LOCAL_PACK_READER_SHA,sha(R/PACK))
 def test_exact_catalog_handoff_load_and_proof_drift_rejection(self):
  handoff=load('_finite_diagnostic_handoff',R/'candidates/same_job_execution_20261030/numeric/candidate_artifact_handoff.py')
  with tempfile.TemporaryDirectory(prefix='finite-revision-')as td:
   repo=P(td).resolve();rows=[]
   for rel in (PACK,PROOF):
    p=repo/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((R/rel).read_bytes());rows.append({'path':rel,'bytes':p.stat().st_size,'sha256':sha(p)})
   cat=repo/'source_catalog.json';cat.write_text(json.dumps({'schema':'REVIEWED_RELATIVE_SOURCE_CLOSURE_V1','files':rows}))
   pin={'path':str(cat),'bytes':cat.stat().st_size,'sha256':sha(cat)}
   # Import only ordinary source-pinned readers; no seven-file artifact is claimed.
   with mock.patch.dict(sys.modules,clear=False):
    for n in ('pack_model_candidate','candidate_dependency_proof'):sys.modules.pop(n,None)
    loaded=handoff.load_candidate_checker(pin,repo)
   self.assertEqual(loaded['candidate_dependency_proof'].FINITE_STAGE_DIAGNOSTIC_REVISION,{JOB:NEW})
   p=repo/PROOF;p.write_text(p.read_text()+'# unreviewed drift\n')
   with mock.patch.dict(sys.modules,clear=False):
    for n in ('pack_model_candidate','candidate_dependency_proof'):sys.modules.pop(n,None)
    with self.assertRaisesRegex(ValueError,'source-pinned candidate verifier before import'):handoff.load_candidate_checker(pin,repo)
if __name__=='__main__':unittest.main(verbosity=2)
