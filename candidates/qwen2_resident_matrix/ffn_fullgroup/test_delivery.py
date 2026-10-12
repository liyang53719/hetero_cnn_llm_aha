"""Check source closure and explicit software-only receipt semantics without data."""
from pathlib import Path
import hashlib
import json
import unittest
HERE = Path(__file__).resolve().parent

class DeliveryTests(unittest.TestCase):
    def test_exact_source_and_no_hardware_acceptance(self):
        d = json.loads((HERE / 'delivery_manifest.json').read_text())
        names = {p.name for p in HERE.iterdir() if p.is_file() and p.name != 'delivery_manifest.json'}
        self.assertEqual(names, set(d['files']))
        for name, item in d['files'].items():
            raw = (HERE / name).read_bytes()
            self.assertEqual(len(raw), item['bytes'], name)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), item['sha256'], name)
        self.assertFalse(d['rtl_executed'])
        self.assertFalse(d['chisel_simulation'])
        self.assertFalse(d['full_block_executed'])
        self.assertEqual(d['native_acceptance'], 'UNCHANGED_FAIL_POLICY_PENDING')

    def test_receipts_cover_real_dependency_and_preserve_limits(self):
        d = json.loads((HERE / 'numerical_receipt.json').read_text())
        self.assertEqual([r['rows'] for r in d['cases']], [16, 128])
        self.assertIsNone(d['hardware_cycle_prediction'])
        self.assertIsNone(d['full_wall_mac_utilization'])
        self.assertFalse(d['public_host_parser_executed'])
        for r in d['cases']:
            self.assertEqual((r['windows'], r['window_terminals'], r['drain_terminals']), (56, 112, 56))
            self.assertTrue(r['same_owner_and_banks'])
            self.assertTrue(r['comparison_after_all_final_acks'])
            self.assertEqual(r['retained_a_load_fences'], 1)
            self.assertEqual(r['actual_act_source']['sha256'], r['group_ddr']['sha256'])
            self.assertTrue(r['actual_act_source']['actual_prior_ack_written'])
            self.assertTrue(r['down_final_ack_fence']['terminal_strictly_after_final_ack'])
            self.assertEqual(r['group_ddr']['ack_bytes'], r['rows'] * 8960 * 4)
            self.assertEqual(r['down_ddr']['ack_bytes'], r['rows'] * 1536 * 4)
            self.assertEqual(r['prefix']['completed_sweeps'], 3)
            self.assertTrue(r['prefix']['seed_ack_before_overwrite'])
            self.assertTrue(r['observed_host_fmas']['not_chisel_or_rtl_counters'])
            for value in r['comparison'].values():
                self.assertEqual(value['independent_direct_bit_mismatches'], 0)
                self.assertEqual(value['saved_producer_bit_mismatches'], 0)
                self.assertEqual(value['actual_sha256'], value['direct_sha256'])
                self.assertEqual(value['actual_sha256'], value['saved_sha256'])
if __name__ == '__main__':
    unittest.main()
