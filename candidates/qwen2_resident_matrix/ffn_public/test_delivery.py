"""Source-only public FFN delivery checks; no actual payloads or EDA."""
from pathlib import Path
import hashlib
import json
import unittest

HERE = Path(__file__).resolve().parent

class DeliveryTests(unittest.TestCase):
    def test_exact_files_and_software_scope(self):
        d = json.loads((HERE / 'delivery_manifest.json').read_text())
        names = {p.name for p in HERE.iterdir() if p.is_file() and p.name != 'delivery_manifest.json'}
        self.assertEqual(names, set(d['files']))
        for name, identity in d['files'].items():
            raw = (HERE / name).read_bytes()
            self.assertEqual(len(raw), identity['bytes'], name)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), identity['sha256'], name)
        for key in ('rtl_executed', 'scala_host_executed', 'full_block_executed', 'actual_idma'):
            self.assertFalse(d[key])
        self.assertEqual(d['native_acceptance'], 'UNCHANGED_FAIL_POLICY_PENDING')

    def test_public_retirement_and_actual_dependency_receipts(self):
        receipt = json.loads((HERE / 'numerical_receipt.json').read_text())
        self.assertEqual([c['rows'] for c in receipt['cases']], [16, 128])
        self.assertIsNone(receipt['hardware_cycle_prediction'])
        self.assertIsNone(receipt['full_wall_mac_utilization'])
        self.assertEqual(receipt['scope'], 'PUBLIC_FFN4_SOFTWARE_MODEL_ONLY')
        for c in receipt['cases']:
            host = c['host']
            self.assertEqual([x['pc'] for x in host['completions']], [0, 1, 2, 3])
            self.assertTrue(all(x['status'] is None for x in host['completions']))
            self.assertEqual(host['launch_result']['completed'], 4)
            self.assertEqual(host['launch_result']['jobs'], 2)
            self.assertEqual(host['accepted']['owner_result_fire'], 2)
            self.assertEqual(host['accepted']['completion_fire'], 4)
            self.assertEqual(host['accepted']['result_fire'], 1)
            self.assertEqual(c['windows'], 56)
            self.assertEqual(c['retained_a_load_fences'], 1)
            self.assertEqual(c['window_terminals'], 112)
            self.assertEqual(c['drain_terminals'], 56)
            self.assertTrue(c['same_owner_and_banks'])
            self.assertTrue(c['comparison_after_public_terminal'])
            self.assertEqual(c['act_ddr']['ack_bytes'], c['rows'] * 8960 * 4)
            self.assertEqual(c['down_ddr']['ack_bytes'], c['rows'] * 1536 * 4)
            self.assertEqual(c['actual_act_source']['sha256'], c['act_ddr']['sha256'])
            self.assertTrue(c['actual_act_source']['actual_prior_ack_written'])
            self.assertTrue(c['down_final_ack_fence']['terminal_strictly_after_final_ack'])
            self.assertEqual(c['metadata']['physical_read_bytes'], c['metadata']['physical_read_beats'] * 64)
            self.assertEqual(c['metadata']['command_records'], 4)
            self.assertEqual(c['metadata']['descriptor_records'], 43)
            self.assertEqual(len(c['physical_spans']), 11)
            for output in c['comparison'].values():
                self.assertEqual(output['independent_direct_bit_mismatches'], 0)
                self.assertEqual(output['saved_producer_bit_mismatches'], 0)
                self.assertEqual(output['actual_sha256'], output['direct_sha256'])
                self.assertEqual(output['actual_sha256'], output['saved_sha256'])

if __name__ == '__main__':
    unittest.main()
