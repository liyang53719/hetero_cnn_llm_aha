"""Pure-stdlib mapping, admission, CLI, and comparator tests; no native owner runs."""
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import chunk_case as cases
import compare_chunk as comparator
import prepare_chunk as preparation

HERE = Path(__file__).resolve().parent


def plan_for(tokens):
    selected = cases.case(tokens)
    plan = dict(schema=selected['schema'], policy={'tokens': tokens},
                limits=dict(cpu_seconds=selected['driver_seconds'],
                            driver_wall_seconds=selected['driver_seconds'],
                            outer_wall_seconds=selected['outer_seconds']))
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
            mapped = cases.head0_output(reference, tokens)
            expected = b''.join(struct.pack('<H', row * 16) * 128 for row in range(tokens))
            self.assertEqual(mapped, expected)
        with self.assertRaises(ValueError):
            cases.head0_output(reference[:-2], 128)

    def test_prep_row_extent_and_selection(self):
        prep = b''.join(bytes([row]) * cases.PREP_ROW_BYTES for row in range(128))
        self.assertEqual(cases.prep_rows(prep, 64), prep[:64 * cases.PREP_ROW_BYTES])
        self.assertEqual(cases.prep_rows(prep, 128), prep)
        with self.assertRaises(ValueError):
            cases.prep_rows(prep[:-1], 64)

    def test_head0_state_contiguous_mapping_and_cache_identity(self):
        state = b''.join(bytes([head]) * cases.STATE_BYTES for head in range(16))
        self.assertEqual(cases.head0_state(state, state), bytes(cases.STATE_BYTES))
        for altered in (state[:-1], state[:-1] + b'X'):
            with self.assertRaises(ValueError):
                cases.head0_state(state, altered)
        with self.assertRaises(ValueError):
            cases.head0_state(state[:-1], state[:-1])

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

    def test_cli_default_and_m128_mandatory_state_inputs(self):
        options = ('repository', 'runtime-site', 'python', 'vector-library', 'vector-metadata',
                   'compiler', 'saved-prep', 'saved-pins', 'saved-progress', 'official-output', 'output')
        argv = [argument for option in options for argument in ('--' + option, 'not-opened')]
        argv += ['--cpu', '0']
        self.assertEqual(preparation.parse_args(argv).tokens, 64)
        state = ['--official-state', 'state', '--official-final-cache', 'cache', '--official-manifest', 'manifest']
        self.assertEqual(preparation.parse_args(argv + ['--tokens', '128'] + state).tokens, 128)
        for extra in (['--tokens', '128'], ['--tokens', '256'], state):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                preparation.parse_args(argv + extra)
            self.assertEqual(error.exception.code, 2)

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

    def test_comparator_cli_both_cases_and_cleanup_fail_closed(self):
        # Synthetic control fixtures, not candidate/native/model execution evidence.
        for tokens in cases.TOKENS:
            with self.subTest(tokens=tokens), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); run = root / 'run'; actual = run / 'actual'; actual.mkdir(parents=True)
                plan = plan_for(tokens)
                output = struct.pack('<H', 0x3f80) * (tokens * 128)
                state = struct.pack('<f', 1.0) * 16384
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
                    owner={'production_geometry': False}, terminal_count=1, elapsed_seconds=0,
                    output_sha256=comparator.sha(output), state_sha256=comparator.sha(state),
                    actual_chunks_completed=2, observed_second_chunk_prior_state_read_beats=cases.CARRY_READ_BEATS,
                    first_chunk_state_sha256='synthetic-fixture')
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
                self.assertEqual(report['elements'], tokens * 128)
                self.assertFalse(report['full_block_acceptance'])
                self.assertTrue(report['meets_existing_node_thresholds'])
                if tokens == 64:
                    self.assertIsNone(report['state_numerical_validation'])
                    self.assertIn('state_unvalidated_pin', report)
                else:
                    self.assertEqual(report['state_numerical_validation']['violations'], 0)
                    self.assertFalse(report['after64_state_oracle_available'])
                    self.assertNotIn('state_unvalidated_pin', report)
                launch['cleanup_confirmed'] = False
                (run / 'LAUNCH.json').write_text(json.dumps(launch))
                with patch.object(sys, 'argv', argv), self.assertRaisesRegex(ValueError, 'supervised component admission'):
                    comparator.main()


if __name__ == '__main__':
    unittest.main()
