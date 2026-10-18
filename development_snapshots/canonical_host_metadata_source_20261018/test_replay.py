"""Small source-only replay checks. No compiler, owner simulation, or payload."""
import argparse
import builtins
import hashlib
import importlib.machinery
import importlib.util
import json
import marshal
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import types
import unittest

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--repository', required=True, type=Path)
args, remaining = parser.parse_known_args()
ROOT = args.repository.resolve(strict=True)
RECEIPT = json.loads((HERE / 'PROJECT_SOURCE_HASHES.json').read_text())
raw = (HERE / 'replay_metadata.py').read_bytes()
if {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()} != RECEIPT['files']['replay_metadata.py']:
    raise ValueError('replay implementation differs before execution')
replay = types.ModuleType('verified_metadata_replay')
replay.__file__ = str(HERE / 'replay_metadata.py')
sys.modules[replay.__name__] = replay
exec(compile(raw, 'replay_metadata.py', 'exec', dont_inherit=True), replay.__dict__)
PIN = json.loads((HERE / 'SOURCE_PIN.json').read_text())
# Digests of the independently reviewed generated artifacts. No artifact bytes
# are stored in this source-only package; fresh replay must reproduce them.
EXPECTED_ARTIFACTS = {
    'host_commands.bin': {'bytes': 384, 'sha256': '618cd4db94fbc5f0e3829182a72d5e298b5a42d2a3840ec2b9f9be639cd884c4'},
    'host_descriptors.bin': {'bytes': 3456, 'sha256': '1e4d35da18b21a4d9de05d2f3129e5bd9717cd923837c83c8d5eb320bfcddb02'},
    'metadata.json': {'bytes': 18629, 'sha256': '463500e31e4f1f3a0cd97b987d8c607cb4e057500ad037a02df941bd33f9ac76'},
    'metadata_layout.hpp': {'bytes': 2962, 'sha256': '1778f7c08ce5a062d9e2bf3dd6454ba1cbe386262dd37d017cfe70371e0a3b83'},
}


def tiny_repository(root):
    records = {r['path']: r for r in PIN['executed_modules']}
    records.update(PIN['reference_only_sources'])
    for key in records:
        path = root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / key).read_bytes())


