"""Offline stdlib-only tests; no network, pip, wheel import or native workload."""
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
from email.message import Message
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
SOURCE_SIZE = 16625
SOURCE_SHA256 = '736ab1d718ffb3fd100fb4e4bb92857fbae0b80bb1fd195c064f36833032050d'
# One read, identity before compile, execution of exactly the verified buffer.
SOURCE_BYTES = (ROOT/'runtime_wheel_gate.py').read_bytes()
if len(SOURCE_BYTES) != SOURCE_SIZE or hashlib.sha256(SOURCE_BYTES).hexdigest() != SOURCE_SHA256:
    raise RuntimeError('COLD_SOURCE_IDENTITY')
gate = types.ModuleType('runtime_wheel_gate')
gate.__file__ = str(ROOT/'runtime_wheel_gate.py')
exec(compile(SOURCE_BYTES, gate.__file__, 'exec'), gate.__dict__)


class Response:
    def __init__(self, body=b'abc', *, status=200, url='https://example.invalid/fixed.whl', headers=None):
        self.body = io.BytesIO(body)
        self.status, self.url = status, url
        self.headers = Message()
        for name, value in (headers or {}).items():
            self.headers[name] = value
        self.read = self.body.read
        self.read1 = self.body.read
    def geturl(self):
        return self.url
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


