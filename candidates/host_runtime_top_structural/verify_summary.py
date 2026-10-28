"""Check internal public metadata invariants only; does not re-read or recreate IR."""
from pathlib import Path
import json
R=Path(__file__).resolve().parent
def need(ok,message):
 if not ok:raise ValueError(message)
def load(n):return json.loads((R/n).read_text())
def main():
 f=load('ACTUAL_STRUCTURAL_FACTS.json');r=load('RESOURCE_SCOPE.json');h=load('HISTORICAL_FINDINGS.json');w=load('WIDTH_WARNINGS.json');c=load('CLASS_LINEAGE.json');s=load('SOURCE_PINS.json');p=load('REPRODUCTION.json')
 need(f['native_exit_code']==0 and f['preflight_checks']==f['postflight_checks']==1656,'actual exit/pins')
 need(f['sv_generated'] is False and f['rtl_simulated'] is False and f['launch_seal_closed'] is True,'scope')
 need(f['numerical_full_m128_passes']==f['rtl_five_profile_passes']==0 and f['performance_measured'] is False,'no numeric or performance claim')
 out={x['relative']:x for x in f['outputs']};need(len(out)==len(f['outputs'])==14,'14 unique artifact identities')
 a=out['host-diagnostic/official-low.fir'];b=out['host-diagnostic/HostBlockTopV4.lo.fir']
 need(a['bytes']==b['bytes']==258102601 and a['sha256']==b['sha256']=='f4bb8b87dea31205536d828d17bfab75e6ce255011ef7e15151055c29228691d','dual low digest')
 need(out['host-diagnostic/original-high.fir']['bytes']==97256876,'actual high size')
 need(r['matrix_endpoints']*r['matrix_macs_per_endpoint']==r['logical_matrix_macs']==4096,'fixed logical MAC')
 need((r['whole_top_fp32_alu_instances'],r['whole_top_scalar_instances'],r['element32_banks'],r['element_bank_alus'],r['idma_instances'])==(81,17,1,32,1),'honest hierarchy')
 need(r['matrix_and_idma_blackbox_interfaces'] and not r['whole_top_one_fpu_claim'] and not r['physical_ram_ports_or_II_proven'],'blackbox and physical limit')
 need(r['input_ports']==41 and r['output_ports']==44 and r['top_ports']==85 and r['launch_bits']==844,'ports')
 need(w['count']==len(w['warnings'])==30 and w['by_code']=={'W004':21,'W005':9},'warnings retained')
 for code,n in w['by_code'].items():need(sum(x['code']==code for x in w['warnings'])==n,'warning count')
 need([x['native_exit_code'] for x in h['attempts']]==[1,1,0] and [x['status'] for x in h['attempts']]==['FAIL','FAIL','PASS_STRUCTURE_ONLY'],'failure history')
 need(len(c['compiles'])==2 and [(x['baseline'],x['new_classes']) for x in c['compiles']]==[(1000,1),(991,10)],'separate incremental compiles')
 need(c['inherited_fence_classes']==148 and c['final']['latest_classes']==159 and c['final']['actual_structural_classes']==1001,'class closure')
 need(len(s['latest_sources'])==31 and len(s['additional_diagnostic_support_sources'])==25 and s['diagnostic_input_source_count']==56,'full diagnostic source boundary')
 need(sum(x['location']=='this_package_separately_compiled' for x in s['latest_sources'])==2 and sum(x['location']=='requires_parent_inherited' for x in s['latest_sources'])==5,'bundled sources and parents')
 need(p['disk_contract']['start_floor_bytes']==3*1024**3 and p['disk_contract']['end_floor_bytes']==2*1024**3,'disk gates unchanged')
 need(f['disk_start']>=p['disk_contract']['start_floor_bytes'] and f['disk_end']>=p['disk_contract']['end_floor_bytes'],'actual disk gate met')
 need(p['exact_inverse_verified'] and p['status']=='REQUIRES_PARENT_STRUCTURE_RECIPE_NOT_SELF_CONTAINED','requires parent')
 print('PASS public metadata invariants only; original IR not bundled or replayed')
if __name__=='__main__':main()
