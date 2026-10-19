"""Fixed actual-header cold checks only. Never runs native, make, or RTL."""
import argparse
import builtins
import copy
import hashlib
import json
import os
from pathlib import Path
import resource
import stat
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
PINS = {
    'header': (899, 'e03ae18149849b305ba69434b78dbba9212b7f5f163d7e5bcc5c44b872b14109'),
    'parser': (25935, '9eaf9a3029e905e1eaaaf1cdd7d72778b5a7556a96435513c95ef92be5372144'),
    'bootstrap': (25509, 'c2a7ca58d8fba3df8b76071e25ad740386ab5113a59897181b39b4d303e50ea8'),
    'observations': (25225, '4e0046efd081ae67f386579c09e4758a4735f8b6054c293085e67788138bbdc6'),
}
ACTUAL = {'bytes': 4630258, 'sha256': 'a9371ed20684a6b5635de6203918cd33b910d856bd83618cf4a33c9dda398aaf'}
CLI = argparse.ArgumentParser(allow_abbrev=False)
CLI.add_argument('--source', required=True, type=Path)
CLI.add_argument('--parser-source', required=True, type=Path)
CLI.add_argument('--bootstrap-source', required=True, type=Path)
CLI.add_argument('--observations', required=True, type=Path)
CLI.add_argument('--header-root', required=True, type=Path)
CLI.add_argument('--mode', choices=('normal', 'optimized', 'relocated'), required=True)
ARGS = CLI.parse_args()


def audit(event, args):
    if event.startswith(('subprocess.', 'socket.')) or event in (
        'os.system', 'os.fork', 'os.forkpty', 'os.exec', 'os.posix_spawn', 'ctypes.dlopen', 'urllib.Request'):
        raise RuntimeError('COLD_NATIVE_NETWORK_FORBIDDEN')
    if event == 'import' and str(args[0]).split('.')[0] in ('numpy', 'scipy', 'torch', 'ctypes'):
        raise RuntimeError('COLD_NUMERICAL_IMPORT_FORBIDDEN')
    if event == 'open' and isinstance(args[0], (str, bytes)):
        flags = args[2]
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            path = Path(os.fsdecode(args[0])).resolve()
            if not path.is_relative_to(HERE):
                raise RuntimeError('COLD_WRITES_ONLY_NEW_TEST_DIRECTORY')


sys.addaudithook(audit)
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise RuntimeError('COLD_ISOLATION_REQUIRED')
resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024**2, 16 * 1024**2))
allowed = os.sched_getaffinity(0)
os.sched_setaffinity(0, {min(allowed)})


def pin(raw):
    return len(raw), hashlib.sha256(raw).hexdigest()


def checked_source(path, wanted):
    path = Path(path)
    if not path.is_absolute() or path.resolve(strict=True) != path or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('COLD_CANONICAL_SOURCE')
    raw = path.read_bytes()
    if pin(raw) != wanted:
        raise ValueError('COLD_FIXED_SOURCE_IDENTITY')
    return raw


def load(path, wanted, name):
    raw = checked_source(path, wanted)
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec', dont_inherit=True), module.__dict__)
    return module


H = load(ARGS.source, PINS['header'], 'fixed_header_gate')
R = load(ARGS.parser_source, PINS['parser'], 'fixed_original_owner_parser')
G = load(ARGS.bootstrap_source, PINS['bootstrap'], 'fixed_original_bootstrap')
OBSERVATIONS = json.loads(checked_source(ARGS.observations, PINS['observations']))
ACTUAL_PATH = ARGS.header_root / H.HEADER_NAME
ACTUAL_BEFORE = (ACTUAL_PATH.stat().st_size, ACTUAL_PATH.stat().st_mode & 0o777,
                 ACTUAL_PATH.stat().st_mtime_ns, ACTUAL_PATH.stat().st_ctime_ns)


def tree(root=ARGS.header_root):
    return {'root': str(root), 'entries': {H.HEADER_NAME: {'kind': 'regular', 'mode': '0o600', **ACTUAL}}}


def fake_reader(raw=b'tiny checked buffer'):
    return types.SimpleNamespace(need=G.need, checked=mock.Mock(return_value=raw))


