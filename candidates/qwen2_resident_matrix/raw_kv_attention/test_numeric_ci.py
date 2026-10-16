"""Cold wrapper checks only: no native math, compilation, or numerical owner."""
from contextlib import ExitStack, redirect_stdout
import copy
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from . import run_numeric_ci as runner


def receipt():
    cases = []
    for tokens in (1, 2):
        requests = 192 * tokens * (tokens + 1) // 2
        counts = {name: 1 if name.startswith('owner_') else requests
                  for name in runner.MATRIX_COUNTERS}
        cases.append(dict(tokens=tokens, status='PASS', kv_requests=requests,
            unique_ddr_reads=32 * tokens, hits=requests - 32 * tokens,
            accepted_matrix=counts, scalar_operations=100, output_words=1536 * tokens))
    return dict(status='PASS_BOUNDED_NUMERIC', cases=cases,
        fault=dict(tokens=1, status='PASS', revoked_reply_arithmetic_operations=0,
                   core_replies=1, output_published=False), arithmetic_executed=True,
        hardware_simulation=False, public_profiles_executed=False,
        model_ticks_are_hardware_cycles=False, native_acceptance='UNCHANGED_FAIL_POLICY_PENDING')


class NumericCI(unittest.TestCase):
    def exercise(self, tmp, *, child=None, snapshot=None, library_drift=False, env=None):
        root = Path(tmp)
        native = root / 'private-native'
        native.mkdir()
        library = native / 'matrix.so'
        library.write_bytes(b'not executable: cold fixture only')
        (native / 'compile.json').write_text('{}')
        environment = {'MATRIX_SERVICE_LIBRARY': str(library),
                       'MATRIX_SERVICE_COMPILE_RECEIPT': str(native / 'compile.json')}
        if env:
            environment.update(env)
        calls = []
        def fake_child(args, **kwargs):
            calls.append((args, kwargs))
            if library_drift:
                library.write_bytes(b'changed cold fixture')
            if child:
                return child(args, **kwargs)
            kwargs['log'].write(json.dumps(receipt()).encode())
            return 0
        frozen = {'scripts/example.py': '0' * 64}
        with ExitStack() as stack:
            stack.enter_context(patch.object(runner, 'source_snapshot', side_effect=snapshot,
                                             return_value=frozen))
            prep = stack.enter_context(patch.object(runner.numeric_prepare, 'check'))
            strict = stack.enter_context(patch.object(runner.recipe, 'from_environment', return_value=library))
            stack.enter_context(patch.object(runner.recipe, 'build', side_effect=AssertionError('never build')))
            stack.enter_context(patch.object(runner, 'run_group', side_effect=fake_child))
            out = root / 'evidence'
            code, summary = runner.run(out, environment)
        return code, summary, out, calls, prep, strict

    def test_complete_strict_pass_schema(self):
        expected = receipt()
        self.assertEqual(runner.validate_child(json.dumps(expected).encode()), expected)

    def test_incomplete_duplicate_extra_or_bulk_schema_rejected(self):
        variants = []
        for field in ('cases', 'fault', 'arithmetic_executed', 'native_acceptance'):
            value = receipt(); del value[field]; variants.append(value)
        value = receipt(); value['cases'].pop(); variants.append(value)
        value = receipt(); value['cases'].reverse(); variants.append(value)
        value = receipt(); value['cases'][1]['tokens'] = 1; variants.append(value)
        value = receipt(); value['fault']['status'] = 'FAIL'; variants.append(value)
        value = receipt(); value['fault']['output_published'] = True; variants.append(value)
        value = receipt(); value['fault']['revoked_reply_arithmetic_operations'] = 1; variants.append(value)
        value = receipt(); value['cases'][0]['accepted_matrix']['payload'] = [1] * 8; variants.append(value)
        value = receipt(); value['payload'] = 'private'; variants.append(value)
        value = receipt(); value['hardware_simulation'] = 0; variants.append(value)
        value = receipt(); value['cases'][0]['kv_requests'] = True; variants.append(value)
        value = receipt(); value['cases'][0]['scalar_operations'] = float('nan'); variants.append(value)
        for value in variants:
            with self.subTest(value=value), self.assertRaises((ValueError, UnicodeError)):
                runner.validate_child(json.dumps(value).encode())
        for raw in (b'{}\n{}', b'payload prefix\n' + json.dumps(receipt()).encode(),
                    b'{"status":1,"status":2}', b'\xff', b'x' * (runner.MAX_CHILD_BYTES + 1)):
            with self.subTest(raw=raw[:30]), self.assertRaises((ValueError, UnicodeError)):
                runner.validate_child(raw)

    def test_missing_environment_cannot_launch_or_pass(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner, 'run_group') as child, \
             patch.object(runner.recipe, 'from_environment') as strict:
            code, summary = runner.run(Path(tmp) / 'evidence', {})
            self.assertEqual((code, summary['status']), (2, 'NOT_RUN'))
            self.assertFalse(summary['numerical_child_started'])
            self.assertEqual(set(p.name for p in (Path(tmp) / 'evidence').iterdir()), set(runner.OUTPUTS))
            child.assert_not_called(); strict.assert_not_called()

    def test_missing_library_file_is_not_run(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner, 'run_group') as child:
            code, summary = runner.run(Path(tmp) / 'evidence', {
                'MATRIX_SERVICE_LIBRARY': str(Path(tmp) / 'absent.so'),
                'MATRIX_SERVICE_COMPILE_RECEIPT': str(Path(tmp) / 'compile.json')})
            self.assertEqual((code, summary['status']), (2, 'NOT_RUN'))
            child.assert_not_called()

    def test_pass_invokes_one_child_and_strict_validation_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, summary, out, calls, prep, strict = self.exercise(tmp, env={
                'PYTHONPATH': '/private/module', 'PYTHONHOME': '/private/python', 'PYTHONOPTIMIZE': '2'})
            self.assertEqual((code, summary['status']), (0, 'PASS_BOUNDED_NUMERIC'))
            self.assertEqual(len(calls), 1)
            args, kw = calls[0]
            self.assertEqual(args, [sys.executable, '-m', runner.CHILD_MODULE])
            self.assertEqual(kw['grace'], 5)
            self.assertGreater(kw['timeout'], 0)
            self.assertLessEqual(kw['timeout'], 114)
            for name in ('PYTHONPATH', 'PYTHONHOME', 'PYTHONOPTIMIZE'):
                self.assertNotIn(name, kw['env'])
            self.assertTrue(kw['log'].closed)
            prep.assert_called_once(); self.assertEqual(strict.call_count, 2)
            evidence = json.loads((out / 'source_hashes.json').read_text())
            self.assertTrue(evidence['inputs_unchanged'])
            self.assertEqual(set(evidence), {'schema', 'sources', 'library_sha256', 'receipt_sha256', 'inputs_unchanged'})
            self.assertEqual(set(p.name for p in out.iterdir()), set(runner.OUTPUTS))
            self.assertNotIn(tmp, ''.join(p.read_text() for p in out.iterdir()))

    def test_nonzero_child_even_with_pass_cannot_succeed(self):
        def child(args, **kw):
            kw['log'].write(json.dumps(receipt()).encode()); return 2
        with tempfile.TemporaryDirectory() as tmp:
            code, summary, *_ = self.exercise(tmp, child=child)
            self.assertEqual(code, 1)
            self.assertEqual(summary['reason'], 'child_exit_nonzero')
            self.assertNotIn('result', summary)

    def test_raw_payload_and_exception_never_escape(self):
        private = '/secret/private TOKEN=credential raw_tensor=[1,2,3]'
        for mode in ('log', 'exception'):
            def child(args, **kw):
                if mode == 'exception':
                    raise RuntimeError(private)
                kw['log'].write((private * 10000).encode()); return 0
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                code, summary, out, calls, *_ = self.exercise(tmp, child=child)
                self.assertEqual(code, 1)
                self.assertTrue(calls[0][1]['log'].closed)
                raw = json.dumps(summary) + ''.join(p.read_text() for p in out.iterdir())
                for secret in ('/secret', 'credential', 'raw_tensor', tmp):
                    self.assertNotIn(secret, raw)
                self.assertLess(len(raw.encode()), 4096)

    def test_source_and_library_hash_drift_fail_closed(self):
        for mode in ('source', 'library'):
            calls = 0
            def snapshot():
                nonlocal calls
                calls += 1
                return {'scripts/example.py': ('1' if calls >= 3 else '0') * 64}
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                code, summary, out, *_ = self.exercise(tmp,
                    snapshot=snapshot if mode == 'source' else None, library_drift=mode == 'library')
                self.assertEqual((code, summary['status'], summary['reason']), (1, 'FAIL', 'input_drift'))
                self.assertFalse(json.loads((out / 'source_hashes.json').read_text())['inputs_unchanged'])

    def test_receipt_must_be_adjacent_and_repository_keys_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); library = root / 'library.so'; library.write_bytes(b'cold')
            foreign = root / 'other.json'; foreign.write_text('{}')
            with self.assertRaises(runner.ReceiptError):
                runner.library_snapshot({'MATRIX_SERVICE_LIBRARY': str(library),
                                         'MATRIX_SERVICE_COMPILE_RECEIPT': str(foreign)})
        for name in ('/secret', '../secret', 'path/../secret', 'path//secret', 'name\nprivate'):
            with self.subTest(name=name), self.assertRaises(runner.ReceiptError):
                runner.repository_path(name)

    def test_cli_setup_error_is_sanitized(self):
        output = io.StringIO()
        with patch.object(runner, 'run', side_effect=ValueError('/private token=secret raw_tensor=[7]')), redirect_stdout(output):
            self.assertEqual(runner.main(['--out', '/private/not-used']), 1)
        data = output.getvalue()
        self.assertNotIn('/private', data); self.assertNotIn('secret', data)
        self.assertEqual(json.loads(data)['status'], 'FAIL')

    def test_child_timeout_and_sigterm_restore_handlers(self):
        old_alarm = signal.getsignal(signal.SIGALRM)
        old_term = signal.getsignal(signal.SIGTERM)
        for mode in ('deadline', 'sigterm'):
            def child(args, **kw):
                if mode == 'sigterm':
                    os.kill(os.getpid(), signal.SIGTERM)
                raise subprocess.TimeoutExpired(args, kw['timeout'])
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp, \
                 patch.object(runner, 'TOTAL_SECONDS', .4), \
                 patch.object(runner, 'CLEANUP_SECONDS', .1), \
                 patch.object(runner, 'RECEIPT_SECONDS', .05):
                started = time.monotonic()
                code, summary, out, calls, *_ = self.exercise(tmp, child=child)
                self.assertLess(time.monotonic() - started, 2)
                self.assertEqual(code, 1)
                self.assertEqual(summary['status'], 'TIMEOUT' if mode == 'deadline' else 'INTERRUPTED')
                self.assertTrue(calls[0][1]['log'].closed)
                self.assertNotIn('result', summary)
                self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0., 0.))
                self.assertEqual(signal.getsignal(signal.SIGALRM), old_alarm)
                self.assertEqual(signal.getsignal(signal.SIGTERM), old_term)

    def test_wrapper_real_group_cleanup_survives_initial_delay(self):
        # Integrated regression: formerly the late outer alarm interrupted the
        # helper's TERM-to-KILL grace, leaking the TERM-resistant child group.
        real_group = runner.run_group
        original_mkdir = Path.mkdir
        def delayed_mkdir(path, *args, **kwargs):
            if path.name == 'evidence':
                time.sleep(.08)
            return original_mkdir(path, *args, **kwargs)
        with tempfile.TemporaryDirectory() as tmp:
            pidfile = Path(tmp) / 'group.pid'
            script = ('import os,signal,sys,time; '
                      'signal.signal(signal.SIGTERM,signal.SIG_IGN); '
                      'open(sys.argv[1],"w").write(str(os.getpid())); time.sleep(30)')
            def child(args, **kw):
                self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0., 0.))
                return real_group([sys.executable, '-c', script, str(pidfile)], **kw)
            try:
                with patch.object(runner, 'TOTAL_SECONDS', .8), \
                     patch.object(runner, 'CLEANUP_SECONDS', .3), \
                     patch.object(runner, 'RECEIPT_SECONDS', .05), \
                     patch.object(Path, 'mkdir', delayed_mkdir):
                    started = time.monotonic()
                    code, summary, out, calls, *_ = self.exercise(tmp, child=child)
                    elapsed = time.monotonic() - started
                self.assertEqual((code, summary['status']), (1, 'TIMEOUT'))
                self.assertLess(elapsed, 2)
                self.assertEqual(len(calls), 1)
                self.assertTrue(calls[0][1]['log'].closed)
                self.assertNotIn('result', summary)
                self.assertEqual(set(p.name for p in out.iterdir()), set(runner.OUTPUTS))
                pid = int(pidfile.read_text())
                with self.assertRaises(ProcessLookupError):
                    os.kill(pid, 0)
                with self.assertRaises(ProcessLookupError):
                    os.killpg(pid, 0)
            finally:
                # A failing regression must not itself leave a sleeping process.
                if pidfile.exists():
                    try:
                        os.killpg(int(pidfile.read_text()), signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    def test_final_hash_and_receipt_io_share_hard_deadline(self):
        # These are injected sleeps around cold fixtures, never numerical work.
        calls = 0
        def snapshot():
            nonlocal calls
            calls += 1
            if calls == 4:
                time.sleep(5)
            return {'scripts/example.py': '0' * 64}
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner, 'TOTAL_SECONDS', .4), \
             patch.object(runner, 'CLEANUP_SECONDS', .1), patch.object(runner, 'RECEIPT_SECONDS', .05):
            started = time.monotonic()
            code, summary, *_ = self.exercise(tmp, snapshot=snapshot)
            self.assertEqual((code, summary['status']), (1, 'TIMEOUT'))
            self.assertNotIn('result', summary)
            self.assertLess(time.monotonic() - started, 2)
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner, 'TOTAL_SECONDS', .2), \
             patch.object(runner, 'CLEANUP_SECONDS', .05), patch.object(runner, 'RECEIPT_SECONDS', .05), \
             patch.object(runner, 'save', side_effect=lambda *args: time.sleep(5)):
            started = time.monotonic()
            with self.assertRaises(TimeoutError):
                runner.run(Path(tmp) / 'evidence', {})
            self.assertLess(time.monotonic() - started, 2)
            self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0., 0.))

    def test_real_process_group_timeout_cleanup_under_two_seconds(self):
        # Pure sleeping Python processes; no wrapper numerical child or CDLL.
        with tempfile.TemporaryDirectory() as tmp:
            pidfile = Path(tmp) / 'descendant.pid'
            grandchild = ('import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(30)')
            code = ('import subprocess,sys,time; p=subprocess.Popen([sys.executable,"-c",' + repr(grandchild) + ']); '
                    'open(sys.argv[1],"w").write(str(p.pid)); time.sleep(30)')
            started = time.monotonic()
            with tempfile.TemporaryFile() as log, self.assertRaises(subprocess.TimeoutExpired):
                runner.run_group([sys.executable, '-c', code, str(pidfile)], cwd=tmp,
                                 env=dict(os.environ), log=log, timeout=0.15, grace=0.1)
            self.assertLess(time.monotonic() - started, 2)
            pid = int(pidfile.read_text())
            # A killed orphan may briefly be a zombie until the system reaps it.
            stat = Path('/proc') / str(pid) / 'stat'
            deadline = time.monotonic() + 1
            while stat.exists() and stat.read_text().split()[2] != 'Z' and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue(not stat.exists() or stat.read_text().split()[2] == 'Z')

    def test_real_closure_snapshot_is_repo_relative_hash_only(self):
        values = runner.source_snapshot()
        self.assertEqual(len(values), 58)
        for name in (*runner.EXTRA_INPUTS, *runner.recipe.SOURCES,
                     'scripts/build_shared_matrix_recipe.py',
                     'candidates/qwen2_resident_matrix/raw_kv/run_unit.py'):
            self.assertIn(name, values)
        self.assertTrue(all(not Path(name).is_absolute() and len(sha) == 64 for name, sha in values.items()))


if __name__ == '__main__':
    unittest.main()
