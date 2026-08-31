#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(p):return json.loads((ROOT/p).read_text())
def sha(p):return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
logp=ROOT/'work/results/l5_qwen2_full_model_trace/tb.log';body=logp.read_text()
m=re.search(r'L5_QWEN2_FULL_MODEL_TRACE_PASS records=(\d+) blocks=(\d+) final_rmsnorm=(\d+) last_token_lm_head=(\d+) total_cycles=(\d+) total_macs=(\d+) ddr_read_bytes=(\d+) ddr_write_bytes=(\d+) tokens_per_second_milli=(\d+)',body)
if not m:raise SystemExit('missing full-model trace PASS')
records,blocks,norms,heads,cycles,macs,reads,writes,tps_milli=map(int,m.groups())
budget=load('config/qwen2_1p5b_300tps_budget.json');shape=load('config/qwen2_1p5b_target_shape.json');e3=load('reports/execution/l5_5_q1024_e3_result.json');rms=load('reports/execution/l5_rmsnorm1536_result.json');matrix=load('reports/execution/l5_revision8b_b_local_result.json');integrity=load('reports/execution/local_upstream_integrity.json')
tps=1024*1_000_000_000/cycles;duration=cycles/1_000_000_000
checks={
 'frozen_revision':shape['revision']==budget['revision']=='ba1cf1846d7df0a0591d6c00649f57e798519da8',
 'all_28_blocks':records==30 and blocks==28,
 'final_rmsnorm_record':norms==1 and rms['status']=='PASS' and rms['max_absolute_error']<=rms['threshold'],
 'last_token_lm_head_record':heads==1 and budget['workload']['lm_head_tokens']==1,
 'mac_accounting':macs==budget['compute']['useful_macs_total'],
 'cycle_gate':cycles<=budget['hard_gate']['integrated_cycles_max'] and tps>=budget['hard_gate']['tokens_per_second_min'],
 'sram_gate':4194304<=budget['memory_gates']['sram_bytes_max'],
 'ddr_read_gate':reads/duration<=budget['memory_gates']['ddr_read_bytes_per_second_max'],
 'ddr_write_gate':writes/duration<=budget['memory_gates']['ddr_write_bytes_per_second_max'],
 'l5_5_e3':e3['status']=='PASS' and e3['curve']['score_ddr_bytes']==0 and e3['curve']['probability_ddr_bytes']==0,
 'matrix_h3':matrix['status']=='PASS' and matrix['h3']['wns_ns']>=0 and matrix['h3']['unmapped']==0 and matrix['h3']['unresolved']==0,
 'upstream_integrity':integrity['status']=='PASS' and integrity['upstream_source_edits']==0,
}
if not all(checks.values()):raise SystemExit(f'full-model trace checks failed:{checks}')
result={
 'schema_version':1,'stage':'L5','subgate':'L5.6_Q1024_FULL_MODEL',
 'status':'PASS_CYCLE_E3_L5_6_NUMERICAL_OPEN','evidence_class':'RTL_count_trace_E3_plus_component_E2_E4_not_28_layer_payload',
 'model':shape['model'],'revision':shape['revision'],'batch':1,'sequence':1024,'layers':28,
 'trace':{'records':records,'block_records':blocks,'final_rmsnorm_records':norms,'last_token_lm_head_records':heads,'total_cycles':cycles,'total_macs':macs,'ddr_read_bytes':reads,'ddr_write_bytes':writes,'tokens_per_second':tps,'wall_mac_utilization':budget['compute']['ideal_cycles']/cycles,'average_ddr_read_GBps':reads/duration/1e9,'average_ddr_write_GBps':writes/duration/1e9,'score_ddr_bytes':0,'probability_ddr_bytes':0},
 'physical':{'revision':matrix['revision'],'clock_ns':matrix['architecture']['clock_period_ns'],'wns_ns':matrix['h3']['wns_ns'],'unmapped':matrix['h3']['unmapped'],'unresolved':matrix['h3']['unresolved'],'sram_bytes':4194304},
 'checks':checks,
 'numerical_boundary':{'one_block_components':'PASS_EXISTING','final_rmsnorm':'PASS_E1_1000_VECTORS','four_layer_executable_subset':'OPEN','last_token_lm_head_official_weight_payload':'OPEN','full_28_layer_payload':'NOT_REQUIRED_BY_TRACE_MODE'},
 'non_claims':['not a 28-layer payload numerical simulation','LM-head cycle count is conservative serialized DDR-read plus Matrix plus logits-write service','not post-route/PVT/SAIF signoff'],
 'provenance':{'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'trace_log_sha256':hashlib.sha256(logp.read_bytes()).hexdigest(),'rtl_sha256':sha('rtl/control/l5_qwen2_full_model_trace_controller.sv'),'testbench_sha256':sha('tb/tb_l5_qwen2_full_model_trace_controller.sv'),'budget_sha256':sha('config/qwen2_1p5b_300tps_budget.json'),'shape_sha256':sha('config/qwen2_1p5b_target_shape.json'),'l5_5_e3_sha256':sha('reports/execution/l5_5_q1024_e3_result.json')},
 'next_action':'Run the frozen Qwen2 four-layer executable numerical subset and official-weight last-token LM-head payload before closing L5.6.'
}
out=ROOT/'reports/execution/l5_qwen2_full_model_trace_result.json';out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps({'status':result['status'],'cycles':cycles,'tokens_per_second':tps,'next_action':result['next_action']},sort_keys=True))
