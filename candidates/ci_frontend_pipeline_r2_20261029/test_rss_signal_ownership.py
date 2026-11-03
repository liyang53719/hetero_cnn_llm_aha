"""Isolated signal-ownership probes. Synthetic host only; never a DUT."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
HERE = Path(__file__).resolve().parent
BASE = Path(os.environ.get('RSS_TELEMETRY_BASE', str(HERE)))

def fixture_caps():
    return dict(wall_seconds=3, cleanup_seconds=3, rss_telemetry_policy={},
                file_bytes=2 << 20, tree_bytes=8 << 20, log_bytes=1 << 20,
                raw_log_bytes=1 << 20, max_entries=1000,
                per_process_as_bytes=512 << 20, per_process_cpu_seconds=3,
                rss_bytes=256 << 20, cpu_seconds=3, min_free_disk_bytes=0)

def probe(kind, name):
    sig = getattr(signal, name)
    timer = signal.ITIMER_REAL if sig == signal.SIGALRM else signal.ITIMER_PROF
    deliveries = []

    def old_handler(number, frame):
        deliveries.append(number)
    signal.signal(sig, old_handler)
    with tempfile.TemporaryDirectory(prefix='rss-signal-probe-') as temp:
        root = Path(temp)
        for filename in ('strict_cleanup.py', 'lossless_log.py'):
            shutil.copyfile(BASE / filename, root / filename)
        for filename in ('rss_telemetry.py', 'supervise_multiroot.py'):
            shutil.copyfile(HERE / filename, root / filename)
        spec = importlib.util.spec_from_file_location('probe_supervisor', root / 'supervise_multiroot.py')
        module = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(root))
        spec.loader.exec_module(module)
        sys.path.pop(0)
        if kind in ('blocked', 'pending'):
            signal.pthread_sigmask(signal.SIG_BLOCK, {sig})
        if kind == 'pending':
            os.kill(os.getpid(), sig)
        if kind == 'active':
            signal.setitimer(timer, 5.0, 1.0)
        before_mask = signal.pthread_sigmask(signal.SIG_BLOCK, set())
        before_pending = signal.sigpending()
        before_timer = signal.getitimer(timer)
        original_mask = signal.pthread_sigmask
        injected = False

        def during_claim(how, signals):
            nonlocal injected
            result = original_mask(how, signals)
            if kind == 'arriving' and (not injected) and (how == signal.SIG_BLOCK) and (sig in signals):
                injected = True
                os.kill(os.getpid(), sig)
            return result
        reason = None
        with patch.object(signal, 'pthread_sigmask', side_effect=during_claim), patch.object(module.subprocess, 'Popen', side_effect=AssertionError('worker must not start')):
            try:
                module.execute(['must-not-start'], root / 'run', root / 'lock', fixture_caps(), {}, {})
            except ValueError as error:
                reason = str(error)
        after_mask = signal.pthread_sigmask(signal.SIG_BLOCK, set())
        after_pending = signal.sigpending()
        after_timer = signal.getitimer(timer)
        expected = ('initially blocked' if kind == 'blocked' or
                    (kind == 'pending' and sig in (signal.SIGALRM, signal.SIGPROF))
                    else 'initially active' if kind == 'active' else 'initially pending')
        if not (reason and expected in reason):
            raise AssertionError((expected, reason))
        if not not (root / 'run').exists():
            raise AssertionError('probe assertion failed')
        if not before_mask == after_mask:
            raise AssertionError((before_mask, after_mask))
        if not signal.getsignal(sig) is old_handler:
            raise AssertionError('probe assertion failed')
        if kind == 'active':
            if not (0 < after_timer[0] <= before_timer[0] and after_timer[1] == before_timer[1] == 1.0):
                raise AssertionError((before_timer, after_timer))
        elif not after_timer == before_timer == (0.0, 0.0):
            raise AssertionError('probe assertion failed')
        if kind == 'pending':
            if not (sig in before_pending and sig in after_pending and (not deliveries)):
                raise AssertionError('probe assertion failed')
        if kind == 'arriving':
            if not (deliveries == [sig] and sig not in after_pending):
                raise AssertionError('probe assertion failed')
        signal.setitimer(timer, 0)
        if sig in signal.sigpending():
            signal.sigtimedwait({sig}, 0)
        signal.pthread_sigmask(signal.SIG_SETMASK, set())
        print(json.dumps(dict(kind=kind, signal=name, reason=reason, preserved=True)))

def late_probe(kind):
    import hashlib
    deliveries = []
    watched = signal.SIGALRM if kind == 'owned_expiry' else signal.SIGTERM

    def old_handler(number, frame):
        deliveries.append(number)
    signal.signal(watched, old_handler)
    with tempfile.TemporaryDirectory(prefix='rss-late-signal-') as temp:
        root = Path(temp)
        for filename in ('strict_cleanup.py', 'lossless_log.py'):
            shutil.copyfile(BASE / filename, root / filename)
        for filename in ('rss_telemetry.py', 'supervise_multiroot.py'):
            shutil.copyfile(HERE / filename, root / filename)
        with (root / 'rss_telemetry.py').open('a') as file:
            file.write('\nimport signal\n_original_verify=verify\ndef verify(*args,**kwargs):\n result=_original_verify(*args,**kwargs)\n')
            if kind == 'owned_expiry':
                file.write(' signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGALRM})\n time.sleep(1.1)\n')
            else:
                file.write(' signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGTERM})\n os.kill(os.getpid(),signal.SIGTERM)\n')
            file.write(' return result\n')
        spec = importlib.util.spec_from_file_location('late_supervisor', root / 'supervise_multiroot.py')
        module = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(root))
        spec.loader.exec_module(module)
        sys.path.pop(0)
        p = dict(schema='FULL_PREFILL_RSS_GZIP_V1', raw_bytes=1 << 20, compressed_bytes=64 << 20, line_bytes=1 << 20, verification_wall_seconds=1, verification_cpu_seconds=1)
        caps = dict(wall_seconds=3, cleanup_seconds=3, rss_telemetry_policy=p, file_bytes=2 << 20, tree_bytes=8 << 20, log_bytes=1 << 20, raw_log_bytes=1 << 20, max_entries=1000, per_process_as_bytes=512 << 20, per_process_cpu_seconds=3, rss_bytes=256 << 20, cpu_seconds=3, min_free_disk_bytes=0)
        pins = {str(root / 'rss_telemetry.py'): hashlib.sha256((root / 'rss_telemetry.py').read_bytes()).hexdigest()}
        result = module.execute([sys.executable, '-c', "import time; print('synthetic-signal-fixture'); time.sleep(.1)"], root / 'run', root / 'lock', caps, dict(os.environ), pins)
        if not result['status'] == ('FAIL_OR_INCOMPLETE' if kind == 'owned_expiry' else 'PASS_PROCESS_ONLY'):
            raise AssertionError(result)
        if not signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0):
            raise AssertionError('probe assertion failed')
        if not signal.getitimer(signal.ITIMER_PROF) == (0.0, 0.0):
            raise AssertionError('probe assertion failed')
        if not not {signal.SIGALRM, signal.SIGPROF, signal.SIGTERM} & signal.sigpending():
            raise AssertionError('probe assertion failed')
        if not not {signal.SIGALRM, signal.SIGPROF} & signal.pthread_sigmask(signal.SIG_BLOCK, set()):
            raise AssertionError('probe assertion failed')
        if not signal.getsignal(watched) is old_handler:
            raise AssertionError('probe assertion failed')
        if not deliveries == ([] if kind == 'owned_expiry' else [signal.SIGTERM]):
            raise AssertionError(deliveries)
        print(json.dumps(dict(kind=kind, complete=True, deliveries=deliveries)))


def invalid_caps_probe(state):
    import fcntl
    deliveries = []
    reserved = {signal.SIGALRM, signal.SIGPROF, signal.SIGINT, signal.SIGTERM}
    def handler(number, frame):
        deliveries.append(number)
    for sig in reserved:
        signal.signal(sig, handler)
    if state == 'foreign':
        signal.pthread_sigmask(signal.SIG_BLOCK, reserved)
        for sig in reserved:
            os.kill(os.getpid(), sig)
        signal.setitimer(signal.ITIMER_REAL, 10, 2)
        signal.setitimer(signal.ITIMER_PROF, 10, 2)
    with tempfile.TemporaryDirectory(prefix='rss-invalid-caps-') as temp:
        root = Path(temp)
        for filename in ('strict_cleanup.py', 'lossless_log.py'):
            shutil.copyfile(BASE / filename, root / filename)
        for filename in ('rss_telemetry.py', 'supervise_multiroot.py'):
            shutil.copyfile(HERE / filename, root / filename)
        spec = importlib.util.spec_from_file_location('caps_supervisor', root / 'supervise_multiroot.py')
        module = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(root))
        try:
            spec.loader.exec_module(module)
        finally:
            sys.path.pop(0)
        required = ('wall_seconds', 'cleanup_seconds', 'cpu_seconds', 'file_bytes',
                    'tree_bytes', 'log_bytes', 'max_entries', 'per_process_as_bytes',
                    'per_process_cpu_seconds', 'rss_bytes')
        optional = ('raw_log_bytes', 'watch_tree_bytes', 'min_free_disk_bytes')
        variants = []
        for key in required:
            caps = fixture_caps(); del caps[key]
            variants.append(('missing '+key, caps))
        for key in required + optional:
            bad_values = [None, 'invalid', True, float('nan'), float('inf'), float('-inf'), -1]
            if key != 'min_free_disk_bytes':
                bad_values.append(0)
            if key not in ('wall_seconds', 'cleanup_seconds', 'cpu_seconds'):
                bad_values.extend([1.0, sys.maxsize + 1])
            else:
                bad_values.append(10 ** 1000)
            for bad in bad_values:
                caps = fixture_caps(); caps[key] = bad
                variants.append(('malformed '+key+' '+repr(bad), caps))
        caps = fixture_caps(); caps['wall_seconds'] = caps['cleanup_seconds'] = 1e308
        variants.append(('nonfinite combined deadline', caps))
        for label, caps in variants:
            before_mask = signal.pthread_sigmask(signal.SIG_BLOCK, set())
            before_pending = signal.sigpending()
            before_handlers = {sig: signal.getsignal(sig) for sig in reserved}
            before_timers = {timer: signal.getitimer(timer) for timer in (signal.ITIMER_REAL, signal.ITIMER_PROF)}
            with patch.object(module.subprocess, 'Popen', side_effect=AssertionError('invalid caps must not start a worker')):
                try:
                    module.execute(['must-not-start'], root/'run', root/'lock', caps, {}, {})
                except ValueError as error:
                    if not str(error).startswith('V2 finite'):
                        raise AssertionError((label, str(error)))
                else:
                    raise AssertionError(('invalid caps accepted', label))
            if signal.pthread_sigmask(signal.SIG_BLOCK, set()) != before_mask or signal.sigpending() != before_pending:
                raise AssertionError(('signal state changed', label))
            if {sig: signal.getsignal(sig) for sig in reserved} != before_handlers or deliveries:
                raise AssertionError(('handlers or deliveries changed', label))
            for timer, before in before_timers.items():
                after = signal.getitimer(timer)
                if before == (0.0, 0.0):
                    if after != before:raise AssertionError(('timer changed', label, before, after))
                elif not (0 < after[0] <= before[0] and after[1] == before[1]):
                    raise AssertionError(('foreign timer changed', label, before, after))
            if (root/'run').exists() or (root/'lock').exists():
                raise AssertionError(('invalid entry created output or lock', label))
            fd = os.open(root/'lock-check', os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with patch.object(module.subprocess, 'Popen', side_effect=AssertionError('invalid caps must not start a worker')):
                    try:
                        module.execute(['must-not-start'], root/'run', root/'lock-check', caps, {}, {})
                    except ValueError:
                        pass
                    else:
                        raise AssertionError(('invalid caps accepted with caller lock', label))
                other = os.open(root/'lock-check', os.O_RDWR)
                try:
                    try:
                        fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        pass
                    else:
                        raise AssertionError(('caller lock was released', label))
                finally:
                    os.close(other)
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN); os.close(fd)
        for timer in (signal.ITIMER_REAL, signal.ITIMER_PROF):
            signal.setitimer(timer, 0)
        for sig in reserved:
            if sig in signal.sigpending():signal.sigtimedwait({sig}, 0)
        signal.pthread_sigmask(signal.SIG_SETMASK, set())
        print(json.dumps(dict(kind='invalid_caps', state=state, cases=len(variants), preserved=True)))

class SignalOwnership(unittest.TestCase):

    def child(self, *args):
        command = [sys.executable] + (['-O'] if not __debug__ else []) + [str(Path(__file__).resolve()), '--probe', *args]
        result = subprocess.run(command, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout.strip().splitlines()[-1])

    def test_invalid_caps_preserve_clean_entry_state(self):
        self.assertTrue(self.child('invalid_caps', 'clean')['preserved'])

    def test_invalid_caps_preserve_foreign_signals_timers_and_lock(self):
        self.assertTrue(self.child('invalid_caps', 'foreign')['preserved'])

    def test_reject_blocked_watchdogs_without_mutation(self):
        for sig in ('SIGALRM', 'SIGPROF'):
            with self.subTest(sig=sig):
                self.assertTrue(self.child('blocked', sig)['preserved'])

    def test_reject_preexisting_pending_without_consuming(self):
        for sig in ('SIGALRM', 'SIGPROF', 'SIGINT', 'SIGTERM'):
            with self.subTest(sig=sig):
                self.assertTrue(self.child('pending', sig)['preserved'])

    def test_reject_active_timers_without_cancelling(self):
        for sig in ('SIGALRM', 'SIGPROF'):
            with self.subTest(sig=sig):
                self.assertTrue(self.child('active', sig)['preserved'])

    def test_arriving_external_pending_delivered_to_original_handler(self):
        for sig in ('SIGALRM', 'SIGPROF', 'SIGINT', 'SIGTERM'):
            with self.subTest(sig=sig):
                self.assertTrue(self.child('arriving', sig)['preserved'])

    def test_owned_pending_expiry_is_drained_before_handler_restore(self):
        self.assertTrue(self.child('owned_expiry')['complete'])

    def test_external_terminal_pending_is_not_drained(self):
        self.assertEqual(self.child('external_terminal')['deliveries'], [signal.SIGTERM])
if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--probe':
        if sys.argv[2] == 'invalid_caps':
            invalid_caps_probe(sys.argv[3])
        elif sys.argv[2] in ('owned_expiry', 'external_terminal'):
            late_probe(sys.argv[2])
        else:
            probe(*sys.argv[2:])
    else:
        unittest.main(verbosity=2)
