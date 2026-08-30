#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(path): return json.loads((ROOT/path).read_text())
control=load('config/control_plane.json');ledger=load('reports/execution/MASTER_LEDGER.json');next_action=load('reports/execution/NEXT_ACTION.json');final=load('reports/final_validation.json')
local=load('reports/execution/l5_revision8b_b_local_result.json');attn=load('reports/execution/l5_blocked_attention_numeric_e0_result.json');stream=load('reports/execution/l5_blocked_attention_stream_e0_result.json');silu=load('reports/execution/l5_silu_dse_e0_result.json');seq=load('reports/execution/sequence_memory_concurrency_e0_result.json');pol=load('reports/execution/qwen38_policy_lowering_e0_result.json')
assert control['plan_version']=='2026-08-30-v6.6'
assert control['current_state']=='L5_2_CLOSED_L5_3_L5_4_SOURCE_READY_WAIT_LOCAL_E1_E4'
assert control['remote_audit']['observed_head']=='eba24625350d14fe3f9d760929736dcf5872fabd'
assert local['status']=='PASS' and all(local['checks'].values())
assert local['architecture']['contexts']==5 and local['architecture']['fma_stages']==5 and local['architecture']['lanes']==512
assert local['h3']['wns_ns']>=0 and local['h3']['max_transition']==0 and local['h3']['max_cap']==0 and local['h3']['unmapped']==0 and local['h3']['unresolved']==0
assert ledger['accepted_local_evidence']['L5.2']['contexts']==5
assert next_action['completed']['L5.2'].startswith('PASS')
assert attn['status']=='PASS' and attn['analytic_q1024_summary_merges']==43008 and attn['maximum_error']['max_abs']<=2e-4
assert stream['status']=='PASS' and stream['frozen_invariants']['q1024_summary_merges']==43008
assert stream['frozen_invariants']['accepted_matrix_revision']=='Revision8B-B' and stream['frozen_invariants']['matrix_pipeline_stages']==5 and stream['cases']['384']['selected']['cycles']==479238
assert silu['status']=='PASS' and silu['selected_source_candidate']['entries']==128
assert seq['status']=='PASS' and seq['frozen_contract']['recommended_first_RTL_MSHR_entries']==8
assert pol['status']=='PASS' and pol['model_layers']==48 and pol['segments']==48
assert final['status'].startswith('PASS_SANDBOX_V6_6')
result={'schema_version':6,'status':'PASS_V6_6','L5.2':'PASS_COMPONENT_H3_L10_RISK_OPEN','L5.3':'NUMERICAL_CYCLE_STREAM_E0_PASS','L5.4':'DSE_PASS','L7':'CONCURRENCY_E0_PASS','L8_L9':'POLICY_LOWERING_E0_PASS'}
(ROOT/'reports/progress_v6_validation.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps(result,indent=2,sort_keys=True))
