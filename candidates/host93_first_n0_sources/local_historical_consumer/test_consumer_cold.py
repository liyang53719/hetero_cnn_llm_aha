"""Stdlib-only source and opaque-mock tests; no runtime/FP32 payload reads."""
import ast
import contextlib
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = Path(__file__).absolute().parent
REPO = Path(os.environ['N0_CONSUMER_SOURCE_REPO'])
PIN = (10384, '9c484ba21665fc0f0a92845d579e8566d3e538f776bcb9bc027e8904a5258129')
MOCK_PYTHON = Path('/mock-python/python3.12')
MOCK_RUNTIME = Path('/mock-private/runtime')
MOCK_REFERENCE = Path('/mock-private/reference/n0.f32le')
MOCK_RECEIPT = MOCK_REFERENCE.parent / 'RECEIPT.json'
TEST_PIN = (31109, 'f1f3e3f5239c43f5aa8bb73b45aaed44d5a89e5971195666bdf02442d56c2b04')


def load(raw, pin, name, filename):
    if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
        raise ValueError('FLAGS')
    if type(raw) is not bytes or (len(raw), hashlib.sha256(raw).hexdigest()) != pin:
        raise ValueError('SOURCE')
    module = types.ModuleType(name)
    module.__file__ = str(filename)
    exec(compile(raw, '<' + name + '>', 'exec', dont_inherit=True), module.__dict__)
    return module


def audit(event, values):
    if ((event == 'import' and values[0].split('.')[0] in ('numpy', 'torch', 'transformers')) or
            event.startswith(('socket.', 'subprocess.', 'ctypes.dlopen')) or
            event in ('os.system', 'os.fork', 'os.posix_spawn', 'os.exec')):
        raise RuntimeError('COLD_ONLY')


sys.addaudithook(audit)
CONSUMER_RAW = (HERE / 'consumer.py').read_bytes()
c = load(CONSUMER_RAW, PIN, '_fixed_consumer', HERE / 'consumer.py')
P, BUFFERS = c.load_pipeline(REPO, c.SOURCE_PINS)
REFPINS = P.decode(BUFFERS[c.REFERENCE + 'PINS.json'])
base = load((HERE / 'test_inherited_numeric.py').read_bytes(), TEST_PIN,
            '_fixed_inherited_numeric', HERE / 'test_inherited_numeric.py')


def identities():
    result = {name: {key: pin[key] for key in ('bytes', 'sha256')}
              for name, pin in REFPINS['runtime_native_files'].items()}
    result['python'] = {key: REFPINS['python_profiles']['historical'][key]
                        for key in ('bytes', 'sha256')}
    return result


def receipt_fixture():
    return dict(schema=1, scope='FROZEN_M128_N0_REFERENCE_ONLY', status='PASS_FROZEN_N0_EXACT',
        stage='COMPLETE', code=None, reference_accepted=True, python_profile='historical',
        rtl_executed=False, fullblock_executed=False, source_identities=REFPINS['sources'],
        input_identities=REFPINS['raw2'], runtime_requirements=REFPINS['runtime_requirements'],
        runtime_before=identities(), runtime_after=identities(),
        observed_runtime={key: REFPINS['runtime_requirements'][key] for key in
                          ('capability', 'numpy', 'torch', 'torch_build_sha256', 'torch_commit')},
        output=dict(native=c.BF16, fp32le=c.F32, native_exact=True, fp32le_exact=True, accepted=True))


