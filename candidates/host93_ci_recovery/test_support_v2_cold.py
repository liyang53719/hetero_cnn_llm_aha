import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('require -I -S -B before project source loading')
import argparse
import hashlib
import json
from pathlib import Path
import signal
import tempfile
import types
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
SIZE = 9154
SHA = '931c8d8e4b42c125617ca1058dac809723f8371ffe90205da6b0c64b0aea1a26'
parser = argparse.ArgumentParser()
parser.add_argument('--repo', required=True, type=Path)
args = parser.parse_args()


def load(raw):
    if len(raw) != SIZE or hashlib.sha256(raw).hexdigest() != SHA:
        raise ValueError('fixed source rejected before compile')
    result = types.ModuleType('cold_ci_support')
    result.__file__ = str(HERE / 'ci_support_v2.py')
    exec(compile(raw, result.__file__, 'exec', dont_inherit=True), result.__dict__)
    return result


RAW = (HERE / 'ci_support_v2.py').read_bytes()
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


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]], verbosity=2)
