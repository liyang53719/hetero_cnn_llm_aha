"""Additional stdlib-only fixed suffix/seed/threshold/chain tests, no native run."""
import contextlib
import copy
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import unittest
from unittest.mock import patch

import check_cold_chain
import compare_suffix as comparator
import prepare_suffix as preparation
import suffix_case as cases
from test_suffix_cases import plan_for, receipt_fixture

HERE = Path(__file__).resolve().parent


def fixture(stage):
    name = 'gate_up' if stage in ('gate', 'up') else 'final_triplet'
    plan = plan_for(name); count = plan['references'][stage]['bytes']; prior = 'synthetic-prior'
    _, summary, terminal, _ = receipt_fixture('o' if stage in cases.DENSE_STAGES else 'attention_residual')
    keys = {'gate': ('post_norm', 'gate_weight_kn'), 'up': ('post_norm', 'up_weight_kn'),
            'silu_mul': ('gate', 'up'), 'down': ('weight_kn',), 'output': ('attention_residual',)}[stage]
    hashes = [plan['stage_inputs'][key]['sha256'] for key in keys]
    if stage in ('down', 'output'):
        hashes.insert(0 if stage == 'down' else 1, prior)
    summary.update(stage=stage, input_sha256=hashes, accepted_write_beats=count//64, accepted_ack_beats=count//64)
    if stage in cases.DENSE_STAGES:
        down = stage == 'down'; cumulative = 2 if stage == 'up' else 1
        summary.update(response=[{'gate': 120, 'up': 130, 'down': 150}[stage], None, count], executed_fmas=469762048,
            counts=dict(steps=114688, a_read_beats=14336 if down else 4096, b_read_beats=114688,
                write_data_bytes=count, ack_bytes=count, done=14 if down else 23, results=64 if down else 112),
            workspace_metadata=dict(base=0x4000000, extent=524288, generation=1, prefix_bytes=0, memory_region_allocated=False))
        summary['matrix'].update(dense_fma_calls=469762048*cumulative,
            counters=dict(owner_acquires=cumulative, owner_releases=cumulative, owner_responses=cumulative))
        if down:
            summary.update(prefix_bytes=524288, prefix_extent=524288, prefix_version=[150, 1, 0, 1, 2560], prefix_published=False)
            summary['counts'].update(prefix_ack_bytes=524288, prefix_read_beats=8192, prefix_write_data_bytes=524288,
                                    seed_acks=32, seed_beats=8192, seed_begins=32, seed_errors=0)
            summary['matrix']['counters']['dense_seed_acks'] = 32
    else:
        reads = 28672 if stage == 'silu_mul' else 8192
        summary['response'].update(tag=140 if stage == 'silu_mul' else 160, write_bytes=count)
        summary['owner'].update(scalar_calls=comparator.SCALAR_CALLS[stage],
            operation='SiluMul' if stage == 'silu_mul' else 'Add', ffn_width=3584,
            accepted=dict(read_requests=reads, write_requests=count//64, write_acks=count//64,
                          memory_responses=reads+count//64, owner_results=1))
    terminal.update(stage=stage, response=copy.deepcopy(summary['response']), input_sha256=hashes, output_bytes=count)
    return plan, summary, terminal, prior


class FinalSuffixTests(unittest.TestCase):
    def test_all_new_stage_admissions_and_input_order(self):
        for stage in ('gate', 'up', 'silu_mul', 'down', 'output'):
            plan, summary, terminal, prior = fixture(stage)
            comparator.stage_admission(stage, summary, terminal, plan, 'fixture-plan', prior)
            for key in ('complete', 'output_published'):
                bad = copy.deepcopy(summary); bad[key] = False
                with self.assertRaises(ValueError):
                    comparator.stage_admission(stage, bad, terminal, plan, 'fixture-plan', prior)
            with self.assertRaises(ValueError):
                comparator.stage_admission(stage, summary, dict(terminal, real_owner_terminal=False), plan, 'fixture-plan', prior)
            if stage in ('down', 'output'):
                with self.assertRaises(ValueError):
                    comparator.stage_admission(stage, summary, terminal, plan, 'fixture-plan', 'wrong')

    def test_seed_prefix_and_matrix_counts_fail_closed(self):
        plan, summary, terminal, prior = fixture('down')
        for key in ('prefix_ack_bytes', 'prefix_read_beats', 'prefix_write_data_bytes', 'seed_acks', 'seed_beats', 'seed_begins', 'seed_errors'):
            bad = copy.deepcopy(summary); bad['counts'][key] += 1
            with self.subTest(field=key), self.assertRaises(ValueError):
                comparator.stage_admission('down', bad, terminal, plan, 'fixture-plan', prior)
        for key, value in (('prefix_published', True), ('prefix_version', 0), ('prefix_extent', 0)):
            bad = dict(summary, **{key: value})
            with self.assertRaises(ValueError):
                comparator.stage_admission('down', bad, terminal, plan, 'fixture-plan', prior)
        plan, summary, terminal, prior = fixture('up'); summary['matrix']['dense_fma_calls'] = 469762048
        with self.assertRaises(ValueError):
            comparator.stage_admission('up', summary, terminal, plan, 'fixture-plan', prior)

    def test_genuine_saved_down_prefix_version_schema(self):
        receipt = json.loads((HERE/'down_receipt_fixture.json').read_text())
        summary = receipt['summary']; terminal = receipt['terminal']; plan = plan_for('final_triplet')
        pins = cases.case('final_triplet')['historical_artifacts']
        for relative, recorded in receipt['source_pins'].items():
            self.assertEqual(recorded, pins[relative])
        self.assertEqual(summary['prefix_version'], [150, 1, 0, 1, 2560])
        comparator.stage_admission('down', summary, terminal, plan, terminal['plan_sha256'], summary['input_sha256'][0])
        versions = [1, [150, 1, 0, 1], [150, True, 0, 1, 2560], tuple(summary['prefix_version'])]
        for index in range(5):
            changed = list(summary['prefix_version']); changed[index] += 1; versions.append(changed)
        for version in versions:
            with self.subTest(prefix_version=version), self.assertRaises(ValueError):
                comparator.stage_admission('down', dict(summary, prefix_version=version), terminal, plan,
                                           terminal['plan_sha256'], summary['input_sha256'][0])

    def test_final_output_gate_is_distinct(self):
        actual = struct.pack('<H', 0x3d20) + bytes(14)  # 0.0390625 maximum, 0.0048828125 mean
        self.assertTrue(comparator.metrics(actual, bytes(16), 'output', 16)['meets_existing_node_thresholds'])
        self.assertFalse(comparator.metrics(actual, bytes(16), 'down', 16)['meets_existing_node_thresholds'])
        self.assertFalse(comparator.metrics(actual[:2], bytes(2), 'output', 2)['meets_existing_node_thresholds'])
        for stage in ('gate', 'up', 'silu_mul'):
            report = comparator.metrics(bytes(7166)+struct.pack('<H', 0x3f80), bytes(7168), stage, 7168)
            self.assertEqual(report['worst_location'], dict(batch=0, token=0, column=3583))

    def test_new_cases_exact_transposes_and_git_allowance(self):
        self.assertEqual(cases.TRANSPOSES['final_triplet'], {'weight_kn': ('weight_nk', 1024, 3584)})
        self.assertEqual(set(cases.TRANSPOSES['gate_up']), {'gate_weight_kn', 'up_weight_kn'})
        self.assertEqual(sum(cases.case('final_triplet')['git_calls'].values()), 4)
        self.assertEqual(cases.case('gate_up')['git_calls'], {})
        common = [x for key in ('repository','runtime-site','python','compiler','inputs','references','output')
                  for x in ('--'+key, 'not-opened')] + ['--cpu', '0']
        for name in ('gate_up', 'final_triplet'):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                preparation.parse_args(common + ['--case', name])

    def test_chain_manifest_sanitized_and_scope_is_not_completion(self):
        spec = json.loads((HERE/'cold_chain_pins.json').read_text())
        self.assertEqual((len(spec['actual_boundary_edges']), len(spec['observed_artifacts'])), (13, 62))
        self.assertEqual(spec['original_execution_status'], 'UNKNOWN')
        self.assertFalse(spec['completion_seal']); self.assertFalse(spec['full_block_acceptance'])
        self.assertFalse(spec['prep_threshold_assigned'])
        self.assertEqual(spec['node_metrics']['output']['thresholds'], dict(max_abs=.05, mean_abs=.01))
        for text in ((HERE/'cold_chain_pins.json').read_text(), (HERE/'suffix_pins.json').read_text()):
            self.assertNotIn('/workspace/', text); self.assertNotIn('qwen35_saved_', text)
        with self.assertRaises(ValueError):
            check_cold_chain.check({})

    def test_chain_cli_and_original_arithmetic_stay_delayed(self):
        result = subprocess.run([sys.executable, '-I', '-S', '-B', str(HERE/'check_cold_chain.py'), '--help'],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        source = (HERE/'suffix_child.py').read_text()
        self.assertIn('TypedSeededDenseDriver(owner, matrix, memory, job)', source)
        self.assertIn('owner.workspace.split_k == 2560', source)
        self.assertIn('driver.pending_seed_ack is None and driver.active_seed is None', source)
        self.assertIn('region.written == region.acknowledged', source)


if __name__ == '__main__':
    unittest.main()