class Source(unittest.TestCase):
    def test_every_function_ast_unchanged_and_exact_inverse(self):
        original = BUFFERS[c.PIPELINE]
        candidate = (HERE / 'pipeline_historical.py').read_bytes()
        self.assertEqual(candidate.replace(c.NEW, c.OLD), original)
        def functions(raw):
            return {node.name: ast.dump(node, include_attributes=False)
                    for node in ast.parse(raw).body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
        self.assertEqual(functions(original), functions(candidate))
        self.assertEqual(P.COMPARISON, c.COMPARISON)

    def test_front_access_exact_three_keys(self):
        tree = ast.parse((HERE / 'pipeline_historical.py').read_bytes())
        node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'run_numeric')
        keys = {node.slice.value for node in ast.walk(node) if isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Name) and node.value.id == 'front'}
        self.assertEqual(keys, {'inputs', 'runtime', 'reference'})

    def test_source_inputs_reject_wrong_historical_worker_before_read(self):
        pins = dict(c.SOURCE_PINS)
        pins[c.COMPARISON + 'n0_compare.py'] = {'bytes': 20997, 'sha256': '0' * 64}
        with mock.patch.object(c, 'read', side_effect=AssertionError('read')) as read:
            with self.assertRaises(c.Rejected) as error:
                c.load_pipeline(REPO, pins)
            self.assertEqual(error.exception.code, 'PINS')
            read.assert_not_called()

    def test_same_buffer_loader_and_precompile_bad_size_sha(self):
        raw = BUFFERS[c.PIPELINE]
        compiler = compile
        with mock.patch.object(c, 'read', side_effect=AssertionError('reopen')):
            with mock.patch('builtins.compile', wraps=compiler) as observed:
                c.module(raw, c.SOURCE_PINS[c.PIPELINE], '_same_buffer')
        selected = [call for call in observed.call_args_list if call.args[1] == '<_same_buffer>']
        self.assertEqual(len(selected), 1)
        self.assertIs(selected[0].args[0], raw)
        for bad in (raw + b' ', bytes([raw[0] ^ 1]) + raw[1:]):
            with mock.patch('builtins.compile', side_effect=AssertionError('compile')) as compiler:
                with self.assertRaises(c.Rejected):
                    c.module(bad, c.SOURCE_PINS[c.PIPELINE], '_bad')
                compiler.assert_not_called()

    def test_read_rejects_symlink_and_changed_size(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'source'
            p.write_bytes(b'x')
            link = Path(directory) / 'link'
            link.symlink_to(p)
            for path in (p, link):
                with self.assertRaises(c.Rejected):
                    c.read(path, c.PROJECTED_PIN)

    def test_synthetic_prior_receipt_exact_fixed_identity(self):
        raw = (json.dumps(receipt_fixture(), sort_keys=True, indent=2) + '\n').encode()
        self.assertEqual(c.checked(raw, c.RECEIPT_PIN), raw)

    def test_full_window_gate_preserves_120_tail_without_reset(self):
        with mock.patch.object(c.time, 'monotonic', return_value=100.):
            self.assertEqual(c.require_numeric_window(3820.), 3715.)
            self.assertEqual(c.require_numeric_window(6600.), 6495.)
            self.assertEqual(c.require_numeric_window(3820.) - 15, 3820. - 120)
            for deadline in (3819.999, 200.):
                with self.assertRaises(c.Rejected) as error:
                    c.require_numeric_window(deadline)
                self.assertEqual(error.exception.code, 'INCOMPLETE_N0_WINDOW')
            for deadline in (True, float('nan'), float('inf'), '6600'):
                with self.assertRaises(c.Rejected):
                    c.require_numeric_window(deadline)


class Prepare(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self, *, receipt_change=None, runtime_error=False, source_drift=False, times=None):
        receipt = receipt_fixture()
        if receipt_change:
            receipt_change(receipt)
        receipt_raw = (json.dumps(receipt, sort_keys=True, indent=2) + '\n').encode()
        helper = types.SimpleNamespace(Rejected=ValueError,
            runtime_before=mock.Mock(side_effect=ValueError('private') if runtime_error else None,
                                     return_value=identities()))
        def read(pathname, pin):
            p = Path(pathname)
            if p == MOCK_RECEIPT:
                self.assertEqual(pin, c.RECEIPT_PIN)
                return receipt_raw
            if p == MOCK_REFERENCE:
                self.assertEqual(pin, c.F32)
                return b'opaque-reference-token-not-an-array'
            name = str(p.relative_to(REPO))
            return BUFFERS[name] + (b' ' if source_drift and name == c.PIPELINE else b'')
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(c, 'load_pipeline', return_value=(P, BUFFERS)))
            stack.enter_context(mock.patch.object(c, 'module', return_value=helper))
            reader = stack.enter_context(mock.patch.object(c, 'read', side_effect=read))
            stack.enter_context(mock.patch.object(Path, 'is_dir', return_value=True))
            stack.enter_context(mock.patch.object(sys, 'executable', str(MOCK_PYTHON)))
            stack.enter_context(mock.patch.object(sys, 'version_info', (3, 12, 99)))
            stack.enter_context(mock.patch.object(c.time, 'monotonic', side_effect=times, return_value=100.))
            yield helper, reader

    def prepare(self, **changes):
        binding = dict(runtime_root=MOCK_RUNTIME, reference_file=MOCK_REFERENCE,
                       reference_receipt=MOCK_RECEIPT)
        binding.update(changes)
        return c.prepare(REPO, Path('/opaque-canonical-inputs'), c.SOURCE_PINS, 10000.,
                         **binding)

    def test_explicit_binding_rejects_wrong_leaf_and_split_reference_parent(self):
        changes = [dict(runtime_root=Path('/mock-private/other-runtime')),
                   dict(reference_file=Path('/mock-private/reference/other.f32le')),
                   dict(reference_file=Path('/mock-private/other/n0.f32le')),
                   dict(reference_receipt=Path('/mock-private/reference/other.json')),
                   dict(reference_receipt=Path('/split/reference/RECEIPT.json')),
                   dict(runtime_root=Path('relative/runtime')),
                   dict(runtime_root=Path('/mock-private/../runtime'))]
        for change in changes:
            with self.fixture() as (helper, reader):
                with self.assertRaises(c.Rejected) as error:
                    self.prepare(**change)
                self.assertEqual(error.exception.code, 'PATH')
                helper.runtime_before.assert_not_called()
                reader.assert_not_called()

    def test_explicit_binding_is_required_without_environment_fallback(self):
        with mock.patch.object(c, 'load_pipeline', side_effect=AssertionError('source')) as source:
            with self.assertRaises(TypeError):
                c.prepare(REPO, Path('/opaque-canonical-inputs'), c.SOURCE_PINS, 10000.)
            source.assert_not_called()

    def test_explicit_front_and_static_observation_without_reference_or_host_execution(self):
        with self.fixture() as (helper, reader):
            run_numeric, front, observation = self.prepare()
        self.assertIs(run_numeric, P.run_numeric)
        self.assertEqual(front, {'inputs': Path('/opaque-canonical-inputs'),
            'runtime': MOCK_RUNTIME, 'reference': MOCK_REFERENCE})
        self.assertEqual(set(front), {'inputs', 'runtime', 'reference'})
        helper.runtime_before.assert_called_once_with(MOCK_RUNTIME, MOCK_PYTHON,
            REFPINS['python_profiles']['historical'], REFPINS)
        self.assertFalse(observation['frontdoor_completed_here'])
        self.assertFalse(observation['reference_regenerated_here'])
        self.assertFalse(observation['current_runtime_dispatch_qualified_here'])
        self.assertFalse(observation['host_or_comparison_executed_here'])
        self.assertEqual(observation['existing_reference_receipt'], c.RECEIPT_PIN)
        self.assertIn(mock.call(MOCK_REFERENCE, c.F32), reader.call_args_list)

    def test_wrong_python_rejected_before_runtime_gate(self):
        with self.fixture() as (helper, reader):
            with mock.patch.object(sys, 'executable', '/wrong-python'):
                with self.assertRaises(c.Rejected) as error:
                    self.prepare()
            self.assertEqual(error.exception.code, 'PYTHON')
            helper.runtime_before.assert_not_called()
            reader.assert_not_called()

    def test_runtime_identity_failure_rejects_before_reference(self):
        with self.fixture(runtime_error=True) as (helper, reader):
            with self.assertRaises(c.Rejected) as error:
                self.prepare()
            self.assertEqual(error.exception.code, 'RUNTIME')
            reader.assert_not_called()

    def test_no_prior_receipt_relabel_or_changed_qualification(self):
        changes = [lambda r: r.update(python_profile='ci31214'),
                   lambda r: r.update(reference_accepted=False),
                   lambda r: r['output'].update(native_exact=False),
                   lambda r: r['runtime_after']['python'].update(sha256='0' * 64)]
        for change in changes:
            with self.fixture(receipt_change=change):
                with self.assertRaises(c.Rejected) as error:
                    self.prepare()
                self.assertEqual(error.exception.code, 'REFERENCE')

    def test_source_postflight_rejects_drift(self):
        with self.fixture(source_drift=True):
            with self.assertRaises(c.Rejected) as error:
                self.prepare()
            self.assertEqual(error.exception.code, 'CHANGED')

    def test_preflight_elapsed_time_can_exhaust_full_numeric_window(self):
        with self.fixture(times=[100., 100., 7000., 7000.]):
            with self.assertRaises(c.Rejected) as error:
                self.prepare()
            self.assertEqual(error.exception.code, 'INCOMPLETE_N0_WINDOW')


