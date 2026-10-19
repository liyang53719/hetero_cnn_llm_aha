"""Fixed-source, pure/mock PC01 capture tests. Never starts a child or long array."""
import argparse
import ast
import builtins
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
PINS = {'run_capture.py': (23328, '919395b434c82f4130385152c6e1a04f73feee1a71af76e0dfde8461a20d4640'), 'launch.py': (2047, 'd73e3a84efee9ebe64e5e03ab44f05d77649a95efbd313255347c327c6baf978')}


def audit(event, args):
    if event.startswith(('socket.', 'subprocess.')) or event in (
        'os.system', 'os.fork', 'os.forkpty', 'os.exec', 'os.posix_spawn',
        'ctypes.dlopen', 'urllib.Request'
    ):
        raise RuntimeError('COLD_NATIVE_NETWORK_FORBIDDEN')
    if event == 'import' and str(args[0]).split('.')[0] in ('numpy', 'scipy', 'torch', 'ctypes'):
        raise RuntimeError('COLD_NUMERICAL_IMPORT_FORBIDDEN')


sys.addaudithook(audit)


def pin(raw):
    return (len(raw), hashlib.sha256(raw).hexdigest())


def load(name, directory=HERE):
    if PINS is None:
        raise RuntimeError('COLD_SOURCE_FREEZE_REQUIRED')
    path = directory / name
    raw = path.read_bytes()
    if pin(raw) != PINS[name]:
        raise RuntimeError('COLD_FIXED_SOURCE_IDENTITY')
    result = types.ModuleType('cold_' + name.replace('.', '_'))
    result.__file__ = str(path)
    exec(compile(raw, str(path), 'exec', dont_inherit=True), result.__dict__)
    return result


R = load('run_capture.py')
E = load('launch.py')


def good_stage(name='fresh_pc0_through_ack1', argv=None, cwd='/fixed/work'):
    return {
        'name': name,
        'record': {
            'exit_code': 0, 'status': 'PASS', 'cleanup_confirmed': True,
            'timed_out': False, 'reaped': True, 'parent_exception': None,
            'group_state': 'absent',
            'exit_observed_while_unreaped': {'code': 1, 'status': 0},
            'argv': argv or ['/fixed/prior/pc01', '/fixed/inputs', '/fixed/work/capture'],
            'cwd': cwd,
        },
        'diagnostics': {
            'receipt_timed_out': False, 'waitid_code': 1, 'waitid_status': 0,
            'cleanup_confirmed': True, 'exit_code': 0,
            'failure_boundary': 'NONE', 'failure_code': 'NONE',
        },
        'usage': {'maxrss_kib_cumulative_parent_children': 4096},
    }


def observation():
    return {
        'status': 'COMPLETE_DATA_OBSERVATION_ONLY',
        'typed_reference': {'bit_exact': True, 'hash_exact': True, 'mismatch_values': 0},
        'math_reference_f32': {'diagnostic': 'synthetic, no real arrays'},
        'math_reference_f64': {'diagnostic': 'synthetic, no real arrays'},
        'full_block_pass': False,
    }


class FixedLoader(unittest.TestCase):
    def test_size_and_same_length_hash_are_checked_before_compile(self):
        for name in PINS:
            source = (HERE / name).read_bytes()
            for changed in (source[:-1], source + b'\n', bytes([source[0] ^ 1]) + source[1:]):
                with self.subTest(name=name, bytes=len(changed)), tempfile.TemporaryDirectory(dir=HERE) as folder:
                    root = Path(folder)
                    (root / name).write_bytes(changed)
                    with mock.patch.object(builtins, 'compile', side_effect=AssertionError('compiled unpinned bytes')) as compiler:
                        with self.assertRaisesRegex(RuntimeError, 'COLD_FIXED_SOURCE_IDENTITY'):
                            load(name, root)
                        compiler.assert_not_called()

    def test_loader_compiles_the_same_verified_buffer_once(self):
        name = 'run_capture.py'
        source = (HERE / name).read_bytes()
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            root = Path(folder)
            path = root / name
            path.write_bytes(source)
            original = builtins.compile
            seen = []
            def compile_buffer(raw, *args, **kwargs):
                seen.append(raw)
                path.write_bytes(b'raise RuntimeError("MUST_NOT_COMPILE")\n')
                return original(raw, *args, **kwargs)
            with mock.patch.object(builtins, 'compile', side_effect=compile_buffer):
                loaded = load(name, root)
            self.assertEqual(loaded.CAPTURE_TOTAL, 10410)
            self.assertEqual(seen, [source])

    def test_production_contracts_do_not_use_optimizable_asserts(self):
        for name in PINS:
            raw = (HERE / name).read_bytes()
            self.assertEqual(pin(raw), PINS[name])
            self.assertFalse(any(isinstance(n, ast.Assert) for n in ast.walk(ast.parse(raw))))

    def test_source_import_has_no_top_level_run(self):
        for name in PINS:
            tree = ast.parse((HERE / name).read_bytes())
            for node in tree.body:
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                    self.assertNotIn(getattr(node.value.func, 'id', ''), ('run', 'main', 'capture_sequence'))

    def test_audit_denies_native_network_and_ctypes(self):
        for event in ('subprocess.Popen', 'socket.connect', 'os.system', 'os.fork',
                      'os.forkpty', 'os.exec', 'os.posix_spawn', 'ctypes.dlopen', 'urllib.Request'):
            with self.subTest(event=event), self.assertRaisesRegex(RuntimeError, 'COLD_NATIVE_NETWORK_FORBIDDEN'):
                sys.audit(event)
        for name in ('numpy', 'scipy', 'torch', 'ctypes'):
            with self.subTest(name=name), self.assertRaisesRegex(RuntimeError, 'COLD_NUMERICAL_IMPORT_FORBIDDEN'):
                audit('import', (name,))


