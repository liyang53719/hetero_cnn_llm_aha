"""Synthetic controller input propagation; not candidate artifact/ELF acceptance."""
import ast,copy,importlib.util,json,pathlib,types,unittest
from unittest.mock import patch
from test_cloud_budget import Budget,m
D=pathlib.Path(__file__).resolve().parent
class CandidateBudget(Budget):
 def candidate(self,review=True):
  artifact=self.put('candidate_artifact',{'schema':m.MODEL_SCHEMA,'status':'UNREVIEWED_MODEL_BUILD'})
  self.b['artifact_manifest']=artifact;self.doc['artifact_manifest_sha256']=artifact['sha256'];self.ap['artifact_manifest_sha256']=artifact['sha256']
  if review:
   row=self.put('candidate_review',{'synthetic':True});self.b['model_candidate_review']=row;self.doc['model_candidate_review']=row;self.ap['model_candidate_review_sha256']=row['sha256']
  self.reapprove()
 def test_missing_null_candidate_review_early_refusal(self):
  self.candidate(False)
  for value in ('missing',None):
   if value is None:self.b['model_candidate_review']=None
   with self.assertRaisesRegex(ValueError,'MODEL_CANDIDATE_REVIEW_REQUIRED'):m.admit(self.b)
 def test_old_cannot_be_relabeled(self):
  self.b['model_candidate_review']=self.put('review2',{})
  with self.assertRaisesRegex(ValueError,'cannot relabel'):m.admit(self.b)
 def test_candidate_approval_and_budget_are_independent(self):
  self.candidate();self.ap['model_candidate_review_sha256']='0'*64;self.reapprove()
  with self.assertRaisesRegex(ValueError,'approved exact model_candidate_review'):m.admit(self.b)
  self.ap['model_candidate_review_sha256']=self.b['model_candidate_review']['sha256'];self.doc['model_candidate_review']=self.put('different',{});self.reapprove()
  with self.assertRaisesRegex(ValueError,'reviewed adaptation input model_candidate_review'):m.admit(self.b)
 def test_candidate_actual_source_guard_and_returned_pin(self):
  self.candidate();numeric=self.d/'numeric';numeric.mkdir();helper=numeric/'candidate_admission.py'
  helper.write_text("def verify(review_pin,b):\n return {'scope':'MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL','artifact_manifest_sha256':b['artifact_manifest']['sha256'],'roots':[]}\n")
  self.b['pins']={str(helper):m.sha(helper)}
  with patch.object(m,'D',self.d):
   result=m.admit(self.b);self.assertEqual(result['model_candidate_review'],self.b['model_candidate_review'])
   self.assertEqual(result['budgets'],self.doc['budgets']);self.assertEqual(result['stage_resources'],self.doc['stage_resources'])
   helper.write_text(helper.read_text()+'# drift\n')
   with self.assertRaisesRegex(ValueError,'admission source pin'):m.admit(self.b)

class Propagation(unittest.TestCase):
 def test_prepare_selected_handoff_arguments(self):
  spec=importlib.util.spec_from_file_location('candidate_prepare',D/'prepare_cloud_execution.py');prepare=importlib.util.module_from_spec(spec);spec.loader.exec_module(prepare)
  calls=[];roles={k:{'path':k,'sha256':'a'*64}for k in ('builder_handoff','artifact_manifest','executor_adaptation','model_candidate_review')}
  pins={str(D/'numeric/candidate_artifact_handoff.py'):'synthetic'}
  class Manifest:
   def stat(self):return types.SimpleNamespace(st_size=123)
   def __str__(self):return '/synthetic/catalog'
  with patch.object(prepare,'sha',return_value='synthetic'),patch.object(prepare,'load',return_value=types.SimpleNamespace(verify=lambda *a,**kw:calls.append((a,kw)))):
   prepare.imported_handoff(roles,{'schema':m.MODEL_SCHEMA},{},pins,Manifest(),D)
  self.assertEqual(calls[0][1]['model_candidate_review'],roles['model_candidate_review']);self.assertEqual(calls[0][1]['repo'],D)
  self.assertIn('current_source_pins_pin',calls[0][1])
 def test_missing_review_no_handoff_side_effect(self):
  spec=importlib.util.spec_from_file_location('candidate_prepare2',D/'prepare_cloud_execution.py');p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
  with patch.object(p,'load',side_effect=AssertionError('must not import unreviewed handoff')):
   with self.assertRaisesRegex(ValueError,'MODEL_CANDIDATE_REVIEW_REQUIRED'):p.imported_handoff({}, {'schema':m.MODEL_SCHEMA},{},{},None,None)
 def test_all_optional_pin_copies_watch_and_scope(self):
  for filename in ('prepare_cloud_execution.py','controller/cloud_flow.py'):
   text=(D/filename).read_text();tree=ast.parse(text)
   for n in ast.walk(tree):
    if isinstance(n,ast.Tuple):
     values=[e.value for e in n.elts if isinstance(e,ast.Constant)]
     if 'retained_materials'in values and 'executor_adaptation'in values:self.assertIn('model_candidate_review',values)
  flow=(D/'controller/cloud_flow.py').read_text()
  self.assertIn("roots.extend(imported['model_candidate_verified']['roots'])",flow)
  self.assertIn('DATA_REFERENCE_ONLY_NOT_NUMERICAL_ABI_OR_RUNTIME_PASS',flow)
  self.assertIn("scope='P0_FIRST_FAULT_READONLY_SAME_FULL_M128_STIMULUS_NOT_NUMERICAL_ACCEPTANCE'if admission['mode']=='P0_FIRST_FAULT_DIAGNOSTIC'else('MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL'if 'model_candidate_review'in b else 'CHISEL_TEST_GENERATED_SIMULATION_BACKEND_NOT_FINAL_RTL')",flow)
  self.assertIn("'model-candidate-review'",(D/'prepare_cloud_execution.py').read_text())
if __name__=='__main__':unittest.main()
