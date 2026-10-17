import json,os,sys,tempfile,time,unittest,signal,io,tarfile
import verify_artifact as va
from pathlib import Path
import bounded_run as b,export_source as e
import preprocess_closure as pc
class Bounds(unittest.TestCase):
 def run_child(self,code,limit=1024,seconds=2):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);r=b.execute([sys.executable,'-c',code],cwd=p,env={'PATH':'/usr/bin:/bin'},out=p/'o',err=p/'e',root=p,absolute_stop=time.monotonic()+15,stage_stop=time.monotonic()+seconds,stdout_limit=limit)
   self.assertTrue(r['cleanup_complete']);self.assertEqual(r['cleanup_scope'],'ANCHORED_ORIGINAL_GROUP_AND_OBSERVED_IDENTITIES_ONLY');return r
 def test_clean_exit(self):self.assertEqual(self.run_child('print("ok")')['exit'],0)
 def test_output_rejection(self):self.assertIsNotNone(self.run_child('print("x"*1024)',limit=8)['error'])
 def test_timeout_cleanup(self):self.assertIsNotNone(self.run_child('import time;time.sleep(3)',seconds=.2)['error'])
 def test_helper_pin(self):self.assertEqual(b.helper(Path(b.__file__).with_name('strict_cleanup.py')).SOURCE_SHA256,b.HELPER_SHA)
 def test_filelist(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'x.sv').write_text('module x;endmodule');(p/'inc').mkdir();f=p/'list';f.write_text('+define+X\n+incdir+@ROOT@/inc\n@ROOT@/x.sv\n');pc.parse_filelist(f,p)
   for bad in ['@ROOT@/missing.sv','/tmp/out.sv','@ROOT@/../escape.sv','+incdir+@ROOT@/missing']:
    f.write_text(bad)
    with self.assertRaises(ValueError):pc.parse_filelist(f,p)
 def test_export_symlink_reject(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'COMMITS.json').write_text(json.dumps({'idma':e.PIN,**e.DEPS}));(p/'SHA256SUMS.json').write_text('{}');(p/'link').symlink_to('/tmp',target_is_directory=True)
   with self.assertRaises(ValueError):e.verify_export(p)
 def test_nested_manifest_reject(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'COMMITS.json').write_text(json.dumps({'idma':e.PIN,**e.DEPS}));(p/'SHA256SUMS.json').write_text('{}');(p/'nested').mkdir();(p/'nested/SHA256SUMS.json').write_text('{}')
   with self.assertRaises(ValueError):e.verify_export(p)
 def test_open_failure_restores_signal_mask(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'e').write_text('existing');before=signal.pthread_sigmask(signal.SIG_BLOCK,set())
   with self.assertRaises(FileExistsError):b.execute([sys.executable,'-c','pass'],cwd=p,env={},out=p/'o',err=p/'e',root=p,absolute_stop=time.monotonic()+15,stage_stop=time.monotonic()+2)
   self.assertEqual(signal.pthread_sigmask(signal.SIG_BLOCK,set()),before)
   self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))
 def test_worktree_external_python_link_allowed(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'python').symlink_to(sys.executable)
   u=b.tree_usage(p);self.assertEqual(u['symlinks']['external'],1)
 def test_tree_scan_deadline(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'x').write_text('x')
   with self.assertRaises(TimeoutError):b.tree_bytes(p,time.monotonic()-1)
 def test_safe_projection_drops_host_identity(self):
  r={k:None for k in va.TOP_KEYS};r['stages']=[{'exit':0,'cleanup_proof':{'boot_id':'secret-boot','pid':123,'monotonic':999},'cwd':'/tmp/secret'}]
  t={'bender':{'path':'/tmp/secret','sha256':'a','archive_sha256':'b','url':'https://example.test'}}
  result=json.dumps(va.projection(r,t,10))
  for forbidden in ['secret','boot_id','monotonic','"pid"','"cwd"','"path"']:self.assertNotIn(forbidden,result)
 def test_expired_verify_fails_closed(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'receipt.json').write_text(json.dumps({'deadline_monotonic':time.monotonic()-1}))
   with self.assertRaises(TimeoutError):va.main(p,p/'tools.json')
   self.assertFalse((p/'SAFE_IDENTITY.json').exists());self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))
 def test_exact_two_exclusions(self):
  bio=io.BytesIO()
  with tarfile.open(fileobj=bio,mode='w') as tf:
   for name,pin in e.EXCLUDED_SYMLINKS.items():
    member=tarfile.TarInfo(name);member.type=tarfile.SYMTYPE;member.linkname=pin['target'];tf.addfile(member)
   member=tarfile.TarInfo('keep.txt');member.size=2;tf.addfile(member,io.BytesIO(b'ok'))
  with tempfile.TemporaryDirectory() as d:
   out=Path(d)/'export';e.unpack_archive(bio.getvalue(),out,e.EXCLUDED_SYMLINKS)
   self.assertEqual((out/'keep.txt').read_text(),'ok');self.assertFalse(any(p.is_symlink() for p in out.rglob('*')))
 def test_unknown_symlink_rejected(self):
  bio=io.BytesIO()
  with tarfile.open(fileobj=bio,mode='w') as tf:
   member=tarfile.TarInfo('other');member.type=tarfile.SYMTYPE;member.linkname='target';tf.addfile(member)
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(ValueError):e.unpack_archive(bio.getvalue(),Path(d)/'export')
 def test_include_closure(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'top.sv').write_text('`include "a.svh"\n');(root/'a.svh').write_text('`include "b.svh"\n');(root/'b.svh').write_text('// leaf\n')
   self.assertEqual(len(pc.admission([root/'top.sv'],[],root)[0]),3)
   (root/'b.svh').write_text('`include "missing.svh"\n')
   self.assertEqual(pc.admission([root/'top.sv'],[],root)[1],['missing.svh'])
if __name__=='__main__':unittest.main()
