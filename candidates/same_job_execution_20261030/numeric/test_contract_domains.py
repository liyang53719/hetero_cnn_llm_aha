"""Actual locked contract bytes, distinct source domains; no execution authority."""
import copy,hashlib,importlib.util,json,os,pathlib,tempfile,unittest
D=pathlib.Path(__file__).resolve().parent
N=pathlib.Path(os.environ.get('MODEL_CONTRACT_BASE',str(D)))
REL='candidates/same_job_execution_20261030/numeric/MODEL_P0_SOURCE_CONTRACT.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def pin(p):return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
class Domains(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.root=pathlib.Path(self.t.name);self.repo=self.root/'executor';n=self.repo/pathlib.Path(REL).parent;n.mkdir(parents=True)
  src=D/'candidate_observation_contract.py';target=n/src.name;target.write_bytes(src.read_bytes());s=importlib.util.spec_from_file_location('domain_under_test',target);self.m=importlib.util.module_from_spec(s);s.loader.exec_module(self.m)
  self.local=n/'MODEL_P0_SOURCE_CONTRACT.json';self.local.write_bytes((N/'MODEL_P0_SOURCE_CONTRACT.json').read_bytes());self.builder=self.root/'builder_contract.json';self.builder.write_bytes(self.local.read_bytes())
  self.cat=self.root/'catalog.json';self.rows=[dict(pin(self.local),path=REL)];self.writecat()
  self.review=self.root/'review.json';self.reviewdoc=dict(scope=self.m.SCOPE,source_contract=pin(self.builder),builder_identity={'source_commit':'a'*40},source_manifest_sha256='b'*64);self.review.write_text(json.dumps(self.reviewdoc))
  self.ctx=dict(candidate_scope=self.m.SCOPE,model_candidate_review=pin(self.review),model_source_contract=pin(self.builder),builder_identity={'source_commit':'a'*40},source_manifest_sha256='b'*64,repo=str(self.repo),current_source_pins_pin=pin(self.cat))
 def writecat(self):self.cat.write_text(json.dumps(dict(schema='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1',files=self.rows)))
 def call(self):return self.m.admitted_context(self.ctx)
 def test_distinct_paths_full_admitted_context_and_source_view(self):
  self.assertNotEqual(self.builder,self.local);self.assertEqual(self.call(),self.reviewdoc)
  e=dict(schema='MODEL_CANDIDATE_P0_SOURCE_EVIDENCE_V1',contract=dict(pin(self.builder),text=self.builder.read_text()),files=[],anchors={},program_contract={})
  self.assertEqual(self.m.source_view({'model_source_evidence':e},self.ctx)['files'],[])
  self.assertEqual(self.ctx['model_source_contract'],pin(self.builder))
 def test_builder_changed_even_repin_rejected(self):
  self.builder.write_bytes(self.builder.read_bytes()+b' ');self.ctx['model_source_contract']=pin(self.builder)
  with self.assertRaises(ValueError):self.call()
 def test_local_changed_even_catalog_repin_rejected(self):
  self.local.write_bytes(self.local.read_bytes()+b' ');self.rows=[dict(pin(self.local),path=REL)];self.writecat();self.ctx['current_source_pins_pin']=pin(self.cat)
  with self.assertRaises(ValueError):self.call()
 def test_missing_duplicate_and_wrong_catalog_role_rejected(self):
  original=copy.deepcopy(self.rows)
  for rows in ([],original*2,[dict(original[0],path='wrong.json')],[dict(original[0],sha256='0'*64)]):
   with self.subTest(rows=rows):
    self.rows=rows;self.writecat();self.ctx['current_source_pins_pin']=pin(self.cat)
    with self.assertRaises(ValueError):self.call()
 def test_wrong_repo_rejected(self):
  self.ctx['repo']=str(self.root/'other')
  with self.assertRaises(ValueError):self.call()
 def test_same_bytes_symlink_rejected(self):
  self.local.unlink();self.local.symlink_to(self.builder)
  with self.assertRaises(ValueError):self.call()
 def test_external_review_domain_cannot_be_rewritten(self):
  self.ctx['model_source_contract']=pin(self.local)
  with self.assertRaisesRegex(ValueError,'same independently reviewed source domain'):self.call()
class ProducerAuthority(unittest.TestCase):
 def test_unapproved_adapter_diff_stops_real_producer_before_mapping(self):
  from unittest.mock import patch
  helper=N.parent/'test_candidate_relocation_producer.py'
  spec=importlib.util.spec_from_file_location('existing_real_producer_fixture',helper);h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
  t=h.RelocationProducer('test_candidate_all_five_real_producer');t.setUp()
  try:
   with patch.object(t.c,'cloud_invocation',return_value=t.b),patch.object(t.c,'verify_local_build',side_effect=ValueError('UNAUTHORIZED_EXECUTOR_DIFF'))as gate:
    with self.assertRaisesRegex(ValueError,'UNAUTHORIZED_EXECUTOR_DIFF'):t.c.approved_source_relocation(t.a,t.f)
    gate.assert_called_once()
  finally:t.doCleanups()
if __name__=='__main__':unittest.main()
