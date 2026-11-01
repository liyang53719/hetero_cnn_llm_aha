"""Synthetic source-domain tests; not compilation/DUT/numerical acceptance."""
import ast,copy,hashlib,json,pathlib,tempfile,unittest
from unittest import mock
import candidate_observation_contract as m
P=pathlib.Path
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=P(self.tmp.name)
  self.here=self.root/'repo/candidates/same_job_execution_20261030/numeric';self.here.mkdir(parents=True)
  self.patch=mock.patch.object(m,'HERE',self.here);self.patch.start();self.addCleanup(self.patch.stop)
  self.repo=self.root/'repo';self.sources={};self.rows=[];self.anchors={};self.generation={};self.pins={};self.catalog={'schema':'REVIEWED_RELATIVE_SOURCE_CLOSURE_V1','files':[]}
  roles=('helper','host_top','host_commands','owner_kernel','qkv_router','resident','bridge','driver','sparse_memory','commands','descriptors','program_manifest')
  for role in roles:
   p=self.repo/'inputs'/role;p.parent.mkdir(exist_ok=True);p.write_bytes(('SYNTHETIC '+role).encode());pin=self.pin(p);key='inputs/'+role
   self.sources[role]={k:pin[k]for k in ('bytes','sha256')};self.anchors[role]=key
   kind='RUNTIME_EXPECTATION_NOT_BUILD_INPUT'if role in('commands','descriptors')else'RUNTIME_ONLY_CONTRACT'if role=='program_manifest'else'ACTUAL_BUILD_INPUT'
   self.rows.append(dict(path=key,origin_path='/builder/'+key,kind=kind,**self.sources[role]));self.generation['/builder/'+key]=pin['sha256'];self.pins[str(p)]=pin['sha256'];self.catalog['files'].append(dict(path=key,**self.sources[role]))
  contract=self.write(self.here/'MODEL_P0_SOURCE_CONTRACT.json',{'schema':'MODEL_CANDIDATE_P0_OBSERVATION_CONTRACT_V1','sources':self.sources})
  self.cp=mock.patch.object(m,'CONTRACT_SHA',contract['sha256']);self.cp.start();self.addCleanup(self.cp.stop)
  self.evidence=dict(schema='MODEL_CANDIDATE_P0_SOURCE_EVIDENCE_V1',contract=dict(contract,text=P(contract['path']).read_text()),files=self.rows,anchors=self.anchors,program_contract={'text':'synthetic'})
  self.manifest=dict(source_commit='a'*40,generation_input_pins=self.generation,model_source_evidence=self.evidence)
  self.review=dict(scope=m.SCOPE,source_contract=contract,builder_identity={'source_commit':'a'*40},source_manifest_sha256='b'*64)
  self.context=dict(candidate_scope=m.SCOPE,model_source_contract=contract,model_candidate_review=self.write(self.root/'review.json',self.review),builder_identity={'source_commit':'a'*40},source_manifest_sha256='b'*64)
 def pin(self,p):return dict(path=str(p),bytes=p.stat().st_size,sha256=m.sha(p))
 def write(self,p,v):p.write_text(json.dumps(v));return self.pin(p)
 def project(self):return m.relocation_records(self.manifest,str(self.repo),self.pins,self.catalog,self.context)
 def test_actual_nine_source_byte_projection(self):
  out=self.project();self.assertEqual(len(out),9);self.assertNotIn('commands',out);self.assertEqual(out['driver']['origin_path'],'/builder/inputs/driver')
 def test_no_context(self):
  with self.assertRaises(ValueError):m.source_view(self.manifest,None)
 def test_review_pin_changed(self):
  P(self.context['model_candidate_review']['path']).write_text('{}')
  with self.assertRaises(ValueError):self.project()
 def test_wrong_scope(self):
  self.context['candidate_scope']='PRODUCTION'
  with self.assertRaises(ValueError):self.project()
 def test_old_evidence_schema_rejected(self):
  self.evidence['schema']='P0_EMBEDDED_ACTUAL_BUILD_EVIDENCE_V1'
  with self.assertRaises(ValueError):self.project()
 def test_wrong_original_generation(self):
  self.generation['/builder/inputs/driver']='0'*64
  with self.assertRaises(ValueError):self.project()
 def test_source_byte_drift(self):
  (self.repo/'inputs/helper').write_bytes(b'new')
  with self.assertRaises(ValueError):self.project()
 def test_program_may_not_be_actual_input(self):
  next(r for r in self.rows if r['path']=='inputs/commands')['kind']='ACTUAL_BUILD_INPUT'
  with self.assertRaises(ValueError):self.project()
 def test_samehash_wrong_relativepath(self):
  self.anchors['driver']='inputs/helper'
  with self.assertRaises(ValueError):self.project()
 def test_omitted_role(self):
  del self.anchors['driver']
  with self.assertRaises(ValueError):self.project()
 def test_embedded_contract_not_reviewed(self):
  self.evidence['contract']['text']='{}'
  with self.assertRaises(ValueError):self.project()
 def test_bundle_cannot_supply_checker_without_source_catalog(self):
  with self.assertRaises(KeyError):m.reviewed_module('candidate_artifact_handoff',self.context)
 def test_default_profile_nonp0_no_authority(self):
  with self.assertRaises(ValueError):m.validate({'id':1},{},{},self.root,None)
 def test_nonp0_cannot_waive_observations(self):
  with self.assertRaises(ValueError):m.validate({'id':1,'observation_policy':{}},{},{},self.root,self.context)
 def test_p0_mandatory_gates_no_sidecar(self):
  with self.assertRaises(ValueError):m.validate({'id':0},{},{},self.root,self.context)

