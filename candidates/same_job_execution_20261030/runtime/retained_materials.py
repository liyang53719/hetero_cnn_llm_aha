"""Revalidate retained data/software-reference bytes, never old runtime liveness.
The manifest pin is an independently approved invocation input. No subprocess,
installation, acquisition, import smoke, tensor arithmetic or numerical DUT PASS.
"""
import hashlib,importlib.util,json,pathlib,re
P=pathlib.Path;D=P(__file__).resolve().parent
SCOPE='REVALIDATED_DATA_AND_SOFTWARE_REFERENCES_NOT_RUNTIME_OR_DUT'
TOTAL_BYTES=3_531_306_272
MODELS=('qwen2_1p5b','qwen3_5_0p8b','qwen3_5_0p8b','qwen3_5_35b_a3b','qwen3_5_35b_a3b')
KEYS=('qwen2','qwen35_08b','qwen35_08b','qwen35_35b','qwen35_35b')
PREFIXES=('candidates/five_profile_acquisition_resume_20261028/','candidates/five_profile_input_recovery_20261028/','candidates/independent_reference_p0_cache_arm_20261028T2313/','candidates/independent_block_reference_prepare_v3_20261028T2312/','config/upstream/weight_headers/')
EXACT=('candidates/same_job_execution_20261030/runtime/reference_job.py','candidates/same_job_execution_20261030/runtime/reference_phase.py')
def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def regular(p,cap):
 p=P(p);need(p.is_absolute()and p==p.resolve()and all(not q.is_symlink()for q in(p,*p.parents))and p.is_file()and 0<p.stat().st_size<=cap,'canonical bounded retained file');return p
def checked(row,cap=2<<20):
 need(type(row)is dict and set(row)=={'path','bytes','sha256'}and type(row['bytes'])is int and 0<row['bytes']<=cap and type(row['sha256'])is str and re.fullmatch('[0-9a-f]{64}',row['sha256']),'exact retained file pin')
 p=regular(row['path'],cap);need(p.stat().st_size==row['bytes']and sha(p)==row['sha256'],'retained bytes drift');return p
def read(row,cap=2<<20):return json.loads(checked(row,cap).read_text())
def at(row,path,cap=2<<20):
 need(P(row['path'])==path,'fixed original material path');return read(row,cap)
