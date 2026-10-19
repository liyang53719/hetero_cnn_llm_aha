import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('require -I -S -B before project source loading')
import argparse
import contextlib
import hashlib
import json
from pathlib import Path
import signal
import tempfile
import types
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
SIZE = 16348
SHA = '653de8cdfbdbb5ffe9b3725467ee0f44c98da353e1d680fec4f282d2b73d00d1'
parser = argparse.ArgumentParser()
parser.add_argument('--repo', required=True, type=Path)
args = parser.parse_args()


def load(raw):
    if len(raw) != SIZE or hashlib.sha256(raw).hexdigest() != SHA:
        raise ValueError('fixed source rejected before compile')
    result = types.ModuleType('cold_ci_support')
    result.__file__ = str(HERE / 'ci_support_v3.py')
    exec(compile(raw, result.__file__, 'exec', dont_inherit=True), result.__dict__)
    return result


RAW = (HERE / 'ci_support_v3.py').read_bytes()
G = load(RAW)


class Cold(unittest.TestCase):
    def test_raw_short_before_compile(self):
        with mock.patch('builtins.compile') as comp:
            with self.assertRaises(ValueError): load(RAW[:-1])
            comp.assert_not_called()

    def test_raw_same_length_before_compile(self):
        with mock.patch('builtins.compile') as comp:
            with self.assertRaises(ValueError): load(bytes([RAW[0] ^ 1]) + RAW[1:])
            comp.assert_not_called()

    def test_module_guard_before_compile(self):
        with mock.patch('builtins.compile') as comp:
            with self.assertRaises(ValueError): G.module_bytes(b'x=1', '/tmp/x.py', 4, 'a' * 64, 'bad')
            comp.assert_not_called()

    def test_exact_byte_read(self):
        raw = b'fixed test'
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / 'source.py'; p.write_bytes(raw)
            self.assertEqual(G.checked_bytes(p, len(raw), G.sha(raw)), raw)

    def test_symlink_read_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / 'source'; p.write_bytes(b'x'); q = Path(root) / 'alias'; q.symlink_to(p)
            with self.assertRaises(OSError): G.checked_bytes(q, 1, G.sha(b'x'))

    def test_wrong_hash_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / 'source'; p.write_bytes(b'x')
            with self.assertRaises(ValueError): G.checked_bytes(p, 1, '0' * 64)

    def test_work_cap(self):
        self.assertEqual(G.remaining_work(20., 6600., 0., 180, 160), 165.)

    def test_shared_cap(self):
        self.assertEqual(G.remaining_work(20., 100., 0., 180, 160), 85.)

    def test_exhausted_shared_cap(self):
        with self.assertRaises(ValueError): G.remaining_work(90., 100., 0., 180, 160)

    def test_nonfinite(self):
        for value in (float('nan'), float('inf'), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                G.remaining_work(value, 100., 0., 180, 160)

    def test_blocked_signal_rejected_without_unblock(self):
        with mock.patch.object(G.signal, 'pthread_sigmask', return_value={signal.SIGALRM}) as query:
            with self.assertRaises(ValueError): G.deadline_ready()
            query.assert_called_once_with(signal.SIG_BLOCK, [])

    def test_occupied_timer_rejected_without_cancel(self):
        with mock.patch.object(G.signal, 'pthread_sigmask', return_value=set()), \
             mock.patch.object(G.signal, 'getitimer', return_value=(10., 0.)), \
             mock.patch.object(G.signal, 'setitimer') as change:
            with self.assertRaises(ValueError): G.deadline_ready()
            change.assert_not_called()

    def test_unoccupied_deadline(self):
        with mock.patch.object(G.signal, 'pthread_sigmask', return_value=set()), \
             mock.patch.object(G.signal, 'getitimer', return_value=(0., 0.)):
            G.deadline_ready()

    def test_published_fixed_projection_without_native(self):
        support, base, pins = G.fixed_support(args.repo.resolve())
        self.assertEqual(len(pins), 4)
        plan = {'published_sources': base['published_sources'], 'environment': {'PATH': '/usr/bin:/bin'},
                'phases': {'probe': {'fsize_bytes': 8 * 1024**2, 'log_bytes': 1024**2,
                                     'sample_rows': 602, 'as_bytes': 1024**3}}}
        supervisor, observers = support.projected_sources(plan, 'probe')
        self.assertIn(b'WNOWAIT', supervisor)
        self.assertIn(b"state['count']<602", observers)
        self.assertNotIn(b"state['count']<340", observers)
        self.assertIn(b'env=BUILD_ENV', supervisor)

    def phase_fixture(self, bounded):
        support = mock.Mock()
        saved = mock.Mock()
        support.make_runner.return_value = {'bounded': bounded, 'save': saved,
                                           'projection_hashes': {'supervisor': 'x', 'observation': 'y'}}
        base = {'published_sources': {}}
        cfg = {'total_seconds': 30, 'work_seconds': 10, 'cpu_seconds': 10}
        return support, base, cfg, saved

    def test_phase_mock_success(self):
        record = {'exit_code': 0, 'cleanup_confirmed': True}
        support, base, cfg, saved = self.phase_fixture(lambda *a: (record, b'fixed log'))
        with mock.patch.object(G, 'deadline_ready'), mock.patch.object(G.os.path, 'lexists', return_value=False), \
             mock.patch.object(G.signal, 'signal'), mock.patch.object(G.signal, 'setitimer'), \
             mock.patch.object(G.time, 'monotonic', return_value=1.):
            result = G.run_phase(support, base, 'probe', ['/fixed/tool'], '/tmp', '/tmp/fresh', {}, cfg, 6600.)
        self.assertEqual(result[:2], (record, b'fixed log'))
        saved.assert_called_once()

    def test_phase_mock_failure_preserved_and_usage_saved(self):
        original = TimeoutError('work limit')
        support, base, cfg, saved = self.phase_fixture(mock.Mock(side_effect=original))
        with mock.patch.object(G, 'deadline_ready'), mock.patch.object(G.os.path, 'lexists', return_value=False), \
             mock.patch.object(G.signal, 'signal'), mock.patch.object(G.signal, 'setitimer'), \
             mock.patch.object(G.time, 'monotonic', return_value=1.):
            with self.assertRaises(TimeoutError) as caught:
                G.run_phase(support, base, 'probe', ['/fixed/tool'], '/tmp', '/tmp/fresh', {}, cfg, 6600.)
        self.assertIs(caught.exception, original)
        saved.assert_called_once()

    def test_phase_mock_postflight_expiry_rejects_child_zero(self):
        clock = [1.]
        def bounded(*args):
            clock[0] = 32.
            return {'exit_code': 0, 'cleanup_confirmed': True}, b''
        support, base, cfg, saved = self.phase_fixture(bounded)
        with mock.patch.object(G, 'deadline_ready'), mock.patch.object(G.os.path, 'lexists', return_value=False), \
             mock.patch.object(G.signal, 'signal'), mock.patch.object(G.signal, 'setitimer'), \
             mock.patch.object(G.time, 'monotonic', side_effect=lambda: clock[0]):
            with self.assertRaisesRegex(ValueError, 'postflight exhausted'):
                G.run_phase(support, base, 'probe', ['/fixed/tool'], '/tmp', '/tmp/fresh', {}, cfg, 6600.)

    def test_owned_timer_exact_current_handler(self):
        handler = lambda *args: None
        with mock.patch.object(G.signal, 'pthread_sigmask', return_value=set()), \
             mock.patch.object(G.signal, 'getitimer', return_value=(99., 0.)), \
             mock.patch.object(G.signal, 'getsignal', return_value=handler), \
             mock.patch.object(G.time, 'monotonic', return_value=1.):
            G.owned_deadline({'handler': handler, 'deadline': 100.}, 100.)

    def test_owned_timer_wrong_handler_rejected_without_mutation(self):
        handler = lambda *args: None
        with mock.patch.object(G.signal, 'pthread_sigmask', return_value=set()), \
             mock.patch.object(G.signal, 'getitimer', return_value=(99., 0.)), \
             mock.patch.object(G.signal, 'getsignal', return_value=lambda *args: None), \
             mock.patch.object(G.signal, 'setitimer') as change, \
             mock.patch.object(G.time, 'monotonic', return_value=1.):
            with self.assertRaises(ValueError): G.owned_deadline({'handler': handler, 'deadline': 100.}, 100.)
            change.assert_not_called()

    def test_owned_timer_wider_or_periodic_rejected(self):
        handler = lambda *args: None
        for timer in ((100., 0.), (99., 1.), (0., 0.)):
            with mock.patch.object(G.signal, 'pthread_sigmask', return_value=set()), \
                 mock.patch.object(G.signal, 'getitimer', return_value=timer), \
                 mock.patch.object(G.signal, 'getsignal', return_value=handler), \
                 mock.patch.object(G.time, 'monotonic', return_value=1.):
                with self.assertRaises(ValueError): G.owned_deadline({'handler': handler, 'deadline': 100.}, 100.)

    def test_preparation_armed_and_owner_restored_on_error(self):
        handler = lambda *args: None
        support, base, cfg, saved = self.phase_fixture(mock.Mock())
        original = RuntimeError('prep failed')
        events=[]
        def prep(*args):
            self.assertTrue(events and events[-1][0] == signal.ITIMER_REAL and events[-1][1] > 0)
            raise original
        support.make_runner.side_effect=prep
        with mock.patch.object(G, 'owned_deadline'), mock.patch.object(G.os.path, 'lexists', return_value=False), \
             mock.patch.object(G.signal, 'signal', return_value=handler), \
             mock.patch.object(G.signal, 'setitimer', side_effect=lambda *a:events.append(a)), \
             mock.patch.object(G.time, 'monotonic', return_value=1.):
            with self.assertRaises(RuntimeError) as caught:
                G.run_phase(support, base, 'probe', ['/fixed/tool'], '/tmp', '/tmp/fresh', {}, cfg, 100., {'handler':handler,'deadline':100.})
        self.assertIs(caught.exception, original)
        self.assertEqual(events[-1], (signal.ITIMER_REAL,99.))
        saved.assert_not_called()


class DiagnosticCold(unittest.TestCase):
    argv = ['/fixed/tool']
    cwd = '/fixed/cwd'
    evidence = '/fixed/evidence'
    cfg = {'total_seconds': 30, 'work_seconds': 10, 'cpu_seconds': 10,
           'as_bytes': 1024 * 1024}

    def receipt(self, **changes):
        value = {
            'stage': 'native', 'argv': list(self.argv), 'cwd': self.cwd,
            'expected_exit': 0, 'cpu_limit_seconds': 10,
            'address_space_limit_bytes': self.cfg['as_bytes'],
            'status': 'FAIL', 'seconds': 0.25, 'pid': 123,
            'exit_code': 2, 'reaped': True, 'timed_out': False,
            'exit_observed_while_unreaped': {'pid': 123, 'code': 1, 'status': 2},
            'kill_attempted': True, 'kill_result': 'signal_sent_before_reap',
            'spawn_handle_acquired': True, 'anchor_confirmed': True,
            'group_state': 'absent', 'cleanup_confirmed': True,
        }
        value.update(changes)
        return value

    def observation(self, record, failure=None, result=None, support=None, allow_read=True):
        if failure is None:
            failure = ValueError('private exception TOKEN=synthetic')
        support = support or mock.Mock()
        return G.terminal_observation(
            support, self.evidence, 'probe', self.argv, self.cwd, self.cfg,
            record, result, failure, 'NATIVE_SUPERVISION', allow_read)

    def fixture(self, bounded, receipt=None, save_error=None):
        support = mock.Mock()
        saved = mock.Mock(side_effect=save_error)
        support.make_runner.return_value = {
            'bounded': bounded, 'save': saved,
            'projection_hashes': {'supervisor': 'x', 'observation': 'y'},
        }
        if receipt is None:
            receipt = self.receipt()
        raw = json.dumps(receipt).encode('ascii')
        support.identity.return_value = {'bytes': len(raw), 'sha256': G.sha(raw)}
        support.checked_read.return_value = raw
        return support, saved

    def phase(self, support, diagnostics, usage_values=None):
        if usage_values is None:
            usage_values = [
                {'user': 10., 'system': 4., 'maxrss_kib_cumulative_parent_children': 111},
                {'user': 12., 'system': 5., 'maxrss_kib_cumulative_parent_children': 222},
            ]
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(G, 'deadline_ready'))
            stack.enter_context(mock.patch.object(G.os.path, 'lexists', return_value=False))
            stack.enter_context(mock.patch.object(G.signal, 'signal'))
            stack.enter_context(mock.patch.object(G.signal, 'setitimer'))
            stack.enter_context(mock.patch.object(G.time, 'monotonic', return_value=1.))
            stack.enter_context(mock.patch.object(G, 'usage', side_effect=usage_values))
            return G.run_phase(support, {'published_sources': {}}, 'probe', self.argv,
                               self.cwd, self.evidence, {}, self.cfg, 6600.,
                               diagnostics=diagnostics)

    def test_terminal_exit2_cleanup_true(self):
        safe = self.observation(self.receipt())
        self.assertEqual(safe['exit_code'], 2)
        self.assertIs(safe['cleanup_confirmed'], True)
        self.assertEqual(safe['failure_code'], 'CHILD_EXIT_NONZERO')
        self.assertEqual((safe['waitid_code'], safe['waitid_status']), (1, 2))
        self.assertIsNone(safe['final_reap_signal'])
        self.assertNotIn('TOKEN', json.dumps(safe))
        self.assertNotIn(self.cwd, json.dumps(safe))

    def test_terminal_timeout_cleanup_signal_distinct_from_original_waitid(self):
        safe = self.observation(self.receipt(exit_code=-9, timed_out=True), TimeoutError('private'))
        self.assertEqual(safe['exit_code'], -9)
        self.assertEqual(safe['final_reap_signal'], 9)
        self.assertEqual((safe['waitid_code'], safe['waitid_status']), (1, 2))
        self.assertEqual(safe['failure_code'], 'SUPERVISOR_TIMEOUT_CLASSIFICATION')
        self.assertIs(safe['cleanup_confirmed'], True)

    def test_terminal_unknown_cleanup_is_null(self):
        for changes in ({'cleanup_confirmed': None}, {'group_state': 'unknown'},
                        {'anchor_confirmed': False}, {'spawn_handle_acquired': False},
                        {'reaped': False}):
            with self.subTest(changes=changes):
                safe = self.observation(self.receipt(exit_code=0, **changes))
                self.assertIsNone(safe['cleanup_confirmed'])
                self.assertEqual(safe['failure_code'], 'CLEANUP_UNCONFIRMED')

    def test_terminal_present_cleanup_false_is_explicit(self):
        safe = self.observation(self.receipt(exit_code=0, group_state='present', cleanup_confirmed=False))
        self.assertIs(safe['cleanup_confirmed'], False)

    def test_terminal_partial_receipts_do_not_promote_exit(self):
        for changes in ({'status': None}, {'status': 'private'}, {'seconds': None},
                        {'seconds': float('nan')}, {'seconds': -1}, {'seconds': True}):
            with self.subTest(changes=changes):
                safe = self.observation(self.receipt(**changes))
                self.assertEqual(safe['failure_code'], 'RECEIPT_PARTIAL')
                self.assertIsNone(safe['exit_code'])
                self.assertIsNone(safe['cleanup_confirmed'])

    def test_terminal_invalid_receipt_bindings_do_not_promote_exit(self):
        for key, value in (('stage', 'wrong'), ('argv', ['/private/other']),
                           ('cwd', '/private/other'), ('expected_exit', 2),
                           ('cpu_limit_seconds', 20), ('address_space_limit_bytes', 10)):
            with self.subTest(key=key):
                safe = self.observation(self.receipt(**{key: value}))
                self.assertEqual(safe['failure_code'], 'RECEIPT_INVALID')
                self.assertIsNone(safe['exit_code'])
                self.assertNotIn('/private', json.dumps(safe))

    def test_terminal_invalid_exit_and_waitid_remain_null(self):
        for code in (True, 256, -256, '2', 2.0):
            with self.subTest(code=code):
                safe = self.observation(self.receipt(exit_code=code,
                    exit_observed_while_unreaped={'pid': 999, 'code': 1, 'status': 2}))
                self.assertIsNone(safe['exit_code'])
                self.assertIsNone(safe['waitid_code'])
                self.assertIsNone(safe['waitid_status'])

    def test_terminal_usage_is_finite_nonnegative_numeric_only(self):
        for value in (float('nan'), float('inf'), -1, True, 'private'):
            with self.subTest(value=value):
                safe = self.observation(self.receipt(), result={
                    'child_user_cpu_seconds': value, 'child_system_cpu_seconds': value,
                    'maxrss_kib_cumulative_parent_children': value})
                self.assertIsNone(safe['child_user_cpu_seconds'])
                self.assertIsNone(safe['child_system_cpu_seconds'])
                self.assertIsNone(safe['child_maxrss_kib_cumulative'])

    def test_terminal_receipt_recovery_uses_bounded_checked_read(self):
        support, unused = self.fixture(mock.Mock())
        safe = self.observation(None, support=support)
        self.assertEqual(safe['exit_code'], 2)
        support.identity.assert_called_once_with(Path(self.evidence) / 'native.json', 1024**2)
        pin = support.identity.return_value
        support.checked_read.assert_called_once_with(
            Path(self.evidence) / 'native.json', pin['bytes'], pin['sha256'])

    def test_terminal_missing_duplicate_or_invalid_json_receipt_is_unavailable(self):
        for raw in (b'{', b'{"stage":"native","stage":"native"}', b'null', b'[]'):
            with self.subTest(raw=raw):
                support, unused = self.fixture(mock.Mock())
                support.checked_read.return_value = raw
                safe = self.observation(None, support=support)
                self.assertEqual(safe['failure_code'], 'RECEIPT_UNAVAILABLE')
                self.assertIsNone(safe['exit_code'])

    def test_terminal_expired_deadline_does_not_read_receipt(self):
        support = mock.Mock()
        safe = self.observation(None, failure=TimeoutError('private'), support=support, allow_read=False)
        support.identity.assert_not_called()
        support.checked_read.assert_not_called()
        self.assertEqual(safe['failure_code'], 'SUPERVISOR_TIMEOUT_CLASSIFICATION')
        self.assertIsNone(safe['cleanup_confirmed'])

    def test_terminal_sampler_contract_has_finite_classification(self):
        safe = self.observation(self.receipt(parent_exception={
            'type': 'ValueError', 'message': 'leader sample row cap exceeded'}))
        self.assertEqual(safe['failure_code'], 'SAMPLER_CONTRACT')
        self.assertNotIn('leader sample row cap exceeded', json.dumps(safe))

    def test_phase_exit2_receipt_and_usage_survive_original_failure(self):
        original = ValueError('original private child failure')
        support, saved = self.fixture(mock.Mock(side_effect=original))
        diagnostics = {}
        with self.assertRaises(ValueError) as caught:
            self.phase(support, diagnostics)
        self.assertIs(caught.exception, original)
        saved.assert_called_once()
        self.assertEqual(saved.call_args.args[0], Path(self.evidence) / 'USAGE.json')
        self.assertEqual(diagnostics['exit_code'], 2)
        self.assertIs(diagnostics['cleanup_confirmed'], True)
        self.assertEqual(diagnostics['failure_code'], 'CHILD_EXIT_NONZERO')
        self.assertEqual(diagnostics['child_user_cpu_seconds'], 2.)
        self.assertEqual(diagnostics['child_system_cpu_seconds'], 1.)
        self.assertEqual(diagnostics['child_maxrss_kib_cumulative'], 222)

    def test_phase_timeout_retains_cleanup_signal_and_original_waitid(self):
        original = TimeoutError('original private timeout')
        support, saved = self.fixture(mock.Mock(side_effect=original),
                                      self.receipt(exit_code=-9, timed_out=True))
        diagnostics = {}
        with self.assertRaises(TimeoutError) as caught:
            self.phase(support, diagnostics)
        self.assertIs(caught.exception, original)
        self.assertEqual(diagnostics['final_reap_signal'], 9)
        self.assertEqual((diagnostics['waitid_code'], diagnostics['waitid_status']), (1, 2))
        self.assertEqual(diagnostics['failure_code'], 'SUPERVISOR_TIMEOUT_CLASSIFICATION')
        self.assertIs(diagnostics['cleanup_confirmed'], True)
        saved.assert_called_once()

    def test_phase_partial_receipt_preserves_original_failure_and_usage(self):
        original = ValueError('original failure')
        support, saved = self.fixture(mock.Mock(side_effect=original), self.receipt(status=None))
        diagnostics = {}
        with self.assertRaises(ValueError) as caught:
            self.phase(support, diagnostics)
        self.assertIs(caught.exception, original)
        self.assertEqual(diagnostics['failure_code'], 'RECEIPT_PARTIAL')
        self.assertIsNone(diagnostics['cleanup_confirmed'])
        self.assertEqual(diagnostics['child_user_cpu_seconds'], 2.)
        saved.assert_called_once()

    def test_phase_usage_save_error_cannot_replace_original_failure(self):
        original = TimeoutError('original timeout')
        support, saved = self.fixture(mock.Mock(side_effect=original),
                                      save_error=RuntimeError('secondary private save error'))
        diagnostics = {}
        with self.assertRaises(TimeoutError) as caught:
            self.phase(support, diagnostics)
        self.assertIs(caught.exception, original)
        self.assertEqual(diagnostics['exit_code'], 2)
        self.assertEqual(diagnostics['child_user_cpu_seconds'], 2.)
        self.assertNotIn('private', json.dumps(diagnostics))

    def test_phase_usage_collection_error_cannot_replace_original_failure(self):
        original = ValueError('original child error')
        support, saved = self.fixture(mock.Mock(side_effect=original))
        diagnostics = {}
        before = {'user': 10., 'system': 4., 'maxrss_kib_cumulative_parent_children': 111}
        with self.assertRaises(ValueError) as caught:
            self.phase(support, diagnostics, [before, RuntimeError('secondary usage error')])
        self.assertIs(caught.exception, original)
        self.assertEqual(diagnostics['exit_code'], 2)
        self.assertIsNone(diagnostics['child_user_cpu_seconds'])
        saved.assert_not_called()

    def test_phase_diagnostic_error_cannot_replace_original_failure(self):
        original = ValueError('original child error')
        support, saved = self.fixture(mock.Mock(side_effect=original))
        diagnostics = {}
        with mock.patch.object(G, 'terminal_observation', side_effect=RuntimeError('secondary diagnostic error')):
            with self.assertRaises(ValueError) as caught:
                self.phase(support, diagnostics)
        self.assertIs(caught.exception, original)
        self.assertEqual(diagnostics, G.diagnostic_defaults())
        saved.assert_called_once()

    def test_phase_returned_nonzero_record_is_classified_before_raise(self):
        record = self.receipt()
        support, saved = self.fixture(mock.Mock(return_value=(record, b'private log')))
        diagnostics = {}
        with self.assertRaises(ValueError):
            self.phase(support, diagnostics)
        self.assertEqual(diagnostics['failure_code'], 'CHILD_EXIT_NONZERO')
        self.assertEqual(diagnostics['exit_code'], 2)
        self.assertIs(diagnostics['cleanup_confirmed'], True)
        saved.assert_called_once()

    def test_phase_returned_unknown_cleanup_is_classified_before_raise(self):
        record = self.receipt(status='PASS', exit_code=0, group_state='unknown', cleanup_confirmed=None)
        support, saved = self.fixture(mock.Mock(return_value=(record, b'private log')))
        diagnostics = {}
        with self.assertRaises(ValueError):
            self.phase(support, diagnostics)
        self.assertEqual(diagnostics['failure_code'], 'CLEANUP_UNCONFIRMED')
        self.assertIsNone(diagnostics['cleanup_confirmed'])
        saved.assert_called_once()


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]], verbosity=2)
