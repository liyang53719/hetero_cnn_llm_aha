"""Pinned, low-resource pure/mock tests. No child, compiler, RTL, or network."""
import argparse
import ast
import builtins
import copy
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent.parent / 'public' / 'supervision.py'
PIN = (4394, '0147d6132bdfa6dccecce28eb6bb31f27ec3876d0345cad4d9e4e70002d106f2')
PARSER = argparse.ArgumentParser(allow_abbrev=False)
PARSER.add_argument('--source', type=Path, default=SOURCE)
PARSER.add_argument('--mode', choices=('normal', 'optimized', 'relocated', 'relocated_optimized'), default='normal')
ARGS = PARSER.parse_args()
SOURCE = ARGS.source.resolve(strict=True)


def audit(event, args):
    if event.startswith(('subprocess.', 'socket.')) or event in (
        'os.system', 'os.fork', 'os.forkpty', 'os.exec', 'os.posix_spawn',
        'ctypes.dlopen', 'urllib.Request'):
        raise RuntimeError('COLD_NATIVE_NETWORK_FORBIDDEN')
    if event == 'import' and str(args[0]).split('.')[0] in ('numpy', 'scipy', 'torch', 'ctypes'):
        raise RuntimeError('COLD_NUMERICAL_IMPORT_FORBIDDEN')


sys.addaudithook(audit)


def pin(raw):
    return len(raw), hashlib.sha256(raw).hexdigest()


def load(path=SOURCE):
    raw = path.read_bytes()
    if pin(raw) != PIN:
        raise RuntimeError('COLD_SOURCE_IDENTITY')
    module = types.ModuleType('fixed_owner_supervision')
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec', dont_inherit=True), module.__dict__)
    return module


R = load()


def good_record():
    return {'exit_code': 0, 'status': 'PASS', 'cleanup_confirmed': True,
            'timed_out': False, 'reaped': True, 'parent_exception': None,
            'group_state': 'absent', 'exit_observed_while_unreaped': {'code': 1, 'status': 0}}


def good_usage():
    return {'maxrss_kib_cumulative_parent_children': 4096}


class Loader(unittest.TestCase):
    def test_exact_pinned_source_and_no_top_level_execution(self):
        raw = SOURCE.read_bytes()
        self.assertEqual(pin(raw), PIN)
        tree = ast.parse(raw)
        self.assertFalse(any(isinstance(n, ast.Assert) for n in ast.walk(tree)))
        for n in tree.body:
            if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call):
                self.fail('Top-level call is not allowed in the source slice')

    def test_hash_and_size_reject_before_compile(self):
        raw = SOURCE.read_bytes()
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            path = Path(folder) / 'source.py'
            for bad in (raw[:-1], raw + b'\n', bytes([raw[0] ^ 1]) + raw[1:]):
                with self.subTest(size=len(bad)):
                    path.write_bytes(bad)
                    with mock.patch.object(builtins, 'compile', side_effect=AssertionError('compiled drift')) as compiler:
                        with self.assertRaisesRegex(RuntimeError, 'COLD_SOURCE_IDENTITY'):
                            load(path)
                        compiler.assert_not_called()

    def test_loader_compiles_same_verified_buffer(self):
        raw = SOURCE.read_bytes()
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            path = Path(folder) / 'source.py'
            path.write_bytes(raw)
            compiler = builtins.compile
            seen = []
            def compile_buffer(buf, *args, **kwargs):
                seen.append(buf)
                path.write_bytes(b'raise RuntimeError("changed file")\n')
                return compiler(buf, *args, **kwargs)
            with mock.patch.object(builtins, 'compile', side_effect=compile_buffer):
                loaded = load(path)
            self.assertEqual(loaded.SHARED_SECONDS, 1320)
            self.assertEqual(seen, [raw])

    def test_audit_blocks_native_network_and_numerical_imports(self):
        for event in ('subprocess.Popen', 'socket.connect', 'os.system', 'os.fork',
                      'os.forkpty', 'os.exec', 'os.posix_spawn', 'ctypes.dlopen', 'urllib.Request'):
            with self.subTest(event=event), self.assertRaisesRegex(RuntimeError, 'COLD_NATIVE_NETWORK_FORBIDDEN'):
                sys.audit(event)
        for name in ('numpy', 'scipy', 'torch', 'ctypes'):
            with self.subTest(name=name), self.assertRaisesRegex(RuntimeError, 'COLD_NUMERICAL_IMPORT_FORBIDDEN'):
                audit('import', (name,))


