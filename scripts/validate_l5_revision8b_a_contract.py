#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
policy = json.loads((ROOT / 'config/l5_revision8b_a_policy.json').read_text())
broadcast = (ROOT / 'rtl/matrix/candidates/rev8b_a/bf16_front_to_cluster_broadcast32_rev8b_a_candidate.sv').read_text()
top = (ROOT / 'rtl/matrix/candidates/rev8b_a/bf16_outer_product_context_array_rev8b_a_candidate.sv').read_text()
operands = (ROOT / 'rtl/matrix/candidates/rev8b_a/bf16_operand_distribution512_rev8b_a_candidate.sv').read_text()

assert policy['decision'] == 'APPROVED'
assert policy['phase_a']['fma_stages'] == 4
assert policy['phase_a']['contexts'] == 4
assert policy['phase_a']['feedback_cycles'] == 4
assert policy['phase_b_fallback']['fma_stages'] == 5
assert policy['phase_b_fallback']['contexts'] == 5
assert 'BRANCHES = 4' in broadcast
assert 'LEAVES_PER_BRANCH = 8' in broadcast
assert broadcast.count('buf u_branch_buffer') == 1
assert broadcast.count('buf u_leaf_buffer') == 1
assert 'bf16_context_front_control_rev8_candidate front_control' in top
assert 'bf16_front_to_cluster_broadcast32_rev8b_a_candidate broadcast32' in top
assert 'bf16_operand_distribution512_rev8b_a_candidate operand_distribution' in top
assert 'bf16_context_lane_cluster16_rev8_candidate u_cluster' in top
assert 'bf16_context_fma_pipeline_lane4_rev8_candidate' not in top
for forbidden in ('set_false_path', 'set_multicycle_path', 'compile_ultra', 'HardFloat_rawFN'):
    assert forbidden not in broadcast
    assert forbidden not in top
    assert forbidden not in operands

result = {
    'schema_version': 1,
    'status': 'PASS',
    'revision': '8B-A',
    'phase_a': '4stage_4context_cycle_neutral_broadcast32',
    'topology': '1_to_4_to_32',
    'canonical_rtl_modified': False,
    'generated_hardfloat_modified': False,
}
out = ROOT / 'reports/execution/l5_revision8b_a_source_contract_result.json'
out.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
print(json.dumps(result, indent=2, sort_keys=True))
