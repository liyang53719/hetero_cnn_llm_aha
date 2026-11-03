"""Controller-only integration tests: synthetic receipts, no numerical execution.

Every supervisor invocation is mocked. Small JSON files exercise the real
controller reconstruction and real three-file safe exporter. These tests do not
establish runtime installation, numerical equivalence, or cleanup correctness.
"""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import run_portable as controller
from safe_export import COMPLETE_CLEANUP, FILENAMES, TENSOR_ORDER, validate_exports
from export_seal import verify_sealed_export
from fixture_gate import FixtureMismatch


class ControllerMockTests(unittest.TestCase):
    def exercise(self, mode, fault=None):
        fixture = controller.frozen()
        affinity = sorted(os.sched_getaffinity(0))
        evidence = dict(architecture='x86_64', python_implementation='CPython',
                        python_version='3.12.3', python_sha256='a' * 64,
                        affinity=affinity, flags_intersection=['sse2', 'avx', 'avx2', 'fma', 'avx512f', 'avx512dq', 'avx512bw', 'avx512vl'])
        if mode == 'cpu_missing': evidence['flags_intersection'].remove('avx512dq')
        calls = []
        held_locks = set()
        actual_flock = controller.fcntl.flock

        def tracked_flock(fd, operation):
            actual_flock(fd, operation)
            if operation & controller.fcntl.LOCK_UN:
                held_locks.discard(fd)
            else:
                held_locks.add(fd)

        def write(path, value):
            path.write_text(json.dumps(value, allow_nan=False) + '\n')

        def check(pin, mismatch=False):
            return dict(status='MISMATCH' if mismatch else 'PASS',
                        expected_bytes=pin['bytes'], observed_bytes=pin['bytes'],
                        expected_sha256=pin['sha256'],
                        observed_sha256=('0' * 64 if mismatch else pin['sha256']),
                        shape_equal=True, dtype_equal=True)

        def fake_execute(argv, run, lock_path, caps, env, pins, resource_gate):
            name = run.name
            calls.append(name)
            self.assertEqual(env['ATEN_CPU_CAPABILITY'], 'avx512')
            self.assertEqual(caps['admitted_affinity'], affinity)
            self.assertGreater(caps['wall_seconds'], 0)
            self.assertGreater(caps['cpu_seconds'], 0)
            self.assertEqual(caps['extra_watch_roots'], [str(run.parent.parent)])
            self.assertEqual(resource_gate['min_available_memory'], caps['rss_bytes'] + controller.GIB)
            output = run / 'output'
            output.mkdir(parents=True)
            report = dict(native_exit=0, errors=[], status='PASS_PROCESS_ONLY',
                          cleanup_proof={'status': COMPLETE_CLEANUP}, observed_remaining=[],
                          log_capture={'pipe_eof_observed': True, 'gzip_finalized': True},
                          reader_join_barrier={'complete': True},
                          rss_telemetry={'all_written_bytes_verified': True},
                          elapsed_seconds=0.1, observed_cpu_seconds=0.01,
                          supervisor_cpu_seconds=0.001, observed_peak_rss=1024,
                          peak_stage_tree_bytes=1024, minimum_free_disk_bytes=10 * controller.GIB,
                          minimum_MemAvailable_bytes=8 * controller.GIB)
            if name == 'runtime':
                write(output / 'RUNTIME_RECEIPT.json', dict(schema='P0_AVX512_FRESH_RUNTIME_V1', observed_capability=('DEFAULT' if mode=='wrong_runtime_capability' else 'AVX512'),
                                                         threads=4, interop_threads=1))
                (output / 'python').write_text('MOCK ONLY; NEVER EXECUTABLE\n')
                write(output / 'SOURCE_SIDECAR.json', fixture['runtime_sidecar']['content'])
            elif name == 'weights':
                # Include the real acquisition schema field: omission masks a
                # controller schema mismatch that unit exporter tests cannot see.
                write(output / 'WEIGHT_CHECKS.json', dict(schema='P0_WEIGHT_CHECKS_V1',
                                                         checked=0 if mode=='weight_http_failure' else 12, mismatch_count=0))
                if mode=='weight_http_failure':
                    write(output/'FAILURE.json',dict(schema='P0_STAGE_FAILURE_V1',status='FAIL',reason='WEIGHT_HTTP403'))
                    report.update(native_exit=1,status='FAIL_OR_INCOMPLETE')
            elif name == 'reference':
                if mode == 'incomplete':
                    report.update(native_exit=None, errors=['MOCK_OWNERSHIP_INCOMPLETE'],
                                  status='FAIL_OR_INCOMPLETE', cleanup_proof=None,
                                  observed_remaining=[{'pid': 123, 'start': 456}],
                                  log_capture={'pipe_eof_observed': False, 'gzip_finalized': False},
                                  reader_join_barrier={'complete': False})
                    return report
                rows = {}
                for tensor in TENSOR_ORDER:
                    mismatch = (mode == 'mismatch' and tensor == 'baseline_output') or (mode == 'attention_mismatch' and tensor == 'stage.self_attn.0.1')
                    rows[tensor] = check(fixture['frozen_fixture']['tensor_records'][tensor], mismatch)
                    if mismatch:
                        break
                write(output / 'CHECKS_INTERNAL.json', rows)
                if mode in ('mismatch', 'attention_mismatch'):
                    write(output / 'FAILURE.json', dict(reason='REFERENCE_HASH', name=('baseline_output' if mode=='mismatch' else 'stage.self_attn.0.1')))
                    report.update(native_exit=1, status='FAIL_OR_INCOMPLETE')
                else:
                    write(output / 'RESULT.json', dict(affinity=affinity, observed_dispatch='AVX512',
                                                      actual_threads=4, actual_interop=1))
            elif name == 'rope':
                self.assertEqual(mode, 'success', 'No RoPE after failed reference')
                write(output / 'CHECKS_INTERNAL.json', {'rope1024': check(fixture['frozen_fixture']['rope1024'])})
                write(output / 'RESULT.json', {'affinity': affinity})
            elif name == 'finalize':
                self.assertEqual(mode, 'success', 'No finalization after failed reference')
            else:
                self.fail('Unexpected controller stage')
            return report

        with tempfile.TemporaryDirectory(prefix='p0-controller-mock-') as directory:
            root = Path(directory)
            identity = root / 'identity.json'
            started = root / 'job-start.json'
            write(identity, dict(schema='P0_AVX512_ONE_SHOT_IDENTITY_V1', run_id=123,
                                 source_commit='b' * 40, launch_commit='c' * 40,
                                 source_manifest_sha256='d' * 64, nonce='e' * 32, default_failed_run_id=41734412224))
            write(started, dict(schema='P0_AVX512_JOB_START_V1', run_id=123,
                                launch_commit='c' * 40, started_monotonic=time.monotonic(),
                                job_budget_seconds=3600))
            work = root / 'p0-original-avx512-123'
            args = SimpleNamespace(repo=root, identity=identity, job_start=started, output=work)
            try:
                with ExitStack() as stack:
                    stack.enter_context(patch.dict(os.environ, {'RUNNER_TEMP': str(root), 'GITHUB_RUN_ID': '123'}))
                    stack.enter_context(patch.object(controller, 'check_identity'))
                    stack.enter_context(patch.object(controller, 'verify_source', return_value={}))
                    stack.enter_context(patch.object(controller, 'host_evidence', return_value=(evidence, 'f' * 64)))
                    stack.enter_context(patch.object(controller, 'available_memory', return_value=8 * controller.GIB))
                    stack.enter_context(patch.object(controller.shutil, 'disk_usage', return_value=SimpleNamespace(free=10 * controller.GIB)))
                    stack.enter_context(patch.object(controller.fcntl, 'flock', side_effect=tracked_flock))
                    supervisor = stack.enter_context(patch.object(controller.supervise_multiroot, 'execute', side_effect=fake_execute))
                    for method in ('Popen', 'run', 'check_output'):
                        stack.enter_context(patch.object(controller.subprocess, method,
                            side_effect=AssertionError('Subprocess forbidden in controller mock test')))
                    if fault:
                        original_write = controller.write_exports
                        def after_export(*argv, **kwargs):
                            value = original_write(*argv, **kwargs)
                            if fault == 'deadline':
                                stack.enter_context(patch.object(controller.time, 'monotonic', return_value=time.monotonic()+3601))
                            elif fault == 'alarm':
                                controller.signal.getsignal(controller.signal.SIGALRM)(controller.signal.SIGALRM, None)
                            return value
                        stack.enter_context(patch.object(controller, 'write_exports', side_effect=after_export))
                        with self.assertRaises(FixtureMismatch):
                            controller.run(args)
                        self.assertFalse((work/'TERMINAL.json').exists())
                        self.assertEqual(validate_exports(work/'export', controller.HERE/'FROZEN_P0.json')['RESULT.json']['status'], 'PASS_EXACT_VISIBLE_FIXTURE')
                        with self.assertRaises((FixtureMismatch, FileNotFoundError)):
                            verify_sealed_export(work, json.loads(identity.read_text()), controller.HERE/'FROZEN_P0.json', 'failure')
                        return
                    exit_code = controller.run(args)
                    self.assertEqual(supervisor.call_count, len(calls))
                self.assertEqual(set(p.name for p in (work / 'export').iterdir()), set(FILENAMES))
                exported = validate_exports(work / 'export', controller.HERE / 'FROZEN_P0.json')
                terminal = json.loads((work / 'TERMINAL.json').read_text())
                outcome = 'success' if mode == 'success' else 'failure'
                verify_sealed_export(work, json.loads(identity.read_text()), controller.HERE/'FROZEN_P0.json', outcome)
                if mode == 'success':
                    with self.assertRaises(FixtureMismatch):
                        verify_sealed_export(work, json.loads(identity.read_text()), controller.HERE/'FROZEN_P0.json', 'failure')
                self.assertEqual(bool(held_locks), mode == 'incomplete')
                return exit_code, calls, exported, terminal
            finally:
                # The production controller intentionally retains an incomplete
                # owner's FD until process exit. This test owns the exact mocked
                # root and no child exists, so release only its captured lock FD.
                for fd in held_locks:
                    actual_flock(fd, controller.fcntl.LOCK_UN)
                    os.close(fd)

    def test_post_export_deadline_never_uploads_stale_pass(self):
        self.exercise('success', 'deadline')

    def test_post_export_alarm_never_uploads_stale_pass(self):
        self.exercise('success', 'alarm')

    def test_success_three_safe_json_and_weight_schema(self):
        code, calls, files, terminal = self.exercise('success')
        result = files['RESULT.json']
        self.assertEqual(code, 0)
        self.assertEqual(calls, ['runtime', 'weights', 'reference', 'rope', 'finalize'])
        self.assertEqual(result['status'], 'PASS_EXACT_VISIBLE_FIXTURE')
        self.assertEqual((result['weight_checked'], result['tensor_checked']), (12, 25))
        self.assertTrue(result['all_visible_exact'])
        self.assertTrue(all(row['status'] == 'PASS' for row in files['CHECKS.json']['checks']))
        self.assertEqual(terminal['status'], result['status'])

    def test_first_reference_mismatch_stops_rope_and_finalize(self):
        code, calls, files, terminal = self.exercise('mismatch')
        result = files['RESULT.json']
        self.assertEqual(code, 1)
        self.assertEqual(calls, ['runtime', 'weights', 'reference'])
        self.assertEqual((result['status'], result['reason']), ('FAIL', 'REFERENCE_HASH'))
        self.assertEqual((result['weight_checked'], result['tensor_checked']), (12, 7))
        self.assertEqual(result['first_mismatch_name'], 'baseline_output')
        rows = {row['name']: row for row in files['CHECKS.json']['checks']}
        for name in TENSOR_ORDER[:6]:
            self.assertEqual(rows[name]['status'], 'PASS')
        self.assertEqual(rows['baseline_output']['status'], 'MISMATCH')
        self.assertTrue(all(rows[name]['status'] == 'NOT_REACHED' for name in (*TENSOR_ORDER[7:], 'rope1024')))
        self.assertEqual([s['status'] for s in files['HOST_RESOURCES.json']['stages']],
                         ['PASS', 'PASS', 'FAIL', 'NOT_REACHED', 'NOT_REACHED'])
        self.assertEqual(terminal['reason'], 'REFERENCE_HASH')

    def test_incomplete_cleanup_never_advances_or_claims_fail_complete(self):
        code, calls, files, terminal = self.exercise('incomplete')
        result = files['RESULT.json']
        self.assertEqual(code, 1)
        self.assertEqual(calls, ['runtime', 'weights', 'reference'])
        self.assertEqual((result['status'], result['reason']), ('INCOMPLETE', 'OWNERSHIP_INCOMPLETE'))
        self.assertEqual(result['tensor_checked'], 0)
        stages = files['HOST_RESOURCES.json']['stages']
        self.assertEqual([s['status'] for s in stages], ['PASS', 'PASS', 'INCOMPLETE', 'NOT_REACHED', 'NOT_REACHED'])
        self.assertEqual(stages[2]['cleanup'], 'INCOMPLETE')
        self.assertEqual(stages[2]['pipe_eof'], 'INCOMPLETE')
        self.assertEqual(terminal['status'], 'INCOMPLETE')


if __name__ == '__main__':
    unittest.main()
