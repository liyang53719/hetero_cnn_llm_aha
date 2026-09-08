#!/usr/bin/env python3
"""Synthetic reports exercise analysis rejection only, NOT hardware results."""
import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from analyze_production_pipeline import analyze,OPCODES
from compare_matrix4096_real2 import metrics

class AnalysisTest(unittest.TestCase):
    def fixture(self):
        def m(c,peak):return metrics(dict(cycles=c,useful_macs=1498202112,executed_macs=1524105216,
                                         read_bytes=385152512,write_ack_bytes=5636096),peak)
        rows=[dict(pc=i,opcode=OPCODES[i%21],burst_cycles=100000,pipeline_cycles=100000) for i in range(42)]
        rows[0]['burst_cycles']+=82001445-4200000
        rows[0]['pipeline_cycles']+=40000000-4200000
        return dict(status='PASS_PIPELINED_REAL16_TWO_LAYER_ALL_OUTPUT_COMPARISON',tested_source='a'*40,
                    tokens=16,layers=2,commands=42,owner_jobs=38,checked_fp32=1409024,bit_differences=0,
                    baseline_512=m(146854495,512),baseline_4096_burst=m(82001446,4096),
                    pipeline_4096=m(40000001,4096),speedup_vs_512=146854495/40000001,
                    speedup_vs_4096_burst=82001446/40000001,per_command_durations=rows)
    def test_conservation(self):
        r=analyze(self.fixture());self.assertEqual(sum(x['pipeline_cycles'] for x in r['per_category'])+1,40000001)
        self.assertIsNone(r['active_matrix_utilization'])
        self.assertAlmostEqual(r['useful_utilization_ratio_vs_512'],r['speedup_vs_512']/8)
    def test_wrong_scope(self):
        for k,v in [('tokens',32),('layers',1),('commands',21),('checked_fp32',1),('bit_differences',1),('layers',True)]:
            with self.subTest(k=k):
                r=self.fixture();r[k]=v
                with self.assertRaises(ValueError):analyze(r)
    def test_unknown_status(self):
        r=self.fixture();r['status']='RUNNING'
        with self.assertRaises(ValueError):analyze(r)
    def test_inflated_metrics(self):
        for k,v in [('useful_wall_mac_utilization',0.99),('executed_wall_mac_utilization',float('nan')),('useful_gmac_per_s_at_target_clock',1e9),('matrix_macs_per_cycle',512)]:
            with self.subTest(k=k):
                r=self.fixture();r['pipeline_4096'][k]=v
                with self.assertRaises(ValueError):analyze(r)
    def test_missing_traffic(self):
        r=self.fixture();r['pipeline_4096']['ddr_read_bytes']=1
        with self.assertRaises(ValueError):analyze(r)
    def test_truncated_or_reordered_trace(self):
        for mode in (0,1,2):
            r=self.fixture()
            if mode==0:r['per_command_durations'].pop()
            elif mode==1:r['per_command_durations'][21]['pc']=20
            else:r['per_command_durations'][11]['opcode']='MATRIX_GEMM'
            with self.assertRaises(ValueError):analyze(r)
    def test_unaccounted_cycle(self):
        r=self.fixture();r['per_command_durations'][41]['pipeline_cycles']+=1
        with self.assertRaises(ValueError):analyze(r)
    def test_bad_cycle_types(self):
        for x in [True,-1,1.5,'1']:
            r=self.fixture();r['per_command_durations'][1]['pipeline_cycles']=x
            with self.assertRaises(ValueError):analyze(r)
    def test_inflated_speedup(self):
        r=self.fixture();r['speedup_vs_512']=100
        with self.assertRaises(ValueError):analyze(r)
    def test_fused_attention(self):
        r=analyze(self.fixture());a=[x for x in r['per_category'] if x['category']=='attention_fused'][0]
        self.assertEqual(a['pipeline_cycles'],600000)
    def test_bad_source(self):
        r=self.fixture();r['tested_source']='x'
        with self.assertRaises(ValueError):analyze(r)

if __name__=='__main__':unittest.main(verbosity=2)
