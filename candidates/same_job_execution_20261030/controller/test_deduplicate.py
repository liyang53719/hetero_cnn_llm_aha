import contextlib,hashlib,importlib.util,json,os,pathlib,tempfile,unittest
from unittest.mock import patch
P=pathlib.Path;D=P(__file__).resolve().parent
s=importlib.util.spec_from_file_location('m',D/'deduplicate_pack.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
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
class Tests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=P(self.tmp.name).resolve();self.job,self.B,self.pack,self.srcs,self.r=fixture(self.root)
 def tearDown(self):self.tmp.cleanup()
 def runit(self):return m.run(P(self.r['path']),self.r['sha256'],self.job,0)
 def test_complete_actual_small_files(self):
  before={x.name:m.sha(x)for x in self.pack.iterdir()};r=self.runit();self.assertEqual(r['status'],'COMPLETE');self.assertEqual(r['logical_saved_bytes'],sum(x.stat().st_size for x in self.srcs.values()));self.assertEqual(before,{x.name:m.sha(x)for x in self.pack.iterdir()});self.assertTrue(os.path.samefile(self.srcs['binary'],self.pack/'dut.bin'));self.assertEqual(len(list(self.pack.iterdir())),7)
 def test_mode_noop_no_chmod(self):
  self.srcs['binary'].chmod(0o755);before=m.identity(self.pack/'dut.bin');r=self.runit();self.assertEqual(r['status'],'NO_OP_MODE_MISMATCH');self.assertEqual(m.identity(self.pack/'dut.bin'),before);self.assertEqual(m.identity(self.srcs['binary'])[3],0o755)
 def test_bad_hash(self):
  self.srcs['sv'].write_bytes(b'wrong');self.assertRaises(ValueError,self.runit)
 def test_preexisting_hardlink(self):
  os.link(self.srcs['sv'],self.job/'alias');self.assertRaises(ValueError,self.runit)
 def test_symlink(self):
  p=self.pack/'hardware.sv';p.unlink();p.symlink_to(self.srcs['sv']);self.assertRaises(ValueError,self.runit)
 def test_missing_cleanup(self):
  write(self.B/'host_link/RESULT.json',dict(good(),cleanup_proof=None));self.assertRaises(ValueError,self.runit)
 def test_wrong_phase_receipt(self):
  write(self.B/'host_archive/RESULT.json',dict(good(),changed=True));self.assertRaises(ValueError,self.runit)
 def test_writer_rejected_real_fd(self):
  with self.srcs['sv'].open('r+b'):self.assertRaises(ValueError,self.runit)
 def test_lock_busy(self):
  with m.locks([self.job/'exclusive.lock']):self.assertRaises(BlockingIOError,self.runit)
 def test_journal_blocks_second_run(self):
  self.runit();self.assertRaises(ValueError,self.runit)
 def test_cross_device_rejected(self):
  real=m.identity
  def fake(p):
   v=real(p);return(v[0]+1,*v[1:])if P(p)==self.pack/'hardware.sv'else v
  with patch.object(m,'identity',side_effect=fake):self.assertRaises(ValueError,self.runit)
 def test_failure_second_pair_rolls_both_back(self):
  original={x:m.identity(x)[:2]for x in self.pack.iterdir()};real=os.link
  def fail(src,dst,**kw):
   if P(dst).name=='.dedup_dut.bin':raise OSError('injected link failure')
   return real(src,dst,**kw)
  with patch.object(m.os,'link',side_effect=fail):self.assertRaises(OSError,self.runit)
  self.assertEqual(original,{x:m.identity(x)[:2]for x in self.pack.iterdir()});self.assertEqual(json.loads((self.job/'PACK_DEDUPLICATION.json').read_text())['status'],'ROLLED_BACK');self.assertFalse(list(self.job.glob('PACK_DEDUP_BACKUP_*')))
 def test_changed_inode_before_replace_rejected(self):
  real=m.writers_absent;calls=0
  def inject(paths,*a,**kw):
   nonlocal calls
   calls+=1
   if calls==3:self.srcs['sv'].write_bytes(b'changed')
   return real(paths,*a,**kw)
  with patch.object(m,'writers_absent',side_effect=inject):self.assertRaises(ValueError,self.runit)
  self.assertEqual((self.pack/'hardware.sv').read_bytes(),b'fixture sv');self.assertTrue((self.pack/'.dedup_hardware.sv').exists());self.assertEqual(json.loads((self.job/'PACK_DEDUPLICATION.json').read_text())['status'],'RECOVERY_REQUIRED') # changed temp/source retained; no blind removal
 def test_symlink_parent_before_lock_creation(self):
  alias=self.root/'alias';alias.symlink_to(self.job,target_is_directory=True)
  self.assertRaises(ValueError,m.run,alias/'build/frontend/BUILD_ONLY_RESULT.json',self.r['sha256'],alias,0)
  self.assertFalse((self.job/'exclusive.lock').exists())
 def test_foreign_same_bytes_temporary_not_deleted(self):
  real=m.os.replace
  def fail(src,dst):
   if P(src).name=='.dedup_hardware.sv':
    q=P(src);data=q.read_bytes();q.unlink();q.write_bytes(data);raise OSError('foreign same-byte temporary')
   return real(src,dst)
  with patch.object(m.os,'replace',side_effect=fail):self.assertRaises(ValueError,self.runit)
  self.assertTrue((self.pack/'.dedup_hardware.sv').exists());self.assertEqual(json.loads((self.job/'PACK_DEDUPLICATION.json').read_text())['status'],'RECOVERY_REQUIRED')
 def test_dangling_journal_rejected(self):
  (self.job/'PACK_DEDUPLICATION.json').symlink_to(self.job/'missing');self.assertRaises(ValueError,self.runit);self.assertTrue((self.job/'PACK_DEDUPLICATION.json').is_symlink())
 def test_foreign_owner_rejected(self):
  real=m.identity
  def fake(p):
   v=list(real(p))
   if P(p)==self.srcs['sv']:v[6]+=1
   return tuple(v)
  with patch.object(m,'identity',side_effect=fake):self.assertRaises(ValueError,self.runit)
  self.assertFalse((self.job/'PACK_DEDUPLICATION.json').exists())
 def test_different_group_rejected(self):
  real=m.identity
  def fake(p):
   v=list(real(p))
   if P(p)==self.pack/'hardware.sv':v[7]+=1
   return tuple(v)
  with patch.object(m,'identity',side_effect=fake):self.assertRaises(ValueError,self.runit)
  self.assertFalse((self.job/'PACK_DEDUPLICATION.json').exists())
 def test_terminal_journal_appears_before_lock_acquisition(self):
  original=m.locks;marker=b'{"status":"NO_OP_MODE_MISMATCH","prior":true}\n';before=m.identity(self.pack/'dut.bin')
  @contextlib.contextmanager
  def raced(paths):
   with original(paths):
    (self.job/'PACK_DEDUPLICATION.json').write_bytes(marker)
    yield
  with patch.object(m,'locks',raced):self.assertRaises(ValueError,self.runit)
  self.assertEqual((self.job/'PACK_DEDUPLICATION.json').read_bytes(),marker);self.assertEqual(m.identity(self.pack/'dut.bin'),before)
 def test_flow_order(self):
  s=(D/'flow.py').read_text();self.assertLess(s.index('duplicate.run('),s.index("archives=job/'runs/archives/output'"));self.assertIn("code==0",s);self.assertIn("pins.get(str(D/'deduplicate_pack.py'))",s)
if __name__=='__main__':unittest.main()
