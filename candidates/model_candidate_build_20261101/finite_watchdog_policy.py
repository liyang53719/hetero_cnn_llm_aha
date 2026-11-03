"""Exact ordinary driver watchdog substitution. No execution or acceptance authority."""
import hashlib,json,pathlib
P=pathlib.Path
OLD_SHA='343e99786a82fd5e738d3e48667fde204e21c077e397f8d20a4cddd59629bb61'
NEW_SHA='def22c17427b929a8e339224799845d729ad56d24b9646d99390b25a4ecd6f59'
OLD_REL='candidates/moe_router_score_observation_20261030/driver/host_axi_driver_non_dpi.cpp'
NEW_REL=OLD_REL.replace('.cpp','_finite_long.cpp')
SELF_REL='candidates/model_candidate_build_20261101/finite_watchdog_policy.py'
SOURCE_REL='candidates/same_job_execution_20261030/numeric/MODEL_P0_FINITE_LONG_SOURCE_CONTRACT.json'
SOURCE_SHA='5b7f12fa31a6ddef6256322fd8f19f46cb764c4b56f42bc599c87e752760d911'
GENERATION_SHA='0a5e09a27a447b028697a631e5207fc0af6cae15d4c324a55524f9d41a46a753'
OVERLAY_SHA='5ff6c6ee4887700b79f8bd3982250743575c3e3624d294d240b7bd92378bfc02'
SCHEMA='ORDINARY_FULL_EXACT_WATCHDOG_DRIVER_V1'
RELATION=dict(schema=SCHEMA,original_driver_sha256=OLD_SHA,finite_driver_sha256=NEW_SHA,driver_bytes=27317,original_max_active_cycles=1000000000,max_active_cycles=1290000000,generation_contract_sha256=GENERATION_SHA,source_overlay_sha256=OVERLAY_SHA,model_source_contract_sha256=SOURCE_SHA)
def need(v,s):
 if not v:raise ValueError(s)
def sha(p):return hashlib.sha256(P(p).read_bytes()).hexdigest()
def checked(path,want,cap=65536):
 p=P(path);need(p.is_absolute()and p==p.resolve()and p.is_file()and all(not q.is_symlink()for q in(p,*p.parents))and 0<p.stat().st_size<=cap,'bounded regular watchdog source')
 raw=p.read_bytes();need(len(raw)<=cap and hashlib.sha256(raw).hexdigest()==want,'exact watchdog source bytes');return raw

def inverse(old,new):
 need(type(old)is bytes and type(new)is bytes and len(old)==len(new)==27317,'exact driver byte counts')
 need(hashlib.sha256(old).hexdigest()==OLD_SHA and hashlib.sha256(new).hexdigest()==NEW_SHA,'fixed original and watchdog-only driver')
 before=b'maxCycles<=1000000000ULL';after=b'maxCycles<=1290000000ULL'
 need(old.count(before)==1 and old.count(after)==0 and new.count(after)==1 and new.count(before)==0 and new.replace(after,before)==old,'one exact inverse substitution only')
 return dict(RELATION)

def binding_policy(b):
 if 'finite_watchdog_driver'not in b:return None
 need(b['finite_watchdog_driver']==RELATION,'exact finite watchdog binding relation')
 need('first_fault_driver_contract'not in b and b.get('hardware_source')=='transposed-tile-address-v1','ordinary corrected159 hardware only')
 repo=P(b['repo']);old=checked(repo/OLD_REL,OLD_SHA);new=checked(repo/NEW_REL,NEW_SHA);inverse(old,new)
 need(b['driver']==str(repo/NEW_REL)and b['model_source_contract']==str(repo/SOURCE_REL),'actual new driver/source roles')
 for rel,want in ((OLD_REL,OLD_SHA),(NEW_REL,NEW_SHA),(SOURCE_REL,SOURCE_SHA)):
  checked(repo/rel,want);need(b['pins'].get(str(repo/rel))==want,'watchdog relation source in generation pins')
 need(b['pins'].get(str(repo/SELF_REL))==sha(repo/SELF_REL),'watchdog checker in generation pins')
 need(b['generation_contract_sha256']==GENERATION_SHA,'unchanged original hardware generation')
 return dict(RELATION)

def expected_driver_sha(b):
 if binding_policy(b)is not None:return NEW_SHA
 from first_fault_policy import expected_driver_sha as legacy
 return legacy(b)

def artifact_policy(source,driver_sha):
 relation=source.get('finite_watchdog_driver')
 if relation is None:
  need(driver_sha!=NEW_SHA,'new driver requires real producer relation');return None
 need(relation==RELATION and driver_sha==NEW_SHA and 'readonly_probe'not in source,'exact ordinary producer watchdog relation')
 c=source['model_candidate_observation']['source_closure']
 need(c['generation_contract_sha256']==GENERATION_SHA and c['source_overlay']['sha256']==OVERLAY_SHA and c['source_count']==159,'unchanged original159 generation')
 need(source['model_source_evidence']['contract']['sha256']==SOURCE_SHA,'new actual source-role contract')
 pins=source['generation_input_pins'];paths=[p for p in pins if p.endswith('/'+NEW_REL)]
 need(len(paths)==1 and pins[paths[0]]==NEW_SHA,'actual new driver generation input')
 repo=paths[0][:-len(NEW_REL)]
 for rel,want in ((OLD_REL,OLD_SHA),(SOURCE_REL,SOURCE_SHA)):
  need(pins.get(repo+rel)==want,'producer retained watchdog relation input')
 # Real compilation receipts are checked independently by existing pack/handoff.
 dep=source['model_candidate_build_evidence']['driver_dependency']
 need(dep['driver']==paths[0] and dep['dependencies'][paths[0]]['sha256']==NEW_SHA,'actual compiled new driver dependency')
 return dict(RELATION)