class CaptureSequence(unittest.TestCase):
    def setUp(self):
        self.work = Path('/fixed/work')
        self.argv = ['/fixed/prior/pc01', '/fixed/inputs', '/fixed/work/capture']
        self.env = {'PATH': '/fixed/work/empty-path', 'LANG': 'C'}
        self.owner = {'deadline': 10620.0, 'handler': object()}
        self.result = {'stages': [], 'full_block_pass': False, 'baseline_adopted': False}
        self.expected = good_stage(argv=self.argv)
        self.compare = mock.Mock(return_value=observation())
        self.preflight = mock.Mock()
        self.admit = mock.Mock(return_value={'mock_admission': True})
        self.calls = []
        self.phase_failure = None
        def phase(*args):
            self.calls.append(args)
            args[10].update(self.expected['diagnostics'])
            if self.phase_failure is not None:
                raise self.phase_failure
            return self.expected['record'], '{}', self.expected['usage']
        self.supervisor = types.SimpleNamespace(run_phase=phase)
        clock = mock.patch.object(R.time, 'monotonic', return_value=0.0)
        self.clock = clock.start()
        self.addCleanup(clock.stop)

    def go(self, stop=10620.0):
        return R.capture_sequence(self.supervisor, 'support', 'base', self.work, self.argv,
                                  self.env, stop, self.owner, self.preflight, self.compare, self.result, self.admit)

    def test_exactly_one_fresh_capture_and_complete_saved_observation(self):
        actual = self.go()
        self.assertIs(actual, self.compare.return_value)
        self.assertIs(self.result['comparison'], actual)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(self.result['stages']), 1)
        self.assertEqual(self.result['stages'][0], self.expected)
        self.assertEqual(self.preflight.call_count, 3)
        self.compare.assert_called_once_with(10500.0)
        self.assertFalse(self.result['full_block_pass'])
        self.assertFalse(self.result['baseline_adopted'])

    def test_phase_argv_cwd_owner_and_environment_are_forwarded_exactly(self):
        self.go()
        args = self.calls[0]
        self.assertEqual(args[:3], ('support', 'base', 'pc01_capture'))
        self.assertIs(args[3], self.argv)
        self.assertEqual(args[4:6], (self.work, self.work / 'phases/capture'))
        self.assertIs(args[6], self.env)
        self.assertEqual(args[8], 10620.0)
        self.assertIs(args[9], self.owner)
        self.assertIs(args[10], self.result['stages'][0]['diagnostics'])

    def test_exact_finite_phase_limits(self):
        self.go()
        self.assertEqual(self.calls[0][7], {
            'total_seconds': 10410, 'work_seconds': 10395, 'cpu_seconds': 10395,
            'as_bytes': 6 * 1024**3, 'fsize_bytes': 16 * R.MIB,
            'tree_bytes': 64 * R.MIB, 'log_bytes': R.MIB,
            'sample_rows': 10412, 'file_count': 64, 'entry_count': 128,
        })

    def test_admission_occurs_after_preflight_before_phase(self):
        order = []
        self.preflight.side_effect = lambda: order.append('preflight')
        self.admit.side_effect = lambda: order.append('admit') or {'mock_admission': True}
        phase = self.supervisor.run_phase
        self.supervisor.run_phase = lambda *args: (order.append('phase'), phase(*args))[1]
        self.go()
        self.assertEqual(order[:3], ['preflight', 'admit', 'phase'])
        self.admit.assert_called_once_with()
        self.assertEqual(self.result['pre_native_admission'], {'mock_admission': True})

    def test_admission_failure_prevents_phase_and_comparison(self):
        first = ValueError('synthetic resource failure')
        self.admit.side_effect = first
        with self.assertRaises(ValueError) as caught:
            self.go()
        self.assertIs(caught.exception, first)
        self.assertEqual(self.calls, [])
        self.compare.assert_not_called()

    def test_initial_full_window_rejected_before_preflight_or_phase(self):
        self.clock.return_value = 30.0001
        with self.assertRaisesRegex(ValueError, 'INCOMPLETE_CAPTURE_WINDOW'):
            self.go()
        self.preflight.assert_not_called()
        self.assertEqual(self.calls, [])
        self.compare.assert_not_called()

    def test_second_full_window_rejected_after_preflight_before_phase(self):
        self.clock.side_effect = [0.0, 30.0001]
        with self.assertRaisesRegex(ValueError, 'INCOMPLETE_CAPTURE_WINDOW'):
            self.go()
        self.preflight.assert_called_once_with()
        self.assertEqual(self.calls, [])
        self.compare.assert_not_called()

    def test_both_full_window_exact_boundaries_allowed(self):
        self.clock.side_effect = [30.0, 30.0, 10499.999]
        self.go()
        self.assertEqual(len(self.calls), 1)
        self.compare.assert_called_once_with(10500.0)

    def test_preflight_failure_prevents_native_phase(self):
        first = ValueError('synthetic preflight failure')
        self.preflight.side_effect = first
        with self.assertRaises(ValueError) as caught:
            self.go()
        self.assertIs(caught.exception, first)
        self.assertEqual(self.calls, [])
        self.compare.assert_not_called()

    def test_phase_exception_is_first_failure_and_stage_is_saved(self):
        first = RuntimeError('synthetic phase failure')
        self.phase_failure = first
        with self.assertRaises(RuntimeError) as caught:
            self.go()
        self.assertIs(caught.exception, first)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(self.result['stages']), 1)
        self.assertIsNone(self.result['stages'][0]['record'])
        self.assertIsNone(self.result['stages'][0]['usage'])
        self.assertEqual(self.result['stages'][0]['diagnostics'], self.expected['diagnostics'])
        self.compare.assert_not_called()

    def test_nonzero_or_boolean_exit_stops_before_comparison(self):
        for code in (7, False, True, '0', None):
            with self.subTest(code=code):
                self.expected['record']['exit_code'] = code
                with self.assertRaisesRegex(ValueError, 'NATURAL_EXIT_CLEANUP'):
                    self.go()
                self.compare.assert_not_called()

    def test_natural_exit_cleanup_and_no_timeout_evidence_required(self):
        mutations = [
            ('record', 'status', 'FAIL'), ('record', 'cleanup_confirmed', False),
            ('record', 'timed_out', True), ('record', 'reaped', False),
            ('record', 'parent_exception', 'failure'), ('record', 'group_state', 'live'),
            ('record', 'exit_observed_while_unreaped', {'code': 2, 'status': 0}),
            ('record', 'exit_observed_while_unreaped', {'code': 1, 'status': 9}),
            ('diagnostics', 'receipt_timed_out', True), ('diagnostics', 'waitid_code', 2),
            ('diagnostics', 'waitid_status', 9), ('diagnostics', 'cleanup_confirmed', False),
            ('diagnostics', 'exit_code', 9), ('diagnostics', 'failure_boundary', 'TIMEOUT'),
            ('diagnostics', 'failure_code', 'FAIL'),
        ]
        for section, key, value in mutations:
            with self.subTest(section=section, key=key):
                self.expected = good_stage(argv=self.argv)
                self.expected[section][key] = value
                with self.assertRaisesRegex(ValueError, 'NATURAL_EXIT_CLEANUP'):
                    self.go()
                self.compare.assert_not_called()

    def test_actual_argv_and_cwd_mismatch_block_comparison(self):
        for key, value in (('argv', ['/fixed/prior/other']), ('cwd', '/elsewhere')):
            with self.subTest(key=key):
                self.expected = good_stage(argv=self.argv)
                self.expected['record'][key] = value
                with self.assertRaisesRegex(ValueError, 'CAPTURE_ACTUAL_ARGV'):
                    self.go()
                self.compare.assert_not_called()

    def test_invalid_cumulative_rss_blocks_comparison(self):
        for value in (-1, True, 6 * 1024**2 + 1, 4096.0, '4096', None):
            with self.subTest(value=value):
                self.expected['usage']['maxrss_kib_cumulative_parent_children'] = value
                with self.assertRaisesRegex(ValueError, 'CUMULATIVE_RSS_6G'):
                    self.go()
                self.compare.assert_not_called()

    def test_exact_cumulative_rss_boundary_allowed(self):
        self.expected['usage']['maxrss_kib_cumulative_parent_children'] = 6 * 1024**2
        self.go()
        self.assertEqual(len(self.calls), 1)

    def test_post_phase_preflight_failure_blocks_comparison(self):
        first = RuntimeError('post phase drift')
        self.preflight.side_effect = [None, first]
        with self.assertRaises(RuntimeError) as caught:
            self.go()
        self.assertIs(caught.exception, first)
        self.assertEqual(len(self.result['stages']), 1)
        self.compare.assert_not_called()

    def test_comparison_window_is_strictly_before_reserved_tail(self):
        self.clock.side_effect = [0.0, 0.0, 10500.0]
        with self.assertRaisesRegex(ValueError, 'INCOMPLETE_COMPARISON_WINDOW'):
            self.go()
        self.assertEqual(len(self.calls), 1)
        self.compare.assert_not_called()

    def test_comparison_exception_preserved_without_success_observation(self):
        first = RuntimeError('synthetic comparison failure')
        self.compare.side_effect = first
        with self.assertRaises(RuntimeError) as caught:
            self.go()
        self.assertIs(caught.exception, first)
        self.assertNotIn('comparison', self.result)
        self.assertEqual(len(self.result['stages']), 1)

    def test_typed_mismatch_preserves_the_entire_three_reference_observation(self):
        for key, value in (('bit_exact', False), ('hash_exact', False), ('mismatch_values', 1)):
            with self.subTest(key=key):
                report = observation()
                report['typed_reference'][key] = value
                report['typed_reference']['first_mismatch'] = {'index': 3, 'rtl_bits': '00000000', 'reference_bits': '00000001'}
                self.compare.return_value = report
                with self.assertRaisesRegex(ValueError, 'TYPED_REFERENCE_MISMATCH'):
                    self.go()
                self.assertIs(self.result['comparison'], report)
                self.assertIn('math_reference_f32', self.result['comparison'])
                self.assertIn('math_reference_f64', self.result['comparison'])

    def test_noncomplete_comparison_is_saved_but_rejected(self):
        report = observation()
        report['status'] = 'INCOMPLETE'
        self.compare.return_value = report
        with self.assertRaisesRegex(ValueError, 'TYPED_REFERENCE_MISMATCH'):
            self.go()
        self.assertIs(self.result['comparison'], report)

    def test_final_preflight_failure_keeps_complete_observation(self):
        first = RuntimeError('post comparison drift')
        self.preflight.side_effect = [None, None, first]
        with self.assertRaises(RuntimeError) as caught:
            self.go()
        self.assertIs(caught.exception, first)
        self.assertIs(self.result['comparison'], self.compare.return_value)


