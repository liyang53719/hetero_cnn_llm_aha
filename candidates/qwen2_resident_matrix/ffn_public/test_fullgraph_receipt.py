"""Check the compact fullgraph result without loading any model payload."""
import hashlib
import json
from pathlib import Path
import subprocess
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
COMMIT = '37b7de74431ed79b7e9f3d52d308ed7f46727b7a'
RECEIPT_SHA = '3d0f449d3e2a62f87ea915d89930dc5788f0ea835b11ce265a169c1fc4e5570e'


class FullgraphReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads((HERE / 'fullgraph_numerical_receipt.json').read_text())

    def test_historical_source_and_acceptance_scope(self):
        r = self.receipt
        self.assertEqual(hashlib.sha256((HERE / 'fullgraph_numerical_receipt.json').read_bytes()).hexdigest(),
                         RECEIPT_SHA)
        self.assertEqual(r['scope'], 'PUBLIC21_FULLGRAPH_SOFTWARE_MODEL_COLD_M16_M128')
        self.assertTrue(r['full_block_software_model_executed'])
        for key in ['full_block_hardware_executed', 'rtl_executed', 'scala_host_executed',
                    'actual_idma', 'carried_cache_executed', 'official_framework_forward']:
            self.assertFalse(r[key], key)
        self.assertEqual(r['native_acceptance'], 'UNCHANGED_FAIL_POLICY_PENDING')
        self.assertIsNone(r['hardware_cycles'])
        self.assertIsNone(r['full_wall_mac_utilization'])
        self.assertEqual(len(r['source_sha256']), 75)
        for path, sha in r['source_sha256'].items():
            # The historical PASS stays bound to the exact original commit and
            # path. Successor live files need their own execution evidence.
            raw = subprocess.check_output(['git', 'show', COMMIT + ':' + path], cwd=ROOT)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), sha, path)
        for path, sha in r['imported_python_sha256'].items():
            self.assertEqual(r['source_sha256'][path], sha)
        self.assertFalse(r['historical_prefix']['pass_inherited'])
        self.assertEqual(r['cases'][0]['comparison_outcome'], 'PASS_WITHIN_ORIGINAL_RUN')
        recovered = r['cases'][1]
        self.assertEqual(recovered['original_run_status'], 'FAILED')
        self.assertEqual(recovered['original_run_error'], 'software recipe timeout; no completion claimed')
        self.assertEqual(recovered['comparison_outcome'], 'PASS_POST_TERMINAL_ARCHIVE_REUSE')
        self.assertTrue(recovered['postprocessing']['original_failure_preserved'])
        self.assertFalse(recovered['postprocessing']['model_rerun'] or recovered['postprocessing']['reference_rerun'])
        provenance = recovered['postprocessing']['actual_output_provenance']
        self.assertEqual(len(provenance), 19)
        self.assertEqual({k for k, v in provenance.items() if 'not prebound' in v}, {'gate', 'up'})

    def test_complete_public_sequence_and_all_stage_comparisons(self):
        self.assertEqual([x['rows'] for x in self.receipt['cases']], [16, 128])
        expected = {'n0', 'qr', 'kr', 'v', 'q', 'k', 'att', 'o', 'r', 'n1', 'gate', 'up', 'act', 'down', 'y'}
        for c in self.receipt['cases']:
            self.assertEqual(c['prelaunch_intermediate_payloads'], [])
            self.assertTrue(c['comparison_after_whole_terminal'])
            self.assertEqual(c['public_metadata']['command']['count'], 21)
            self.assertEqual(c['public_metadata']['descriptor']['count'], 215)
            h = c['host']
            self.assertEqual([x['pc'] for x in h['completions']], list(range(21)))
            self.assertTrue(all(x['status'] is None for x in h['completions']))
            self.assertEqual(h['launch_result']['completed'], 21)
            self.assertEqual(h['launch_result']['jobs'], 17)
            self.assertIsNone(h['launch_result']['status'])
            self.assertEqual(h['accepted']['result_fire'], 1)
            self.assertEqual(h['accepted']['owner_result_fire'], 17)
            self.assertEqual(set(c['whole_comparison']), expected)
            self.assertEqual(set(c['additional_prefix_comparison']), {'qraw', 'kraw', 'vraw', 'kv'})
            self.assertEqual(c['whole_stage_count'], 15)
            self.assertEqual(c['distinct_output_count'], 19)
            self.assertEqual(c['whole_checked_values'], sum(x['values'] for x in c['whole_comparison'].values()))
            self.assertEqual(c['distinct_checked_values'], c['whole_checked_values'] + sum(x['values'] for x in c['additional_prefix_comparison'].values()))
            for entry in [*c['whole_comparison'].values(), *c['additional_prefix_comparison'].values()]:
                self.assertEqual(entry['independent_bit_mismatches'], 0)
                self.assertEqual(entry['actual_sha256'], entry['independent_sha256'])
                self.assertIn(entry['saved_bit_mismatches'], [0, None])
                if entry['saved_bit_mismatches'] == 0:
                    self.assertEqual(entry['actual_sha256'], entry['saved_sha256'])

    def test_shared_service_retirement_and_real_write_counts(self):
        for c in self.receipt['cases']:
            h, m, mem = c['host'], c['matrix'], c['memory_accepted']
            self.assertTrue(m['same_accumulator_resource'] and h['same_owner_and_banks'])
            self.assertFalse(m['reset_required'] or h['reset_required'])
            self.assertEqual(m['accumulator_bytes'], 81920)
            counter = m['counters']
            self.assertEqual([counter[x] for x in ['owner_acquires', 'owner_responses', 'owner_releases']], [118] * 3)
            self.assertEqual(counter['dense_groups'], counter['dense_done'])
            self.assertEqual(counter['normal_groups'], counter['normal_done'])
            self.assertEqual(counter['normal_steps'], counter['normal_results'])
            self.assertEqual(counter['normal_results'], counter['legacy_replies'])
            self.assertEqual(m['dense_fma_calls'], counter['dense_steps'] * 4096)
            self.assertEqual(m['normal_fma_calls'], counter['normal_steps'] * 512)
            self.assertEqual(h['launch_result']['executed_macs'], m['dense_fma_calls'] + m['normal_fma_calls'])
            prefix = c['down']['prefix']
            self.assertEqual(mem['write_ack_bytes'], mem['write_data_bytes'])
            self.assertEqual(mem['write_ack_bytes'], h['launch_result']['write_bytes'] + prefix['ack_bytes'])
            self.assertEqual(c['all_read_write_bytes'], mem['read_bytes'] + mem['write_ack_bytes'])
            self.assertEqual(prefix['extent'], 786432)
            self.assertEqual(prefix['completed_sweeps'], 3)
            self.assertEqual(prefix['ack_bytes'], 3 * prefix['extent'])
            self.assertTrue(prefix['shared_public_allocation'] and prefix['seed_ack_before_overwrite'] and prefix['exact_version_read_before_overwrite'])
            for version in prefix['versions'].values():
                self.assertEqual([version[k] for k in ['ack_beats', 'read_beats', 'seed_beats']], [12288] * 3)
            self.assertEqual(c['ffn']['windows'], 56)
            self.assertEqual(c['ffn']['coordinator_accepted']['window_result_fire'], 112)
            self.assertEqual(c['virtual_outputs']['physical_writes'], 0)
            for k in ['attention', 'down']:
                fence = c[k]['final_ack_fence']
                self.assertTrue(fence['terminal_strictly_after_final_ack'])
                self.assertGreater(fence['terminal_tick'], fence['final_ack_tick'])

    def test_mode_counts_and_conditional_bounds_do_not_claim_rtl_utilization(self):
        c = self.receipt['cases'][1]
        b = self.receipt['architecture_bounds']
        self.assertEqual(b['fixed_matrix_macs_per_cycle'], 4096)
        useful = 128 * (2*1536*1536 + 2*1536*256 + 3*1536*8960) + 2*12*128*(128*129//2)
        self.assertEqual(useful, c['host']['launch_result']['useful_macs'])
        self.assertEqual(b['useful_matrix_macs'], useful)
        steps = c['matrix']['counters']['dense_steps'] + c['matrix']['counters']['normal_steps']
        self.assertEqual(b['serialized_single_service_issue_lower_bound_cycles'], steps)
        self.assertEqual(b['issue_utilization_upper_bound'], useful / (4096 * steps))
        traffic = c['memory_accepted']['read_bytes'] + c['memory_accepted']['write_ack_bytes']
        self.assertEqual(traffic, sum(c['reads_by_allocation'].values()) + c['memory_accepted']['write_ack_bytes'])
        self.assertEqual(b['shared_read_write_bytes'], traffic)
        self.assertEqual(b['assumed_shared_read_write_bytes_per_cycle'], 64)
        self.assertEqual(b['conditional_traffic_lower_bound_cycles'], (traffic + 63) // 64)
        self.assertEqual(b['conditional_traffic_utilization_upper_bound'], useful / (4096*((traffic + 63)//64)))
        self.assertFalse(b['assumed_bandwidth_is_rtl_measurement'])
        self.assertIsNone(b['predicted_complete_cycles'])
        self.assertIsNone(b['rtl_measured_cycles'])


if __name__ == '__main__':
    unittest.main()
