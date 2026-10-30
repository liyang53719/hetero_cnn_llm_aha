import ast, hashlib, importlib.util, json, pathlib, struct, sys, tempfile, unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'numeric'))
import consumer_owned as c
import moe_score_compare as m

class Tests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.t.name)
  self.data=struct.pack('<I',0x3b800000)*32768
  self.ids=b''.join(struct.pack('<q',i%8) for i in range(1024))
  self.route=b''.join(struct.pack('<Q',(i//8)<<34|(i%8)<<31|(i%8)<<23|(i//8)) for i in range(1024))
  self.log='HOST_ROUTER_RAW_SCORE_V1 profile=3 transaction=0 owner=9 values=32768 bytes=131072 dtype=FP32 source=SELECTION_INPUT_FIRE terminal=CLEAN coverage=EXACT_ONCE\nCOMPLETE_ORIGINAL_HOST_DDR_REPLAY profile=3 cycles=1\n'
  (self.root/'router_selection_scores.fp32.actual.bin').write_bytes(self.data)
 def tearDown(self):self.t.cleanup()
 def test_full_diagnostics(self):
  r=m.observe(self.root,self.log,3,self.data,self.route,self.ids)
  self.assertEqual(r['full_probabilities']['element_mismatches'],0)
  self.assertEqual(r['full_probabilities']['elements'],32768)
  self.assertFalse(r['numerical_pass'])
 def test_one_ulp(self):
  data=struct.pack('<I',0x3b800001)+self.data[4:]
  r=m.diagnostic(data,self.data)
  self.assertEqual(r['max_ulp_distance'],1);self.assertEqual(r['element_mismatches'],1)
  self.assertGreater(r['max_absolute_error'],0)
 def test_bad_receipts(self):
  for log in ('',self.log+self.log,self.log.replace('transaction=0','transaction=1'),self.log.replace('owner=9','owner=0'),self.log.replace('profile=3','profile=4'),self.log.replace('EXACT_ONCE','PARTIAL'),self.log.replace('32768','32767'),self.log.replace('FP32','BF16'),self.log.splitlines()[0]):
   with self.subTest(log=log),self.assertRaises(ValueError):m.observe(self.root,log,3,self.data,self.route,self.ids)
 def test_bad_file(self):
  p=self.root/'router_selection_scores.fp32.actual.bin'
  p.write_bytes(self.data[:-4])
  with self.assertRaises(ValueError):m.observe(self.root,self.log,3,self.data,self.route,self.ids)
  p.unlink();target=self.root/'other';target.write_bytes(self.data);p.symlink_to(target)
  with self.assertRaises(ValueError):m.observe(self.root,self.log,3,self.data,self.route,self.ids)
 def test_nonfinite_preserved_and_counted(self):
  words=(0x7fc00001,0x7f800000,0xff800000,0xbf800000,0x80000000)
  data=struct.pack('<5I',*words)+self.data[20:]
  self.assertEqual(m.probabilities(data)[:5],list(words))
  r=m.diagnostic(data,self.data)
  self.assertEqual(r['nonfinite_pair_count'],3)
  self.assertEqual(r['actual_value_counts'],dict(nan=1,positive_infinity=1,negative_infinity=1,negative_finite=1,negative_zero=1,above_one_finite=0))
  z=m.diagnostic(struct.pack('<I',0x80000000),bytes(4))
  self.assertEqual(z['element_mismatches'],1);self.assertEqual(z['max_ulp_distance'],0)
  n=m.diagnostic(struct.pack('<I',0x7fc00001),struct.pack('<I',0x7fc00002))
  self.assertIsNone(n['max_absolute_error']);self.assertIsNone(n['max_ulp_distance']);self.assertEqual(n['element_mismatches'],1)
 def reference(self):
  (self.root/'reference_only').mkdir();(self.root/'reference_only/raw.bin').write_bytes(self.data)
  return dict(profile={'profile':3},status='CAPTURED_FRESH_OFFICIAL_FULL_BLOCK_REFERENCE_ONLY',complete_block_tokens=128,exact_baseline_observer_output_equal=True,hardware_executed=False,numerical_comparison_with_hardware=False,router_policy='UNMODIFIED_OFFICIAL_TORCH_TOPK',raw_router_score_observation='ORIGINAL_FORWARD_LOCAL_RETURN_READONLY_PROFILE',no_reference_outputs_or_router_ids_allowed_in_hardware_stimulus=True,tensor_records={m.KEY:dict(shape=[128,256],dtype='torch.float32',bytes=len(self.data),file='reference_only/raw.bin',sha256=m.digest(self.data))})
 def test_reference_contract(self):
  r=self.reference();self.assertEqual(m.reference_probabilities(self.root,r,3),self.data)
  record=r['tensor_records'][m.KEY]
  for k,v in [('shape',[256,128]),('dtype','torch.bfloat16'),('bytes',1),('sha256','0'*64),('file','raw.bin'),('file','reference_only/../raw.bin')]:
   with patch.dict(record,{k:v}),self.assertRaises(ValueError):m.reference_probabilities(self.root,r,3)
  for k,v in [('hardware_executed',True),('router_policy','SMALL_ID'),('exact_baseline_observer_output_equal',False)]:
   with patch.dict(r,{k:v}),self.assertRaises(ValueError):m.reference_probabilities(self.root,r,3)
 def test_parent_symlink_reference_rejected(self):
  r=self.reference();folder=self.root/'reference_only';folder.rename(self.root/'outside');folder.symlink_to(self.root/'outside',target_is_directory=True)
  with self.assertRaises(ValueError):m.reference_probabilities(self.root,r,3)
 def test_selected_id_correspondence(self):
  ref=bytearray(self.data);ref[4:8]=struct.pack('<I',0x3b800001)
  r=m.selected_diagnostics(self.data,bytes(ref),self.route,self.ids)
  self.assertEqual(r['hardware_id_correspondence']['element_mismatches'],1)
  self.assertEqual(r['official_id_correspondence']['element_mismatches'],1)
 def test_guard_not_promoted(self):
  r={'comparisons':{'x':{'byte_mismatches':0}},'router':{k:{'byte_mismatches':0} for k in ('ids','normalized_bf16_weights','bf16_dense_logits')}}
  c.classify_observed_profile(r,True);self.assertEqual(r['status'],'INCOMPLETE');self.assertEqual(len(r['missing_observations']),2)
  r['router']['raw_probability_diagnostics']={'status':'COMPARED_DIAGNOSTIC_ONLY','full_probabilities':{'byte_mismatches':0}}
  c.classify_observed_profile(r,True);self.assertEqual(r['status'],'INCOMPLETE');self.assertFalse(r['numerical_pass']);self.assertEqual(r['missing_observations'],['raw_fp32_selected_topk_scores'])
  r['router']['raw_probability_diagnostics']['full_probabilities']['byte_mismatches']=1
  c.classify_observed_profile(r,True);self.assertEqual(r['observed_subset_status'],'BITWISE_MISMATCH_DIAGNOSTIC')
 def test_original_functions_unchanged(self):
  def funcs(p):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(p.read_text()).body if isinstance(n,ast.FunctionDef)}
  base=funcs(ROOT/'BASE_consumer_owned.py');new=funcs(ROOT/'numeric/consumer_owned.py')
  for name in base:
   if name!='main':self.assertEqual(base[name],new[name],name)
 def test_actual_main_connections_and_permanent_exit2(self):
  tree=ast.parse((ROOT/'numeric/consumer_owned.py').read_text());main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
  calls=[ast.unparse(n.func) for n in ast.walk(main) if isinstance(n,ast.Call)]
  for call in ('resident_helper.compare_full128','moe_helper.reference_probabilities','moe_helper.observe','verify_current_observation_round','classify_observed_profile'):self.assertIn(call,calls)
  self.assertTrue(any(isinstance(n,ast.Raise) and ast.unparse(n.exc)=='SystemExit(2)' for n in ast.walk(main)))
 def test_round_provenance(self):
  binary=self.root/'binary';binary.write_bytes(b'dut')
  runtime=self.root/'runtime';runtime.write_bytes(b'launch')
  log=self.root/'profile3.log';receipt=log.with_suffix('.started.json')
  tick=int(pathlib.Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19])
  proof=dict(schema='ACTUAL_DUT_POPEN_V1',pid=123,consumer_pid=c.os.getpid(),consumer_start_tick=tick,inherited_group=c.os.getpid(),inherited_session=c.os.getpid(),binary_sha256=c.sha(binary),runtime_sha256=c.sha(runtime))
  receipt.write_text(json.dumps(proof))
  with patch.object(c.os,'getpgrp',return_value=c.os.getpid()),patch.object(c.os,'getsid',return_value=c.os.getpid()):
   self.assertEqual(c.verify_current_observation_round(log,binary,runtime)['pid'],123)
   for key,value in [('consumer_pid',0),('consumer_start_tick',0),('binary_sha256','0'*64),('runtime_sha256','0'*64),('inherited_group',0)]:
    changed=dict(proof,**{key:value});receipt.write_text(json.dumps(changed))
    with self.subTest(key=key),self.assertRaises(ValueError):c.verify_current_observation_round(log,binary,runtime)
 def test_full128_resident_shape_hash(self):
  import resident_compare as r
  reference=bytes(128*8960*2);actual=bytes(128*8960*4)
  for stage in ('gate','up'):(self.root/('resident_'+stage+'.fp32.actual.bin')).write_bytes(actual)
  result=r.compare_full128(self.root,r.MARKER,dict(gate=reference,up=reference))
  self.assertEqual(result['resident_gate']['shape'],[128,8960])
  self.assertEqual(result['resident_up']['actual_sha256'],m.digest(actual))
  with self.assertRaises(ValueError):r.compare_full128(self.root,r.MARKER+r.MARKER,dict(gate=reference,up=reference))
 def test_pinned_helpers(self):self.assertEqual(len(c.observation_helpers()),2)
if __name__=='__main__':unittest.main()
