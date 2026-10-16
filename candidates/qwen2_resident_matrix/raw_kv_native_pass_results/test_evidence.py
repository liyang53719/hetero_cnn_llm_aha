"""Read-only stdlib checks of historical native PASS evidence; no native imports."""
import hashlib
import json
import os
from pathlib import Path
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
MEMBER_HASHES = {
    'summary.json': '1c00d3cd92a623b01d469a8345c9f1b79d073afbd479286b45cdce7c614054fd',
    'progress.json': 'c7b451175512d5aa2e18021b6c2b6df1b98c535bd260d8f0afac1c74602ffd65',
    'source_hashes.json': 'a21c19f68711a2af7748a650fabddb2cdbca0a80dfe04d32c9a349fc009a55ef',
}
ARCHIVE_HASH = '88d79cf4b74fb7bc5df60b4aed2383c1e1bf02bbbe18e5c59c3d41c1e4882689'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode('utf-8')


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        raw = (HERE / 'EVIDENCE.json').read_bytes()
        self.assertEqual(sha(raw), '003fb256f0d686e3fe9d602cfcc9c47cb4e0aa511412a278bd33e8cc07697c0e')
        self.e = json.loads(raw)

    def test_run_identity_and_original_summary_progress_bytes(self):
        e = self.e
        self.assertEqual((e['run_id'], e['placement'], e['job_id'], e['artifact_id']),
                         (38944308159, 2, 117120055314, 12065025969))
        self.assertEqual(e['checkout_commit'], 'fb64c97971ba5c6109051e7547f6a0d57a76f256')
        self.assertEqual(e['summary']['checkout_commit'], e['checkout_commit'])
        self.assertEqual(e['archive_filename'], 'native-qkv-qk-m16-m128-pass.zip')
        self.assertEqual(e['archive_sha256'], ARCHIVE_HASH)
        self.assertEqual(e['artifact_files_sha256'], MEMBER_HASHES)
        self.assertEqual(e['artifact_files_bytes'], {
            'summary.json': 48180, 'progress.json': 96, 'source_hashes.json': 34786})
        for member in ('summary', 'progress'):
            raw = canonical(e[member]) + b'\n'
            self.assertEqual(sha(raw), MEMBER_HASHES[member + '.json'])
            self.assertEqual(len(raw), e['artifact_files_bytes'][member + '.json'])
        self.assertEqual(e['progress'], {'elapsed_seconds': 65.347275, 'phase': 'finalize',
                                        'schema': 1, 'status': 'TERMINAL_RECEIPT_PENDING'})

    def test_exact_archive_and_source_projection_when_available(self):
        supplied = os.environ.get('RAW_KV_PASS_ARCHIVE')
        archive = Path(supplied) if supplied else HERE / self.e['archive_filename']
        if not supplied and not archive.is_file():
            self.skipTest('Original ZIP absent; set RAW_KV_PASS_ARCHIVE for byte verification')
        self.assertTrue(archive.is_file(), str(archive))
        self.assertEqual(sha(archive.read_bytes()), ARCHIVE_HASH)
        with zipfile.ZipFile(archive) as z:
            self.assertEqual(len(z.infolist()), 3)
            self.assertEqual(set(z.namelist()), set(MEMBER_HASHES))
            members = {name: z.read(name) for name in MEMBER_HASHES}
        for name, raw in members.items():
            self.assertEqual(sha(raw), MEMBER_HASHES[name], name)
            self.assertEqual(len(raw), self.e['artifact_files_bytes'][name])
        for name in ('summary', 'progress'):
            self.assertEqual(json.loads(members[name + '.json']), self.e[name])
        source, p = json.loads(members['source_hashes.json']), self.e['source_hashes_projection']
        self.assertEqual(sha(canonical(source)), p['source_hashes_canonical_sha256'])
        self.assertEqual(sha(canonical(source['source_sha256'])), p['source_map_canonical_sha256'])
        self.assertEqual(len(source['source_sha256']), p['source_file_count'])
        for key in ('schema', 'contract_sha256', 'generated_module_sha256', 'generated_sha256'):
            self.assertEqual(source[key], p[key])
        for group in ('historical_runtime_sha256', 'frozen_recipe_input_sha256'):
            for name, digest in p[group].items():
                self.assertEqual(source['source_sha256'][name], digest, name)

    def test_source_identity_and_unchanged_recipe_inputs(self):
        p = self.e['source_hashes_projection']
        self.assertEqual(p['source_file_count'], 252)
        self.assertEqual(p['source_map_canonical_sha256'],
                         '1223accc53ab7b047f9f764ceb22a07df23a19d75c820bd0550b0aabde7bb1a9')
        self.assertEqual(p['source_hashes_canonical_sha256'],
                         'c3ea3b5f76b4a65d03b17470d0737750c57a9fdc89e88137535a919a6a3eda99')
        self.assertEqual(len(p['generated_sha256']), 10)
        self.assertEqual(sha(canonical(p['generated_sha256'])),
                         'ce2ffd6e9f3a837a8d59b9759400e2d1c37b5fc6c67b2698ec82598ce65c1e65')
        self.assertEqual(len(p['historical_runtime_sha256']), 13)
        self.assertEqual(len(p['frozen_recipe_input_sha256']), 21)
        # Current runtime/parser may evolve; historical hashes remain bound to
        # the archived run, never to successor runtime bytes.
        prefix = 'candidates/qwen2_resident_matrix/raw_kv_native_qk_run/'
        self.assertEqual(p['historical_runtime_sha256'][prefix + 'contract.json'], p['contract_sha256'])
        for name, digest in p['frozen_recipe_input_sha256'].items():
            self.assertNotIn('/raw_kv_native_qk_run/', name)
            self.assertEqual(sha((ROOT / name).read_bytes()), digest, name)
        self.assertEqual(len(json.loads((ROOT / 'config/payload_pins/qwen2_layer0.json').read_text())['tensors']), 13)

    def test_both_original_passes_and_fresh_small_gate_binding(self):
        s = self.e['summary']
        self.assertEqual((s['status'], s['phase']), ('PASS_NATIVE_QKV_QK_M16_M128', 'finalize'))
        self.assertEqual(s['profile'], 'qwen2-fresh-native-qkv-qk-dispatch-m16-m128-v3')
        self.assertEqual(s['elapsed_seconds'], 65.347275)
        self.assertTrue(s['numerical_acceptance'] and s['postflight_complete'])
        self.assertTrue(s['packages_started'] and s['compile_started'] and s['native_started'])
        self.assertEqual(s['native_rows'], [16, 128])
        self.assertEqual(set(s['native_results']), {'native16', 'native128'})
        self.assertEqual(set(s['native_diagnostics']), {'native16', 'native128'})
        a, b = s['native_results']['native16'], s['native_results']['native128']
        self.assertIsNone(a['m16_result_sha256'])
        self.assertEqual(b['m16_result_sha256'], a['result_sha256'])
        for key in ('contract_sha256', 'source_manifest_sha256', 'generated_module_sha256',
                    'library_sha256', 'library_receipt_sha256', 'qkv_library_sha256',
                    'qkv_library_receipt_sha256', 'recipe_pins_sha256',
                    'qkv_recipe_pins_sha256', 'payload_manifest_sha256'):
            self.assertEqual(a[key], b[key], key)
        for case, tokens in (('native16', 16), ('native128', 128)):
            r, d = s['native_results'][case], s['native_diagnostics'][case]
            self.assertEqual(r['tokens'], tokens)
            self.assertEqual(r['status'], 'COMPLETE_NATIVE_VALIDATION')
            self.assertEqual(r['native_status'], 'PASS_BF16_STAGE_BUDGET')
            self.assertTrue(r['native_acceptance'] and r['postflight_complete'])
            self.assertEqual(d['status'], 'COMPLETE_DIAGNOSTICS')
            self.assertTrue(d['postflight_complete'] and d['diagnostic_only'])
            self.assertFalse(d['numerical_acceptance'])
            self.assertEqual((r['stage_count'], r['assigned_bf16_checks'], r['export_count']), (29, 28, 116))
            self.assertEqual(r['approved_limits'], {'operator': {'max_abs': 0.03125, 'mean_abs': 0.005},
                                                  'block': {'max_abs': 0.05, 'mean_abs': 0.01}})
            self.assertEqual(len(r['bf16_stages']), 29)
            self.assertEqual(sum(v['passed'] is True for v in r['bf16_stages'].values()), 28)
            self.assertIsNone(r['bf16_stages']['softmax_fp32']['passed'])
            for mode in ('bf16', 'fp32'):
                m = r['modes'][mode]
                self.assertTrue(m['all_semantics_exact'])
                self.assertEqual(m['failed_stages'], [])
                self.assertEqual(len(m['semantics']), 9)
                self.assertTrue(all(v is True for v in m['semantics'].values()))
                self.assertEqual(len(d['stage_sha256'][mode]), 29)
            self.assertEqual(r['modes']['fp32']['status'], 'DIAGNOSTIC_FP32')
            self.assertEqual(len(d['payload_sha256']), 13)
            for key in ('contract_sha256', 'source_manifest_sha256', 'generated_module_sha256',
                        'library_sha256', 'qkv_library_sha256', 'payload_manifest_sha256', 'result_sha256'):
                self.assertEqual(r[key], d[key], key)
        for name in ('scores', 'logits'):
            stage = b['bf16_stages'][name]
            self.assertTrue(stage['bit_exact'] and stage['passed'])
            self.assertEqual((stage['max_abs'], stage['mean_abs']), (0.0, 0.0))
        self.assertEqual((b['bf16_stages']['y']['max_abs'], b['bf16_stages']['y']['mean_abs']),
                         (0.00390625, 5.5594719015061855e-06))

    def test_bound_prior_native16_comparison_and_causality_boundary(self):
        c = self.e['comparison_to_prior_native16']
        raw = (ROOT / c['prior_evidence_path']).read_bytes()
        self.assertEqual(sha(raw), c['prior_evidence_sha256'])
        self.assertEqual(sha(raw), '0209d413e7814637cb8cb5cffbc5be8cc555a054b60eba9037cade687dd24c8b')
        prior = json.loads(raw)
        for key in ('run_id', 'placement', 'job_id', 'artifact_id', 'checkout_commit',
                    'archive_sha256', 'artifact_files_sha256'):
            self.assertEqual(c['prior_' + key], prior[key])
        a = prior['summary']['native_diagnostics']['native16']
        b = self.e['summary']['native_diagnostics']['native16']
        for mode in ('bf16', 'fp32'):
            for field in ('actual_f32_sha256', 'reference_f32_sha256'):
                expected = {'equal_stages': [], 'different_stages': []}
                for stage in sorted(a['stage_sha256'][mode]):
                    key = 'equal_stages' if a['stage_sha256'][mode][stage][field] == b['stage_sha256'][mode][stage][field] else 'different_stages'
                    expected[key].append(stage)
                self.assertEqual(c['stage_hash_comparison'][mode][field], expected)
                self.assertEqual(len(expected['equal_stages']) + len(expected['different_stages']), 29)
            independent = c['stage_hash_comparison'][mode]['reference_f32_sha256']
            self.assertEqual(len(independent['equal_stages']), 29)
            self.assertEqual(independent['different_stages'], [])
        native_differences = {
            'bf16': 'act att cache_v down gate kr n1 o pv q qr r repeat_v silu up v y'.split(),
            'fp32': 'act att cache_k cache_v down gate k kr logits n1 o prob pv q qr r repeat_k repeat_v scores silu softmax_fp32 up v y'.split(),
        }
        for mode, expected in native_differences.items():
            self.assertEqual(c['stage_hash_comparison'][mode]['actual_f32_sha256']['different_stages'], expected)
        self.assertEqual(c['stage_field_semantics']['actual_f32_sha256'], 'native_forward')
        self.assertEqual(c['stage_field_semantics']['reference_f32_sha256'], 'independent_forward')
        self.assertEqual(sha((ROOT / c['stage_field_semantics']['definition_source_path']).read_bytes()),
                         c['stage_field_semantics']['definition_source_sha256'])
        self.assertEqual(len(a['payload_sha256']), c['payload_tensor_count'])
        self.assertEqual(c['payload_tensor_count'], 13)
        for field, flag in (('payload_sha256', 'payload_sha256_maps_equal'),
                            ('payload_tensor_map_sha256', 'payload_tensor_map_sha256_equal'),
                            ('fenv', 'fenv_equal'), ('fenv_changes', 'fenv_change_flags_equal')):
            self.assertEqual(a[field], b[field])
            self.assertTrue(c[flag])
        self.assertEqual(c['shared_payload_tensor_map_sha256'], b['payload_tensor_map_sha256'])
        build_equal = {key: a['backend_build'][key] == b['backend_build'][key] for key in a['backend_build']}
        self.assertEqual(c['backend_build_field_equal'], build_equal)
        self.assertEqual([key for key, value in build_equal.items() if not value], ['numpy_build_sha256'])
        self.assertEqual(c['prior_numpy_build_sha256'], a['backend_build']['numpy_build_sha256'])
        self.assertEqual(c['current_numpy_build_sha256'], b['backend_build']['numpy_build_sha256'])
        for records, implementation in ((a['capture']['bf16']['records'], c['prior_bf16_implementation']),
                                        (b['capture']['bf16']['records'], c['current_bf16_implementation'])):
            self.assertTrue(all(record['implementation'] == implementation for record in records))
        self.assertNotEqual(a['cpu']['flags'], b['cpu']['flags'])
        self.assertNotIn('native128', prior['summary']['native_results'])
        for key in ('cpu_flags_equal', 'only_isa_varied', 'sole_isa_causality_proven',
                    'prior_native128_exists', 'cross_run_native128_comparison_available'):
            self.assertFalse(c[key])

    def test_prior_archive_when_explicitly_supplied(self):
        supplied = os.environ.get('RAW_KV_PASS_PRIOR_ARCHIVE')
        if not supplied:
            self.skipTest('Set RAW_KV_PASS_PRIOR_ARCHIVE to reverify the prior AMX ZIP bytes')
        archive = Path(supplied)
        self.assertTrue(archive.is_file(), str(archive))
        c = self.e['comparison_to_prior_native16']
        self.assertEqual(sha(archive.read_bytes()), c['prior_archive_sha256'])
        prior = json.loads((ROOT / c['prior_evidence_path']).read_bytes())
        with zipfile.ZipFile(archive) as z:
            self.assertEqual(len(z.infolist()), 3)
            self.assertEqual(set(z.namelist()), set(c['prior_artifact_files_sha256']))
            members = {name: z.read(name) for name in z.namelist()}
        for name, raw in members.items():
            self.assertEqual(sha(raw), c['prior_artifact_files_sha256'][name], name)
        for name in ('summary', 'progress'):
            self.assertEqual(json.loads(members[name + '.json']), prior[name])
        source = json.loads(members['source_hashes.json'])
        self.assertEqual(sha(canonical(source)), prior['source_hashes_projection']['source_hashes_canonical_sha256'])

    def test_exact_dispatch_profile_cpu_fenv_and_scoped_claims(self):
        s = self.e['summary']
        self.assertFalse(s['public_executed'] or s['rtl_executed'])
        self.assertTrue(s['cpu_eligibility']['eligibility_only'])
        self.assertFalse(s['cpu_eligibility']['backend_qualified'])
        for case in ('native16', 'native128'):
            r, d = s['native_results'][case], s['native_diagnostics'][case]
            self.assertFalse(r['carried'] or r['actual_chain_executed'] or r['backend_order_proven'] or r['rtl_execution'])
            self.assertFalse(d['actual_chain_executed'] or d['backend_order_proven'] or d['rtl_execution'])
            bf, fp = d['capture']['bf16'], d['capture']['fp32']
            self.assertEqual(bf['status'], 'COMPLETE_DIAGNOSTIC')
            self.assertEqual((bf['exec_records'], bf['info_records'], bf['lines_observed'],
                              bf['unsupported_records'], bf['malformed_records']), (9, 7, 16, 0, 0))
            attention = ['QK', 'PV'] if case == 'native16' else ['ATTENTION_SQUARE', 'ATTENTION_SQUARE']
            self.assertEqual([x['role'] for x in bf['records']],
                             ['DENSE_HIDDEN', 'QKV_KV', *attention, 'DENSE_HIDDEN', 'MLP'])
            self.assertEqual([x['count'] for x in bf['records']], [1, 2, 1, 1, 1, 3])
            for record in bf['records']:
                self.assertEqual((record['primitive'], record['implementation'], record['isa']),
                                 ('matmul', 'brg_matmul:avx512_core_bf16', 'avx512_core_bf16'))
            self.assertEqual(fp['status'], 'NO_ONEDNN_EXECUTION_OBSERVED')
            self.assertEqual(fp['records'], [])
            self.assertTrue(all(fp[k] == 0 for k in ('exec_records', 'info_records', 'lines_observed',
                                                     'unsupported_records', 'malformed_records')))
            for capture in (bf, fp):
                self.assertFalse(capture['truncated'] or capture['numerical_acceptance'] or capture['backend_order_proven'])
                self.assertTrue(capture['diagnostic_only'])
                for field, count in (('unsupported_reasons', 11), ('unsupported_info_subtypes', 6)):
                    self.assertEqual(len(capture[field]), count)
                    self.assertTrue(all(v == 0 for v in capture[field].values()))
            flags = d['cpu']['flags']
            self.assertEqual(len(flags), 11)
            self.assertTrue(flags['avx512_bf16'])
            self.assertTrue(all(value is (not key.startswith('amx_')) for key, value in flags.items()))
            self.assertEqual(d['cpu']['processor_records'], 4)
            observed = {'status': 'OBSERVED', 'daz': False, 'ftz': False, 'sse_round': 0, 'x87_round': 0}
            for key in ('before_recipe', 'after_recipe', 'after_gate'):
                self.assertEqual(d['fenv'][key], observed)
            for value in d['fenv']['libraries'].values():
                self.assertEqual(value, observed)
            self.assertEqual(d['fenv_changes'], {'gate': False, 'qk_load': False, 'qkv_load': False, 'recipe': False})
        i = self.e['interpretation']
        self.assertEqual(i['native_rows_executed'], [16, 128])
        self.assertTrue(i['fresh_native16_result_binds_native128_gate'])
        self.assertTrue(i['progress_receipt_status_is_preserved_not_rewritten'])
        for key in ('diagnostics_independently_grant_numerical_acceptance', 'generic_backend_equivalence_proven',
                    'cross_host_numerical_causality_proven', 'amx_backend_validated_by_this_run',
                    'full_public_execution', 'rtl_execution', 'historical_failures_reclassified_as_pass',
                    'arithmetic_or_acceptance_limits_changed_by_this_checkpoint',
                    'checkpoint_native_execution', 'checkpoint_ci_dispatch', 'checkpoint_download',
                    'historical_runtime_hashes_must_match_current_files'):
            self.assertFalse(i[key], key)


if __name__ == '__main__':
    unittest.main()
