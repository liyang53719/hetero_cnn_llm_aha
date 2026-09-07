#!/usr/bin/env python3
"""Analyzer counterexample tests. Fixtures below are NOT hardware results."""
import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from analyze_weight_burst_real2 import analyze, OPS
from compare_matrix4096_real2 import metrics

class AnalysisTest(unittest.TestCase):
    def example(self):
        c=dict(cycles=114418263,useful_macs=1498202112,executed_macs=1524105216,
               read_bytes=385152512,write_ack_bytes=5636096)
        a,b=metrics(c,4096),metrics(dict(c,cycles=80000000),4096)
        rows=[dict(pc=i,opcode=OPS[i%21],baseline4096_cycles=1000000,burst4096_cycles=1000000) for i in range(42)]
        rows[1]['baseline4096_cycles']+=a['cycles']-1-42000000
        rows[1]['burst4096_cycles']+=b['cycles']-1-42000000
        return dict(status='PASS_WEIGHT_BURST_REAL16_TWO_LAYER_EXACT_COMPARISON',
                    tested_source='a'*40,baseline_source='b'*40,tokens=16,layers=2,
                    host_commands=42,checked_fp32=1409024,bit_differences=0,
                    baseline4096=a,burst4096=b,cycle_speedup=a['cycles']/b['cycles'],
                    read_bursts=500000,cached_logical_beats=5518008,idma_transfers=588064,
                    per_command_durations=rows)
    def test_account_all_intervals(self):
        r=analyze(self.example())
        self.assertEqual(sum(x['burst_cycles'] for x in r['per_category'])+1,80000000)
        self.assertEqual(r['optimistic_read_only_lower_bound_cycles'],6018008)
        self.assertAlmostEqual(r['single_512bit_read_port_peak_GBps_at_target'],51.2)
    def test_reject_wrong_scope(self):
        for k,v in [('tokens',32),('layers',1),('host_commands',21),('checked_fp32',1),('bit_differences',False),('status','RUNNING')]:
            r=self.example();r[k]=v
            with self.subTest(k=k),self.assertRaises(ValueError):analyze(r)
    def test_reject_bad_sources(self):
        for v in ['x',7,'a'*39]:
            r=self.example();r['tested_source']=v
            with self.assertRaises(ValueError):analyze(r)
    def test_reject_missing_duplicate_opcode(self):
        for mode in range(3):
            r=self.example()
            if mode==0:r['per_command_durations'].pop()
            elif mode==1:r['per_command_durations'][41]['pc']=40
            else:r['per_command_durations'][10]['opcode']='MATRIX_GEMM'
            with self.assertRaises(ValueError):analyze(r)
    def test_reject_bad_cycles(self):
        for v in [True,-1,1.5,'100']:
            r=self.example();r['per_command_durations'][0]['burst4096_cycles']=v
            with self.assertRaises(ValueError):analyze(r)
    def test_reject_lost_cycles(self):
        r=self.example();r['per_command_durations'][0]['burst4096_cycles']+=1
        with self.assertRaises(ValueError):analyze(r)
    def test_reject_inflated_metrics(self):
        for mode in range(2):
            r=self.example()
            if mode:r['cycle_speedup']=8
            else:r['burst4096']['useful_wall_mac_utilization']=0.79
            with self.assertRaises(ValueError):analyze(r)
    def test_reject_missing_bytes_or_macs(self):
        for k in ['ddr_read_bytes','ddr_write_ack_bytes','useful_macs','executed_macs','matrix_macs_per_cycle']:
            r=self.example();r['burst4096'][k]=1
            with self.assertRaises(ValueError):analyze(r)
    def test_reject_burst_miscount(self):
        for k,v in [('read_bursts',0),('cached_logical_beats',0),('idma_transfers',1)]:
            r=self.example();r[k]=v
            with self.assertRaises(ValueError):analyze(r)
if __name__=='__main__':unittest.main(verbosity=2)
