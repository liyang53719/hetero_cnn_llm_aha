"""Source-only delivery closure; no producer payload is needed for this gate."""
from pathlib import Path
import hashlib
import json
import unittest

HERE = Path(__file__).resolve().parent


class DeliveryTests(unittest.TestCase):
    def test_manifest_matches_all_delivered_sources(self):
        d = json.loads((HERE/'delivery_manifest.json').read_text())
        actual = {p.name for p in HERE.iterdir() if p.is_file() and p.name != 'delivery_manifest.json'}
        self.assertEqual(actual, set(d['files']))
        for name, wanted in d['files'].items():
            data = (HERE/name).read_bytes()
            self.assertEqual(len(data), wanted['bytes'], name)
            self.assertEqual(hashlib.sha256(data).hexdigest(), wanted['sha256'], name)
        self.assertEqual(d['resources']['new_sram_arrays'], 0)
        self.assertEqual(d['resources']['new_sfu_units'], 0)
        self.assertFalse(d['rtl_generated'])
        self.assertFalse(d['production_host_ffn_fused'])
        self.assertEqual(d['native_acceptance'], 'UNCHANGED_FAIL_POLICY_PENDING')


if __name__ == '__main__':
    unittest.main()
