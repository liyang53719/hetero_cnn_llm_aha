import contextlib,hashlib,importlib.util,json,os,pathlib,tempfile,unittest
from unittest.mock import patch
P=pathlib.Path;D=P(__file__).resolve().parent
s=importlib.util.spec_from_file_location('m',D/'controller/deduplicate_pack.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def write(p,v):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2)+'\n');return dict(path=str(p),bytes=p.stat().st_size,sha256=m.sha(p))
def good():return dict(native_exit=0,errors=[],cleanup_proof={'status':m.CLEAN},log_capture={'pipe_eof_observed':True,'gzip_finalized':True})
def fixture(root):
 job=root/'job';B=job/'build/frontend';pack=B/'frozen_artifact';pack.mkdir(parents=True)
 for n in m.BOOT:write(B.parent/('stage_'+n)/'RESULT.json',good())
 for n in m.NATIVE:write(B/n/'RESULT.json',good())
 srcs={'sv':B/'emit_host/compiled-host/HostBlockTopV4.sv','binary':B/'frontend/obj/VHostBlockTopV4'};common={}
 for k,p in srcs.items():
  p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'fixture '+k.encode());dst=pack/('hardware.sv'if k=='sv'else'dut.bin');dst.write_bytes(p.read_bytes());p.chmod(0o600);dst.chmod(0o600);common[k]=dict(path=dst.name,bytes=dst.stat().st_size,sha256=m.sha(dst))
 for k in ('driver','tool_manifest'):
  dst=pack/(k+'.json');write(dst,{'fixture':True});common[k]=dict(path=dst.name,bytes=dst.stat().st_size,sha256=m.sha(dst))
 source=dict(verified_gate_pins={str(srcs['sv']):m.sha(srcs['sv'])},physical_closure=dict(initial_frontend_argv=[str(srcs['sv'])],top_raw_sha256=m.sha(srcs['sv'])),p0_retained_evidence=dict(driver_dependency=dict(binary=dict(path=str(srcs['binary']),bytes=common['binary']['bytes'],sha256=common['binary']['sha256']),host_link_receipt=good())))
 p=pack/'source_manifest.json';write(p,source);common['source_manifest']=dict(path=p.name,bytes=p.stat().st_size,sha256=m.sha(p))
 receipt=dict(status='BINARY_BUILD_ONLY_NO_NUMERICS',source_commit='a'*40,launch_commit='b'*40,tool_manifest_sha256=common['tool_manifest']['sha256'],**{k+'_sha256':common[k]['sha256']for k in ('binary','sv','source_manifest','driver')},phases=[dict(phase=n,supervisor_receipt_sha256=m.canonical(good()),output_sha256=common['binary']['sha256'])for n in m.NATIVE[-5:]])
 p=pack/'build_receipt.json';write(p,receipt);common['build_receipt']=dict(path=p.name,bytes=p.stat().st_size,sha256=m.sha(p));tool=common.pop('tool_manifest');manifest=dict(common=common,tool_manifest=tool,artifact_identity={'source_commit':'a'*40,'launch_commit':'b'*40});v=write(pack/'frozen_artifact.json',manifest)
 r=write(B/'BUILD_ONLY_RESULT.json',dict(status='PASS_BINARY_BUILD_AND_FROZEN_ARTIFACT_ONLY_NO_NUMERICS',scope='CHISEL_TEST_BACKEND_PREPARATION_NOT_FINAL_RTL_REPLAY',artifact=dict(manifest=v,expanded_bytes=sum(x.stat().st_size for x in pack.iterdir()))));return job,B,pack,srcs,r
