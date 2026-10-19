"""Historical-profile adapter tests. Stdlib mocks only; no tensor/array execution."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / 'fixtures'
PREFIX = 'candidates/host93_first_n0_sources/'
WORKER_PIN = (21000, 'e2d1a644e369147772ccd3e6b074559a9b29e9230ace172a3f4bcb4594794800')
ORIGINAL_PIN = (20997, '66e0c2e92790f46efbf1833a0aa2d8a30bc0e8b80b4f03b4e62da74ca402a8c3')
PINS_PIN = (6364, 'ecea4b9b9137c06ae3c3f37bf9710f40f12a4556d1ae2c9aa77b84a857548db8')
HELPER_PIN = (13753, 'd26bd286857a6bff8217472733658cbdcb1e6590fa095e0d0589bc1be81b8fc4')
OLD = b"profile = pins['python_profiles']['ci31214']"
NEW = b"profile = pins['python_profiles']['historical']"


def checked(raw, pin):
    if type(raw) is not bytes or (len(raw), hashlib.sha256(raw).hexdigest()) != pin:
        raise ValueError('SOURCE')
    return raw


def fixed_module(raw, pin, name):
    if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
        raise ValueError('FLAGS')
    checked(raw, pin)
    module = types.ModuleType(name)
    module.__file__ = str(HERE / (name + '.py'))
    exec(compile(raw, '<fixed-' + name + '>', 'exec', dont_inherit=True), module.__dict__)
    return module


WORKER_RAW = checked((HERE / 'n0_compare.py').read_bytes(), WORKER_PIN)
PINS_RAW = checked((FIXTURES / PREFIX / 'reference/PINS.json').read_bytes(), PINS_PIN)
HELPER_RAW = checked((FIXTURES / PREFIX / 'reference/n0_reference.py').read_bytes(), HELPER_PIN)
n = fixed_module(WORKER_RAW, WORKER_PIN, '_historical_comparator_cold')
PINS = json.loads(PINS_RAW)


def counts_fixture():
    counts = {key: 0 for key in n.COUNT_KEYS}
    counts.update(scope='FIRST_N0_M128_ONLY', status='ACK0_ACTUAL_CAPTURED',
        numeric_comparison='NOT_RUN', phase='OUTPUT', code='ACK0_COMPLETE',
        full_block_pass=False, root256_handles='UNKNOWN', cycle_budget=8000000,
        reduction_only_source_floor=2428928, unproven_overhead_allowance=5571072,
        cycles=3000000, launches=1, jobs=1, owner_dones=1, completion_acks=1,
        committed_bytes=786432, successful_b=12288, writeback_bytes=786432,
        post_pc=1, post_issued_jobs=1, further_eval_calls=0,
        actual_values=196608, actual_bytes=786432)
    counts.update({key: [0] * length for key, length in n.ARRAY_SIZES.items()})
    counts['axi'] = {key: 0 for key in n.AXI_KEYS}
    counts['axi'].update(bs=12288, strobed_bytes=786432)
    return counts


class HistoricalCold(unittest.TestCase):
    def test_worker_inverse_is_exact_original_source(self):
        self.assertEqual(WORKER_RAW.count(NEW), 1)
        self.assertNotIn(OLD, WORKER_RAW)
        self.assertEqual(checked(WORKER_RAW.replace(NEW, OLD), ORIGINAL_PIN).count(OLD), 1)

    def test_launch_and_existing_tests_have_binding_only_deltas(self):
        originals = {
            'launch.py': (1984, '6e8dcfaa20d2c6811b92b91d596e8ebb9e27123fcf641f19b9b02e12cd6286b4'),
            'test_cold.py': (20332, 'c99124649ff999e4dc7e756c0c8670c8aacfce66b0ae493f09607218d1dd40de'),
        }
        for name, original in originals.items():
            raw = (HERE / name).read_bytes()
            self.assertEqual(raw.count(str(WORKER_PIN[0]).encode()), 1)
            self.assertEqual(raw.count(WORKER_PIN[1].encode()), 1)
            reverse = raw.replace(str(WORKER_PIN[0]).encode(), str(ORIGINAL_PIN[0]).encode())
            reverse = reverse.replace(WORKER_PIN[1].encode(), ORIGINAL_PIN[1].encode())
            self.assertEqual(checked(reverse, original), reverse)

    def test_existing_pins_profiles_and_dual_reference_identities_unchanged(self):
        self.assertEqual(PINS['python_profiles']['historical'], {
            'bytes': 30894944,
            'sha256': 'fa67443527ed9647f760d807e2a38f26340757123e643c4639cf273ed15d5ea7',
            'version': [3, 12],
        })
        self.assertEqual(PINS['python_profiles']['ci31214'], {
            'bytes': 17752,
            'sha256': 'bef88f140b625959f8af25c7b75cce2cd5d4b29cc2f2b079befd7f68eda4dba0',
            'version': [3, 12, 14],
        })
        helper = n.load_reference_helper(HELPER_RAW)
        self.assertEqual(PINS['output']['sha256'], n.REFERENCE['sha256'])
        self.assertEqual(PINS['output']['sha256'], helper.F32_SHA256)
        self.assertEqual(PINS['output']['native_sha256'], helper.BF16_SHA256)
        self.assertEqual(PINS['output']['native_bytes'], helper.BF16_BYTES)

    def test_cold_same_buffer_compile_and_precompile_tamper_rejection(self):
        compiler = compile
        with mock.patch.object(Path, 'open', side_effect=AssertionError('reopen')):
            with mock.patch('builtins.compile', wraps=compiler) as observed:
                loaded = fixed_module(WORKER_RAW, WORKER_PIN, '_same_buffer_cold')
        self.assertEqual(loaded.ELEMENTS, 196608)
        selected = [call for call in observed.call_args_list
                    if call.args[1] == '<fixed-_same_buffer_cold>']
        self.assertEqual(len(selected), 1)
        self.assertIs(selected[0].args[0], WORKER_RAW)
        for raw in (WORKER_RAW + b' ', bytes([WORKER_RAW[0] ^ 1]) + WORKER_RAW[1:]):
            with mock.patch('builtins.compile', side_effect=AssertionError('compile')) as compiler:
                with self.assertRaisesRegex(ValueError, 'SOURCE'):
                    fixed_module(raw, WORKER_PIN, '_invalid_source')
                compiler.assert_not_called()

    def test_loader_requires_all_isolation_flags_before_compile(self):
        for missing in ('isolated', 'no_site', 'dont_write_bytecode'):
            flags = dict(isolated=1, no_site=1, dont_write_bytecode=1)
            flags[missing] = 0
            with mock.patch.object(sys, 'flags', types.SimpleNamespace(**flags)):
                with mock.patch('builtins.compile', side_effect=AssertionError('compile')) as compiler:
                    with self.assertRaisesRegex(ValueError, 'FLAGS'):
                        fixed_module(WORKER_RAW, WORKER_PIN, '_missing_isolation')
                    compiler.assert_not_called()

    def test_pin_file_tamper_rejected_before_json_parse(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'PINS.json'
            for raw in (PINS_RAW + b' ', bytes([PINS_RAW[0] ^ 1]) + PINS_RAW[1:]):
                path.write_bytes(raw)
                with mock.patch.object(json, 'loads', side_effect=AssertionError('parse')) as parser:
                    with self.assertRaises(n.Rejected):
                        n.read_pin(path, n.REFERENCE_PINS)
                    parser.assert_not_called()

    def test_profile_cannot_be_overridden_by_cli(self):
        for argv in (['--python-profile', 'ci31214'], ['--profile', 'historical'],
                     ['--execute', '--python-profile', 'historical']):
            with mock.patch.object(n, 'run', side_effect=AssertionError('run')) as run:
                with contextlib.redirect_stdout(io.StringIO()) as stdout:
                    with contextlib.redirect_stderr(io.StringIO()) as stderr:
                        self.assertEqual(n.main(argv), 1)
                self.assertEqual(stdout.getvalue(), 'NOT_COMPLETED:FLAGS\n')
                self.assertEqual(stderr.getvalue(), '')
                run.assert_not_called()

    def test_original_runtime_helper_uses_exact_historical_and_unchanged_dependencies(self):
        helper = n.load_reference_helper(HELPER_RAW)
        python = Path('/mock-historical-python')
        runtime = Path('/mock-runtime')
        profile = PINS['python_profiles']['historical']
        def observed(path, pin, *, retain):
            self.assertFalse(retain)
            return {'bytes': pin['bytes'], 'sha256': pin['sha256']}
        with mock.patch.object(sys, 'version_info', (3, 12, 99)):
            with mock.patch.object(sys, 'executable', str(python)):
                with mock.patch.object(helper, 'read_checked', side_effect=observed) as read:
                    identities = helper.runtime_before(runtime, python, profile, PINS)
        self.assertEqual(read.call_args_list[0], mock.call(python, profile, retain=False))
        self.assertIs(read.call_args_list[0].args[1], profile)
        expected = [mock.call(python, profile, retain=False)]
        for name, pin in PINS['runtime_native_files'].items():
            if name != 'python':
                expected.append(mock.call(runtime / pin['path'].split('site-packages/', 1)[1], pin, retain=False))
        for relative, pin in PINS['runtime_sources'].items():
            expected.append(mock.call(runtime / relative, pin, retain=False))
        self.assertEqual(read.call_args_list, expected)
        self.assertEqual(len(read.call_args_list), 10)
        self.assertEqual(identities['python'], {key: profile[key] for key in ('bytes', 'sha256')})

    def test_original_runtime_helper_rejects_wrong_python_before_native_reads(self):
        helper = n.load_reference_helper(HELPER_RAW)
        for version in ((3, 11, 9), (3, 13, 0)):
            with mock.patch.object(sys, 'version_info', version):
                with mock.patch.object(helper, 'read_checked', side_effect=AssertionError('read')) as read:
                    with self.assertRaises(helper.Rejected) as error:
                        helper.runtime_before(Path('/mock-runtime'), Path('/mock-python'),
                                              PINS['python_profiles']['historical'], PINS)
                    self.assertEqual(error.exception.code, 'RUNTIME')
                    read.assert_not_called()

    def test_original_runtime_helper_rejects_historical_sha_failure(self):
        helper = n.load_reference_helper(HELPER_RAW)
        with mock.patch.object(sys, 'version_info', (3, 12, 99)):
            with mock.patch.object(sys, 'executable', '/mock-python'):
                with mock.patch.object(helper, 'read_checked', side_effect=helper.Rejected('SHA')) as read:
                    with self.assertRaises(helper.Rejected) as error:
                        helper.runtime_before(Path('/mock-runtime'), Path('/mock-python'),
                                              PINS['python_profiles']['historical'], PINS)
        self.assertEqual(error.exception.code, 'SHA')
        self.assertEqual(read.call_count, 1)

    @contextlib.contextmanager
    def mocked_run(self, *, before_error=None, after_drift=False, capture_change=None,
                   pins_raw=PINS_RAW):
        """Exercise control flow with opaque byte/sentinel fixtures, never real arrays."""
        with tempfile.TemporaryDirectory() as directory, contextlib.ExitStack() as stack:
            root = Path(directory)
            args = types.SimpleNamespace(repo=root / 'repo', runtime_root=root / 'runtime',
                python=root / 'python', reference_worker=root / 'reference-worker.py',
                pins=root / 'pins.json', reference=root / 'reference.f32le',
                actual=root / 'capture/actual_n0.f32le', capture=root / 'capture/counts.json',
                out=root / 'out', shared_stop=1000.)
            counts = counts_fixture()
            if capture_change is not None:
                capture_change(counts)
            capture_raw = json.dumps(counts).encode()
            # These are opaque mock tokens, not FP32 arrays or an alternative reference.
            actual_raw, reference_raw = b'mock-actual-token', b'mock-reference-token'
            source_map = {args.reference_worker: HELPER_RAW, args.pins: pins_raw,
                          args.repo / n.SCRIPT_PATH: b'mock-script-token',
                          args.repo / n.CONTRACT_PATH: b'mock-contract-token'}
            helper = types.SimpleNamespace(Rejected=n.Rejected,
                limits=mock.Mock(), source_buffers=mock.Mock(return_value={'mock-source': b'x'}),
                read_checked=mock.Mock(return_value=reference_raw),
                no_external_actions=mock.Mock(), runtime_before=mock.Mock())
            if before_error:
                helper.runtime_before.side_effect = n.Rejected(before_error)
            else:
                helper.runtime_before.side_effect = [{'mock-identity': 'before'},
                    {'mock-identity': 'after' if after_drift else 'before'}]
            torch = types.SimpleNamespace(get_num_threads=lambda: 4,
                get_num_interop_threads=lambda: 1, are_deterministic_algorithms_enabled=lambda: True,
                backends=types.SimpleNamespace(cpu=types.SimpleNamespace(get_cpu_capability=lambda: 'AVX512')),
                __config__=types.SimpleNamespace(show=lambda: 'mock configuration'))
            real_digest = n.digest
            def mock_digest(raw):
                return PINS['runtime_requirements']['torch_build_sha256'] if raw == b'mock configuration' else real_digest(raw)
            spies = {'helper': helper}
            patches = {
                'read_pin': {'side_effect': lambda path, pin: source_map[Path(path)]},
                'load_reference_helper': {'return_value': helper},
                'read_fixed': {'side_effect': lambda path, *a, **k: capture_raw if Path(path) == args.capture else actual_raw},
                'runtime_import': {'return_value': (object(), torch)},
                'original_namespace': {'return_value': {'mock-namespace': True}},
                'original_policy': {'return_value': {'mock-policy': True}},
                'checked_arrays': {'return_value': (object(), object())},
                'evaluate': {'return_value': {'numeric_pass': True, 'bit_exact': False, 'hash_exact': False}},
                'write_receipt': {},
                'digest': {'side_effect': mock_digest},
            }
            for name, options in patches.items():
                spies[name] = stack.enter_context(mock.patch.object(n, name, **options))
            stack.enter_context(mock.patch.object(n.time, 'monotonic', return_value=1.))
            spies['audit_install'] = stack.enter_context(mock.patch.object(sys, 'addaudithook'))
            yield args, spies

    def test_mock_complete_both_runtime_gates_use_same_fixed_historical_profile(self):
        with self.mocked_run() as (args, spies):
            report = n.run(args)
        self.assertEqual(report['status'], 'N0_LIMITED_TOLERANCE_PASS')
        self.assertEqual(report['stage'], 'COMPLETE')
        self.assertFalse(report['full_block_pass'])
        self.assertTrue(report['numeric_pass'])
        self.assertFalse(report['bit_exact'])
        self.assertFalse(report['hash_exact'])
        calls = spies['helper'].runtime_before.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].args[2], PINS['python_profiles']['historical'])
        self.assertIs(calls[0].args[2], calls[1].args[2])
        self.assertIs(calls[0].args[2], calls[0].args[3]['python_profiles']['historical'])
        self.assertEqual(calls[0].args[3], PINS)
        spies['runtime_import'].assert_called_once()
        spies['checked_arrays'].assert_called_once()
        spies['evaluate'].assert_called_once()
        spies['write_receipt'].assert_called_once_with(args.out, report)

    def test_mock_runtime_identity_failure_prevents_import_and_comparison(self):
        for code in ('RUNTIME', 'SHA'):
            with self.mocked_run(before_error=code) as (args, spies):
                report = n.run(args)
            self.assertEqual((report['status'], report['stage'], report['code']),
                             ('NOT_COMPLETED', 'RUNTIME_IDENTITY', code))
            self.assertIsNone(report['numeric_pass'])
            spies['runtime_import'].assert_not_called()
            spies['checked_arrays'].assert_not_called()
            spies['evaluate'].assert_not_called()
            spies['audit_install'].assert_not_called()

    def test_mock_postflight_drift_prevents_numeric_success_receipt(self):
        with self.mocked_run(after_drift=True) as (args, spies):
            report = n.run(args)
        self.assertEqual((report['status'], report['stage'], report['code']),
                         ('NOT_COMPLETED', 'POSTFLIGHT', 'CHANGED'))
        self.assertIsNone(report['numeric_pass'])
        self.assertFalse(report['full_block_pass'])
        spies['evaluate'].assert_called_once()

    def test_mock_missing_historical_has_no_ci_fallback(self):
        pins = json.loads(PINS_RAW)
        del pins['python_profiles']['historical']
        with self.mocked_run(pins_raw=json.dumps(pins).encode()) as (args, spies):
            report = n.run(args)
        self.assertEqual((report['status'], report['stage'], report['code']),
                         ('NOT_COMPLETED', 'RUNTIME_IDENTITY', 'UNEXPECTED'))
        spies['helper'].runtime_before.assert_not_called()
        spies['runtime_import'].assert_not_called()
        spies['evaluate'].assert_not_called()

    def test_mock_b_retirement_ack0_and_complete_payload_gate_before_runtime(self):
        mutations = [lambda c: c.update(successful_b=12287),
                     lambda c: c['axi'].update(bs=12287),
                     lambda c: c.update(completion_acks=0),
                     lambda c: c.update(actual_values=196607),
                     lambda c: c.update(further_eval_calls=1)]
        for change in mutations:
            with self.mocked_run(capture_change=change) as (args, spies):
                report = n.run(args)
            self.assertEqual((report['status'], report['stage'], report['code']),
                             ('NOT_COMPLETED', 'CAPTURE', 'CAPTURE'))
            spies['helper'].runtime_before.assert_not_called()
            spies['runtime_import'].assert_not_called()
            spies['evaluate'].assert_not_called()

    def test_no_numerical_runtime_loaded(self):
        self.assertFalse(any(name.split('.')[0] in ('torch', 'numpy', 'transformers')
                             for name in sys.modules))


if __name__ == '__main__':
    unittest.main()
