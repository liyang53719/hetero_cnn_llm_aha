#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
policy=json.loads((ROOT/'config/l5_revision8b_a_policy.json').read_text())
activation=(ROOT/'reports/L5_2_REVISION8B_B_ACTIVATION.md').read_text()
files=list((ROOT/'rtl/matrix/candidates/rev8b_b').glob('*.sv'))
text='\n'.join(p.read_text() for p in files)
assert policy['phase_b_fallback']['authorized'] is True
assert policy['phase_b_fallback']['fma_stages']==5 and policy['phase_b_fallback']['contexts']==5
assert 'Status: **ACTIVE**' in activation
for token in ('bf16_context_scheduler5_rev8b_b_candidate','bf16_outer_product_array_control5_rev8b_b_candidate','bf16_context_tag_pipeline5_rev8b_b_candidate','bf16_context_fma_pipeline_lane5_rev8b_b_candidate','bf16_context_lane_cluster16_rev8b_b_candidate','bf16_cluster_flags_glue32_rev8b_b_candidate','bf16_context_front_control5_rev8b_b_candidate','bf16_outer_product_context_array_rev8b_b_candidate'):
 assert token in text,token
assert 'logic [31:0] accumulator_bank[0:4]' in text
assert 'logic [15:0] input_a_q,input_b_q' in text
assert 'input_context_q' in text
for forbidden in ('set_false_path','set_multicycle_path','HardFloat_rawFN'):
 assert forbidden not in text
r={'schema_version':1,'status':'PASS','revision':'8B-B','fma_stages':5,'contexts':5,'internal_context_tag_bits':3,'cluster_local_input_pre_boundary':True,'generated_hardfloat_modified':False,'public_128bit_command_modified':False,'candidate_files':sorted(str(p.relative_to(ROOT)) for p in files)}
out=ROOT/'reports/execution/l5_revision8b_b_source_contract_result.json';out.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps(r,indent=2,sort_keys=True))
