"""Stdlib-only source/identity tests; no numerical imports or model execution."""
import ast
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock
import sys

HERE=Path(__file__).resolve().parent
WORKER_BYTES=13753
WORKER_SHA256='d26bd286857a6bff8217472733658cbdcb1e6590fa095e0d0589bc1be81b8fc4'

def load_worker(raw):
    if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
        raise ValueError('require Python -I -S -B before project loads')
    if type(raw) is not bytes or len(raw) != WORKER_BYTES:
        raise ValueError('fixed worker length')
    if hashlib.sha256(raw).hexdigest() != WORKER_SHA256:
        raise ValueError('fixed worker SHA256')
    module=types.ModuleType('n0_reference_cold')
    module.__file__=str(HERE/'n0_reference.py')
    exec(compile(raw,module.__file__,'exec'),module.__dict__)
    return module

if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('require Python -I -S -B before project loads')
with (HERE/'n0_reference.py').open('rb') as source:
    WORKER_RAW=source.read(WORKER_BYTES+1)
n=load_worker(WORKER_RAW)
REPO=Path(os.environ['N0_REFERENCE_SOURCE_REPO']).resolve()

class Cold(unittest.TestCase):
    def test_loader_bad_length_rejected_before_compile(self):
        with mock.patch('builtins.compile',side_effect=AssertionError('compile reached')) as compile_spy:
            with self.assertRaisesRegex(ValueError,'fixed worker length'):
                load_worker(WORKER_RAW+b' ')
            compile_spy.assert_not_called()
    def test_loader_same_length_bad_sha_rejected_before_compile(self):
        bad=bytes([WORKER_RAW[0]^1])+WORKER_RAW[1:]
        with mock.patch('builtins.compile',side_effect=AssertionError('compile reached')) as compile_spy:
            with self.assertRaisesRegex(ValueError,'fixed worker SHA256'):
                load_worker(bad)
            compile_spy.assert_not_called()
    def test_loader_missing_isolation_rejected_before_compile(self):
        flags=types.SimpleNamespace(isolated=0,no_site=1,dont_write_bytecode=1)
        with mock.patch.object(sys,'flags',flags),mock.patch('builtins.compile',side_effect=AssertionError('compile reached')) as compile_spy:
            with self.assertRaisesRegex(ValueError,'require Python'):
                load_worker(WORKER_RAW)
            compile_spy.assert_not_called()
    def test_loader_executes_checked_buffer_without_file_reopen(self):
        with mock.patch.object(Path,'open',side_effect=AssertionError('file reread')):
            loaded=load_worker(WORKER_RAW)
        self.assertEqual(loaded.F32_SHA256,n.F32_SHA256)
    def test_import_is_cold(self):
        self.assertFalse(any(k.split('.')[0] in ('torch','numpy','transformers') for k in sys.modules))
    def test_pins_and_original_source_closure(self):
        p=n.load_pins(HERE/'PINS.json'); b=n.source_buffers(REPO,p)
        node=n.official_node(b[p['official_class']['path']],p['official_class'])
        self.assertEqual(node.name,'Qwen2RMSNorm')
        self.assertEqual(p['runtime_requirements']['capability'],'AVX512')
    def test_original_whole_node_no_new_formula(self):
        p=n.load_pins(HERE/'PINS.json'); b=n.source_buffers(REPO,p)
        node=n.official_node(b[p['official_class']['path']],p['official_class'])
        self.assertEqual(n.sha(ast.get_source_segment(b[p['official_class']['path']].decode(),node).encode()),'aa3ab02a1c962fe69a38879727e14296bdde68f562f42a383bf0296719d72d9b')
    def test_source_edit_rejected(self):
        p=n.load_pins(HERE/'PINS.json'); raw=(REPO/p['official_class']['path']).read_bytes()
        with self.assertRaises(n.Rejected):n.official_node(raw.replace(b'variance + self.variance_epsilon',b'variance + 1e-5'),p['official_class'])
    def test_pins_edit_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'PINS.json'; p.write_bytes((HERE/'PINS.json').read_bytes()+b' ')
            with self.assertRaises(n.Rejected):n.load_pins(p)
    def test_exact_fixed_output_contract(self):
        p=n.load_pins(HERE/'PINS.json')['output']
        self.assertEqual([p['bytes'],p['native_bytes'],p['shape']],[786432,393216,[1,128,1536]])
        self.assertEqual(p['sha256'],n.F32_SHA256);self.assertEqual(p['native_sha256'],n.BF16_SHA256)
    def test_synthetic_output_both_hashes_required(self):
        with mock.patch.object(n,'sha',side_effect=[n.BF16_SHA256,n.F32_SHA256]):
            self.assertTrue(n.output_identity(bytes(n.BF16_BYTES),bytes(n.F32_BYTES))['accepted'])
    def test_synthetic_output_native_mismatch_rejected(self):
        with mock.patch.object(n,'sha',side_effect=['0'*64,n.F32_SHA256]):
            self.assertFalse(n.output_identity(bytes(n.BF16_BYTES),bytes(n.F32_BYTES))['accepted'])
    def test_synthetic_output_float_mismatch_rejected(self):
        with mock.patch.object(n,'sha',side_effect=[n.BF16_SHA256,'0'*64]):
            self.assertFalse(n.output_identity(bytes(n.BF16_BYTES),bytes(n.F32_BYTES))['accepted'])
    def test_short_output_even_mock_hash_rejected(self):
        with mock.patch.object(n,'sha',side_effect=[n.BF16_SHA256,n.F32_SHA256]):
            self.assertFalse(n.output_identity(b'a',b'b')['accepted'])
    def test_unrelated_fixture_rejected(self):
        self.assertFalse(n.output_identity(b'0'*20,b'0'*40)['accepted'])
    def test_read_size_sha_and_symlink(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'v';p.write_bytes(b'abc');pin={'bytes':3,'sha256':n.sha(b'abc')}
            self.assertEqual(n.read_checked(p,pin),b'abc')
            self.assertEqual(n.read_checked(p,pin,retain=False),pin)
            p.write_bytes(b'abd')
            with self.assertRaises(n.Rejected):n.read_checked(p,pin)
            p.write_bytes(b'abcd')
            with self.assertRaises(n.Rejected):n.read_checked(p,pin)
            q=Path(t)/'link';q.symlink_to(p)
            with self.assertRaises(n.Rejected):n.read_checked(q,pin)
    def test_fifo_not_read(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'fifo';os.mkfifo(p)
            with self.assertRaises(n.Rejected):n.read_checked(p,{'bytes':0,'sha256':n.sha(b'')})
    def test_relative_path_rejected(self):
        with self.assertRaises(n.Rejected):n.path('relative')
    def test_no_execute_is_noop(self):
        with mock.patch.object(n,'recover',side_effect=AssertionError),contextlib.redirect_stdout(io.StringIO()) as s:
            self.assertEqual(n.main([]),0)
        self.assertEqual(s.getvalue(),'N0_REFERENCE_NOT_EXECUTED\n')
    def test_missing_arguments_no_native(self):
        with mock.patch.object(n,'recover',side_effect=AssertionError),contextlib.redirect_stdout(io.StringIO()) as s:
            self.assertEqual(n.main(['--execute']),1)
        self.assertEqual(s.getvalue(),'NOT_COMPLETED:FLAGS\n')
    def test_external_actions_blocked(self):
        for event in ('os.fork','subprocess.Popen','socket.__new__','socket.connect'):
            with self.assertRaises(n.Rejected):n.no_external_actions(event,())
    def test_refuses_output_overwrite(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t);n.write_new(out,'x',b'abc')
            with self.assertRaises(FileExistsError):n.write_new(out,'x',b'def')
            self.assertEqual((out/'x').read_bytes(),b'abc')
    def test_single_official_forward_no_fullblock(self):
        text=(HERE/'n0_reference.py').read_text();tree=ast.parse(text)
        calls=[v for v in ast.walk(tree) if isinstance(v,ast.Call)]
        self.assertEqual(sum(isinstance(v.func,ast.Name) and v.func.id=='norm' for v in calls),1)
        self.assertNotIn('numpy_norm',text);self.assertNotIn('Qwen2MLP',text)
        self.assertNotIn('subprocess.run',text)
    def test_budget_contract(self):
        p=n.load_pins(HERE/'PINS.json')['limits']
        self.assertEqual(p['wall_seconds'],120);self.assertEqual(p['cpu_seconds'],90)
        self.assertEqual(p['threads'],4);self.assertEqual(p['interop_threads'],1)

if __name__=='__main__':unittest.main()
