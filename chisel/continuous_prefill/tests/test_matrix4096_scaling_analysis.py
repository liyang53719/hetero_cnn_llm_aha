#!/usr/bin/env python3
"""Negative tests of report analysis, NOT numerical hardware simulation."""
import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from analyze_matrix4096_scaling import analyze,OPCODES
from compare_matrix4096_real2 import metrics

class ScalingAnalysisTest(unittest.TestCase):
    def example(self):
        old_cycles,new_cycles=146854495,110000001
        base=dict(cycles=old_cycles,useful_macs=1498202112,executed_macs=1524105216,read_bytes=385152512,write_ack_bytes=5636096)
        new=dict(base,cycles=new_cycles)
        rows=[dict(pc=pc,opcode=OPCODES[pc%21],baseline_cycles=1000000,matrix4096_cycles=1000000) for pc in range(42)]
        rows[1]["baseline_cycles"]+=old_cycles-1-42000000
        rows[1]["matrix4096_cycles"]+=new_cycles-1-42000000
        return dict(status="PASS_MATRIX4096_REAL16_TWO_LAYER_EXACT_COMPARISON",tokens=16,layers=2,checked_fp32=1409024,bit_differences=0,
                    tested_source="a"*40,baseline_source="b"*40,baseline_512=metrics(base,512),matrix4096=metrics(new,4096),
                    wall_cycle_speedup=old_cycles/new_cycles,per_command_durations=rows)
    def test_account_all_cycles_and_fused_attention(self):
        r=analyze(self.example());d={x['category']:x for x in r['per_category']}
        self.assertEqual(d['attention_fused']['matrix4096_cycles'],6000000)
        self.assertEqual(sum(x['matrix4096_cycles'] for x in d.values())+1,110000001)
        self.assertAlmostEqual(r['useful_utilization_ratio'],r['wall_speedup']/8)
        self.assertEqual(r['frozen_fp32_container_weight_bytes'],374341632)
    def test_reject_wrong_scope(self):
        for key,value in [('tokens',32),('layers',1),('checked_fp32',1),('bit_differences',1),('status','RUNNING')]:
            with self.subTest(key=key):
                r=self.example();r[key]=value
                with self.assertRaises(ValueError):analyze(r)
    def test_reject_missing_reordered_and_wrong_opcode(self):
        for mode in range(3):
            r=self.example()
            if mode==0:r['per_command_durations'].pop()
            elif mode==1:r['per_command_durations'][20]['pc']=19
            else:r['per_command_durations'][11]['opcode']='MATRIX_GEMM'
            with self.assertRaises(ValueError):analyze(r)
    def test_reject_noninteger_or_negative_cycles(self):
        for value in [True,1.5,-1,'1']:
            r=self.example();r['per_command_durations'][0]['matrix4096_cycles']=value
            with self.assertRaises(ValueError):analyze(r)
    def test_reject_unaccounted_cycles(self):
        r=self.example();r['per_command_durations'][41]['matrix4096_cycles']+=1
        with self.assertRaises(ValueError):analyze(r)
    def test_reject_inflated_metrics(self):
        for mode in range(2):
            r=self.example()
            if mode==0:r['matrix4096']['useful_wall_mac_utilization']=0.98
            else:r['wall_cycle_speedup']=8
            with self.assertRaises(ValueError):analyze(r)
    def test_reject_missing_work_and_traffic(self):
        for key,value in [('useful_macs',1),('ddr_read_bytes',1),('matrix_macs_per_cycle',512)]:
            r=self.example();r['matrix4096'][key]=value
            with self.assertRaises(ValueError):analyze(r)
if __name__=='__main__':unittest.main(verbosity=2)
