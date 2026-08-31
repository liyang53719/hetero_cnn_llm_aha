from pathlib import Path
import re
from heteronpu.attention_e2_vectors import attention_e2_pack_report,controller_task_count,summary_merge_rows
from heteronpu.silu_edge_and_stall import combined_report,simulate_stall,StallScenario
from heteronpu.quant_tail_scheduler import schedule_tail,validate_schedule,tail_report
from heteronpu.state_adversarial_vectors import adversarial_report
from heteronpu.e3_minimum_matrix import minimum_e3_matrix

def test_attention_e2_pack():
 r=attention_e2_pack_report();assert r['status']=='PASS';assert r['cases']['128']['rows_compared']==1536;assert r['cases']['1024']['summary_merge_rows']==43008;assert r['cases']['1024']['controller_tasks']==12672;assert r['max_abs']<2e-5;assert r['max_relative_l2']<2e-5;assert attention_e2_pack_report()['aggregate_sha256']==r['aggregate_sha256']
def test_attention_geometry():
 assert controller_task_count(128)==240 and controller_task_count(384)==1872 and controller_task_count(1024)==12672;assert summary_merge_rows(128)==0 and summary_merge_rows(384)==4608 and summary_merge_rows(1024)==43008
def test_silu_edge_and_stall():
 r=combined_report();assert r['status']=='PASS';assert r['special_vectors']['vectors']==625;assert r['special_vectors']['nan_checked_by_class_not_payload'];assert r['special_vectors']['edge_policy_status']=='REQUIRES_LOCAL_RTL_DECISION';assert r['stall_envelope']['scenarios']==160;assert any(x['result']['producer_stall_fraction']>.02 for x in r['stall_envelope']['results']);assert simulate_stall(StallScenario(1,8,1)).producer_stall_fraction==0
def test_quant_tail_schedule():
 for fmt in ('FP16','Q8_0','Q6_K','Q3_K'):
  for k in (0,1,15,16,17,31,32,33,255,256,257,1023,1024,1025):validate_schedule(k,fmt)
  beats=schedule_tail(257,fmt);assert sum(b.valid_count for b in beats)==257 and beats[-1].valid_count==1 and beats[-1].last
 r=tail_report(128,dot_cases_per_format=64);assert r['status']=='PASS' and not r['hardware_contract']['format_specific_multiplier_array']
def test_quant_tail_rtl_source():
 source=Path('rtl/quant/ggml_quant_k_tail_sequencer.sv').read_text();assert 'module ggml_quant_k_tail_sequencer' in source and "block_beats=5'd16" in source and 'valid_count_o' in source;stripped=re.sub(r'//.*','',source);assert len(re.findall(r'\bmodule\s+[A-Za-z_]',stripped))==len(re.findall(r'\bendmodule\b',stripped))
def test_state_adversarial():
 r=adversarial_report(1000);assert r['status']=='PASS' and r['page_leak']==0;assert r['counters']['pages_allocated']==r['counters']['pages_freed'];assert r['counters']['timeout_abort']>0 and r['counters']['oom_abort']>0 and r['counters']['stale_ack']>0;assert adversarial_report(1000)['sha256']==r['sha256']
def test_e3_minimum_matrix():
 r=minimum_e3_matrix();assert r['status']=='PASS' and r['case_count']<=20;labels={c['label'] for c in r['cases']};assert {'baseline','review_scenario','closest_pass_300','closest_fail_300'}<=labels;assert any(not c['projection']['passes_300tps'] for c in r['cases']);assert r['acceptance']['pre_route_review_floor_tps']==315 and r['acceptance']['score_DDR_bytes']==0
