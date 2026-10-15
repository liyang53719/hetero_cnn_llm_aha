import unittest
from dataclasses import replace
from candidates.qwen2_aten_q_schedule_screen import screen as s

class ScreenTests(unittest.TestCase):
    def test_fixed_resources_and_actual_source_identity(self):
        self.assertEqual(s.source_check(),5)
        r=s.resource_mapping();self.assertEqual(r['accumulator_words'],20480)
        self.assertEqual(r['accumulator_bytes'],81920);self.assertEqual(r['maximum_live_outputs'],320)
        self.assertEqual(r['new_accumulator_words'],0);self.assertEqual(r['new_mac_lanes'],0)
    def test_geometric_fill_is_not_utilization(self):
        sparse=s.screen();wide=s.screen('wide_k_hypothesis')
        self.assertEqual(sparse['geometric_issue_fill'],1/64)
        self.assertEqual(wide['geometric_issue_fill'],1)
        for r in (sparse,wide):
            self.assertIsNone(r['hardware_cycles']);self.assertIsNone(r['cycle_prediction'])
            self.assertIsNone(r['measured_utilization']);self.assertFalse(r['hardware_implemented'])
            self.assertLess(r['conditional_effective_mac_ratio'],r['geometric_issue_fill'])
    def test_full_work_and_reduction_counts(self):
        r=s.screen();self.assertEqual(r['useful_macs'],301989888)
        self.assertEqual(r['vector_fp32_adds'],12779520)
        self.assertEqual(r['issued_physical_mac_slots'],4718592*4096)
        self.assertEqual(s.screen('wide_k_hypothesis')['issued_physical_mac_slots'],73728*4096)
    def test_nonfree_full_denominator(self):
        r=s.screen();ledger=r['conditional_serial_cost_units']
        self.assertEqual(len(ledger),10);self.assertTrue(all(v>0 for v in ledger.values()))
        self.assertEqual(r['conditional_serial_total'],sum(ledger.values()))
        self.assertGreater(ledger['fma_issue_and_recurrence'],4718592)
    def test_service_cost_monotonicity(self):
        base=s.screen()
        for field in s.asdict(s.Assumptions()):
            a=replace(s.Assumptions(),**{field:getattr(s.Assumptions(),field)+1})
            self.assertLess(s.screen(assumptions=a)['conditional_effective_mac_ratio'],base['conditional_effective_mac_ratio'])
    def test_no_free_or_shortened_resource_assumptions(self):
        for field in s.asdict(s.Assumptions()):
            for value in (0,-1,True):
                with self.assertRaises(ValueError):s.screen(assumptions=replace(s.Assumptions(),**{field:value}))
        with self.assertRaises(ValueError):s.screen(assumptions=replace(s.Assumptions(),recurrence_cycles=4))
        with self.assertRaises(ValueError):s.screen('invented')

if __name__=='__main__':unittest.main()
