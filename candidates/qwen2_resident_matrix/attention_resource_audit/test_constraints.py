"""Cheap counts/source guards; these do not execute floating-point RTL."""
import json
import unittest
from .constraints import (HERE, check_sources, report, raw_k_bank_pair,
                          proposed_swizzled_cells, scalar_primitive_trace,
                          scalar_full_exp_trace)


class ResourceAuditTest(unittest.TestCase):
    def test_pinned_sources(self):
        self.assertGreaterEqual(check_sources(), 10)

    def test_saved_report_reproduces(self):
        # Normalize tuples exactly as the CLI's JSON serialization does.
        self.assertEqual(json.loads((HERE / 'M128_BOUNDS.json').read_text()),
                         json.loads(json.dumps(report())))

    def test_scalar_trace_edges(self):
        self.assertEqual(len(scalar_primitive_trace()), 3)
        self.assertEqual(len(scalar_full_exp_trace()), 20)
        self.assertEqual(scalar_full_exp_trace().count('expMul'), 7)
        self.assertEqual(scalar_full_exp_trace().count('expAdd'), 7)

    def test_exact_work_and_budgets(self):
        r = report()
        self.assertEqual((r['causal_pairs'], r['qk_groups'], r['fold_adds']),
                         (99072, 6912, 1585152))
        self.assertEqual(r['matrix_issue_floor'], 1534080)
        self.assertEqual(r['overhead_budget_80'], 301500)
        self.assertEqual(r['overhead_budget_90_exact'], '292640/3')
        self.assertEqual(r['serial_fold_service_only']['minimum_cycles'], 6289536)

    def test_vector_reduction_is_not_acceptance(self):
        r = report()
        self.assertEqual(r['hypothetical_vector_fold_only']['minimum_cycles'], 1644672)
        self.assertLess(r['hypothetical_vector_fold_and_scale_only']['utilization_ceiling_percent'], 90)
        self.assertFalse(r['accepted_80'])
        self.assertFalse(r['accepted_90'])
        self.assertIsNone(r['actual_hardware_cycles'])

    def test_scalar_softmax_is_separate_resource_debt(self):
        r = report()
        self.assertEqual(r['scalar_softmax_subtract_and_sum_minimum'], 594432)
        self.assertEqual(r['scalar_softmax_exp_subtract_sum_minimum'], 917760)
        self.assertGreater(r['scalar_softmax_subtract_and_sum_minimum'], r['overhead_budget_80'])

    def test_real_layout_bank_collision(self):
        for first in range(0, 128, 16):
            for head in range(2):
                for stripe in range(8):
                    pairs = {raw_k_bank_pair(k, head, stripe) for k in range(first, first + 16)}
                    self.assertEqual(len(pairs), 1)

    def test_proposed_swizzle_capacity_and_conflicts_only(self):
        cells = [cell for k in range(128) for h in range(2) for s in range(8)
                 for cell in proposed_swizzled_cells(k, h, s)]
        self.assertEqual(len(cells), len(set(cells)))
        self.assertTrue(all(0 <= b < 16 and 0 <= w < 256 for b, w in cells))
        for stripe in range(8):
            banks = [proposed_swizzled_cells(k, 0, stripe)[0][0] for k in range(16)]
            self.assertTrue(all(banks.count(bank) == 2 for bank in set(banks)))

    def test_silu_cannot_be_counted_as_free(self):
        r = report()
        self.assertEqual(r['silu_vectors'], 71680)
        self.assertEqual(r['silu_service_minimum_excluding_division'], 1075200)
        self.assertEqual(r['silu_all_full_exp_service_excluding_division'], 2293760)


if __name__ == '__main__':
    unittest.main()
