"""Pure-stdlib mapping, admission, CLI, and comparator tests; no native owner runs."""
import ast
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import chunk_case as cases
import compare_chunk as comparator
import prepare_chunk as preparation
import launch_chunk as supervisor

HERE = Path(__file__).resolve().parent


def plan_for(tokens, heads=1):
    selected = cases.case(tokens, heads)
    plan = dict(schema=selected['schema'], policy={'tokens': tokens, 'heads': heads},
                limits=dict(cpu_seconds=selected['driver_seconds'],
                            driver_wall_seconds=selected['driver_seconds'],
                            outer_wall_seconds=selected['outer_seconds']))
    if heads == 16:
        plan['limits'].update(cases.ALL16_LIMITS)
    if tokens == 128:
        plan['reference_state_slice'] = 'state-reference'
    return plan


class CaseTests(unittest.TestCase):
    def test_default_is_unchanged_m64(self):
        selected = cases.case()
        self.assertEqual((selected['tokens'], selected['chunks'], selected['elements']), (64, 1, 8192))
        self.assertEqual((selected['driver_seconds'], selected['outer_seconds'], selected['cleanup_reserve_seconds']), (60, 75, 15))
        self.assertFalse(selected['state_oracle'])

    def test_m128_is_two_chunks_not_two_terminals(self):
        selected = cases.plan_case(plan_for(128))
        self.assertEqual((selected['chunks'], selected['elements']), (2, 16384))
        self.assertEqual((selected['driver_seconds'], selected['outer_seconds'], selected['cleanup_reserve_seconds']), (90, 110, 20))
        self.assertTrue(selected['state_oracle'])

    def test_reject_unbounded_tokens(self):
        for tokens in (0, 32, 65, 256, True, 64.0, '128'):
            with self.subTest(tokens=tokens), self.assertRaises(ValueError):
                cases.case(tokens)

    def test_reject_inconsistent_plan(self):
        plan = plan_for(128)
        for change in ('schema', 'state', 'limit'):
            altered = copy.deepcopy(plan)
            if change == 'schema':
                altered['schema'] = cases.case(64)['schema']
            elif change == 'state':
                del altered['reference_state_slice']
            else:
                altered['limits']['outer_wall_seconds'] = 111
            with self.subTest(change=change), self.assertRaises(ValueError):
                cases.plan_case(altered)
        plan = plan_for(64)
        plan['reference_state_slice'] = 'not-an-after64-oracle'
        with self.assertRaises(ValueError):
            cases.plan_case(plan)

    def test_token_strided_head0_mapping(self):
        reference = b''.join(struct.pack('<H', row * 16 + head) * 128
                             for row in range(128) for head in range(16))
        for tokens in cases.TOKENS:
            mapped = cases.output_slice(reference, tokens)
            expected = b''.join(struct.pack('<H', row * 16) * 128 for row in range(tokens))
            self.assertEqual(mapped, expected)
        with self.assertRaises(ValueError):
            cases.output_slice(reference[:-2], 128)

    def test_prep_row_extent_and_selection(self):
        prep = b''.join(bytes([row]) * cases.PREP_ROW_BYTES for row in range(128))
        self.assertEqual(cases.prep_rows(prep, 64), prep[:64 * cases.PREP_ROW_BYTES])
        self.assertEqual(cases.prep_rows(prep, 128), prep)
        with self.assertRaises(ValueError):
            cases.prep_rows(prep[:-1], 64)

    def test_head0_state_contiguous_mapping_and_cache_identity(self):
        state = b''.join(bytes([head]) * cases.STATE_BYTES for head in range(16))
        self.assertEqual(cases.state_slice(state, state), bytes(cases.STATE_BYTES))
        for altered in (state[:-1], state[:-1] + b'X'):
            with self.assertRaises(ValueError):
                cases.state_slice(state, altered)
        with self.assertRaises(ValueError):
            cases.state_slice(state[:-1], state[:-1])

    def test_carry_requires_every_phase_and_two_completions(self):
        cases.validate_carry(2, cases.CARRY_READ_BEATS)
        for count, beats in ((1, cases.CARRY_READ_BEATS), (2, {}),
                             (2, dict(cases.CARRY_READ_BEATS, state_decay=1023)),
                             (2, dict(cases.CARRY_READ_BEATS, other=1))):
            with self.assertRaises(ValueError):
                cases.validate_carry(count, beats)

    def test_elementwise_state_gate_not_aggregate_gate(self):
        reference = bytes(cases.STATE_BYTES)
        actual = struct.pack('<f', .0002) + reference[4:]
        metrics = comparator.state_metrics(actual, reference)
        self.assertLess(metrics['mean_abs'], 1e-4)
        self.assertEqual(metrics['violations'], 1)
        self.assertFalse(metrics['meets_existing_state_threshold'])
        self.assertEqual(comparator.state_metrics(reference, reference)['violations'], 0)

    def test_state_rejects_nonfinite_or_wrong_extent(self):
        reference = bytes(cases.STATE_BYTES)
        for value in (float('nan'), float('inf'), -float('inf')):
            with self.assertRaises(ValueError):
                comparator.state_metrics(struct.pack('<f', value) + reference[4:], reference)
        with self.assertRaises(ValueError):
            comparator.state_metrics(reference[:-4], reference)

    def test_all16_bounded_geometry_resources_and_addresses(self):
        selected = cases.plan_case(plan_for(128, 16))
        self.assertEqual((selected['heads'], selected['tokens'], selected['chunks'],
                          selected['elements'], selected['state_bytes']), (16, 128, 32, 262144, 1048576))
        self.assertEqual((selected['driver_seconds'], selected['outer_seconds'],
                          selected['cleanup_reserve_seconds'], selected['postflight_reserve_seconds']),
                         (600, 660, 60, 10))
        self.assertEqual(selected['job_addresses'], (0x400000, 0x800000, 0xA00000, 0xC00000, 0x1000000))
        for field in cases.ALL16_LIMITS:
            altered = plan_for(128, 16)
            altered['limits'][field] += 1
            with self.subTest(field=field), self.assertRaises(ValueError):
                cases.plan_case(altered)

    def test_reject_unbounded_heads_and_all16_m64(self):
        for heads in (0, 2, 15, 17, True, 16.0, '16'):
            with self.subTest(heads=heads), self.assertRaises(ValueError):
                cases.case(128, heads)
        with self.assertRaises(ValueError):
            cases.case(64, 16)
        plan = plan_for(128, 16)
        plan['policy']['heads'] = 1
        with self.assertRaises(ValueError):
            cases.plan_case(plan)

    def test_all16_contiguous_mapping_and_head0_consistency(self):
        output = b''.join(struct.pack('<H', row * 16 + head) * 128
                          for row in range(128) for head in range(16))
        self.assertEqual(cases.output_slice(output, 128, 16), output)
        self.assertEqual(cases.output_slice(cases.output_slice(output, 128, 16), 128, 1),
                         cases.output_slice(output, 128))
        state = b''.join(bytes([head]) * cases.STATE_BYTES for head in range(16))
        self.assertEqual(cases.state_slice(state, state, 16), state)
        self.assertEqual(cases.state_slice(state, state, 1), state[:cases.STATE_BYTES])
        with self.assertRaises(ValueError):
            cases.state_slice(state, state[:-1] + b'X', 16)
        with self.assertRaises(ValueError):
            cases.output_slice(output[:-2], 128, 16)

    def test_all16_carry_and_first_state_require_every_head(self):
        observed = {str(h): dict(cases.CARRY_READ_BEATS) for h in range(16)}
        first = {str(h): 'synthetic-fixture' for h in range(16)}
        cases.validate_carry(32, observed, 16)
        cases.validate_first_states(first, 16)
        for altered in (dict(list(observed.items())[:-1]), dict(observed, extra=cases.CARRY_READ_BEATS),
                        dict(observed, **{'15': dict(cases.CARRY_READ_BEATS, state_decay=1023)})):
            with self.assertRaises(ValueError):
                cases.validate_carry(32, altered, 16)
        with self.assertRaises(ValueError):
            cases.validate_carry(2, observed, 16)
        for altered in (dict(list(first.items())[:-1]), dict(first, extra='fixture'),
                        dict(first, **{'15': ''}), 'head0-only'):
            with self.assertRaises(ValueError):
                cases.validate_first_states(altered, 16)

    def test_all16_state_gate_checks_last_head_and_location(self):
        reference = bytes(16 * cases.STATE_BYTES)
        actual = reference[:-4] + struct.pack('<f', .0002)
        metrics = comparator.state_metrics(actual, reference, 16)
        self.assertEqual(metrics['elements'], 262144)
        self.assertEqual(metrics['violations'], 1)
        self.assertFalse(metrics['meets_existing_state_threshold'])
        self.assertEqual(metrics['worst_normalized_location'], {'head': 15, 'key_row': 127, 'value_column': 127})
        with self.assertRaises(ValueError):
            comparator.state_metrics(actual, reference, 1)
        with self.assertRaises(ValueError):
            comparator.state_metrics(reference[:-4] + struct.pack('<f', float('nan')), reference, 16)

    def test_cli_default_and_m128_mandatory_state_inputs(self):
        options = ('repository', 'runtime-site', 'python', 'vector-library', 'vector-metadata',
                   'compiler', 'saved-prep', 'saved-pins', 'saved-progress', 'official-output', 'output')
        argv = [argument for option in options for argument in ('--' + option, 'not-opened')]
        argv += ['--cpu', '0']
        self.assertEqual((preparation.parse_args(argv).tokens, preparation.parse_args(argv).heads), (64, 1))
        state = ['--official-state', 'state', '--official-final-cache', 'cache', '--official-manifest', 'manifest']
        self.assertEqual(preparation.parse_args(argv + ['--tokens', '128'] + state).tokens, 128)
        self.assertEqual(preparation.parse_args(argv + ['--tokens', '128', '--heads', '16'] + state).heads, 16)
        for extra in (['--tokens', '128'], ['--tokens', '256'], state, ['--heads', '16'],
                      ['--tokens', '128', '--heads', '2'] + state):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                preparation.parse_args(argv + extra)
            self.assertEqual(error.exception.code, 2)

    def test_all16_observer_exposes_chunk_progress_without_changing_head0(self):
        # Stub process observation; never launch, signal, or inspect a real child.
        owner = dict(process=SimpleNamespace(pid=123), identity={'pid': 123})
        strict = SimpleNamespace(OWNER_KEYS=('pid',),
            _Linux=lambda: SimpleNamespace(read=lambda pid: {'pid': pid, 'session': pid}))
        value = dict(commands=[], roots={'generation': 0}, context={'head': 15, 'chunk': 1},
                     position={'row': 63}, head_chunk_completions=32,
                     second_chunk_prior_state_read_beats={'15': cases.CARRY_READ_BEATS})
        expected = dict(chunk_context=value['context'], chunk_position=value['position'],
                        head_chunk_completions=32,
                        second_chunk_prior_state_read_beats=value['second_chunk_prior_state_read_beats'])
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory); (run / 'actual').mkdir()
            (run / 'actual/progress.json').write_text(json.dumps(value))
            for heads in (1, 16):
                plan = plan_for(128, heads)
                plan['limits'].setdefault('file_bytes', 2 << 20)
                with patch.object(Path, 'glob', return_value=()):
                    progress = supervisor.observe(run, owner, strict, plan)['progress']
                if heads == 16:
                    self.assertEqual({key: progress[key] for key in expected}, expected)
                else:
                    self.assertTrue(set(expected).isdisjoint(progress))
                self.assertEqual(progress['terminal_count'], 0)
                self.assertEqual(progress['roots_generation'], 0)

    def test_all16_supervisor_completion_predicate_requires_32_head_chunks(self):
        # Evaluate only the parsed admission expression, not execute()/native code.
        tree = ast.parse((HERE / 'launch_chunk.py').read_text())
        expression = next(node.value for node in ast.walk(tree) if isinstance(node, ast.Assign)
                          and any(isinstance(target, ast.Name) and target.id == 'complete'
                                  for target in node.targets) and isinstance(node.value, ast.BoolOp))
        code = compile(ast.Expression(expression), 'completion-predicate-only', 'eval')
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory); (run / 'actual').mkdir(); (run / 'actual/output.bf16le').touch()
            for tokens, heads in ((64, 1), (128, 1), (128, 16)):
                selected = cases.case(tokens, heads)
                summary = dict(status='ISOLATED_CHUNK_COMPLETE_UNCOMPARED', output_elements=selected['elements'])
                scope = dict(summary=summary, record={'terminal_count': 1}, run=run, selected=selected)
                if heads == 1:
                    self.assertTrue(eval(code, {'__builtins__': {}}, scope))
                else:
                    for completed in (None, 0, 2, 31, 32, 33):
                        summary['actual_chunks_completed'] = completed
                        self.assertIs(eval(code, {'__builtins__': {}}, scope), completed == 32)
                    scope['record']['terminal_count'] = 2
                    summary['actual_chunks_completed'] = 32
                    self.assertFalse(eval(code, {'__builtins__': {}}, scope))

    def test_child_record_fsyncs_file_before_replace_then_directory(self):
        # Import and exercise only the stdlib record writer, never child main.
        child = runpy.run_path(str(HERE / 'chunk_child.py'), run_name='import_only')
        events = []
        fsync, replace = os.fsync, os.replace
        def record_fsync(fd):
            events.append('directory' if stat.S_ISDIR(os.fstat(fd).st_mode) else 'file')
            fsync(fd)
        def record_replace(source, target):
            events.append('replace')
            replace(source, target)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'progress.json'
            with patch.object(os, 'fsync', record_fsync), patch.object(os, 'replace', record_replace):
                child['save'](target, {'head_chunk_completions': 32})
            self.assertEqual(json.loads(target.read_text()), {'head_chunk_completions': 32})
            self.assertFalse(target.with_suffix('.json.tmp').exists())
        self.assertEqual(events, ['file', 'replace', 'directory'])
        self.assertNotIn('candidates.qwen35_gdn_prefill.chunk.model', sys.modules)

    def test_cli_help_never_requires_native_dependencies(self):
        for name in ('prepare_chunk.py', 'launch_chunk.py', 'compare_chunk.py', 'diagnose_prep_g.py'):
            result = subprocess.run([sys.executable, '-I', '-S', '-B', str(HERE / name), '--help'],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
        # Import the child under its exact isolated flags without entering main,
        # reading any plan, loading native code, or constructing an owner.
        command = f"import runpy; runpy.run_path({str(HERE / 'chunk_child.py')!r}, run_name='import_only')"
        result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', command],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('numpy', sys.modules)
        self.assertNotIn('candidates.qwen35_gdn_prefill.chunk.model', sys.modules)

    def test_comparator_cli_all_cases_and_cleanup_fail_closed(self):
        # Synthetic control fixtures, not candidate/native/model execution evidence.
        for tokens, heads in ((64, 1), (128, 1), (128, 16)):
            with self.subTest(tokens=tokens, heads=heads), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); run = root / 'run'; actual = run / 'actual'; actual.mkdir(parents=True)
                plan = plan_for(tokens, heads)
                output = struct.pack('<H', 0x3f80) * (tokens * heads * 128)
                state = struct.pack('<f', 1.0) * (heads * 16384)
                for path, raw in ((actual / 'output.bf16le', output), (actual / 'state.fp32le', state),
                                  (root / 'reference.bf16le', output), (root / 'state-reference', state)):
                    path.write_bytes(raw)
                plan.update(run_directory=str(run), reference_slice=str(root / 'reference.bf16le'), inputs={})
                if tokens == 128:
                    plan['reference_state_slice'] = str(root / 'state-reference')
                for path in (root / 'reference.bf16le', root / 'state-reference'):
                    plan['inputs'][str(path)] = dict(comparator.pin(path), resolved=str(path.resolve()))
                plan_path = root / 'PLAN.json'; plan_path.write_text(json.dumps(plan))
                plan_sha = hashlib.sha256(plan_path.read_bytes()).hexdigest()
                summary = dict(output_reference_read=False, state_oracle_available=tokens == 128,
                    owner={'production_geometry': heads == 16}, terminal_count=1, elapsed_seconds=0,
                    output_sha256=comparator.sha(output), state_sha256=comparator.sha(state),
                    actual_chunks_completed=heads * 2,
                    observed_second_chunk_prior_state_read_beats=(cases.CARRY_READ_BEATS if heads == 1 else
                        {str(h): cases.CARRY_READ_BEATS for h in range(heads)}),
                    first_chunk_state_sha256=('synthetic-fixture' if heads == 1 else
                        {str(h): 'synthetic-fixture' for h in range(heads)}))
                (actual / 'summary.json').write_text(json.dumps(summary))
                proof = dict(status='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP', empty_complete_scans=2,
                             direct_leader_reaped=True, direct_exit_code=0)
                launch = dict(isolated_component_complete_uncompared=True, natural_exit=True,
                    cleanup_confirmed=True, returncode=0, failure=None, all_frozen_actual_inputs_unchanged=True,
                    plan_sha256=plan_sha, cleanup_proof=proof, elapsed_seconds=0, observed_peak_rss_bytes=0)
                (run / 'LAUNCH.json').write_text(json.dumps(launch)); (run / 'CLEANUP.json').write_text(json.dumps(proof))
                argv = ['compare_chunk.py', '--plan', str(plan_path), '--reviewed-plan-sha256', plan_sha,
                        '--output', str(root / 'comparison.json')]
                with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(io.StringIO()):
                    comparator.main()
                report = json.loads((root / 'comparison.json').read_text())
                self.assertEqual(report['elements'], tokens * heads * 128)
                self.assertEqual(report['status'], f"ISOLATED_{'ALL16' if heads == 16 else 'HEAD0'}_M{tokens}_COMPARISON_COMPLETE")
                self.assertFalse(report['full_block_acceptance'])
                self.assertTrue(report['meets_existing_node_thresholds'])
                if tokens == 64:
                    self.assertIsNone(report['state_numerical_validation'])
                    self.assertIn('state_unvalidated_pin', report)
                else:
                    self.assertEqual(report['state_numerical_validation']['violations'], 0)
                    self.assertEqual(report['state_numerical_validation']['elements'], heads * 16384)
                    self.assertFalse(report['after64_state_oracle_available'])
                    self.assertNotIn('state_unvalidated_pin', report)
                launch['cleanup_confirmed'] = False
                (run / 'LAUNCH.json').write_text(json.dumps(launch))
                with patch.object(sys, 'argv', argv), self.assertRaisesRegex(ValueError, 'supervised component admission'):
                    comparator.main()


if __name__ == '__main__':
    unittest.main()