class LocalNumeric(base.Fixture):
    def test_actual_original_function_wires_historical_source_and_relocated_inputs(self):
        self.front = {'inputs': self.root / 'inputs', 'runtime': MOCK_RUNTIME, 'reference': MOCK_REFERENCE}
        with mock.patch.object(sys, 'executable', str(MOCK_PYTHON)):
            self.assertTrue(self.numeric(c.require_numeric_window(3820.)))
        call = self.calls[1]
        self.assertEqual(call[0], 'host93_n0_compare')
        argv = call[1]
        self.assertEqual(argv[0], str(MOCK_PYTHON))
        self.assertEqual(argv[6], str(self.repo / c.COMPARISON / 'n0_compare.py'))
        for flag, value in (('--runtime-root', MOCK_RUNTIME), ('--reference', MOCK_REFERENCE),
                            ('--python', MOCK_PYTHON)):
            self.assertEqual(argv[argv.index(flag) + 1], str(value))
        self.assertNotIn('--python-profile', argv)
        self.assertEqual(call[4], base.A.limits(30, 15, 25, 8 * base.A.GIB, 4 * base.A.MIB))
        self.assertEqual(self.completed, ['n0_capture', 'n0_comparison'])
        self.assertFalse(self.obs['runtime_ready'])
        self.assertFalse(self.obs['reference_ready'])
        self.assertLessEqual(float(argv[argv.index('--shared-stop') + 1]), 3820. - 120)


class RuntimeCold(unittest.TestCase):
    def test_no_numerical_imports(self):
        self.assertFalse(any(name.split('.')[0] in ('numpy', 'torch', 'transformers') for name in sys.modules))


if __name__ == '__main__':
    unittest.main()
