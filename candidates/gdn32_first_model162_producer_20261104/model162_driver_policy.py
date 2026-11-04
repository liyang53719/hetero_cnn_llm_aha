"""Exact literal-diagnostic signature revision only; no hardware/runtime waiver."""
import hashlib,json,pathlib
P=pathlib.Path
OLD_REL='candidates/moe_router_score_observation_20261030/driver/host_axi_driver_non_dpi.cpp'
NEW_REL='candidates/gdn32_first_model162_producer_20261104/driver/host_axi_driver_non_dpi.cpp'
OLD_SHA='343e99786a82fd5e738d3e48667fde204e21c077e397f8d20a4cddd59629bb61'
NEW_SHA='e8aeaac48a407e27bcbf54db0d85867a904c67a2dce7e1d270999a8482453261'
BEFORE=b'void need(bool p,const std::string& why){if(!p)throw std::runtime_error(why);}'
AFTER=b'void need(bool p,const char* why){if(!p)throw std::runtime_error(why);}'
def need(v,m):
 if not v:raise ValueError(m)
def sha(p):return hashlib.sha256(P(p).read_bytes()).hexdigest()
def inverse(before,after):
 need(hashlib.sha256(before).hexdigest()==OLD_SHA and hashlib.sha256(after).hexdigest()==NEW_SHA,'exact numerical driver revision bytes')
 need(before.count(BEFORE)==after.count(AFTER)==1 and AFTER not in before and BEFORE not in after and before.replace(BEFORE,AFTER)==after and after.replace(AFTER,BEFORE)==before,'single diagnostic signature whole-file inverse')
 return {'original_sha256':OLD_SHA,'candidate_sha256':NEW_SHA,'numeric_execution_authorized':False,'performance_measured':False}
def binding_policy(b):
 from candidate_generation_gate import MODEL162_SOURCE,MODEL162_GENERATION_SHA
 if b.get('hardware_source')!=MODEL162_SOURCE:
  need(b.get('driver')is None or not str(b['driver']).endswith('/'+NEW_REL),'new driver cannot use legacy hardware alias');return None
 need(b.get('generation_contract_sha256')==MODEL162_GENERATION_SHA and not any(k in b for k in ('first_fault_driver_contract','finite_watchdog_driver','host_profile_driver')),'independent actual162 ordinary driver policy')
 repo=P(b['repo']);old=repo/OLD_REL;new=repo/NEW_REL
 need(b['driver']==str(new)and b['pins'].get(str(new))==NEW_SHA and b['pins'].get(str(old))==OLD_SHA,'old and new driver generation source identities')
 for p in (old,new):need(p.is_file()and all(not q.is_symlink()for q in(p,*p.parents)),'canonical driver source')
 return inverse(old.read_bytes(),new.read_bytes())
def expected_driver_sha(b):
 if binding_policy(b)is not None:return NEW_SHA
 from host_profile_policy import expected_driver_sha as previous
 return previous(b)
def artifact_policy(source,driver_sha):
 from candidate_generation_gate import MODEL162_GENERATION_SHA,MODEL162_OVERLAY_SHA,MODEL162_SOURCE_CONTRACT_REL,MODEL162_SOURCE_CONTRACT_SHA
 c=source.get('model_candidate_observation',{}).get('source_closure',{})
 if c.get('generation_contract_sha256')!=MODEL162_GENERATION_SHA:
  need(driver_sha!=NEW_SHA,'new driver requires independent actual162 artifact');return None
 need(c.get('source_overlay',{}).get('sha256')==MODEL162_OVERLAY_SHA and c.get('source_count')==162 and source.get('driver_sha256')==driver_sha==NEW_SHA,'actual162 generation and driver artifact identity')
 dep=source.get('model_candidate_build_evidence',{}).get('driver_dependency',{});driver=dep.get('driver','');need(driver.endswith('/'+NEW_REL)and P(driver).is_absolute(),'actual new driver GCC compile input')
 root=driver[:-len(NEW_REL)];pins=source['generation_input_pins'];need(pins.get(root+OLD_REL)==OLD_SHA and pins.get(root+NEW_REL)==NEW_SHA and pins.get(root+MODEL162_SOURCE_CONTRACT_REL)==MODEL162_SOURCE_CONTRACT_SHA,'complete driver source and P0 evidence pins')
 need(not any(k in source for k in ('readonly_probe','host_profile_driver','finite_watchdog_driver')),'no driver policy crossover')
 return {'driver_sha256':NEW_SHA,'numeric_execution_authorized':False,'performance_measured':False}
