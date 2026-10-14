"""Metadata, AST, mock receipts only. Never imports a numeric runtime or loads inputs."""
import ast
from collections import Counter
import contextlib
import copy
import io
import json
from pathlib import Path
import subprocess
import tempfile
import time
from types import SimpleNamespace as S
import unittest
from unittest.mock import patch
from . import gates, launch, native_artifact, runner, telemetry


def fake_context():
    attention = S(state='matrix_wait', counts=Counter(matrix_requests=3, matrix_results=2),
        clock=100, ack_bytes=64, functional_state_ticks=Counter(matrix_wait=7),
        memory_pending=True, abort_pending=False, matrix_client='client', matrix_request='request')
    shared = S(client='attention', calls=Counter(bf=32))
    service = S(owner='attention', counts=Counter(normal_steps=3))
    owner = S(pending=None, fifo=[], read_active=None, a_hold=None, a_rmw_pending=None,
        accepted_write=None, tiles=S(leased=False, idle=True), lease=None)
    physical = S(pending='dma', counts=Counter(write_ack_bytes=64), regions={
        'att': dict(readonly=False, written={0, 1}, acked={0}, terminal=False, published=False)})
    host = S(pc=10, completed=10, jobs=11, state='execute', status=None,
        events=set(range(11)), published=[(10, 20)])
    x = S(host=host, attention_owner=attention, owner=owner, reduction=None,
          prefix_owner=S(state='idle'), launch_result=None, counts=Counter(request_fire=11))
    return dict(x=x, physical=physical, service=service, shared=shared)


class ColdGateTests(unittest.TestCase):
    def test_defaults_cannot_import_numeric_or_spawn(self):
        for entry in (runner, launch):
            stream = io.StringIO()
            with patch.object(runner, 'dependencies', side_effect=AssertionError('numeric forbidden')), \
                 patch.object(native_artifact, 'load', side_effect=AssertionError('load forbidden')), \
                 patch.object(subprocess, 'Popen', side_effect=AssertionError('spawn forbidden')), \
                 contextlib.redirect_stdout(stream):
                self.assertEqual(entry.main([]), 0)
            result = json.loads(stream.getvalue())
            self.assertEqual(result['status'], 'NOT_EXECUTED')
            self.assertFalse(result['input_loading'] or result['build'] or result['rtl'] or result['fullblock'])
            self.assertFalse(result['actual_execution_authorized'])

    def test_review_required_before_paths(self):
        with patch.object(gates, 'data_path', side_effect=AssertionError('path forbidden')):
            for digest in (None, '', 'bad', '0' * 64):
                with self.assertRaises(ValueError):
                    runner.run('out', 'data', 'ref', reviewed_source_manifest=digest)

    def test_historical_approval_never_authorizes(self):
        with patch.object(gates, 'pins', return_value=dict(gates.pins(), actual_execution_authorized=True)):
            with self.assertRaisesRegex(ValueError, 'stored approval'):
                gates.verify_dependencies()

    def test_frozen_original_169_and_new_only(self):
        p = gates.verify_dependencies()
        self.assertEqual(len(p['dependency_sha256']), 169)
        sources = gates.sources()
        self.assertTrue(all(sources[n] == h for n, h in p['dependency_sha256'].items()))
        self.assertTrue(all(n in p['dependency_sha256'] or n.startswith('candidates/qwen2_live_attention_model_m128_bounded/') for n in sources))
        self.assertFalse(any('idle_fastpath' in n or 'fullblock_reference' in n or 'model_m16' in n for n in sources))
        self.assertEqual(gates.require_review(gates.manifest(sources)), sources)

    def test_narrow_outputs_and_oracle_isolation(self):
        data = gates.ROOT / 'work/qwen2_live_qkv_inputs_m128/frozen01'
        reference = gates.ROOT / 'work/qwen2_live_attention_reference_m128/frozen01/reference'
        out = gates.OUTPUT_ROOT / 'cold_absent_run'
        gate = gates.OracleGate(data, out, reference)
        for role in gates.ROLES:
            gate.audit('open', (str(data / 'inputs' / (role + '.bin')), 'rb', 0))
        for role in gates.REFERENCES:
            with self.assertRaises(ValueError):
                gate.audit('open', (str(reference / (role + '.f32le')), 'rb', 0))
        for path in (data / 'inputs/q.bin', gates.ROOT / 'work/qwen2_live_attention_numeric_m128_20261014/m128_pv32_actual_v1/q.f32le'):
            with self.assertRaises(ValueError): gate.audit('open', (str(path), 'rb', 0))
        for path in (gates.OUTPUT_ROOT, out / 'nested', data / 'output'):
            with self.assertRaises(ValueError): gates.fresh_output(path, data)
        self.assertFalse(gate.opened); self.assertEqual(gate.reference_reads, [])

    def test_native_hashes_without_loading(self):
        result = native_artifact.identity()
        self.assertEqual(result['library']['sha256'], 'a44f4cd7861d1207698bb3dfc89820ded30a44db1cf1c8b9f951019d1edce1fa')

    def test_exact_native_audit_events_only(self):
        gate = gates.OracleGate(gates.ROOT / 'work/qwen2_live_qkv_inputs_m128/frozen01',
            gates.OUTPUT_ROOT / 'cold_absent_run',
            gates.ROOT / 'work/qwen2_live_attention_reference_m128/frozen01/reference')
        for path in gate.artifacts.values(): gate.audit('open', (str(path), 'rb', 0))
        gate.audit('ctypes.dlopen', (str(gate.artifacts['library']),))
        self.assertEqual(len(gate.artifact_reads), 3)
        for path in (gate.artifacts['library'].with_name('other.so'), gate.artifacts['library'].parent.parent / 'RESULT.json'):
            with self.assertRaises(ValueError): gate.audit('open', (str(path), 'rb', 0))
        for path in (None, str(gate.artifacts['library'].with_name('other.so')), '/tmp/other.so'):
            with self.assertRaises(ValueError): gate.audit('ctypes.dlopen', (path,))
        with self.assertRaises(ValueError): gate.audit('open', (str(gate.artifacts['library']), 'wb', 0))
        with self.assertRaises(ValueError): gate.audit('open', (str(gates.ROOT / 'work/other/model.so'), 'rb', 0))
        self.assertFalse(gate.opened); self.assertEqual(gate.reference_reads, [])

    def test_partial_arguments(self):
        for entry in (runner, launch):
            for args in (['--actual'], ['--out', 'x'], ['--reviewed-source-manifest', '0' * 64]):
                with self.assertRaises(ValueError): entry.main(args)


