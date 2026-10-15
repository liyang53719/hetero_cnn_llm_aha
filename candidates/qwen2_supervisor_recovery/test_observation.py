import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from . import observation as o, launch

class ObserverTests(unittest.TestCase):
    def test_atomic_failure_preserves_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.HEARTBEAT.json';o.save(p,{'acceptance':False})
            with patch.object(o.os,'replace',side_effect=OSError('injected')):
                with self.assertRaises(OSError):o.save(p,{'seq':2})
            self.assertEqual(json.loads(p.read_text()),{'acceptance':False})

    def test_stage_last_line_partial_and_missing(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'PROGRESS.jsonl';self.assertEqual(o.stage(p)['state'],'MISSING')
            p.write_text('{"stage":"ffn"}\n');self.assertEqual(o.stage(p)['stage'],'ffn')
            p.write_text('{"stage":');self.assertEqual(o.stage(p)['state'],'UNREADABLE_OR_PARTIAL')

    def test_real_signals_restore_handlers(self):
        for n in (signal.SIGTERM,signal.SIGHUP,signal.SIGINT):
            before=signal.getsignal(n);scope=o.SignalScope();scope.start()
            try:
                os.kill(os.getpid(),n)
                with self.assertRaises(o.ObservedSignal):scope.check()
            finally:scope.stop()
            self.assertEqual(signal.getsignal(n),before)

    def test_cleanup_ignores_repeated_signals(self):
        scope=o.SignalScope();scope.start()
        try:
            scope.cleaning()
            for n in (signal.SIGTERM,signal.SIGHUP,signal.SIGINT):
                os.kill(os.getpid(),n)
        finally:scope.stop()

    def test_postspawn_save_failure_reaps_worker(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out=root/'attempt';fake=root/'fake.py'
            fake.write_text('import time\ntime.sleep(20)\n')
            limits=dict(outer_wall_seconds=8,poll_seconds=.01,rss_bytes=1<<28,output_bytes=1<<20,log_bytes=1<<20)
            real_save=launch.save;failed=[]
            def save_once(path,value):
                if str(path).endswith('.LAUNCH.json') and value.get('pid') and not failed:
                    failed.append(True);raise OSError('postspawn disk failure')
                return real_save(path,value)
            with patch.object(launch.gates,'require_review'),patch.object(launch.gates,'require_budget',return_value=limits),patch.object(launch.gates,'data_path',return_value=root/'data'),patch.object(launch.gates,'reference_path'),patch.object(launch.gates,'fresh_output'),patch.object(launch.runner,'__file__',str(fake)),patch.object(launch,'save',side_effect=save_once):
                self.assertEqual(launch.supervise(out,'data','reference','0'*64),1)
            receipt=json.loads((root/'attempt.LAUNCH.json').read_text())
            self.assertEqual(receipt['failure_kind'],'SUPERVISOR_EXCEPTION')
            self.assertFalse(receipt['cleanup_incomplete'])
            self.assertLess(receipt['returncode'],0)

    def test_signal_inside_popen_assignment_window_reaps(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out=root/'attempt';fake=root/'fake.py'
            fake.write_text('import time\ntime.sleep(20)\n')
            limits=dict(outer_wall_seconds=8,poll_seconds=.01,rss_bytes=1<<28,output_bytes=1<<20,log_bytes=1<<20)
            real_popen=launch.subprocess.Popen;children=[]
            def interrupted_popen(*args,**kwargs):
                child=real_popen(*args,**kwargs);children.append(child)
                os.kill(os.getpid(),signal.SIGTERM)
                return child
            with patch.object(launch.gates,'require_review'),patch.object(launch.gates,'require_budget',return_value=limits),patch.object(launch.gates,'data_path',return_value=root/'data'),patch.object(launch.gates,'reference_path'),patch.object(launch.gates,'fresh_output'),patch.object(launch.runner,'__file__',str(fake)),patch.object(launch.subprocess,'Popen',side_effect=interrupted_popen):
                self.assertEqual(launch.supervise(out,'data','reference','0'*64),1)
            self.assertLess(children[0].returncode,0)
            receipt=json.loads((root/'attempt.LAUNCH.json').read_text())
            self.assertFalse(receipt['cleanup_incomplete'])
            self.assertEqual(receipt['failure_kind'],'SUPERVISOR_EXCEPTION')

    def test_missing_review_blocks_spawn(self):
        with patch.object(launch.subprocess,'Popen') as popen:
            with self.assertRaises(ValueError):launch.supervise('not_output','not_data','not_reference','0'*64)
            popen.assert_not_called()

    def test_real_fake_worker_term_cleanup(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out=root/'attempt';fake=root/'fake.py'
            fake.write_text('import os,signal,time\ntime.sleep(.1)\nos.kill(os.getppid(),signal.SIGTERM)\ntime.sleep(20)\n')
            limits=dict(outer_wall_seconds=8,poll_seconds=.01,rss_bytes=1<<28,output_bytes=1<<20,log_bytes=1<<20)
            with patch.object(launch.gates,'require_review'),patch.object(launch.gates,'require_budget',return_value=limits),patch.object(launch.gates,'data_path',return_value=root/'data'),patch.object(launch.gates,'reference_path'),patch.object(launch.gates,'fresh_output'),patch.object(launch.runner,'__file__',str(fake)):
                self.assertEqual(launch.supervise(out,'data','reference','0'*64),1)
            receipt=json.loads((root/'attempt.LAUNCH.json').read_text())
            self.assertEqual(receipt['failure_kind'],'SUPERVISOR_EXCEPTION')
            self.assertIn('ObservedSignal',receipt['supervisor_error'])
            self.assertLess(receipt['returncode'],0)
            self.assertFalse(receipt['cleanup_incomplete'])

    def test_real_fake_workers_exit_records(self):
        # Stub only admission for tiny fake scripts; do not waive real-run gates.
        for exitcode in (0,7):
            with self.subTest(exitcode=exitcode),tempfile.TemporaryDirectory() as d:
                root=Path(d);out=root/'attempt';fake=root/'fake.py'
                fake.write_text('import sys,time\ntime.sleep(.05)\nsys.exit('+str(exitcode)+')\n')
                limits=dict(outer_wall_seconds=8,poll_seconds=.01,rss_bytes=1<<28,output_bytes=1<<20,log_bytes=1<<20)
                with patch.object(launch.gates,'require_review'),patch.object(launch.gates,'require_budget',return_value=limits),patch.object(launch.gates,'data_path',return_value=root/'data'),patch.object(launch.gates,'reference_path'),patch.object(launch.gates,'fresh_output'),patch.object(launch.runner,'__file__',str(fake)):
                    self.assertEqual(launch.supervise(out,'data','reference','0'*64),1)
                receipt=json.loads((root/'attempt.LAUNCH.json').read_text())
                self.assertEqual(receipt['returncode'],exitcode)
                self.assertFalse(receipt['fullblock_pass'])
                heartbeat=json.loads((root/'attempt.HEARTBEAT.json').read_text())
                self.assertFalse(heartbeat['acceptance']);self.assertEqual(heartbeat['returncode'],exitcode)

if __name__=='__main__':unittest.main()
