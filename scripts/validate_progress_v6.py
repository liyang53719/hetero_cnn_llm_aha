#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(path):return json.loads((ROOT/path).read_text())
control=load('config/control_plane.json');ledger=load('reports/execution/MASTER_LEDGER.json');next_action=load('reports/execution/NEXT_ACTION.json');final=load('reports/final_validation.json');cross=load('reports/execution/l5_qwen2_four_layer_cross_replay_result.json');full=load('reports/execution/l5_qwen2_full_model_trace_result.json');v78=load('reports/execution/sandbox_v78_result.json');l10=load('reports/execution/l10_hierarchical_synthesis_result.json');sram=load('reports/execution/l10_sram_macro_result.json');checkpoints=load('reports/execution/qwen2_payload_checkpoint_result.json');groups=load('reports/execution/qwen2_payload_group_result.json')
assert control['schema_version']==6 and control['plan_version']=='2026-09-01-v6.15'
assert control['branch_inventory']['remote_branches']==['main'] and not control['branch_inventory']['merge_required']
assert control['current_stage']=='L10' and control['current_subgate']=='L10_EARLY_PPA'
assert control['current_state']=='L10_1_2_PASS_PAYLOAD_P1_PASS_P2_REAL_DATAPATH_OPEN_P3_OPEN'
assert ledger['current_state']==control['current_state']
assert next_action['decision']=='BUILD_OR_SELECT_REAL_PAYLOAD_DATAPATH_FOR_P2_P3'
assert final['status']=='L10_1_2_PASS_PAYLOAD_P1_PASS_P2_REAL_DATAPATH_OPEN_P3_OPEN'
assert cross['status']=='PASS' and cross['layers']==4 and cross['rtl']['bf16_bit_exact']==7840
assert full['status']=='PASS_CYCLE_E3' and full['layers']==28
assert any('not a 28-layer payload numerical simulation' in x for x in full['non_claims'])
assert 'L5.6_P2_real_payload_datapath' in final['remaining_local_gates']
assert 'L5.6d.P1' in ledger['closed_tasks'] and 'L5.6d.P2_REAL_PAYLOAD_DATAPATH' in ledger['open_tasks']
assert v78['status']=='PASS_SANDBOX_V7_8'
assert v78['l5_boundary']['subgates']['L5.6d_full_28_layer_payload_numerical_RTL']=='OPEN'
assert v78['l10_early_ppa']['minimum_margin']['margin_ps']<0.1
assert v78['qwen2_payload_closure']['checkpoint_count']==168
assert l10['status']=='PASS_L10_1_L10_2_EARLY_PPA' and l10['owner_hierarchy']['wns_ns']>=0 and l10['owner_hierarchy']['area_double_count']==0
assert sram['status']=='PASS_L10_2_EARLY_MACRO_DB' and sram['sram']['total_kib']==4096 and sram['sram']['physical_macros']==124
assert checkpoints['status']=='PASS_168_OFFICIAL_CHECKPOINTS' and checkpoints['checkpoint_count']==168
assert groups['status']=='PASS_P1_CHECKPOINTS_AND_P2_REFERENCE_CONTINUITY_RTL_CONTROL' and groups['open']['P2_real_payload_RTL_datapath']=='OPEN'
result={'schema_version':6,'status':'PASS_V6_15_L10_1_2_PAYLOAD_P1_P2_CONTROL','branch_policy':'MAIN_ONLY','L5_performance':'PASS','L5_reduced_cross_RTL':'PASS','L5_full_payload_RTL':'OPEN','L10':'L10_1_L10_2_PASS_POST_ROUTE_OPEN','payload_P1':'PASS_168','payload_P2':'REFERENCE_CONTINUITY_RTL_CONTROL_PASS_REAL_DATAPATH_OPEN'}
(ROOT/'reports/progress_v6_validation.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps(result,indent=2,sort_keys=True))
