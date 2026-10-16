"""Synthetic stdout/control fixtures only; no Torch or model/native arithmetic."""
from contextlib import contextmanager
from pathlib import Path
import os
import tempfile
import types
import unittest
from unittest.mock import patch,Mock
from . import dispatch_capture as c


class CaptureTests(unittest.TestCase):
    def fixture(self):
        events=[]
        @contextmanager
        def verbose(level):
            events.append(('enter',level))
            try:yield
            finally:events.append(('exit',level))
        backend=types.SimpleNamespace(enabled=True,VERBOSE_ON=1,verbose=verbose)
        return types.SimpleNamespace(backends=types.SimpleNamespace(mkldnn=backend)),events

    def test_scoped_fd_capture_preserves_call_and_modes(self):
        torch,events=self.fixture();parsed=[]
        def parse(raw,*,truncated=False):parsed.append((raw,truncated));return {'fixture':len(raw),'truncated':truncated}
        with tempfile.TemporaryDirectory() as d,patch.object(c,'flush_stdout'), \
                patch.object(c.diagnostic,'parse_verbose',side_effect=parse), \
                patch.object(c.diagnostic,'validate_verbose',side_effect=lambda x:x):
            capture=c.Capture(Path(d)/'private',torch)
            before=os.fstat(1)
            for mode in ('bf16','fp32'):
                with capture.capture(mode):os.write(1,('CONTROL_ONLY_'+mode).encode())
            after=os.fstat(1)
            self.assertEqual((before.st_dev,before.st_ino),(after.st_dev,after.st_ino))
            self.assertEqual(parsed[:2],[(b'CONTROL_ONLY_bf16',False),(b'CONTROL_ONLY_fp32',False)])
            self.assertEqual(set(capture.report()),{'bf16','fp32'})
            self.assertEqual(events,[('enter',1),('exit',1)]*2)
            self.assertIs(torch.backends.mkldnn.enabled,True)
            with self.assertRaises(ValueError):
                with capture.capture('bf16'):pass

    def test_bounded_pipe_drains_excess_without_exposing_payload(self):
        torch,_=self.fixture();parsed=[]
        with tempfile.TemporaryDirectory() as d,patch.object(c,'flush_stdout'),patch.object(c,'LIMIT',64), \
                patch.object(c.diagnostic,'parse_verbose',side_effect=lambda raw,**kw:parsed.append((raw,kw)) or {}):
            capture=c.Capture(Path(d)/'private',torch)
            with capture.capture('bf16'):
                for _ in range(32):os.write(1,b'CONTROL_ONLY'*1024)
            self.assertEqual(len(parsed[0][0]),64)
            self.assertIs(parsed[0][1]['truncated'],True)
            self.assertEqual((Path(d)/'private/bf16.private.log').stat().st_size,64)

    def test_exception_restores_stdout_verbose_and_activity(self):
        torch,events=self.fixture()
        with tempfile.TemporaryDirectory() as d,patch.object(c,'flush_stdout'), \
                patch.object(c.diagnostic,'parse_verbose',return_value={}):
            capture=c.Capture(Path(d)/'private',torch);before=os.fstat(1)
            with self.assertRaisesRegex(RuntimeError,'CONTROL_ONLY'):
                with capture.capture('bf16'):
                    os.write(1,b'private_fixture');raise RuntimeError('CONTROL_ONLY')
            after=os.fstat(1)
            self.assertEqual((before.st_dev,before.st_ino),(after.st_dev,after.st_ino))
            self.assertFalse(capture.active);self.assertEqual(events,[('enter',1),('exit',1)])

    def test_backend_mutation_not_silently_accepted(self):
        torch,_=self.fixture()
        with tempfile.TemporaryDirectory() as d,patch.object(c,'flush_stdout'), \
                patch.object(c.diagnostic,'parse_verbose',return_value={}):
            capture=c.Capture(Path(d)/'private',torch)
            with self.assertRaises(ValueError):
                with capture.capture('bf16'):torch.backends.mkldnn.enabled=False
            self.assertFalse(capture.active)

    def test_private_path_and_mode_guards(self):
        torch,_=self.fixture()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'exists').mkdir();(root/'link').symlink_to(root/'exists')
            for name in ('exists','link'):
                with self.assertRaises(ValueError):c.Capture(root/name,torch)
            capture=c.Capture(root/'new',torch)
            for mode in (None,True,'unknown'):
                with self.assertRaises(ValueError):
                    with capture.capture(mode):self.fail('entered')

    def test_read_only_fenv_schema_and_library_order(self):
        good=dict(status='OBSERVED',x87_round=0,sse_round=0,ftz=False,daz=False)
        self.assertEqual(c.validate_fenv(good),good)
        for key,bad in (('x87_round',True),('sse_round',4),('ftz',0),('daz',1)):
            with self.assertRaises(ValueError):c.validate_fenv(dict(good,**{key:bad}))
        with patch.object(c,'fenv_snapshot',side_effect=[good,dict(good,ftz=True),good]), \
                patch.object(c.ctypes,'CDLL') as load:
            result=c.library_fenv('/CONTROL_ONLY/qkv','/CONTROL_ONLY/qk')
        self.assertEqual([call.args[0] for call in load.call_args_list],['/CONTROL_ONLY/qkv','/CONTROL_ONLY/qk'])
        self.assertIs(result['after_qkv']['ftz'],True)
        with patch.object(c.platform,'machine',return_value='unsupported'),patch.object(c.ctypes,'CDLL') as load:
            self.assertEqual(c.fenv_snapshot(),{'status':'UNSUPPORTED'});load.assert_not_called()

if __name__=='__main__':unittest.main()