class TailEvidence(unittest.TestCase):
    def setUp(self):
        self.work = Path('/mock/work')
        self.result = {'stages': []}
        self.h = types.SimpleNamespace(save_preserving_failure=mock.Mock(side_effect=lambda w, r, failure: failure))
        clock = mock.patch.object(R.time, 'monotonic', return_value=100.0)
        self.clock = clock.start()
        self.addCleanup(clock.stop)
        timer = mock.patch.object(R.signal, 'setitimer')
        self.timer = timer.start()
        self.addCleanup(timer.stop)

    def test_tail_is_clamped_to_120_seconds_from_now(self):
        self.assertIsNone(R.save_tail(self.h, self.work, self.result, None, 1000.0))
        self.assertEqual(self.result['report_deadline_monotonic'], 220.0)
        self.timer.assert_called_once_with(signal.ITIMER_REAL, 120.0)
        self.h.save_preserving_failure.assert_called_once_with(self.work, self.result, None)

    def test_tail_never_extends_shared_deadline(self):
        self.assertIsNone(R.save_tail(self.h, self.work, self.result, None, 160.0))
        self.assertEqual(self.result['report_deadline_monotonic'], 160.0)
        self.timer.assert_called_once_with(signal.ITIMER_REAL, 60.0)

    def test_expired_tail_does_not_attempt_save(self):
        failure = R.save_tail(self.h, self.work, self.result, None, 100.0)
        self.assertIsInstance(failure, ValueError)
        self.assertEqual(str(failure), 'INCOMPLETE_EVIDENCE_WINDOW')
        self.timer.assert_not_called()
        self.h.save_preserving_failure.assert_not_called()

    def test_original_failure_survives_save_failure(self):
        first, second = ValueError('native first'), OSError('receipt second')
        self.h.save_preserving_failure.side_effect = second
        self.assertIs(R.save_tail(self.h, self.work, self.result, first, 1000.0), first)

    def test_original_failure_survives_timer_failure(self):
        first, second = ValueError('native first'), OSError('timer second')
        self.timer.side_effect = second
        self.assertIs(R.save_tail(self.h, self.work, self.result, first, 1000.0), first)
        self.h.save_preserving_failure.assert_not_called()

    def test_original_failure_survives_expired_evidence_window(self):
        first = RuntimeError('native first')
        self.assertIs(R.save_tail(self.h, self.work, self.result, first, 100.0), first)
        self.h.save_preserving_failure.assert_not_called()

    def test_save_failure_is_returned_without_prior_failure(self):
        second = OSError('receipt second')
        self.h.save_preserving_failure.side_effect = second
        self.assertIs(R.save_tail(self.h, self.work, self.result, None, 1000.0), second)

    def test_timer_failure_is_returned_without_prior_failure(self):
        second = OSError('timer second')
        self.timer.side_effect = second
        self.assertIs(R.save_tail(self.h, self.work, self.result, None, 1000.0), second)

    def test_late_timer_uses_positive_minimum_without_deadline_extension(self):
        self.clock.side_effect = [100.0, 219.999, 220.001]
        R.save_tail(self.h, self.work, self.result, None, 1000.0)
        self.timer.assert_called_once_with(signal.ITIMER_REAL, 0.001)
        self.assertEqual(self.result['report_deadline_monotonic'], 220.0)


class SupervisorProjection(unittest.TestCase):
    def test_only_fixed_6600_to_10620_projection_and_exact_inverse(self):
        raw = b'SHARED_SECONDS = 6600\nPRESERVED = 73\n'
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            path = Path(folder) / 'supervisor.py'
            path.write_bytes(raw)
            module, evidence = R.supervisor_projection(path, pin(raw))
        derived = raw.replace(b'SHARED_SECONDS = 6600\n', b'SHARED_SECONDS = 10620\n')
        self.assertEqual(module.SHARED_SECONDS, 10620)
        self.assertEqual(module.PRESERVED, 73)
        self.assertEqual(evidence, {'original': R.identity(raw), 'derived': R.identity(derived),
                                   'only_change': 'SHARED_SECONDS_6600_TO_10620', 'inverse_exact': True})
        self.assertEqual(derived.replace(b'SHARED_SECONDS = 10620\n', b'SHARED_SECONDS = 6600\n'), raw)

    def test_missing_duplicate_new_or_altered_anchor_rejected_before_compile(self):
        for raw in (b'SHARED_SECONDS = 6601\n', b'SHARED_SECONDS=6600\n',
                    b'SHARED_SECONDS = 6600\nSHARED_SECONDS = 6600\n',
                    b'SHARED_SECONDS = 6600\nSHARED_SECONDS = 10620\n'):
            with self.subTest(raw=raw), mock.patch.object(R, 'read', return_value=raw), \
                 mock.patch.object(builtins, 'compile', side_effect=AssertionError('bad projection compiled')) as compiler:
                with self.assertRaisesRegex(ValueError, 'SUPERVISOR_BUDGET_ANCHOR'):
                    R.supervisor_projection(Path('/mock/supervisor.py'), pin(raw))
                compiler.assert_not_called()

    def test_projected_execution_uses_only_checked_buffer(self):
        raw = b'SHARED_SECONDS = 6600\nPRESERVED = 73\n'
        original = builtins.compile
        seen = []
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            path = Path(folder) / 'supervisor.py'
            path.write_bytes(raw)
            def compile_buffer(data, *args, **kwargs):
                seen.append(data)
                path.write_bytes(b'raise RuntimeError("MUST_NOT_COMPILE")\n')
                return original(data, *args, **kwargs)
            with mock.patch.object(builtins, 'compile', side_effect=compile_buffer):
                actual, _ = R.supervisor_projection(path, pin(raw))
        self.assertEqual(actual.PRESERVED, 73)
        self.assertEqual(seen, [raw.replace(b'SHARED_SECONDS = 6600\n', b'SHARED_SECONDS = 10620\n')])


