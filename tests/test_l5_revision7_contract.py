from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from heteronpu.revision7_contract import approval_report,recurrence_stress,validate_tcl

def test_revision7_source_and_tcl_contract():
 r=approval_report(ROOT,ROOT/'config/l5_revision7_policy.json',ROOT/'dc/synth_l5_bf16_context_lane_rev7.tcl',operations=20000);assert r['status']=='PASS',r;assert r['decision']=='APPROVE_WITH_GATES';assert r['source_contract']['contract']['contexts']==4

def test_four_contexts_hide_four_cycle_recurrence():
 r=recurrence_stress(operations=50000,contexts=4,latency=4,stall_probability=0.0);assert r['status']=='PASS';assert r['cycles']==50004;assert r['same_cycle_bypasses']>49000;assert r['no_stall_ideal_issue_per_cycle']==1.0

def test_three_contexts_do_not_hide_four_cycles():
 r=recurrence_stress(operations=100,contexts=3,latency=4,stall_probability=0.0);assert r['no_stall_ideal_issue_per_cycle']==0.75

def test_revision7_tcl_has_no_timing_exception_or_leaf_ddc():
 r=validate_tcl(ROOT/'dc/synth_l5_bf16_context_lane_rev7.tcl');assert r['status']=='PASS',r;assert r['false_paths']==['set_false_path -from [get_ports rst_ni]']
