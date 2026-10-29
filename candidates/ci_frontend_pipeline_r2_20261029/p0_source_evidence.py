"""Enrich NEW source manifest after real build; preserve original prebuild ledger.
Only bounded text receipts/overlay/depfile; no binary, weights or tensor payloads.
"""
import json,pathlib,hashlib
from driver_dependency_proof import need,sha,pin,text_pin,check_text
P=pathlib.Path
SCALA={'helper':'DiagnoseOriginalHostMoePhaseV5.scala','host_top':'HostBlockTopV4.scala','host_commands':'HostBlockCommandsV4.scala','owner_kernel':'QwenOwnerProtocol.scala','qkv_router':'Public21QkvReductionRouter.scala','resident':'FfnResidentCoordinator.scala','bridge':'FfnTileSiluBridge.scala'}
CONTRACT_SHA='9a0a4e8e7acb477b48e90afe0fc545d971f9fbaa87cf6586fe090f6f344c41f0'
CORRECTOR_SHA='3e205b979194d82fc215a1f8c013eff6e009ef79444d05cb20f857db56de3c1d'
def enrich(original,b,built):
 old=text_pin(b['source_manifest'],16*1024**2);m=json.loads(old['text']);repo=P(original['repo']).resolve()
 contract_path=repo/'candidates/same_job_materialization_20261029/consumer/LOCKED_SOURCE_CONTRACT.json';program=repo/'candidates/p0_newboundary_input_provider_20261028/PROGRAM_MANIFEST.json'
 need(original['pins'].get(str(contract_path))==sha(contract_path)==CONTRACT_SHA,'original independently pinned P0 contract')
 contract=json.loads(contract_path.read_text())['sources'];need(original['pins'].get(str(program))==sha(program)==contract['program_manifest']['sha256'],'original independently pinned runtime manifest')
 overlay_path=m['fixed_source_overlay'];overlay=text_pin(overlay_path);need(overlay['sha256']==m['generation_input_pins'][overlay_path],'original overlay generation pin')
 fixed={r['name']:r for r in json.loads(overlay['text'])['files']};records=[];anchors={}
 def row(name,path,role,kind='ACTUAL_BUILD_INPUT'):
  v=pin(path);want=contract[name];need(v['bytes']==want['bytes'] and v['sha256']==want['sha256'],'locked role '+name)
  rel=str(P(path).resolve().relative_to(repo));records.append(dict(path=rel,origin_path=str(P(path).resolve()),bytes=v['bytes'],sha256=v['sha256'],role=role,kind=kind));anchors[name]=rel
 for name,filename in SCALA.items():row(name,repo/fixed[filename]['repo_path'],'FIXED155_SCALA_INPUT')
 row('driver',original['driver'],'FRONTEND_EXE_DRIVER')
 need(built['phases'][-1]['phase']=='host_link','actual final host link phase')
 dep=built['phases'][-1]['driver_dependency']
 need(len((json.dumps(dep,indent=2)+'\n').encode())<=2*1024**2,'bounded retained driver dependency metadata')
 for key in ('depfile','object','host_make','host_hierarchy','global_make','resolved_sparse_header','binary'):
  value=dep[key];need(pin(value['path'])=={k:value[k]for k in ('path','bytes','sha256')},'captured driver evidence drift '+key)
 for path,value in dep['dependencies'].items():need(pin(path)==value,'captured non-system dependency drift')
 row('sparse_memory',dep['resolved_sparse_header']['path'],'ACTUAL_GCC_DRIVER_HEADER')
 row('program_manifest',program,'RUNTIME_PROGRAM_METADATA','RUNTIME_ONLY_CONTRACT')
 meta=json.loads(program.read_text())
 for name,filename,lo,hi in [('commands','host_commands.bin','commandBase','commandLimit'),('descriptors','host_descriptors.bin','descriptorBase','descriptorLimit')]:
  want=contract[name];need(meta['table_sha256'][filename]==want['sha256'] and meta[hi]-meta[lo]==want['bytes'],'actual runtime manifest table pin')
  rel='runtime_contract/P0/'+filename;records.append(dict(path=rel,bytes=want['bytes'],sha256=want['sha256'],role='RUNTIME_'+name.upper()+'_BYTES',kind='RUNTIME_EXPECTATION_NOT_BUILD_INPUT',derived_from=str(program.relative_to(repo))));anchors[name]=rel
 retained={overlay_path:overlay}
 for stage in ('compile155','original_high'):
  candidates=[p for p in m['verified_gate_pins']if P(p).name=='RESULT.json' and P(p).parent.name==stage];need(len(candidates)==1,'actual unique retained '+stage)
  path=candidates[0];v=text_pin(path);need(v['sha256']==m['verified_gate_pins'][path],'actual stage pin');retained[path]=v
 m['files']=records
 m['observation_policy_bindings']={'P0':dict(schema='P0_RESIDENT_OBSERVATION_SOURCE_LINK_V2',contract_sha256=CONTRACT_SHA,corrector_sha256=CORRECTOR_SHA,anchors=anchors)}
 m['p0_retained_evidence']=dict(schema='P0_EMBEDDED_ACTUAL_BUILD_EVIDENCE_V1',original_source_manifest=old,files=retained,driver_dependency=dep,program_contract=text_pin(program))
 return m
