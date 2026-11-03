"""Record actual candidate P0 source inputs; not a numeric/corrector approval."""
import hashlib,json,pathlib
P=pathlib.Path
SCALA={'helper':'DiagnoseOriginalHostMoePhaseV5.scala','host_top':'HostBlockTopV4.scala','host_commands':'HostBlockCommandsV4.scala','owner_kernel':'QwenOwnerProtocol.scala','qkv_router':'Public21QkvReductionRouter.scala','resident':'FfnResidentCoordinator.scala','bridge':'FfnTileSiluBridge.scala'}
CONTRACT_SHA='7b46242a1206f651e8fac111436b6cb515b6a69f981b6f01c1e1f26bd7f51f13'
def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pin(p):
 p=P(p);need(p.is_file()and not any(q.is_symlink()for q in(p,*p.parents)),'actual regular source evidence');return {'path':str(p.resolve()),'bytes':p.stat().st_size,'sha256':sha(p)}
def text_pin(p,cap=2<<20):
 v=pin(p);need(0<v['bytes']<=cap,'bounded source text');v['text']=P(p).read_text();need(hashlib.sha256(v['text'].encode()).hexdigest()==v['sha256'],'exact LF/source text');return v

def record(original,b,built):
 repo=P(original['repo']).resolve();contract_path=P(original['model_source_contract']);contract_doc=text_pin(contract_path)
 from first_fault_policy import binding_policy,SOURCE_CONTRACT_SHA,SOURCE_CONTRACT_REPO_PATH
 readonly=binding_policy(original)
 from finite_watchdog_policy import binding_policy as finite_binding,SOURCE_SHA as FINITE_SOURCE_SHA,SOURCE_REL
 finite=finite_binding(original)
 want_contract=FINITE_SOURCE_SHA if finite is not None else CONTRACT_SHA if readonly is None else SOURCE_CONTRACT_SHA
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
