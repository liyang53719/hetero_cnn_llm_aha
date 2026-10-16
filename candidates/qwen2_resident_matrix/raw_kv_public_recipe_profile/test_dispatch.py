"""Cold synthetic metadata checks. No arrays, native library or runtime launch."""

import builtins
import copy
import importlib
import os
import sys
import unittest
from unittest.mock import patch

from . import dispatch
from ..raw_kv_native_qk_run import dispatch_diagnostic as diagnostic
from ..raw_kv_native_qk_run import phase
from ..raw_kv_native_qk_run.test_phase import diagnostics_fixture, report_fixture


def context_for(pair):
    """Synthetic test context only; production must independently bind its run."""
    small, small_diagnostics, large, large_diagnostics = pair
    shared = {key: small[key] for key in dispatch.SHARED_REPORT_HASHES}
    shared['payload_tensor_map_sha256'] = small_diagnostics['payload_tensor_map_sha256']
    result = dict(schema=1, profile=dispatch.PROFILE, shared=shared)
    for name, report, observed in (
            ('native16', small, small_diagnostics),
            ('native128', large, large_diagnostics)):
        result[name] = dict(
            result_sha256=report['result_sha256'],
            source_manifest_sha256=report['source_manifest_sha256'],
            report_sha256=phase.kernel.sha(phase.kernel.encoded(report)),
            diagnostics_sha256=phase.kernel.sha(phase.kernel.encoded(observed)),
        )
    return result


def pair_fixture(cause=None, failed_tokens=16):
    pair = []
    for tokens in (16, 128):
        failure = cause if tokens == failed_tokens else None
        report = report_fixture(tokens, failure)
        observed = diagnostics_fixture(tokens, failure)
        # Distinct result hashes are required for these two distinct shapes.
        digest = ('4' if tokens == 16 else 'a') * 64
        report['result_sha256'] = observed['result_sha256'] = digest
        report['m16_result_sha256'] = None if tokens == 16 else '4' * 64
        for record in observed['capture']['bf16']['records']:
            record['implementation'] = dispatch.IMPLEMENTATION
            record['isa'] = dispatch.ISA
        pair.extend((report, observed))
    return pair


class DispatchPrerequisiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = pair_fixture()
        cls.bound_context = context_for(cls.baseline)

    def fresh(self):
        return copy.deepcopy(self.baseline), copy.deepcopy(self.bound_context)

    def reject(self, pair, context=None):
        if context is None:
            context = context_for(pair)
        with self.assertRaises(ValueError):
            dispatch.validate_pair(*pair, context=context)

    def test_accepts_complete_exact_native_pair_as_prerequisite_only(self):
        pair, context = self.fresh()
        before = copy.deepcopy((pair, context))
        result = dispatch.validate_pair(*pair, context=context)
        self.assertEqual(result['profile'], 'qwen2-public-pv16-native-pair-avx512bf16-v1')
        self.assertEqual(result['status'], 'NUMERICAL_PREREQUISITE_ONLY')
        self.assertIs(result['native_numerical_prerequisite_passed'], True)
        self.assertIs(result['preparation_only'], True)
        for key in ('runtime_ready', 'actual_chain_executed', 'public_execution',
                    'backend_order_proven', 'rtl_execution', 'full_29_node_acceptance'):
            self.assertIs(result[key], False)
        self.assertEqual(result['tokens'], [16, 128])
        self.assertEqual(result['bf16_matmuls_per_shape'], 9)
        self.assertEqual(result['stages_per_mode'], 29)
        self.assertEqual(result['semantics_per_mode'], 9)
        self.assertEqual(result['native16'], context['native16'])
        self.assertEqual(result['native128'], context['native128'])
        self.assertEqual(result['shared'], context['shared'])
        self.assertEqual(result['m16_result_sha256'], pair[0]['result_sha256'])
        self.assertLessEqual(len(phase.kernel.encoded(result)), dispatch.MAX_SUMMARY_BYTES)
        self.assertNotIn('PRIVATE', phase.kernel.encoded(result).decode())
        self.assertEqual((pair, context), before)
        result['shared']['library_sha256'] = '0' * 64
        self.assertEqual((pair, context), before)

    def test_requires_original_numerical_pass_for_both_shapes_and_modes(self):
        for tokens in (16, 128):
            for cause in ('budget', 'bf16_semantics', 'fp32_semantics'):
                with self.subTest(tokens=tokens, cause=cause):
                    pair = pair_fixture(cause, tokens)
                    self.assertEqual(pair[1 if tokens == 16 else 3]['status'], 'COMPLETE_DIAGNOSTICS')
                    self.reject(pair)

    def test_original_stage_semantic_policy_and_boolean_validation_is_preserved(self):
        for slot in (0, 2):
            for case in ('stage_missing', 'stage_extra', 'semantic_missing',
                         'semantic_extra', 'mode_missing', 'mode_extra', 'limit',
                         'stage_verdict', 'acceptance_type', 'carried', 'postflight',
                         'count', 'claim', 'private_extra'):
                pair, _ = self.fresh()
                report = pair[slot]
                if case == 'stage_missing': report['bf16_stages'].pop('gate')
                elif case == 'stage_extra': report['bf16_stages']['extra'] = copy.deepcopy(report['bf16_stages']['gate'])
                elif case == 'semantic_missing': report['modes']['fp32']['semantics'].pop('mask_exact')
                elif case == 'semantic_extra': report['modes']['bf16']['semantics']['extra'] = True
                elif case == 'mode_missing': report['modes'].pop('fp32')
                elif case == 'mode_extra': report['modes']['extra'] = copy.deepcopy(report['modes']['bf16'])
                elif case == 'limit': report['approved_limits']['operator']['max_abs'] = 999
                elif case == 'stage_verdict': report['bf16_stages']['gate']['passed'] = False
                elif case == 'acceptance_type': report['native_acceptance'] = 1
                elif case == 'carried': report['carried'] = True
                elif case == 'postflight': report['postflight_complete'] = False
                elif case == 'count': report['stage_count'] = 28
                elif case == 'claim': report['actual_chain_executed'] = True
                else: report['private_extra'] = '/PRIVATE/secret'
                with self.subTest(slot=slot, case=case): self.reject(pair)

    def test_every_bf16_execution_requires_exact_impl_and_corresponding_isa(self):
        alternatives = ('brg_matmul:avx512_core_amx', 'brg_matmul:avx10_1_512_amx',
                        'brg_matmul:avx512_core', 'brg_matmul:avx2',
                        'brg:avx512_core_bf16', 'gemm:jit:bf16')
        for slot in (1, 3):
            for impl in alternatives:
                for mixed in (False, True):
                    pair, _ = self.fresh()
                    records = pair[slot]['capture']['bf16']['records']
                    for record in (records[-1:] if mixed else records):
                        record.update(implementation=impl, isa=diagnostic.IMPL_ISA[impl])
                    # These remain valid, complete diagnostics with nine matmuls.
                    self.assertTrue(phase.continuation_eligible(pair[slot]))
                    with self.subTest(slot=slot, impl=impl, mixed=mixed): self.reject(pair)
            for field, value in (('implementation', 'PRIVATE_UNKNOWN'),
                                 ('isa', 'avx512_core_amx')):
                pair, _ = self.fresh()
                pair[slot]['capture']['bf16']['records'][-1][field] = value
                with self.subTest(slot=slot, field=field): self.reject(pair)

    def test_info_only_incomplete_is_rejected_even_when_continuation_eligible(self):
        for tokens, slot in ((16, 1), (128, 3)):
            pair, _ = self.fresh()
            observed = diagnostics_fixture(tokens, info_unknown=True)
            observed['result_sha256'] = pair[slot]['result_sha256']
            pair[slot] = observed
            self.assertTrue(phase.continuation_eligible(observed))
            self.assertEqual(observed['status'], 'INCOMPLETE_DIAGNOSTICS')
            with self.subTest(tokens=tokens): self.reject(pair)

    def test_absent_fp32_execution_does_not_fabricate_dispatch_identity(self):
        pair, _ = self.fresh()
        for slot in (1, 3):
            pair[slot]['capture']['fp32'] = diagnostic.parse_verbose(b'')
        result = dispatch.validate_pair(*pair, context=context_for(pair))
        self.assertIs(result['backend_order_proven'], False)
        self.assertNotIn('fp32_implementation', result)

    def test_known_fp32_dispatch_is_not_used_as_the_bf16_selection(self):
        pair, _ = self.fresh()
        for slot in (1, 3):
            for record in pair[slot]['capture']['fp32']['records']:
                record.update(implementation='brg_matmul:avx512_core_amx', isa='avx512_core_amx')
        self.assertIs(dispatch.validate_pair(*pair, context=context_for(pair))[
            'native_numerical_prerequisite_passed'], True)

    def test_exact_nine_matmul_inventory_and_descriptors_are_required(self):
        for slot in (1, 3):
            for case in ('missing', 'extra', 'wrong_role', 'wrong_dtype', 'bias_dtype',
                         'wrong_primitive', 'cross_shape', 'empty'):
                pair, _ = self.fresh()
                capture = pair[slot]['capture']['bf16']
                first = capture['records'][0]
                if case in ('missing', 'extra'):
                    delta = -1 if case == 'missing' else 1
                    first['count'] += delta
                    capture['exec_records'] += delta
                    capture['lines_observed'] += delta
                elif case == 'wrong_role': first['role'] = 'OTHER'
                elif case == 'wrong_dtype': first['descriptors']['dst']['dtype'] = 'f32'
                elif case == 'bias_dtype': first['descriptors']['bia'] = dict(dtype='f32', layout='ab')
                elif case == 'wrong_primitive': first['primitive'] = 'inner_product'
                elif case == 'cross_shape':
                    pair[slot]['capture']['bf16'] = copy.deepcopy(pair[4 - slot]['capture']['bf16'])
                else:
                    pair[slot]['capture']['bf16'] = diagnostic.parse_verbose(b'')
                    pair[slot]['status'] = 'INCOMPLETE_DIAGNOSTICS'
                with self.subTest(slot=slot, case=case): self.reject(pair)

    def test_diagnostic_completeness_unknowns_and_postflight_fail_closed(self):
        for slot in (1, 3):
            for case in ('cpu', 'backend', 'fenv', 'postflight', 'unknown',
                         'malformed', 'truncated', 'fp32_unknown', 'stage_inventory'):
                pair, _ = self.fresh()
                observed = pair[slot]
                if case == 'cpu': observed['cpu'] = None
                elif case == 'backend': observed['backend_build'] = None
                elif case == 'fenv':
                    observed['fenv']['after_gate'] = {'status': 'UNSUPPORTED'}
                    observed['fenv_changes'] = phase.fenv_changes(observed['fenv'])
                elif case == 'postflight':
                    observed['postflight_complete'] = False
                    for key in ('result_sha256', 'payload_manifest_sha256',
                                'payload_tensor_map_sha256', 'payload_sha256', 'stage_sha256'):
                        observed[key] = None
                elif case == 'stage_inventory': observed['stage_sha256']['fp32'].pop('gate')
                else:
                    raw = b'PRIVATE\n' if case == 'malformed' else b'onednn_verbose,v1,graph,exec,PRIVATE\n'
                    mode = 'fp32' if case == 'fp32_unknown' else 'bf16'
                    observed['capture'][mode] = diagnostic.parse_verbose(raw, truncated=case == 'truncated')
                observed['status'] = 'INCOMPLETE_DIAGNOSTICS'
                with self.subTest(slot=slot, case=case): self.reject(pair, self.bound_context)

    def test_report_and_diagnostic_identity_fields_cannot_be_mixed(self):
        for report_slot, diagnostic_slot in ((0, 1), (2, 3)):
            for key in dispatch.REPORT_DIAGNOSTIC_IDENTITIES:
                pair, _ = self.fresh()
                pair[diagnostic_slot][key] = 128 if key == 'tokens' and report_slot == 0 else (
                    16 if key == 'tokens' else '0' * 64)
                with self.subTest(slot=diagnostic_slot, key=key): self.reject(pair)

    def test_every_shared_library_receipt_pin_source_contract_and_payload_is_bound(self):
        for key in dispatch.SHARED_REPORT_HASHES:
            pair, _ = self.fresh()
            pair[2][key] = '0' * 64
            if key in pair[3]: pair[3][key] = '0' * 64
            with self.subTest(key=key): self.reject(pair)

    def test_payload_tensor_maps_must_match_even_with_a_valid_rehashed_map(self):
        pair, _ = self.fresh()
        name = next(iter(pair[3]['payload_sha256']))
        pair[3]['payload_sha256'][name] = '0' * 64
        pair[3]['payload_tensor_map_sha256'] = phase.kernel.sha(phase.kernel.encoded(pair[3]['payload_sha256']))
        self.assertEqual(phase.validate_diagnostics(pair[3]), pair[3])
        self.reject(pair)

    def test_crosscase_backend_cpu_and_fenv_substitution_rejects_recomputed_context(self):
        for slot in (1, 3):
            for case in ('torch_build', 'numpy_build', 'cpu_flag', 'cpu_count', 'fenv'):
                pair, _ = self.fresh()
                observed = pair[slot]
                if case in ('torch_build', 'numpy_build'):
                    observed['backend_build'][case + '_sha256'] = '0' * 64
                elif case == 'cpu_flag': observed['cpu']['flags']['amx_tile'] = False
                elif case == 'cpu_count': observed['cpu']['processor_records'] += 1
                else:
                    observed['fenv']['after_gate']['ftz'] = True
                    observed['fenv_changes'] = phase.fenv_changes(observed['fenv'])
                self.assertEqual(phase.validate_diagnostics(observed), observed)
                self.assertTrue(phase.continuation_eligible(observed))
                with self.subTest(slot=slot, case=case):
                    self.reject(pair, context_for(pair))

    def test_equal_but_nondefault_fenv_cannot_qualify_even_with_recomputed_context(self):
        for field, value in (('x87_round', 1), ('sse_round', 2), ('ftz', True), ('daz', True)):
            pair, _ = self.fresh()
            for slot in (1, 3):
                env = pair[slot]['fenv']
                snapshots = list(env['libraries'].values()) + [
                    env[key] for key in ('before_recipe', 'after_recipe', 'after_gate')]
                for snapshot in snapshots: snapshot[field] = value
                pair[slot]['fenv_changes'] = phase.fenv_changes(env)
                self.assertTrue(all(changed is False for changed in pair[slot]['fenv_changes'].values()))
                self.assertTrue(phase.continuation_eligible(pair[slot]))
            with self.subTest(field=field): self.reject(pair, context_for(pair))

    def test_all_six_fenv_positions_must_be_default(self):
        positions = (('libraries', 'before'), ('libraries', 'after_qkv'), ('libraries', 'after_qk'),
                     (None, 'before_recipe'), (None, 'after_recipe'), (None, 'after_gate'))
        for section, name in positions:
            pair, _ = self.fresh()
            for slot in (1, 3):
                env = pair[slot]['fenv']
                (env[section] if section else env)[name]['ftz'] = True
                pair[slot]['fenv_changes'] = phase.fenv_changes(env)
                self.assertTrue(phase.continuation_eligible(pair[slot]))
            with self.subTest(section=section, name=name): self.reject(pair, context_for(pair))

    def test_verified_historical_archive_is_compatible_metadata_without_freshness_claim(self):
        # Archived-fixture verification only. This deliberately test-built
        # context does not prove these historical files are a current run.
        raw = phase.kernel.read(phase.ROOT / (
            'candidates/qwen2_resident_matrix/raw_kv_native_pass_results/EVIDENCE.json'), 262144)
        self.assertEqual(phase.kernel.sha(raw), '003fb256f0d686e3fe9d602cfcc9c47cb4e0aa511412a278bd33e8cc07697c0e')
        evidence = phase.kernel.json_bytes(raw, 262144)
        summary = evidence['summary']
        pair = [summary[group][case] for case in ('native16', 'native128')
                for group in ('native_results', 'native_diagnostics')]
        result = dispatch.validate_pair(*pair, context=context_for(pair))
        self.assertEqual(result['native16']['result_sha256'], pair[0]['result_sha256'])
        self.assertEqual(result['native128']['result_sha256'], pair[2]['result_sha256'])
        self.assertIs(result['native_numerical_prerequisite_passed'], True)
        self.assertIs(result['actual_chain_executed'], False)
        self.assertIs(result['runtime_ready'], False)

    def test_prior_incomplete_native16_cannot_form_an_accepted_archived_pair(self):
        root = phase.ROOT / 'candidates/qwen2_resident_matrix'
        passed = phase.kernel.json_bytes(phase.kernel.read(root / 'raw_kv_native_pass_results/EVIDENCE.json', 262144), 262144)
        raw = phase.kernel.read(root / 'raw_kv_native_info_results/EVIDENCE.json', 262144)
        self.assertEqual(phase.kernel.sha(raw), '0209d413e7814637cb8cb5cffbc5be8cc555a054b60eba9037cade687dd24c8b')
        prior = phase.kernel.json_bytes(raw, 262144)['summary']
        self.assertEqual(set(prior['native_results']), {'native16'})
        self.assertEqual(prior['native_diagnostics']['native16']['status'], 'INCOMPLETE_DIAGNOSTICS')
        pair = [prior['native_results']['native16'], prior['native_diagnostics']['native16'],
                passed['summary']['native_results']['native128'], passed['summary']['native_diagnostics']['native128']]
        self.reject(pair, context_for(pair))

    def test_m128_must_reference_this_fresh_m16_and_distinct_result(self):
        for case in ('stale_link', 'self_link', 'same_result', 'cross_order', 'm16_carried_link'):
            pair, _ = self.fresh()
            if case == 'stale_link': pair[2]['m16_result_sha256'] = '1' * 64
            elif case == 'self_link': pair[2]['m16_result_sha256'] = pair[2]['result_sha256']
            elif case == 'same_result': pair[2]['result_sha256'] = pair[3]['result_sha256'] = pair[0]['result_sha256']
            elif case == 'cross_order': pair = pair[2:] + pair[:2]
            else: pair[0]['m16_result_sha256'] = '1' * 64
            with self.subTest(case=case): self.reject(pair)

    def test_stale_expected_result_source_and_artifact_contexts_reject(self):
        for section in ('native16', 'native128'):
            for key in dispatch.CASE_CONTEXT_HASHES:
                pair, context = self.fresh()
                context[section][key] = '0' * 64
                with self.subTest(section=section, key=key): self.reject(pair, context)
        for key in dispatch.SHARED_CONTEXT_HASHES:
            pair, context = self.fresh()
            context['shared'][key] = '0' * 64
            with self.subTest(section='shared', key=key): self.reject(pair, context)

    def test_valid_metadata_substitutions_cannot_reuse_the_bound_artifact_context(self):
        for slot in (0, 2):
            pair, context = self.fresh()
            pair[slot]['bf16_stages']['gate'].update(max_abs=1e-7, mean_abs=1e-8, bit_exact=False)
            self.assertEqual(phase.validate_report(pair[slot]), pair[slot])
            with self.subTest(slot=slot): self.reject(pair, context)
        for slot in (1, 3):
            pair, context = self.fresh()
            pair[slot]['stage_sha256']['fp32']['gate']['actual_f32_sha256'] = '0' * 64
            self.assertEqual(phase.validate_diagnostics(pair[slot]), pair[slot])
            with self.subTest(slot=slot): self.reject(pair, context)

    def test_context_schema_profile_types_extra_fields_and_absence_reject(self):
        for case in ('schema', 'profile', 'missing', 'extra', 'shared_missing',
                     'case_missing', 'bad_hash', 'not_dict', 'oversize_private'):
            pair, context = self.fresh()
            if case == 'schema': context['schema'] = True
            elif case == 'profile': context['profile'] = 'qwen2-fresh-native-qkv-qk-dispatch-m16-m128-v3'
            elif case == 'missing': context.pop('native16')
            elif case == 'extra': context['runtime_ready'] = True
            elif case == 'shared_missing': context['shared'].pop('library_receipt_sha256')
            elif case == 'case_missing': context['native128'].pop('source_manifest_sha256')
            elif case == 'bad_hash': context['native16']['result_sha256'] = 'A' * 64
            elif case == 'not_dict': context = None
            else: context['native128']['diagnostics_sha256'] = 'PRIVATE' * 100000
            with self.subTest(case=case): self.reject(pair, context if context is not None else False)
        with self.assertRaises(TypeError): dispatch.validate_pair(*self.baseline)

    def test_import_and_validation_do_not_load_arrays_probe_cpu_or_launch(self):
        pair, context = self.fresh()
        before_environment = dict(os.environ)
        before_numerical = {name for name in sys.modules if name.split('.')[0] in ('torch', 'numpy')}
        original_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name.split('.')[0] in ('torch', 'numpy', 'ctypes') or name.endswith('.adapter'):
                raise AssertionError('forbidden numerical/native import')
            return original_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=guarded_import), \
                patch('subprocess.Popen', side_effect=AssertionError('process launch')), \
                patch.object(phase, 'run', side_effect=AssertionError('runtime launch')), \
                patch.object(phase, '_generated', side_effect=AssertionError('native module')), \
                patch.object(phase, 'read_cpu_features', side_effect=AssertionError('CPU probe')):
            importlib.reload(dispatch)
            result = dispatch.validate_pair(*pair, context=context)
        self.assertIs(result['actual_chain_executed'], False)
        self.assertEqual(dict(os.environ), before_environment)
        self.assertEqual({name for name in sys.modules if name.split('.')[0] in ('torch', 'numpy')}, before_numerical)


if __name__ == '__main__':
    unittest.main()