class SourceLoading(unittest.TestCase):
    def test_all_loaded_source_and_observation_pins_still_fixed(self):
        for path, key in ((ARGS.source, 'header'), (ARGS.parser_source, 'parser'),
                          (ARGS.bootstrap_source, 'bootstrap'), (ARGS.observations, 'observations')):
            self.assertEqual(pin(path.read_bytes()), PINS[key])

    def test_loader_short_long_wrong_hash_fail_before_compile(self):
        raw = ARGS.source.read_bytes()
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            path = Path(folder) / 'header_gate.py'
            for changed in (raw[:-1], raw + b'\n', bytes([raw[0] ^ 1]) + raw[1:]):
                path.write_bytes(changed)
                with mock.patch.object(builtins, 'compile', side_effect=AssertionError('compiled wrong pin')) as compiler:
                    with self.assertRaisesRegex(ValueError, 'COLD_FIXED_SOURCE_IDENTITY'):
                        load(path, PINS['header'], 'bad')
                    compiler.assert_not_called()

    def test_loader_compiles_same_verified_buffer_after_file_replacement(self):
        raw = ARGS.source.read_bytes()
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            path = Path(folder) / 'header_gate.py'; path.write_bytes(raw)
            compiler = builtins.compile; seen = []
            def compile_buffer(buf, *args, **kwargs):
                seen.append(buf); path.write_bytes(b'raise RuntimeError("replacement")\n')
                return compiler(buf, *args, **kwargs)
            with mock.patch.object(builtins, 'compile', side_effect=compile_buffer):
                loaded = load(path, PINS['header'], 'same_buffer')
            self.assertEqual(seen, [raw]); self.assertEqual(loaded.HEADER_PIN, ACTUAL)


class FixedHeaderGate(unittest.TestCase):
    def test_real_header_readonly_positive_and_original_parser_exact_95(self):
        self.assertEqual(H.HEADER_PIN, ACTUAL)
        self.assertEqual(H.HEADER_CAP, 16 * 1024**2)
        self.assertEqual(stat.S_IMODE(ACTUAL_PATH.stat().st_mode), 0o600)
        original_checked = G.checked
        with mock.patch.object(G, 'checked', wraps=original_checked) as checked:
            text = H.header_text(G, tree())
        checked.assert_called_once_with(ACTUAL_PATH, ACTUAL, 16 * 1024**2,
                                       fixed_leaf='VQwenOwnerKernel___024root.h')
        self.assertEqual(pin(text.encode('ascii')), (ACTUAL['bytes'], ACTUAL['sha256']))
        result = R.observation_declarations(text, OBSERVATIONS)
        self.assertEqual(len(result), 95)
        self.assertEqual(set(result), {row['member'] for row in OBSERVATIONS})
        for row in OBSERVATIONS:
            self.assertEqual(result[row['member']]['width'], row['width'])
        self.assertEqual((ACTUAL_PATH.stat().st_size, stat.S_IMODE(ACTUAL_PATH.stat().st_mode),
                          ACTUAL_PATH.stat().st_mtime_ns, ACTUAL_PATH.stat().st_ctime_ns), ACTUAL_BEFORE)

    def test_original_default_four_mib_guard_rejects_before_open(self):
        with mock.patch.object(G.os, 'open', side_effect=AssertionError('must fail before opening')) as opener:
            with self.assertRaisesRegex(ValueError, 'bounded fixed identity'):
                G.checked(ACTUAL_PATH, ACTUAL, fixed_leaf='VQwenOwnerKernel___024root.h')
            opener.assert_not_called()

    def test_four_and_sixteen_mib_metadata_neighbors_are_all_rejected(self):
        for value in (4 * 1024**2 - 1, 4 * 1024**2, 4 * 1024**2 + 1,
                      16 * 1024**2 - 1, 16 * 1024**2, 16 * 1024**2 + 1):
            with self.subTest(bytes=value):
                value_tree = tree(); value_tree['entries'][H.HEADER_NAME]['bytes'] = value
                g = fake_reader()
                with self.assertRaisesRegex(ValueError, 'OWNER_FIXED_HEADER_IDENTITY'):
                    H.header_text(g, value_tree)
                g.checked.assert_not_called()

    def test_wrong_hash_size_mode_kind_and_types_rejected_before_reader(self):
        mutations = [('sha256', '0' * 64), ('sha256', None), ('bytes', ACTUAL['bytes'] + 1),
                     ('bytes', str(ACTUAL['bytes'])), ('bytes', True), ('mode', '0o644'),
                     ('mode', 0o600), ('mode', None), ('kind', 'symlink'), ('kind', None)]
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                value_tree = tree(); value_tree['entries'][H.HEADER_NAME][key] = value; g = fake_reader()
                with self.assertRaisesRegex(ValueError, 'OWNER_FIXED_HEADER_IDENTITY'):
                    H.header_text(g, value_tree)
                g.checked.assert_not_called()

    def test_non_dict_missing_header_and_missing_identity_fields_rejected(self):
        variants = []
        for value in (None, [], '', 123):
            t = tree(); t['entries'][H.HEADER_NAME] = value; variants.append(t)
        t = tree(); del t['entries'][H.HEADER_NAME]; variants.append(t)
        for field in ('bytes', 'sha256', 'kind', 'mode'):
            t = tree(); del t['entries'][H.HEADER_NAME][field]; variants.append(t)
        for value_tree in variants:
            g = fake_reader()
            with self.assertRaisesRegex(ValueError, 'OWNER_FIXED_HEADER_IDENTITY'): H.header_text(g, value_tree)
            g.checked.assert_not_called()

    def test_missing_tree_fields_fail_before_reader(self):
        for field in ('entries', 'root'):
            value_tree = tree(); del value_tree[field]; g = fake_reader()
            with self.assertRaises(KeyError): H.header_text(g, value_tree)
            g.checked.assert_not_called()

    def test_exact_reader_cap_path_leaf_and_returned_ascii_buffer(self):
        raw = b'CData/*0:0*/ QwenOwnerKernel__DOT__one;\n'; g = fake_reader(raw)
        self.assertEqual(H.header_text(g, tree()), raw.decode('ascii'))
        g.checked.assert_called_once_with(ACTUAL_PATH, ACTUAL, 16 * 1024**2,
                                         fixed_leaf='VQwenOwnerKernel___024root.h')

    def test_non_ascii_checked_buffer_fails_closed(self):
        with self.assertRaises(UnicodeDecodeError): H.header_text(fake_reader(b'\xff'), tree())


