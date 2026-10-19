"""Pure mock/metadata checks. No raw tensors, weight conversion, network or native."""
from __future__ import annotations
import argparse
import ast
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

P = argparse.ArgumentParser(allow_abbrev=False)
P.add_argument('--repo', required=True, type=Path)
ARGS, REST = P.parse_known_args()
HERE = Path(__file__).resolve().parent
REPO = ARGS.repo
ADAPTER_PIN = (13146, 'bccd714fe46a4f3e27bddd293817367e8b6abc3702f5bf022516bf2321c466de')
BASE_CONVERTER = ('development_snapshots/canonical_provider_transform_source_20261018/convert_providers.py',
                  17116, '104234daaec9bb37a1cdaefe428dd13abab4906bbc5fdf58a331c5520e632d57')
BASE_SPEC = ('development_snapshots/canonical_provider_transform_source_20261018/CONVERSION_SPEC.json',
             17884, '423fa7e23c1adfd12977b37c1a8d73e7ca9d812ba4876eeb5e9c28363333589d')


def checked(path, pin):
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('test source path')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        a = os.fstat(stream.fileno())
        if not stat.S_ISREG(a.st_mode) or a.st_size != pin[0]:
            raise ValueError('test source size/type')
        raw = stream.read(pin[0] + 1)
        z = os.fstat(stream.fileno())
    stamp = lambda x: (x.st_dev, x.st_ino, x.st_size, x.st_mode, x.st_mtime_ns, x.st_ctime_ns)
    if stamp(a) != stamp(z) or stamp(z) != stamp(path.stat(follow_symlinks=False)):
        raise ValueError('test source changed')
    if (len(raw), hashlib.sha256(raw).hexdigest()) != pin:
        raise ValueError('test source pin')
    return raw


RAW = checked(HERE / 'prepare_inputs.py', ADAPTER_PIN)
A = types.ModuleType('_input_adapter_cold')
A.__file__ = str(HERE / 'prepare_inputs.py')
sys.modules[A.__name__] = A
exec(compile(RAW, A.__file__, 'exec', dont_inherit=True), A.__dict__)
BUFFERS = {name: checked(REPO / name, pin) for name, pin in A.PINS.items()}
SPEC = json.loads(BUFFERS[A.PROVIDER + 'CONVERSION_SPEC.json'])
SOURCES = A.metadata_sources(REPO, BUFFERS, time.monotonic() + 30)
EXPECTED = [
 ('commands', 384, '618cd4db94fbc5f0e3829182a72d5e298b5a42d2a3840ec2b9f9be639cd884c4'),
 ('descriptors', 3456, '1e4d35da18b21a4d9de05d2f3129e5bd9717cd923837c83c8d5eb320bfcddb02'),
 ('wq', 4718592, 'ad7ce2dae58deb01656348a6ee2bd6919ed6c2bc83f31b88eed75381cd718b72'),
 ('wk', 786432, '313f8c46dec3be020734db5647f124467f86b0f637c1e80a5c85814971413344'),
 ('wv', 786432, 'a00fd3873f1d0ab098694b6003fd27f464e769c3395e227c729bb856246de84a'),
 ('wo', 4718592, '69532da7bcc69b44b0bb627a4c0142f83b6713833d8ec08d6f73926eae80722c'),
 ('wg', 27525120, 'be5cdf567f7ac2f91f63bfad26194336f4f857596716b3c365986b4ad1e5a44f'),
 ('wu', 27525120, '59f200f6eb3b67e947248d6f5f0308c28ec0256b93893342e2f27d028c80a040'),
 ('wd', 27525120, '90b75c3a30d975516e17cc61ba0fe2e41eff5b7d98c1cc9361b25f0d172a53ec'),
 ('gamma0', 6144, '320e4ac88269676897cf9c3b4996f966a6100ced2bc0f684216c200bc82b7180'),
 ('gamma1', 6144, 'e8e9d18c28e26e06d89fbb591b749cb77617e32cc17607f2b92e4b6a1828c70a'),
 ('bq', 6144, '47506ca51cfd69119a774c09466b718c0b400b84b9a392bc1e9bcb691f28b72d'),
 ('bk', 1024, 'c77424743b1f69c60e2de1b4780666973af58831169c3ee02d7443701bc6d03d'),
 ('bv', 1024, 'e0ba90f0d591f0266f0140802b6e4ccc24a9961ef26e96ee00f5b1567f8b2f70'),
 ('rope', 524288, 'c4dd66159d1868988937a2c15bf45609a09ec1dd40e47b63b708c6c9c1a0a7d1'),
 ('x', 786432, 'ddcdcca67cb3e26007880a78074ea3eb70bf83e8d8060fa2258bb2c7644695df'),
]
IDENTITIES = [dict(name=n, bytes=b, sha256=s) for n, b, s in EXPECTED]