class Limits(unittest.TestCase):
    def test_fixed_three_phase_limits_and_tail(self):
        self.assertEqual((R.SHARED_SECONDS, R.TAIL_SECONDS), (1320, 60))
        for name, total, fsize, tree, log in (
            ('generate', 360, 128, 512, 4), ('build', 600, 512, 2048, 4), ('run', 300, 16, 2048, 1)):
            with self.subTest(phase=name):
                self.assertEqual(R.phase_limits(name), {
                    'total_seconds': total, 'work_seconds': total - 15, 'cpu_seconds': total - 15,
                    'as_bytes': 6 * 1024**3, 'fsize_bytes': fsize * R.MIB,
                    'tree_bytes': tree * R.MIB, 'log_bytes': log * R.MIB,
                    'sample_rows': total + 2, 'file_count': 32768, 'entry_count': 65536})

    def test_phase_limits_are_new_values_and_unknown_phase_rejected(self):
        first = R.phase_limits('generate')
        first['total_seconds'] = 999
        self.assertEqual(R.phase_limits('generate')['total_seconds'], 360)
        with self.assertRaises(KeyError):
            R.phase_limits('fourth')

    def test_full_window_exact_boundary_and_insufficient_rejected(self):
        for name in ('generate', 'build', 'run'):
            edge = 1320 - 60 - R.phase_limits(name)['total_seconds']
            with self.subTest(phase=name), mock.patch.object(R.time, 'monotonic', return_value=float(edge)):
                R.complete_window(1320.0, name)
            with self.subTest(phase=name), mock.patch.object(R.time, 'monotonic', return_value=edge + 0.0001):
                with self.assertRaisesRegex(ValueError, 'INCOMPLETE_PHASE_WINDOW'):
                    R.complete_window(1320.0, name)

    def test_successful_natural_exit_and_exact_rss_boundary(self):
        R.natural_success(good_record(), good_usage())
        R.natural_success(good_record(), {'maxrss_kib_cumulative_parent_children': 6 * 1024**2})

    def test_nonnatural_exits_rejected(self):
        changes = [('exit_code', x) for x in (1, False, True, '0', None)] + [
            ('status', 'FAIL'), ('cleanup_confirmed', False), ('timed_out', True), ('reaped', False),
            ('parent_exception', 'error'), ('group_state', 'live'),
            ('exit_observed_while_unreaped', {'code': 2, 'status': 0}),
            ('exit_observed_while_unreaped', {'code': 1, 'status': 9})]
        for key, value in changes:
            with self.subTest(key=key, value=value):
                record = good_record(); record[key] = value
                with self.assertRaisesRegex(ValueError, 'NATURAL_EXIT_OR_CLEANUP'):
                    R.natural_success(record, good_usage())

    def test_invalid_rss_rejected(self):
        for value in (-1, True, 6 * 1024**2 + 1, 4096.0, '4096', None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'CUMULATIVE_RSS_6G'):
                R.natural_success(good_record(), {'maxrss_kib_cumulative_parent_children': value})