class SameBufferAndDrift(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=HERE); self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name); self.path = self.root / H.HEADER_NAME
        self.path.parent.mkdir()
        self.raw = G.checked(ACTUAL_PATH, ACTUAL, H.HEADER_CAP, fixed_leaf='VQwenOwnerKernel___024root.h')
        self.path.write_bytes(self.raw); self.path.chmod(0o600)

    def test_after_read_file_change_still_decodes_same_verified_buffer(self):
        original = G.checked; calls = []
        def checked(*args, **kwargs):
            raw = original(*args, **kwargs); calls.append(raw)
            self.path.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
            return raw
        with mock.patch.object(G, 'checked', side_effect=checked):
            actual = H.header_text(G, tree(self.root))
        self.assertEqual(calls, [self.raw])
        self.assertEqual(actual.encode('ascii'), self.raw)
        self.assertNotEqual(self.path.read_bytes(), self.raw)

    def test_same_size_wrong_actual_hash_rejected_by_original_checked(self):
        self.path.write_bytes(bytes([self.raw[0] ^ 1]) + self.raw[1:])
        with self.assertRaisesRegex(ValueError, 'stable exact bytes'):
            H.header_text(G, tree(self.root))

    def test_file_drift_during_original_reader_rejected(self):
        original = G.os.read; changed = []
        def drift(fd, count):
            raw = original(fd, count)
            if raw and not changed:
                with self.path.open('r+b') as stream:
                    stream.write(bytes([self.raw[0] ^ 1]))
                changed.append(True)
            return raw
        with mock.patch.object(G.os, 'read', side_effect=drift):
            with self.assertRaisesRegex(ValueError, 'stable exact bytes'):
                H.header_text(G, tree(self.root))
        self.assertEqual(changed, [True])

    def test_short_actual_file_and_symlink_rejected(self):
        self.path.write_bytes(self.raw[:-1])
        with self.assertRaisesRegex(ValueError, 'regular exact size'): H.header_text(G, tree(self.root))
        self.path.unlink(); self.path.symlink_to(ACTUAL_PATH)
        with self.assertRaises(OSError): H.header_text(G, tree(self.root))


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    actual_after = (ACTUAL_PATH.stat().st_size, stat.S_IMODE(ACTUAL_PATH.stat().st_mode),
                    ACTUAL_PATH.stat().st_mtime_ns, ACTUAL_PATH.stat().st_ctime_ns)
    if actual_after != ACTUAL_BEFORE:
        raise RuntimeError('ORIGINAL_HEADER_METADATA_DRIFT')
    final_raw = G.checked(ACTUAL_PATH, ACTUAL, H.HEADER_CAP, fixed_leaf='VQwenOwnerKernel___024root.h')
    summary = {'schema': 'FIXED_OWNER_HEADER_COLD_V1', 'status': 'PASS' if result.wasSuccessful() else 'FAIL',
               'mode': ARGS.mode, 'python_optimize': sys.flags.optimize, 'tests_run': result.testsRun,
               'failures': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped),
               'source_pins': {key: {'bytes': p[0], 'sha256': p[1]} for key, p in PINS.items()},
               'actual_header_identity': ACTUAL, 'actual_header_mode': '0o600',
               'actual_header_metadata_unchanged': actual_after == ACTUAL_BEFORE,
               'original_parser_expected_observations': 95, 'gate_cap_bytes': H.HEADER_CAP,
               'fixed_header_only_not_general_16mib_acceptance': True,
               'production_run_main_executed': False, 'native_make_rtl_network_executed': False,
               'process_limits': {'as_bytes': 512 * 1024**2, 'cpu_seconds': 30,
                                  'fsize_bytes': 16 * 1024**2, 'cpu_affinity_count': len(os.sched_getaffinity(0))}}
    (HERE / ('RESULT_' + ARGS.mode + '.json')).write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
