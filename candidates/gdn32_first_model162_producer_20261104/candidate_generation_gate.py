"""Independent exact actual162 adapter. Legacy159 admission is never relaxed.
Only source/build identity is established; no runtime or historical PASS transfer.
"""
import hashlib, importlib.util, json, pathlib, re
P=pathlib.Path
D=P(__file__).resolve().parent
MODEL162_SOURCE='gdn-chunk32-abort-v2'
MODEL162_DIR='candidates/gdn32_first_model162_producer_20261104'
MODEL162_CATALOG_REL='candidates/gdn32_first_model_execution_20261104/GDN32_FULL_SOURCE_PINS.json'
UPSTREAM_DIR='candidates/gdn_chunk32_actual_v2_20261104'
LEGACY_DIR='candidates/model_candidate_build_20261101'
MODEL162_GENERATION_SHA='c18dd273361ad7b5917dab8c780c61205a509adbf4e820e9b23fe11ed1cb4040'
MODEL162_OVERLAY_SHA='589e1e0f522aae929d25283b180ec566683254862f9537494aec26e2bd27efe1'
UPSTREAM_GENERATION_SHA='2b2f02d698f16a57ba696c52c4669a1226a68c5378efdc8ebe392cc1b9098f52'
UPSTREAM_OVERLAY_SHA='1bd1db80190d2d611cfeb15f50c2bbadec76f2aaad74280671b22e843240a945'
LEGACY_GATE_SHA='9131e8c6e2e0a3e357990b795ee808837d04ae8bc181862be7a143037166fac2'
LEGACY_OVERLAY_SHA='51621bbffc5ab0dfc97e88d66fee93722e66b6b1ed2a8c2ba7d0f588d9345472'
PRECONDITIONS_SHA='80c1426efa4a8f2740dadc1757a35d01913233e86c5fc5c2a35f9d3a8d044f0e'
HOST_PORTS_SHA='289f230ec8fc85e7aee0396ab34424f505855074a762707e874fbf8a2f45ca08'
DRIVER_SHA='e8aeaac48a407e27bcbf54db0d85867a904c67a2dce7e1d270999a8482453261'
MODEL162_SOURCE_CONTRACT_REL='candidates/gdn32_first_model_execution_20261104/numeric/MODEL_P0_GDN32_SOURCE_CONTRACT.json'
MODEL162_SOURCE_CONTRACT_SHA='8ac291f2d129de351a19c95c643437a3600a01d8b40a8e55b5eafabb32975cbc'
MODEL162_RESOURCE_POLICY='ORIGINAL_SERIAL_FRONTEND_STAGE_TUPLES_V1'
MODEL162_RESOURCE_ADAPTER_REL=MODEL162_DIR+'/model162_resources.py'
MODEL162_RESOURCE_ADAPTER_SHA='97454e9a114370d0f6282ad5da693b9b3386003f3d5180f60798a9c9a3c25865'
MODEL162_PACK_POLICY='ACTUAL162_CATALOG_AND_WRITER_CANONICAL_PATH_V1'
MODEL162_PACK_REL=MODEL162_DIR+'/pack_model_candidate.py'
MODEL162_PACK_SHA='047434165a66c20bd2d9a0b64db7acbde26fbd9c06fd206e7a890dab8a2e6609'
SOURCE_CHOICES=('legacy','transposed-tile-address-v1','prefill-supply-overlap-v1',MODEL162_SOURCE)
CORE_FIELDS={'schema','scope','source_overlay_sha256','source_count','unchanged_module_contract_sha256','host_ports_sha256','driver_sha256','cpp_build_policy','matrix_macs','vector_lanes','tokens','profiles','numeric_execution_authorized','final_rtl_accepted'}
CONTRACT_FIELDS=CORE_FIELDS|{'hardware_source','upstream_generation_contract_repo_path','upstream_generation_contract_sha256','upstream_overlay_sha256','model_source_contract_repo_path','model_source_contract_sha256','old_artifact_reuse_permitted','host_resource_policy','resource_adapter_sha256','pack_binding_policy','pack_source_sha256'}
def need(v,s):
 if not v:raise ValueError(s)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def regular(p,cap=2<<20):
 p=P(p);need(p.is_absolute() and p==p.resolve() and all(not q.is_symlink()for q in(p,*p.parents)) and p.is_file() and 0<p.stat().st_size<=cap,'bounded canonical regular input');return p