class Opener:
    def __init__(self, response):
        self.response = response
        self.calls = []
    def open(self, request, timeout):
        self.calls.append((request.full_url, timeout, dict(request.header_items())))
        return self.response


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='.mock-', dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.row = ('fixed', '1', 'fixed.whl', 3, hashlib.sha256(b'abc').hexdigest(),
                    'https://example.invalid/fixed.whl')

    def error(self, code, fn, *args, **kwargs):
        with self.assertRaises(gate.GateError) as e:
            fn(*args, **kwargs)
        self.assertEqual(str(e.exception), code)

    def download(self, response, row=None):
        op = Opener(response)
        got = gate._download_one(op, row or self.row, self.directory, gate.time.monotonic()+10)
        return got, op

    def test_real_frozen_source_offline(self):
        with patch.object(gate.urllib.request, 'build_opener', side_effect=AssertionError('NETWORK')):
            result = gate.source_preflight(ROOT)
        self.assertEqual(result['wheel_bytes'], 215906086)
        self.assertFalse(result['acquired'])
        self.assertEqual(len(gate.WHEELS), 11)
        self.assertEqual(max(x[3] for x in gate.WHEELS), 188943803)
        for row in gate.WHEELS:
            url = urlsplit(row[5])
            self.assertEqual(url.scheme, 'https')
            self.assertIn(url.hostname, {'files.pythonhosted.org', 'download-r2.pytorch.org'})
            self.assertIsNone(url.username)
            self.assertFalse(url.query or url.fragment)

    def test_missing_source_rejected(self):
        self.error('SOURCE_IDENTITY', gate.source_preflight, self.directory)

    def test_source_mutation_rejected(self):
        for name in gate.SOURCE_PINS:
            (self.directory/name).write_bytes((ROOT/name).read_bytes())
        p = self.directory/'WHEELS.json'
        p.write_bytes(p.read_bytes()[:-1]+b'x')
        self.error('SOURCE_IDENTITY', gate.source_preflight, self.directory)

    def test_network_disabled_even_truthy(self):
        with patch.object(gate.urllib.request, 'build_opener', side_effect=AssertionError('NETWORK')):
            for flag in (False, None, 1, 'yes'):
                self.error('EXECUTION_DISABLED', gate.acquire_wheels, ROOT,
                           self.directory/'wheels', execute=flag)
        self.assertFalse((self.directory/'wheels').exists())

    def test_stream_accepts_exact_body(self):
        count, opener = self.download(Response(headers={'Content-Length': '3'}))
        self.assertEqual(count, 3)
        self.assertEqual((self.directory/'fixed.whl').read_bytes(), b'abc')
        self.assertEqual((self.directory/'fixed.whl').stat().st_mode & 0o777, 0o400)
        self.assertEqual(len(opener.calls), 1)
        self.assertLessEqual(opener.calls[0][1], 10)

    def test_stream_accepts_no_content_length(self):
        self.assertEqual(self.download(Response())[0], 3)

    def test_stream_rejects_short(self):
        self.error('WHEEL_SIZE', self.download, Response(b'ab'))

    def test_stream_rejects_oversize_before_write(self):
        self.error('WHEEL_SIZE', self.download, Response(b'abcd'))
        self.assertEqual((self.directory/'fixed.whl').stat().st_size, 0)

    def test_stream_rejects_hash(self):
        self.error('WHEEL_HASH', self.download, Response(b'xyz'))

    def test_stream_rejects_false_length(self):
        self.error('WHEEL_SIZE', self.download, Response(headers={'Content-Length': '4'}))

    def test_stream_rejects_duplicate_length(self):
        r = Response(headers={'Content-Length': '3'})
        r.headers['Content-Length'] = '3'
        self.error('RESPONSE', self.download, r)

    def test_stream_rejects_compression(self):
        self.error('RESPONSE', self.download, Response(headers={'Content-Encoding': 'gzip'}))

    def test_stream_rejects_status(self):
        self.error('RESPONSE', self.download, Response(status=206))

    def test_stream_rejects_response_url(self):
        self.error('RESPONSE', self.download, Response(url='https://example.invalid/other.whl'))

    def test_redirect_rejected(self):
        self.error('REDIRECT', gate._NoRedirect().redirect_request, None, None, 302,
                   'Found', {}, 'https://example.invalid/other.whl')

    def test_deadline_rejected_before_network(self):
        with patch.object(gate.urllib.request, 'build_opener', side_effect=AssertionError('NETWORK')):
            self.error('DEADLINE', gate.acquire_wheels, ROOT, self.directory/'new',
                       execute=True, deadline=gate.time.monotonic()-1)
            self.error('DEADLINE', gate.acquire_wheels, ROOT, self.directory/'new',
                       execute=True, deadline=float('nan'))

    def test_fresh_directory_required(self):
        self.error('NETWORK', gate.acquire_wheels, ROOT, self.directory, execute=True)

    def test_symlink_directory_rejected(self):
        p = self.directory/'link'; p.symlink_to(self.directory, target_is_directory=True)
        self.error('FILESYSTEM', gate._private_dir, p)

    def test_public_acquire_never_retries_and_redacts(self):
        with patch.object(gate.urllib.request, 'build_opener', return_value=object()), \
             patch.object(gate, '_download_one', side_effect=OSError('secret path TOKEN')) as f:
            self.error('NETWORK', gate.acquire_wheels, ROOT, self.directory/'new', execute=True)
        self.assertEqual(f.call_count, 1)

    def test_public_acquire_fixed_table_and_order(self):
        calls = []
        def download(opener, row, directory, deadline):
            calls.append(row)
            return row[3]
        with patch.object(gate.urllib.request, 'build_opener', return_value=object()), \
             patch.object(gate, '_download_one', side_effect=download), \
             patch.object(gate, 'verify_wheels', return_value={'packages':11,'wheel_bytes':215906086}):
            result = gate.acquire_wheels(ROOT, self.directory/'new', execute=True)
        self.assertEqual(tuple(calls), gate.WHEELS)
        self.assertFalse(result['installed'])

    def test_verify_set_extra_rejected(self):
        (self.directory/'evil.whl').write_bytes(b'abc')
        self.error('WHEEL_SET', gate.verify_wheels, self.directory)

    def test_verify_small_fixture(self):
        (self.directory/'fixed.whl').write_bytes(b'abc')
        with patch.object(gate, 'WHEELS', (self.row,)), patch.object(gate, 'WHEEL_BYTES', 3):
            self.assertEqual(gate.verify_wheels(self.directory)['wheel_bytes'], 3)
            (self.directory/'fixed.whl').write_bytes(b'abd')
            self.error('WHEEL_HASH', gate.verify_wheels, self.directory)

    def test_verify_link_rejected(self):
        body = self.directory/'body'; body.write_bytes(b'abc')
        sub = self.directory/'wheels'; sub.mkdir(mode=0o700)
        (sub/'fixed.whl').symlink_to(body)
        with patch.object(gate, 'WHEELS', (self.row,)), patch.object(gate, 'WHEEL_BYTES', 3):
            self.error('FILESYSTEM', gate.verify_wheels, sub)

    def test_python_other_path_rejected(self):
        self.error('PYTHON_IDENTITY', gate.require_current_python, self.directory/'fakepython')

    def test_python_exact_current_observation(self):
        with patch.object(gate.sys, 'version_info', (3,12,14)), \
             patch.object(gate, '_checked_bytes', return_value=b'') as check:
            path = gate.require_current_python()
        self.assertEqual(path, str(Path(gate.sys.executable).resolve()))
        self.assertEqual(check.call_args.args[1:3], (17752, gate.PYTHON_SHA256))

    def test_python_version_rejected(self):
        with patch.object(gate.sys, 'version_info', (3,12,13)):
            self.error('PYTHON_IDENTITY', gate.require_current_python)

    def test_install_only_returns_fixed_local_argv(self):
        wheels = self.directory/'wheels'; wheels.mkdir(mode=0o700)
        with patch.object(gate, 'require_current_python', return_value='/fixed/python'), \
             patch.object(gate, 'verify_wheels', return_value={'packages':11,'wheel_bytes':215906086}):
            argv = gate.install_argv(ROOT, wheels, self.directory/'target')
        self.assertEqual(argv[:4], ['/fixed/python','-I','-m','pip'])
        for option in ('--isolated','--no-index','--no-deps','--only-binary=:all:',
                       '--require-hashes','--no-cache-dir','--no-compile','--no-input'):
            self.assertIn(option, argv)
        self.assertEqual(argv[argv.index('--retries')+1], '0')
        lock = Path(argv[-1]).read_text().splitlines()
        self.assertEqual(len(lock),11)
        for line, row in zip(lock, gate.WHEELS):
            self.assertEqual(line, (wheels/row[2]).as_uri()+' --hash=sha256:'+row[4])
        self.assertNotIn('https:', '\n'.join(argv+lock))

    def test_install_requires_python_before_target(self):
        with patch.object(gate, 'require_current_python', side_effect=gate.GateError('PYTHON_IDENTITY')):
            self.error('PYTHON_IDENTITY', gate.install_argv, ROOT, self.directory, self.directory/'target')
        self.assertFalse((self.directory/'target').exists())

    def test_tree_observation_is_measured_not_install_claim(self):
        (self.directory/'tiny').write_bytes(b'abc')
        with patch.object(gate, 'verify_wheels', return_value={}):
            result = gate.observe_installed_tree(self.directory, self.directory)
        self.assertEqual(result['installed_tree_logical_bytes'],3)
        self.assertEqual(result['status'],'SIZE_ACCEPTED_ONLY')
        self.assertFalse(result['os_hard_size_limit'])
        self.assertFalse(result['native_identity_checked'])

    def test_tree_observation_cap(self):
        (self.directory/'tiny').write_bytes(b'abc')
        with patch.object(gate, 'verify_wheels', return_value={}), \
             patch.object(gate, 'INSTALLED_OBSERVATION_CAP', 2):
            self.error('TREE_LIMIT', gate.observe_installed_tree, self.directory, self.directory)

    def test_walk_error_callback_fails_closed(self):
        def failed_walk(root, *, followlinks, onerror):
            onerror(PermissionError('private path and diagnostic'))
            return iter(())
        with patch.object(gate, 'verify_wheels', return_value={}), \
             patch.object(gate.os, 'walk', side_effect=failed_walk):
            self.error('OBSERVATION', gate.observe_installed_tree, self.directory, self.directory)

    def test_unreadable_subtree_rejected(self):
        sub = self.directory/'unreadable'; sub.mkdir(mode=0o700)
        (sub/'hidden').write_bytes(b'x'*32)
        sub.chmod(0)
        try:
            try:
                list(sub.iterdir())
                unreadable = False
            except PermissionError:
                unreadable = True
            if not unreadable:
                self.skipTest('requires unprivileged owner permission enforcement')
            with patch.object(gate, 'verify_wheels', return_value={}):
                self.error('OBSERVATION', gate.observe_installed_tree, self.directory, self.directory)
        finally:
            sub.chmod(0o700)

    def test_healthy_nested_tree_positive(self):
        sub = self.directory/'readable'; sub.mkdir(mode=0o700)
        (sub/'visible').write_bytes(b'x'*32)
        with patch.object(gate, 'verify_wheels', return_value={}):
            result = gate.observe_installed_tree(self.directory, self.directory)
        self.assertEqual(result['status'], 'SIZE_ACCEPTED_ONLY')
        self.assertEqual(result['installed_tree_logical_bytes'], 32)
        self.assertEqual(result['installed_regular_files'], 1)

    def test_finite_errors(self):
        self.assertEqual(str(gate.GateError('private secret')), 'OBSERVATION')


if __name__ == '__main__':
    unittest.main()
