"""Pre-reviewed source-only candidate-generation gate; NEVER numeric acceptance.
The checked-in contract pin is frozen only after independent source review.
Observed IR/SV hashes cannot replace it or authorize executor admission.
"""
import hashlib,json,pathlib,re
P=pathlib.Path
D=P(__file__).resolve().parent
GENERATION_CONTRACT_SHA256='3354827c1c9d2ac167b3b325dc07acbd50ea663ddd384dddfea1b1d037ae3851' # Independently reviewed generation inputs only; no numeric acceptance
CONTRACT_FIELDS={'schema','scope','source_overlay_sha256','source_count','unchanged_module_contract_sha256','host_ports_sha256','driver_sha256','cpp_build_policy','matrix_macs','vector_lanes','tokens','profiles','numeric_execution_authorized','final_rtl_accepted'}
def need(v,s):
 if not v:raise ValueError(s)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def regular(p,cap=2<<20):
 p=P(p);need(p.is_absolute()and all(not q.is_symlink()for q in(p,*p.parents))and p.is_file()and 0<p.stat().st_size<=cap,'bounded canonical regular input');return p
def load_contract(path,expected):
 need(type(GENERATION_CONTRACT_SHA256)is str and re.fullmatch('[0-9a-f]{64}',GENERATION_CONTRACT_SHA256)and expected==GENERATION_CONTRACT_SHA256,'candidate source review not frozen')
 p=regular(path);need(sha(p)==expected,'candidate contract drift');d=json.loads(p.read_text())
 need(set(d)==CONTRACT_FIELDS and d['schema']=='MODEL_CANDIDATE_GENERATION_CONTRACT_V1'and d['scope']=='SOURCE_STRUCTURAL_PRECONDITIONS_ONLY_NOT_NUMERICAL_ACCEPTANCE','candidate contract exact schema')
 need(d['matrix_macs']==4096 and d['vector_lanes']==32 and d['tokens']==128 and d['profiles']==list(range(5))and all(type(v)is int for v in d['profiles']),'single full physical candidate configuration')
 need(d['numeric_execution_authorized']is False and d['final_rtl_accepted']is False and d['cpp_build_policy']=='CPP_O1_STRICT_V1','generation never numeric authorization')
 need(type(d['source_count'])is int and 155<d['source_count']<=256,'bounded actual extended original source list')
 for k in ('source_overlay_sha256','unchanged_module_contract_sha256','host_ports_sha256','driver_sha256'):need(type(d[k])is str and re.fullmatch('[0-9a-f]{64}',d[k]),'exact source contract hash')
 return d
def require_generation_binding(b):
 from first_fault_policy import binding_policy
 diagnostic=binding_policy(b)
 d=load_contract(b['generation_contract'],b['generation_contract_sha256'])
 need(b['generation_contract']in b['pins']and b['pins'][b['generation_contract']]==b['generation_contract_sha256'],'generation contract in source closure')
 for field,key in [('fixed_source_overlay','source_overlay_sha256'),('unchanged_module_contract','unchanged_module_contract_sha256'),('host_port_contract','host_ports_sha256'),('driver','driver_sha256')]:
  p=regular(b[field]);expected=diagnostic['diagnostic_driver']['sha256'] if diagnostic is not None and field=='driver' else d[key]
  need(sha(p)==expected and b['pins'].get(str(p))==expected,'pre-reviewed generation input '+field)
 need(b.get('candidate_status')=='UNREVIEWED_MODEL_BUILD'and b.get('numeric_execution_authorized')is False,'candidate cannot self-admit')
 return d

def checked_paths(repo,overlay,original,contract):
 """Original fixed155 rows keep order; reviewed replacements/new rows only."""
 repo=P(repo).resolve();p=regular(overlay);need(sha(p)==contract['source_overlay_sha256'],'selected original source overlay')
 d=json.loads(p.read_text());need(d['schema']=='MODEL_SOURCE_OVERLAY_V1'and d['base_overlay_sha256']=='9be7810a372572e87b40d86d0b30245140c31cd40cdd6cf2f9cacead459beda2','new versioned overlay on original frozen source')
 base=repo/'candidates/ci_frontend_materialization_r2_20261029/FIXED_SOURCE_OVERLAY_R2.json';need(sha(base)==d['base_overlay_sha256'],'original overlay preserved')
 old=json.loads(base.read_text())['files'];rows=d['files'];need(len(original['sources'])==len(old)==155 and len(rows)==d['source_count']==contract['source_count'],'actual source count')
 names=[r['name']for r in rows];need(len(set(names))==len(names)and names[:155]==[r['name']for r in old],'original source order and unique new definitions')
 changed=[r['name']for r,o in zip(rows,old)if r['sha256']!=o['sha256']];need(changed==d['changed_names']and names[155:]==d['added_names'],'reviewed exact changed/new selection')
 paths=[]
 for r in rows:
  rel=pathlib.PurePosixPath(r['repo_path']);need(not rel.is_absolute()and '..'not in rel.parts and str(rel)==r['repo_path']and rel.name==r['name']and rel.suffix=='.scala','canonical Scala source path')
  q=regular(repo/rel,4<<20);need(type(r['bytes'])is int and q.stat().st_size==r['bytes']and sha(q)==r['sha256'],'exact candidate Scala bytes');paths.append(str(q))
 return paths
