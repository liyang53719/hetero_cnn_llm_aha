"""Stdlib control tests only. Synthetic receipts never certify native arithmetic."""
import ast
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import runpy
import struct
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import suffix_case as cases
import prepare_suffix as preparation
import compare_suffix as comparator
import launch_chunk as supervisor
from suffix_git_guard import SourceGitGuard

HERE = Path(__file__).resolve().parent


def plan_for(name):
    selected = cases.case(name)
    plan = {key: copy.deepcopy(selected[key]) for key in ('schema', 'policy', 'limits', 'addresses', 'stages')}
    plan.update(case=name, inputs={}, git_source_identity={'expected_calls': selected['git_calls']})
    for section in ('stage_inputs', 'references'):
        plan[section] = {}
        for key, expected in selected[section].items():
            item = {field: expected[field] for field in ('bytes', 'sha256')}; item['path'] = section + '/' + key
            plan[section][key] = item
            plan['inputs'][item['path']] = {field: expected[field] for field in ('bytes', 'sha256')}
    return plan


def receipt_fixture(stage):
    name = 'residual_post_norm' if stage in ('attention_residual', 'post_norm') else stage
    plan = plan_for(name); count = plan['references'][stage]['bytes']; prior = 'synthetic-prior'
    keys = {'gated_norm': ('core', 'z', 'weight'), 'o': ('gated_norm', 'weight_kn'),
            'attention_residual': ('hidden', 'o'), 'post_norm': ('weight',)}[stage]
    hashes = [plan['stage_inputs'][key]['sha256'] for key in keys]
    if stage == 'post_norm':
        hashes.insert(0, prior)
    summary = dict(stage=stage, status='ISOLATED_STAGE_COMPLETE_UNCOMPARED', terminal_count=1, complete=True,
        output_published=True, block_generation=0, aborted_for_deadline=False, input_sha256=hashes, output_sha256='fixture',
        accepted_write_beats=count//64, accepted_ack_beats=count//64, **{key: False for key in comparator.SCOPE_FLAGS})
    if stage == 'o':
        summary.update(response=[90, None, count], numeric_fault=None, executed_fmas=268435456,
            counts=dict(steps=65536, a_read_beats=8192, b_read_beats=65536, write_data_bytes=count, ack_bytes=count, done=7, results=32),
            matrix=dict(counters=dict(owner_acquires=1, owner_releases=1, owner_responses=1), dense_fma_calls=268435456,
                normal_fma_calls=0, same_accumulator_resource=True, reset_required=False),
            workspace_metadata=dict(base=0x1000000, extent=524288, generation=1, prefix_bytes=0, memory_region_allocated=False))
    else:
        reads = {'gated_norm': 16392, 'attention_residual': 8192, 'post_norm': 4128}[stage]
        summary.update(response=dict(status=None, write_bytes=count, tag={'gated_norm': 80, 'attention_residual': 100, 'post_norm': 110}[stage]),
            staging_complete=True, scalar_arithmetic_binding=dict(implementation='DecayScalar', enable_ieee_exp=True, enable_softplus=True),
            owner=dict(scalar_calls=comparator.SCALAR_CALLS[stage], accepted=dict(read_requests=reads, write_requests=count//64,
                write_acks=count//64, memory_responses=reads+count//64, owner_results=1), production_geometry=True, active_heads=16,
                operation='Add', hidden_width=1024, test_geometry=False, identity={'policy': 'torch210_cpu_default1024'}))
    terminal = {key: copy.deepcopy(summary[key]) for key in ('stage', 'response', 'input_sha256', 'output_sha256', 'output_published')}
    terminal.update(status='STAGE_COMPLETE_UNCOMPARED', plan_sha256='fixture-plan', real_owner_terminal=True,
                    terminal_count=1, output_bytes=count)
    return plan, summary, terminal, prior


class SuffixTests(unittest.TestCase):
    def test_only_three_fixed_cases_and_policies(self):
        for name in cases.NAMES:
            selected = cases.plan_case(plan_for(name))
            self.assertEqual((selected['tokens'], selected['driver_seconds'], selected['outer_seconds']), (128, 180, 210))
            self.assertEqual(selected['limits']['address_space_bytes'], 1 << 30)
            self.assertEqual(supervisor.plan_case(plan_for(name)), selected)
        for name in ('post_norm', 'final_residual', 'gate_up', 128, True, None):
            with self.assertRaises(ValueError):
                cases.case(name)
        self.assertFalse(cases.case('o')['policy']['independent_k512_applied'])
        self.assertEqual(cases.case('residual_post_norm')['policy']['rms_policy'], 'torch210_cpu_default1024')

    def test_configuration_and_every_input_pin_fail_closed(self):
        for name in cases.NAMES:
            original = plan_for(name)
            for field in ('schema', 'policy', 'limits', 'addresses', 'stages'):
                plan = copy.deepcopy(original); plan[field] = None
                with self.subTest(name=name, field=field), self.assertRaises((ValueError, TypeError)):
                    cases.plan_case(plan)
            for section in ('stage_inputs', 'references'):
                for key in original[section]:
                    plan = copy.deepcopy(original); plan[section][key]['sha256'] = 'altered'
                    with self.assertRaises(ValueError):
                        cases.plan_case(plan)
                    plan = copy.deepcopy(original); del plan['inputs'][plan[section][key]['path']]
                    with self.assertRaises(ValueError):
                        cases.plan_case(plan)
            plan = copy.deepcopy(original); plan['git_source_identity']['expected_calls'] = {'arbitrary': 1}
            with self.assertRaises(ValueError):
                cases.plan_case(plan)

    def test_opaque_uint16_transpose_not_numeric_conversion(self):
        words = [0, 0x8000, 0x7fc1, 0x7f80, 0xffff, 0x1234]
        raw = struct.pack('<6H', *words)
        self.assertEqual(struct.unpack('<6H', preparation.transpose_words(raw, 2, 3)),
                         (words[0], words[3], words[1], words[4], words[2], words[5]))
        with self.assertRaises(ValueError):
            preparation.transpose_words(raw[:-2], 2, 3)

    def test_cli_requires_explicit_inputs_and_matrix_only_for_o(self):
        options = ('repository', 'runtime-site', 'python', 'compiler', 'inputs', 'references', 'output')
        common = [value for option in options for value in ('--' + option, 'not-opened')] + ['--cpu', '0']
        matrix = ['--matrix-library', 'elf', '--matrix-receipt', 'receipt']
        for name in cases.NAMES:
            self.assertEqual(preparation.parse_args(common + ['--case', name] + (matrix if name == 'o' else [])).case, name)
        for suffix in (['--case', 'o'], ['--case', 'gated_norm'] + matrix, ['--case', 'post_norm'],
                       ['--case', 'o', '--matrix-library', 'elf']):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                preparation.parse_args(common + suffix)

    def test_exact_isolated_entrypoints_and_import_only_child(self):
        for filename in ('prepare_suffix.py', 'suffix_child.py', 'compare_suffix.py', 'launch_chunk.py'):
            completed = subprocess.run([sys.executable, '-I', '-S', '-B', str(HERE/filename), '--help'],
                                       capture_output=True, text=True, timeout=10)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn('usage:', completed.stdout)
        source = ('import runpy,sys; runpy.run_path(' + repr(str(HERE/'suffix_child.py')) + ",run_name='import_only'); "
                  "assert not any(x.split('.')[0] in ('numpy','torch','candidates') for x in sys.modules)")
        result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', source], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_supervised_admission_rejects_every_incomplete_field(self):
        proof = dict(status='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP', empty_complete_scans=2,
                     direct_leader_reaped=True, direct_exit_code=0)
        launch = dict(plan_sha256='fixture', isolated_component_complete_uncompared=True, natural_exit=True,
            cleanup_confirmed=True, returncode=0, failure=None, all_frozen_actual_inputs_unchanged=True, cleanup_proof=proof)
        cleanup = dict(cleanup_complete=True, proof=copy.deepcopy(proof))
        comparator.supervised_admission(launch, cleanup, 'fixture')
        for key in launch:
            bad = copy.deepcopy(launch); bad[key] = 'fixture failure' if key == 'failure' else None
            with self.subTest(key=key), self.assertRaises((ValueError, TypeError)):
                comparator.supervised_admission(bad, cleanup, 'fixture')
        for key in proof:
            bad = copy.deepcopy(launch); bad['cleanup_proof'][key] = None
            with self.assertRaises(ValueError):
                comparator.supervised_admission(bad, cleanup, 'fixture')
        with self.assertRaises(ValueError):
            comparator.supervised_admission(launch, dict(cleanup_complete=True, proof={}), 'fixture')

    def test_completion_requires_both_real_stage_files_and_counts(self):
        selected = cases.case('residual_post_norm')
        with tempfile.TemporaryDirectory() as folder:
            actual = Path(folder)
            summary = dict(status='ISOLATED_SUFFIX_COMPLETE_UNCOMPARED', completed_stages=selected['stages'], terminal_count=2, block_generation=0)
            for stage in selected['stages']:
                (actual/stage).mkdir(); (actual/stage/'STAGE_TERMINAL.json').write_text('{}')
                (actual/stage/'output.bf16le').write_bytes(bytes(262144))
            self.assertTrue(cases.complete(summary, actual, selected))
            for key, value in (('completed_stages', ['attention_residual']), ('terminal_count', 1), ('block_generation', 1)):
                self.assertFalse(cases.complete(dict(summary, **{key: value}), actual, selected))
            (actual/'post_norm/output.bf16le').write_bytes(bytes(262142))
            self.assertFalse(cases.complete(summary, actual, selected))
            (actual/'post_norm/STAGE_TERMINAL.json').unlink()
            self.assertFalse(cases.complete(summary, actual, selected))

    def test_all_four_stage_admissions_and_forged_terminal_rejection(self):
        for stage in ('gated_norm', 'o', 'attention_residual', 'post_norm'):
            plan, summary, terminal, prior = receipt_fixture(stage)
            comparator.stage_admission(stage, summary, terminal, plan, 'fixture-plan', prior)
            for key, value in (('real_owner_terminal', False), ('plan_sha256', 'wrong'), ('input_sha256', []),
                               ('output_bytes', 0), ('output_sha256', 'wrong')):
                bad = copy.deepcopy(terminal); bad[key] = value
                with self.subTest(stage=stage, field=key), self.assertRaises(ValueError):
                    comparator.stage_admission(stage, summary, bad, plan, 'fixture-plan', prior)
            for key in comparator.SCOPE_FLAGS:
                bad = copy.deepcopy(summary); bad[key] = True
                with self.assertRaises(ValueError):
                    comparator.stage_admission(stage, bad, terminal, plan, 'fixture-plan', prior)
            bad = copy.deepcopy(summary); bad['input_sha256'] = ['wrong']; altered = dict(terminal, input_sha256=['wrong'])
            with self.assertRaises(ValueError):
                comparator.stage_admission(stage, bad, altered, plan, 'fixture-plan', prior)

    def test_recipe_counts_and_policy_fail_closed(self):
        for stage in ('gated_norm', 'attention_residual', 'post_norm'):
            plan, summary, terminal, prior = receipt_fixture(stage)
            summary['owner']['scalar_calls'] = {}
            with self.assertRaises(ValueError):
                comparator.stage_admission(stage, summary, terminal, plan, 'fixture-plan', prior)
        plan, summary, terminal, prior = receipt_fixture('o'); summary['executed_fmas'] -= 1
        with self.assertRaises(ValueError):
            comparator.stage_admission('o', summary, terminal, plan, 'fixture-plan', prior)
        plan, summary, terminal, prior = receipt_fixture('post_norm'); summary['owner']['identity']['policy'] = 'changed'
        with self.assertRaises(ValueError):
            comparator.stage_admission('post_norm', summary, terminal, plan, 'fixture-plan', prior)

    def test_finite_bf16_metrics_signed_zero_and_last_element(self):
        report = comparator.metrics(b'\x00\x80', b'\x00\x00', 'o', 2)
        self.assertEqual((report['bit_mismatches'], report['numerical_mismatches'], report['max_abs']), (1, 0, 0))
        for word in (0x7f80, 0x7fc1, 0xff80):
            with self.assertRaises(ValueError):
                comparator.metrics(struct.pack('<H', word), b'\x00\x00', 'o', 2)
        with self.assertRaises(ValueError):
            comparator.metrics(b'', b'', 'o', 2)
        actual = bytes(262142) + struct.pack('<H', 0x3f80)
        report = comparator.metrics(actual, bytes(262144), 'post_norm', 262144)
        self.assertEqual(report['worst_location'], dict(batch=0, token=127, column=1023))
        self.assertFalse(report['meets_existing_node_thresholds'])

    def test_git_allowlist_without_starting_git(self):
        name = next(iter(cases.case('gated_norm')['git_calls']))
        with tempfile.TemporaryDirectory() as folder:
            plan = dict(repository=folder, case='gated_norm', git_source_identity=dict(expected_calls={name: 2}, execution_pins={}))
            with patch.dict(os.environ, {'PATH': '/usr/bin:/bin'}, clear=True):
                guard = SourceGitGuard(plan, dict(os.environ), Path(folder)/'log')
                for bad in (['git', 'status'], ['git', 'show', 'HEAD:other'], ['git', 'show', 'HEAD:'+name, '--extra']):
                    with self.assertRaises(RuntimeError):
                        guard.audit('subprocess.Popen', ('git', bad, folder, None))
                for _ in range(2):
                    guard.audit('subprocess.Popen', ('git', ['git', 'show', 'HEAD:'+name], folder, None))
                self.assertTrue(guard.report()['complete'])
                with self.assertRaises(RuntimeError):
                    guard.audit('subprocess.Popen', ('git', ['git', 'show', 'HEAD:'+name], folder, None))

    def test_drain_guard_precedes_constructor_scalar_acquisition(self):
        module = runpy.run_path(str(HERE/'suffix_child.py'), run_name='import_only')
        memory = SimpleNamespace(pending=None); scalar = SimpleNamespace(client=None); owner = object(); called = []
        def factory():
            self.assertIsNone(scalar.client)
            scalar.client = owner; called.append('constructor'); return owner
        self.assertIs(module['construct_driver'](factory, memory, scalar), owner)
        self.assertIs(scalar.client, owner)
        self.assertEqual(called, ['constructor'])
        with self.assertRaises(ValueError):
            module['construct_driver'](factory, memory, scalar)
        scalar.client = None; memory.pending = object()
        with self.assertRaises(ValueError):
            module['construct_driver'](factory, memory, scalar)
        self.assertEqual(called, ['constructor'])

    def test_native_constructors_remain_delayed_and_fixed(self):
        source = (HERE/'suffix_child.py').read_text(); tree = ast.parse(source)
        top = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]
        self.assertFalse(any(isinstance(node, ast.ImportFrom) and (node.module or '').startswith('candidates.') for node in top))
        self.assertIn('ReductionPolicy.Torch210CpuDefault1024', source)
        self.assertIn('m=128, k=2048, n=1024', source)
        self.assertNotIn('IndependentK512', source)
        self.assertNotIn('.preflight_response(', source)
        self.assertIn('driver.input is previous.output', source)
        self.assertIn('driver.input.storage is previous.output.storage', source)


if __name__ == '__main__':
    unittest.main()