class ReceiptAcceptance(unittest.TestCase):
    def setUp(self):
        self.work = Path('/fixed/relink')
        self.commands = {'compile': ['/fixed/g++', '-c', '/fixed/source'],
                         'link': ['/fixed/g++', '/fixed/object', '-o', '/fixed/relink/pc01']}
        self.r = types.SimpleNamespace(CATALOG_PIN=(1, 'a' * 64), REUSE_PIN=(2, 'b' * 64),
                                       commands=mock.Mock(return_value=self.commands))
        self.relink = {
            'schema': 1, 'status': 'COMPLETE_DRIVER_COMPILE_LINK_ONLY', 'scope': 'DRIVER_COMPILE_LINK_ONLY',
            'rtl_executed': False, 'pc01_executable_invoked': False, 'full_block_pass': False,
            'shared_seconds_cap': 180, 'cpu_affinity_count': 1, 'binary': {'identity': copy.deepcopy(R.ELF_PIN)},
            'stages': [good_stage(name, argv=argv, cwd=str(self.work)) for name, argv in self.commands.items()],
            'compiler_catalog_identity': {'bytes': 1, 'sha256': 'a' * 64},
            'reuse_identity': {'bytes': 2, 'sha256': 'b' * 64},
        }
        self.models = {
            'schema': 1, 'status': 'COMPLETE_SUPERVISED_TWO_REFERENCE_MODELS',
            'full_models_executed': True, 'rtl_executed': False, 'old_ram_resumed': False,
            'official_raw_numeric_pass': None, 'application_accuracy_pass': None, 'baseline_adopted': False,
            'stages': [good_stage(name) for name in ('compile', 'micro', 'full_models')],
            'outputs': {'outputs': copy.deepcopy(R.REFERENCE_PINS),
                        'result_identity': dict(zip(('bytes', 'sha256'), R.MODEL_RESULT_PIN))},
        }

    def accept_relink(self):
        return R.accept_relink(self.relink, self.r, 'catalog', self.work, 'contract')

    def test_valid_compile_link_only_receipt_accepted(self):
        self.assertIsNone(self.accept_relink())
        self.r.commands.assert_called_once_with('catalog', self.work, 'contract')

    def test_relink_fixed_scope_and_limits_rejected_on_drift(self):
        original = copy.deepcopy(self.relink)
        for key, value in (('schema', 2), ('status', 'COMPLETE'), ('scope', 'RUN_RTL'),
                           ('rtl_executed', True), ('pc01_executable_invoked', True), ('full_block_pass', True),
                           ('shared_seconds_cap', 181), ('cpu_affinity_count', 2)):
            with self.subTest(key=key):
                self.relink = copy.deepcopy(original)
                self.relink[key] = value
                with self.assertRaisesRegex(ValueError, 'RELINK_RECEIPT_SCOPE'):
                    self.accept_relink()

    def test_relink_stage_order_count_and_binary_hash_are_fixed(self):
        original = copy.deepcopy(self.relink)
        for stages in (original['stages'][::-1], original['stages'][:1], original['stages'] + [good_stage('execute')]):
            self.relink = copy.deepcopy(original)
            self.relink['stages'] = stages
            with self.assertRaisesRegex(ValueError, 'RELINK_RECEIPT_SCOPE'):
                self.accept_relink()
        self.relink = copy.deepcopy(original)
        self.relink['binary']['identity']['sha256'] = 'f' * 64
        with self.assertRaisesRegex(ValueError, 'RELINK_RECEIPT_SCOPE'):
            self.accept_relink()

    def test_relink_actual_argv_and_cwd_checked_for_both_stages(self):
        original = copy.deepcopy(self.relink)
        for index in (0, 1):
            for key, value in (('argv', ['/unauthorized/program']), ('cwd', '/changed/work')):
                with self.subTest(index=index, key=key):
                    self.relink = copy.deepcopy(original)
                    self.relink['stages'][index]['record'][key] = value
                    with self.assertRaisesRegex(ValueError, 'RELINK_ACTUAL_ARGV'):
                        self.accept_relink()

    def test_relink_natural_exit_cleanup_and_rss_apply_to_both_stages(self):
        original = copy.deepcopy(self.relink)
        for index in (0, 1):
            for section, key, value, code in (
                ('record', 'timed_out', True, 'NATURAL_EXIT_CLEANUP'),
                ('diagnostics', 'cleanup_confirmed', False, 'NATURAL_EXIT_CLEANUP'),
                ('usage', 'maxrss_kib_cumulative_parent_children', 6 * 1024**2 + 1, 'CUMULATIVE_RSS_6G'),
            ):
                with self.subTest(index=index, key=key):
                    self.relink = copy.deepcopy(original)
                    self.relink['stages'][index][section][key] = value
                    with self.assertRaisesRegex(ValueError, code):
                        self.accept_relink()

    def test_relink_catalog_and_reuse_identity_are_fixed(self):
        original = copy.deepcopy(self.relink)
        for key in ('compiler_catalog_identity', 'reuse_identity'):
            self.relink = copy.deepcopy(original)
            self.relink[key]['sha256'] = 'f' * 64
            with self.assertRaisesRegex(ValueError, 'RELINK_INPUT_IDENTITY'):
                self.accept_relink()

    def test_valid_full_models_receipt_accepted(self):
        self.assertIsNone(R.accept_models(self.models))

    def test_model_scope_is_observation_only_and_no_baseline_claim(self):
        original = copy.deepcopy(self.models)
        for key, value in (('schema', 2), ('status', 'COMPLETE'), ('full_models_executed', False),
                           ('rtl_executed', True), ('old_ram_resumed', True), ('official_raw_numeric_pass', True),
                           ('application_accuracy_pass', True), ('baseline_adopted', True)):
            with self.subTest(key=key):
                self.models = copy.deepcopy(original)
                self.models[key] = value
                with self.assertRaisesRegex(ValueError, 'MODEL_RECEIPT_SCOPE'):
                    R.accept_models(self.models)

    def test_model_stage_order_and_count_are_fixed(self):
        original = copy.deepcopy(self.models)
        for stages in (original['stages'][::-1], original['stages'][:2], original['stages'] + [good_stage('extra')]):
            self.models = copy.deepcopy(original)
            self.models['stages'] = stages
            with self.assertRaisesRegex(ValueError, 'MODEL_RECEIPT_SCOPE'):
                R.accept_models(self.models)

    def test_model_each_stage_must_have_natural_exit_cleanup(self):
        original = copy.deepcopy(self.models)
        for index in range(3):
            self.models = copy.deepcopy(original)
            self.models['stages'][index]['diagnostics']['receipt_timed_out'] = True
            with self.assertRaisesRegex(ValueError, 'NATURAL_EXIT_CLEANUP'):
                R.accept_models(self.models)

    def test_model_each_reference_hash_and_result_identity_are_fixed(self):
        original = copy.deepcopy(self.models)
        for name in R.REFERENCE_PINS:
            self.models = copy.deepcopy(original)
            self.models['outputs']['outputs'][name]['sha256'] = 'f' * 64
            with self.assertRaisesRegex(ValueError, 'MODEL_OUTPUT_IDENTITIES'):
                R.accept_models(self.models)
        self.models = copy.deepcopy(original)
        self.models['outputs']['result_identity']['bytes'] += 1
        with self.assertRaisesRegex(ValueError, 'MODEL_OUTPUT_IDENTITIES'):
            R.accept_models(self.models)


