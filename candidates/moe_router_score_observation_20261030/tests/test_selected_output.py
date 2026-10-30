import pathlib,struct,sys,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'numeric'))
import moe_score_compare as m
import consumer_owned as c
class Tests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.t.name)
  self.data=struct.pack('<I',0x3b800000)*32768;self.scores=struct.pack('<I',0x3b800000)*1024
  self.ids=b''.join(struct.pack('<I',i%8) for i in range(1024));self.official=b''.join(struct.pack('<q',i%8) for i in range(1024))
  self.route=b''.join(struct.pack('<Q',(i//8)<<34|(i%8)<<31|(i%8)<<23|i//8) for i in range(1024))
  for name,data in [('router_selection_scores.fp32.actual.bin',self.data),('router_selected_scores.fp32.actual.bin',self.scores),('router_selected_ids.u32.actual.bin',self.ids)]: (self.root/name).write_bytes(data)
  self.marker='HOST_ROUTER_SELECTED_SCORE_V2 profile=3 transaction=0 owner=9 values=1024 score_bytes=4096 id_bytes=4096 dtype=FP32 index_dtype=UINT32 source=SELECTION_OUTPUT_FIRE terminal=CLEAN coverage=EXACT_ONCE'
  self.log='HOST_ROUTER_RAW_SCORE_V1 profile=3 transaction=0 owner=9 values=32768 bytes=131072 dtype=FP32 source=SELECTION_INPUT_FIRE terminal=CLEAN coverage=EXACT_ONCE\nCOMPLETE_ORIGINAL_HOST_DDR_REPLAY profile=3 cycles=1\n'+self.marker+'\n'
 def tearDown(self):self.t.cleanup()
 def observe(self):return m.observe(self.root,self.log,3,self.data,self.route,self.official)
 def test_actual_output(self):
  r=self.observe()['actual_selected_output'];self.assertEqual(r['status'],'COMPARED_ACTUAL_SELECTION_OUTPUT_DIAGNOSTIC_ONLY');self.assertEqual(r['input_output_score_consistency']['element_mismatches'],0)
  self.assertEqual(r['score_sha256'],m.digest(self.scores));self.assertEqual(r['id_sha256'],m.digest(self.ids))
 def test_missing_does_not_reconstruct(self):
  (self.root/'router_selected_scores.fp32.actual.bin').unlink()
  r=self.observe();self.assertEqual(r['status'],'COMPARED_DIAGNOSTIC_ONLY');self.assertEqual(r['actual_selected_output']['status'],'INCOMPLETE')
 def test_score_not_reconstructed_or_clipped(self):
  actual=struct.pack('<I',0x7fc00001)+self.scores[4:];(self.root/'router_selected_scores.fp32.actual.bin').write_bytes(actual)
  r=self.observe()['actual_selected_output'];self.assertEqual(r['score_sha256'],m.digest(actual))
  self.assertEqual(r['input_output_score_consistency']['element_mismatches'],1);self.assertEqual(r['input_output_score_consistency']['actual_value_counts']['nan'],1)
 def test_id_uniqueness_and_range(self):
  for value in (0,256):
   (self.root/'router_selected_ids.u32.actual.bin').write_bytes(self.ids[:4]+struct.pack('<I',value)+self.ids[8:])
   self.assertEqual(self.observe()['actual_selected_output']['status'],'INCOMPLETE')
 def test_marker_identity_and_coverage(self):
  original=self.log
  for token,replacement in [('owner=9','owner=8'),('1024','1023'),('4096','4092'),('UINT32','INT32'),('SELECTION_OUTPUT_FIRE','SELECTION_INPUT_FIRE')]:
   self.log=original.replace(self.marker,self.marker.replace(token,replacement));self.assertEqual(self.observe()['actual_selected_output']['status'],'INCOMPLETE')
  self.log=original+self.marker;self.assertEqual(self.observe()['actual_selected_output']['status'],'INCOMPLETE')
 def test_internal_not_official_pass(self):
  changed=bytearray(self.data);changed[0:4]=struct.pack('<I',0x3b800001)
  r=m.observe(self.root,self.log,3,bytes(changed),self.route,self.official)['actual_selected_output']
  self.assertEqual(r['input_output_score_consistency']['element_mismatches'],0)
  self.assertEqual(r['official_probability_at_actual_selected_id']['element_mismatches'],1);self.assertFalse(r['numerical_pass'])
 def test_actual_ids_not_replaced_by_official(self):
  swapped=self.ids[4:8]+self.ids[:4]+self.ids[8:]
  (self.root/'router_selected_ids.u32.actual.bin').write_bytes(swapped)
  r=self.observe()['actual_selected_output']
  self.assertEqual(r['id_sha256'],m.digest(swapped));self.assertEqual(r['selected_vs_route_id_mismatches'],2);self.assertEqual(r['selected_vs_official_id_mismatches'],2)
 def test_output_file_shape_and_symlink(self):
  p=self.root/'router_selected_ids.u32.actual.bin';p.write_bytes(self.ids[:-4])
  self.assertEqual(self.observe()['actual_selected_output']['status'],'INCOMPLETE')
  p.unlink();other=self.root/'ids';other.write_bytes(self.ids);p.symlink_to(other)
  self.assertEqual(self.observe()['actual_selected_output']['status'],'INCOMPLETE')
 def test_guard_only_clears_actual_capture(self):
  raw=self.observe();r={'comparisons':{'x':{'byte_mismatches':0}},'router':dict(raw_probability_diagnostics=raw,**{k:{'byte_mismatches':0} for k in ('ids','normalized_bf16_weights','bf16_dense_logits')})}
  c.classify_observed_profile(r,True);self.assertEqual(r['missing_observations'],[]);self.assertEqual(r['status'],'INCOMPLETE');self.assertFalse(r['numerical_pass'])
  raw['actual_selected_output']['status']='INCOMPLETE';c.classify_observed_profile(r,True);self.assertIn('raw_fp32_selected_topk_scores',r['missing_observations'])
if __name__=='__main__':unittest.main()