class Sequence(unittest.TestCase):
    def setUp(self):
        self.work = Path('/fixed/work')
        self.commands = {n: ['/fixed/' + n, '--fixed'] for n in ('generate', 'build', 'run')}
        self.env = {'PATH': '/fixed/empty', 'OMP_NUM_THREADS': '1'}
        self.owner = {'deadline': 1320.0, 'handler': object()}
        self.result = {'stages': [], 'full_block_pass': False}
        self.calls = []
        self.order = []
        self.failures = {}
        self.record = good_record()
        self.usage = good_usage()
        self.support = object()
        self.preflight = mock.Mock(side_effect=lambda: self.order.append('preflight'))
        self.admit = mock.Mock(side_effect=lambda: self.order.append('admit') or {'mem': 8 * 1024**3})
        self.after = mock.Mock(side_effect=lambda name, raw, stage: self.order.append('after:' + name))
        def phase(*args):
            name = args[2].removeprefix('owner_local_')
            self.order.append('phase:' + name)
            self.calls.append(args)
            args[10]['synthetic_only'] = True
            if name in self.failures:
                raise self.failures[name]
            return copy.deepcopy(self.record), 'synthetic record bytes', copy.deepcopy(self.usage)
        self.s = types.SimpleNamespace(run_phase=phase)
        clock = mock.patch.object(R.time, 'monotonic', return_value=0.0)
        self.clock = clock.start(); self.addCleanup(clock.stop)
        logs = mock.patch.object(R, 'observe_log', return_value={'synthetic_log_identity': True})
        self.logs = logs.start(); self.addCleanup(logs.stop)

    def go(self):
        return R.sequence(self.s, self.support, 'base', self.work, self.commands, self.env,
                          1320.0, self.owner, self.preflight, self.after, self.result, self.admit)

    def test_only_three_phases_order_and_persisted_stage_receipts(self):
        self.assertIs(self.go(), self.result)
        self.assertEqual([x['name'] for x in self.result['stages']], ['generate', 'build', 'run'])
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(self.after.call_count, 3)
        self.assertEqual(self.preflight.call_count, 9)
        self.assertEqual(self.admit.call_count, 3)
        self.assertFalse(self.result['full_block_pass'])
        for stage in self.result['stages']:
            self.assertEqual(stage['diagnostics'], {'synthetic_only': True})
            self.assertEqual(stage['log_observation'], {'synthetic_log_identity': True})
            self.assertEqual(stage['secondary_failure_types'], [])

    def test_exact_owner_stop_environment_commands_and_limits_forwarded(self):
        self.go()
        for args, name, stage in zip(self.calls, ('generate', 'build', 'run'), self.result['stages']):
            self.assertEqual(args[:3], (self.support, 'base', 'owner_local_' + name))
            self.assertIs(args[3], self.commands[name])
            self.assertEqual(args[4:6], (self.work, self.work / 'phases' / name))
            self.assertIs(args[6], self.env)
            self.assertEqual(args[7], R.phase_limits(name))
            self.assertEqual(args[8], 1320.0)
            self.assertIs(args[9], self.owner)
            self.assertIs(args[10], stage['diagnostics'])

    def test_each_phase_preflight_admission_then_native_then_after_phase(self):
        self.go()
        self.assertEqual(self.order, [item for name in ('generate', 'build', 'run') for item in
                                     ('preflight', 'admit', 'phase:' + name, 'preflight', 'after:' + name, 'preflight')])
        self.assertEqual([a['phase'] for a in self.result['admissions']], ['generate', 'build', 'run'])

    def test_missing_or_extra_command_rejected_before_work(self):
        for commands in ({'generate': []}, {**self.commands, 'extra': []}):
            self.commands = commands
            with self.assertRaisesRegex(ValueError, 'EXACT_THREE_COMMANDS'):
                self.go()
        self.preflight.assert_not_called(); self.admit.assert_not_called()
        self.assertEqual(self.calls, [])

    def test_first_window_failure_before_preflight(self):
        self.clock.return_value = 900.0001
        with self.assertRaisesRegex(ValueError, 'INCOMPLETE_PHASE_WINDOW'):
            self.go()
        self.preflight.assert_not_called(); self.admit.assert_not_called()
        self.assertEqual(self.calls, [])

    def test_second_window_failure_after_admission_before_native(self):
        self.clock.side_effect = [0.0, 900.0001]
        with self.assertRaisesRegex(ValueError, 'INCOMPLETE_PHASE_WINDOW'):
            self.go()
        self.preflight.assert_called_once_with(); self.admit.assert_called_once_with()
        self.assertEqual(self.calls, [])

    def test_build_and_run_full_windows_each_stop_before_late_native(self):
        for name, clock_values, expected_count in (
            ('build', [0, 0, 0, 0, 660.0001], 1),
            ('run', [0, 0, 0, 0, 0, 0, 0, 0, 960.0001], 2)):
            with self.subTest(phase=name):
                self.setUp()
                self.clock.side_effect = clock_values
                with self.assertRaisesRegex(ValueError, 'INCOMPLETE_PHASE_WINDOW'):
                    self.go()
                self.assertEqual(len(self.calls), expected_count)
                self.assertEqual(len(self.result['stages']), expected_count)

    def test_admission_failure_prevents_any_native(self):
        first = ValueError('synthetic admission')
        self.admit.side_effect = first
        with self.assertRaises(ValueError) as caught:
            self.go()
        self.assertIs(caught.exception, first)
        self.assertEqual(self.calls, []); self.after.assert_not_called()

    def test_preflight_failure_prevents_any_native(self):
        first = RuntimeError('synthetic preflight')
        self.preflight.side_effect = first
        with self.assertRaises(RuntimeError) as caught:
            self.go()
        self.assertIs(caught.exception, first)
        self.assertEqual(self.calls, []); self.admit.assert_not_called()

    def test_each_phase_exception_stops_successors_and_keeps_diagnostics(self):
        for name, count in (('generate', 1), ('build', 2), ('run', 3)):
            with self.subTest(phase=name):
                self.setUp()
                first = RuntimeError('native synthetic ' + name)
                self.failures[name] = first
                with self.assertRaises(RuntimeError) as caught:
                    self.go()
                self.assertIs(caught.exception, first)
                self.assertEqual(len(self.calls), count)
                self.assertEqual(len(self.result['stages']), count)
                stage = self.result['stages'][-1]
                self.assertIsNone(stage['record']); self.assertIsNone(stage['usage'])
                self.assertEqual(stage['diagnostics'], {'synthetic_only': True})

    def test_invalid_record_or_rss_prevents_after_phase_and_next_phase(self):
        for attr, key, value, code in (
            ('record', 'exit_code', 2, 'NATURAL_EXIT_OR_CLEANUP'),
            ('record', 'cleanup_confirmed', False, 'NATURAL_EXIT_OR_CLEANUP'),
            ('usage', 'maxrss_kib_cumulative_parent_children', 6 * 1024**2 + 1, 'CUMULATIVE_RSS_6G')):
            with self.subTest(key=key):
                self.setUp(); getattr(self, attr)[key] = value
                with self.assertRaisesRegex(ValueError, code):
                    self.go()
                self.assertEqual(len(self.calls), 1); self.after.assert_not_called()
                self.assertEqual(len(self.result['stages']), 1)

    def test_postphase_preflight_failure_stops_before_callback(self):
        first = RuntimeError('synthetic postphase drift')
        self.preflight.side_effect = [None, first]
        with self.assertRaises(RuntimeError) as caught:
            self.go()
        self.assertIs(caught.exception, first)
        self.assertEqual(len(self.calls), 1); self.after.assert_not_called()
        self.assertEqual(len(self.result['stages']), 1)

    def test_after_phase_failure_preserved_and_blocks_next_phase(self):
        first = RuntimeError('synthetic after phase')
        self.after.side_effect = first
        with self.assertRaises(RuntimeError) as caught:
            self.go()
        self.assertIs(caught.exception, first)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(self.result['stages']), 1)

    def test_original_phase_failure_survives_log_failure(self):
        first = RuntimeError('synthetic native first')
        self.failures['generate'] = first
        self.logs.side_effect = OSError('synthetic log failure')
        with self.assertRaises(RuntimeError) as caught:
            self.go()
        self.assertIs(caught.exception, first)
        self.assertEqual(self.result['stages'][0]['secondary_failure_types'], ['OSError'])

    def test_log_failure_without_prior_failure_blocks_next_phase(self):
        first = OSError('synthetic log failure')
        self.logs.side_effect = first
        with self.assertRaises(OSError) as caught:
            self.go()
        self.assertIs(caught.exception, first)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.result['stages'][0]['secondary_failure_types'], ['OSError'])

    def test_reserved_tail_prevents_log_and_preserves_original_failure(self):
        first = RuntimeError('synthetic native first')
        self.failures['generate'] = first
        self.clock.side_effect = [0, 0, 1260.0]
        with self.assertRaises(RuntimeError) as caught:
            self.go()
        self.assertIs(caught.exception, first); self.logs.assert_not_called()
        self.assertEqual(self.result['stages'][0]['secondary_failure_types'], ['ValueError'])

    def test_log_consuming_work_window_cannot_start_next_phase(self):
        self.clock.side_effect = [0, 0, 1259.0, 1260.0]
        with self.assertRaisesRegex(ValueError, 'INCOMPLETE_WORK_WINDOW'):
            self.go()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.result['stages'][0]['log_observation'], {'synthetic_log_identity': True})

    def test_unknown_secondary_exception_is_type_sanitized(self):
        self.failures['generate'] = RuntimeError('native first')
        self.logs.side_effect = KeyboardInterrupt('SECRET' * 1000)
        with self.assertRaises(RuntimeError):
            self.go()
        self.assertEqual(self.result['stages'][0]['secondary_failure_types'], ['OTHER'])
        self.assertNotIn('SECRET', json.dumps(self.result))

    def test_whole_log_original_caps_forwarded_for_each_phase(self):
        self.go()
        self.assertEqual(self.logs.call_args_list, [
            mock.call(self.support, self.work / 'phases' / name, R.phase_limits(name)['log_bytes'])
            for name in ('generate', 'build', 'run')])