class CanonicalInputs(unittest.TestCase):
    def setUp(self):
        metadata_size = sum(row['bytes'] for row in R.METADATA_PINS.values())
        total = 94920448 - metadata_size
        self.spec = {'providers': [
            {'output_filename': f'input{i}.bin', 'output_bytes': 1 if i else total - 13,
             'expected_output_sha256': f'{i:064x}'} for i in range(14)]}

    def get_pins(self):
        with mock.patch.object(R, 'read', return_value=json.dumps(self.spec).encode()) as reader:
            value = R.input_pins(Path('/fixed/repo'))
        reader.assert_called_once_with(Path('/fixed/repo/candidates/host93_first_n0_sources/inputs/CONVERSION_SPEC.json'), R.SPEC_PIN)
        return value

    def test_exact_14_providers_plus_two_metadata_and_total_size(self):
        pins = self.get_pins()
        self.assertEqual(len(pins), 16)
        self.assertEqual(sum(p['bytes'] for p in pins.values()), 94920448)
        self.assertEqual({k: pins[k] for k in R.METADATA_PINS}, R.METADATA_PINS)
        for row in self.spec['providers']:
            self.assertEqual(pins['providers/' + row['output_filename']],
                             {'bytes': row['output_bytes'], 'sha256': row['expected_output_sha256']})

    def test_provider_missing_duplicate_extra_and_byte_total_rejected(self):
        original = copy.deepcopy(self.spec)
        cases = [original['providers'][:-1], original['providers'] + [copy.deepcopy(original['providers'][0])],
                 original['providers'][:-1] + [copy.deepcopy(original['providers'][0])]]
        changed = copy.deepcopy(original['providers'])
        changed[0]['output_bytes'] += 1
        cases.append(changed)
        for rows in cases:
            self.spec = {'providers': rows}
            with self.assertRaisesRegex(ValueError, 'CANONICAL16_COUNT'):
                self.get_pins()

    def fixture(self, root):
        pins = {}
        for index in range(16):
            rel = f'providers/input{index}.bin' if index < 14 else f'metadata{index}.json'
            path = root / rel
            path.parent.mkdir(exist_ok=True)
            raw = f'fixture{index}'.encode()
            path.write_bytes(raw)
            pins[rel] = R.identity(raw)
        return pins

    def checker(self):
        def checked(path, expected, cap, **kwargs):
            self.assertEqual(cap, 32 * R.MIB)
            self.assertEqual(kwargs, {'fixed_leaf': path.name})
            raw = path.read_bytes()
            if R.identity(raw) != expected:
                raise ValueError('MOCK_CANONICAL_HASH_DRIFT')
            return raw
        return types.SimpleNamespace(checked=mock.Mock(side_effect=checked))

    def test_exact_16_tiny_inputs_all_hashed_without_long_arrays(self):
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            root = Path(folder)
            pins = self.fixture(root)
            g = self.checker()
            R.check_inputs(g, root, pins)
            self.assertEqual(g.checked.call_count, 16)
            self.assertEqual([call.args[0] for call in g.checked.call_args_list], [root / rel for rel in pins])

    def test_missing_extra_and_symlink_input_entries_rejected_before_hashes(self):
        for mode in ('missing', 'extra', 'symlink'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(dir=HERE) as folder:
                root = Path(folder)
                pins = self.fixture(root)
                target = root / 'providers/input0.bin'
                if mode == 'missing':
                    target.unlink()
                elif mode == 'extra':
                    (root / 'extra.bin').write_bytes(b'fixture')
                else:
                    target.unlink()
                    target.symlink_to(root / 'providers/input1.bin')
                g = self.checker()
                with self.assertRaisesRegex(ValueError, 'CANONICAL16_ENTRIES'):
                    R.check_inputs(g, root, pins)
                g.checked.assert_not_called()

    def test_same_length_input_hash_drift_rejected(self):
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            root = Path(folder)
            pins = self.fixture(root)
            (root / 'providers/input0.bin').write_bytes(b'Fixture0')
            with self.assertRaisesRegex(ValueError, 'MOCK_CANONICAL_HASH_DRIFT'):
                R.check_inputs(self.checker(), root, pins)


class FullRun(unittest.TestCase):
    """The whole caller executes; every external module/action is a bounded mock."""
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        folder = self.stack.enter_context(tempfile.TemporaryDirectory(dir=HERE))
        self.root = Path(folder)
        self.work, self.repo, self.source = [self.root / name for name in ('work', 'repo', 'source')]
        self.prior, self.refs, self.inputs = [self.root / name for name in ('prior', 'references', 'inputs')]
        self.config = self.root / 'private.json'
        self.cfg = {
            'schema': 'PC01_CAPTURE_PRIVATE_BINDING_V1',
            'relink_source': str(self.root / 'relink_source'), 'relink_config': str(self.root / 'relink.json'),
            'inputs': str(self.inputs), 'reference_root': str(self.refs),
            'model_execution_receipt': str(self.root / 'models.json'),
            'comparison_source': str(self.root / 'comparison_source'), 'work': str(self.work),
            'review_evidence': [{'path': str(self.root / f'review{i}.txt'), **R.identity(f'review{i}'.encode())} for i in range(3)],
        }
        self.rc = {
            'repo': str(self.repo), 'source': str(self.source), 'binding_source': str(self.root / 'binding_source'),
            'work': str(self.prior), 'binding': {'path': str(self.root / 'binding.json'), 'identity': R.identity(b'binding')},
            'profile': {'path': str(self.root / 'profile.json'), 'identity': R.identity(b'{}')},
            'dependencies': str(self.root / 'catalog.json'), 'reuse_binding': str(self.root / 'reuse.json'),
        }
        self.catalog = {'files': {f'fixed{i}': {} for i in range(39)}, 'programs': {'g++': '/fixed/g++'},
                        'libraries': {'libc.so.6': '/fixed/lib/libc.so.6', 'libatomic.so.1': '/fixed/lib/libatomic.so.1'}}
        self.binding = {'system_programs': {'/usr/bin/g++': {'path': '/fixed/g++'},
                                           '/usr/bin/python3': {'path': str(Path(sys.executable).resolve(strict=True))}}}
        self.reuse = {'old_work_readonly': str(self.root / 'old_readonly')}
        self.buffers = {'source/mock.cpp': b'fixed mock source', 'cache/mock.a': b'fixed mock cache'}
        self.commands = {'compile': ['/fixed/g++', '-c', '/fixed/mock.cpp'],
                         'link': ['/fixed/g++', '/fixed/mock.o', '-o', str(self.prior / 'pc01')]}
        self.r = types.SimpleNamespace(
            CONFIG_PIN=(1, 'c' * 64), HELPER_PIN=(2, 'd' * 64), GATE_PIN=(3, 'e' * 64),
            CATALOG_PIN=(4, 'a' * 64), REUSE_PIN=(5, 'b' * 64), COMMAND_PIN=(6, 'f' * 64),
            commands=mock.Mock(return_value=self.commands),
            input_buffers=mock.Mock(side_effect=lambda *args: dict(self.buffers)), verify_copies=mock.Mock(),
            resource_gate=mock.Mock(return_value={'mem_available_bytes': 8 * 1024**3, 'disk_available_bytes': 3 * 1024**3}),
        )
        self.relink = {
            'schema': 1, 'status': 'COMPLETE_DRIVER_COMPILE_LINK_ONLY', 'scope': 'DRIVER_COMPILE_LINK_ONLY',
            'rtl_executed': False, 'pc01_executable_invoked': False, 'full_block_pass': False,
            'shared_seconds_cap': 180, 'cpu_affinity_count': 1,
            'binary': {'identity': copy.deepcopy(R.ELF_PIN)}, 'object': R.identity(b'object'),
            'stages': [good_stage(name, argv=argv, cwd=str(self.prior)) for name, argv in self.commands.items()],
            'compiler_catalog_identity': dict(zip(('bytes', 'sha256'), self.r.CATALOG_PIN)),
            'reuse_identity': dict(zip(('bytes', 'sha256'), self.r.REUSE_PIN)),
            'staged_files': {rel: R.identity(raw) for rel, raw in self.buffers.items()},
        }
        self.models = {
            'schema': 1, 'status': 'COMPLETE_SUPERVISED_TWO_REFERENCE_MODELS',
            'full_models_executed': True, 'rtl_executed': False, 'old_ram_resumed': False,
            'official_raw_numeric_pass': None, 'application_accuracy_pass': None, 'baseline_adopted': False,
            'stages': [good_stage(name) for name in ('compile', 'micro', 'full_models')],
            'outputs': {'outputs': copy.deepcopy(R.REFERENCE_PINS),
                        'result_identity': dict(zip(('bytes', 'sha256'), R.MODEL_RESULT_PIN))},
        }
        self.read_map = {
            Path(R.__file__).resolve(): (HERE / 'run_capture.py').read_bytes(),
            self.config: json.dumps(self.cfg).encode(), Path(self.cfg['relink_config']): json.dumps(self.rc).encode(),
            Path(self.rc['dependencies']): json.dumps(self.catalog).encode(),
            Path(self.rc['reuse_binding']): json.dumps(self.reuse).encode(),
            self.source / 'RELINK_CONTRACT.json': b'{"mock_contract": true}',
            self.prior / 'EXECUTION_RESULT.json': json.dumps(self.relink).encode(),
            Path(self.cfg['model_execution_receipt']): json.dumps(self.models).encode(),
            self.refs / 'RESULT.json': b'{"mock_reference_result": true}',
        }
        self.read_map.update({Path(row['path']): f'review{i}'.encode() for i, row in enumerate(self.cfg['review_evidence'])})
        self.reader = self.stack.enter_context(mock.patch.object(R, 'read', side_effect=lambda path, expected: self.read_map.get(path, b'fixed helper mock source')))
        self.r.read = mock.Mock(side_effect=lambda path, expected: self.read_map[path])
        def checked(path, expected, *args, **kwargs):
            if path == Path(self.rc['binding']['path']):
                return b'binding'
            if path == Path(self.rc['profile']['path']):
                return b'{}'
            return b'bounded mock artifact'
        self.g = types.SimpleNamespace(checked=mock.Mock(side_effect=checked), clean=Path,
                                       binding=mock.Mock(return_value=self.binding), decode=json.loads)
        self.l = types.SimpleNamespace(validate=mock.Mock())
        self.o = object()
        self.d = types.SimpleNamespace(verify=mock.Mock(return_value={'dependencies': 'fixed'}),
                                       check_binary=mock.Mock(return_value=copy.deepcopy(self.relink['binary'])))
        self.c = types.SimpleNamespace(compare=mock.Mock(return_value=observation()))
        self.calls, self.saved, self.after_phase = [], [], None
        self.phase_failure, self.save_failure, self.restore_failure = None, None, None
        self.support = types.SimpleNamespace(fresh_directory=mock.Mock(side_effect=lambda path: path.mkdir()))
        def phase(*args):
            self.calls.append(args)
            stage = good_stage(argv=args[3], cwd=str(args[4]))
            args[10].update(stage['diagnostics'])
            if self.phase_failure is not None:
                raise self.phase_failure
            if self.after_phase is not None:
                self.after_phase()
            return stage['record'], '{}', stage['usage']
        self.s = types.SimpleNamespace(fixed_support=mock.Mock(return_value=(self.support, 'mock base', {})),
                                       run_phase=mock.Mock(side_effect=phase))
        def save(work, result, failure):
            self.saved.append((work, copy.deepcopy(result), failure))
            if self.save_failure is not None:
                raise self.save_failure
            return failure
        def restore(old, failure):
            # Model the already-qualified helper's failure-preserving interface.
            return failure if failure is not None else self.restore_failure
        self.h = types.SimpleNamespace(
            PINS={name: (1, '0' * 64) for name in ('bootstrap.py', 'binding_observer.py', 'local_mount_profile.py', 'ci_support_v3.py')},
            save_preserving_failure=mock.Mock(side_effect=save), restore_preserving_failure=mock.Mock(side_effect=restore),
        )
        modules = {'capture_bootstrap': self.g, 'capture_observer': self.o, 'capture_mount': self.l}
        self.h.module = mock.Mock(side_effect=lambda path, expected, name: modules[name])
        self.r.module = mock.Mock(side_effect=lambda path, expected, name: {'fixed_evidence_helpers': self.h, 'capture_dependencies': self.d}[name])
        self.stack.enter_context(mock.patch.object(R, 'module', side_effect=lambda path, expected, name:
            {'fixed_relink_readonly_helpers': self.r, 'capture_three_reference_comparison': self.c}[name]))
        self.stack.enter_context(mock.patch.object(R, 'supervisor_projection', return_value=(self.s, {'inverse_exact': True})))
        self.pins = {f'mock/input{i}.bin': R.identity(f'input{i}'.encode()) for i in range(16)}
        self.inputs_mock = self.stack.enter_context(mock.patch.object(R, 'input_pins', return_value=self.pins))
        self.check_inputs = self.stack.enter_context(mock.patch.object(R, 'check_inputs'))
        self.clock = self.stack.enter_context(mock.patch.object(R.time, 'monotonic', return_value=1.0))
        self.timer_state = self.stack.enter_context(mock.patch.object(R.signal, 'getitimer', return_value=(0.0, 0.0)))
        self.mask = self.stack.enter_context(mock.patch.object(R.signal, 'pthread_sigmask', return_value=set()))
        self.stack.enter_context(mock.patch.object(R.signal, 'getsignal', return_value='old_handler'))
        self.sig = self.stack.enter_context(mock.patch.object(R.signal, 'signal'))
        self.timer = self.stack.enter_context(mock.patch.object(R.signal, 'setitimer'))
        self.hard_limit = self.stack.enter_context(mock.patch.object(R.resource, 'getrlimit', return_value=(R.resource.RLIM_INFINITY, R.resource.RLIM_INFINITY)))
        self.limits = self.stack.enter_context(mock.patch.object(R.resource, 'setrlimit'))
        self.allowed = self.stack.enter_context(mock.patch.object(R.os, 'sched_getaffinity', return_value={3, 7}))
        self.affinity = self.stack.enter_context(mock.patch.object(R.os, 'sched_setaffinity'))

    def go(self):
        return R.run(self.config, True, started=1.0, source_pin=PINS['run_capture.py'])

    def test_complete_full_caller_mock_positive_control(self):
        result = self.go()
        self.assertEqual(result['status'], 'COMPLETE_SUPERVISED_PC01_TYPED_MATCH_AND_MATH_DIAGNOSTICS')
        self.assertEqual(result['scope'], 'FRESH_PC0_THROUGH_ACK1_ONLY')
        self.assertEqual(result['fresh_reset_native_runs'], 1)
        self.assertTrue(result['typed_recipe_bit_exact_to_rtl'])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][3], [str(self.prior / 'pc01'), str(self.inputs), str(self.work / 'capture')])
        self.assertEqual(self.calls[0][6], R.environment(self.catalog, self.work))
        self.assertEqual(self.calls[0][8], 10621.0)
        self.assertEqual(self.calls[0][9]['deadline'], 10621.0)
        self.assertEqual(result['shared_seconds_cap'], 10620)
        self.assertEqual(result['combined_authorized_ceiling_seconds'], 10800)
        self.assertEqual(result['global_main_cycle_cap'], 8000000)
        self.assertEqual(result['fixed_mac_lanes'], 4096)
        self.assertEqual(result['pc1_useful_macs'], 301989888)
        for field in ('full_block_pass', 'baseline_adopted', 'old_process_resumed', 'offline_n0_loaded', 'inter_step_wait_in_native_wall'):
            self.assertIs(result[field], False)
        for field in ('official_raw_numeric_pass', 'application_accuracy_pass', 'whole_block_utilization'):
            self.assertIsNone(result[field])
        self.affinity.assert_called_once_with(0, {3})
        self.assertEqual(len(self.limits.call_args_list), 3)
        self.assertEqual(self.saved[0][0], self.work)
        self.assertEqual(self.saved[0][1], result)
        self.assertIsNone(self.saved[0][2])
        self.h.restore_preserving_failure.assert_called_once_with('old_handler', None)
        self.c.compare.assert_called_once_with(self.work / 'capture', self.refs, self.refs / 'RESULT.json', shared_stop=10501.0)
        self.assertEqual(self.r.resource_gate.call_args_list, [mock.call(self.root), mock.call(self.work), mock.call(self.work)])
        self.assertEqual(self.check_inputs.call_count, 4)
        self.assertEqual(self.r.verify_copies.call_count, 4)

    def test_every_fixed_helper_and_receipt_is_rechecked(self):
        self.go()
        paths = [call.args[0] for call in self.reader.call_args_list]
        for leaf in ('run_capture.py', 'run_relink.py', 'dependency_gate.py', 'compare.py',
                     'run_reference.py', 'bootstrap.py', 'binding_observer.py', 'local_mount_profile.py', 'ci_support_v3.py'):
            self.assertGreaterEqual(sum(path.name == leaf for path in paths), 4)
        for path in (self.prior / 'EXECUTION_RESULT.json', Path(self.cfg['model_execution_receipt']), self.refs / 'RESULT.json'):
            self.assertEqual(paths.count(path), 5)
        self.assertEqual(self.g.checked.call_count, 26)

    def test_unknown_failure_code_remains_null_and_original_is_raised(self):
        first = RuntimeError('/private/path must never become a public failure code')
        self.phase_failure = first
        with self.assertRaises(RuntimeError) as caught:
            self.go()
        self.assertIs(caught.exception, first)
        self.assertIsNone(self.saved[0][1]['failure_code'])
        self.assertEqual(self.saved[0][1]['status'], 'INCOMPLETE')
        self.assertEqual(len(self.saved[0][1]['stages']), 1)
        self.c.compare.assert_not_called()

    def test_save_and_restore_faults_do_not_replace_original_phase_failure(self):
        first = RuntimeError('first phase failure')
        self.phase_failure = first
        self.save_failure, self.restore_failure = OSError('second save failure'), OSError('third restore failure')
        with self.assertRaises(RuntimeError) as caught:
            self.go()
        self.assertIs(caught.exception, first)
        self.h.restore_preserving_failure.assert_called_once_with('old_handler', first)
        self.c.compare.assert_not_called()

    def test_save_fault_after_success_is_passed_to_restore_and_raised(self):
        first = OSError('first save failure')
        self.save_failure, self.restore_failure = first, OSError('second restore failure')
        with self.assertRaises(OSError) as caught:
            self.go()
        self.assertIs(caught.exception, first)
        self.h.restore_preserving_failure.assert_called_once_with('old_handler', first)

    def test_restore_fault_after_success_is_raised(self):
        first = OSError('restore failure')
        self.restore_failure = first
        with self.assertRaises(OSError) as caught:
            self.go()
        self.assertIs(caught.exception, first)

    def test_early_read_failure_and_both_restore_faults_preserve_first(self):
        first = RuntimeError('first source failure')
        self.reader.side_effect = first
        self.timer.side_effect = [None, OSError('second reset failure')]
        self.sig.side_effect = [None, OSError('third handler failure')]
        with self.assertRaises(RuntimeError) as caught:
            self.go()
        self.assertIs(caught.exception, first)
        self.assertEqual(self.timer.call_args.args, (signal.ITIMER_REAL, 0))
        self.assertEqual(self.sig.call_args.args, (signal.SIGALRM, 'old_handler'))
        self.assertEqual(self.calls, [])

    def test_actual_typed_mismatch_is_saved_with_all_diagnostics_and_safe_code(self):
        self.c.compare.return_value['typed_reference']['mismatch_values'] = 17
        with self.assertRaisesRegex(ValueError, 'TYPED_REFERENCE_MISMATCH'):
            self.go()
        saved = self.saved[0][1]
        self.assertEqual(saved['comparison'], self.c.compare.return_value)
        self.assertEqual(saved['failure_code'], 'TYPED_REFERENCE_MISMATCH')
        self.assertEqual(saved['status'], 'INCOMPLETE')
        self.assertFalse(saved['full_block_pass'])

    def test_postphase_source_drift_stops_before_comparison(self):
        self.after_phase = lambda: self.read_map.update({Path(R.__file__).resolve(): b'changed'})
        with self.assertRaisesRegex(ValueError, 'CALLER_OR_CONFIG_CHANGED'):
            self.go()
        self.assertEqual(len(self.calls), 1)
        self.c.compare.assert_not_called()

    def test_postphase_dependency_drift_stops_before_comparison(self):
        self.d.verify.side_effect = [{'dependencies': 'fixed'}] * 3 + [{'dependencies': 'changed'}]
        with self.assertRaisesRegex(ValueError, 'DEPENDENCY_CHANGED'):
            self.go()
        self.assertEqual(len(self.calls), 1)
        self.c.compare.assert_not_called()

    def test_postphase_input_hash_failure_stops_before_comparison(self):
        self.check_inputs.side_effect = [None, None, ValueError('mock input hash drift')]
        with self.assertRaisesRegex(ValueError, 'mock input hash drift'):
            self.go()
        self.assertEqual(len(self.calls), 1)
        self.c.compare.assert_not_called()

    def test_existing_work_is_rejected_without_phase(self):
        self.work.mkdir()
        with self.assertRaisesRegex(ValueError, 'FRESH_DISJOINT_WORK'):
            self.go()
        self.assertEqual(self.calls, [])

    def test_final_resource_admission_failure_prevents_phase(self):
        first = ValueError('mock admission failure')
        self.r.resource_gate.side_effect = [{}, {}, first]
        with self.assertRaises(ValueError) as caught:
            self.go()
        self.assertIs(caught.exception, first)
        self.assertEqual(self.calls, [])
        self.c.compare.assert_not_called()

    def test_inherited_hard_limit_rejected_before_source_or_phase(self):
        self.hard_limit.return_value = (1, 1)
        with self.assertRaisesRegex(ValueError, 'INHERITED_HARD_LIMIT'):
            self.go()
        self.limits.assert_not_called()
        self.reader.assert_not_called()
        self.assertEqual(self.calls, [])

    def test_timer_ownership_rejected_before_setting_timer(self):
        self.timer_state.return_value = (1.0, 0.0)
        with self.assertRaisesRegex(ValueError, 'TIMER_OWNERSHIP'):
            self.go()
        self.timer.assert_not_called()
        self.sig.assert_not_called()
        self.reader.assert_not_called()


