"""Synthetic predicate/receipt wiring tests ONLY. No hardware executed."""
import copy,json,pathlib,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'numeric'))
import required_acceptance as a
import dut_evidence as d
import consumer_owned as c
H='1'*64
DOMAIN=dict(nan=0,positive_infinity=0,negative_infinity=0,negative_finite=0,negative_zero=0,above_one_finite=0)

def comparison(size):return dict(bytes=size,byte_mismatches=0,actual_sha256=H,expected_layout_sha256=H,actual_nonfinite_elements=0,reference_nonfinite_elements=0)
def row(i):
 r=dict(profile=i,complete_block_tokens=128,exit_code=0,execution_evidence={k:True for k in a.EXECUTION},comparisons={k:comparison(v) for k,v in a.OUTPUTS[i].items()})
 if i in (3,4):
  r['router']={k:comparison(v) for k,v in [('ids',8192),('normalized_bf16_weights',2048),('bf16_dense_logits',65536)]}
  r['router']['raw_probability_diagnostics']=dict(status='COMPARED_DIAGNOSTIC_ONLY',shape=[128,256],dtype='FP32_LE',coverage='EXACT_ONCE_32768',full_probabilities=dict(elements=32768,bytes=131072,actual_sha256=H,reference_sha256='2'*64,byte_mismatches=131072,actual_value_counts=dict(DOMAIN)),actual_selected_output=dict(status='COMPARED_ACTUAL_SELECTION_OUTPUT_DIAGNOSTIC_ONLY',shape=[128,8],score_bytes=4096,id_bytes=4096,score_sha256=H,id_sha256=H,coverage='EXACT_ONCE_1024',input_output_score_consistency=dict(elements=1024,bytes=4096,element_mismatches=0,byte_mismatches=0,actual_sha256=H,reference_sha256=H,actual_value_counts=dict(DOMAIN)),selected_vs_route_id_mismatches=0))
 return r

def records():
 identity=dict(layer=a.LAYER,matrix_macs=4096,vector_lanes=32,**{k:H for k in ('artifact_manifest_sha256','binary_sha256','sv_sha256','source_manifest_sha256','driver_sha256')})
 return [dict(profile=i,numerical_pass=True,qualification=a.evaluate(row(i),outer_verified=True),common_artifact_identity=copy.deepcopy(identity)) for i in range(5)]

