#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(path):return json.loads((ROOT/path).read_text())
control=load('config/control_plane.json');policy=load('config/git_workflow_policy.json');ledger=load('reports/execution/MASTER_LEDGER.json');next_action=load('reports/execution/NEXT_ACTION.json');final=load('reports/final_validation.json');local=load('reports/execution/l5_3_l5_4_local_result.json');bridge=load('reports/execution/l5_attention_trace_bridge_result.json');probability=load('reports/execution/l5_probability_hilo_result.json');v69=load('reports/execution/sandbox_v69_result.json');l52=load('reports/execution/l5_revision8b_b_local_result.json')
assert control['schema_version']==6 and control['plan_version']=='2026-08-31-v6.10'
assert control['branch_inventory']['remote_branches']==['main'] and not control['branch_inventory']['merge_required']
assert policy['status']=='ENFORCED_MAIN_ONLY' and policy['rules']['allowed_remote_branches']==['main']
assert control['current_subgate']=='L5.3_BLOCKED_ATTENTION_NUMERICAL_E2'
assert control['current_state']=='MAIN_ONLY_TRACE_BRIDGE_BLOCK32_WEIGHT_AND_VECTOR_PACK_PASS_WAIT_SINGLE_SIM'
assert l52['status']=='PASS' and l52['h3']['wns_ns']>=0
assert local['status']=='BRIDGE_AND_COMPONENT_GATES_PASS_SINGLE_SIM_OPEN'
assert all(local['checks'][key] for key in ('controller_e1','controller_dc','attention_trace_bridge','block32_weight_e1','block32_weight_dc','silu_1lane_e1','silu_1lane_dc','silu_2lane_e1','silu_2lane_dc'))
assert not local['checks']['full_attention_numerical_e2'] and not local['checks']['silu_lane_selection']
assert bridge['status']=='PASS_TRACE_COUPLED_BRIDGE' and bridge['cases']['1024']['merge_rows']==43008
assert probability['status']=='PASS' and not probability['single_bf16_pass'] and probability['hilo_pass'] and probability['bf16_hi_plus_residual']['max_abs']<=0.002
assert ledger['current_state']==control['current_state']
assert next_action['decision']=='BUILD_SINGLE_SIM_Q128_CONTROLLER_MATRIX_WEIGHT_PV_MERGE'
assert next_action['L5.5_review']['review_floor_tps']==315
assert final['status']=='PASS_V6_10_MAIN_ONLY_TRACE_BRIDGE_BLOCK32_WEIGHT_SINGLE_SIM_OPEN'
assert v69['status']=='PASS'
for path in ('config/git_workflow_policy.json','scripts/check_main_only_workflow.sh','rtl/attention/blocked_attention_stream_controller.sv','rtl/attention/fp32_block32_softmax_weights.sv','scripts/run_l5_blocked_attention_controller_e1.sh','scripts/run_l5_blocked_attention_controller_dc.sh','scripts/run_l5_block32_softmax_weight_e1.sh','scripts/run_l5_block32_softmax_weight_dc.sh','rtl/sfu/bf16_silu_mul_lut_lane.sv','scripts/run_l5_silu_lut_e1.sh','scripts/run_l5_silu_lut_dc.sh','reports/CURRENT_WORK_BREAKDOWN_MAIN_ONLY.md'):
 assert (ROOT/path).is_file(),path
result={'schema_version':6,'status':'PASS_V6_10_LOCAL_BRIDGE','branch_policy':'MAIN_ONLY','L5_2':'PASS','L5_3_controller':'PASS_E1_E4','L5_3_trace_bridge':'PASS_NOT_SINGLE_SIM','L5_3_block32_weight':'PASS_E1_E4','L5_3_full_E2':'OPEN','L5_4_candidates':'PASS_E1_E4','L5_4_selection':'OPEN','L5_5':'WAIT_JOIN'}
(ROOT/'reports/progress_v6_validation.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps(result,indent=2,sort_keys=True))
