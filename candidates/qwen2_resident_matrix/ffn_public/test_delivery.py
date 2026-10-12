"""Source-only public FFN delivery checks; no actual payloads or EDA."""
from pathlib import Path
import hashlib
import json
import subprocess
import unittest

HERE = Path(__file__).resolve().parent
COMMIT = 'df18ba25a439fd90c846b22b9aafe992a2a6ae79'

class DeliveryTests(unittest.TestCase):
    def test_prefix_capture_keeps_actual_public_fences_and_historical_scope(self):
        receipt = json.loads((HERE / 'prefix_numerical_receipt.json').read_text())
        self.assertEqual(receipt['scope'], 'PUBLIC21_PREFIX_PC0_9_SOFTWARE_MODEL_ONLY')
        self.assertEqual([c['rows'] for c in receipt['cases']], [16, 128])
        self.assertFalse(receipt['full_block_executed'])
        self.assertFalse(receipt['whole_program_terminal_observed'])
        self.assertFalse(receipt['carried_cache_executed'])
        self.assertIsNone(receipt['hardware_cycles'])
        self.assertIsNone(receipt['full_wall_mac_utilization'])
        self.assertEqual(receipt['native_acceptance'], 'UNCHANGED_FAIL_POLICY_PENDING')
        self.assertEqual(receipt['historical_ffn4']['commit'], '8212a32f43338163baee4126e522dcacede0fa23')
        self.assertFalse(receipt['historical_ffn4']['new_source_pass_inherited'])
        self.assertEqual(hashlib.sha256((HERE / 'numerical_receipt.json').read_bytes()).hexdigest(),
                         '011712a7bbcee20cd4226452ab7d7b7d2d1dd78e7a0b83a83899d7f85ca19541')
        root = HERE.parents[2]
        for path, digest in receipt['source_sha256'].items():
            # The prefix PASS remains bound to the immutable original source,
            # never rebound to the new fullgraph successor's live files.
            raw = subprocess.check_output(['git', 'show', COMMIT + ':' + path], cwd=root)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), digest, path)
        for case in receipt['cases']:
            rows = case['rows']
            self.assertEqual(case['prelaunch_intermediate_payloads'], [])
            self.assertEqual(case['checkpoint']['public_completion_pcs'], list(range(10)))
            self.assertTrue(case['checkpoint']['all_actual_final_acks_before_comparison'])
            self.assertTrue(case['checkpoint']['pc10_not_executed'])
            self.assertIsNone(case['host']['launch_result'])
            self.assertEqual(case['host']['accepted']['result_fire'], 0)
            self.assertEqual(case['host']['accepted']['completion_fire'], 10)
            self.assertEqual(case['public_metadata']['command']['count'], 21)
            self.assertEqual(case['public_metadata']['descriptor']['count'], 215)
            self.assertEqual(case['metadata_read_bytes'], 7168)
            self.assertEqual(case['checked_values'], rows * 7936)
            writes = case['memory_accepted']['write_ack_bytes']
            self.assertEqual(writes, rows * 7936 * 4)
            self.assertEqual(writes, case['memory_accepted']['write_data_bytes'])
            self.assertEqual(case['all_read_write_bytes'],
                             writes + case['payload_read_bytes'] + case['metadata_read_bytes'])
            self.assertEqual(set(case['outputs']), set(case['comparison']))
            for name, output in case['outputs'].items():
                c = case['comparison'][name]
                self.assertTrue(output['terminal'] and output['published'])
                self.assertEqual(output['bytes'], output['written_bytes'])
                self.assertEqual(output['bytes'], output['ack_bytes'])
                self.assertEqual(output['sha256'], c['actual_sha256'])
                self.assertEqual(c['actual_sha256'], c['independent_sha256'])
                self.assertEqual(c['independent_bit_mismatches'], 0)
                self.assertIn(c['saved_bit_mismatches'], (None, 0))
            self.assertTrue(case['observed_software_macs']['not_hardware_measurement'])
            self.assertEqual(case['observed_software_macs']['useful'], rows * 1536 * 2048)
            self.assertEqual(case['observed_software_macs']['physical_host_fmas'], 402653184)

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