# All proc observations below are mocks. Never inspect the failing /proc FD.
ss=importlib.util.spec_from_file_location('safe_summary',D/'summarize_same_job.py');summary=importlib.util.module_from_spec(ss);ss.loader.exec_module(summary)
class Tests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=P(self.tmp.name).resolve();self.job,self.B,self.pack,self.srcs,self.r=fixture(self.root)
 def tearDown(self):self.tmp.cleanup()
 def runit(self):return m.run(P(self.r['path']),self.r['sha256'],self.job,0)
 def artifacts(self):return [*self.srcs.values(),self.pack/'hardware.sv',self.pack/'dut.bin']
 def noop(self,exception,call=1):
  before={p:(m.identity(p),p.read_bytes())for p in self.artifacts()};counter=0
  def scan(*args):
   nonlocal counter
   counter+=1
   if counter==call:raise exception
   return dict(scope='MOCK_COMPLETE_CENSUS',processes=1)
  with patch.object(m,'_writer_census',side_effect=scan),patch.object(m.os,'link',wraps=m.os.link)as link:report=self.runit();link.assert_not_called()
  self.assertEqual(report['status'],'NO_OP_WRITER_CENSUS_UNAVAILABLE');self.assertEqual(report['logical_saved_bytes'],0);self.assertIs(report['writer_census']['writers_absent_established'],False);self.assertIs(report['artifact_mutation_started'],False)
  self.assertEqual(before,{p:(m.identity(p),p.read_bytes())for p in self.artifacts()});self.assertFalse(list(self.job.glob('PACK_DEDUP_BACKUP_*')))
  safe=summary.pack_deduplication(self.job);self.assertEqual(safe['status'],report['status']);self.assertEqual(safe['writer_census']['reason'],report['writer_census']['reason']);self.assertNotIn('/proc',json.dumps(safe));return report
 def test_permission_noop_preserves_all_artifact_metadata(self):self.assertEqual(self.noop(PermissionError('restricted private path'))['writer_census']['reason'],'PERMISSION_DENIED')
 def test_disappeared_fd_is_inconclusive_not_writer_absence(self):self.assertEqual(self.noop(FileNotFoundError('gone'))['writer_census']['reason'],'PROCESS_OR_FD_DISAPPEARED')
 def test_disappeared_process(self):self.noop(ProcessLookupError('gone'))
 def test_other_io_noop(self):self.assertEqual(self.noop(OSError('injected IO'))['writer_census']['reason'],'IO_UNAVAILABLE')
 def test_deadline_noop(self):self.noop(m.WriterCensusUnavailable('DEADLINE'))
 def test_process_cap_noop(self):self.noop(m.WriterCensusUnavailable('PROCESS_CAP'))
 def test_fd_cap_noop(self):self.noop(m.WriterCensusUnavailable('FD_CAP'))
 def test_maps_cap_noop(self):self.noop(m.WriterCensusUnavailable('MAPS_CAP'))
 def test_malformed_metadata_noop(self):self.noop(m.WriterCensusUnavailable('MALFORMED_PROC_METADATA'))
 def test_prelink_inconclusive_before_first_mutation_noop(self):self.noop(PermissionError('injected'),call=2)
 def test_observed_writer_is_not_masked(self):
  with patch.object(m,'_writer_census',side_effect=ValueError('observed writable descriptor')),patch.object(m.os,'link')as link:
   with self.assertRaisesRegex(ValueError,'observed writable'):self.runit()
   link.assert_not_called()
  self.assertFalse((self.job/'PACK_DEDUPLICATION.json').exists())
 def test_unknown_value_error_not_masked(self):
  with patch.object(m,'_writer_census',side_effect=ValueError('unexpected bug')):
   with self.assertRaisesRegex(ValueError,'unexpected bug'):self.runit()
 def test_artifact_admission_failure_not_noop(self):
  self.srcs['sv'].write_bytes(b'changed')
  with patch.object(m,'_writer_census',side_effect=PermissionError('injected'))as scan:
   with self.assertRaises(ValueError):self.runit()
   scan.assert_not_called()
 def rollback(self,call):
  before={p:(m.identity(p)[:2],p.read_bytes())for p in self.artifacts()};counter=0
  def scan(*args):
   nonlocal counter
   counter+=1
   if counter==call:raise PermissionError('injected private path')
   return dict(scope='MOCK_COMPLETE_CENSUS',processes=1)
  with patch.object(m,'_writer_census',side_effect=scan):
   with self.assertRaises(m.WriterCensusUnavailable):self.runit()
  self.assertEqual(before,{p:(m.identity(p)[:2],p.read_bytes())for p in self.artifacts()});r=json.loads((self.job/'PACK_DEDUPLICATION.json').read_text());self.assertEqual(r['status'],'ROLLED_BACK');self.assertIs(r['artifact_mutation_started'],True);self.assertEqual(r['logical_saved_bytes'],0);self.assertFalse(list(self.job.glob('PACK_DEDUP_BACKUP_*')));self.assertFalse(list(self.pack.glob('.dedup_*')))
  safe=summary.pack_deduplication(self.job);self.assertEqual(safe['status'],'ROLLED_BACK');self.assertEqual(safe['writer_census']['reason'],'PERMISSION_DENIED')
 def test_postlink_inconclusive_rolls_back_not_noop(self):self.rollback(3)
 def test_second_pair_prelink_inconclusive_rolls_back(self):self.rollback(4)
 def test_second_pair_postlink_inconclusive_rolls_back(self):self.rollback(5)
 def test_final_census_inconclusive_rolls_back(self):self.rollback(6)
 def test_complete_mock_census_retains_original_transaction(self):
  with patch.object(m,'_writer_census',return_value=dict(scope='MOCK_COMPLETE_CENSUS',processes=1)):r=self.runit()
  self.assertEqual(r['status'],'COMPLETE');self.assertTrue(os.path.samefile(self.srcs['binary'],self.pack/'dut.bin'))
 def test_safe_summary_refuses_false_absence(self):
  self.noop(PermissionError('private'));p=self.job/'PACK_DEDUPLICATION.json';r=json.loads(p.read_text());r['writer_census']['writers_absent_established']=True;p.write_text(json.dumps(r));self.assertEqual(summary.pack_deduplication(self.job)['status'],'INVALID_FIELDS')
 def test_safe_summary_refuses_mutated_noop(self):
  self.noop(PermissionError('private'));p=self.job/'PACK_DEDUPLICATION.json';r=json.loads(p.read_text());r['artifact_mutation_started']=True;p.write_text(json.dumps(r));self.assertEqual(summary.pack_deduplication(self.job)['status'],'INVALID_FIELDS')
 def test_safe_summary_refuses_complete_with_unavailable_census(self):
  self.noop(PermissionError('private'));p=self.job/'PACK_DEDUPLICATION.json';r=json.loads(p.read_text());r['status']='COMPLETE'
  for row in r['pairs']:row['status']='BOTH_PATHS_RETAINED_SAME_INODE'
  p.write_text(json.dumps(r));self.assertEqual(summary.pack_deduplication(self.job)['status'],'INVALID_FIELDS')
 def test_safe_summary_refuses_rollback_without_mutation(self):
  self.noop(PermissionError('private'));p=self.job/'PACK_DEDUPLICATION.json';r=json.loads(p.read_text());r['status']='ROLLED_BACK';p.write_text(json.dumps(r));self.assertEqual(summary.pack_deduplication(self.job)['status'],'INVALID_FIELDS')
if __name__=='__main__':unittest.main()
