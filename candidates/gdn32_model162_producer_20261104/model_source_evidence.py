"""Record actual candidate P0 source inputs; not a numeric/corrector approval."""
import hashlib,json,pathlib
P=pathlib.Path
SCALA={'helper':'DiagnoseOriginalHostMoePhaseV5.scala','host_top':'HostBlockTopV4.scala','host_commands':'HostBlockCommandsV4.scala','owner_kernel':'QwenOwnerProtocol.scala','qkv_router':'Public21QkvReductionRouter.scala','resident':'FfnResidentCoordinator.scala','bridge':'FfnTileSiluBridge.scala'}
CONTRACT_SHA='7b46242a1206f651e8fac111436b6cb515b6a69f981b6f01c1e1f26bd7f51f13'
# Source-only prefill revision; these pins do not qualify fullTop or authorize execution.
PREFILL_SOURCE='prefill-supply-overlap-v1'
PREFILL_DIR='candidates/prefill_supply_overlap_20261103'
PREFILL_GENERATION_SHA='d6b8f476cb4f586ff47a44d4f2155891f15e3bac99f56e45039c459093feaabb'
PREFILL_OVERLAY_SHA='a43e536bc0d0af808429f0730e4ad5fd6f949f4b4e1deb8194c1518eeacb521b'
PREFILL_CONTRACT_SHA='2cdb20b502877708ab91d054f18b7032573569fafd9121144ca7466c68a0f1bd'
PREFILL_CONTRACT_REL='candidates/same_job_execution_20261030/numeric/MODEL_P0_PREFILL_SUPPLY_SOURCE_CONTRACT.json'
PREFILL_DRIVER_REL='candidates/moe_router_score_observation_20261030/driver/host_axi_driver_non_dpi.cpp'
PREFILL_DRIVER_SHA='343e99786a82fd5e738d3e48667fde204e21c077e397f8d20a4cddd59629bb61'
def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pin(p):
 p=P(p);need(p.is_file()and not any(q.is_symlink()for q in(p,*p.parents)),'actual regular source evidence');return {'path':str(p.resolve()),'bytes':p.stat().st_size,'sha256':sha(p)}
def text_pin(p,cap=2<<20):
 v=pin(p);need(0<v['bytes']<=cap,'bounded source text');v['text']=P(p).read_text();need(hashlib.sha256(v['text'].encode()).hexdigest()==v['sha256'],'exact LF/source text');return v

def prefill_contract(b):
 """Select only the exact ordinary prefill source domain; no legacy aliases."""
 active=(b.get('hardware_source')==PREFILL_SOURCE or b.get('generation_contract_sha256')==PREFILL_GENERATION_SHA or str(b.get('fixed_source_overlay','')).endswith('/'+PREFILL_DIR+'/MODEL_SOURCE_OVERLAY.json') or str(b.get('model_source_contract','')).endswith('/'+PREFILL_CONTRACT_REL))
 if not active:return None
 need(b.get('hardware_source')==PREFILL_SOURCE and 'first_fault_driver_contract'not in b and 'finite_watchdog_driver'not in b,'prefill requires explicit ordinary source selection, no readonly/finite crossover')
 repo=P(b['repo']).resolve()
 from host_profile_policy import binding_policy as profile_binding,CONTRACT_REL as PROFILE_CONTRACT_REL,CONTRACT_SHA as PROFILE_CONTRACT_SHA,DRIVER_REL as PROFILE_DRIVER_REL,DRIVER_SHA as PROFILE_DRIVER_SHA
 profile=profile_binding(b)
 contract_rel,contract_sha,driver_rel,driver_sha=(PROFILE_CONTRACT_REL,PROFILE_CONTRACT_SHA,PROFILE_DRIVER_REL,PROFILE_DRIVER_SHA)if profile is not None else(PREFILL_CONTRACT_REL,PREFILL_CONTRACT_SHA,PREFILL_DRIVER_REL,PREFILL_DRIVER_SHA)
 for field,rel,want in [('generation_contract',PREFILL_DIR+'/GENERATION_CONTRACT.json',PREFILL_GENERATION_SHA),('fixed_source_overlay',PREFILL_DIR+'/MODEL_SOURCE_OVERLAY.json',PREFILL_OVERLAY_SHA),('model_source_contract',contract_rel,contract_sha),('driver',driver_rel,driver_sha)]:
  path=repo/rel;need(b.get(field)==str(path),'exact prefill source path '+field)
  actual=pin(path);need(actual['sha256']==want and b['pins'].get(str(path))==want,'exact pinned prefill input '+field)
 need(b.get('generation_contract_sha256')==PREFILL_GENERATION_SHA,'exact prefill generation selection')
 return contract_sha