def legacy_gate(repo=None):
 repo=P(repo).resolve() if repo is not None else D.parent.parent
 p=regular(repo/LEGACY_DIR/'candidate_generation_gate.py');need(sha(p)==LEGACY_GATE_SHA,'unchanged legacy159 gate')
 spec=importlib.util.spec_from_file_location('_unchanged_model159_generation_gate',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def validate_source_selection(name='legacy',first_fault_readonly=False,terminal_finite_readonly=False):
 need(type(name)is str and name in SOURCE_CHOICES,'explicit bounded hardware source selection')
 need(not(first_fault_readonly and terminal_finite_readonly),'one readonly source mode')
 need(name=='legacy' or not(first_fault_readonly or terminal_finite_readonly),'new hardware cannot reuse unchanged-SV diagnostics')
 return name

def load_contract(path,expected):
 if expected!=MODEL162_GENERATION_SHA:return legacy_gate().load_contract(path,expected)
 p=regular(path);need(sha(p)==MODEL162_GENERATION_SHA,'independently pinned model162 adapter contract');d=json.loads(p.read_text())
 need(set(d)==CONTRACT_FIELDS and d['schema']=='MODEL162_GENERATION_CONTRACT_V3' and d['scope']=='SOURCE_STRUCTURAL_PRECONDITIONS_ONLY_NOT_NUMERICAL_ACCEPTANCE','exact independent model162 contract schema')
 need(d['hardware_source']==MODEL162_SOURCE and type(d['source_count'])is int and d['source_count']==162,'explicit actual162 selection')
 need(d['source_overlay_sha256']==MODEL162_OVERLAY_SHA and d['upstream_generation_contract_repo_path']==UPSTREAM_DIR+'/GENERATION_CONTRACT.json' and d['upstream_generation_contract_sha256']==UPSTREAM_GENERATION_SHA and d['upstream_overlay_sha256']==UPSTREAM_OVERLAY_SHA,'actual hardware and adapter identities')
 need(d['pack_binding_policy']==MODEL162_PACK_POLICY and d['pack_source_sha256']==MODEL162_PACK_SHA,'exact actual162 writer binding contract')
 need(d['host_resource_policy']==MODEL162_RESOURCE_POLICY and d['resource_adapter_sha256']==MODEL162_RESOURCE_ADAPTER_SHA,'exact original serial frontend resource contract')
 need(d['model_source_contract_repo_path']==MODEL162_SOURCE_CONTRACT_REL and d['model_source_contract_sha256']==MODEL162_SOURCE_CONTRACT_SHA,'actual162 P0 source roles')
 need(d['unchanged_module_contract_sha256']==PRECONDITIONS_SHA and d['host_ports_sha256']==HOST_PORTS_SHA and d['driver_sha256']==DRIVER_SHA,'unchanged15 modules bank subtree typed122 and ordinary driver')
 need(d['matrix_macs']==4096 and d['vector_lanes']==32 and d['tokens']==128 and d['profiles']==list(range(5)) and all(type(v)is int for v in d['profiles']),'one full physical all-five M128 build')
 need(d['numeric_execution_authorized']is False and d['final_rtl_accepted']is False and d['old_artifact_reuse_permitted']is False and d['cpp_build_policy']=='CPP_O1_STRICT_V1','no numerical authority or historical artifact reuse')
 return d

def selected_inputs(repo,name='legacy',first_fault_readonly=False,terminal_finite_readonly=False):
 name=validate_source_selection(name,first_fault_readonly,terminal_finite_readonly);repo=P(repo).resolve()
 if name!=MODEL162_SOURCE:return legacy_gate(repo).selected_inputs(repo,name,first_fault_readonly,terminal_finite_readonly)
 directory=repo/MODEL162_DIR;contract_path=directory/'GENERATION_CONTRACT.json';overlay=directory/'MODEL_SOURCE_OVERLAY.json';contract=load_contract(contract_path,MODEL162_GENERATION_SHA)
 need(sha(regular(repo/MODEL162_PACK_REL))==MODEL162_PACK_SHA,'actual reviewed writer source bytes')
 need(sha(regular(repo/MODEL162_RESOURCE_ADAPTER_REL))==MODEL162_RESOURCE_ADAPTER_SHA,'exact named original-stage resource adapter')
 need(sha(regular(overlay))==MODEL162_OVERLAY_SHA,'exact normalized actual162 source overlay')
 for n,h in [('GENERATION_CONTRACT.json',UPSTREAM_GENERATION_SHA),('MODEL_SOURCE_OVERLAY.json',UPSTREAM_OVERLAY_SHA)]:need(sha(regular(repo/UPSTREAM_DIR/n))==h,'upstream actual hardware source identity')
 return dict(name=name,contract_path=contract_path,contract_sha256=MODEL162_GENERATION_SHA,overlay=overlay,contract=contract)

def checked_paths(repo,overlay,original,contract):
 repo=P(repo).resolve()
 if contract.get('schema')!='MODEL162_GENERATION_CONTRACT_V3':return legacy_gate(repo).checked_paths(repo,overlay,original,contract)
 expected=selected_inputs(repo,MODEL162_SOURCE)
 need(P(overlay)==expected['overlay'] and contract==expected['contract'],'exact selected actual162 input object')
 doc=json.loads(regular(overlay).read_text());up=json.loads(regular(repo/UPSTREAM_DIR/'MODEL_SOURCE_OVERLAY.json').read_text());legacy_path=regular(repo/LEGACY_DIR/'MODEL_SOURCE_OVERLAY.json');need(sha(legacy_path)==LEGACY_OVERLAY_SHA,'legacy159 overlay unchanged')
 prior=json.loads(legacy_path.read_text())['files'];rows=doc['files'];need(doc['schema']=='MODEL162_SOURCE_OVERLAY_V1' and doc['upstream_overlay_repo_path']==UPSTREAM_DIR+'/MODEL_SOURCE_OVERLAY.json' and doc['upstream_overlay_sha256']==UPSTREAM_OVERLAY_SHA and doc['base_overlay_sha256']==LEGACY_OVERLAY_SHA,'explicit adapter transformation provenance')
 need(len(original['sources'])==155 and len(prior)==159 and len(rows)==len(up['files'])==doc['source_count']==162,'fixed original155 legacy159 actual162 counts')
 normalized=[]
 for r in up['files']:
  q=dict(r);root=q.pop('root');need(root in ('candidate','compatibility'),'exact upstream root domain')
  if root=='candidate':q['repo_path']=UPSTREAM_DIR+'/'+q['repo_path']
  normalized.append(q)
 need(rows==normalized,'normalization only, no source replacement')
 names=[r['name']for r in rows];need(names[:159]==[r['name']for r in prior] and names[159:]==up['added_names'] and len(set(names))==162,'fixed source ordering and unique actual helpers')
 changed=[r['name']for r,o in zip(rows,prior)if r['sha256']!=o['sha256']];need(changed==[r['name']for r in up['changes']],'exact ten actual source replacements')
 paths=[]
 for row in rows:
  rel=pathlib.PurePosixPath(row['repo_path']);need(not rel.is_absolute() and '..'not in rel.parts and str(rel)==row['repo_path'] and rel.name==row['name'] and rel.suffix=='.scala','canonical Scala input path')
  p=regular(repo/rel,4<<20);need(type(row['bytes'])is int and p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],'actual162 Scala input bytes');paths.append(str(p))
 helper=repo/UPSTREAM_DIR/'source/DiagnoseOriginalHostMoePhaseV5.scala';need(str(helper)in paths and sha(helper)==up['helper']['candidate_sha256'],'actual compile/elaboration helper selects Chunk32')
 return paths

