"""Source-only standard-library tests. No tensor, runner, compiler or RTL."""
import ast
from fractions import Fraction
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger


class LedgerTests(unittest.TestCase):
    def test_source_pins(self):
        self.assertEqual(ledger.verify_sources(), ledger.SOURCE_PINS)
        self.assertEqual(len(ledger.SOURCE_PINS), 9)
        self.assertTrue(all(not p.startswith('work/') for p in ledger.SOURCE_PINS))

    def test_current_attention_traffic(self):
        a = ledger.workload()['attention']
        self.assertEqual(a['causal_pairs'], 99072)
        self.assertEqual(a['q_read_bytes'], 786432)
        self.assertEqual(a['k_repeated_read_bytes'], 50724864)
        self.assertEqual(a['v_repeated_read_bytes'], 50724864)
        self.assertEqual(a['output_write_bytes'], 786432)
        self.assertEqual(a['external_bytes'], 103022592)
        self.assertEqual(a['score_probability_external_bytes'], 0)
        self.assertFalse(a['resident_kv_cache_implemented_in_pinned_path'])

    def test_dense_and_shared_bus_subset(self):
        w = ledger.workload()
        self.assertEqual(len(w['dense']), 7)
        self.assertEqual(w['useful']['full_block_macs'], 6014828544)
        self.assertEqual(w['useful']['full_width_equivalent_slots'], 1468464)
        d = w['known_ddr_subset']
        self.assertEqual(d['unique_seven_dense_weight_bytes'], 93585408)
        self.assertEqual(d['lower_bound_bytes'], 196608000)
        self.assertEqual(d['ideal_64b_service_slot_floor'], 3072000)
        self.assertEqual(d['full_mac_capacity_ceiling'], Fraction('0.478015625'))
        self.assertFalse(d['complete_block_traffic'])

    def test_issue_workload_not_full_cycle_prediction(self):
        w = ledger.workload()
        self.assertEqual(w['attention']['qk_matrix_requests'], 792576)
        self.assertEqual(w['attention']['pv32_matrix_requests'], 396288)
        i = w['issue_capacity']
        self.assertEqual(i['ideal_dense_fma_issue_floor'], 1462272)
        self.assertEqual(i['attention_legacy_request_count'], 1188864)
        self.assertEqual(i['shared_issue_service_slot_floor'], 2651136)
        self.assertEqual(i['full_mac_capacity_ceiling'], Fraction(1468464, 2651136))

    def test_scalar_and_silu_units(self):
        w = ledger.workload()
        s = w['scalar_workload']
        self.assertEqual(s['attention_add_mul'], 2278656)
        self.assertEqual(s['attention_add'] + s['attention_mul'], 2278656)
        self.assertEqual(s['attention_exp_negative_calls'], 99072)
        self.assertEqual(s['attention_div_calls'], 1536)
        self.assertIsNone(s['exp_internal_primitive_expansion_count'])
        f = w['silu_workload']
        self.assertEqual(f['vector_packets'], 71680)
        self.assertEqual(f['vector_phase_invocations'], 71680*6)
        self.assertEqual(f['local_bridge_logical_payload_bytes'], 13762560)
        self.assertEqual(f['local_bridge_read_bytes'] + f['local_bridge_write_bytes'], 13762560)
        self.assertFalse(f['local_bridge_bytes_are_ddr'])

    def test_exact_80_budget_boundary(self):
        b = ledger.target_budget(Fraction(4, 5))
        self.assertEqual(b['integer_complete_block_slot_budget'], 1835580)
        self.assertEqual(b['ideal_shared_64b_byte_budget'], 117477120)
        self.assertEqual(b['remaining_after_unique_dense_weights'], 23891712)
        self.assertTrue(ledger.meets_target(1835580, Fraction(4, 5)))
        self.assertFalse(ledger.meets_target(1835581, Fraction(4, 5)))

    def test_exact_90_budget_boundary(self):
        b = ledger.target_budget(Fraction(9, 10))
        self.assertEqual(b['exact_complete_block_slot_budget'], Fraction(4894880, 3))
        self.assertEqual(b['integer_complete_block_slot_budget'], 1631626)
        self.assertEqual(b['ideal_shared_64b_byte_budget'], 104424064)
        self.assertEqual(b['remaining_after_unique_dense_weights'], 10838656)
        self.assertTrue(ledger.meets_target(1631626, Fraction(9, 10)))
        self.assertFalse(ledger.meets_target(1631627, Fraction(9, 10)))

    def test_reject_inexact_or_invalid_thresholds(self):
        for target in (0.8, 1, Fraction(0), Fraction(-1), Fraction(2)):
            with self.subTest(target=target), self.assertRaises(ValueError):
                ledger.target_budget(target)
        for slots in (0, -1, 1.5, True):
            with self.subTest(slots=slots), self.assertRaises(ValueError):
                ledger.meets_target(slots, Fraction(4, 5))

    def test_no_acceptance_or_cycle_claim(self):
        r = ledger.report()
        for key in ('rtl_cycles', 'measured_cycles', 'prediction_cycles',
                    'hardware_utilization', 'numerical_acceptance'):
            self.assertIsNone(r[key])
        for key in ('rtl_executed', 'full_chain_executed', 'old_acceptance_changed',
                    'old_rectangular_ledger_used'):
            self.assertFalse(r[key])
        imports = ast.parse(Path(ledger.__file__).read_text())
        modules = {n.module for n in ast.walk(imports) if isinstance(n, ast.ImportFrom)}
        modules |= {a.name for n in ast.walk(imports) if isinstance(n, ast.Import) for a in n.names}
        self.assertEqual(modules, {'argparse', 'fractions', 'hashlib', 'json', 'pathlib'})

    def test_source_only_cold_tree_and_fail_closed_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for relative in ledger.SOURCE_PINS:
                dest = root / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ledger.ROOT / relative, dest)
            script = root / 'candidates/qwen2_live_attention_cost_ledger/ledger.py'
            script.parent.mkdir(parents=True)
            shutil.copyfile(ledger.__file__, script)
            p = subprocess.run([sys.executable, '-I', '-B', str(script)],
                               cwd=root, capture_output=True, text=True, check=True)
            result = json.loads(p.stdout)
            self.assertEqual(result['known_ddr_subset']['lower_bound_bytes'], 196608000)
            self.assertFalse((root / 'work').exists())
            target = root / next(iter(ledger.SOURCE_PINS))
            target.write_bytes(target.read_bytes() + b'\n# deliberate test drift\n')
            with self.assertRaisesRegex(ValueError, 'source drift'):
                ledger.report(root)
            target.unlink()
            with self.assertRaisesRegex(ValueError, 'missing pinned source'):
                ledger.report(root)


if __name__ == '__main__':
    unittest.main()
