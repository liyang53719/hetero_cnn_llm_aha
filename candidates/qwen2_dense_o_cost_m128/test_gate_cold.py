"""Cold source/metadata and synthetic audit tests: no inputs, ELF init or FMAs."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import pathlib
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from . import gates as g
from . import launch


class IsolatedOGateColdTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pin = g.pins()
        cls.template = g.OracleGate(g.OUTPUT_ROOT / 'cold_gate_only')

    def setUp(self):
        self.gate = copy.copy(self.template)
        for name in ('input_reads', 'artifact_reads', 'source_cache_bypasses', 'disposal_writes', 'reference_reads'):
            setattr(self.gate, name, [])
        self.gate.disposal_events = self.gate.disposal_writes
        self.gate.blocked = 0

    def read(self, path):
        self.gate.audit('open', (str(path), 'rb', 0))

    def test_exact_two_inputs_readonly(self):
        self.assertEqual(self.gate.input_paths, {g.ROOT / s['path'] for s in g.INPUTS.values()})
        for path in self.gate.input_paths:
            self.read(path)
            for mode, flags in (('wb', 0), ('r+b', 0), (None, os.O_WRONLY), ('rb', os.O_CREAT)):
                with self.assertRaisesRegex(ValueError, 'read-only'):
                    self.gate.audit('open', (str(path), mode, flags))
        self.assertEqual(len(self.gate.input_reads), 2)

    def test_oracle_payloads_are_always_closed(self):
        for opened in (False, True):
            self.gate.opened = opened  # Even an invented seal cannot grant oracle access.
            for role in ('att', 'o', 'n1', 'gate', 'up', 'act', 'down', 'y'):
                for suffix in ('.f32le', '.bf16le', '.bin', '.json', '.txt', ''):
                    with self.assertRaises(ValueError):
                        self.read(g.ROOT / ('work/qwen2_fullblock_reference_capture_20261014/'
                            'fullblock_pair_v2/frozen/' + role + suffix))
        self.assertEqual(self.gate.reference_reads, [])

    def test_all_old_arrays_denied_regardless_extension(self):
        for role in ('q', 'k', 'v', 'att', 'o', 'n1', 'gate', 'up', 'act', 'down', 'y'):
            for suffix in ('.bin', '.npy', '.npz', '.f32le', '.u32le', '.presence', '.json', '.txt', ''):
                for parent in (g.OUTPUT_ROOT / 'old', self.gate.artifacts['library'].parent,
                               g.ROOT / 'work/qwen2_live_tail_inputs_m128/reconstruct01/inputs'):
                    with self.assertRaises(ValueError):
                        self.read(parent / (role + suffix))

    def test_native_artifacts_exact_readonly(self):
        for path in self.gate.artifacts.values():
            self.read(path)
            with self.assertRaisesRegex(ValueError, 'read-only'):
                self.gate.audit('open', (str(path), 'w', os.O_WRONLY))
        self.gate.audit('ctypes.dlopen', (str(self.gate.artifacts['library']),))
        for path in (None, '/tmp/unknown.so', str(self.gate.artifacts['receipt'])):
            with self.assertRaises(ValueError):
                self.gate.audit('ctypes.dlopen', (path,))
        for handle in (None, types.SimpleNamespace(_name=None), types.SimpleNamespace(_name='/tmp/unknown.so')):
            with self.assertRaises(ValueError):
                self.gate.audit('ctypes.dlsym', (handle, 'fegetround'))
        self.gate.audit('ctypes.dlsym', (types.SimpleNamespace(_name=str(self.gate.artifacts['library'])), 'td_reset'))

    def test_metadata_and_exact_runtime_code_remain_readable(self):
        for path in self.gate.metadata_paths | self.gate.runtime_paths:
            self.read(path)
        self.assertFalse(self.gate.input_reads)
        self.assertFalse(self.gate.reference_reads)
        with self.assertRaises(ValueError):
            self.read(g.ROOT / 'work/runtime_recovery/site-packages/not_pinned.npy')

    def test_no_torch_transformers_or_subprocess(self):
        for name in ('torch', 'torch.nn.functional', 'transformers', 'transformers.cache_utils'):
            with self.assertRaises(ValueError):
                self.gate.audit('import', (name, None, None, None, None))
        for event in ('subprocess.Popen', 'os.system', 'os.exec', 'os.posix_spawn', 'os.fork'):
            with self.assertRaises(ValueError):
                self.gate.audit(event, ())

    def test_stdlib_source_only_no_unpinned_sitepackages(self):
        self.read(Path(json.__file__).resolve())
        with self.assertRaises(FileNotFoundError):
            self.read(Path(g.__file__).parent / '__pycache__/gates.cpython-312.pyc')
        with self.assertRaises(ValueError):
            self.read(self.gate.stdlib / 'site-packages/unpinned.py')
        with self.assertRaises(ValueError):
            self.read(self.gate.stdlib / 'site-packages/unpinned.so')

    def test_output_metadata_and_exact_driver_prefixes_only(self):
        for name in ('RESULT.json', 'CONTROL.json', 'events_prefix.jsonl', 'progress.log', 'RESULT.json.tmp',
                     'down_seed_records_prefix.bin', 'down_prefix_transactions_prefix.jsonl'):
            self.read(self.gate.out / name)
            self.gate.audit('open', (str(self.gate.out / name), 'w', os.O_WRONLY | os.O_CREAT))
        for name in ('o.f32le', 'actual_down.f32le', 'array.bin', 'array.npy', 'sub/RESULT.json'):
            with self.assertRaises(ValueError):
                self.gate.audit('open', (str(self.gate.out / name), 'w', os.O_WRONLY))
        with self.assertRaises(ValueError):
            self.gate.audit('open', (3, 'rb', 0))

    def test_mutations_outside_output_and_alias_creation_denied(self):
        for event, args in (('os.remove', (str(g.HERE / 'pins.json'), -1)),
                            ('os.rename', (str(self.gate.out / 'RESULT.json'), str(g.HERE / 'pins.json'), -1, -1)),
                            ('os.symlink', ('/dev/null', str(self.gate.disposal), -1)),
                            ('os.link', ('/tmp/a', '/tmp/b', -1, -1)),
                            ('os.chmod', (str(self.gate.out / 'RESULT.json'), 0o777, -1))):
            with self.assertRaises(ValueError):
                self.gate.audit(event, args)
        self.gate.audit('os.rename', (str(self.gate.out / 'RESULT.json.tmp'),
                                     str(self.gate.out / 'RESULT.json'), -1, -1))

    def test_input_and_output_symlink_aliases_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            alias = Path(tmp) / 'alias'
            alias.symlink_to(next(iter(self.gate.input_paths)))
            with self.assertRaisesRegex(ValueError, 'aliased'):
                self.read(alias)
            with self.assertRaises(ValueError):
                g.fresh_output(alias)

    def test_disposal_rejects_direct_read_write_and_wrong_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.gate.out = Path(tmp)
            self.gate.disposal = Path(tmp) / 'actual_dense.f32le'
            self.gate.disposal.symlink_to('/dev/null')
            with self.assertRaisesRegex(ValueError, 'write-only'):
                self.read(self.gate.disposal)
            with self.assertRaisesRegex(ValueError, 'call chain'):
                self.gate.audit('open', (str(self.gate.disposal), 'w', os.O_WRONLY | os.O_CREAT | os.O_TRUNC))
            with self.assertRaises(ValueError):
                self.read('/dev/null')
            self.gate.audit('os.remove', (str(self.gate.disposal), -1))
            with self.assertRaises(ValueError):
                self.gate.audit('os.remove', (str(self.gate.disposal), 3))
            self.gate.disposal.unlink()
            self.gate.disposal.symlink_to('/tmp/not_dev_null')
            with self.assertRaises(ValueError):
                self.gate.audit('os.remove', (str(self.gate.disposal), -1))
            with self.assertRaises(ValueError):
                self.gate.audit('open', (str(self.gate.disposal), 'w', os.O_WRONLY | os.O_CREAT | os.O_TRUNC))

    def test_disposal_exact_pinned_frame_predicate_synthetic_only(self):
        # No driver invocation or tensor write: synthetic frame views test the
        # call-chain predicate using the actual source-compiled code objects.
        module = types.ModuleType(g.DRIVER_MODULE)
        module.__file__ = str(self.gate.driver_path)
        module._execute_dense = types.FunctionType(self.gate.expected_driver, module.__dict__)
        driver = types.SimpleNamespace(f_globals=module.__dict__, f_code=module._execute_dense.__code__,
            f_locals=dict(out=self.gate.out, output_path='actual_dense.f32le', legacy_down=False,
                          raw=bytes(786432)), f_back=None)
        write = types.SimpleNamespace(f_globals=pathlib.__dict__, f_code=Path.write_bytes.__code__,
            f_locals={'self':self.gate.disposal}, f_back=driver)
        opening = types.SimpleNamespace(f_globals=pathlib.__dict__, f_code=Path.open.__code__,
            f_locals={'self':self.gate.disposal}, f_back=write)
        with patch.dict(sys.modules, {g.DRIVER_MODULE: module}):
            self.gate._disposal_frames(opening)
            for key, value in (('legacy_down', True), ('output_path', 'actual_down.f32le'),
                               ('raw', bytes(12)), ('out', self.gate.out / 'nested')):
                previous = driver.f_locals[key]
                driver.f_locals[key] = value
                with self.assertRaises(ValueError):
                    self.gate._disposal_frames(opening)
                driver.f_locals[key] = previous
        self.assertEqual(self.gate.disposal_writes, [])

    def test_disposal_single_use_synthetic_event_predicate_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.gate.out = Path(tmp)
            self.gate.disposal = Path(tmp) / 'actual_dense.f32le'
            self.gate.disposal.symlink_to('/dev/null')
            with patch.object(self.gate, '_disposal_frames') as checked:
                self.gate.audit('open', (str(self.gate.disposal), 'w', os.O_WRONLY | os.O_CREAT | os.O_TRUNC))
                checked.assert_called_once()
                with self.assertRaisesRegex(ValueError, 'single-use'):
                    self.gate.audit('open', (str(self.gate.disposal), 'w', os.O_WRONLY | os.O_CREAT | os.O_TRUNC))
            self.assertEqual(len(self.gate.disposal_events), 1)

    def test_fixed_scope_and_frozen_closure(self):
        p = g.verify_dependencies()
        self.assertEqual(len(p['dependency_sha256']), 267)
        for key, value in (('scope', 'SAME_CHAIN'), ('actual_execution_authorized', True),
                           ('numerical_acceptance', True), ('fullchain_source_manifest', '0' * 64),
                           ('schema', True), ('stage', 'DENSE_DOWN_M128')):
            with patch.object(g, 'pins', return_value=dict(self.pin, **{key:value})):
                with self.assertRaises(ValueError):
                    g.verify_dependencies()
        changed = copy.deepcopy(self.pin)
        changed['dependency_sha256'][g.DRIVER] = '0' * 64
        with patch.object(g, 'pins', return_value=changed):
            with self.assertRaises(ValueError):
                g.verify_dependencies()

    def test_exact_input_pins_cannot_be_substituted(self):
        for role in ('att', 'wo'):
            for key, value in (('path', 'work/old/' + role + '.bin'), ('bytes', 1), ('sha256', '0' * 64)):
                changed = copy.deepcopy(self.pin)
                changed['inputs'][role][key] = value
                with patch.object(g, 'pins', return_value=changed):
                    with self.assertRaises(ValueError):
                        g.verify_dependencies()

    def test_input_loader_synthetic_hash_validation_without_real_inputs(self):
        # Only in-memory test bytes are used; this never opens an operand file.
        fake = {name: b'synthetic-' + name.encode() for name in g.INPUTS}
        pin = {'inputs':{name:dict(path=spec['path'], bytes=len(fake[name]),
            sha256=hashlib.sha256(fake[name]).hexdigest()) for name,spec in g.INPUTS.items()}}
        def canonical(path):
            name = next(n for n,s in g.INPUTS.items() if path == g.ROOT / s['path'])
            return types.SimpleNamespace(is_file=lambda:True, stat=lambda:types.SimpleNamespace(st_size=len(fake[name])),
                                         read_bytes=lambda:fake[name])
        with patch.object(g, 'verify_dependencies', return_value=pin), patch.object(g, '_canonical', side_effect=canonical):
            self.assertEqual(g.load_inputs(), fake)
            pin['inputs']['att']['sha256'] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'hash drift'):
                g.load_inputs()

    def test_source_validation_never_opens_operand_or_oracle_payload(self):
        forbidden = self.gate.input_paths
        original_open = Path.open
        def guarded(path, *args, **kwargs):
            self.assertNotIn(path.resolve(), forbidden)
            self.gate.audit('open', (str(path), 'rb', 0))
            return original_open(path, *args, **kwargs)
        before = set(sys.modules)
        with patch.object(Path, 'open', guarded):
            source = g.sources()
        self.assertTrue(source)
        self.assertFalse(any(n.split('.')[0] in ('torch', 'transformers', 'numpy') for n in set(sys.modules) - before))
        self.assertEqual(self.gate.input_reads, [])
        self.assertEqual(self.gate.reference_reads, [])

    def test_review_manifest_covers_new_sources_excludes_new_freeze(self):
        source = g.sources()
        for name in ('gates.py', 'launch.py', 'test_gate_cold.py', 'runner.py', 'controls.py', 'pins.json'):
            self.assertIn(str((g.HERE / name).relative_to(g.ROOT)), source)
        self.assertNotIn(str((g.HERE / 'FREEZE.json').relative_to(g.ROOT)), source)
        for value in (None, '', '0' * 64, 'x' * 64):
            with self.assertRaises(ValueError):
                g.require_review(value)
        self.assertEqual(g.require_review(g.manifest(source)), source)

    def test_fixed_budget_no_override_or_wholeblock_budget_change(self):
        self.assertEqual(g.LIMITS, dict(work_wall_seconds=60, outer_wall_seconds=70, rss_bytes=2147483648,
            output_bytes=2097152, log_bytes=262144, file_bytes=1048576,
            poll_seconds=.1, threads=1, automatic_retry=False))
        old = g._parse((g.ROOT / 'candidates/qwen2_live_fullblock_model_m128/BUDGET.json').read_bytes())
        self.assertEqual(old['status'], 'BLOCKED_PENDING_REPRESENTATIVE_TIMING')
        for arg in ('--rows', '--wall-seconds', '--timeout', '--data', '--reference'):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                launch.main([arg, '1'])

    def test_fresh_output_direct_child_only(self):
        g.fresh_output(self.gate.out)
        for path in (g.OUTPUT_ROOT, self.gate.out / 'nested', g.HERE / 'output',
                     g.OUTPUT_ROOT / '.hidden', g.OUTPUT_ROOT / ('x' * 65)):
            with self.assertRaises(ValueError):
                g.fresh_output(path)
        with patch.object(Path, 'exists', return_value=True):
            with self.assertRaisesRegex(ValueError, 'already exists'):
                g.fresh_output(self.gate.out)

    def test_launcher_default_delegates_cold_only_and_actual_requires_review(self):
        from . import runner
        with patch.object(runner, 'main', return_value=37) as cold, patch.object(launch, 'supervise') as actual:
            self.assertEqual(launch.main([]), 37)
            cold.assert_called_once_with([])
            actual.assert_not_called()
        for args in (['--actual'], ['--actual', '--out', str(self.gate.out)],
                     ['--out', str(self.gate.out)], ['--reviewed-source-manifest', '0' * 64]):
            with self.assertRaises(ValueError):
                launch.main(args)
        with patch.object(launch.subprocess, 'Popen') as popen:
            with self.assertRaises(ValueError):
                launch.supervise(str(self.gate.out), '0' * 64)
            popen.assert_not_called()

    def test_supervisor_inventory_ignores_only_null_disposal(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / 'RESULT.json').write_text('{}')
            (out / 'actual_dense.f32le').symlink_to('/dev/null')
            self.assertEqual(launch.directory_bytes(out), 2)
            (out / 'other').symlink_to('/dev/null')
            with self.assertRaises(ValueError):
                launch.directory_bytes(out)
            (out / 'other').unlink()
            with patch.object(g, 'LIMITS', dict(g.LIMITS, file_bytes=1)):
                with self.assertRaisesRegex(ValueError, 'per-file cap'):
                    launch.directory_bytes(out)


class SupervisorColdTests(unittest.TestCase):
    """No child is launched: exercise receipts and cleanup with a mock process."""
    def simulate(self, *, changes=None, running=False, rss=0, disk=None,
                 remaining_group=False, cleanup_incomplete=False, timeout=False, missing=False, log_bytes=0):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / 'synthetic_supervisor'
            value = dict(status='COST_ONLY_O_COMPLETE', scope=g.SCOPE,
                         cost_complete=True, numerical_acceptance=False)
            value.update(changes or {})
            child = types.SimpleNamespace(pid=999999, poll=lambda:None if running else 0,
                                          wait=lambda **kwargs:0)
            def fake_popen(argv, **kwargs):
                out.mkdir()
                if log_bytes:
                    kwargs['stdout'].write('x' * log_bytes)
                    kwargs['stdout'].flush()
                if not missing:
                    (out / 'RESULT.json').write_text(json.dumps(value))
                self.assertEqual(kwargs['env']['OMP_NUM_THREADS'], '1')
                self.assertEqual(kwargs['env']['OPENBLAS_NUM_THREADS'], '1')
                self.assertTrue(kwargs['start_new_session'])
                self.assertIs(kwargs['preexec_fn'], launch._child_limits)
                self.assertEqual(argv[3:6], ['--actual', '--out', str(out)])
                self.assertEqual(argv[6:], ['--reviewed-source-manifest', 'a' * 64])
                return child
            with contextlib.ExitStack() as stack:
                stack.enter_context(patch.object(g, 'OUTPUT_ROOT', root))
                review = stack.enter_context(patch.object(g, 'require_review', return_value={}))
                popen = stack.enter_context(patch.object(launch.subprocess, 'Popen', side_effect=fake_popen))
                stack.enter_context(patch.object(launch, 'group_exists', return_value=remaining_group))
                cleanup = stack.enter_context(patch.object(launch, 'terminate_group', return_value=(0, cleanup_incomplete)))
                stack.enter_context(patch.object(launch, 'process_group_rss', return_value=rss))
                if disk is not None:
                    stack.enter_context(patch.object(launch, 'directory_bytes', return_value=disk))
                if timeout:
                    times = iter((0.0, 0.0))
                    stack.enter_context(patch.object(launch.time, 'monotonic', side_effect=lambda:next(times, 64.0)))
                stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                code = launch.supervise(out, 'a' * 64)
                review.assert_called_once_with('a' * 64)
                popen.assert_called_once()
            receipt = json.loads(out.with_name(out.name + '.LAUNCH.json').read_text())
            result = json.loads((out / 'RESULT.json').read_text())
            self.assertIs(receipt['numerical_acceptance'], False)
            self.assertIs(receipt['automatic_retry'], False)
            self.assertEqual(receipt['scope'], g.SCOPE)
            return code, receipt, result, cleanup.call_count

    def test_cost_only_completion_receipt_no_numeric_acceptance(self):
        code, receipt, result, cleanups = self.simulate()
        self.assertEqual(code, 0)
        self.assertEqual(receipt['status'], 'COST_ONLY_O_COMPLETE')
        self.assertTrue(receipt['cost_complete'])
        self.assertFalse(receipt['fullblock_pass'])
        self.assertEqual(cleanups, 0)

    def test_numeric_or_fullblock_claim_fails_closed(self):
        for changes in ({'numerical_acceptance':True}, {'fullblock_pass':True},
                        {'acceptance_sealed':True}, {'scope':'SAME_CHAIN'}, {'cost_complete':False},
                        {'same_chain_acceptance':True}, {'fullblock_executed':True},
                        {'public21_executed':True}, {'official_observed_node_pass':True}):
            with self.subTest(changes=changes):
                code, receipt, result, _ = self.simulate(changes=changes)
                self.assertEqual(code, 1)
                self.assertEqual(receipt['status'], 'FAILED')
                self.assertFalse(receipt['cost_complete'])
                self.assertFalse(result['numerical_acceptance'])
                self.assertFalse(result['fullblock_pass'])
                self.assertFalse(result['acceptance_sealed'])

    def test_missing_child_result_fails_without_retry(self):
        code, receipt, _, _ = self.simulate(missing=True)
        self.assertEqual(code, 1)
        self.assertEqual(receipt['failure_kind'], 'CHILD_FAILED_OR_INVALID_COST_RECEIPT')

    def test_sampled_rss_cap_cleans_group_and_revokes_completion(self):
        code, receipt, result, cleanups = self.simulate(running=True, rss=g.LIMITS['rss_bytes']+1)
        self.assertEqual(code, 1)
        self.assertEqual(receipt['failure_kind'], 'SAMPLED_RSS_CAP')
        self.assertFalse(result['cost_complete'])
        self.assertEqual(cleanups, 1)

    def test_sampled_output_cap_cleans_group(self):
        code, receipt, _, cleanups = self.simulate(running=True, disk=g.LIMITS['output_bytes']+1)
        self.assertEqual(code, 1)
        self.assertEqual(receipt['failure_kind'], 'SAMPLED_OUTPUT_CAP')
        self.assertEqual(cleanups, 1)

    def test_sampled_log_cap_cleans_group(self):
        code, receipt, _, cleanups = self.simulate(running=True, log_bytes=g.LIMITS['log_bytes']+1)
        self.assertEqual(code, 1)
        self.assertEqual(receipt['failure_kind'], 'SAMPLED_LOG_CAP')
        self.assertEqual(cleanups, 1)

    def test_outer_timeout_cleans_group(self):
        code, receipt, _, cleanups = self.simulate(running=True, timeout=True)
        self.assertEqual(code, 1)
        self.assertEqual(receipt['failure_kind'], 'OUTER_WALL_TIMEOUT')
        self.assertEqual(cleanups, 1)

    def test_incomplete_process_group_cleanup_fails_closed(self):
        code, receipt, _, cleanups = self.simulate(remaining_group=True, cleanup_incomplete=True)
        self.assertEqual(code, 1)
        self.assertEqual(receipt['failure_kind'], 'PROCESS_GROUP_CLEANUP_INCOMPLETE')
        self.assertEqual(cleanups, 1)


if __name__ == '__main__':
    unittest.main()
