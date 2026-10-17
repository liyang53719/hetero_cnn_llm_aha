"""Tiny Python child supervisor tests; never Java/compiler/RTL."""
import os,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import owned_compile as owner
HERE=Path(__file__).resolve().parent
class Tests(unittest.TestCase):
    def child(self,code,work=2):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);c=p/'classes';c.mkdir()
            with (p/'log').open('wb') as log:
                r=owner.execute([sys.executable,'-I','-B','-c',code],cwd=p,classes=c,log=log,
                    cleanup_helper=HERE/'strict_cleanup.py',absolute_stop=time.monotonic()+work+8.5,work_stop=time.monotonic()+work)
            self.assertTrue(r['cleanup_complete']);self.assertEqual((p/'log').stat().st_size,r['log_bytes']);return r
    def test_clean_exit_and_stderr(self):
        r=self.child("import sys; print('hello'); print('err',file=sys.stderr)")
        self.assertEqual(r['exit_code'],0);self.assertIsNone(r['error'])
    def test_nonzero_retained_exit(self):
        r=self.child('raise SystemExit(7)');self.assertEqual(r['exit_code'],7)
    def test_log_hard_cap(self):
        with patch.object(owner,'LOG_LIMIT_BYTES',128):r=self.child("import os;os.write(1,b'x'*8192)")
        self.assertEqual(r['log_bytes'],128);self.assertIn('cap exceeded',r['error'])
    def test_class_tree_sampled_softcap(self):
        with patch.object(owner,'TREE_SOFTCAP_BYTES',128):r=self.child("from pathlib import Path;Path('classes/a.class').write_bytes(b'x'*1024)")
        self.assertIn('softcap exceeded',r['error'])
    def test_timeout_cleanup(self):
        r=self.child('import time;time.sleep(10)',work=.08);self.assertIsNotNone(r['error'])
    def test_child_limits_are_not_rss_claim(self):
        r=self.child("import resource,os;assert resource.getrlimit(resource.RLIMIT_FSIZE)==(50331648,50331648);assert len(os.sched_getaffinity(0))==1")
        self.assertEqual(r['exit_code'],0);self.assertIsNone(r['whole_process_memory_hard_limit'])
    def test_inherited_jvm_options_filtered(self):
        with patch.dict(os.environ,{'JAVA_TOOL_OPTIONS':'bad','_JAVA_OPTIONS':'bad','JDK_JAVA_OPTIONS':'bad','CLASSPATH':'bad'}):
            r=self.child("import os;assert not any(k in os.environ for k in ('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH'))")
        self.assertEqual(r['exit_code'],0)
    def test_tree_symlink_rejected(self):
        r=self.child("from pathlib import Path;Path('classes/bad').symlink_to('/tmp')")
        self.assertIn('symlink',r['error'])
if __name__=='__main__':unittest.main()
