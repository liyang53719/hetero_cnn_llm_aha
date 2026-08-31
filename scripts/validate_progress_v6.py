#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(path):return json.loads((ROOT/path).read_text())
control=load('config/control_plane.json');policy=load('config/git_workflow_policy.json');ledger=load('reports/execution/MASTER_LEDGER.json');next_action=load('reports/execution/NEXT_ACTION.json');final=load('reports/final_validation.json');local=load('reports/execution/l5_3_l5_4_local_result.json');attempt=load('reports/execution/l5_q128_single_sim_attempt_result.json');q384=load('reports/execution/l5_q384_sampled_e2_result.json');q1024=load('reports/execution/l5_q1024_reviewed_e2_result.json');stress=load('reports/execution/l5_attention_stress_service_result.json');selection=load('reports/execution/l5_silu_lane_selection_result.json');precheck=load('reports/execution/l5_5_measured_precheck_result.json');candidate=load('reports/execution/l5_5_pipelined_sfu_candidate_result.json');balanced=load('reports/execution/l5_5_balanced_8x8_local_result.json');e3=load('reports/execution/l5_5_q1024_e3_result.json');full=load('reports/execution/l5_qwen2_full_model_trace_result.json');subset=load('reports/execution/l5_qwen2_numerical_subset_result.json');cross=load('reports/execution/l5_qwen2_four_layer_cross_replay_result.json');bridge=load('reports/execution/l5_attention_trace_bridge_result.json');probability=load('reports/execution/l5_probability_hilo_result.json');v69=load('reports/execution/sandbox_v69_result.json');l52=load('reports/execution/l5_revision8b_b_local_result.json')
assert control['schema_version']==6 and control['plan_version']=='2026-09-01-v6.13'
assert control['branch_inventory']['remote_branches']==['main'] and not control['branch_inventory']['merge_required']
assert policy['status']=='ENFORCED_MAIN_ONLY' and policy['rules']['allowed_remote_branches']==['main']
assert control['current_stage']=='L10' and control['current_subgate']=='L10_EARLY_PPA'
assert control['current_state']=='L5_6_REDUCED_CROSS_RTL_PASS_READY_L10_EARLY_PPA'
assert l52['status']=='PASS' and l52['h3']['wns_ns']>=0
assert local['status']=='L5_3_L5_4_PASS_L5_5_OPEN'
assert all(local['checks'][key] for key in ('controller_e1','controller_dc','attention_trace_bridge','block32_weight_e1','block32_weight_dc','silu_1lane_e1','silu_1lane_dc','silu_2lane_e1','silu_2lane_dc'))
assert local['checks']['full_attention_numerical_e2'] and local['checks']['silu_lane_selection']
assert bridge['status']=='PASS_TRACE_COUPLED_BRIDGE' and bridge['cases']['1024']['merge_rows']==43008
assert probability['status']=='PASS' and not probability['single_bf16_pass'] and probability['hilo_pass'] and probability['bf16_hi_plus_residual']['max_abs']<=0.002
assert ledger['current_state']==control['current_state']
assert next_action['decision']=='RUN_L10_EARLY_PPA'
assert next_action['sandbox_preflight']['predicted_stress_tps']>=315
assert next_action['component_targets']['tile16_stress_cycles_max_for_320_with_merge323']==336
assert final['status']=='L5_6_REDUCED_CROSS_RTL_PASS_READY_L10_EARLY_PPA'
assert attempt['status']=='PASS_Q128_SINGLE_PROCESS_E2' and attempt['observed_progress']['rows']==1536
assert q384['status']=='PASS_Q384_SAMPLED_E2' and q384['actual_compared_rows']>=180 and q384['controller_merge_rows']==4608
assert q1024['status']=='PASS_Q1024_REVIEWED_E2' and q1024['actual_compared_rows']>=108 and q1024['controller_merge_rows']==43008
assert stress['status']=='PASS' and stress['controller_stress']['transactions_qk_sfu_pv']>=100000 and stress['controller_stress']['loss']==0
assert selection['status']=='PASS' and selection['selected_lanes']==1 and selection['candidates']['one']['producer_stall_fraction']<=0.02
assert precheck['status']=='FAIL_REOPEN_ARCHITECTURE' and precheck['imported']['calibration']['tokens_per_second']<315
assert candidate['status']=='PASS_COMPONENTS_FAIL_STRESS_REOPEN' and candidate['q1024_projection']['nominal_tokens_per_second']>=315 and candidate['q1024_projection']['stress_tokens_per_second']<315
assert balanced['status']=='PASS_E1_E4_READY_E3' and balanced['q1024_projection']['stress_tokens_per_second']>=320 and balanced['score_ddr_bytes']==0 and balanced['probability_ddr_bytes']==0
assert e3['status']=='PASS' and e3['evidence_class']=='composed_real_RTL_E3'
assert e3['imported']['status']=='PASS_REVIEW' and e3['imported']['calibration']['tokens_per_second']>=315
assert e3['curve']['score_ddr_bytes']==0 and e3['curve']['probability_ddr_bytes']==0
assert full['status']=='PASS_CYCLE_E3' and full['trace']['tokens_per_second']>=300 and full['trace']['total_cycles']==3192103543
assert full['trace']['block_records']==28 and full['trace']['final_rmsnorm_records']==1 and full['trace']['last_token_lm_head_records']==1
assert subset['status']=='PASS_REDUCED_FOUR_LAYER_CROSS_RTL'
assert subset['checks']['exact_revision'] and subset['checks']['bf16_boundary_threshold'] and subset['checks']['argmax_preserved']
assert cross['status']=='PASS' and cross['rtl']['bf16_bit_exact']==7840 and cross['refined_rsqrt']['dc_wns_ns']>=0
assert not attempt['source_policy']['generated_rtl_modified'] and not attempt['source_policy']['production_rtl_modified']
assert v69['status']=='PASS'
for path in ('config/git_workflow_policy.json','scripts/check_main_only_workflow.sh','rtl/attention/blocked_attention_stream_controller.sv','rtl/attention/fp32_block32_softmax_weights.sv','scripts/run_l5_blocked_attention_controller_e1.sh','scripts/run_l5_blocked_attention_controller_dc.sh','scripts/run_l5_block32_softmax_weight_e1.sh','scripts/run_l5_block32_softmax_weight_dc.sh','rtl/sfu/bf16_silu_mul_lut_lane.sv','scripts/run_l5_silu_lut_e1.sh','scripts/run_l5_silu_lut_dc.sh','reports/CURRENT_WORK_BREAKDOWN_MAIN_ONLY.md'):
 assert (ROOT/path).is_file(),path
result={'schema_version':6,'status':'PASS_V6_13_L5_6_REDUCED_CROSS_RTL','branch_policy':'MAIN_ONLY','L5_2':'PASS','L5_3_full_E2':'PASS','L5_4_selection':'PASS_ONE_LANE','L5_5':'PASS_E3_321_869TPS','L5_6':'PASS_REDUCED_CROSS_RTL_320_792TPS','next':'L10_EARLY_PPA'}
(ROOT/'reports/progress_v6_validation.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps(result,indent=2,sort_keys=True))