def strict(row,argv):
 need(type(row['native_exit'])is int and row['native_exit']==0 and row['errors']==[] and row['argv']==list(map(str,argv)),'original exact invocation native success')
 need((row.get('cleanup_proof')or{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'and(row.get('log_capture')or{}).get('pipe_eof_observed')is True and(row.get('log_capture')or{}).get('gzip_finalized')is True,'original strict cleanup and complete capture')
def source(relative,old,b):
 op=P(old['repo'])/relative;np=P(b['repo'])/relative
 need(str(op)in old['pins']and old['pins'][str(op)]==b['pins'].get(str(np)),'unchanged original material source/config')
 need(sha(regular(op,32<<20))==old['pins'][str(op)]and sha(regular(np,32<<20))==old['pins'][str(op)],'actual original and current source bytes')
 return op
def material_artifact_identity(old,b):
 # Python references and original tensors are data, not a cached ELF result.
 # A different executable/build receipt may reuse them only for the exact same
 # frozen SV and driver bytes. This is NOT compiler/ABI/DUT admission: the new
 # independently pinned handoff, live owner and full numerical gates still run.
 before=old['artifact_manifest'];after=b['artifact_manifest']
 if before['sha256']==after['sha256']:return
 docs=[]
 for row in (before,after):
  path=checked(row,65536);need(path.name=='frozen_artifact.json','fixed retained hardware manifest filename');doc=json.loads(path.read_text())
  need(doc['schema']=='FROZEN_FIVE_PROFILE_DUT_ARTIFACT_V2'and doc['profiles']==list(range(5))and all(type(x)is int for x in doc['profiles'])and type(doc['matrix_macs'])is int and doc['matrix_macs']==4096 and type(doc['vector_lanes'])is int and doc['vector_lanes']==32,'same complete fixed hardware definition for material reuse')
  need(doc['layer']=='CHISEL_EMITTED_SV_NUMERICAL_BACKEND'and doc['moe_reference_contract']=='ORIGINAL_TORCH_TOPK_PENDING_SMALL_ID_ACCEPTANCE','same frozen material interpretation and original routing contract')
  files={}
  for role,name in (('sv','hardware.sv'),('driver','driver.cpp')):
   value=doc['common'][role];need(type(value)is dict and set(value)=={'path','bytes','sha256'}and value['path']==name,'fixed common source role for material reuse')
   actual=dict(value,path=str(path.parent/name));checked(actual,1<<30);files[role]={k:value[k]for k in ('bytes','sha256')}
  docs.append(files)
 need(docs[0]==docs[1],'recompiled binary may not change actual frozen SV or driver')
 checked(before,65536);checked(after,65536)
 return str(P(before['path']).parent)

def verify(manifest_pin,b):
 d=read(manifest_pin,1<<20)
 need(set(d)=={'schema','scope','old_controller_binding','old_executor_identity','weights_summary','weights_outer','references_manifest','weights','references','numerical_pass'}and d['schema']=='RETAINED_M128_MATERIALS_V1'and d['scope']==SCOPE and d['numerical_pass']is False,'retained material scope only')
 old=read(d['old_controller_binding']);ident=read(d['old_executor_identity'],65536)
 identity_path=D.parent/'executor_identity.py';need(b['pins'].get(str(identity_path))==sha(identity_path),'current identity validator source pin')
 spec=importlib.util.spec_from_file_location('retained_identity_shape',identity_path);identity=importlib.util.module_from_spec(spec);spec.loader.exec_module(identity)
 identity.validate(ident) # Deliberately NOT verify_owner/current: original controller is finished.
 need(old['identity']==ident and old['executor_identity']==ident and old['executor_identity_pin']==d['old_executor_identity'],'original controller/executor immutable join')
 need(old['execution_context']=='CLOUD_EXECUTOR_V1'and old['profiles']==list(range(5))and old['tokens']==128 and old['matrix_macs']==4096,'original full five M128 inputs')
 need(b['identity']['execution_id']!=ident['execution_id']and b['identity']!=ident,'new execution cannot impersonate old owner')
 previous_artifact_root=material_artifact_identity(old,b)
 job=P(old['job_root']);need(job.is_absolute()and job==job.resolve()and job.is_dir()and all(not p.is_symlink()for p in(job,*job.parents)),'canonical original job')
 need(P(d['old_controller_binding']['path'])==P(str(job)+'-CLOUD_BINDING.json')and P(d['old_executor_identity']['path'])==P(str(job)+'-EXECUTOR_IDENTITY.json'),'fixed original controller records')
 # Complete unchanged material-producing source/config subset of the original
 # source closure, not merely the leaf script's claimed hash.
 catalog=read(old['source_pins']);need(catalog['schema']=='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1','original source catalog')
 selected=[]
 for row in catalog['files']:
  name=row['path']
  if name.startswith(PREFIXES)or name in EXACT:
   need(not P(name).is_absolute()and '..'not in P(name).parts,'source relative path')
   p=source(name,old,b);need(p.stat().st_size==row['bytes']and sha(p)==row['sha256'],'historical source catalog exact');selected.append(name)
 need(all(x in selected for x in EXACT)and len(selected)==len(set(selected)),'complete original reference controller sources')
 payload=job/'runs/weights/output';acq=source('candidates/five_profile_acquisition_resume_20261028/acquire_resumable.py',old,b)
 strict(at(d['weights_outer'],job/'runs/weights/RESULT.json'),[old['python'],'-B',acq,'--output',payload,'--execute'])
 summary=at(d['weights_summary'],payload/'SUMMARY.json')
 need(summary['status']=='ACQUIRED_70_ORIGINAL_TENSORS_ONLY'and type(summary['tensors'])is int and summary['tensors']==70 and summary['tensor_bytes']==TOTAL_BYTES and summary['reference_executed']is False and summary['dut_executed']is False,'complete original acquisition only')
 need(type(d['weights'])is list and len(d['weights'])==70,'exact70 retained tensors')
 weights=[];seen=set();receipts=set()
 for item in d['weights']:
  need(type(item)is dict and set(item)=={'file','receipt'},'exact tensor manifest row')
  rp=checked(item['receipt'],65536);need(rp.parent.parent==payload and rp.parent.name in set(MODELS) and rp.name.endswith('.receipt.json')and rp not in receipts,'unique fixed weight receipt');receipts.add(rp)
  r=json.loads(rp.read_text());p=checked(item['file'],2<<30)
  need(p==rp.with_name(rp.name.removesuffix('.receipt.json')+'.bin')and p not in seen,'unique exact weight binary');seen.add(p)
  need(r['status']=='ACQUIRED_ORIGINAL_TENSOR_BYTES_ONLY_NOT_REFERENCE_OR_DUT'and r['actual_bytes']==item['file']['bytes']and r['actual_sha256']==item['file']['sha256']and r['bytes']==r['actual_bytes'],'actual original tensor digest')
  need(r['model']==rp.parent.name and r['name']==rp.name.removesuffix('.receipt.json')and r['file']==str(p.relative_to(payload)),'original weight naming contract')
  weights.append(dict(model=r['model'],name=r['name'],pin=item['file']))
 need(sum(w['pin']['bytes']for w in weights)==TOTAL_BYTES and receipts==set(payload.glob('*/*.receipt.json'))and seen=={p for p in payload.glob('*/*.bin')if p.parent.name!='headers'},'all original70 weight inventory no omission')
 refs=at(d['references_manifest'],job/'materials/references/REFERENCES.json')
 need(refs['identity']==ident and refs['execution_policy']==old['execution_policy']and refs['scope']=='REGISTERED_FIVE_ELIGIBLE_SOFTWARE_REFERENCES_NOT_DUT'and set(refs['references'])==set(d['references'])==set(map(str,range(5))),'all five original software references')
 runtime=read(old['runtime_reuse_manifest'],65536);need(runtime['source_commit']==ident['source_commit'],'original runtime provenance source')
 result={}
 for i in range(5):
  item=d['references'][str(i)];need(type(item)is dict and set(item)=={'result','phase','outer'},'exact reference metadata row')
  home=job/f'materials/references/profile{i}';dest=home/'actual/reference'
  need(item['result']==refs['references'][str(i)],'reference index result pin')
  phase=at(item['phase'],home/'PHASE.json');doc=at(item['result'],dest/'RESULT.json')
  rel='candidates/'+('independent_reference_p0_cache_arm_20261028T2313'if i==0 else'independent_block_reference_prepare_v3_20261028T2312')+'/run_reference.py';src=source(rel,old,b)
  config=source('config/upstream/weight_headers/'+MODELS[i]+'/config.json',old,b);rt=runtime['entries'][KEYS[i]]
  for key in ('wrapper','installation','sidecar'):checked(rt[key],2<<20)
  args=[str(src),'--profile',str(i),'--payload',str(payload),'--config',str(config),'--runtime-receipt',rt['installation']['path'],'--runtime-receipt-sha256',rt['installation']['sha256'],'--runtime-source-pins',rt['sidecar']['path'],'--runtime-source-pins-sha256',rt['sidecar']['sha256'],'--output',str(dest),'--execute-reviewed']
  need(set(phase)=={'argv','source_sha256'}and phase['argv']==args and phase['source_sha256']==sha(src),'exact original reference source and argv')
  strict(at(item['outer'],home/'actual/RESULT.json'),[rt['wrapper']['path'],str(P(old['runtime_package'])/'reference_phase.py'),'--binding',home/'PHASE.json','--sha256',item['phase']['sha256']])
  need(P(old['runtime_package'])==P(old['repo'])/'candidates/same_job_execution_20261030/runtime','fixed original phase wrapper source')
  need(doc['status']=='CAPTURED_FRESH_OFFICIAL_FULL_BLOCK_REFERENCE_ONLY'and type(doc['profile']['profile'])is int and doc['profile']['profile']==i and doc['profile']['model']==MODELS[i]and doc['profile']['layer']==(3 if i in(2,4)else 0),'original complete block reference profile')
  need(doc['complete_block_tokens']==128 and doc['exact_baseline_observer_output_equal']is True and doc['hardware_executed']is False and doc['router_policy']=='UNMODIFIED_OFFICIAL_TORCH_TOPK'and doc['runtime_receipt_sha256']==rt['installation']['sha256']and doc['runtime_source_pins_sha256']==rt['sidecar']['sha256'],'unaltered independent numerical reference contract')
  need(doc['profile']['config_sha256']==sha(config)and type(doc['tensor_records'])is dict and doc['tensor_records'],'reference config/tensor set')
  tensor_files=set()
  for row in doc['tensor_records'].values():
   name=row['file'];need(type(name)is str and not P(name).is_absolute()and '..'not in P(name).parts and str(P(name))==name,'relative reference tensor')
   p=checked(dict(path=str(dest/name),bytes=row['bytes'],sha256=row['sha256']),2<<30);need(p.is_relative_to(dest)and p not in tensor_files,'unique in-reference tensor');tensor_files.add(p)
  result[str(i)]=item['result']
 # Input metadata is rechecked after streaming all retained payloads.
 checked(manifest_pin,1<<20);checked(d['old_controller_binding']);checked(d['old_executor_identity'],65536)
 return dict(payload=str(payload),weights=weights,references=result,roots=[str(job),str(P(d['old_controller_binding']['path']).parent)]+([previous_artifact_root]if previous_artifact_root is not None else[]),scope=SCOPE)
