#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(path):return json.loads((ROOT/path).read_text())
control=load('config/control_plane.json');ledger=load('reports/execution/MASTER_LEDGER.json');next_action=load('reports/execution/NEXT_ACTION.json');final=load('reports/final_validation.json');v69=load('reports/execution/sandbox_v69_result.json');l52=load('reports/execution/l5_revision8b_b_local_result.json')
assert control['schema_version']==6 and control['plan_version']=='2026-08-31-v6.9'
assert control['current_subgate']=='L5.3_BLOCKED_ATTENTION_E1_E2'
assert control['remote_audit']['user_reported_local_agent_commit']=='eba24625350d14fe3f9d760929736dcf5872fabd'
assert control['remote_audit']['observed_head_before_v69']=='c13b7469096f0100b8519bdc5d9a7288e38e7e15'
assert l52['status']=='PASS' and l52['h3']['wns_ns']>=0 and l52['h3']['max_transition']==0 and l52['h3']['max_cap']==0
assert ledger['current_state']==control['current_state'];assert next_action['L5.5_review']['review_floor_tps']==315
assert final['status']=='PASS_SANDBOX_V6_9_L5_3_CONTROLLER_L5_4_DATAPATH_SOURCE_READY';assert v69['status']=='PASS';assert v69['attention_controller']['status']=='PASS';assert v69['attention_controller']['q1024']['merge_rows']==43008;assert v69['attention_controller']['q1024']['tasks']==12672;assert v69['silu_lut']['status']=='PASS' and v69['silu_lut']['relative_l2']<.001;assert v69['source_contract']['status']=='PASS'
for path in ('rtl/attention/blocked_attention_stream_controller.sv','tb/tb_blocked_attention_stream_controller.sv','scripts/run_l5_blocked_attention_controller_e1.sh','scripts/run_l5_blocked_attention_controller_dc.sh','rtl/sfu/bf16_silu_lut_128.svh','rtl/sfu/bf16_silu_mul_lut_lane.sv','rtl/sfu/bf16_silu_mul_lut_array.sv','rtl/sfu/bf16_silu_mul_lut_tops.sv','tb/tb_bf16_silu_mul_lut_array.sv','scripts/run_l5_silu_lut_e1.sh','scripts/run_l5_silu_lut_dc.sh','reports/SANDBOX_CONTINUATION_V6_9.md','reports/FINAL_TARGET_GAP_V6_9.md'):assert (ROOT/path).is_file(),path
result={'schema_version':6,'status':'PASS_V6_9','L5_2':'PASS_RETAINED','L5_3_controller_E0_source':'PASS','L5_3_full_stream':'OPEN','L5_4_bit_contract_source':'PASS','L5_4_E1_E4':'OPEN','L5_5':'WAIT_JOIN'}
(ROOT/'reports/progress_v6_validation.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps(result,indent=2,sort_keys=True))