class Tests(unittest.TestCase):
 def test_all_profile_fixture_predicates(self):
  for i in range(5):
   with self.subTest(i=i):
    self.assertTrue(a.evaluate(row(i),outer_verified=True)['numerical_pass'])
    self.assertEqual(a.evaluate(row(i))['missing'],['verified_outer_cleanup_and_log_eof'])
 def test_every_required_output_missing(self):
  for i in range(5):
   for key in a.OUTPUTS[i]:
    r=row(i);del r['comparisons'][key]
    self.assertFalse(a.evaluate(r,outer_verified=True)['numerical_pass'])
 def test_every_execution_receipt_required(self):
  for key in a.EXECUTION:
   r=row(1);r['execution_evidence'][key]=False
   self.assertIn(key,a.evaluate(r,outer_verified=True)['missing'])
 def test_actual_mismatch_fails(self):
  r=row(1);r['comparisons']['output']['byte_mismatches']=1
  self.assertEqual(a.evaluate(r,outer_verified=True)['status'],'FAIL_EXACT_REFERENCE')
 def test_same_nan_bits_cannot_pass(self):
  for key in ('actual_nonfinite_elements','reference_nonfinite_elements'):
   r=row(1);r['comparisons']['output'][key]=1
   self.assertEqual(a.evaluate(r,outer_verified=True)['status'],'FAIL_EXACT_REFERENCE')
 def test_small_tensor_not_full(self):
  r=row(1);r['comparisons']['output']['bytes']=4
  self.assertFalse(a.evaluate(r,outer_verified=True)['numerical_pass'])
 def test_moe_arithmetic_diagnostic_not_new_contract(self):
  self.assertTrue(a.evaluate(row(3),outer_verified=True)['numerical_pass'])
 def test_raw_domain_exceptions_not_hidden(self):
  for key in ('nan','positive_infinity','negative_infinity','negative_finite'):
   r=row(3);r['router']['raw_probability_diagnostics']['full_probabilities']['actual_value_counts'][key]=1
   self.assertEqual(a.evaluate(r,outer_verified=True)['status'],'FAIL_EXACT_REFERENCE')
  r=row(3);r['router']['raw_probability_diagnostics']['full_probabilities']['actual_value_counts']['negative_zero']=1
  self.assertTrue(a.evaluate(r,outer_verified=True)['numerical_pass'])
  r['router']['raw_probability_diagnostics']['full_probabilities']['actual_value_counts']['above_one_finite']=1
  self.assertEqual(a.evaluate(r,outer_verified=True)['status'],'INCOMPLETE')
 def test_original_route_mismatch_is_not_tie_override(self):
  r=row(3);r['router']['ids']['byte_mismatches']=1
  q=a.evaluate(r,outer_verified=True);self.assertFalse(q['numerical_pass']);self.assertTrue(q['route_divergence_requires_diagnosis'])
 def test_selector_corruption_fails(self):
  r=row(3);r['router']['raw_probability_diagnostics']['actual_selected_output']['input_output_score_consistency']['element_mismatches']=1
  self.assertEqual(a.evaluate(r,outer_verified=True)['status'],'FAIL_EXACT_REFERENCE')
 def test_selector_zero_element_contradiction_rejected(self):
  r=row(3);c=r['router']['raw_probability_diagnostics']['actual_selected_output']['input_output_score_consistency']
  c.update(byte_mismatches=4096,actual_sha256='2'*64)
  self.assertFalse(a.evaluate(r,outer_verified=True)['numerical_pass'])
 def test_missing_raw_observation(self):
  r=row(3);del r['router']['raw_probability_diagnostics']
  q=a.evaluate(r,outer_verified=True);self.assertFalse(q['numerical_pass']);self.assertIn('raw_fp32_selected_topk_scores',q['missing'])
 def test_missing_element_coverage(self):
  r=row(3);r['router']['raw_probability_diagnostics']['actual_selected_output']['input_output_score_consistency']['elements']=1
  self.assertFalse(a.evaluate(r,outer_verified=True)['numerical_pass'])
 def test_five_profiles_required(self):
  self.assertTrue(a.aggregate(records())['numerical_pass'])
  for i in range(5):
   rs=records();rs.pop(i);self.assertFalse(a.aggregate(rs)['numerical_pass'])
 def test_duplicate_profile_rejected(self):
  rs=records();rs[-1]=rs[0];self.assertFalse(a.aggregate(rs)['numerical_pass'])
 def test_common_hardware_identity(self):
  for key,value in [('sv_sha256','2'*64),('matrix_macs',512),('layer','FINAL_RTL_REPLAY')]:
   rs=records();rs[4]['common_artifact_identity'][key]=value
   self.assertFalse(a.aggregate(rs)['numerical_pass'])
 def test_final_rtl_never_claimed(self):
  q=a.aggregate(records());self.assertFalse(q['final_rtl_executed']);self.assertEqual(q['utilization_qualification'],'UNMEASURED')
 def test_nonfinite_bit_detection_no_rounding(self):
  self.assertEqual(c.nonfinite(bytes.fromhex('0100807f0000803f'),'FP32'),1)
  self.assertEqual(c.nonfinite(bytes.fromhex('c17f803f'),'BF16'),1)
  x=bytes.fromhex('0100803f');q=c.compare(x,bytes.fromhex('0000803f'),'FP32')
  self.assertEqual(q['byte_mismatches'],1)
 def test_outer_actual_receipt_join_fixture(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=pathlib.Path(tmp);r=row(1);r['qualification']=a.evaluate(r);r['status']='INCOMPLETE';r['numerical_pass']=False
   report=dict(status='INCOMPLETE',numerical_pass=False,layer=a.LAYER,final_rtl_executed=False,artifact_manifest_sha256=H,runtime_bundle_sha256=H,profiles=[r],matrix_macs=4096,vector_lanes=32,common={k:dict(sha256=H) for k in ('binary','sv','source_manifest','driver')})
   (p/'RESULT.json').write_text(json.dumps(report))
   start=dict(schema='ACTUAL_DUT_POPEN_V1',binary_sha256=H,runtime_sha256=H,pid=12,consumer_pid=11,consumer_start_tick=42,inherited_group=11,inherited_session=11)
   (p/'profile1.started.json').write_text(json.dumps(start))
   identity=dict(pid=11,start=42,group=11)
   outer=dict(worker_started=True,native_exit=2,errors=[],owner_identity=identity,cleanup_proof=dict(status='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP',owner_identity=identity,session=11),log_capture=dict(pipe_eof_observed=True,gzip_finalized=True))
   op=p/'outer.json';op.write_text(json.dumps(outer))
   result=d.verify(p,1,H,H,H,H,d.pin(op));self.assertTrue(result['qualification']['numerical_pass'])
   report['status']='FAIL_EXACT_REFERENCE';(p/'RESULT.json').write_text(json.dumps(report));outer['native_exit']=1;op.write_text(json.dumps(outer))
   with self.assertRaises(ValueError):d.verify(p,1,H,H,H,H,d.pin(op))
   report['status']='INCOMPLETE';(p/'RESULT.json').write_text(json.dumps(report));outer['native_exit']=2
   outer['log_capture']['pipe_eof_observed']=False;op.write_text(json.dumps(outer))
   with self.assertRaises(ValueError):d.verify(p,1,H,H,H,H,d.pin(op))
 def test_timeout_cannot_promote(self):
  r=row(1);r['error_class']='TimeoutError';self.assertFalse(a.evaluate(r,outer_verified=True)['numerical_pass'])
if __name__=='__main__':unittest.main()
