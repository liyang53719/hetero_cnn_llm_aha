#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(path): return json.loads((ROOT/path).read_text())
control=load('config/control_plane.json'); policy=load('config/git_workflow_policy.json'); ledger=load('reports/execution/MASTER_LEDGER.json'); next_action=load('reports/execution/NEXT_ACTION.json'); final=load('reports/final_validation.json'); v69=load('reports/execution/sandbox_v69_result.json'); l52=load('reports/execution/l5_revision8b_b_local_result.json')
assert control['schema_version']==6 and control['plan_version']=='2026-08-31-v6.10'
assert control['git_workflow_policy']=='config/git_workflow_policy.json'
assert control['branch_inventory']['remote_branches']==['main'] and control['branch_inventory']['merge_required'] is False
assert control['current_subgate']=='L5.3_BLOCKED_ATTENTION_E1_E2'
assert policy['status']=='ENFORCED_MAIN_ONLY' and policy['rules']['allowed_remote_branches']==['main']
assert policy['rules']['branch_creation']=='FORBIDDEN_WITHOUT_EXPLICIT_USER_APPROVAL'
assert policy['rules']['force_push'] is False
assert l52['status']=='PASS' and l52['h3']['wns_ns']>=0 and l52['h3']['max_transition']==0 and l52['h3']['max_cap']==0
assert ledger['current_state']==control['current_state'] and ledger['git_workflow']['status']=='ENFORCED_MAIN_ONLY'
assert next_action['git_workflow']['policy']=='config/git_workflow_policy.json'
assert next_action['L5.5_review']['review_floor_tps']==315
assert final['status']=='PASS_SANDBOX_V6_10_MAIN_ONLY_CONSOLIDATED'
assert v69['status']=='PASS'; assert v69['attention_controller']['q1024']['merge_rows']==43008; assert v69['silu_lut']['relative_l2']<.001
for path in ('reports/BRANCH_CONSOLIDATION_MAIN_ONLY.md','reports/CURRENT_WORK_BREAKDOWN_MAIN_ONLY.md','scripts/check_main_only_workflow.sh','rtl/attention/blocked_attention_stream_controller.sv','rtl/sfu/bf16_silu_mul_lut_lane.sv'):
 assert (ROOT/path).is_file(),path
result={'schema_version':6,'status':'PASS_V6_10_MAIN_ONLY','remote_branches':['main'],'merge_required':False,'L5_2':'PASS_RETAINED','L5_3_L5_4':'OPEN_SOURCE_READY','main_only_policy':'PASS'}
(ROOT/'reports/progress_v6_validation.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n'); print(json.dumps(result,indent=2,sort_keys=True))