def require_generation_binding(b):
 if b.get('hardware_source','legacy')!=MODEL162_SOURCE:
  need(b.get('generation_contract_sha256')!=MODEL162_GENERATION_SHA and not str(b.get('fixed_source_overlay','')).endswith('/'+MODEL162_DIR+'/MODEL_SOURCE_OVERLAY.json'),'no implicit actual162 alias')
  return legacy_gate(b['repo']).require_generation_binding(b)
 need(not any(k in b for k in ('first_fault_driver_contract','finite_watchdog_driver','host_profile_driver')),'ordinary model162 numerical driver only')
 repo=P(b['repo']).resolve();s=selected_inputs(repo,MODEL162_SOURCE);d=s['contract']
 need(b['generation_contract']==str(s['contract_path']) and b['generation_contract_sha256']==MODEL162_GENERATION_SHA and b['fixed_source_overlay']==str(s['overlay']),'exact adapter identity binding')
 for field,key in [('generation_contract',None),('fixed_source_overlay','source_overlay_sha256'),('unchanged_module_contract','unchanged_module_contract_sha256'),('host_port_contract','host_ports_sha256'),('driver','driver_sha256'),('model_source_contract','model_source_contract_sha256')]:
  p=regular(b[field]);h=MODEL162_GENERATION_SHA if key is None else d[key];need(sha(p)==h and b['pins'].get(str(p))==h,'independently pinned actual162 input '+field)
 from model162_driver_policy import binding_policy
 binding_policy(b)
 need(b['model_source_contract']==str(repo/MODEL162_SOURCE_CONTRACT_REL),'exact actual162 P0 contract path')
 need(b.get('candidate_status')=='UNREVIEWED_MODEL_BUILD' and b.get('numeric_execution_authorized')is False,'model162 builder never self-admits')
 original=json.loads(regular(repo/'candidates/fresh_original_top_recovery_20261028/SOURCE_AND_TOOLCHAIN_PINS.json').read_text());paths=checked_paths(repo,s['overlay'],original,d)
 required=paths+[str(s['overlay']),str(s['contract_path']),str(repo/UPSTREAM_DIR/'GENERATION_CONTRACT.json'),str(repo/UPSTREAM_DIR/'MODEL_SOURCE_OVERLAY.json'),str(repo/MODEL162_DIR/'candidate_generation_gate.py'),str(repo/MODEL162_RESOURCE_ADAPTER_REL),str(repo/MODEL162_PACK_REL)]
 catalog=regular(repo/MODEL162_CATALOG_REL);need(b['pins'].get(str(catalog))==sha(catalog),'actual same-job catalog pin')
 rows=json.loads(catalog.read_text())['files'];index={r['path']:r for r in rows};need(len(index)==len(rows),'unique source catalog')
 for p in required:
  row=index.get(str(P(p).relative_to(repo)),{});need(b['pins'].get(p)==sha(p)==row.get('sha256') and P(p).stat().st_size==row.get('bytes'),'actual162 complete compile source/catalog closure')
 return d