class LogObservation(unittest.TestCase):
    def test_missing_log_performs_no_identity_read(self):
        support = types.SimpleNamespace(identity=mock.Mock())
        with mock.patch.object(Path, 'exists', return_value=False):
            self.assertEqual(R.observe_log(support, Path('/fixed/phase'), R.MIB),
                             {'present': False, 'complete_file_identity': None})
        support.identity.assert_not_called()

    def test_present_log_uses_exact_original_path_cap_and_identity(self):
        identity = {'bytes': 10, 'sha256': 'synthetic'}
        support = types.SimpleNamespace(identity=mock.Mock(return_value=identity))
        with mock.patch.object(Path, 'exists', return_value=True):
            result = R.observe_log(support, Path('/fixed/phase'), 4 * R.MIB)
        support.identity.assert_called_once_with(Path('/fixed/phase/native.log'), 4 * R.MIB)
        self.assertIs(result['complete_file_identity'], identity)
        self.assertTrue(result['whole_file_not_tail'])
        self.assertFalse(result['capsule_or_progress_parsed'])


class Finish(unittest.TestCase):
    def setUp(self):
        self.result = {'stages': []}
        self.work = Path('/fixed/work')
        self.save = mock.Mock()
        self.timer = mock.Mock()
        clock = mock.patch.object(R.time, 'monotonic', return_value=100.0)
        self.clock = clock.start(); self.addCleanup(clock.stop)

    def go(self, failure=None, stop=1320.0):
        return R.finish('support', self.work, self.result, failure, stop, self.save, self.timer)

    def test_report_capped_to_sixty_seconds_and_original_stop(self):
        self.assertIsNone(self.go())
        self.assertEqual(self.result['report_stop'], 160.0)
        self.timer.assert_called_once_with(60.0)
        self.save.assert_called_once_with(self.work / 'EXECUTION_RESULT.json', self.result)
        self.timer.reset_mock(); self.save.reset_mock()
        self.assertIsNone(self.go(stop=125.0))
        self.assertEqual(self.result['report_stop'], 125.0)
        self.timer.assert_called_once_with(25.0)

    def test_first_failure_survives_save_timer_and_expired_tail(self):
        first = RuntimeError('native first')
        self.save.side_effect = OSError('save second')
        self.assertIs(self.go(first), first)
        self.timer.side_effect = OSError('timer second')
        self.assertIs(self.go(first), first)
        self.timer.side_effect = None
        self.save.reset_mock()
        self.assertIs(self.go(first, stop=100.0), first)
        self.save.assert_not_called()

    def test_save_or_timer_failure_returned_without_prior_failure(self):
        for method in (self.save, self.timer):
            with self.subTest(method=method):
                first = OSError('synthetic tail failure')
                method.side_effect = first
                self.assertIs(self.go(), first)
                method.side_effect = None

    def test_expired_tail_does_not_save_and_no_work_does_not_save(self):
        error = self.go(stop=100.0)
        self.assertIsInstance(error, ValueError)
        self.assertEqual(str(error), 'INCOMPLETE_REPORT_WINDOW')
        self.save.assert_not_called()
        self.work = None
        self.assertIsNone(self.go())
        self.save.assert_not_called()

    def test_save_consuming_tail_is_incomplete_without_timer_renewal(self):
        self.clock.side_effect = [100.0, 100.0, 100.0, 160.0]
        error = self.go()
        self.assertIsInstance(error, ValueError)
        self.assertEqual(str(error), 'INCOMPLETE_REPORT_WINDOW')
        self.timer.assert_called_once_with(60.0)
        self.save.assert_called_once()


if __name__ == '__main__':
    if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
        raise RuntimeError('COLD_ISOLATION_REQUIRED')
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024**2, 16 * 1024**2))
    allowed = os.sched_getaffinity(0)
    os.sched_setaffinity(0, {min(allowed)})
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    summary = {'schema': 1, 'mode': 'PURE_MOCK_NO_CHILD_COMPILER_RTL_NETWORK',
               'test_mode': ARGS.mode, 'python_optimize': sys.flags.optimize,
               'source_bytes': PIN[0], 'source_sha256': PIN[1],
               'tests_run': result.testsRun, 'failures': len(result.failures),
               'errors': len(result.errors), 'skipped': len(result.skipped),
               'process_limits': {'as_bytes': 512 * 1024**2, 'cpu_seconds': 30,
                                  'file_bytes': 16 * 1024**2, 'cpu_affinity_count': len(os.sched_getaffinity(0))},
               'status': 'PASS' if result.wasSuccessful() else 'FAIL'}
    (HERE / ('RESULT_' + ARGS.mode + '.json')).write_text(json.dumps(summary, indent=2) + '\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
