"""Pure-source manifest closure, with no downloaded model payload."""
from pathlib import Path
import hashlib
import json
import unittest
HERE = Path(__file__).resolve().parent
class DeliveryTests(unittest.TestCase):
    def test_source_manifest_and_explicit_acceptance_boundary(self):
        d=json.loads((HERE/'delivery_manifest.json').read_text())
        actual={p.name for p in HERE.iterdir() if p.is_file() and p.name!='delivery_manifest.json'}
        self.assertEqual(actual,set(d['files']))
        for name,wanted in d['files'].items():
            data=(HERE/name).read_bytes()
            self.assertEqual(len(data),wanted['bytes'],name)
            self.assertEqual(hashlib.sha256(data).hexdigest(),wanted['sha256'],name)
        self.assertEqual(d['resources']['net_added_metadata_bits'],262)
        for name in ('new_sram_arrays','new_result_buffers','matrix_units_added','sfu_units_added'):
            self.assertEqual(d['resources'][name],0)
        self.assertFalse(d['rtl_generated'])
        self.assertFalse(d['hardware_arithmetic_executed'])
        self.assertFalse(d['production_host_ffn_fused'])
        self.assertFalse(d['act_ddr_drain_implemented'])
        self.assertEqual(d['native_acceptance'],'UNCHANGED_FAIL_POLICY_PENDING')
if __name__=='__main__': unittest.main()
