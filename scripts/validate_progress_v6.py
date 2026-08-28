#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(path:str): return json.loads((ROOT/path).read_text(encoding='utf-8'))
control=load('config/control_plane.json')
ledger=load('reports/execution/MASTER_LEDGER.json')
next_action=load('reports/execution/NEXT_ACTION.json')
final=load('reports/final_validation.json')
l51=load('reports/execution/l5_block128_local_e1_e4_result.json')
l52=load('reports/execution/l5_matrix_context_local_e1_e4_result.json')
rev8=load('reports/execution/l5_revision8a_sandbox_result.json')
rev8_local=load('reports/execution/l5_revision8a_local_result.json')
attention=load('reports/execution/l5_blocked_attention_cycle_e0_result.json')
control_audit=load('reports/execution/control_plane_v6_audit.json')
archspec=load('reports/execution/archspec_v6_collateral_result.json')
program=load('reports/execution/qwen38_full_shape_program_v6_result.json')
sequence=load('reports/execution/sequence_memory_cycle_v6_result.json')
rev8b=load('config/l5_revision8b_a_policy.json')

assert control['schema_version']==6 and control['plan_version']=='2026-08-28-v6.4'
assert control['current_state']=='L5_2_REV8B_A_APPROVED_WAIT_IMPLEMENTATION'
assert control['remote_audit']['observed_head']=='4dec4a8df6b246f01778925745b7ae21292f74a3'
assert control['remote_audit']['decision']=='ACCEPT_REV7_LANE_EQUIV_E1_REJECT_H3_APPROVE_REV8A_CANDIDATE'
assert control['revision8A']['decision']=='APPROVE_CANDIDATE_E0_WITH_LOCAL_GATES'
assert control['revision8B']['decision']=='APPROVE_REVISION8B_A_WITH_AUTOMATIC_REVISION8B_B_FALLBACK'
assert ledger['current_state']==control['current_state']
assert ledger['accepted_local_evidence']['L5.2']['revision7_h3_wns_ns']<0
assert next_action['state']=='APPROVED_WAIT_LOCAL_REVISION8B_A_IMPLEMENTATION'
assert next_action['decision']=='APPROVE_REVISION8B_A_FANOUT_TREE_WITH_REVISION8B_B_FALLBACK'
assert final['status']=='PASS_SANDBOX_V6_4_REV8B_A_APPROVED_WAIT_IMPLEMENTATION'
assert rev8b['decision']=='APPROVED'
assert rev8b['phase_a']['fma_stages']==4 and rev8b['phase_a']['contexts']==4
assert rev8b['phase_a_gates']['h3_max_transition_violations']==0
assert rev8b['phase_a_gates']['h3_max_cap_violations']==0
assert rev8b['phase_b_fallback']['authorized'] is True
assert rev8b['phase_b_fallback']['fma_stages']==5 and rev8b['phase_b_fallback']['contexts']==5
assert rev8b['parallel_execution']['join_gate'].startswith('L5.2 plus L5.3 plus L5.4')

assert l51['status']=='PASS' and l51['e4']['block128_wns_ns']>=0
assert l52['e1']['lanes']==512 and l52['e1']['contexts']==4
assert l52['e1']['dependent_steps']==1_000_000 and l52['e1']['issue_utilization_ppm']==1_000_000
r7=l52['hierarchical_e4']['revision7']
assert r7['lane_E4'].startswith('PASS_MARGINAL')
assert r7['equivalence'].startswith('PASS_POST_SYNTHESIS_GATE_COMPARE')
assert r7['real_E1']=='PASS' and r7['structural_H3']=='FAIL_TIMING'
assert r7['h3_wns_ns']==-0.926028 and r7['h3_unmapped']==0 and r7['h3_unresolved']==0
assert l52['closure']['l5_2_pass'] is False

assert rev8['status']=='PASS'
assert rev8['decision']=='APPROVE_REVISION8A_CANDIDATE_FOR_LOCAL_E1_E4'
assert rev8['primary_differential']['accepted_operations']==100_000
assert rev8['primary_differential']['public_cycle_exact'] is True
assert rev8['primary_differential']['final_state_equal'] is True
assert rev8['multi_seed']['accepted_operations']==500_000
assert rev8['rtl_static_contract']['status']=='PASS'
assert rev8['local_flow_static_contract']['status']=='PASS'
assert rev8_local['status']=='INCOMPLETE_OR_FAIL'
assert all(rev8_local['checks'][key] for key in ('rev7_vs_rev8a','main_e1','adversarial_e1','lane','equivalence','cluster16','front'))
assert rev8_local['checks']['top'] is False
assert rev8_local['structural_h3']['wns_ns']<0
assert rev8_local['structural_h3']['max_transition_violations']==53455
assert rev8_local['structural_h3']['max_cap_violations']==10

for path in (
 'config/l5_revision8a_policy.json',
 'reports/L5_2_REVISION8A_APPROVAL.md',
 'reports/L5_LOCAL_AGENT_AUDIT_AFTER_REV7.md',
 'reports/L5_2_REVISION8B_REVIEW_REQUEST.md',
 'reports/L5_2_REVISION8B_A_APPROVAL.md',
 'config/l5_revision8b_a_policy.json',
 'src/heteronpu/revision8_early_commit.py',
 'scripts/run_l5_matrix_context_revision8a.sh',
 'scripts/run_l5_matrix_context_revision8a_compare.sh',
 'scripts/run_l5_matrix_context_revision8a_e1.sh',
 'scripts/run_l5_matrix_context_revision8a_adversarial_e1.sh',
 'scripts/run_l5_revision8a_gate_compare.sh',
 'dc/synth_l5_bf16_context_lane_rev8a.tcl',
 'dc/synth_l5_bf16_context_cluster16_rev8a.tcl',
 'dc/synth_l5_bf16_front_control_rev8a.tcl',
 'dc/synth_l5_bf16_context_top_rev8a.tcl',
): assert (ROOT/path).is_file(),path

assert attention['status']=='PASS'
assert attention['cases']['384']['serialized_cycles']==656644
assert attention['frozen_checks']['q1024_summary_merges']==43008
assert attention['frozen_checks']['all_score_DDR_materialization_zero'] is True
assert control_audit['status']=='PASS'
assert archspec['status']=='PASS' and archspec['total_sram_kib']==4096
assert program['status']=='PASS' and program['prefill']['operations']==500 and program['decode']['operations']==500
assert sequence['status']=='PASS' and sequence['stale_generation_rejected'] is True
assert 'candidate_sandbox_not_canonical' in (ROOT/'configs/arch_v2_qwen38_candidate.yaml').read_text()

result={
 'schema_version':6,
 'status':'PASS_V6_4',
 'L5_1':'PASS_ACCEPTED_ZERO_MARGIN',
 'L5_2_revision7':'LANE_EQUIV_E1_PASS_H3_FAIL',
 'L5_2_revision8A':'COMPONENTS_E1_EQUIV_PASS_H3_FAIL',
 'L5_2_revision8B_A':'APPROVED_WAIT_IMPLEMENTATION',
 'L5_3_L5_4':'PARALLEL_EXECUTION_AUTHORIZED',
 'blocked_attention_cycle_E0':'PASS',
 'retained_v6_gates':['control_plane_audit','Archspec_collateral','Qwen38_full_shape_program','SequenceMemory_cycle_E0'],
}
(ROOT/'reports/progress_v6_validation.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps(result,indent=2,sort_keys=True))
