import unittest
from .schedule import GroupSchedule
from .model import schedule_counts,serial_lower_bound

class ScheduleTests(unittest.TestCase):
    def test_frozen_sources_and_resource_structure(self):
        from .check_sources import check
        result=check()
        self.assertEqual((result['sources'],result['own']),(10,6))
        self.assertFalse(result['native_execution'])

    def test_joined_wide_result_holds_and_blocks_done_until_ack(self):
        for mask in (15,255):
            m=GroupSchedule(8,mask,latency=3)
            while m.held is None:m.tick()
            held=m.held
            for _ in range(11):
                p=m.tick(result_ready=False)
                self.assertEqual(p['result'],held);self.assertFalse(p['step_fire']);self.assertFalse(p['done_valid'])
            self.assertTrue(m.tick()['result_fire']);self.assertEqual(m.result_acks,1)
            m.tick()
            for _ in range(3):self.assertTrue(m.tick(done_ready=False)['done_valid'])
            self.assertTrue(m.tick()['done_fire']);self.assertEqual((m.accepted,m.returned),(8,8))
    def test_resource_and_full128_count_bound_is_not_utilization(self):
        c=schedule_counts(128)
        self.assertEqual((c['packed_qk_steps'],c['packed_pv_steps'],c['packed_steps']),(55296,16512,71808))
        self.assertEqual(c['legacy_qk_steps']+c['legacy_pv_steps'],1585152)
        self.assertEqual(c['qk_fold_adds'],1585152)
        self.assertEqual(c['physical_slice_issues'],508416)
        self.assertEqual(c['qk_issued_fmas']+c['pv_issued_fmas'],512*c['physical_slice_issues'])
        self.assertEqual((c['contexts_used'],c['metadata_slots_used'],c['result_tiles_used']),(1,1,1))
        b=serial_lower_bound(128,dense_issue_cycles=1462272)
        self.assertEqual(b['serial_minimum_cycles'],6289536)
        ideal=serial_lower_bound(128,dense_issue_cycles=1462272,fold_latency=1,fold_ii=1)
        self.assertEqual(ideal['serial_minimum_cycles'],3119232)
        self.assertTrue(ideal['hypothetical_unrealizable_ii1'])
        self.assertIsNone(b['measured_utilization']);self.assertFalse(b['accepts_80_percent'])
        self.assertGreater(serial_lower_bound(128,dense_issue_cycles=1462272,fold_latency=5)['serial_minimum_cycles'],b['serial_minimum_cycles'])
    def test_domain_and_feed_stalls(self):
        m=GroupSchedule(1,15,latency=1);m.tick()
        for _ in range(5):self.assertFalse(m.tick(step_valid=False)['step_fire'])
        self.assertEqual(m.accepted,0)
        for bad in (True,0,129):
            with self.assertRaises(ValueError):schedule_counts(bad)
        with self.assertRaises(ValueError):GroupSchedule(8,15,latency=True)

if __name__=='__main__':unittest.main()
