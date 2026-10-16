"""Cold historical evidence checks: stdlib only; no numerical/native execution."""
import hashlib
import json
import os
from pathlib import Path
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[3]
MEMBER_HASHES = {
    'summary.json': 'b418cebfc061d5d1fb10c32372eda8e2507e6ad2cd25bcf45ed884250ddbd661',
    'progress.json': '79549584eb25d7cfb8ccbb9957d53357ce7632085c794c4e80a271bdd24e04d3',
    'source_hashes.json': '6eda5565a73b39037951aa996a9230a9fc90c7b70673669e4a5ed6f4b261bb84',
}
ARCHIVE_HASH = 'a30c1dbdc35a320d6eaa1b5fecc10a41c93e0bf82e101d897eef4c68728fcaae'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode('utf-8')


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        raw = Path(__file__).with_name('EVIDENCE.json').read_bytes()
        self.assertEqual(sha(raw), '0209d413e7814637cb8cb5cffbc5be8cc555a054b60eba9037cade687dd24c8b')
        self.e = json.loads(raw)

    def test_run_identity_and_preserved_json_members(self):
        e = self.e
        self.assertEqual((e['run_id'], e['placement'], e['job_id'], e['artifact_id']),
                         (38941569876, 1, 117110232158, 12062928370))
        self.assertEqual(e['checkout_commit'], '331d428872946a3341c173823c6fa7f416600401')
        self.assertEqual(e['summary']['checkout_commit'], e['checkout_commit'])
        self.assertEqual(e['archive_filename'], 'dispatch-info-record-failure.zip')
        self.assertEqual(e['archive_sha256'], ARCHIVE_HASH)
        self.assertEqual(e['artifact_files_sha256'], MEMBER_HASHES)
        self.assertEqual(e['artifact_files_bytes'], {
            'summary.json': 24572, 'progress.json': 78, 'source_hashes.json': 34786})
        # These members used canonical JSON plus a final newline. Their complete
        # original bytes can therefore be verified without retaining extra files.
        for name in ('summary', 'progress'):
            raw = canonical(e[name]) + b'\n'
            self.assertEqual(sha(raw), MEMBER_HASHES[name + '.json'])
            self.assertEqual(len(raw), e['artifact_files_bytes'][name + '.json'])

    def test_exact_source_archive_when_available(self):
        supplied = os.environ.get('RAW_KV_INFO_ARCHIVE')
        archive = Path(supplied) if supplied else (
            Path(__file__).resolve().parent / 'dispatch-info-record-failure.zip')
        if not archive.is_file() and not supplied:
            self.skipTest('Original ZIP absent; set RAW_KV_INFO_ARCHIVE for byte verification')
        self.assertTrue(archive.is_file(), str(archive))
        self.assertEqual(sha(archive.read_bytes()), ARCHIVE_HASH)
        with zipfile.ZipFile(archive) as z:
            self.assertEqual(len(z.infolist()), 3)
            self.assertEqual(set(z.namelist()), set(MEMBER_HASHES))
            raw = {name: z.read(name) for name in MEMBER_HASHES}
        for name, body in raw.items():
            self.assertEqual(sha(body), MEMBER_HASHES[name], name)
            self.assertEqual(len(body), self.e['artifact_files_bytes'][name])
        self.assertEqual(json.loads(raw['summary.json']), self.e['summary'])
        self.assertEqual(json.loads(raw['progress.json']), self.e['progress'])
        source = json.loads(raw['source_hashes.json'])
        projection = self.e['source_hashes_projection']
        self.assertEqual(len(source['source_sha256']), projection['source_file_count'])
        self.assertEqual(sha(canonical(source)), projection['source_hashes_canonical_sha256'])
        self.assertEqual(sha(canonical(source['source_sha256'])),
                         projection['source_map_canonical_sha256'])
        for key in ('schema', 'contract_sha256', 'generated_module_sha256', 'generated_sha256'):
            self.assertEqual(source[key], projection[key])
        for group in ('historical_runtime_sha256', 'frozen_recipe_input_sha256'):
            for name, digest in projection[group].items():
                self.assertEqual(source['source_sha256'][name], digest, name)

    def test_source_and_result_identity_without_binding_edited_runtime(self):
        e = self.e
        p = e['source_hashes_projection']
        self.assertEqual(p['source_file_count'], 252)
        self.assertEqual(p['source_map_canonical_sha256'],
                         '75f7727abcae8a42315999bb94529556abc87635330cc89fae2face2331a45da')
        self.assertEqual(p['source_hashes_canonical_sha256'],
                         'b627ec9094cd0aeb8be4c7d73657bd41c13cf07c87ca7ef0bddb1a689683eace')
        self.assertEqual(len(p['generated_sha256']), 10)
        self.assertEqual(sha(canonical(p['generated_sha256'])),
                         'ce2ffd6e9f3a837a8d59b9759400e2d1c37b5fc6c67b2698ec82598ce65c1e65')
        historical = p['historical_runtime_sha256']
        self.assertEqual(len(historical), 13)
        prefix = 'candidates/qwen2_resident_matrix/raw_kv_native_qk_run/'
        self.assertEqual(historical[prefix + 'contract.json'], p['contract_sha256'])
        self.assertEqual(historical[prefix + 'dispatch_capture.py'],
                         '584d282fa7060af484b27f92199e4a7ba309c8bec6a110f5385fa210570d82fa')
        self.assertEqual(historical[prefix + 'runtime.py'],
                         'b32986c23938d66d8490023f8040a753af2aa1ef7424b43351b3de6d9008227d')
        # Historical runtime bytes are identified in the immutable original
        # artifact, never compared with the separately repaired current runtime.
        s = e['summary']
        result, diagnostic = s['native_results']['native16'], s['native_diagnostics']['native16']
        self.assertEqual(s['contract_sha256'], p['contract_sha256'])
        self.assertEqual(result['generated_module_sha256'], p['generated_module_sha256'])
        for key in ('contract_sha256', 'generated_module_sha256', 'source_manifest_sha256',
                    'result_sha256', 'library_sha256', 'qkv_library_sha256', 'payload_manifest_sha256'):
            self.assertEqual(result[key], diagnostic[key], key)
        self.assertEqual(result['source_manifest_sha256'],
                         'e045c16c64d753e13e9d116ad4e7e0ab933ca04eca92ad334edcc512e7bbe90e')

    def test_frozen_recipe_inputs_and_original_limits(self):
        e = self.e
        frozen = e['source_hashes_projection']['frozen_recipe_input_sha256']
        self.assertEqual(len(frozen), 21)
        for name, digest in frozen.items():
            self.assertNotIn('/raw_kv_native_qk_run/', name)
            self.assertEqual(sha((ROOT / name).read_bytes()), digest, name)
        ledger = json.loads((ROOT / 'config/payload_pins/qwen2_layer0.json').read_text())
        self.assertEqual(len(ledger['tensors']), 13)
        r = e['summary']['native_results']['native16']
        self.assertEqual(r['approved_limits'], {
            'operator': {'max_abs': 0.03125, 'mean_abs': 0.005},
            'block': {'max_abs': 0.05, 'mean_abs': 0.01}})
        self.assertEqual(r['original_module_sha256'], frozen['scripts/qwen2_layer0_model_gate.py'])
        for name, stage in r['bf16_stages'].items():
            expected = None if name in ('mask', 'softmax_fp32') else r['approved_limits'][
                'block' if name == 'y' else 'operator']
            self.assertEqual(stage['limits'], expected, name)

    def test_native16_original_pass_is_preserved(self):
        r = self.e['summary']['native_results']['native16']
        self.assertEqual(r['tokens'], 16)
        self.assertEqual(r['status'], 'COMPLETE_NATIVE_VALIDATION')
        self.assertEqual(r['native_status'], 'PASS_BF16_STAGE_BUDGET')
        self.assertTrue(r['native_acceptance'])
        self.assertTrue(r['postflight_complete'])
        self.assertFalse(r['carried'])
        self.assertIsNone(r['m16_result_sha256'])
        self.assertEqual((r['stage_count'], r['assigned_bf16_checks'], r['export_count']), (29, 28, 116))
        self.assertEqual(len(r['bf16_stages']), 29)
        self.assertEqual(sum(stage['passed'] is True for stage in r['bf16_stages'].values()), 28)
        self.assertIsNone(r['bf16_stages']['softmax_fp32']['passed'])
        self.assertTrue(all(stage['finite'] for stage in r['bf16_stages'].values()))
        for mode in ('bf16', 'fp32'):
            m = r['modes'][mode]
            self.assertEqual(m['failed_stages'], [])
            self.assertTrue(m['all_semantics_exact'])
            self.assertEqual(len(m['semantics']), 9)
            self.assertTrue(all(v is True for v in m['semantics'].values()))
        self.assertEqual(r['modes']['fp32']['status'], 'DIAGNOSTIC_FP32')

    def test_partial_failure_does_not_claim_native128_or_acceptance(self):
        e = self.e
        s, p = e['summary'], e['progress']
        self.assertEqual((s['status'], s['phase'], p['status'], p['phase']),
                         ('FAILED', 'native16', 'FAILED', 'native16'))
        self.assertEqual(s['elapsed_seconds'], 56.418942)
        self.assertEqual(p['elapsed_seconds'], s['elapsed_seconds'])
        self.assertEqual(s['native_rows'], [16, 128])
        self.assertEqual(set(s['native_results']), {'native16'})
        self.assertEqual(set(s['native_diagnostics']), {'native16'})
        self.assertEqual(s['diagnostic']['exception'], 'RuntimeError')
        self.assertEqual(s['diagnostic']['exit_code'], 1)
        self.assertEqual(s['diagnostic']['phase'], 'native16')
        self.assertTrue(s['packages_started'] and s['compile_started'] and s['native_started'])
        self.assertFalse(s['postflight_complete'])
        self.assertFalse(s['numerical_acceptance'] or s['public_executed'] or s['rtl_executed'])
        d = s['native_diagnostics']['native16']
        self.assertEqual(d['status'], 'INCOMPLETE_DIAGNOSTICS')
        self.assertTrue(d['postflight_complete'])
        self.assertTrue(d['diagnostic_only'])
        self.assertFalse(d['numerical_acceptance'])
        for r in (s['native_results']['native16'], d):
            self.assertFalse(r['actual_chain_executed'] or r['rtl_execution'] or r['backend_order_proven'])
        self.assertEqual(e['interpretation']['native128_status'], 'NOT_RUN')
        self.assertFalse(e['interpretation']['native128_executed'])

    def test_dispatch_counts_known_implementation_and_safe_hashes(self):
        d = self.e['summary']['native_diagnostics']['native16']
        bf, fp = d['capture']['bf16'], d['capture']['fp32']
        self.assertEqual(bf['status'], 'UNSUPPORTED')
        self.assertEqual((bf['unsupported_records'], bf['exec_records'], bf['info_records'],
                          bf['lines_observed'], bf['malformed_records'], bf['truncated']),
                         (1, 9, 6, 16, 0, False))
        # Preserve ordered groups: DENSE_HIDDEN occurs twice and must not be
        # collapsed into a dictionary that silently loses the first matmul.
        self.assertEqual([(r['role'], r['count']) for r in bf['records']],
                         [('DENSE_HIDDEN', 1), ('QKV_KV', 2), ('QK', 1),
                          ('PV', 1), ('DENSE_HIDDEN', 1), ('MLP', 3)])
        self.assertEqual(sum(r['count'] for r in bf['records']), 9)
        reasons = {'attributes': 0, 'auxiliary': 0, 'engine': 0,
                   'implementation': 0, 'information_header': 0,
                   'information_record': 1, 'memory_descriptor': 0,
                   'primitive': 0, 'prop_kind': 0, 'verbose_version': 0}
        self.assertEqual(bf['unsupported_reasons'], reasons)
        self.assertEqual(sum(bf['unsupported_reasons'].values()), 1)
        self.assertEqual(fp['unsupported_reasons'], dict.fromkeys(reasons, 0))
        for r in bf['records']:
            self.assertEqual(r['implementation'], 'brg_matmul:avx10_1_512_amx')
            self.assertEqual(r['isa'], 'avx10_1_512_amx')
            self.assertEqual(r['primitive'], 'matmul')
        self.assertEqual(fp['status'], 'NO_ONEDNN_EXECUTION_OBSERVED')
        self.assertEqual(fp['records'], [])
        for key in ('unsupported_records', 'exec_records', 'info_records', 'lines_observed', 'malformed_records'):
            self.assertEqual(fp[key], 0)
        for capture in (bf, fp):
            self.assertFalse(capture['truncated'] or capture['numerical_acceptance'] or capture['backend_order_proven'])
            self.assertTrue(capture['diagnostic_only'])
        self.assertEqual(len(d['payload_sha256']), 13)
        self.assertEqual(set(d['stage_sha256']), {'bf16', 'fp32'})
        for mode, stages in d['stage_sha256'].items():
            self.assertEqual(len(stages), 29, mode)
            for pairs in stages.values():
                self.assertEqual(set(pairs), {'actual_f32_sha256', 'reference_f32_sha256'})
                for digest in pairs.values():
                    self.assertRegex(digest, r'^[0-9a-f]{64}$')

    def test_cpu_build_fenv_observations_are_not_cross_host_causality(self):
        s = self.e['summary']
        d = s['native_diagnostics']['native16']
        self.assertFalse(s['cpu_eligibility']['backend_qualified'])
        self.assertTrue(s['cpu_eligibility']['eligibility_only'])
        self.assertEqual(d['cpu']['processor_records'], 4)
        self.assertTrue(d['cpu']['diagnostic_only'])
        self.assertEqual(len(d['cpu']['flags']), 11)
        self.assertTrue(all(v is True for v in d['cpu']['flags'].values()))
        self.assertTrue(all(d['cpu']['flags'][k] for k in ('amx_bf16', 'amx_int8', 'amx_tile', 'avx512_bf16')))
        self.assertEqual(d['backend_build']['onednn_version'], '3.7.1')
        self.assertEqual(d['backend_build']['onednn_commit'], '8d263e693366ef8db40acc569cc7d8edf644556d')
        self.assertTrue(d['backend_build']['installed_sources_verified_exact'])
        observed = {'status': 'OBSERVED', 'daz': False, 'ftz': False, 'sse_round': 0, 'x87_round': 0}
        for key in ('before_recipe', 'after_recipe', 'after_gate'):
            self.assertEqual(d['fenv'][key], observed)
        for key in ('before', 'after_qkv', 'after_qk'):
            self.assertEqual(d['fenv']['libraries'][key], observed)
        self.assertEqual(d['fenv_changes'], {'gate': False, 'qk_load': False, 'qkv_load': False, 'recipe': False})
        i = self.e['interpretation']
        self.assertTrue(i['information_record_classification_only'])
        self.assertFalse(i['unsupported_information_record_identity_proven'])
        for key in ('unsupported_record_contents_recovered', 'unsupported_record_cause_proven',
                    'cross_host_dispatch_difference_proven', 'cross_host_numerical_causality_proven',
                    'parser_repair_retroactively_changes_this_run',
                    'arithmetic_or_acceptance_limits_changed_by_this_checkpoint',
                    'checkpoint_native_execution', 'checkpoint_ci_dispatch', 'checkpoint_download',
                    'historical_runtime_hashes_must_match_current_files'):
            self.assertFalse(i[key], key)


if __name__ == '__main__':
    unittest.main()
