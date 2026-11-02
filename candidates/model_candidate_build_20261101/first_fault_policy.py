"""Separately frozen read-only driver inputs; old candidate defaults stay exact."""
import hashlib,importlib.util,json,pathlib
P=pathlib.Path
D=P(__file__).resolve().parent
# Full original digest, not a caller-controlled expected value.
LEGACY_DRIVER_SHA='343e99786a82fd5e738d3e48667fde204e21c077e397f8d20a4cddd59629bb61'
CONTRACT_SHA='79cd00d5f9d0dd95c160b6de35c1d1c2e174171933b98721168d818eb6fcbff2'
ORIGINAL_SV_SHA='3d148277114ff5d968d0e200f4ab117839a3b6c0c0d33e5388e6e5268d42d029'
FIRST_FAULT_MANIFEST_SCHEMA='MODEL_CANDIDATE_FIRST_FAULT_BUILD_ARTIFACT_V1'
FIRST_FAULT_SCOPE='P0_FIRST_FAULT_READONLY_SAME_FULL_M128_STIMULUS_NOT_NUMERICAL_ACCEPTANCE'
CONTRACT_REPO_PATH='candidates/model_candidate_build_20261101/FIRST_FAULT_DRIVER_CONTRACT.json'
SOURCE_CONTRACT_SHA='b31095b3e118fe5a2639886bb3dbe3f6de8067cd886884d898c1220b85f8500f'
SOURCE_CONTRACT_REPO_PATH='candidates/same_job_execution_20261030/numeric/MODEL_P0_FIRST_FAULT_SOURCE_CONTRACT.json'
ROLES=('legacy_driver','diagnostic_driver','host_observer','probe_schema','probe_config','probe_generator','inverse_verifier','hardware_generation_contract')
def need(v,s):
 if not v:raise ValueError(s)
def sha(p):
 with P(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def regular(p,cap=2<<20):
 p=P(p);need(p.is_absolute() and str(p)==str(p.resolve()) and p.is_file() and all(not q.is_symlink() for q in(p,*p.parents)) and 0<p.stat().st_size<=cap,'canonical bounded source');return p
def decode_contract(raw):
 need(type(raw)is bytes and 0<len(raw)<=65536 and hashlib.sha256(raw).hexdigest()==CONTRACT_SHA,'independently frozen first-fault contract')
 d=json.loads(raw);need(set(d)=={'schema','scope',*ROLES,'host_ports_sha256','control_semantics_changed','extra_eval_or_clock','payload_data_or_addresses'},'exact contract fields')
 need(d['schema']=='FIRST_FAULT_DRIVER_CONTRACT_V1' and d['scope']==FIRST_FAULT_SCOPE,'driver contract scope')
 need(all(d[k] is False for k in ('control_semantics_changed','extra_eval_or_clock','payload_data_or_addresses')),'read-only contract')
 need(d['legacy_driver']['sha256']==LEGACY_DRIVER_SHA,'original driver identity')
 for r in ROLES:
  v=d[r];need(set(v)=={'repo_path','bytes','sha256'} and type(v['bytes'])is int and 0<v['bytes']<=2<<20,'source role pin');p=P(v['repo_path']);need(not p.is_absolute() and '..'not in p.parts and str(p)==v['repo_path'],'role repo path')
 return d

def load_source_contract(repo):
 repo=P(repo).resolve(strict=True);p=regular(repo/CONTRACT_REPO_PATH);d=decode_contract(p.read_bytes())
 for name in ROLES:
  row=d[name];q=regular(repo/row['repo_path']);need(q.stat().st_size==row['bytes'] and sha(q)==row['sha256'],'fixed role bytes '+name)
 verifier=repo/d['inverse_verifier']['repo_path'];s=importlib.util.spec_from_file_location('_fixed_readonly_driver_inverse',verifier);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
 proof=m.verify_driver((repo/d['legacy_driver']['repo_path']).read_bytes(),(repo/d['diagnostic_driver']['repo_path']).read_bytes())
 need(proof['exact_inverse'] is True and proof['legacy_driver_sha256']==LEGACY_DRIVER_SHA and proof['diagnostic_driver_sha256']==d['diagnostic_driver']['sha256'],'whole driver inverse relation')
 return d

def binding_policy(b):
 if 'first_fault_driver_contract'not in b:return None
 repo=P(b['repo']).resolve(strict=True);v=b['first_fault_driver_contract'];need(type(v)is dict and set(v)=={'path','sha256'} and v=={'path':str(repo/CONTRACT_REPO_PATH),'sha256':CONTRACT_SHA},'explicit fixed first-fault selector')
 d=load_source_contract(repo);need(b['pins'].get(v['path'])==CONTRACT_SHA,'contract in original source pins')
 for name in ROLES:
  row=d[name];need(b['pins'].get(str(repo/row['repo_path']))==row['sha256'],'role in original source pins '+name)
 need(b['driver']==str(repo/d['diagnostic_driver']['repo_path']),'exact selected diagnostic driver')
 need(b['generation_contract']==str(repo/d['hardware_generation_contract']['repo_path']) and b['generation_contract_sha256']==d['hardware_generation_contract']['sha256'],'unchanged hardware generation identity')
 need(b.get('model_source_contract')==str(repo/SOURCE_CONTRACT_REPO_PATH) and b['pins'].get(str(repo/SOURCE_CONTRACT_REPO_PATH))==SOURCE_CONTRACT_SHA and sha(regular(repo/SOURCE_CONTRACT_REPO_PATH))==SOURCE_CONTRACT_SHA,'exact first-fault P0 source contract')
 return d

def expected_driver_sha(b):
 d=binding_policy(b);return LEGACY_DRIVER_SHA if d is None else d['diagnostic_driver']['sha256']

def artifact_policy(manifest,source):
 if manifest.get('schema')!='MODEL_CANDIDATE_FIRST_FAULT_BUILD_ARTIFACT_V1':
  need('readonly_probe'not in source and 'readonly_probe_contract'not in manifest,'no diagnostic evidence in old artifact');return None
 need(manifest.get('scope')==FIRST_FAULT_SCOPE,'new artifact exact diagnostic scope')
 need(manifest['common']['sv']['sha256']==source['sv_sha256']==ORIGINAL_SV_SHA,'exact unchanged actual hardware SV')
 e=source.get('readonly_probe');need(type(e)is dict and set(e)=={'schema','status','contract','accessor_generation'} and e['schema']=='FIRST_FAULT_READONLY_BUILD_EVIDENCE_V1' and e['status']=='OBSERVED_UNREVIEWED','complete readonly build evidence')
 row=e['contract'];need(type(row)is dict and set(row)=={'path','bytes','sha256','text'},'retained contract original text')
 raw=row['text'].encode();d=decode_contract(raw);need(row['bytes']==len(raw) and row['sha256']==CONTRACT_SHA and manifest['readonly_probe_contract']=={'bytes':len(raw),'sha256':CONTRACT_SHA},'artifact contract bytes joined')
 need(source['generation_input_pins'].get(row['path'])==CONTRACT_SHA,'contract actual producer pin')
 need(manifest['common']['driver']['sha256']==source['driver_sha256']==d['diagnostic_driver']['sha256'],'actual diagnostic driver pin')
 return d