def report():
    return dict(status='FIXED_PROVIDER14_BYTES_VERIFIED', provider_payload_bytes=94916608,
                conversion_spec_sha256=A.PINS[A.PROVIDER + 'CONVERSION_SPEC.json'][1],
                raw_receipt_sha256=SPEC['raw_receipt']['sha256'],
                providers=[dict(name=r['name'], file=r['output_filename'], bytes=r['output_bytes'],
                                sha256=r['expected_output_sha256']) for r in SPEC['providers']])


def captured(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = A.main(argv)
    return code, out.getvalue(), err.getvalue()


class Cold(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='cold_', dir=HERE)
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.raw = self.root / 'raw'
        self.raw.mkdir()
        self.out = self.root / 'out'
        self.stop = time.monotonic() + 60

    @contextlib.contextmanager
    def pipeline(self, overrides=None):
        """Never call real provider receipt/output/collect; no raw payload exists."""
        converter = types.SimpleNamespace(
            check_sources=mock.Mock(return_value=copy.deepcopy(SPEC)),
            check_receipt=mock.Mock(),
            prepare_output=mock.Mock(return_value=self.out / 'providers'),
            collect=mock.Mock(return_value=report()))
        options = dict(source_buffers=mock.Mock(return_value=BUFFERS),
                       metadata_sources=mock.Mock(return_value=SOURCES),
                       module=mock.Mock(return_value=converter),
                       metadata_artifacts=mock.Mock(return_value={
                           'metadata.json': b'{}', 'host_commands.bin': b'commands',
                           'host_descriptors.bin': b'descriptors', 'metadata_layout.hpp': b'header'}),
                       verify_inputs=mock.Mock(return_value=copy.deepcopy(IDENTITIES)))
        options.update(overrides or {})
        with contextlib.ExitStack() as stack:
            for name, value in options.items():
                stack.enter_context(mock.patch.object(A, name, value))
            yield converter, options

    def test_01_default_source_only_no_preparation(self):
        with mock.patch.object(A, 'prepare', side_effect=AssertionError('must not execute')):
            self.assertEqual(captured([]), (0, 'N0_INPUTS_SOURCE_ONLY\n', ''))

    def test_02_cli_errors_do_not_echo_argv(self):
        for argv in (['--SECRET_PATH'], ['--shared-stop', 'SECRET_PATH'],
                     ['--repo'], ['--exe'], ['--help'], ['--execute']):
            with self.subTest(argv=argv):
                self.assertEqual(captured(argv), (1, 'N0_INPUTS_INCOMPLETE:FLAGS\n', ''))

    def test_03_flags_precede_every_exec(self):
        for missing in ('isolated', 'no_site', 'dont_write_bytecode'):
            values = dict(isolated=1, no_site=1, dont_write_bytecode=1)
            values[missing] = 0
            with self.subTest(flag=missing), mock.patch.object(A.sys, 'flags', types.SimpleNamespace(**values)):
                with self.assertRaisesRegex(A.ContractError, '^FLAGS$'):
                    A.module(b'raise RuntimeError("SECRET")', self.root / 'source.py', '_never_loaded')
                with self.assertRaisesRegex(A.ContractError, '^FLAGS$'):
                    A.prepare(REPO, self.raw, self.out, self.stop)
                self.assertFalse(self.out.exists())
        self.assertNotIn('_never_loaded', sys.modules)

    def test_04_deadline_rejects_nonfinite_bool_expired(self):
        for stop in (float('nan'), float('inf'), float('-inf'), True, False, 0, time.monotonic() - 1):
            with self.subTest(stop=stop), self.assertRaisesRegex(A.ContractError, '^DEADLINE$'):
                A.prepare(REPO, self.raw, self.out, stop)
        self.assertFalse(self.out.exists())

    def test_05_stable_regular_read_and_no_retained_payload(self):
        raw = b'x' * 65537
        p = self.root / 'tiny'
        p.write_bytes(raw)
        pin = (len(raw), hashlib.sha256(raw).hexdigest())
        self.assertEqual(A.read(p, pin, deadline=self.stop), raw)
        self.assertEqual(A.read(p, pin, False, self.stop), dict(bytes=len(raw), sha256=pin[1]))
        for wrong in ((len(raw) - 1, pin[1]), (len(raw), '0' * 64)):
            with self.assertRaises(A.ContractError):
                A.read(p, wrong, deadline=self.stop)

    def test_06_symlink_fifo_directory_and_escape_rejected(self):
        p = self.root / 'tiny'
        p.write_bytes(b'x')
        pin = (1, hashlib.sha256(b'x').hexdigest())
        link = self.root / 'link'
        link.symlink_to(p)
        fifo = self.root / 'fifo'
        os.mkfifo(fifo)
        parent_link = self.root / 'parent_link'
        parent_link.symlink_to(self.raw, target_is_directory=True)
        for path in (link, fifo, self.raw, parent_link / 'x'):
            with self.subTest(path=path.name), self.assertRaises((A.ContractError, OSError)):
                A.read(path, pin, deadline=self.stop)
        for path in ('relative', self.root / '..' / 'escape', str(self.root) + '/bad\nname'):
            with self.assertRaises(A.ContractError):
                A.plain(path)

    def test_07_replacement_during_read_rejected(self):
        p = self.root / 'tiny'
        p.write_bytes(b'x')
        replacement = self.root / 'replacement'
        replacement.write_bytes(b'x')
        original = os.fstat
        calls = 0
        def changing(fd):
            nonlocal calls
            result = original(fd)
            calls += 1
            if calls == 2:
                replacement.replace(p)
            return result
        with mock.patch.object(A.os, 'fstat', changing), self.assertRaises(A.ContractError):
            A.read(p, (1, hashlib.sha256(b'x').hexdigest()), deadline=self.stop)

    def test_08_compiles_checked_buffer_not_reopened_path(self):
        p = self.root / 'source.py'
        raw = b'value = 123\n'
        p.write_bytes(raw)
        got = A.read(p, (len(raw), hashlib.sha256(raw).hexdigest()), deadline=self.stop)
        p.write_bytes(b'raise RuntimeError("must not reopen")\n')
        loaded = A.module(got, p, '_same_buffer_cold')
        try:
            self.assertEqual(loaded.value, 123)
        finally:
            sys.modules.pop('_same_buffer_cold', None)

    def test_09_failed_exec_removes_module(self):
        with self.assertRaises(RuntimeError):
            A.module(b'raise RuntimeError("private")', self.root / 'source.py', '_failure_cold')
        self.assertNotIn('_failure_cold', sys.modules)

    def test_10_all_fixed_pins_and_original_functions_unchanged(self):
        self.assertEqual(A.source_buffers(REPO, self.stop), BUFFERS)
        old = checked(REPO / BASE_CONVERTER[0], BASE_CONVERTER[1:])
        old_spec = json.loads(checked(REPO / BASE_SPEC[0], BASE_SPEC[1:]))
        new = BUFFERS[A.PROVIDER + 'convert_providers.py']
        def functions(raw):
            lines = raw.splitlines(keepends=True)
            return {n.name: b''.join(lines[n.lineno - 1:n.end_lineno])
                    for n in ast.parse(raw).body if isinstance(n, ast.FunctionDef)}
        self.assertEqual(functions(new), functions(old))
        spec = copy.deepcopy(SPEC)
        spec['raw_receipt'] = old_spec['raw_receipt']
        self.assertEqual(spec, old_spec)
        self.assertEqual(len(SOURCES), 13)
        self.assertEqual(len([r for r in json.loads(BUFFERS[A.META + 'SOURCE_PIN.json'])['executed_modules']]), 8)

    def test_11_actual_provider_source_api_without_conversion(self):
        converter = A.module(BUFFERS[A.PROVIDER + 'convert_providers.py'],
                             REPO / (A.PROVIDER + 'convert_providers.py'), '_api_cold')
        try:
            self.assertEqual(converter.check_sources(REPO), SPEC)
            self.assertEqual(list(__import__('inspect').signature(converter.collect).parameters),
                             ['spec', 'raw_root', 'output', 'deadline'])
            self.assertEqual(SPEC['raw_receipt']['sha256'],
                             '0b319b9dc84a4c3942f3068b397e01f0e3493515b542ddf726d7d0677e01b6fa')
        finally:
            sys.modules.pop('_api_cold', None)

    def test_12_actual_metadata_replay_deterministic_and_numeric_free(self):
        before = tuple(sys.path)
        artifacts = []
        original_module = A.module
        forbidden = mock.Mock(side_effect=AssertionError('numeric pack_words forbidden'))
        def load(*args, **kwargs):
            value = original_module(*args, **kwargs)
            if args[2] == 'metadata_original_converter':
                value.pack_words = forbidden
            return value
        with mock.patch.object(A, 'module', load):
            for i in range(2):
                private = self.root / ('metadata' + str(i))
                private.mkdir()
                artifacts.append(A.metadata_artifacts(REPO, private, BUFFERS, SOURCES, self.stop))
        self.assertEqual(artifacts[0], artifacts[1])
        self.assertEqual(tuple(sys.path), before)
        forbidden.assert_not_called()
        document = json.loads(artifacts[0]['metadata.json'])
        self.assertEqual(document['status'], 'EXACT_SOURCE_METADATA_REPLAY_ONLY')
        self.assertEqual(len(document['audit']['project_modules_executed']), 8)
        for key in ('numpy_imported', 'torch_imported', 'numeric_payload_loaded',
                    'numerical_pack_words_called', 'native_compiled', 'eda_executed'):
            self.assertFalse(document['audit'][key])
        for name, size, digest in EXPECTED[:2]:
            raw = artifacts[0]['host_' + name + '.bin']
            self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest()), (size, digest))
        self.assertFalse(any(n.split('.')[0] in ('torch', 'numpy') for n in sys.modules))
        self.assertFalse(any(n.startswith(('heteronpu.', 'metadata_original_')) for n in sys.modules))

    def test_13_metadata_rejects_altered_executable_buffer(self):
        altered = dict(SOURCES)
        key = json.loads(BUFFERS[A.META + 'SOURCE_PIN.json'])['executed_modules'][0]['path']
        altered[key] = altered[key] + b'\n'
        private = self.root / 'metadata'
        private.mkdir()
        with self.assertRaisesRegex(A.ContractError, '^METADATA_REPLAY$'):
            A.metadata_artifacts(REPO, private, BUFFERS, altered, self.stop)
        self.assertNotIn('_fixed_original_metadata', sys.modules)

    def test_14_exact_all16_inventory_independent_hashes(self):
        calls = []
        def fake_read(path, pin, retain, deadline):
            calls.append((path, pin, retain, deadline))
            return dict(bytes=pin[0], sha256=pin[1])
        with mock.patch.object(A, 'read', fake_read):
            self.assertEqual(A.verify_inputs(self.out, SPEC, self.stop), IDENTITIES)
        self.assertEqual(len(calls), 16)
        self.assertTrue(all(not r[2] and r[3] == self.stop for r in calls))
        self.assertEqual(sum(row['bytes'] for row in IDENTITIES), 94920448)
        self.assertEqual([p.name for p, _, _, _ in calls],
                         ['host_commands.bin', 'host_descriptors.bin'] + [n + '.bin' for n, _, _ in EXPECTED[2:]])

    def test_15_bad_metadata_and_provider_identity_fail_real_read(self):
        for relative in ('metadata/host_commands.bin', 'providers/wq.bin'):
            target = self.out / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b'wrong')
        with self.assertRaisesRegex(A.ContractError, '^INPUT_IDENTITY$'):
            A.verify_inputs(self.out, SPEC, self.stop)
        with self.assertRaisesRegex(A.ContractError, '^INPUT_IDENTITY$'):
            A.read(self.out / 'providers/wq.bin', EXPECTED[2][1:], False, self.stop)

    def test_16_mocked_success_receipt_and_api_order(self):
        with self.pipeline() as (converter, options):
            result = A.prepare(REPO, self.raw, self.out, self.stop)
            self.assertEqual(result['inputs'], IDENTITIES)
            self.assertEqual(result['status'], 'CANONICAL16_PREPARED_ONLY')
            self.assertFalse(result['weights_loaded_into_rtl'])
            self.assertFalse(result['reference_used'])
            self.assertEqual(json.loads((self.out / 'INPUTS_READY.json').read_bytes()), result)
            self.assertFalse((self.out / 'INPUTS_READY.part').exists())
            self.assertEqual(converter.check_receipt.call_args.args[2], self.stop)
            self.assertEqual(converter.collect.call_args.args[3], self.stop)
            self.assertEqual(options['verify_inputs'].call_args.args[2], self.stop)
            self.assertEqual(options['source_buffers'].call_count, 2)
            self.assertEqual(options['metadata_sources'].call_count, 2)

    def test_17_parent_stop_clipped_once_120_no_extension(self):
        now = time.monotonic()
        with self.pipeline() as (converter, options), mock.patch.object(A.time, 'monotonic', return_value=now):
            A.prepare(REPO, self.raw, self.out, now + 999)
            self.assertEqual(converter.collect.call_args.args[3], now + 120)
            self.assertEqual(options['verify_inputs'].call_args.args[2], now + 120)
            self.assertTrue(all(call.args[1] == now + 120 for call in options['source_buffers'].call_args_list))

    def test_18_expiry_during_final_verification_never_ready(self):
        now = time.monotonic()
        current = [now]
        def expired(*args):
            current[0] = now + 11
            return IDENTITIES
        with self.pipeline({'verify_inputs': mock.Mock(side_effect=expired)}), \
                mock.patch.object(A.time, 'monotonic', side_effect=lambda: current[0]):
            with self.assertRaisesRegex(A.ContractError, '^DEADLINE$'):
                A.prepare(REPO, self.raw, self.out, now + 10)
        self.assertFalse((self.out / 'INPUTS_READY.json').exists())

    def test_19_source_drift_after_preparation_never_ready(self):
        changed = dict(BUFFERS)
        changed[A.META + 'SOURCE_PIN.json'] += b' '
        with self.pipeline({'source_buffers': mock.Mock(side_effect=[BUFFERS, changed])}), \
                self.assertRaisesRegex(A.ContractError, '^SOURCE$'):
            A.prepare(REPO, self.raw, self.out, self.stop)
        self.assertFalse((self.out / 'INPUTS_READY.json').exists())

    def test_20_report_wrong_order_identity_status_total_rejected(self):
        for field in ('status', 'provider_payload_bytes', 'conversion_spec_sha256', 'raw_receipt_sha256', 'providers'):
            target = self.root / ('out_' + field)
            with self.pipeline() as (converter, options):
                value = report()
                value[field] = list(reversed(value[field])) if field == 'providers' else 'wrong'
                converter.collect.return_value = value
                with self.subTest(field=field), self.assertRaisesRegex(A.ContractError, '^PROVIDER_OUTPUT$'):
                    A.prepare(REPO, self.raw, target, self.stop)
                options['metadata_artifacts'].assert_not_called()
                self.assertFalse((target / 'INPUTS_READY.json').exists())

    def test_21_provider_arbitrary_errors_and_prints_not_public(self):
        secret = 'SECRET:/private/path weights=999 argv=foo'
        def fail(*args):
            print(secret)
            print(secret, file=sys.stderr)
            raise RuntimeError(secret)
        with self.pipeline() as (converter, _):
            converter.collect.side_effect = fail
            argv = ['--execute', '--repo', str(REPO), '--raw-root', str(self.raw),
                    '--out', str(self.out), '--shared-stop', str(self.stop)]
            self.assertEqual(captured(argv), (1, 'N0_INPUTS_INCOMPLETE:PROVIDER_OUTPUT\n', ''))
        self.assertFalse((self.out / 'INPUTS_READY.json').exists())

    def test_22_source_failure_before_output_has_fixed_code(self):
        with self.pipeline({'source_buffers': mock.Mock(side_effect=RuntimeError('SECRET'))}):
            with self.assertRaisesRegex(A.ContractError, '^SOURCE$'):
                A.prepare(REPO, self.raw, self.out, self.stop)
        self.assertFalse(self.out.exists())

    def test_23_reject_existing_and_source_tree_destinations(self):
        self.out.mkdir()
        sentinel = self.out / 'INPUTS_READY.json'
        sentinel.write_bytes(b'caller data')
        for target in (self.out, REPO / 'NO_WRITE', self.raw / 'NO_WRITE'):
            with self.subTest(path=target.name), self.assertRaisesRegex(A.ContractError, '^PATH$'):
                A.prepare(REPO, self.raw, target, self.stop)
        self.assertEqual(sentinel.read_bytes(), b'caller data')

    def test_24_resource_error_has_only_fixed_public_code(self):
        for error in (TimeoutError('SECRET'), MemoryError('SECRET')):
            with mock.patch.object(A, 'prepare', side_effect=A.ContractError('RESOURCE')):
                self.assertEqual(captured(['--execute', '--repo', 'x', '--raw-root', 'x', '--out', 'x',
                                           '--shared-stop', '1']), (2, 'N0_INPUTS_INCOMPLETE:RESOURCE\n', ''))
            with self.pipeline() as (converter, _):
                converter.collect.side_effect = error
                target = self.root / type(error).__name__
                with self.assertRaisesRegex(A.ContractError, '^RESOURCE$'):
                    A.prepare(REPO, self.raw, target, self.stop)

    def test_25_no_timer_rlimit_or_process_ownership(self):
        tree = ast.parse(RAW)
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        self.assertTrue({'signal', 'resource', 'subprocess'}.isdisjoint(names))
        self.assertTrue({'setitimer', 'setrlimit', 'activate_limits', 'system', 'Popen'}.isdisjoint(attrs))

    def test_26_expiry_after_ready_link_removes_receipt(self):
        now = time.monotonic()
        current = [now]
        original_link = A.os.link
        def late_link(*args, **kwargs):
            original_link(*args, **kwargs)
            current[0] = now + 11
        with self.pipeline(), mock.patch.object(A.time, 'monotonic', side_effect=lambda: current[0]), \
                mock.patch.object(A.os, 'link', late_link):
            with self.assertRaisesRegex(A.ContractError, '^DEADLINE$'):
                A.prepare(REPO, self.raw, self.out, now + 10)
        self.assertFalse((self.out / 'INPUTS_READY.json').exists())


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0], *REST])
