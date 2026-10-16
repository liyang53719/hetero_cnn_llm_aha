"""Cold evidence integrity only: no native imports, compilation, or execution."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        raw = Path(__file__).with_name('EVIDENCE.json').read_bytes()
        self.assertEqual(sha(raw), '90fde66adc9c9d8689f827641a0db2232c41893aae54151fedf052bd3d81a3c1')
        self.e = json.loads(raw)

    def test_actual_failed_run_and_fresh_small_gate_binding(self):
        e = self.e
        self.assertEqual((e['run_id'], e['placement'], e['job_id'], e['artifact_id']),
                         (38934796546, 2, 117087788071, 12059689836))
        self.assertEqual(e['archive_sha256'],
                         '541ba5f9b0b0650fecd64cd34721709c5383251fa52e9e89bc4e2590c4f24755')
        self.assertEqual(e['artifact_files_sha256'], {
            'summary.json': '5aa6a9a0141202ca505b32da69c32cf69dae776473b537f7943434f51a19c1e3',
            'progress.json': '345202510657c67cb6ffb9919116fc9c0ff60c73192e80571ea2cc74357ca086',
            'source_hashes.json': '0d6295537c25a41d3fe325c9a5dd489cf28c88060839e802b0b5423b9b5783fa'})
        self.assertEqual(e['status'], 'FAILED')
        self.assertEqual(e['checkout_commit'], 'cacc320580ca93dd7d70d4b3129b5522531bb66f')
        self.assertFalse(e['numerical_acceptance'] or e['public_execution'] or e['rtl_execution'])
        self.assertFalse(e['summary_postflight_complete'])
        a, b = (e['native_results'][n] for n in ('native16', 'native128'))
        self.assertEqual(a['status'], 'COMPLETE_NATIVE_VALIDATION')
        self.assertEqual(b['status'], 'FAIL_NATIVE_VALIDATION')
        self.assertTrue(a['native_acceptance'])
        self.assertFalse(b['native_acceptance'])
        self.assertEqual(b['m16_result_sha256'], a['result_sha256'])
        for name in ('contract_sha256', 'library_sha256', 'library_receipt_sha256',
                     'qkv_library_sha256', 'qkv_library_receipt_sha256',
                     'generated_module_sha256', 'recipe_pins_sha256',
                     'qkv_recipe_pins_sha256', 'payload_manifest_sha256'):
            self.assertEqual(a[name], b[name])
        for report in (a, b):
            self.assertFalse(report['carried'] or report['actual_chain_executed'] or
                             report['rtl_execution'] or report['backend_order_proven'])
            self.assertTrue(report['postflight_complete'])
            self.assertEqual(report['stage_count'], 29)
            self.assertEqual(report['assigned_bf16_checks'], 28)
            self.assertEqual(len(report['bf16_stages']), 29)
            for mode in ('bf16', 'fp32'):
                semantics = report['modes'][mode]['semantics']
                self.assertEqual(len(semantics), 9)
                self.assertTrue(all(v is True for v in semantics.values()))

    def test_unrelaxed_failures_and_nonisolated_qk_comparison(self):
        e = self.e
        c = e['comparison_to_prior']
        prior_raw = (ROOT / c['evidence_path']).read_bytes()
        self.assertEqual(sha(prior_raw), c['evidence_sha256'])
        prior = json.loads(prior_raw)
        self.assertEqual(c['run_id'], prior['run_id'])
        self.assertEqual(c['checkout_commit'], prior['checkout_commit'])
        self.assertTrue(c['qkv_library_sha256_unchanged'])
        self.assertFalse(c['isolated_qk_improvement_or_regression_established'])
        for size, report in e['native_results'].items():
            old = prior['native_results'][size]
            self.assertEqual(report['qkv_library_sha256'], old['library_sha256'])
            self.assertEqual(report['qkv_library_sha256'], c['shared_qkv_library_sha256'])
            for name, projection in c['prior_bf16_stage_projection'][size].items():
                self.assertEqual(projection, old['bf16_stages'][name])
            for name in ('qr', 'kr', 'v'):
                self.assertTrue(old['bf16_stages'][name]['bit_exact'])
                self.assertFalse(report['bf16_stages'][name]['bit_exact'])
                self.assertGreater(report['bf16_stages'][name]['max_abs'], 0)
            self.assertEqual(report['approved_limits'], old['approved_limits'])
        b = e['native_results']['native128']
        self.assertEqual(b['modes']['bf16']['failed_stages'], ['gate', 'logits', 'prob', 'scores'])
        for name, maximum in (('gate', 0.041015625), ('logits', 0.5),
                              ('prob', 0.031494140625), ('scores', 16.0)):
            stage = b['bf16_stages'][name]
            self.assertEqual(stage['max_abs'], maximum)
            self.assertEqual(stage['limits'], {'max_abs': 0.03125, 'mean_abs': 0.005})
            self.assertFalse(stage['passed'])
        self.assertTrue(b['bf16_stages']['y']['passed'])
        self.assertIsNone(b['bf16_stages']['softmax_fp32']['passed'])

    def test_pinned_sources_and_manifest_change_is_not_tensor_drift_proof(self):
        e = self.e
        # Runtime diagnostics have a separately versioned successor. Retain
        # their historical identities rather than binding a past run to new code.
        historical = {
            'candidates/qwen2_resident_matrix/raw_kv_native_qk_run/contract.json':
                'd8d81fbc5ac94d632b6c304a7a6db3f8eaa4624362b0674b9eee38dd4bb76675',
            'candidates/qwen2_resident_matrix/raw_kv_native_qk_run/phase.py':
                '1b78c5ca04ac054a1c11f8d1f90452a1f9a50b6e1edda65a47ee73f17218272e',
        }
        for name, expected in e['selected_source_sha256'].items():
            self.assertEqual(historical[name] if name in historical else sha((ROOT / name).read_bytes()), expected, name)
        p = e['input_provenance']
        self.assertEqual(p['original_loader_sha256'],
                         e['selected_source_sha256'][p['original_loader_path']])
        ledger_raw = (ROOT / p['tensor_pin_ledger_path']).read_bytes()
        self.assertEqual(sha(ledger_raw), p['tensor_pin_ledger_sha256'])
        self.assertEqual(len(json.loads(ledger_raw)['tensors']), p['pinned_raw_tensor_count'])
        self.assertEqual(p['pinned_raw_tensor_count'], 13)
        self.assertTrue(p['manifest_contains_http_receipts'])
        self.assertFalse(p['manifest_change_alone_proves_raw_input_drift'])
        self.assertFalse(p['raw_payloads_reaudited_in_this_checkpoint'])
        self.assertTrue(e['comparison_to_prior']['payload_manifest_sha256_changed'])
        self.assertNotEqual(e['native_results']['native128']['payload_manifest_sha256'],
                            e['comparison_to_prior']['prior_payload_manifest_sha256'])


if __name__ == '__main__':
    unittest.main()