class MetadataCold(unittest.TestCase):
    def test_01_exact_package_source_receipt(self):
        for name, expected in RECEIPT['files'].items():
            self.assertEqual(replay.digest((HERE / name).read_bytes()), expected, name)
        self.assertFalse((HERE / 'generated').exists())
        self.assertEqual(len(PIN['executed_modules']), 8)
        self.assertEqual(PIN['repository_commit'], '6bde92d43d2ea9a78e951c0062e133aecf8b091e')
        for record in PIN['executed_modules']:
            self.assertFalse(Path(record['path']).is_absolute())

    def test_02_real_replay_exact_output_and_no_global_path_change(self):
        before = tuple(sys.path)
        actual = replay.artifacts(ROOT)
        self.assertEqual(tuple(sys.path), before)
        for name, raw in actual.items():
            self.assertEqual(replay.digest(raw), EXPECTED_ARTIFACTS[name], name)
        data = json.loads(actual['metadata.json'])
        self.assertEqual(data['layout']['payload_layout_bytes'], 94920448)
        self.assertEqual(len(data['layout']['allocations']), 35)
        self.assertEqual(sum(a['readonly'] for a in data['layout']['allocations']), 14)
        self.assertFalse(data['audit']['resident_ddr_permissions_established'])
        self.assertFalse(data['audit']['historical_stream_framing_recovered'])

    def test_03_numeric_pack_words_never_called(self):
        calls = []
        def profile(frame, event, arg):
            if event == 'call' and frame.f_code.co_name == 'pack_words':
                calls.append(frame.f_code.co_filename)
        old = sys.getprofile()
        sys.setprofile(profile)
        try:
            replay.replay(ROOT)
        finally:
            sys.setprofile(old)
        self.assertEqual(calls, [])
        self.assertFalse(any(n.split('.')[0] in ('numpy', 'torch') for n in sys.modules))

    def test_04_valid_polluted_cache_on_all_eight_sources_is_ignored(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'repository'
            tiny_repository(root)
            for record in PIN['executed_modules']:
                path = root / record['path']
                source = path.read_bytes()
                stats = path.stat()
                cache = Path(importlib.util.cache_from_source(str(path)))
                cache.parent.mkdir(exist_ok=True)
                code = compile('PYC_INJECTED_MARKER = True\n', record['path'], 'exec')
                cache.write_bytes(importlib.util.MAGIC_NUMBER + struct.pack(
                    '<III', 0, int(stats.st_mtime) & 0xffffffff, len(source)) + marshal.dumps(code))
                # Deliberately vulnerable temporary positive control. Its only
                # behavior is setting the harmless module marker from this pyc.
                name = 'temporary_legacy_cache_control'
                loader = importlib.machinery.SourceFileLoader(name, str(path))
                spec = importlib.util.spec_from_loader(name, loader)
                legacy = importlib.util.module_from_spec(spec)
                loader.exec_module(legacy)
                self.assertTrue(legacy.PYC_INJECTED_MARKER)
            cache_reads = []
            active = [True]
            def audit(event, arguments):
                if active[0] and event == 'open' and isinstance(arguments[0], (str, bytes)):
                    name = str(arguments[0])
                    if name.endswith('.pyc') and str(root) in name:
                        cache_reads.append(name)
            sys.addaudithook(audit)
            try:
                actual = replay.artifacts(root)
            finally:
                active[0] = False
            self.assertEqual(cache_reads, [])
            for name, raw in actual.items():
                self.assertEqual(replay.digest(raw), EXPECTED_ARTIFACTS[name], name)

    def test_05_bad_executed_or_reference_source_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'repository'
            tiny_repository(root)
            keys = [r['path'] for r in PIN['executed_modules']] + list(PIN['reference_only_sources'])
            for key in keys:
                with self.subTest(path=key):
                    path = root / key
                    raw = path.read_bytes()
                    path.write_bytes(raw + b'\nSOURCE_INJECTED_MARKER = True\n')
                    try:
                        with self.assertRaisesRegex(ValueError, 'before execution|reference source drift'):
                            replay.replay(root)
                        self.assertFalse(any(n.startswith(('heteronpu.', 'metadata_original_')) for n in sys.modules))
                    finally:
                        path.write_bytes(raw)

    def test_06_numpy_torch_import_and_preloaded_modules_rejected(self):
        imports = replay.fixed_importer({}, replay.FixedPathRequest(ROOT))
        for name in ('numpy', 'numpy.linalg', 'torch', 'torch.nn'):
            with self.subTest(name=name), self.assertRaisesRegex(ImportError, 'forbids numerical library'):
                imports(name)
        for name in ('numpy', 'torch'):
            sys.modules[name] = types.ModuleType(name)
            try:
                with self.assertRaisesRegex(ValueError, 'numerical library already imported'):
                    replay.replay(ROOT)
            finally:
                sys.modules.pop(name)
        for name in ('heteronpu.unlisted', 'model', 'importlib', 'site', 'os'):
            with self.subTest(name=name), self.assertRaises(ImportError):
                imports(name)

    def test_07_only_exact_known_path_requests_suppressed(self):
        requests = replay.FixedPathRequest(ROOT)
        requests.insert(0, str(ROOT / 'src'))
        self.assertEqual(len(requests.requests), 1)
        for index, value in ((1, str(ROOT / 'src')), (True, str(ROOT / 'src')), (0, '/tmp'), (0, ROOT / 'src')):
            with self.subTest(index=index, value=str(value)), self.assertRaises(ValueError):
                requests.insert(index, value)
        self.assertEqual(len(requests.requests), 1)

    def test_08_identical_read_buffer_is_compiled_once(self):
        # A read-side replacement cannot change the already hashed bytes.
        raw = b'SOURCE_VALUE = 17\n'
        class OneRead:
            count = 0
            def read_bytes(self):
                self.count += 1
                if self.count != 1:
                    raise RuntimeError('second source read')
                return raw
            def resolve(self):
                return Path('/unused/same-buffer-control.py')
        path = OneRead()
        seen = []
        original_compile = builtins.compile
        def capture(source, *args, **kwargs):
            seen.append(source)
            return original_compile(source, *args, **kwargs)
        builtins.compile = capture
        try:
            loaded = replay.module('temporary_same_buffer', path, 'same-buffer-control.py', replay.digest(raw), builtins.__import__)
            self.assertEqual(loaded.SOURCE_VALUE, 17)
            self.assertEqual(path.count, 1)
            self.assertEqual(len(seen), 1)
            self.assertIs(seen[0], raw)
        finally:
            builtins.compile = original_compile
            sys.modules.pop('temporary_same_buffer', None)

    def test_09_wrong_hash_never_creates_or_executes_module(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'changed.py'
            path.write_bytes(b'SOURCE_INJECTED_MARKER = True\n')
            with self.assertRaisesRegex(ValueError, 'before execution'):
                replay.module('temporary_changed_source', path, 'changed.py', replay.digest(b'original'), builtins.__import__)
            self.assertNotIn('temporary_changed_source', sys.modules)

    def test_10_unsafe_relative_names_rejected(self):
        for value in ('', '..', '../source', '/source', 'a/../b', 'a\\b', 'a//b', './a'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                replay.relative(value)

    def test_11_fresh_normal_and_optimized_cli_are_byte_stable(self):
        with tempfile.TemporaryDirectory() as temporary:
            results = []
            for mode in ([], ['-O']):
                output = Path(temporary) / ('optimized' if mode else 'normal')
                command = [sys.executable, '-I', '-S', '-B'] + mode + [str(HERE / 'replay_metadata.py'),
                           '--repository', str(ROOT), '--output', str(output)]
                run = subprocess.run(command, text=True, capture_output=True, check=True)
                self.assertEqual(run.stderr, '')
                results.append(run.stdout)
                for name in ('metadata.json', 'host_commands.bin', 'host_descriptors.bin', 'metadata_layout.hpp'):
                    self.assertEqual(replay.digest((output / name).read_bytes()), EXPECTED_ARTIFACTS[name], name)
                second = subprocess.run(command, text=True, capture_output=True)
                self.assertNotEqual(second.returncode, 0)
                self.assertIn('output already exists', second.stderr)
            self.assertEqual(results[0], results[1])


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]] + remaining, verbosity=2)
