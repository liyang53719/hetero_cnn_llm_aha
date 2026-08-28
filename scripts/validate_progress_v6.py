#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(path): return json.loads((ROOT/path).read_text(encoding='utf-8'))
control=load('config/control_plane.json');ledger=load('reports/execution/MASTER_LEDGER.json');next_action=load('reports/execution/NEXT_ACTION.json');final=load('reports/final_validation.json');rev7=load('reports/execution/l5_revision7_sandbox_approval.json');attention=load('reports/execution/l5_blocked_attention_cycle_e0_result.json');control_audit=load('reports/execution/control_plane_v6_audit.json');archspec=load('reports/execution/archspec_v6_collateral_result.json');program=load('reports/execution/qwen38_full_shape_program_v6_result.json');sequence=load('reports/execution/sequence_memory_cycle_v6_result.json');l51=load('reports/execution/l5_block128_local_e1_e4_result.json');l52=load('reports/execution/l5_matrix_context_local_e1_e4_result.json')
assert control['schema_version']==6
assert control['current_state']=='L5_2_REV7_H3_FAIL_WAIT_REV8_REVIEW'
assert control['remote_audit']['observed_head']=='fdecb3bf6ba08b403a2b9c7c87f63f6725c6eb0c'
assert control['remote_audit']['new_local_agent_commit_detected'] is True
assert control['revision7']['decision']=='EXECUTED_H3_FAIL_TIMING'
assert ledger['accepted_local_evidence']['L5.1']['status']=='PASS_E1_E4_ACCEPTED_ZERO_ENGINEERING_MARGIN'
assert ledger['accepted_local_evidence']['L5.2']['status']=='REV7_LANE_EQUIV_E1_PASS_H3_FAIL_TIMING'
assert next_action['state']=='WAIT_REMOTE_REVISION8_REVIEW' and next_action['decision']=='REVISION7_H3_FAIL_TIMING'
assert final['status']=='PASS_SANDBOX_V6_2_REV7_H3_FAIL_WAIT_REV8_REVIEW'
assert l51['status']=='PASS' and l51['e1']['fp32_pipeline_vectors']==1024 and l51['e1']['block128_vectors']==132
assert l51['e4']['block128_wns_ns']>=0 and l51['e4']['unmapped_cells']==0 and l51['e4']['unresolved_references']==0
assert l52['e1']['lanes']==512 and l52['e1']['contexts']==4 and l52['e1']['dependent_steps']==1000000 and l52['e1']['issue_utilization_ppm']==1000000
assert l52['hierarchical_e4']['context_components']['context_lane_joint_normal']['wns_ns']==-0.034333
assert l52['hierarchical_e4']['context_components']['context_lane_joint_high']['wns_ns']==-0.0371628
assert l52['closure']['l5_2_pass'] is False
assert rev7['status']=='PASS' and rev7['decision']=='APPROVE_WITH_GATES' and rev7['source_contract']['status']=='PASS' and rev7['tcl_contract']['status']=='PASS'
assert rev7['recurrence_stress']['operations']==100000 and rev7['recurrence_stress']['same_cycle_bypasses']==99996
assert attention['status']=='PASS' and attention['cases']['384']['serialized_cycles']==656644
assert attention['frozen_checks']['q1024_summary_merges']==43008 and attention['frozen_checks']['all_score_DDR_materialization_zero'] is True
assert control_audit['status']=='PASS';assert archspec['status']=='PASS' and archspec['total_sram_kib']==4096
assert program['status']=='PASS' and program['prefill']['operations']==500 and program['decode']['operations']==500
assert sequence['status']=='PASS' and sequence['stale_generation_rejected'] is True
assert 'candidate_sandbox_not_canonical' in (ROOT/'configs/arch_v2_qwen38_candidate.yaml').read_text()
for path in ('config/l5_revision7_policy.json','dc/synth_l5_bf16_context_lane_rev7.tcl','dc/formality_l5_context_lane_rev7.tcl','scripts/run_l5_matrix_context_revision7.sh','reports/L5_2_REVISION7_APPROVAL.md'): assert (ROOT/path).is_file(),path
lane=load('reports/execution/l5_revision7_lane_local_result.json')
assert lane['status']=='LANE_E4_PASS_MARGINAL_EQUIVALENCE_PASS_H3_FAIL' and lane['wns_ns']>=0 and lane['area_delta_percent']<0
assert (ROOT/'reports/L5_2_REVISION7_GATE_COMPARE_PLAN.md').is_file()
rev7_local=load('reports/execution/l5_matrix_context_revision7_result.json')
gate_compare=load('reports/execution/l5_revision7_gate_compare_result.json')
assert rev7_local['status']=='INCOMPLETE' and rev7_local['equivalence']['status']=='PASS' and rev7_local['e1']['status']=='PASS' and rev7_local['full_context_top']['wns_ns']<0
assert gate_compare['status']=='PASS' and gate_compare['method']=='post_synthesis_gate_compare' and gate_compare['mismatches']==0 and gate_compare['compared_cycles']==120032
assert (ROOT/'reports/L5_2_REVISION8_REVIEW_REQUEST.md').is_file()
result={'schema_version':6,'status':'PASS_V6_2','revision7':'EXECUTED_H3_FAIL_TIMING','L5_1':'PASS_ACCEPTED','L5_2_E1':'PASS_ACCEPTED','L5_2_E4':'FAIL_TIMING_WAIT_REV8_REVIEW','blocked_attention_cycle_E0':'PASS','retained_v6_gates':['control_plane_audit','Archspec_collateral','Qwen38_full_shape_program','SequenceMemory_cycle_E0']}
(ROOT/'reports/progress_v6_validation.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps(result,indent=2,sort_keys=True))
