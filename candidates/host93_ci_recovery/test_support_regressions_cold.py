"""F01/F02 regression expectations; every phase effect is mocked."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('require -I -S -B before project source loading')
import contextlib
import hashlib
import json
from pathlib import Path
import types
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
SIZE = 16348
SHA = '653de8cdfbdbb5ffe9b3725467ee0f44c98da353e1d680fec4f282d2b73d00d1'
RAW = (HERE / 'ci_support_v3.py').read_bytes()
if len(RAW) != SIZE or hashlib.sha256(RAW).hexdigest() != SHA:
    raise ValueError('fixed source rejected before compile')
G = types.ModuleType('cold_support_regressions')
G.__file__ = str(HERE / 'ci_support_v3.py')
exec(compile(RAW, G.__file__, 'exec', dont_inherit=True), G.__dict__)

ARGV = ['/fixed/tool']
CWD = '/fixed/cwd'
EVIDENCE = '/fixed/evidence'
LIMITS = {'total_seconds': 30, 'work_seconds': 10, 'cpu_seconds': 10, 'as_bytes': 1048576}


def receipt(**changes):
    value = {'stage': 'native', 'argv': ARGV, 'cwd': CWD, 'expected_exit': 0,
             'cpu_limit_seconds': 10, 'address_space_limit_bytes': 1048576,
             'status': 'PASS', 'seconds': 0.25, 'pid': 123,
             'exit_code': 0, 'reaped': True, 'timed_out': False,
             'exit_observed_while_unreaped': {'pid': 123, 'code': 1, 'status': 0},
             'kill_attempted': True, 'kill_result': 'signal_sent_before_reap',
             'spawn_handle_acquired': True, 'anchor_confirmed': True,
             'group_state': 'absent', 'cleanup_confirmed': True}
    value.update(changes)
    return value


class Regressions(unittest.TestCase):
    def setUp(self):
        self.support = mock.Mock()
        self.bounded = mock.Mock(return_value=(receipt(), b''))
        self.saved = mock.Mock()
        self.support.make_runner.return_value = {
            'bounded': self.bounded, 'save': self.saved,
            'projection_hashes': {'supervisor': 'fixed', 'observation': 'fixed'}}
        raw = json.dumps(receipt()).encode('ascii')
        self.support.identity.return_value = {
            'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        self.support.checked_read.return_value = raw
        self.clock = [1.0]
        self.diag = {}
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        for patch in (mock.patch.object(G, 'deadline_ready'),
                      mock.patch.object(G, 'owned_deadline'),
                      mock.patch.object(G.os.path, 'lexists', return_value=False),
                      mock.patch.object(G.signal, 'signal'),
                      mock.patch.object(G.time, 'monotonic', side_effect=lambda: self.clock[0])):
            self.stack.enter_context(patch)
        self.timer = self.stack.enter_context(mock.patch.object(G.signal, 'setitimer'))
        self.usage = self.stack.enter_context(mock.patch.object(G, 'usage', side_effect=[
            {'user': 10., 'system': 4., 'maxrss_kib_cumulative_parent_children': 111},
            {'user': 12., 'system': 5., 'maxrss_kib_cumulative_parent_children': 222}]))

    def phase(self, owner=None):
        return G.run_phase(self.support, {'published_sources': {}}, 'probe', ARGV, CWD,
            EVIDENCE, {}, LIMITS, 100., owner=owner, diagnostics=self.diag)

    def timeout_observation(self):
        self.assertEqual(self.diag['failure_code'], 'SUPERVISOR_TIMEOUT_CLASSIFICATION')
        self.assertEqual(self.diag['failure_boundary'], 'USAGE_OR_POSTFLIGHT')
        self.assertGreaterEqual(self.clock[0], 31.)

    def test_f01_preparation_rejection_never_reads_stale_receipt(self):
        G.os.path.lexists.return_value = True
        with self.assertRaisesRegex(ValueError, 'fresh phase evidence'):
            self.phase()
        self.support.fresh_directory.assert_not_called()
        self.support.make_runner.assert_not_called()
        self.bounded.assert_not_called()
        self.support.identity.assert_not_called()
        self.support.checked_read.assert_not_called()
        self.assertEqual(self.diag['failure_boundary'], 'PREPARE')
        self.assertEqual(self.diag['failure_code'], 'RECEIPT_UNAVAILABLE')
        self.assertEqual(self.diag['native_record_status'], 'UNKNOWN')
        for key in ('exit_code', 'final_reap_signal', 'cleanup_confirmed',
                    'waitid_code', 'waitid_status', 'receipt_timed_out',
                    'child_user_cpu_seconds', 'child_system_cpu_seconds',
                    'child_maxrss_kib_cumulative'):
            self.assertIsNone(self.diag[key], key)

    def test_f02_phase_alarm_during_projection_is_raised(self):
        def alarm(*args, **kwargs):
            self.clock[0] = 32.0
            G.interrupted(G.signal.SIGALRM, None)
        self.stack.enter_context(mock.patch.object(G, 'terminal_observation', side_effect=alarm))
        with self.assertRaisesRegex(TimeoutError, 'fixed CI phase or shared deadline'):
            self.phase()
        self.timeout_observation()
        self.assertEqual(self.timer.call_args.args, (G.signal.ITIMER_REAL, 0))

    def test_f02_phase_alarm_with_owner_raises_and_restores_shared_timer(self):
        def alarm(*args, **kwargs):
            self.clock[0] = 32.0
            G.interrupted(G.signal.SIGALRM, None)
        self.stack.enter_context(mock.patch.object(G, 'terminal_observation', side_effect=alarm))
        with self.assertRaisesRegex(TimeoutError, 'fixed CI phase or shared deadline'):
            self.phase({'handler': lambda *args: None, 'deadline': 100.})
        self.timeout_observation()
        self.assertEqual(self.timer.call_args.args, (G.signal.ITIMER_REAL, 68.))

    def test_f02_projection_overrun_without_alarm_is_raised(self):
        original = G.terminal_observation
        def slow(*args, **kwargs):
            self.clock[0] = 32.0
            return original(*args, **kwargs)
        self.stack.enter_context(mock.patch.object(G, 'terminal_observation', side_effect=slow))
        with self.assertRaisesRegex(TimeoutError, 'phase diagnostic deadline exhausted'):
            self.phase({'handler': lambda *args: None, 'deadline': 100.})
        self.timeout_observation()
        self.assertEqual(self.diag['exit_code'], 0)
        self.assertIs(self.diag['cleanup_confirmed'], True)
        self.assertEqual(self.timer.call_args.args, (G.signal.ITIMER_REAL, 68.))

    def test_original_failure_survives_projection_failure(self):
        original = ValueError('original native failure')
        self.bounded.side_effect = original
        self.stack.enter_context(mock.patch.object(G, 'terminal_observation',
                                                   side_effect=RuntimeError('projection')))
        with self.assertRaises(ValueError) as caught:
            self.phase()
        self.assertIs(caught.exception, original)

    def test_original_failure_survives_usage_failure(self):
        original = ValueError('original native failure')
        self.bounded.side_effect = original
        self.usage.side_effect = [{'user': 1., 'system': 0.}, RuntimeError('usage')]
        with self.assertRaises(ValueError) as caught:
            self.phase()
        self.assertIs(caught.exception, original)
        self.assertIsNone(self.diag['child_user_cpu_seconds'])

    def test_original_failure_survives_usage_save_failure(self):
        original = ValueError('original native failure')
        self.bounded.side_effect = original
        self.saved.side_effect = RuntimeError('save')
        with self.assertRaises(ValueError) as caught:
            self.phase()
        self.assertIs(caught.exception, original)
        self.assertEqual(self.diag['child_user_cpu_seconds'], 2.)


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]], verbosity=2)
