#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(path):return json.loads((ROOT/path).read_text())
control=load('config/control_plane.json');ledger=load('reports/execution/MASTER_LEDGER.json');next_action=load('reports/execution/NEXT_ACTION.json');final=load('reports/final_validation.json');cross=load('reports/execution/l5_qwen2_four_layer_cross_replay_result.json');full=load('reports/execution/l5_qwen2_full_model_trace_result.json');v78=load('reports/execution/sandbox_v78_result.json')
assert control['schema_version']==6 and control['plan_version']=='2026-09-01-v6.14'
assert control['branch_inventory']['remote_branches']==['main'] and not control['branch_inventory']['merge_required']
assert control['current_stage']=='L10' and control['current_subgate']=='L10_EARLY_PPA'
assert control['current_state']=='L10_EARLY_PPA_IN_PARALLEL_WITH_L5_6_FULL_PAYLOAD_OPEN'
assert ledger['current_state']==control['current_state']
assert next_action['decision']=='RUN_BOUNDED_L10_EARLY_PPA_AND_PAYLOAD_GROUP_REPLAY'
assert final['status']=='L10_EARLY_PPA_READY_L5_6_FULL_PAYLOAD_OPEN'
assert cross['status']=='PASS' and cross['layers']==4 and cross['rtl']['bf16_bit_exact']==7840
assert full['status']=='PASS_CYCLE_E3' and full['layers']==28
assert any('not a 28-layer payload numerical simulation' in x for x in full['non_claims'])
assert 'L5.6_full_payload_RTL' in final['remaining_local_gates']
assert 'L5.6d' not in ledger['closed_tasks'] and 'L5.6d' in ledger['open_tasks']
assert v78['status']=='PASS_SANDBOX_V7_8'
assert v78['l5_boundary']['subgates']['L5.6d_full_28_layer_payload_numerical_RTL']=='OPEN'
assert v78['l10_early_ppa']['minimum_margin']['margin_ps']<0.1
assert v78['qwen2_payload_closure']['checkpoint_count']==168
result={'schema_version':6,'status':'PASS_V6_14_L10_EARLY_PPA_FULL_PAYLOAD_OPEN','branch_policy':'MAIN_ONLY','L5_performance':'PASS','L5_reduced_cross_RTL':'PASS','L5_full_payload_RTL':'OPEN','L10':'EARLY_PPA_IN_PROGRESS'}
(ROOT/'reports/progress_v6_validation.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps(result,indent=2,sort_keys=True))
