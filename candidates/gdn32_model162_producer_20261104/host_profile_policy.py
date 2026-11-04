"""Exact profiled mapper source relation; no run or numerical acceptance authority.
Only the new same-job diagnostic may consume its future actual build evidence.
Old driver/readonly/finite domains and their policies are unchanged.
"""
import hashlib,json,pathlib
P=pathlib.Path
REL='candidates/prefill_host_diagnostic_20261103/SOURCE_RELATION.json'
REL_SHA='0eb2261d28b1afd49692c40b578659a101a5fd5014655be18ededdc144110ddf'
DRIVER_REL='candidates/prefill_host_diagnostic_20261103/source/host_axi_driver_non_dpi.cpp'
DRIVER_SHA='e4b23d01ee81a738220512eb24d63b4e323723f686c8af340ad64849a00b5887'
CONTRACT_REL='candidates/same_job_execution_20261030/numeric/MODEL_P0_PREFILL_HOST_PROFILE_SOURCE_CONTRACT.json'
CONTRACT_SHA='634ecd3e0187844b7f97ef7ca9b0d38fdd274960bccc210a2419923164e05c24'
HARDWARE='prefill-supply-overlap-v1'
GENERATION_SHA='d6b8f476cb4f586ff47a44d4f2155891f15e3bac99f56e45039c459093feaabb'
OVERLAY_SHA='a43e536bc0d0af808429f0730e4ad5fd6f949f4b4e1deb8194c1518eeacb521b'
SCOPE='SAME_JOB_P0_M128_HOST_DIAGNOSTIC_NOT_FULL_ACCEPTANCE'
def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def regular(p,cap=1<<20):
 p=P(p);need(p.is_absolute() and p==p.resolve() and p.is_file()and all(not q.is_symlink()for q in(p,*p.parents))and 0<p.stat().st_size<=cap,'canonical bounded profiled source');return p

def decode(raw):
 need(type(raw)is bytes and len(raw)<=65536 and hashlib.sha256(raw).hexdigest()==REL_SHA,'exact frozen profiled source relation')
 d=json.loads(raw)
 need(d['schema']=='PREFILL_PROFILED_MAPPER_SOURCE_RELATION_V1'and d['scope']==SCOPE and d['hardware_source']==HARDWARE and d['generation_contract_sha256']==GENERATION_SHA and d['source_overlay_sha256']==OVERLAY_SHA,'same physical supply159 selection')
 need(d['driver_sha256']==DRIVER_SHA and d['source_contract']['repo_path']==CONTRACT_REL and d['source_contract']['sha256']==CONTRACT_SHA,'driver and P0 source roles')
 need(all(d[k]is False for k in('arithmetic_changed','eval_or_clock_sequence_changed','numeric_execution_authorized')),'source relation is not execution authority')
 return d

def load(repo):
 repo=P(repo).resolve(strict=True);raw=regular(repo/REL,65536).read_bytes();d=decode(raw)
 for row in [*d['sources'].values(),d['source_contract']]:
  p=regular(repo/row['repo_path']);need(p.stat().st_size==row['bytes']and sha(p)==row['sha256'],'exact profiled source role '+row['repo_path'])
 return d

def binding_policy(b):
 if 'host_profile_driver'not in b:return None
 need('first_fault_driver_contract'not in b and 'finite_watchdog_driver'not in b,'exclusive source policy')
 repo=P(b['repo']).resolve(strict=True);need(b['host_profile_driver']=={'path':str(repo/REL),'sha256':REL_SHA},'explicit fixed profiled driver selection')
 d=load(repo)
 need(b.get('hardware_source')==HARDWARE and b.get('generation_contract_sha256')==GENERATION_SHA,'profiled mapper only on selected supply159')
 need(b['driver']==str(repo/DRIVER_REL)and b['model_source_contract']==str(repo/CONTRACT_REL),'actual diagnostic driver and source-contract paths')
 need(b['pins'].get(str(repo/REL))==REL_SHA and b['pins'].get(b['fixed_source_overlay'])==OVERLAY_SHA,'relation/overlay generation pins')
 for row in [*d['sources'].values(),d['source_contract']]:need(b['pins'].get(str(repo/row['repo_path']))==row['sha256'],'profile role in original generation closure')
 need(b.get('numeric_execution_authorized')is False,'build does not self-admit')
 return d

def expected_driver_sha(b):
 d=binding_policy(b)
 if d is not None:return DRIVER_SHA
 from finite_watchdog_policy import expected_driver_sha as previous
 return previous(b)

def retained_relation(b):
 d=binding_policy(b)
 if d is None:return None
 p=P(b['repo'])/REL;raw=regular(p,65536).read_bytes()
 return {'path':str(p),'bytes':len(raw),'sha256':REL_SHA,'text':raw.decode()}

def artifact_policy(source,driver_sha):
 row=source.get('host_profile_driver')
 if row is None:
  need(driver_sha!=DRIVER_SHA,'profiled driver requires actual source relation');return None
 need(type(row)is dict and set(row)=={'path','bytes','sha256','text'},'retained profiled source relation')
 raw=row['text'].encode();d=decode(raw);need(row['bytes']==len(raw)and row['sha256']==REL_SHA,'retained relation bytes')
 need('readonly_probe'not in source and 'finite_watchdog_driver'not in source,'no policy crossover')
 need(source.get('driver_sha256')==driver_sha==DRIVER_SHA and source.get('model_candidate_observation',{}).get('source_closure',{}).get('generation_contract_sha256')==GENERATION_SHA,'actual selected source identity')
 dep=source['model_candidate_build_evidence']['driver_dependency'];driver=dep['driver']
 need(driver.endswith('/'+DRIVER_REL)and P(driver).is_absolute(),'actual profiled driver compiler input')
 root=driver[:-len(DRIVER_REL)];pins=source['generation_input_pins']
 need(pins.get(root+'candidates/prefill_supply_overlap_20261103/GENERATION_CONTRACT.json')==GENERATION_SHA and pins.get(source['fixed_source_overlay'])==OVERLAY_SHA,'actual selected supply generation/overlay pins')
 need(row['path']==root+REL and pins.get(root+REL)==REL_SHA and pins.get(root+CONTRACT_REL)==CONTRACT_SHA,'real retained source-contract generation inputs')
 for r in d['sources'].values():
  path=root+r['repo_path'];actual=dep['dependencies'].get(path)
  need(pins.get(path)==r['sha256']and type(actual)is dict and actual['path']==path and actual['bytes']==r['bytes']and actual['sha256']==r['sha256'],'fresh actual driver/helper dependency '+r['repo_path'])
 return d
