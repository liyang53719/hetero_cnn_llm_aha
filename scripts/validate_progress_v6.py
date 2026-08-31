#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(path):return json.loads((ROOT/path).read_text())
control=load('config/control_plane.json');policy=load('config/git_workflow_policy.json');ledger=load('reports/execution/MASTER_LEDGER.json');next_action=load('reports/execution/NEXT_ACTION.json');final=load('reports/final_validation.json');local=load('reports/execution/l5_3_l5_4_local_result.json');v69=load('reports/execution/sandbox_v69_result.json');l52=load('reports/execution/l5_revision8b_b_local_result.json')
assert control['schema_version']==6 and control['plan_version']=='2026-08-31-v6.10'
assert control['branch_inventory']['remote_branches']==['main'] and not control['branch_inventory']['merge_required']
assert policy['status']=='ENFORCED_MAIN_ONLY' and policy['rules']['allowed_remote_branches']==['main'] and not policy['rules']['force_push']
assert l52['status']=='PASS' and l52['h3']['wns_ns']>=0
assert local['checks']['controller_e1'] and local['checks']['controller_dc']
assert local['checks']['silu_1lane_e1'] and local['checks']['silu_1lane_dc']
assert local['checks']['silu_2lane_e1'] and local['checks']['silu_2lane_dc']
assert not local['checks']['full_attention_numerical_e2'] and not local['checks']['silu_lane_selection']
assert ledger['current_state']==control['current_state'];assert next_action['L5.5_review']['review_floor_tps']==315
assert final['status']=='PASS_V6_10_MAIN_ONLY_LOCAL_CANDIDATE_GATES_ACCEPTED';assert v69['status']=='PASS'
for path in ('reports/BRANCH_CONSOLIDATION_MAIN_ONLY.md','reports/CURRENT_WORK_BREAKDOWN_MAIN_ONLY.md','scripts/check_main_only_workflow.sh','rtl/attention/blocked_attention_stream_controller.sv','rtl/sfu/bf16_silu_mul_lut_lane.sv'):assert (ROOT/path).is_file(),path
result={'schema_version':6,'status':'PASS_V6_10_MAIN_ONLY','remote_branches':['main'],'L5_2':'PASS','L5_3_controller':'PASS_E1_E4','L5_3_full':'OPEN','L5_4_candidates':'PASS_E1_E4','L5_4_selection':'OPEN','L5_5':'WAIT_JOIN'}
(ROOT/'reports/progress_v6_validation.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps(result,indent=2,sort_keys=True))
