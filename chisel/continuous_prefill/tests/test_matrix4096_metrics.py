#!/usr/bin/env python3
"""Counter arithmetic rejection tests; these do not simulate hardware."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from compare_matrix4096_real2 import metrics
class MetricsTest(unittest.TestCase):
    def base(self): return dict(cycles='146854495',useful_macs='1498202112',executed_macs='1524105216',read_bytes='385152512',write_ack_bytes='5636096')
    def test_frozen_baseline(self):
        r=metrics(self.base(),512)
        self.assertAlmostEqual(r['useful_wall_mac_utilization'],1498202112/(146854495*512))
        self.assertEqual(r['peak_tmac_per_s_at_target_clock'],0.4096)
    def test_not_eightfold_speedup(self):
        a=metrics(self.base(),512);b=metrics(self.base(),4096)
        self.assertEqual(a['latency_ms_at_target_clock'],b['latency_ms_at_target_clock'])
        self.assertEqual(a['useful_wall_mac_utilization']/8,b['useful_wall_mac_utilization'])
        self.assertEqual(b['peak_tmac_per_s_at_target_clock'],3.2768)
    def test_reject_counter_types(self):
        for v in (True,1.2,-1,'NaN','1e9','-1'):
            with self.subTest(v=v):
                r=self.base();r['cycles']=v
                with self.assertRaises(ValueError):metrics(r,4096)
    def test_reject_counter_bounds(self):
        for change in ({'cycles':'0'},{'executed_macs':'1'},{'useful_macs':'0'},{'cycles':'1'}):
            r=self.base();r.update(change)
            with self.assertRaises(ValueError):metrics(r,4096)
    def test_reject_peak(self):
        for p in (0,2048,True,'4096'):
            with self.assertRaises(ValueError):metrics(self.base(),p)
if __name__=='__main__':unittest.main(verbosity=2)
