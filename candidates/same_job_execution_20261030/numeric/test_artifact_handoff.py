"""SYNTHETIC seven tiny text files only. No ELF, download, execution or remote proof."""
import copy,json,pathlib,tempfile,unittest
import artifact_handoff as a

class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.base=pathlib.Path(self.tmp.name);self.root=self.base/'seven';self.root.mkdir()
  self.builder=dict(run_id=123,artifact_name='synthetic',source_commit='a'*40,launch_commit='b'*40,launch_manifest_path='ci_launch/synthetic.json',launch_manifest_blob_sha='c'*40)
  self.executor=dict(schema='CLOUD_EXECUTOR_IDENTITY_V1',source_commit='a'*40,execution_id='11111111-2222-4333-8444-555555555555',boot_id='aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',controller_pid=123,start_tick=456,host_identity_sha256='d'*64,started_monotonic=1)
  self.rows={}
  for k,n in a.NAMES.items():
   if k!='build_receipt':(self.root/n).write_text('SYNTHETIC NOT EXECUTABLE '+k);self.rows[k]=self.pin(self.root/n)
  phases=['archive_bf16_context_lane_cluster16_rev8b_b_candidate_d','archive_qwen2_matrix_command_endpoint_0','archive_TransposedDenseDownOwner','host_archive','host_link']
  self.receipt=dict(status='BINARY_BUILD_ONLY_NO_NUMERICS',scope='CHISEL_TEST_BACKEND_NOT_FINAL_RTL_REPLAY',config_only=False,software_arithmetic_substitution=False,source_commit='a'*40,launch_commit='b'*40,phases=[dict(phase=p,native_exit=0,output_sha256=self.rows['binary']['sha256'],supervisor_receipt_sha256='e'*64)for p in phases],**{k+'_sha256':r['sha256']for k,r in self.rows.items()})
  self.manifest=self.root/'frozen_artifact.json';self.handoff=self.base/'HANDOFF.json'
  self.frozen=dict(schema='FROZEN_FIVE_PROFILE_DUT_ARTIFACT_V2',profiles=list(range(5)),matrix_macs=4096,vector_lanes=32,artifact_identity=self.builder,common={},tool_manifest=self.rows['tool_manifest'])
  self.h=dict(schema='VERIFIED_SEVEN_FILE_BUILD_HANDOFF_V1',scope='BUILD_BYTES_ONLY_REVALIDATE_EXECUTOR_ABI_AND_NUMERICS',builder_identity=self.builder,source_pins_sha256='f'*64,artifact_manifest_sha256='',artifact_expanded_bytes=0,remote_receipt=dict(artifact_id=456,archive_sha256='1'*64,verified_api_receipt_sha256='2'*64,source_commit='a'*40,run_id=123),numerical_pass=False,final_rtl_executed=False)
  self.refresh()
 def tearDown(self):self.tmp.cleanup()
 def pin(self,p):return dict(path=p.name,bytes=p.stat().st_size,sha256=a.sha(p))
 def refresh(self):
  rp=self.root/'build_receipt.json';rp.write_text(json.dumps(self.receipt));self.rows['build_receipt']=self.pin(rp)
  self.frozen['common']={k:r for k,r in self.rows.items()if k!='tool_manifest'}
  self.manifest.write_text(json.dumps(self.frozen));self.h['artifact_manifest_sha256']=a.sha(self.manifest);self.h['artifact_expanded_bytes']=sum(p.stat().st_size for p in self.root.iterdir());self.handoff.write_text(json.dumps(self.h))
 def verify(self):
  self.handoff.write_text(json.dumps(self.h))
  return a.verify(self.handoff,a.sha(self.handoff),self.manifest,a.sha(self.manifest),self.frozen,self.executor)
 def test_synthetic_only_consistent(self):
  r=self.verify();self.assertEqual(r['status'],'VERIFIED_IMPORTED_BUILD_BYTES_NOT_NUMERICAL');self.assertIs(r['numerical_pass'],False);self.assertIs(r['final_rtl_executed'],False)
 def test_changed_payload_bytes(self):
  (self.root/'dut.bin').write_text('changed')
  with self.assertRaises(ValueError):self.verify()
 def test_extra_npz(self):
  (self.root/'local.npz').write_bytes(b'synthetic forbidden')
  with self.assertRaises(ValueError):self.verify()
 def test_symlink(self):
  p=self.root/'dut.bin';outside=self.base/'outside';p.rename(outside);p.symlink_to(outside)
  with self.assertRaises(ValueError):self.verify()
 def test_wrong_builder(self):
  self.h['builder_identity']=dict(self.builder,run_id=124)
  with self.assertRaises(ValueError):self.verify()
 def test_wrong_source(self):
  self.h['remote_receipt']['source_commit']='d'*40
  with self.assertRaises(ValueError):self.verify()
 def test_wrong_executor(self):
  self.executor=dict(self.executor,source_commit='d'*40)
  with self.assertRaises(ValueError):self.verify()
 def test_distinct_executor_receipt_same_source_not_pass(self):
  first=self.verify();self.executor=dict(self.executor,execution_id='22222222-2222-4333-8444-555555555555');second=self.verify()
  self.assertNotEqual(first['executor_identity'],second['executor_identity']);self.assertFalse(second['numerical_pass'])
 def test_numerical_or_rtl_pass_forbidden(self):
  for k in ('numerical_pass','final_rtl_executed'):
   self.h[k]=True
   with self.assertRaises(ValueError):self.verify()
   self.h[k]=False
 def test_builder_receipt_mismatch(self):
  self.receipt['binary_sha256']='3'*64;self.refresh()
  with self.assertRaises(ValueError):self.verify()
 def test_native_failure_and_partial_hardware(self):
  self.receipt['phases'][0]['native_exit']=1;self.refresh()
  with self.assertRaises(ValueError):self.verify()
  self.receipt['phases'][0]['native_exit']=0;self.frozen['matrix_macs']=512;self.refresh()
  with self.assertRaises(ValueError):self.verify()
 def test_bool_native_exit_rejected(self):
  self.receipt['phases'][0]['native_exit']=False;self.refresh()
  with self.assertRaises(ValueError):self.verify()
 def test_bool_profile_rejected(self):
  self.frozen['profiles']=[False,True,2,3,4];self.refresh()
  with self.assertRaises(ValueError):self.verify()
 def test_bool_remote_run_rejected(self):
  self.builder['run_id']=1;self.h['remote_receipt']['run_id']=True;self.refresh()
  with self.assertRaises(ValueError):self.verify()
 def test_oversized_receipt_rejected_before_parsing(self):
  self.receipt['unused_padding']='x'*65536;self.refresh()
  with self.assertRaises(ValueError):self.verify()
 def test_unknown_handoff_field(self):
  self.h['payload']='forbidden'
  with self.assertRaises(ValueError):self.verify()
 def test_extra_or_reordered_phase(self):
  original=copy.deepcopy(self.receipt['phases'])
  self.receipt['phases'].append(dict(original[-1]));self.refresh()
  with self.assertRaises(ValueError):self.verify()
  self.receipt['phases']=list(reversed(original));self.refresh()
  with self.assertRaises(ValueError):self.verify()
 def test_untrusted_hash_refused(self):
  with self.assertRaises(ValueError):a.verify(self.handoff,'0'*64,self.manifest,a.sha(self.manifest),self.frozen,self.executor)
if __name__=='__main__':unittest.main()
