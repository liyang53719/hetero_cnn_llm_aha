#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(path): return json.loads((ROOT/path).read_text())
control=load('config/control_plane.json')
ledger=load(control['ledger'])
next_action=load('reports/execution/NEXT_ACTION.json')
final=load('reports/final_validation.json')
audit=load('reports/execution/REMOTE_AUDIT_11483E8.json')
acceptance=load('reports/execution/P3_BACKEND_ACCEPTANCE.json')
assert control['schema_version']==6 and control['plan_version']=='2026-09-02-v6.16'
assert control['branch_inventory']['remote_branches']==['main'] and not control['branch_inventory']['merge_required']
assert control['current_stage']=='L9' and control['current_subgate']=='L9.4_COMMAND128_DEVICE_TRANSPORT'
assert ledger['current_state']==control['current_state']
assert next_action['decision']=='BUILD_REAL_COMMAND128_TRANSPORT_CANARY_AND_CAPTURE_FULL_LOGITS_METRICS'
assert final['status']=='PASS_L5_6D_P3_LLAMA_BACKEND_FUNCTIONAL_NOT_HARDWARE_DEVICE'
assert audit['status']=='PASS_LLAMA_BACKEND_FUNCTIONAL_SOFTWARE_EMULATION'
assert audit['binding_semantics']['total_bindings']==338
assert audit['binding_semantics']['raw_storage_byte_parity']==281
assert audit['binding_semantics']['canonical_converted_parity']==57
assert audit['graph']['nodes_received']==958 and audit['graph']['manifest_commands']==588
assert audit['graph']['commands_executed_by_RTL_frontend']==0
assert audit['source_semantics']['host_cpu_buffer_type']
assert audit['source_semantics']['software_stage_backend']
assert audit['backpressure_scope']['scope']=='layer_completion_callback'
assert audit['output_scope']['full_logits_metrics_present'] is False
assert acceptance['not_closed']['Command128_RTL_execution']
assert 'L9.4_Command128_RTL_device_transport' in final['remaining_local_gates']
assert 'L5.6d.P3_real_llama_backend_equivalent' in ledger['closed_tasks']
assert 'L9.4_Command128_RTL_transport' in ledger['open_tasks']
result={'schema_version':6,'status':'PASS_V6_16_P3_BACKEND_FUNCTIONAL_BOUNDARY','branch_policy':'MAIN_ONLY','L5_6d_P3':'PASS_REAL_LLAMA_BACKEND_EQUIVALENT','hardware_device':'OPEN','Command128_RTL':'OPEN','full_logits_metrics':'OPEN','L10_physical':'OPEN'}
(ROOT/'reports/progress_v6_validation.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps(result,indent=2,sort_keys=True))
