"""Cold integrity checks for the actual QKV recipe validation evidence."""
import hashlib
import json
from pathlib import Path
import unittest


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        raw=Path(__file__).with_name('QKV_NATIVE_EVIDENCE.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'f5d56364ed43c16fe53b8cddee26cd67b67d7c8aca04a603d65b45bd7ce65eaf')
        self.e=json.loads(raw)

    def test_failed_overall_and_real_small_gate_link(self):
        e=self.e;a=e['native_results']['native16'];b=e['native_results']['native128']
        self.assertEqual(e['status'],'FAILED')
        self.assertEqual(a['status'],'COMPLETE_NATIVE_VALIDATION')
        self.assertEqual(b['status'],'FAIL_NATIVE_VALIDATION')
        self.assertTrue(a['native_acceptance']);self.assertFalse(b['native_acceptance'])
        self.assertEqual(b['m16_result_sha256'],a['result_sha256'])
        for name in ('library_sha256','library_receipt_sha256','generated_module_sha256','recipe_pins_sha256','payload_manifest_sha256'):
            self.assertEqual(a[name],b[name])
        self.assertFalse(e['public_execution']);self.assertFalse(e['rtl_execution'])

    def test_exact_inputs_and_unrelaxed_remaining_failures(self):
        b=self.e['native_results']['native128'];st=b['bf16_stages']
        for name in ('qr','kr','v','q','k','cache_k','cache_v','repeat_k','repeat_v'):
            self.assertIs(st[name]['bit_exact'],True)
            self.assertEqual(st[name]['max_abs'],0.0)
        self.assertEqual(b['modes']['bf16']['failed_stages'],['logits','scores'])
        for name,error in (('scores',16.0),('logits',2.0)):
            self.assertEqual(st[name]['max_abs'],error)
            self.assertEqual(st[name]['limits']['max_abs'],0.03125)
            self.assertIs(st[name]['passed'],False)
        for name in ('gate','prob','y'):self.assertIs(st[name]['passed'],True)
        for mode in ('bf16','fp32'):
            self.assertEqual(len(b['modes'][mode]['semantics']),9)
            self.assertTrue(all(v is True for v in b['modes'][mode]['semantics'].values()))
        self.assertEqual(len(st),29)
        self.assertIsNone(st['softmax_fp32']['passed'])

if __name__=='__main__':unittest.main()
