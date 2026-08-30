#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(path):return json.loads((ROOT/path).read_text())
control=load('config/control_plane.json');ledger=load('reports/execution/MASTER_LEDGER.json');next_action=load('reports/execution/NEXT_ACTION.json');final=load('reports/final_validation.json');v68=load('reports/execution/sandbox_v68_result.json');l52=load('reports/execution/l5_revision8b_b_local_result.json')
assert control['schema_version']==6 and control['plan_version']=='2026-08-31-v6.8'
assert control['current_subgate']=='L5.3_BLOCKED_ATTENTION_E1_E2'
assert control['remote_audit']['new_local_agent_commit_detected'] is False
assert control['remote_audit']['observed_head']=='e87eb9763ddec26ed67a92980e7487452519103b'
assert l52['status']=='PASS' and l52['h3']['wns_ns']>=0 and l52['h3']['max_transition']==0 and l52['h3']['max_cap']==0
assert ledger['current_state']==control['current_state']
assert next_action['L5.5_preflight']['review_floor_tps']==315
assert final['status']=='PASS_SANDBOX_V6_8_NO_NEW_LOCAL_PUSH_SOURCE_READY_EXTENSIONS'
assert v68['status']=='PASS'
assert v68['quant_operand_frontend']['status']=='PASS' and not v68['quant_operand_frontend']['contract']['format_specific_multiplier_array']
assert v68['state_commit_barrier']['status']=='PASS' and v68['state_commit_barrier']['counters']['protocol_errors']==0
assert v68['official_trace_schema']['status']=='PASS' and v68['official_trace_schema']['mutation_differences']>0
assert v68['ggml_node_adapter']['status']=='PASS' and v68['ggml_node_adapter']['unsupported_nodes']==['vision']
assert v68['L5_join_sensitivity']['baseline']['tokens_per_second']>300
assert v68['L5_join_sensitivity']['review_scenario']['result']['tokens_per_second']>315
for path in ('rtl/quant/ggml_operand_group_decode.sv','rtl/state/state_epoch_table.sv','rtl/state/state_stale_response_filter.sv','rtl/state/state_commit_barrier.sv','rtl/state/state_dirty_domain_tracker.sv','src/heteronpu/trace_schema.py','src/heteronpu/ggml_node_adapter.py','reports/SANDBOX_CONTINUATION_V6_8.md','reports/FINAL_TARGET_GAP_V6_8.md'):
 assert (ROOT/path).is_file(),path
result={'schema_version':6,'status':'PASS_V6_8','L5_2':'PASS_RETAINED','L5_3_L5_4':'OPEN','quant_frontend_E0':'PASS','state_commit_E0':'PASS','trace_schema_E0':'PASS','GGML_adapter_E0':'PASS','L5_join_sensitivity_E0':'PASS'}
(ROOT/'reports/progress_v6_validation.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps(result,indent=2,sort_keys=True))