class SourceEquivalenceTests(unittest.TestCase):
    def test_attention_driver_ast_restores_original(self):
        original_path = gates.ROOT / 'candidates/qwen2_resident_matrix/ffn_public/fullgraph_execution.py'
        base = next(n for n in ast.parse(original_path.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == 'execute_attention_owner')
        candidate = next(n for n in ast.parse((gates.HERE / 'attention_driver.py').read_text()).body if isinstance(n, ast.FunctionDef))
        self.assertEqual(candidate.args.kwonlyargs[-1].arg, 'progress')
        candidate.args.kwonlyargs.pop(); candidate.args.kw_defaults.pop()
        loop = next(n for n in candidate.body if isinstance(n, ast.While))
        sample = loop.body.pop()
        expected = ast.parse("if progress is not None and counts['ticks'] % 131072 == 0:\n    progress.emit('attention_loop', driver=dict(accepted=dict(counts), pending=pending is not None, held=held is not None))").body[0]
        self.assertEqual(ast.dump(sample), ast.dump(expected))
        self.assertEqual(ast.dump(candidate), ast.dump(base))

    def test_original_gate_calls_preserved(self):
        def required(path):
            return {ast.dump(n) for n in ast.walk(ast.parse(path.read_text())) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'require'}
        original = required(gates.ROOT / 'candidates/qwen2_live_attention_model_m128/runner.py')
        new = required(gates.HERE / 'runner.py')
        removed = original - new
        self.assertEqual(len(removed), 2)
        self.assertTrue(any('execution awaiting' in v for v in removed))
        self.assertTrue(any('data/out require' in v for v in removed))
        source = (gates.HERE / 'runner.py').read_text()
        self.assertNotIn('build_library(', source)
        self.assertNotIn('DenseIdle', source)
        self.assertIn('from candidates.qwen2_live_attention_model_m128 import boundary, compare', source)


class TelemetryTests(unittest.TestCase):
    def test_snapshot_does_not_mutate_any_model_field(self):
        context = fake_context(); before = copy.deepcopy(context)
        result = telemetry.snapshot(context)
        self.assertEqual(context, before)
        self.assertEqual(result['attention']['matrix_requests'], 3)
        self.assertEqual(result['attention']['matrix_results'], 2)
        self.assertEqual(result['physical_outputs']['att']['ack_bytes'], 64)
        self.assertFalse(result['physical_outputs']['att']['published'])
        self.assertTrue(result['debts']['matrix_owned'] and result['debts']['dma_pending'])
        json.dumps(result, allow_nan=False)

    def test_signal_never_reads_model(self):
        progress = telemetry.SparseTelemetry(Path('unused'), started=time.monotonic(), cpu=time.process_time())
        with patch.object(telemetry, 'snapshot', side_effect=AssertionError('signal cannot read model')):
            with self.assertRaises(telemetry.BudgetExceeded): progress._alarm(None, None)

    def test_deadline_does_not_depend_on_sampling_or_model_ticks(self):
        progress = telemetry.SparseTelemetry(Path('unused'), started=time.monotonic() - 901, cpu=time.process_time())
        with self.assertRaises(telemetry.BudgetExceeded): progress.check()

    def test_preflight_failure_receipt_preserves_original_cause(self):
        oldtmp = tempfile.tempdir
        with tempfile.TemporaryDirectory(dir=gates.OUTPUT_ROOT) as directory:
            root = Path(directory); out = root / 'cold_failure'
            try:
                with patch.object(gates, 'OUTPUT_ROOT', root), \
                     patch.object(gates, 'require_review', return_value={}), \
                     patch.object(gates, 'require_final_reference'), \
                     patch.object(gates, 'data_path', return_value=root / 'absent_data'), \
                     patch.object(gates, 'reference_path', return_value=root / 'absent_reference'), \
                     patch.object(telemetry.SparseTelemetry, 'start'), \
                     patch.object(runner, 'dependencies', side_effect=ValueError('public FFN host budget exceeded')):
                    with self.assertRaisesRegex(RuntimeError, 'M128 dependency_setup: software wall deadline exceeded') as raised:
                        runner.run(str(out), 'cold_data', 'cold_ref', reviewed_source_manifest='0' * 64)
                self.assertIsInstance(raised.exception.__cause__, ValueError)
                result = json.loads((out / 'RESULT.json').read_text())
                self.assertEqual(result['failure_stage'], 'dependency_setup')
                self.assertEqual(result['original_error_message'], 'public FFN host budget exceeded')
                self.assertEqual(result['failure_kind'], 'BUDGET_EXCEEDED')
                self.assertFalse(result['actual_outputs_sealed'] or result['acceptance_sealed'] or result['oracle_opened'])
                self.assertEqual(result['oracle_reference_reads'], [])
                self.assertFalse((root / 'absent_data').exists())
            finally:
                tempfile.tempdir = oldtmp

    def test_nonbudget_exception_identity_preserved(self):
        error = ValueError('shape mismatch')
        self.assertIs(telemetry.contextual_error('attention', error), error)

    def test_outer_timeout_never_becomes_acceptance(self):
        with tempfile.TemporaryDirectory(dir=gates.OUTPUT_ROOT) as directory:
            root = Path(directory); out = root / 'cold_supervisor'
            class Child:
                pid = 999999
                count = 0
                def wait(self, timeout=None):
                    self.count += 1
                    if self.count == 1: raise subprocess.TimeoutExpired('mock', timeout)
                    return 1
            with patch.object(gates, 'OUTPUT_ROOT', root), patch.object(gates, 'require_review'), \
                 patch.object(gates, 'data_path', return_value=root / 'absent_data'), \
                 patch.object(gates, 'reference_path'), patch.object(subprocess, 'Popen', return_value=Child()), \
                 patch.object(launch.os, 'killpg') as group_kill, \
                 patch.object(launch, 'group_exists', return_value=False), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(launch.supervise(out, 'cold_data', 'cold_ref', '0' * 64), 1)
            self.assertEqual(group_kill.call_count, 2)
            receipt = json.loads((root / 'cold_supervisor.LAUNCH.json').read_text())
            self.assertEqual(receipt['status'], 'FAILED')
            self.assertTrue(receipt['outer_timeout']); self.assertFalse(receipt['acceptance_sealed'])

    def test_unreapable_process_is_bounded_and_disclosed(self):
        waits = []
        class Child:
            pid = 999999
            def wait(self, timeout=None):
                waits.append(timeout)
                raise subprocess.TimeoutExpired('mock', timeout)
        with patch.object(launch.os, 'killpg'), patch.object(launch, 'group_exists', return_value=False), \
             patch.object(launch.time, 'monotonic', side_effect=[924, 927]):
            returncode, incomplete = launch.terminate_group(Child(), cleanup_deadline=929)
        self.assertIsNone(returncode); self.assertTrue(incomplete)
        self.assertEqual(waits, [3, 2])

    def test_reaped_leader_with_live_descendants_is_not_clean(self):
        child = S(pid=999999, wait=lambda timeout: 0)
        with patch.object(launch.os, 'killpg'), patch.object(launch, 'group_exists', return_value=True), \
             patch.object(launch.time, 'sleep'), patch.object(launch.time, 'monotonic', side_effect=[925, 926, 929]):
            returncode, incomplete = launch.terminate_group(child, cleanup_deadline=929)
        self.assertEqual(returncode, 0); self.assertTrue(incomplete)


if __name__ == '__main__':
    unittest.main()