def record(original,b,built):
 repo=P(original['repo']).resolve();contract_path=P(original['model_source_contract']);contract_doc=text_pin(contract_path)
 from candidate_generation_gate import MODEL162_SOURCE,MODEL162_SOURCE_CONTRACT_REL,MODEL162_SOURCE_CONTRACT_SHA,require_generation_binding
 actual162=original.get('hardware_source')==MODEL162_SOURCE
 if actual162:
  require_generation_binding(original);require_generation_binding(b)
  need(contract_path==repo/MODEL162_SOURCE_CONTRACT_REL,'exact actual162 source contract path')
 prefill=MODEL162_SOURCE_CONTRACT_SHA if actual162 else prefill_contract(original)
 if prefill is not None and not actual162:need(prefill_contract(b)==prefill,'same original/admitted prefill source contract')
 from first_fault_policy import binding_policy,SOURCE_CONTRACT_SHA,SOURCE_CONTRACT_REPO_PATH
 readonly=binding_policy(original)
 from finite_watchdog_policy import binding_policy as finite_binding,SOURCE_SHA as FINITE_SOURCE_SHA,SOURCE_REL
 finite=finite_binding(original)
 want_contract=prefill if prefill is not None else FINITE_SOURCE_SHA if finite is not None else CONTRACT_SHA if readonly is None else SOURCE_CONTRACT_SHA
 if finite is not None:need(contract_path==repo/SOURCE_REL,'exact finite watchdog source contract')
 if readonly is not None:need(contract_path==repo/SOURCE_CONTRACT_REPO_PATH,'exact readonly P0 source contract path')
 need(original['pins'].get(str(contract_path))==contract_doc['sha256']==want_contract,'independently reviewed candidate P0 contract')
 doc=json.loads(contract_doc['text']);need(doc['schema']==('MODEL_CANDIDATE_P0_OBSERVATION_CONTRACT_V1' if readonly is None else 'MODEL_CANDIDATE_P0_FIRST_FAULT_OBSERVATION_CONTRACT_V1'),'candidate source contract only');contract=doc['sources']
 overlay_path=P(original['fixed_source_overlay']);need(sha(overlay_path)==original['pins'][str(overlay_path)],'actual selected source list');fixed={r['name']:r for r in json.loads(overlay_path.read_text())['files']}
 rows=[];anchors={}
 def row(name,path,role,kind='ACTUAL_BUILD_INPUT'):
  v=pin(path);want=contract[name];need(v['bytes']==want['bytes']and v['sha256']==want['sha256'],'candidate source role '+name)
  need(original['pins'].get(v['path'])==v['sha256'],'role really pinned during generation')
  rel=str(P(v['path']).relative_to(repo));rows.append(dict(path=rel,origin_path=v['path'],bytes=v['bytes'],sha256=v['sha256'],role=role,kind=kind));anchors[name]=rel
 for name,filename in SCALA.items():row(name,repo/fixed[filename]['repo_path'],'MODEL_CANDIDATE_SCALA_INPUT')
 row('driver',original['driver'],'FRONTEND_EXE_DRIVER')
 need(built['phases'][-1]['phase']=='host_link','actual final link');dep=built['phases'][-1]['driver_dependency']
 row('sparse_memory',dep['resolved_sparse_header']['path'],'ACTUAL_GCC_DRIVER_HEADER')
 program=repo/'candidates/p0_newboundary_input_provider_20261028/PROGRAM_MANIFEST.json';row('program_manifest',program,'RUNTIME_PROGRAM_METADATA','RUNTIME_ONLY_CONTRACT');meta=json.loads(program.read_text())
 for name,filename,lo,hi in [('commands','host_commands.bin','commandBase','commandLimit'),('descriptors','host_descriptors.bin','descriptorBase','descriptorLimit')]:
  want=contract[name];need(meta['table_sha256'][filename]==want['sha256']and meta[hi]-meta[lo]==want['bytes'],'original runtime manifest table bytes')
  rel='runtime_contract/P0/'+filename;rows.append(dict(path=rel,bytes=want['bytes'],sha256=want['sha256'],role='RUNTIME_'+name.upper()+'_BYTES',kind='RUNTIME_EXPECTATION_NOT_BUILD_INPUT',derived_from=str(program.relative_to(repo))));anchors[name]=rel
 need(set(anchors)==set(contract),'complete source roles, none omitted')
 return {'schema':'MODEL_CANDIDATE_P0_SOURCE_EVIDENCE_V1' if readonly is None else 'MODEL_CANDIDATE_P0_FIRST_FAULT_SOURCE_EVIDENCE_V1','contract':contract_doc,'files':rows,'anchors':anchors,'program_contract':text_pin(program)}
