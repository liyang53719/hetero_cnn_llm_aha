"""Public metadata invariant checks only, never compiler/elaboration/DUT proof."""
from pathlib import Path
import json
R=Path(__file__).resolve().parent
def load(n):return json.loads((R/n).read_text())
def need(b,m):
 if not b:raise ValueError(m)
def main():
 a=load('ACTUAL_FACTS.json');c=load('CLASS_LINEAGE.json');s=load('SOURCE_PINS.json');h=load('HISTORICAL_FINDINGS.json');r=load('RESOURCE_SCOPE.json');p=load('REPRODUCTION.json');lim=load('REPRODUCTION_LIMITS.json')
 need(a['native_exit_code']==0 and a['compile_log_empty'] and a['pre_post_pin_checks']==3790,'actual compile')
 need((a['compiled_source_count'],a['baseline_class_count'],a['new_class_count'],a['new_class_bytes'])==(1,997,4,1164032),'incremental compile only')
 need((a['final_source_closure_count'],a['final_class_count'],a['inherited_source_count'],a['inherited_class_count'])==(31,159,30,155),'final source closure')
 need(a['admission_opened'] is True,'bounded new admission')
 for key in ['prior_structural_pass_inherited','new_structural_run','full_program_backend_executed','historical_transitive_graph_verified']:need(a[key] is False,'no inherited or unrun PASS '+key)
 need(a['full_m128_passes']==a['rtl_five_profile_passes']==h['full_m128_passes']==h['rtl_five_profile_passes']==0,'no numerical RTL PASS')
 need(h['prior_structural_pass_inherited'] is False and len(h['preserved_previous_failures'])==2,'history retained')
 need(lim['historical_transitive_graph_verified'] is False and lim['prior_structural_pass_inherited'] is False and lim['full_program_backend_executed'] is False,'reproduction limits')
 rows=s['final_sources'];need(len(rows)==31 and len({x['name'] for x in rows})==31,'source31')
 need([sum(x['location']==k for x in rows) for k in ['this_package_compiled','shared_public_inherited','requires_parent_inherited']]==[1,25,5],'source location closure')
 need(sum(x['class_count'] for x in rows)==159,'class159')
 need((c['baseline']['retained_ancestor_count'],c['baseline']['inherited_count'],c['baseline']['retained_count'])==(842,155,997),'baseline composition')
 need((c['baseline']['composed_count'],c['baseline']['removed_count'],c['actual']['new_classes'])==(1001,4,4),'whole source family')
 need((c['final']['sources'],c['final']['classes'],c['final']['inherited_sources'])==(31,159,30),'class lineage')
 need(r['rank3_scratch_dims']==['heads',128,3280] and r['rank3_scratch_element_strides']==[419840,3280,1] and r['scratch_bytes_per_head']==1679360,'scratch geometry')
 need(r['physical_scratch_layout_capacity_unchanged'] is True and r['common_entry_rows']==128,'cold128 capacity')
 need(r['control_comparison_logic_changed'] is True and r['zero_area_claim'] is False,'resource honesty')
 need(r['existing_matrix_logical_macs']==4096 and r['existing_shared_bank_lanes']==32,'resource source definition')
 need(len(p['argv_template'])==17 and p['argv_template'][-1]=='{PACKAGE}/source/HostBlockCommandsV4.scala' and p['baseline_count']==997 and p['actual_sources']==1,'recipe source count')
 need(p['original_caps']['heap_bytes']==1073741824 and p['original_caps']['total_wall_seconds']==180 and p['original_caps']['outer_wall_seconds']==210,'bounded historical recipe')
 print('PASS public metadata invariants only; prior structural PASS not inherited; full numerical/sameRTL0of5')
if __name__=='__main__':main()
