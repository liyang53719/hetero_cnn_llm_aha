"""Cold M128 wrapper tests: synthetic receipts and sleeping children only."""
from contextlib import ExitStack, redirect_stdout
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

from . import run_m128_ci as runner
from . import run_numeric_ci as common
from . import run_calibration_ci as calibration
from .streaming import profile

SOURCES = {'scripts/cold-fixture.py': '0' * 64}
NATIVE = {'library_sha256': '1' * 64, 'receipt_sha256': '2' * 64}


def receipt(sources=SOURCES, native=NATIVE):
    def digest(kind, count, size):
        return dict(version='raw-kv-stream-v1', kind=kind, count=count, bytes=count * size, sha256='3' * 64)
    work = profile(128); passes = []
    for loan in (False, True):
        writes = digest('memory-requests', work['output_writes'], 90)
        writes.update(reads=0, writes=work['output_writes'],
                      metadata=digest('core-metadata', work['output_writes'], 17))
        counts = {name: 1 if name.startswith('owner_') else
            work['matrix_groups'] if name in ('normal_groups', 'normal_done') else work['matrix_packets']
            for name in common.MATRIX_COUNTERS}
        value = dict(loan=loan, seconds=1234.56789, events=100,
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
    case = dict(tokens=128, status='PASS', reference_seconds=1.25, reference_bytes=4365312,
                work=work, passes=passes)
    return dict(status=runner.PASS_STATUS, profiles=[case], m128_executed=True,
        hardware_simulation=False, model_ticks_are_hardware_cycles=False, process_peak_rss_kib=1234567,
        source_manifest_sha256=calibration.manifest_sha256(sources), native_hashes=dict(native), inputs_unchanged=True)


def progress(phase='complete'):
    work = profile(128)
    active = phase in ('direct', 'loan', 'complete')
    return dict(schema=1, status='PROGRESS', phase=phase, tokens=128,
        loan=runner.PHASE_LOAN[phase], events=100 if active else 0,
        scalar_operations=work['scalar_total_no_cutoff'] if active else 0,
        matrix_packets=work['matrix_packets'] if active else 0, elapsed_seconds=.1, sequence=5)


class M128CI(unittest.TestCase):
    def test_m128_exact_receipt_and_old_validators_stay_closed(self):
        value = receipt(); raw = json.dumps(value).encode()
        self.assertLessEqual(len(raw), common.MAX_CHILD_BYTES)
        self.assertEqual(runner.validate_child(raw, expected_sources=SOURCES, expected_native=NATIVE), value)
        with self.assertRaises(ValueError):
            common.validate_child(raw)
        with self.assertRaises(ValueError):
            calibration.validate_child(raw, expected_sources=SOURCES, expected_native=NATIVE)
        self.assertEqual(common.TOTAL_SECONDS, 120)
        self.assertEqual(common.OUTPUTS, ('summary.json', 'source_hashes.json'))

    def test_m128_receipt_rejects_false_pass_scope_counts_and_payload(self):
        changes = []
        for field, value in (('status', 'PASS_CALIBRATION_ONLY'), ('m128_executed', False),
                ('hardware_simulation', 0), ('raw_tensor', [1]), ('inputs_unchanged', False),
                ('source_manifest_sha256', 'f' * 64)):
            changed = receipt(); changed[field] = value; changes.append(changed)
        changed = receipt(); changed['profiles'] *= 2; changes.append(changed)
        changed = receipt(); changed['native_hashes']['library_sha256'] = 'f' * 64; changes.append(changed)
        for field, value in (('tokens', 8), ('reference_bytes', 1), ('reference_seconds', 2401)):
            changed = receipt(); changed['profiles'][0][field] = value; changes.append(changed)
        for field, value in (('loan', 1), ('ddr_read_count', 1), ('seconds', float('nan')), ('events', True)):
            changed = receipt(); changed['profiles'][0]['passes'][1][field] = value; changes.append(changed)
        for key in ('scalar', 'matrix', 'core', 'writes'):
            changed = receipt(); changed['profiles'][0]['passes'][1][key]['sha256'] = 'f' * 64; changes.append(changed)
            changed = receipt(); changed['profiles'][0]['passes'][1][key]['bytes'] += 1; changes.append(changed)
        for changed in changes:
            with self.subTest(changed=changes.index(changed)), self.assertRaises(ValueError):
                runner.validate_child(json.dumps(changed).encode(), expected_sources=SOURCES, expected_native=NATIVE)

    def test_progress_strict_finite_bounds_and_no_pass_authority(self):
        for phase in runner.PHASE_LOAN:
            value = progress(phase)
            self.assertEqual(runner.validate_progress(json.dumps(value).encode()), value)
        for field, value in (('schema', True), ('tokens', 4), ('status', 'PASS'), ('phase', '/private'),
                ('loan', 1), ('events', -1), ('scalar_operations', 10**12), ('matrix_packets', True),
                ('elapsed_seconds', float('inf')), ('elapsed_seconds', 2401), ('sequence', 0),
                ('raw_payload', 'secret'), ('events', 0)):
            changed = progress(); changed[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                runner.validate_progress(json.dumps(changed).encode())
        changed = progress('reference'); changed['matrix_packets'] = 1
        with self.assertRaises(ValueError): runner.validate_progress(json.dumps(changed).encode())
        for raw in (b'{"schema":1,"schema":1}', b'x' * 1025, b'{}\n{}'):
            with self.assertRaises(ValueError): runner.validate_progress(raw)

    def test_progress_reader_rejects_symlinks_fifo_bulk_and_redacts_final_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); path = out / 'progress.json'; other = out / 'private'
            other.write_text('token=secret raw_tensor=[1]')
            path.symlink_to(other)
            with self.assertRaises(OSError): runner.read_progress(path)
            path.unlink(); os.mkfifo(path)
            with self.assertRaises(ValueError): runner.read_progress(path)
            path.unlink(); path.write_bytes(b'x' * 1025)
            with self.assertRaises(ValueError): runner.read_progress(path)
            path.write_text('{"raw_tensor":"token=secret"}')
            other.unlink()
            runner.write_evidence(out, common.safe_summary('FAIL', 'child_failed'), {})
            text = ''.join(p.read_text() for p in out.iterdir())
            self.assertNotIn('secret', text); self.assertNotIn('raw_tensor', text)
            self.assertEqual(json.loads(path.read_text())['status'], 'NOT_AVAILABLE')

    def exercise(self, tmp, *, child=None, snapshot=None):
        root = Path(tmp); library = root / 'fixture.so'; library.write_bytes(b'cold only')
        native_receipt = root / 'compile.json'; native_receipt.write_text('{}')
        env = {'MATRIX_SERVICE_LIBRARY': str(library), 'MATRIX_SERVICE_COMPILE_RECEIPT': str(native_receipt)}
        native = common.library_snapshot(env)[2]
        def execute(args, **kwargs):
            if child: return child(args, **kwargs)
            Path(args[-1]).write_text(json.dumps(progress()))
            kwargs['log'].write(json.dumps(receipt(SOURCES, native)).encode()); return 0
        with ExitStack() as stack:
            stack.enter_context(patch.object(runner, 'source_snapshot', side_effect=snapshot, return_value=dict(SOURCES)))
            stack.enter_context(patch.object(common.numeric_prepare, 'check'))
            stack.enter_context(patch.object(common.recipe, 'from_environment', return_value=library))
            stack.enter_context(patch.object(common.recipe, 'build', side_effect=AssertionError('never build')))
            launched = stack.enter_context(patch.object(common, 'run_group', side_effect=execute))
            code, result = runner.run(root / 'evidence', env)
        return code, result, launched

    def test_one_child_fixed_budget_and_only_three_safe_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, result, launched = self.exercise(tmp)
            self.assertEqual((code, result['status']), (0, runner.PASS_STATUS))
            launched.assert_called_once()
            args, kwargs = launched.call_args.args[0], launched.call_args.kwargs
            self.assertEqual(args[2:5], [runner.CHILD_MODULE, '--run-m128', '--progress'])
            self.assertGreater(kwargs['timeout'], 2393); self.assertLessEqual(kwargs['timeout'], 2394)
            self.assertEqual(kwargs['grace'], 5)
            self.assertLessEqual(result['total_budget_seconds'], 2400)
            out = Path(tmp) / 'evidence'
            self.assertEqual({p.name for p in out.iterdir()}, set(runner.OUTPUTS))
            self.assertNotIn(tmp, ''.join(p.read_text() for p in out.iterdir()))
            self.assertEqual(json.loads((out / 'progress.json').read_text())['status'], 'PROGRESS')

    def test_missing_library_never_launches_and_progress_is_not_a_pass(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(common, 'run_group') as launched:
            code, result = runner.run(Path(tmp) / 'evidence', {})
            self.assertEqual((code, result['status']), (2, 'NOT_RUN'))
            launched.assert_not_called()
            self.assertEqual(json.loads((Path(tmp) / 'evidence/progress.json').read_text())['status'], 'NOT_AVAILABLE')
        def failed(args, **kwargs):
            Path(args[-1]).write_text(json.dumps(progress()))
            kwargs['log'].write(b'raw_tensor=[1] token=secret /private\n'); return 1
        with tempfile.TemporaryDirectory() as tmp:
            code, result, _ = self.exercise(tmp, child=failed)
            self.assertEqual((code, result['status']), (1, 'FAIL'))
            self.assertNotIn('result', result)
            text = ''.join(p.read_text() for p in (Path(tmp) / 'evidence').iterdir())
            self.assertNotIn('secret', text); self.assertNotIn('/private', text)

    def test_missing_progress_or_source_drift_cannot_pass(self):
        def no_progress(args, **kwargs):
            native = common.library_snapshot(kwargs['env'])[2]
            kwargs['log'].write(json.dumps(receipt(SOURCES, native)).encode()); return 0
        with tempfile.TemporaryDirectory() as tmp:
            code, result, _ = self.exercise(tmp, child=no_progress)
            self.assertEqual((code, result['status']), (1, 'FAIL'))
        calls = 0
        def snapshot():
            nonlocal calls
            calls += 1
            return SOURCES if calls <= 3 else {'scripts/cold-fixture.py': 'f' * 64}
        with tempfile.TemporaryDirectory() as tmp:
            code, result, _ = self.exercise(tmp, snapshot=snapshot)
            self.assertEqual((code, result['status'], result['reason']), (1, 'FAIL', 'input_drift'))
            self.assertNotIn('result', result)

    def test_abandoned_atomic_stage_is_unlinked_without_following_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'evidence'; out.mkdir()
            target = Path(tmp) / 'private'; target.write_text('secret payload')
            pending = out / 'progress.pending'; pending.symlink_to(target)
            (out / 'progress.json').write_text(json.dumps(progress('direct')))
            summary = common.safe_summary('TIMEOUT', 'total_budget')
            runner.write_evidence(out, summary, {'schema': 1})
            self.assertEqual(target.read_text(), 'secret payload')
            self.assertEqual({p.name for p in out.iterdir()}, set(runner.OUTPUTS))
            self.assertEqual(json.loads((out / 'progress.json').read_text())['phase'], 'direct')
            pending.write_text('{"raw_tensor":"partial secret"')
            runner.write_evidence(out, summary, {'schema': 1})
            self.assertFalse(pending.exists())
            self.assertNotIn('secret', ''.join(p.read_text() for p in out.iterdir()))

    def test_final_progress_revalidation_can_only_downgrade_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); (out / 'progress.json').write_text(json.dumps(progress('direct')))
            summary = common.safe_summary(runner.PASS_STATUS, 'complete_numeric_receipt')
            summary['result'] = receipt()
            runner.write_evidence(out, summary, {})
            self.assertEqual(summary['status'], 'FAIL')
            self.assertNotIn('result', summary)
        writer = runner.write_evidence
        def changed_before_final_copy(out, summary, hashes):
            (out / 'progress.json').write_text(json.dumps(progress('direct')))
            writer(out, summary, hashes)
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner, 'write_evidence', changed_before_final_copy):
            code, result, _ = self.exercise(tmp)
            self.assertEqual((code, result['status']), (1, 'FAIL'))
            self.assertNotIn('result', result)

    def test_real_group_timeout_retains_partial_progress_and_kills_resistant_child(self):
        real_group = common.run_group; mkdir = Path.mkdir
        with tempfile.TemporaryDirectory() as tmp:
            pidfile = Path(tmp) / 'child.pid'
            partial = progress('loan'); partial.update(events=9, scalar_operations=3, matrix_packets=1)
            code = ('import os,signal,sys,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); '
                    'open(sys.argv[1],"w").write(str(os.getpid())); '
                    'open(sys.argv[2],"w").write(sys.argv[3]); '
                    'open(os.path.join(os.path.dirname(sys.argv[2]),"progress.pending"),"w").write("partial"); '
                    'time.sleep(30)')
            def child(args, **kwargs):
                self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0., 0.))
                return real_group([sys.executable, '-c', code, str(pidfile), args[-1], json.dumps(partial)], **kwargs)
            def delayed(path, *args, **kwargs):
                answer = mkdir(path, *args, **kwargs)
                if path.name == 'evidence': time.sleep(.08)
                return answer
            try:
                with patch.object(runner, 'TOTAL_SECONDS', .8), patch.object(common, 'CLEANUP_SECONDS', .3), \
                     patch.object(common, 'RECEIPT_SECONDS', .05), patch.object(Path, 'mkdir', delayed):
                    start = time.monotonic(); rc, summary, _ = self.exercise(tmp, child=child)
                self.assertEqual((rc, summary['status']), (1, 'TIMEOUT'))
                self.assertLess(time.monotonic() - start, 2)
                self.assertEqual(json.loads((Path(tmp) / 'evidence/progress.json').read_text()), partial)
                self.assertFalse((Path(tmp) / 'evidence/progress.pending').exists())
                with self.assertRaises(ProcessLookupError): os.killpg(int(pidfile.read_text()), 0)
            finally:
                if pidfile.exists():
                    try: os.killpg(int(pidfile.read_text()), signal.SIGKILL)
                    except ProcessLookupError: pass

    def test_safe_cli_setup_failure_and_frozen_71_source_closure(self):
        output = io.StringIO()
        with patch.object(runner, 'run', side_effect=RuntimeError('/private token=secret')), redirect_stdout(output):
            self.assertEqual(runner.main(['--out', '/unused']), 1)
        self.assertNotIn('secret', output.getvalue()); self.assertNotIn('/private', output.getvalue())
        self.assertEqual(json.loads(output.getvalue())['total_budget_seconds'], 2400)
        sources = runner.source_snapshot()
        self.assertEqual(len(sources), 71)
        self.assertTrue(all(not Path(name).is_absolute() and len(value) == 64 for name, value in sources.items()))


if __name__ == '__main__':
    unittest.main()
