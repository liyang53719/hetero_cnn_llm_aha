"""Cold byte-only diagnostic tests plus bounded stdlib subprocess fixtures."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('cold_failure_diagnostic', HERE/'failure_diagnostic.py')
D = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(D)
ABSOLUTE = '/source/candidates/producer/driver.py'
RELATIVE = 'candidates/producer/driver.py'
HASH = 'a' * 64
METADATA = {ABSOLUTE: dict(path=RELATIVE, sha256=HASH, lines=600)}
SECRET = 'PRIVATE_SENTINEL_tensors_0123456789_https://secret.invalid/token'


def trace(*, path=ABSOLUTE, number=43, function='need', terminal='ValueError: private failure', detail=True):
    lines = [D.HEADER, '  File "' + path + '", line ' + str(number) + ', in ' + function]
    if detail:
        lines += ['    raise ValueError("' + SECRET + '")', '    ^^^^^^^^^^^^^^^^^^^^^^^^^^^']
    lines += [terminal]
    return ('\n'.join(lines) + '\n').encode()


class DiagnosticTests(unittest.TestCase):
    def unavailable(self, raw, reason=None, metadata=METADATA):
        value = D.extract(raw, metadata)
        self.assertEqual(value['status'], 'UNAVAILABLE')
        if reason is not None:
            self.assertEqual(value['reason'], reason)
        self.assertIsNone(value['error_code'])
        self.assertIsNone(value['exception_class'])
        self.assertEqual(value['frames'], [])
        self.assertEqual(value['unknown_frames_omitted'], 0)
        self.assertEqual(value['known_frames_omitted'], 0)
        self.assertIs(value['diagnostic_only'], True)
        self.assertIs(value['origin_authenticated'], False)
        self.assertLessEqual(len(json.dumps(value).encode()), 8192)
        return value

    def test_exact_observation_and_redaction(self):
        raw = (SECRET + '\n').encode() + trace(function=SECRET, terminal='ValueError: ' + SECRET)
        value = D.extract(raw, METADATA)
        self.assertEqual(value, dict(schema=1, status='OBSERVED', reason='COMPLETE_SINGLE_TRACEBACK',
            error_code='PYTHON_VALUE_ERROR', exception_class='ValueError',
            frames=[dict(path=RELATIVE, sha256=HASH, line=43)], unknown_frames_omitted=0,
            known_frames_omitted=0, diagnostic_only=True, origin_authenticated=False))
        output = json.dumps(value)
        for forbidden in (SECRET, '/source/', 'raise ValueError', '^^^^', 'https://', 'need'):
            self.assertNotIn(forbidden, output)

    def test_all_terminal_classes_are_explicit(self):
        for name, code in D._EXCEPTIONS.items():
            with self.subTest(name=name):
                value = D.extract(trace(terminal=name + ': ' + SECRET), METADATA)
                self.assertEqual(value['exception_class'], name)
                self.assertEqual(value['error_code'], code)
        self.unavailable(trace(terminal='SecretException: ' + SECRET), 'UNSUPPORTED_EXCEPTION_CLASS')
        self.unavailable(trace(terminal='custom.ValueError: ' + SECRET), 'UNSUPPORTED_EXCEPTION_CLASS')
        self.unavailable(trace(terminal='ExceptionGroup: ' + SECRET), 'UNSUPPORTED_EXCEPTION_CLASS')

    def test_exception_without_message(self):
        self.assertEqual(D.extract(trace(terminal='ValueError'), METADATA)['status'], 'OBSERVED')

    def test_acquisition_exception_allowlist_redacts_url_status_and_message(self):
        expected = {
            'urllib.error.HTTPError': 'PYTHON_URLLIB_HTTP_ERROR',
            'urllib.error.URLError': 'PYTHON_URLLIB_URL_ERROR',
            'ssl.SSLError': 'PYTHON_SSL_ERROR',
            'ssl.SSLCertVerificationError': 'PYTHON_SSL_CERT_VERIFICATION_ERROR',
            'http.client.IncompleteRead': 'PYTHON_HTTP_INCOMPLETE_READ',
            'http.client.RemoteDisconnected': 'PYTHON_HTTP_REMOTE_DISCONNECTED',
            'ConnectionError': 'PYTHON_CONNECTION_ERROR',
            'ConnectionResetError': 'PYTHON_CONNECTION_RESET_ERROR',
            'BrokenPipeError': 'PYTHON_BROKEN_PIPE_ERROR',
        }
        private_message = 'HTTP Error 599: https://private.invalid/token=' + SECRET
        for name, code in expected.items():
            with self.subTest(name=name):
                value = D.extract(trace(terminal=name + ': ' + private_message), METADATA)
                self.assertEqual(value['status'], 'OBSERVED')
                self.assertEqual(value['exception_class'], name)
                self.assertEqual(value['error_code'], code)
                for forbidden in (SECRET, 'HTTP Error 599', '599', 'https://private.invalid', 'token='):
                    self.assertNotIn(forbidden, json.dumps(value))
        self.unavailable(trace(terminal='urllib.error.PrivateError: ' + private_message),
            'UNSUPPORTED_EXCEPTION_CLASS')
        self.unavailable(trace(terminal='custom.urllib.error.HTTPError: ' + private_message),
            'UNSUPPORTED_EXCEPTION_CLASS')

    def test_external_paths_are_omitted(self):
        raw = trace(detail=False).splitlines()[:-1]
        raw += [('  File "/secret/' + SECRET + '", line 7, in ' + SECRET).encode(), b'ValueError: secret']
        value = D.extract(b'\n'.join(raw) + b'\n', METADATA)
        self.assertEqual(value['status'], 'OBSERVED')
        self.assertEqual(value['unknown_frames_omitted'], 1)
        self.assertNotIn(SECRET, json.dumps(value))
        self.unavailable(trace(path='/other/candidates/producer/driver.py'), 'NO_PINNED_FRAME')
        self.unavailable(trace(path=ABSOLUTE + '.evil'), 'NO_PINNED_FRAME')
        self.unavailable(trace(path='/source/../source/candidates/producer/driver.py'), 'NO_PINNED_FRAME')

    def test_pinned_line_bounds(self):
        self.unavailable(trace(number=601), 'SOURCE_LINE_OUT_OF_RANGE')
        self.unavailable(trace(number=0), 'MALFORMED_TRACEBACK')
        self.unavailable(trace(number=-1), 'MALFORMED_TRACEBACK')
        self.unavailable(trace(number=1000001), 'INVALID_FRAME_LINE')

    def test_last_eight_known_frames(self):
        rows = [D.HEADER]
        rows += ['  File "' + ABSOLUTE + '", line ' + str(n) + ', in safe' for n in range(1, 12)]
        rows += ['ValueError: ' + SECRET]
        value = D.extract(('\n'.join(rows) + '\n').encode(), METADATA)
        self.assertEqual([item['line'] for item in value['frames']], list(range(4, 12)))
        self.assertEqual(value['known_frames_omitted'], 3)
        self.assertLessEqual(len(json.dumps(value).encode()), 8192)
        rows = [D.HEADER] + ['  File "' + ABSOLUTE + '", line 1, in safe'] * 65 + ['ValueError']
        self.unavailable(('\n'.join(rows) + '\n').encode(), 'TOO_MANY_FRAMES')

    def test_malformed_truncated_and_injected_traces(self):
        self.unavailable(trace()[:-1], 'INCOMPLETE_LOG')
        self.unavailable((D.HEADER + '\n').encode(), 'INCOMPLETE_TRACEBACK')
        self.unavailable(trace() + b'private trailing note\n', 'UNSUPPORTED_TERMINAL')
        self.unavailable(trace(terminal='ValueError: first\nsecond private line'), 'UNSUPPORTED_TERMINAL')
        self.unavailable(trace() + trace(), 'AMBIGUOUS_TRACEBACK')
        self.unavailable(trace(terminal='ValueError: ' + D.HEADER), 'AMBIGUOUS_TRACEBACK')
        for separator in D._CHAINS:
            self.unavailable(trace() + ('\n' + separator + '\n\n').encode() + trace(), 'CHAINED_TRACEBACK')
        self.unavailable(trace().replace(b'  File', b' File'), 'MALFORMED_TRACEBACK')
        self.unavailable(trace().replace(b'    ^^^', b'  private ^^^'), 'MALFORMED_TRACEBACK')
        self.unavailable(trace().replace(b'ValueError:', b'    extra source\nValueError:'), 'MALFORMED_TRACEBACK')
        self.unavailable(b'  + Exception Group Traceback (most recent call last):\n', 'AMBIGUOUS_TRACEBACK')
        self.unavailable(trace().replace(b'ValueError:', b'  [Previous line repeated 4 more times]\nValueError:'), 'MALFORMED_TRACEBACK')

    def test_non_traceback_failures(self):
        self.unavailable(b'usage: driver.py [options]\ndriver.py: error: private argument\n', 'NO_TRACEBACK')
        self.unavailable(b'Segmentation fault\n', 'NO_TRACEBACK')
        self.unavailable(trace(path='<string>', terminal='FileNotFoundError: ' + SECRET), 'NO_PINNED_FRAME')

    def test_raw_types_and_bounds(self):
        for raw in (None, True, 1, 'text', bytearray(trace()), memoryview(trace())):
            with self.subTest(kind=type(raw).__name__):
                self.unavailable(raw, 'INVALID_RAW_TYPE')
        self.unavailable(b'', 'EMPTY_LOG')
        self.unavailable(b'x' * 65537, 'LOG_TOO_LARGE')
        self.unavailable(b'\xff\n', 'INVALID_ENCODING')
        self.unavailable(trace(terminal='ValueError: \x00secret'), 'UNSUPPORTED_CONTROL_CHARACTER')
        self.unavailable(trace().replace(b'\n', b'\r\n'), 'UNSUPPORTED_CONTROL_CHARACTER')
        self.unavailable(b'x' * 4097 + b'\n' + trace(), 'LINE_TOO_LONG')
        self.unavailable(b'\n' * 2048 + trace(), 'TOO_MANY_LINES')
        raw = b'x\n' * 20 + trace()
        self.assertEqual(D.extract(raw, METADATA)['status'], 'OBSERVED')

    def test_metadata_types_and_bounds(self):
        for metadata in (None, True, [], {}, {1: METADATA[ABSOLUTE]}, {ABSOLUTE: []}):
            with self.subTest(metadata=metadata):
                self.unavailable(trace(), 'INVALID_SOURCE_METADATA', metadata)
        item = METADATA[ABSOLUTE]
        for changed in (dict(item, lines=True), dict(item, lines=0), dict(item, lines=1.0),
                dict(item, lines=1000001), dict(item, sha256='G'*64), dict(item, sha256=True),
                dict(item, path='../private.py'), dict(item, path='/private.py'),
                dict(item, path='https://secret.invalid/private.py'), dict(item, path='secret\\private.py'),
                dict(item, path='private\nsecret.py'), dict(item, path='different.py'),
                dict(item, extra=SECRET)):
            with self.subTest(changed=changed):
                value = self.unavailable(trace(), 'INVALID_SOURCE_METADATA', {ABSOLUTE: changed})
                self.assertNotIn(SECRET, json.dumps(value))
        for absolute in ('relative.py', '/source//driver.py', '/source/../driver.py', '/source/"driver.py'):
            self.unavailable(trace(), 'INVALID_SOURCE_METADATA', {absolute: item})
        too_many = {'/root/file' + str(n) + '.py': dict(path='file' + str(n) + '.py', sha256=HASH, lines=1)
                    for n in range(1025)}
        self.unavailable(trace(), 'INVALID_SOURCE_METADATA', too_many)

    def test_forged_valid_trace_is_never_authoritative(self):
        value = D.extract(trace(function='invented', terminal='ValueError: forged'), METADATA)
        self.assertEqual(value['status'], 'OBSERVED')
        self.assertIs(value['diagnostic_only'], True)
        self.assertIs(value['origin_authenticated'], False)
        self.assertNotIn('forged', json.dumps(value))
        self.assertNotIn('invented', json.dumps(value))

    def test_real_stdlib_failure_normal_and_optimized(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'failing.py'
            source = ('def fail():\n    raise ValueError(' + repr(SECRET) + ')\nfail()\n').encode()
            path.write_bytes(source)
            metadata = {str(path): dict(path='failing.py', sha256=hashlib.sha256(source).hexdigest(), lines=3)}
            for flags in ([], ['-O']):
                with self.subTest(flags=flags):
                    completed = subprocess.run([sys.executable, '-I', '-B', *flags, str(path)],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=5, check=False)
                    self.assertEqual(completed.returncode, 1)
                    self.assertIn(SECRET.encode(), completed.stdout)
                    value = D.extract(completed.stdout, metadata)
                    self.assertEqual(value['status'], 'OBSERVED')
                    self.assertEqual(value['frames'][-1]['line'], 2)
                    self.assertNotIn(SECRET, json.dumps(value))
                    self.assertNotIn(directory, json.dumps(value))

    def test_cold_import_normal_and_optimized(self):
        code = ('import importlib.util,sys;'
            's=importlib.util.spec_from_file_location("cold",sys.argv[1]);'
            'm=importlib.util.module_from_spec(s);s.loader.exec_module(m);'
            'bad=set(sys.modules)&{"torch","numpy","ctypes","transformers","safetensors"};'
            'sys.exit(1 if bad else 0)')
        for flags in ([], ['-O']):
            with self.subTest(flags=flags):
                completed = subprocess.run([sys.executable, '-I', '-B', *flags, '-c', code, str(HERE/'failure_diagnostic.py')],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=5, check=False)
                self.assertEqual(completed.returncode, 0, completed.stdout)

    def test_real_qualified_stdlib_exception_normal_and_optimized(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'network_error.py'
            source = ('import urllib.error\nraise urllib.error.URLError(' + repr(SECRET) + ')\n').encode()
            path.write_bytes(source)
            metadata = {str(path): dict(path='network_error.py',
                sha256=hashlib.sha256(source).hexdigest(), lines=2)}
            for flags in ([], ['-O']):
                with self.subTest(flags=flags):
                    completed = subprocess.run([sys.executable, '-I', '-B', *flags, str(path)],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=5, check=False)
                    self.assertEqual(completed.returncode, 1)
                    self.assertIn(SECRET.encode(), completed.stdout)
                    value = D.extract(completed.stdout, metadata)
                    self.assertEqual(value['status'], 'OBSERVED')
                    self.assertEqual(value['exception_class'], 'urllib.error.URLError')
                    self.assertEqual(value['error_code'], 'PYTHON_URLLIB_URL_ERROR')
                    self.assertNotIn(SECRET, json.dumps(value))
                    self.assertNotIn(directory, json.dumps(value))


if __name__ == '__main__':
    unittest.main()
