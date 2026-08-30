from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from heteronpu.silu_dse import DirectSiluLut,evaluate_candidate,silu_dse_report,throughput_dse

def test_boundaries():
 l=DirectSiluLut(128);assert l.evaluate(-20)==0 and l.evaluate(20)==20

def test_accuracy():
 r=evaluate_candidate(128,random_cases=5000,seed=2);assert r['fused']['relative_l2']<=.001 and r['fused']['mean_abs']<=.001

def test_throughput():
 r=throughput_dse();assert r['producer_pairs_per_cycle']<1 and r['lanes'][0]['drains_before_next_tile']

def test_report():assert silu_dse_report()['selected_source_candidate']['entries']==128
