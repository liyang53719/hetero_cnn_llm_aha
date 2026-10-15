import contextlib
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from candidates.qwen2_m16_stage_diagnostic import supervise as S

class TestSupervisor(unittest.TestCase):
    def run_child(self,script,*,base=None,wall=5):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory) if base is None else base
            with contextlib.redirect_stdout(io.StringIO()):
                result=S.supervise([sys.executable,'-B','-c',script],root,'MODEL',test_limits=(10,wall))
            return result,json.loads((root/'model.SUPERVISOR.json').read_text())
    def test_complete_and_nonzero(self):
        for code in (0,3):
            result,receipt=self.run_child('raise SystemExit('+str(code)+')')
            self.assertEqual(receipt['returncode'],code)
            self.assertEqual(result,0 if code==0 else 1)
            self.assertFalse(receipt['acceptance']);self.assertIsNone(receipt['hardware_cycles'])
    def test_timeout(self):
        result,receipt=self.run_child('import time;time.sleep(20)',wall=2.2)
        self.assertEqual(result,1);self.assertEqual(receipt['stop_reason'],'WALL_BUDGET')
        self.assertLess(receipt['wall_seconds'],2.2)
    def test_timeout_cleans_descendant_group(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);pid_file=base/'grandchild.pid'
            script=('import subprocess,sys,time,pathlib;'
                'p=subprocess.Popen([sys.executable,"-B","-c","import time;time.sleep(20)"]);'
                f'pathlib.Path({str(pid_file)!r}).write_text(str(p.pid));time.sleep(20)')
            result,receipt=self.run_child(script,base=base,wall=2.5)
            self.assertEqual(result,1);self.assertTrue(pid_file.exists())
            stat=Path('/proc')/pid_file.read_text()/'stat'
            if stat.exists():self.assertEqual(stat.read_text().split(') ',1)[1].split()[0],'Z')
    def test_duplicate_and_unknown_phase(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);(base/'model.SUPERVISOR.json').write_text('{}')
            with patch.object(S.subprocess,'Popen',side_effect=AssertionError('must not spawn')):
                with self.assertRaises(ValueError):S.supervise([],base,'MODEL')
                with self.assertRaises(ValueError):S.supervise([],base,'OTHER')
    def test_spawn_signal_window(self):
        original=subprocess.Popen
        for sig in (signal.SIGTERM,signal.SIGHUP,signal.SIGINT):
            children=[]
            def spawn(*args,**kwargs):
                child=original(*args,**kwargs);children.append(child)
                os.kill(os.getpid(),sig);return child
            with patch.object(S.subprocess,'Popen',side_effect=spawn):
                result,receipt=self.run_child('import time;time.sleep(20)')
            self.assertEqual(result,1);self.assertIsNotNone(children[0].poll())
            self.assertEqual(receipt['stop_reason'],'SUPERVISOR_INTERRUPTED_OR_ERROR')
    def test_heartbeat_failure_still_reaps(self):
        original=subprocess.Popen;children=[]
        def spawn(*args,**kwargs):
            child=original(*args,**kwargs);children.append(child);return child
        original_atomic=S.atomic
        def write(path,value):
            if value['status']=='RUNNING':raise OSError('private diagnostic error')
            return original_atomic(path,value)
        with patch.object(S.subprocess,'Popen',side_effect=spawn),patch.object(S,'atomic',side_effect=write):
            result,receipt=self.run_child('import time;time.sleep(20)')
        self.assertEqual(result,1);self.assertIsNotNone(children[0].poll())
        self.assertEqual(receipt['error_class'],'OSError');self.assertNotIn('private',json.dumps(receipt))
    def test_default_and_reference_order(self):
        with contextlib.redirect_stdout(io.StringIO()) as capture:self.assertEqual(S.main([]),0)
        self.assertEqual(json.loads(capture.getvalue())['status'],'NOT_EXECUTED')
        with tempfile.TemporaryDirectory() as directory,patch.object(S,'BASE',Path(directory)),patch.object(S,'supervise',side_effect=AssertionError('no launch')):
            with self.assertRaises(FileNotFoundError):S.main(['--execute','--phase','REFERENCE'])
    def test_final_record_reserve(self):
        with patch.object(S,'output_bytes',return_value=S.OUTPUT-1024):
            result,receipt=self.run_child('pass')
        self.assertEqual(result,1)
        self.assertIn(receipt['stop_reason'],('FINAL_RECORD_OUTPUT_RESERVE','OBSERVED_OUTPUT_BUDGET'))
    def test_record_size_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):S.atomic(Path(directory)/'r.json',{'x':'x'*8192})
    def test_output_alias_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);(base/'alias').symlink_to('/tmp')
            with self.assertRaises(ValueError):S.output_bytes(base)

if __name__=='__main__':unittest.main()
