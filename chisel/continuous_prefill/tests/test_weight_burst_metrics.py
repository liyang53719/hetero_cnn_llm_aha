#!/usr/bin/env python3
"""Validator-only negative tests. Synthetic counters here are NOT DUT evidence."""
import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from compare_weight_burst_real2 import validate_counters
class WeightBurstMetricsTest(unittest.TestCase):
 def setUp(self):
  self.old=dict(cycles=114418263,useful_macs=1498202112,executed_macs=1524105216,read_bytes=385152512,write_ack_bytes=5636096)
  self.new=dict(self.old,cycles=100000000,read_bursts=1000000,weight_cache_hits=5018008,idma_transfers=1088064,weight_read_burst_beats=16)
 def test_complete_example(self):
  r=validate_counters(self.old,self.new);self.assertAlmostEqual(r['cycle_speedup'],1.14418263)
 def test_reject_changed_work_or_traffic(self):
  for k in ('useful_macs','executed_macs','read_bytes','write_ack_bytes'):
   with self.subTest(k=k):
    x=dict(self.new);x[k]-=1
    with self.assertRaises(ValueError):validate_counters(self.old,x)
 def test_reject_counter_types(self):
  for k in ('read_bursts','weight_cache_hits','idma_transfers','weight_read_burst_beats'):
   for v in (True,-1,1.5,'x'):
    with self.subTest(k=k,v=v):
     x=dict(self.new);x[k]=v
     with self.assertRaises(ValueError):validate_counters(self.old,x)
 def test_reject_missing_bursts_hits_or_transfers(self):
  for k in ('read_bursts','weight_cache_hits','idma_transfers'):
   with self.subTest(k=k):
    x=dict(self.new);x[k]+=1
    with self.assertRaises(ValueError):validate_counters(self.old,x)
 def test_reject_nonburst_capacity(self):
  x=dict(self.new,weight_read_burst_beats=1)
  with self.assertRaises(ValueError):validate_counters(self.old,x)
 def test_reject_impossible_compute_capacity(self):
  x=dict(self.new,cycles=1)
  with self.assertRaises(ValueError):validate_counters(self.old,x)
if __name__=='__main__':unittest.main(verbosity=2)