class AlgorithmPreservation(unittest.TestCase):
 def test_gate_and_corrector_algorithm_remain_mandatory(self):
  source=(P(m.__file__).parent/'candidate_observation_contract.py').read_text()
  self.assertIn("for name in ('gate','up')",source)
  self.assertIn("policy['required_hidden_gates']==required",source)
  self.assertIn("m.verify_delta(original,corrected",source)
  self.assertIn("m.validate_views(views.read_bytes()",source)
  self.assertIn("len(set(anchors.values()))==12",source)
  self.assertIn("result[name]=dict(relative_path=key,origin_path=origin,local=row)",source)
 def test_no_legacy_consumption_checker(self):
  source=(P(m.__file__).parent/'candidate_observation_contract.py').read_text()
  self.assertNotIn("consumption_proof.py",source)
  self.assertIn("module.verify_compilation_policy(artifact,root,receipt",source)
 def test_module_cannot_compile_unpinned_python(self):
  with tempfile.TemporaryDirectory()as t:
   p=P(t)/'cat.json';p.write_text(json.dumps({'schema':'REVIEWED_RELATIVE_SOURCE_CLOSURE_V1','files':[]}))
   context=dict(current_source_pins_pin=dict(path=str(p),bytes=p.stat().st_size,sha256=m.sha(p)),repo=t)
   with self.assertRaises(ValueError):m.reviewed_module('candidate_artifact_handoff',context)

# Frozen from the reviewed d84ed source bytes, not the candidate under test.
# Provenance module hashes are retained even when old connect is no longer present.
LEGACY_CONNECT_MODULE_SHA256='ff53ddcd6fa598c76bbe00c3fe60b93d8aa4cae29d543a71634931548b531c76'
LEGACY_OBSERVATION_MODULE_SHA256='b8401fd6c8c238757103c3c093ea7dc6f3a0d37aab5f0d423e2a7edf2c293e71'
LEGACY_CONNECT_FUNCTION_AST_SHA256={'pin': 'a7edc1661d34422c321479ab508c5c246886239daf2022f48de1533fe55948f1', 'source_guard': '3c00ef595cd40c1daf22c957e2250640cb647468be050b5b15088066ad8825ec', 'base': '867a01f182130cf7393d1a6120b437512690848e09eba20b9d5fae34c35759c6', 'add_arguments': '59139420636ec29b3ade1cd41a67329872db258a83211370b7789c38e4cb2577', 'preflight_artifact': '090c4d0736ca11e9c93affbc757faacaa6d166f1c84863ae62d591a5d7d5638b', 'main': '93e840e70aeb832a361390580ddb820180dd89e07a5f09d847ac71452c6081be'}
LEGACY_VALIDATE_AST_SHA256='eec3d82358bd053376ba6281e06d00ad544c29b4a6621a5b22b56c92e95c00b6'

