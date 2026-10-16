"""Cold calibration schema/deadline checks; no native arithmetic or compilation."""
from contextlib import ExitStack, redirect_stdout
import copy
import io
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from . import run_calibration_ci as runner
from . import run_numeric_ci as common
from .streaming import profile

SOURCES = {'scripts/cold-fixture.py': '0' * 64}
NATIVE = {'library_sha256': '1' * 64, 'receipt_sha256': '2' * 64}


def receipt(sources=SOURCES, native=NATIVE):
    def digest(kind, count, size):
        return dict(version='raw-kv-stream-v1', kind=kind, count=count, bytes=count * size, sha256='3' * 64)
    profiles = []
    for tokens in (4, 8):
        work = profile(tokens); passes = []
        for loan in (False, True):
            writes = digest('memory-requests', work['output_writes'], 90)
            writes.update(reads=0, writes=work['output_writes'],
                          metadata=digest('core-metadata', work['output_writes'], 17))
            counts = {name: 1 if name.startswith('owner_') else
                work['matrix_groups'] if name in ('normal_groups', 'normal_done') else work['matrix_packets']
                for name in common.MATRIX_COUNTERS}
            value = dict(loan=loan, seconds=.12345678912345678, events=100,
                scalar=digest('scalar', work['scalar_total_no_cutoff'], 14),
                matrix=digest('matrix-results', work['matrix_packets'], 16398),
                core=digest('core-metadata', work['core_memory_requests'], 17), writes=writes,
                accepted_matrix=counts, useful_macs=work['useful_fmas'], executed_macs=work['native_fmas'],
                scalar_checkpoints=work['scalar_total_no_cutoff'],
                ddr_read_count=work['loan_ddr_reads'] if loan else work['q_reads'] + work['kv_reads'],
                ddr_write_count=work['output_writes'])
            if loan:
                value['kv'] = dict(core_requests=work['kv_reads'], ddr_requests=work['unique_kv_lines'],
                    hits=work['kv_hits'], fills=work['unique_kv_lines'], releases=1)
            passes.append(value)
        nbytes = 7 * 12 * (tokens * (tokens + 1) // 2) * 4 + 3 * tokens * 12 * 4 + 2 * tokens * 1536 * 4
        profiles.append(dict(tokens=tokens, status='PASS', reference_seconds=.12345678912345678,
                             reference_bytes=nbytes, work=work, passes=passes))
    return dict(status='PASS_CALIBRATION_ONLY', profiles=profiles, m128_executed=False,
        hardware_simulation=False, model_ticks_are_hardware_cycles=False, process_peak_rss_kib=1234567,
        source_manifest_sha256=runner.manifest_sha256(sources), native_hashes=dict(native), inputs_unchanged=True)


class CalibrationCI(unittest.TestCase):
    def test_complete_schema_and_compact_child_receipt(self):
        value = receipt(); raw = json.dumps(value, sort_keys=True).encode()
        self.assertLessEqual(len(raw), common.MAX_CHILD_BYTES)
        self.assertEqual(runner.validate_child(raw, expected_sources=SOURCES, expected_native=NATIVE), value)

    def test_schema_rejects_m128_missing_drift_payload_and_false_equality(self):
        def validate(value):
            runner.validate_child(json.dumps(value).encode(), expected_sources=SOURCES, expected_native=NATIVE)
        changes = []
        for field, value in (('m128_executed', True), ('hardware_simulation', 0), ('inputs_unchanged', False),
                             ('source_manifest_sha256', 'f' * 64), ('process_peak_rss_kib', True),
                             ('raw_tensor', [1, 2]), ('status', 'PASS_BOUNDED_NUMERIC')):
            changed = receipt(); changed[field] = value; changes.append(changed)
        changed = receipt(); changed['native_hashes']['library_sha256'] = 'f' * 64; changes.append(changed)
        changed = receipt(); changed['profiles'].reverse(); changes.append(changed)
        changed = receipt(); changed['profiles'].pop(); changes.append(changed)
        for field, value in (('tokens', 128), ('reference_bytes', 1), ('reference_seconds', float('nan'))):
            changed = receipt(); changed['profiles'][0][field] = value; changes.append(changed)
        changed = receipt(); changed['profiles'][0]['work']['hardware_cycles'] = 0; changes.append(changed)
        changed = receipt(); changed['profiles'][0]['passes'].pop(); changes.append(changed)
        for field, value in (('loan', 1), ('ddr_read_count', 1), ('events', 10**12), ('raw_trace', 'private')):
            changed = receipt(); changed['profiles'][0]['passes'][1][field] = value; changes.append(changed)
        for name in ('scalar', 'matrix', 'core', 'writes'):
            changed = receipt(); changed['profiles'][0]['passes'][1][name]['sha256'] = 'f' * 64; changes.append(changed)
            changed = receipt(); changed['profiles'][0]['passes'][1][name]['bytes'] += 1; changes.append(changed)
        changed = receipt(); changed['profiles'][0]['passes'][1]['kv']['releases'] = True; changes.append(changed)
        for i, changed in enumerate(changes):
            with self.subTest(mutation=i), self.assertRaises(ValueError):
                validate(changed)
        for raw in (b'{}\n{}', b'{"status":0,"status":1}', b'x' * (common.MAX_CHILD_BYTES + 1)):
            with self.assertRaises(ValueError):
                runner.validate_child(raw, expected_sources=SOURCES, expected_native=NATIVE)

    def test_expired_and_too_small_deadlines_never_start_or_create_files(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(common, 'run') as child:
            for seconds in (-1, 0, 1, 6):
                out = Path(tmp) / str(seconds)
                code, result = runner.run(out, deadline_ns=time.monotonic_ns() + int(seconds * 1e9), environ={})
                self.assertEqual((code, result['status']), (2, 'NOT_RUN'))
                self.assertFalse(result['numerical_child_started']); self.assertFalse(out.exists())
            child.assert_not_called()
        for invalid in (True, 0, -1, 1.5, 1 << 63):
            with self.assertRaises(ValueError):
                runner.run(Path('/unused'), deadline_ns=invalid)

    def test_shared_absolute_deadline_and_exact_child_are_forwarded(self):
        deadline = time.monotonic_ns() + 20_000_000_000
        with patch.object(common, 'run', return_value=(2, {})) as shared:
            runner.run(Path('/unused'), deadline_ns=deadline, environ={})
        args = shared.call_args.kwargs
        self.assertEqual(args['deadline_ns'], deadline)
        self.assertGreater(args['total_seconds'], 6)
        self.assertLessEqual(args['total_seconds'], 20)
        self.assertEqual(args['child_module'], runner.CHILD_MODULE)
        self.assertEqual(args['child_args'], ('--calibrate',))
        self.assertIs(args['snapshot'], runner.source_snapshot)

    def exercise(self, tmp, *, child=None, deadline_ns=None):
        root = Path(tmp); library = root / 'fixture.so'; library.write_bytes(b'cold only')
        native_receipt = root / 'compile.json'; native_receipt.write_text('{}')
        env = {'MATRIX_SERVICE_LIBRARY': str(library), 'MATRIX_SERVICE_COMPILE_RECEIPT': str(native_receipt)}
        native = common.library_snapshot(env)[2]
        def execute(args, **kwargs):
            if child:
                return child(args, **kwargs)
            kwargs['log'].write(json.dumps(receipt(SOURCES, native)).encode()); return 0
        with ExitStack() as stack:
            stack.enter_context(patch.object(runner.profile_numeric, 'source_snapshot', return_value=SOURCES))
            stack.enter_context(patch.object(runner, 'source_snapshot', return_value=dict(SOURCES)))
            stack.enter_context(patch.object(common.numeric_prepare, 'check'))
            stack.enter_context(patch.object(common.recipe, 'from_environment', return_value=library))
            stack.enter_context(patch.object(common.recipe, 'build', side_effect=AssertionError('never build')))
            launched = stack.enter_context(patch.object(common, 'run_group', side_effect=execute))
            code, result = runner.run(root / 'evidence', deadline_ns=deadline_ns or time.monotonic_ns() + 20_000_000_000, environ=env)
        return code, result, launched

    def test_shared_runner_pass_keeps_two_safe_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, result, launched = self.exercise(tmp)
            self.assertEqual((code, result['status']), (0, 'PASS_CALIBRATION_ONLY'))
            launched.assert_called_once()
            out = Path(tmp) / 'evidence'
            self.assertEqual(set(p.name for p in out.iterdir()), set(common.OUTPUTS))
            self.assertNotIn(tmp, ''.join(p.read_text() for p in out.iterdir()))
            self.assertTrue(json.loads((out / 'source_hashes.json').read_text())['inputs_unchanged'])
            self.assertLess(result['total_budget_seconds'], 20)
            self.assertEqual(common.MAX_CHILD_BYTES, 8192)
            self.assertEqual(common.TOTAL_SECONDS, 120)

    def test_calibration_timeout_real_helper_cleans_term_resistant_child(self):
        real_group = common.run_group
        with tempfile.TemporaryDirectory() as tmp:
            pidfile = Path(tmp) / 'child.pid'
            code = ('import os,signal,sys,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); '
                    'open(sys.argv[1],"w").write(str(os.getpid())); time.sleep(30)')
            def child(args, **kwargs):
                self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0., 0.))
                return real_group([sys.executable, '-c', code, str(pidfile)], **kwargs)
            try:
                with patch.object(common, 'CLEANUP_SECONDS', .3), patch.object(common, 'RECEIPT_SECONDS', .05):
                    start = time.monotonic()
                    rc, summary, _ = self.exercise(tmp, child=child, deadline_ns=time.monotonic_ns() + 800_000_000)
                self.assertEqual((rc, summary['status']), (1, 'TIMEOUT'))
                self.assertLess(time.monotonic() - start, 2)
                with self.assertRaises(ProcessLookupError):
                    os.killpg(int(pidfile.read_text()), 0)
            finally:
                if pidfile.exists():
                    try: os.killpg(int(pidfile.read_text()), signal.SIGKILL)
                    except ProcessLookupError: pass

    def test_extended_source_closure_and_safe_cli_error(self):
        sources = runner.source_snapshot()
        self.assertEqual(len(sources), 66)
        for name in runner.WRAPPER_INPUTS:
            self.assertIn(name, sources)
        output = io.StringIO()
        with patch.object(runner, 'run', side_effect=RuntimeError('/private token=secret payload=[1]')), redirect_stdout(output):
            self.assertEqual(runner.main(['--out', '/unused', '--deadline-ns', '1']), 1)
        self.assertNotIn('/private', output.getvalue()); self.assertNotIn('secret', output.getvalue())
        self.assertEqual(json.loads(output.getvalue())['status'], 'FAIL')


if __name__ == '__main__':
    unittest.main()
