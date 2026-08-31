#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(path):return json.loads((ROOT/path).read_text())
control=load('config/control_plane.json');ledger=load('reports/execution/MASTER_LEDGER.json');next_action=load('reports/execution/NEXT_ACTION.json');final=load('reports/final_validation.json');v69=load('reports/execution/sandbox_v69_result.json');l52=load('reports/execution/l5_revision8b_b_local_result.json');local=load('reports/execution/l5_3_l5_4_local_result.json')
assert control['schema_version']==6 and control['plan_version']=='2026-08-31-v6.9'
assert control['current_subgate']=='L5.3_BLOCKED_ATTENTION_E1_E2'
assert control['current_state']=='L5_3_CONTROLLER_E1_E4_PASS_L5_4_ONE_TWO_LANE_E1_E4_PASS_WAIT_NUMERIC_AND_SELECTION'
assert control['remote_audit']['user_reported_local_agent_commit']=='eba24625350d14fe3f9d760929736dcf5872fabd'
assert control['remote_audit']['observed_head_before_v69']=='c13b7469096f0100b8519bdc5d9a7288e38e7e15'
assert l52['status']=='PASS' and l52['h3']['wns_ns']>=0 and l52['h3']['max_transition']==0 and l52['h3']['max_cap']==0
assert ledger['current_state']==control['current_state'];assert next_action['L5.5_review']['review_floor_tps']==315
assert next_action['decision']=='INTEGRATE_REAL_QK_MLO_PV_AND_MEASURE_PRODUCER_STALL'
assert final['status']=='PASS_LOCAL_L5_3_CONTROLLER_E1_E4_L5_4_CANDIDATES_E1_E4_INTEGRATION_OPEN';assert v69['status']=='PASS';assert v69['attention_controller']['status']=='PASS';assert v69['attention_controller']['q1024']['merge_rows']==43008;assert v69['attention_controller']['q1024']['tasks']==12672;assert v69['silu_lut']['status']=='PASS' and v69['silu_lut']['relative_l2']<.001;assert v69['source_contract']['status']=='PASS'
assert local['status']=='SOURCE_LOCAL_GATES_PASS_INTEGRATION_OPEN'
assert all(local['checks'][key] for key in ('controller_e1','controller_dc','silu_1lane_e1','silu_2lane_e1','silu_1lane_dc','silu_2lane_dc'))
assert not local['checks']['full_attention_numerical_e2'] and not local['checks']['silu_lane_selection']
for path in ('rtl/attention/blocked_attention_stream_controller.sv','tb/tb_blocked_attention_stream_controller.sv','scripts/run_l5_blocked_attention_controller_e1.sh','scripts/run_l5_blocked_attention_controller_dc.sh','rtl/sfu/bf16_silu_lut_128.svh','rtl/sfu/bf16_silu_mul_lut_lane.sv','rtl/sfu/bf16_silu_mul_lut_array.sv','rtl/sfu/bf16_silu_mul_lut_tops.sv','tb/tb_bf16_silu_mul_lut_array.sv','scripts/run_l5_silu_lut_e1.sh','scripts/run_l5_silu_lut_dc.sh','reports/SANDBOX_CONTINUATION_V6_9.md','reports/FINAL_TARGET_GAP_V6_9.md'):assert (ROOT/path).is_file(),path
result={'schema_version':6,'status':'PASS_V6_9_LOCAL_GATES','L5_2':'PASS_RETAINED','L5_3_controller_E1_E4':'PASS','L5_3_full_stream':'OPEN','L5_4_one_two_lane_E1_E4':'PASS','L5_4_selection':'OPEN','L5_5':'WAIT_JOIN'}
(ROOT/'reports/progress_v6_validation.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps(result,indent=2,sort_keys=True))
