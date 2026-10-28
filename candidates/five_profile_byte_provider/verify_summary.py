"""Checks published count/hash metadata, not payload bytes or DUT results."""
from pathlib import Path
import json
R=Path(__file__).resolve().parent
def load(n):return json.loads((R/n).read_text())
def need(b,m):
 if not b:raise ValueError(m)
def main():
 a=load('ACTUAL_FACTS.json');p=load('PROGRAM_PINS.json');e=load('EXTERNAL_INPUTS.json');h=load('LOGICAL_HASHES.json')
 need(a['status']=='BYTE_PROVIDER_ONLY_NOT_DUT','scope')
 for k in ['cpp_backend_source_frozen_in_this_package','cpp_backend_source_bundled','numeric_pass','performance_measurement','publication_rehashed_multigb_payloads','publication_repeated_integration']:need(a[k] is False,'no invented qualification '+k)
 need(a['full_chisel_m128_passes']==a['rtl_five_profile_passes']==0,'full qualification zero')
 need(a['tensor_streams']==84 and a['tensor_bytes']==3631340832,'logical count')
 need(e['source_file_count']==a['source_files_verified']==88 and e['source_bytes']==a['source_bytes_verified']==3534006784,'source record count')
 need(len(e['export_verified_source_files'])==88 and sum(x['bytes'] for x in e['export_verified_source_files'])==3534006784,'source sum')
 need(sum(x['checks'] for x in a['cross_language']['profiles'])==561 and sum(x['readonly_allocations'] for x in a['cross_language']['profiles'])==94,'cross-language byte scope')
 need(a['cross_language']['numeric_pass'] is False,'cross-language not numerical')
 need([x['profile'] for x in a['profiles']]==list(range(5)),'five profiles')
 need([x['transport_checks'] for x in a['profiles']]==[118,127,117,149,139],'transport checks')
 total=0;count=0
 for i,r in enumerate(h['profiles']):
  need(r['profile']==i,'logical profile')
  tensors={k:v for k,v in r['logical_ro'].items() if k not in ['command_bytes','descriptor_bytes']}
  need(len(tensors)==a['profiles'][i]['tensor_streams'],'tensor count per profile');count+=len(tensors);total+=sum(x['bytes'] for x in tensors.values())
  need(a['profiles'][i]['numeric_pass'] is False and a['profiles'][i]['timing_model'] is False and a['profiles'][i]['test_writes_exported'] is False,'transport only')
 need(count==84 and total==3631340832,'logical total')
 need([(x['commands'],x['descriptors']) for x in p['profiles']]==[(21,215),(17,219),(22,261),(13,199),(18,241)],'program counts')
 need(p['profiles'][0]['reproduction']=='exact_three_parent_files_required','profile0 parent gap')
 need(p['prior_prefix_pass_inherited'] is False,'prior prefix not inherited')
 need(all(p['profiles'][i]['qknorm_recipe']=='C2_Torch210CpuDefault256' for i in [2,4]),'existing C2 contract')
 print('PASS metadata invariants only: BYTE_PROVIDER_ONLY,84 tensor hashes,561 probes; full numerical/RTL0of5')
if __name__=='__main__':main()