class OriginalValidationPreservation(unittest.TestCase):
 def test_original_full_p0_validation_ast(self):
  new=ast.parse(P(m.__file__).read_text())
  b=next(n for n in new.body if isinstance(n,ast.FunctionDef)and n.name=='validate')
  first=b.body.pop(0)
  self.assertEqual(ast.dump(first,include_attributes=False),ast.dump(ast.parse('admitted_context(source_relocation)').body[0],include_attributes=False))
  calls=[n for n in ast.walk(b)if isinstance(n,ast.Call)and isinstance(n.func,ast.Name)and n.func.id=='corrector']
  self.assertEqual(len(calls),1);self.assertEqual(ast.dump(calls[0].args[0]),"Name(id='source_relocation', ctx=Load())");calls[0].args=[]
  self.assertEqual(hashlib.sha256(ast.dump(b,include_attributes=False).encode()).hexdigest(),LEGACY_VALIDATE_AST_SHA256)
 def test_unchanged_default_connection_functions(self):
  new=ast.parse((P(m.__file__).parent/'connect_owned.py').read_text())
  for name in ('pin','source_guard','base','add_arguments','preflight_artifact','main'):
   b=next(n for n in new.body if isinstance(n,ast.FunctionDef)and n.name==name)
   if name=='preflight_artifact':
    self.assertEqual(b.args.args[-1].arg,'source_relocation');self.assertIsNone(b.args.defaults[-1].value);b.args.args.pop();b.args.defaults.pop()
    assignments=[n for n in ast.walk(b)if isinstance(n,ast.Assign)and any(isinstance(x,ast.Name)and x.id=='identity'for x in n.targets)]
    self.assertEqual(len(assignments),1);expr=assignments[0].value
    self.assertEqual(ast.dump(expr.test),ast.dump(ast.parse('source_relocation is None',mode='eval').body))
    self.assertEqual(expr.body.func.attr,'artifact_identity');self.assertEqual(len(expr.body.args),1)
    self.assertEqual(expr.orelse.func.attr,'artifact_identity');self.assertEqual(expr.orelse.args[-1].id,'source_relocation')
    assignments[0].value=expr.body
   self.assertEqual(hashlib.sha256(ast.dump(b,include_attributes=False).encode()).hexdigest(),LEGACY_CONNECT_FUNCTION_AST_SHA256[name],name)

class AdmissionOrdering(unittest.TestCase):
 def test_candidate_identity_requires_admitted_context_first(self):
  tree=ast.parse((P(m.__file__).parent/'connect_owned.py').read_text())
  for name in ('connect','preflight'):
   fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name==name)
   branch=next(n for n in fn.body if isinstance(n,ast.If)and 'MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1'in ast.unparse(n.test))
   self.assertIn('approved_source_relocation',ast.unparse(branch.body[0]))
   self.assertIn('source_relocation',ast.unparse(branch.body[1]))
   self.assertNotIn('source_relocation',ast.unparse(branch.orelse[0]))
  fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='connect')
  branch=next(n for n in fn.body if isinstance(n,ast.If)and 'MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1'in ast.unparse(n.test))
  self.assertIn('artifact_identity(frozen)',ast.unparse(branch.orelse[0]))
  self.assertIn('verify_local_build',ast.unparse(branch.orelse[1]))
  self.assertIn('approved_source_relocation',ast.unparse(branch.orelse[2]))

if __name__=='__main__':unittest.main()