class SourcesAndEntry(unittest.TestCase):
    def test_fixed_caller_pin_matches_loaded_source(self):
        self.assertEqual(E.CALLER_PIN, PINS['run_capture.py'])

    def test_runtime_and_entry_return_exact_checked_buffer(self):
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            path = Path(folder) / 'source.py'
            raw = b'value = 73\n'
            path.write_bytes(raw)
            self.assertEqual(R.read(path, pin(raw)), raw)
            self.assertEqual(E.checked(path, pin(raw)), raw)
            self.assertEqual(R.module(path, pin(raw), 'checked_fixture').value, 73)

    def test_runtime_module_uses_same_checked_bytes_after_file_changes(self):
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            path = Path(folder) / 'source.py'
            raw = b'value = 73\n'
            path.write_bytes(raw)
            original = builtins.compile
            seen = []
            def compile_buffer(data, *args, **kwargs):
                seen.append(data)
                path.write_bytes(b'value = 99\n')
                return original(data, *args, **kwargs)
            with mock.patch.object(builtins, 'compile', side_effect=compile_buffer):
                value = R.module(path, pin(raw), 'same_buffer_fixture')
            self.assertEqual(value.value, 73)
            self.assertEqual(seen, [raw])

    def test_runtime_module_short_long_and_same_length_drift_before_compile(self):
        raw = b'value = 73\n'
        for changed in (b'x', raw + b'\n', b'value = 74\n'):
            with self.subTest(raw=changed), tempfile.TemporaryDirectory(dir=HERE) as folder:
                path = Path(folder) / 'source.py'
                path.write_bytes(changed)
                with mock.patch.object(builtins, 'compile', side_effect=AssertionError('compiled unpinned module')) as compiler:
                    with self.assertRaisesRegex(ValueError, 'SOURCE_(SIZE|HASH_OR_DRIFT)'):
                        R.module(path, pin(raw), 'rejected')
                    compiler.assert_not_called()

    def test_runtime_and_entry_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            root = Path(folder)
            raw = b'value = 73\n'
            (root / 'source.py').write_bytes(raw)
            (root / 'alias.py').symlink_to(root / 'source.py')
            for reader, code in ((R.read, 'SOURCE_CANONICAL'), (E.checked, 'ENTRY_CANONICAL')):
                with self.assertRaisesRegex(ValueError, code):
                    reader(root / 'alias.py', pin(raw))

    def test_runtime_and_entry_descriptor_drift_is_rejected(self):
        for reader, code in ((R.read, 'SOURCE_HASH_OR_DRIFT'), (E.checked, 'ENTRY_HASH_OR_DRIFT')):
            with self.subTest(code=code), tempfile.TemporaryDirectory(dir=HERE) as folder:
                path = Path(folder) / 'source.py'
                raw = b'value = 73\n'
                path.write_bytes(raw)
                original = os.read
                changed = []
                def read(fd, count):
                    value = original(fd, count)
                    if value and not changed:
                        path.write_bytes(raw + b'\n')
                        changed.append(True)
                    return value
                with mock.patch.object(os, 'read', side_effect=read):
                    with self.assertRaisesRegex(ValueError, code):
                        reader(path, pin(raw))

    def test_entry_short_long_and_same_length_hash_fail_before_compile(self):
        raw = (HERE / 'run_capture.py').read_bytes()
        for changed in (raw[:-1], raw + b'\n', bytes([raw[0] ^ 1]) + raw[1:]):
            with self.subTest(bytes=len(changed)), tempfile.TemporaryDirectory(dir=HERE) as folder:
                root = Path(folder)
                (root / 'run_capture.py').write_bytes(changed)
                with mock.patch.object(E, '__file__', str(root / 'launch.py')), \
                     mock.patch.object(E.time, 'monotonic', return_value=1.0), \
                     mock.patch.object(builtins, 'compile', side_effect=AssertionError('compiled changed entry')) as compiler:
                    with self.assertRaisesRegex(ValueError, 'ENTRY_(SIZE|HASH_OR_DRIFT)'):
                        E.main([], started=1.0)
                    compiler.assert_not_called()

    def test_entry_uses_frozen_buffer_and_without_execute_flag_stops_before_native(self):
        raw = (HERE / 'run_capture.py').read_bytes()
        original = builtins.compile
        seen = []
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            root = Path(folder)
            path = root / 'run_capture.py'
            path.write_bytes(raw)
            def compile_buffer(data, *args, **kwargs):
                seen.append(data)
                path.write_bytes(b'raise RuntimeError("MUST_NOT_COMPILE")\n')
                return original(data, *args, **kwargs)
            with mock.patch.object(E, '__file__', str(root / 'launch.py')), \
                 mock.patch.object(E.time, 'monotonic', return_value=1.0), \
                 mock.patch.object(builtins, 'compile', side_effect=compile_buffer):
                with self.assertRaisesRegex(ValueError, 'EXPLICIT_CAPTURE_AND_ISOLATION_REQUIRED'):
                    E.main(['--private-config', '/unused'], started=1.0)
        self.assertEqual(seen, [raw])

    def test_entry_t0_requires_float_nonfuture_and_younger_than_30_seconds(self):
        for origin in (None, 0, True, -30.0, 2.0):
            with self.subTest(origin=origin), mock.patch.object(E.time, 'monotonic', return_value=1.0), \
                 mock.patch.object(E, 'STARTED', -30.0), mock.patch.object(builtins, 'compile') as compiler:
                with self.assertRaisesRegex(ValueError, 'ENTRY_T0'):
                    E.main([], started=origin)
                compiler.assert_not_called()

    def test_entry_and_caller_require_all_three_isolation_flags(self):
        for disabled in ('isolated', 'no_site', 'dont_write_bytecode'):
            flags = {name: True for name in ('isolated', 'no_site', 'dont_write_bytecode')}
            flags[disabled] = False
            with self.subTest(disabled=disabled), mock.patch.object(sys, 'flags', types.SimpleNamespace(**flags)):
                with self.assertRaisesRegex(ValueError, 'ENTRY_ISOLATION'):
                    E.main([], started=1.0)
                with self.assertRaisesRegex(ValueError, 'EXPLICIT_CAPTURE_AND_ISOLATION_REQUIRED'):
                    R.run(Path('/unused'), True, started=1.0)

    def test_caller_explicit_execute_and_entry_t0_required(self):
        with self.assertRaisesRegex(ValueError, 'EXPLICIT_CAPTURE_AND_ISOLATION_REQUIRED'):
            R.run(Path('/unused'), False)
        for origin in (None, 0, True, -30.0, 2.0):
            with self.subTest(origin=origin), mock.patch.object(R.time, 'monotonic', return_value=1.0):
                with self.assertRaisesRegex(ValueError, 'ENTRY_T0_REQUIRED'):
                    R.run(Path('/unused'), True, started=origin)

    def test_cli_exact_arguments_forward_original_t0_and_source_pin(self):
        value = {'status': 'MOCK_ONLY', 'stages': [None]}
        with mock.patch.object(R, 'run', return_value=value) as runner, \
             mock.patch.object(R.sys, 'addaudithook') as hook, contextlib.redirect_stdout(io.StringIO()) as output:
            R.main(['--private-config', '/fixed/private.json', '--execute-reviewed-capture'], started=1.0, source_pin=PINS['run_capture.py'])
        runner.assert_called_once_with(Path('/fixed/private.json'), True, started=1.0, source_pin=PINS['run_capture.py'])
        self.assertEqual(json.loads(output.getvalue()), {'status': 'MOCK_ONLY', 'phases': 1, 'full_block_pass': False})
        hook.assert_called_once()
        with self.assertRaisesRegex(RuntimeError, 'NETWORK_FORBIDDEN'):
            hook.call_args.args[0]('socket.connect', ())

    def test_cli_rejects_abbreviated_missing_and_extra_arguments_before_run(self):
        for argv in ([], ['--private-config', '/fixed', '--execute-reviewed-capt'],
                     ['--private-conf', '/fixed'], ['--private-config', '/fixed', '--other']):
            with self.subTest(argv=argv), mock.patch.object(R, 'run') as runner, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    R.main(argv, started=1.0, source_pin=PINS['run_capture.py'])
                runner.assert_not_called()

    def test_fixed_environment_excludes_every_parent_override(self):
        catalog = {'libraries': {'libc.so.6': '/fixed/lib/libc.so.6', 'libatomic.so.1': '/fixed/lib/libatomic.so.1'}}
        poison = {'PATH': '/evil', 'LD_PRELOAD': '/evil.so', 'PYTHONPATH': '/evil', 'CPATH': '/evil',
                  'HOME': '/evil', 'OMP_NUM_THREADS': '99', 'OPENBLAS_NUM_THREADS': '99', 'MKL_NUM_THREADS': '99'}
        with mock.patch.dict(os.environ, poison):
            actual = R.environment(catalog, Path('/fixed/work'))
        self.assertEqual(actual, {'PATH': '/fixed/work/empty-path', 'LD_LIBRARY_PATH': '/fixed/lib',
                                 'HOME': '/fixed/work/home', 'TMPDIR': '/fixed/work/tmp',
                                 'LC_ALL': 'C', 'LANG': 'C', 'TZ': 'UTC',
                                 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'})

    def test_library_environment_requires_one_fixed_directory(self):
        for libraries in ({}, {'one.so': '/one/one.so', 'two.so': '/two/two.so'}):
            with self.assertRaisesRegex(ValueError, 'FIXED_LIBRARY_DIRECTORY'):
                R.environment({'libraries': libraries}, Path('/fixed/work'))


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromModule(types.SimpleNamespace(**globals()))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.testsRun > 0 and result.wasSuccessful() else 1)
