"""Real original-provider V1 -> reviewed V3 connection. No DUT or reference math."""
import copy,hashlib,importlib.util,json,os,pathlib,sys,types
P=pathlib.Path
HERE=P(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import consumer_owned as consumer
import attach_bundle

def pin(p):
 p=P(p).resolve();return dict(path=str(p),bytes=p.stat().st_size,sha256=consumer.sha(p))
def source_guard():
 rows=json.loads((HERE/'CONNECTION_OWNED_SOURCE_PINS.json').read_text())
 for rel,h in rows.items():consumer.need(consumer.sha(HERE/rel)==h,'connection source drift '+rel)
def base(old,profile):
 consumer.need(old['schema']=='SINGLE_PROFILE_RUNTIME_BUNDLE_V1','original materializer V1 only')
 consumer.need(old['hardware_executed'] is False and old['raw_payloads_upload_allowed'] is False,'independent materialization only')
 consumer.need(len(old['profiles'])==1 and old['profiles'][0]['id']==profile,'selected profile only')
 consumer.need(not {'original_runtime','observation_policy','consumption_evidence'}&set(old['profiles'][0]),'no preexisting exception')
 result=copy.deepcopy(old);result['schema']='SINGLE_PROFILE_RUNTIME_BUNDLE_V3';return result

def candidate_contract(context):
 if context is None or ('model_candidate_review'not in context and not consumer.host_context(context) and not consumer.gdn32_context(context)):return None
 first_fault=context.get('candidate_scope')==consumer.FIRST_FAULT_SCOPE
 consumer.need(consumer.gdn32_context(context) or consumer.host_context(context) or first_fault or context.get('candidate_scope')=='MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL','admitted model scope')
 catalog_path=consumer.pin(context['current_source_pins_pin']);consumer.need(catalog_path.stat().st_size<=2<<20,'bounded actual source catalog')
 catalog=json.loads(catalog_path.read_text());consumer.need(catalog['schema']=='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1','current source catalog')
 observer='first_fault_observation_contract.py'if first_fault else'candidate_observation_contract.py'
 relative='candidates/gdn32_first_model_execution_20261104/numeric/'+observer
 rows=[r for r in catalog['files']if r['path']==relative];consumer.need(len(rows)==1,'one candidate observation implementation')
 path=P(context['repo'])/relative;consumer.need(path==HERE/observer and path==path.resolve()and all(not q.is_symlink()for q in(path,*path.parents)),'fixed local candidate observer')
 raw=path.read_bytes();consumer.need(len(raw)==rows[0]['bytes']and hashlib.sha256(raw).hexdigest()==rows[0]['sha256'],'source-pinned candidate observation bytes')
 module=types.ModuleType('p0_admitted_candidate_observation');module.__file__=str(path);exec(compile(raw,str(path),'exec'),module.__dict__)
 module.admitted_context(context);return module

def candidate_hydration_view(manifest,context):
 module=candidate_contract(context)
 if module is None:return manifest
 result=module.source_view(manifest,context)
 actual=manifest['model_candidate_build_evidence']
 consumer.need(actual['schema']=='MODEL_CANDIDATE_ACTUAL_BUILD_EVIDENCE_V1','candidate retained real compilation metadata')
 files={}
 for row in actual['actual_stage_receipts'].values():
  consumer.need(row['path']not in files,'unique actual candidate stage path');files[row['path']]=row
 result['p0_retained_evidence']=dict(result['p0_retained_evidence'],schema='MODEL_CANDIDATE_EMBEDDED_BUILD_EVIDENCE_V1',files=files,driver_dependency=actual['driver_dependency'])
 return result

def hydrate_p0(args,out,frozen,source_relocation=None):
 """Retain actual producer text metadata; bind regenerated runtime program paths."""
 source_row=frozen['common']['source_manifest'];source=consumer.pin(dict(source_row,path=str(args.artifact_manifest.resolve().parent/source_row['path'])))
 m=candidate_hydration_view(json.loads(source.read_text()),source_relocation);embedded=m['p0_retained_evidence'];consumer.need(embedded['schema']==('MODEL_CANDIDATE_EMBEDDED_BUILD_EVIDENCE_V1'if candidate_contract(source_relocation)is not None else'P0_EMBEDDED_ACTUAL_BUILD_EVIDENCE_V1'),'actual producer retained evidence required')
 rows={r['path']:r for r in m['files']};anchors=m['observation_policy_bindings']['P0']['anchors'];bindings={}
 for name,key in anchors.items():
  if name in ('program_manifest','commands','descriptors'):
   fn={'program_manifest':'manifest.json','commands':'host_commands.bin','descriptors':'host_descriptors.bin'}[name];bindings[name]=str(out/'p0_provider/program'/fn)
  else:
   if source_relocation is None:bindings[name]=rows[key]['origin_path']
   else:
    mapped=source_relocation['anchors'][name];consumer.need(mapped['relative_path']==key and mapped['origin_path']==rows[key]['origin_path'],'same admitted original anchor role');bindings[name]=mapped['local']['path']
 retained=out/'p0_retained_build_evidence';retained.mkdir()
 files={}
 for i,(original,v) in enumerate(sorted(embedded['files'].items())):
  raw=v['text'].encode();consumer.need(len(raw)==v['bytes'] and hashlib.sha256(raw).hexdigest()==v['sha256'],'actual embedded retained text hash')
  f=retained/(str(i)+'.json')
  with f.open('xb')as stream:stream.write(raw)
  files[original]=pin(f)
 dependency_path=retained/'DRIVER_DEPENDENCY.json';dependency_raw=(json.dumps(embedded['driver_dependency'],indent=2)+'\n').encode()
 consumer.need(len(dependency_raw)<=2*1024**2,'bounded actual dependency metadata')
 with dependency_path.open('xb')as stream:stream.write(dependency_raw)
 evidence=dict(schema='MODEL_CANDIDATE_RETAINED_PRODUCER_EVIDENCE_V1'if candidate_contract(source_relocation)is not None else'P0_RETAINED_PRODUCER_EVIDENCE_V2',files=files,driver_dependency=pin(dependency_path))
 bp=retained/'BINDINGS.json';ep=retained/'EVIDENCE.json'
 for path,doc in ((bp,bindings),(ep,evidence)):
  raw=(json.dumps(doc,indent=2)+'\n').encode();consumer.need(len(raw)<=65536,'bounded P0 bindings/evidence index')
  with path.open('xb')as stream:stream.write(raw)
 args.p0_bindings=bp;args.p0_bindings_sha256=consumer.sha(bp);args.consumption_evidence=ep;args.consumption_evidence_sha256=consumer.sha(ep)

def connect(args,out):
 source_guard();out=P(out).resolve();original=out/'runtime_bundle.json';old_pin=pin(original)
 consumer.need(original.is_file() and not original.is_symlink(),'original fresh bundle required')
 old=json.loads(original.read_text());result=base(old,args.profile)
 long_admission=consumer.finite_long_connection_admission(args)
 consumer.verify_frozen(args.artifact_manifest,args.artifact_manifest_sha256)
 frozen=json.loads(args.artifact_manifest.read_text())
 if frozen.get('schema')in('MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1',consumer.FIRST_FAULT_SCHEMA):
  source_relocation=consumer.approved_source_relocation(args,frozen)
  consumer.artifact_identity(frozen,source_relocation)
  provenance=consumer.verify_local_build(args,frozen)
 else:
  consumer.artifact_identity(frozen)
  provenance=consumer.verify_local_build(args,frozen)
  source_relocation=consumer.approved_source_relocation(args,frozen)
 consumer.verify_runtime_abi(args,frozen)
 p0_fields=('p0_bindings','p0_bindings_sha256','consumption_evidence','consumption_evidence_sha256')
 if args.profile==0:
  if all(getattr(args,k,None) is None for k in p0_fields):hydrate_p0(args,out,frozen,source_relocation)
  consumer.need(all(getattr(args,k,None) is not None for k in p0_fields),'P0 requires independently pinned bindings and retained consumption evidence')
  consumer.verify_frozen(args.p0_bindings,args.p0_bindings_sha256)
  consumer.verify_frozen(args.consumption_evidence,args.consumption_evidence_sha256)
  bindings=json.loads(args.p0_bindings.read_text())
  # Locked original corrector validates all12 bytes/roles and exact20->18 delta.
  candidate=candidate_contract(source_relocation)
  if candidate is None:
   import correct_observation_policy as correction
  else:correction=candidate.corrector(source_relocation)
  p=old['profiles'][0]
  correction.apply(p['runtime']['path'],p['runtime']['sha256'],p['views']['path'],p['views']['sha256'],bindings,out/'p0_observation_correction')
  policy=out/'p0_observation_correction/OBSERVATION_POLICY.json'
  retained=out/'P0_CONSUMPTION_EVIDENCE.json'
  with retained.open('xb') as f:f.write(args.consumption_evidence.read_bytes())
  consumer.need(consumer.sha(retained)==args.consumption_evidence_sha256,'retained evidence copy')
  result=attach_bundle.assemble(old,pin(policy),pin(retained))
 else:
  consumer.need(all(getattr(args,k,None) is None for k in p0_fields),'P1-P4 cannot request P0 exception')
 if long_admission is not None:
  import provider_from_frozen
  result=provider_from_frozen.finite_long_runtime_metadata(result,long_admission,args.profile,consumer.finite_long_mode())
 abi_copy=out/'STARTUP_ABI.json'
 with abi_copy.open('xb') as f:f.write(args.local_runtime_abi.read_bytes())
 consumer.need(consumer.sha(abi_copy)==args.local_runtime_abi_sha256,'startup ABI retained exact bytes')
 result['local_runtime_abi']=pin(abi_copy)
 final=out/'runtime_bundle.v3.json';staged=out/'runtime_bundle.v3.UNADMITTED.json'
 consumer.need(not final.exists() and not staged.exists(),'fresh V3 metadata only')
 with staged.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
 # Fail closed on missing real source mapping/retained receipts/header evidence.
 consumer.load_binding(args.artifact_manifest,args.artifact_manifest_sha256,staged,args.profile,source_relocation,long_admission)
 consumer.verify_local_build(args,frozen);consumer.pin(old_pin)
 os.link(staged,final);staged.unlink()
 argv=[sys.executable,str(HERE/'consumer_owned.py'),'--artifact-manifest',str(args.artifact_manifest),'--artifact-manifest-sha256',args.artifact_manifest_sha256,'--expected-run-id',str(args.expected_run_id),'--expected-launch-commit',args.expected_launch_commit,'--expected-source-commit',args.expected_source_commit,'--local-runtime-abi',str(abi_copy),'--local-runtime-abi-sha256',args.local_runtime_abi_sha256,'--owned-environment',str(args.owned_environment),'--owned-environment-sha256',args.owned_environment_sha256,'--runtime-bundle',str(final),'--profile',str(args.profile),'--output',str(out/'dut_result')]
 if consumer.executor_context(args) is None:
  argv+=['--local-build-result',str(args.local_build_result),'--local-build-result-sha256',args.local_build_result_sha256]
 else:
  argv+=['--builder-handoff',str(args.builder_handoff),'--builder-handoff-sha256',args.builder_handoff_sha256,'--executor-identity',str(args.executor_identity),'--executor-identity-sha256',args.executor_identity_sha256]
  if getattr(args,'cloud_binding',None)is not None:argv+=['--cloud-binding',str(args.cloud_binding),'--cloud-binding-sha256',args.cloud_binding_sha256]
 if consumer.gdn32_context(source_relocation):argv+=['--samejob-full-binding',str(args.samejob_full_binding),'--samejob-full-binding-sha256',args.samejob_full_binding_sha256]
 if consumer.host_context(source_relocation):argv+=['--execution-mode',consumer.HOST_DIAGNOSTIC_MODE,'--samejob-diagnostic-binding',str(args.samejob_diagnostic_binding),'--samejob-diagnostic-binding-sha256',args.samejob_diagnostic_binding_sha256]
 argv+=['--strict-outer-supervised']
 receipt=dict(status='MATERIALIZED_AND_BOUND_NOT_DUT_EXECUTED',profile=args.profile,original_bundle=old_pin,runtime_bundle=pin(final),artifact_manifest_sha256=args.artifact_manifest_sha256,provenance=provenance,consumer_argv=argv,validate_only_argv=argv+['--validate-only'],hardware_executed=False,numerical_pass=False,raw_payloads_upload_allowed=False)
 if source_relocation is not None:receipt['source_relocation']=source_relocation
 with (out/'CONSUMER_ARGV.json').open('x') as f:json.dump(receipt,f,indent=2);f.write('\n')
 return receipt

def add_arguments(ap):
 ap.add_argument('--owned-environment',type=P,required=True);ap.add_argument('--owned-environment-sha256',required=True)
 ap.add_argument('--artifact-manifest',type=P);ap.add_argument('--artifact-manifest-sha256')
 ap.add_argument('--local-build-result',type=P);ap.add_argument('--local-build-result-sha256')
 ap.add_argument('--builder-handoff',type=P);ap.add_argument('--builder-handoff-sha256')
 ap.add_argument('--executor-identity',type=P);ap.add_argument('--executor-identity-sha256')
 ap.add_argument('--samejob-full-binding',type=P);ap.add_argument('--samejob-full-binding-sha256')
 ap.add_argument('--samejob-diagnostic-binding',type=P);ap.add_argument('--samejob-diagnostic-binding-sha256')
 ap.add_argument('--cloud-binding',type=P);ap.add_argument('--cloud-binding-sha256')
 ap.add_argument('--expected-run-id',type=int);ap.add_argument('--expected-launch-commit');ap.add_argument('--expected-source-commit')
 ap.add_argument('--local-runtime-abi',type=P);ap.add_argument('--local-runtime-abi-sha256')
 ap.add_argument('--p0-bindings',type=P);ap.add_argument('--p0-bindings-sha256')
 ap.add_argument('--consumption-evidence',type=P);ap.add_argument('--consumption-evidence-sha256')

def preflight_artifact(args,frozen,source_relocation=None):
 root=args.artifact_manifest.resolve().parent;identity=consumer.artifact_identity(frozen)if source_relocation is None else consumer.artifact_identity(frozen,source_relocation)
 consumer.need(set(frozen['common'])=={'binary','sv','source_manifest','driver','build_receipt'},'complete common identity')
 paths={}
 for name,row in dict(frozen['common'],tool_manifest=frozen['tool_manifest']).items():
  rel=P(row['path']);consumer.need(not rel.is_absolute() and '..' not in rel.parts and str(rel) not in ('','.'),'relative artifact member')
  full=root/rel;consumer.need(full.resolve().is_relative_to(root),'artifact member escape');paths[name]=consumer.pin(dict(row,path=str(full)))
 if frozen['schema']==consumer.FIRST_FAULT_SCHEMA:
  consumer.need(type(args.profile)is int and args.profile==0,'first fault connection is P0 only');consumer.diagnostic_driver(frozen,source_relocation,frozen['common']['driver'])
 elif consumer.gdn32_context(source_relocation):
  consumer.gdn32_module().admitted_context(source_relocation);consumer.need(frozen['common']['driver']['sha256']==consumer.gdn32_module().DRIVER_SHA,'new ordinary full driver')
 elif consumer.host_context(source_relocation):
  consumer.host_diagnostic_module().admitted_context(source_relocation);consumer.need(args.profile==0 and frozen['common']['driver']['sha256']==consumer.host_diagnostic_module().DRIVER_SHA,'new same-job P0 driver domain')
 else:
  long_admission=consumer.finite_long_connection_admission(args)
  if long_admission is not None:consumer.finite_long_mode().verify_finite_driver(long_admission,frozen['common']['driver']['sha256'],args.artifact_manifest_sha256)
  else:consumer.need(frozen['common']['driver']['sha256']==consumer.V3_DRIVER_SHA256,'original V3 driver')
 receipt=json.loads(paths['build_receipt'].read_text())
 consumer.need(receipt['source_commit']==identity['source_commit'] and receipt['launch_commit']==identity['launch_commit'],'build source/launch')
 consumer.need(receipt['tool_manifest_sha256']==frozen['tool_manifest']['sha256'],'build tool pin')
 consumer.need(receipt['config_only'] is False and receipt['software_arithmetic_substitution'] is False,'real build flags')
 for name in ('binary','sv','source_manifest','driver'):consumer.need(receipt[name+'_sha256']==frozen['common'][name]['sha256'],'build member pin '+name)
 consumer.need(frozen['layer']=='CHISEL_EMITTED_SV_NUMERICAL_BACKEND' and frozen['moe_reference_contract']=='ORIGINAL_TORCH_TOPK_PENDING_SMALL_ID_ACCEPTANCE','unchanged layer/MoE contract')

def preflight(args):
 consumer.OWNED_ENVIRONMENT=(args.owned_environment,args.owned_environment_sha256,consumer.owning_environment_identity(args))
 source_guard()
 for k in ('artifact_manifest','artifact_manifest_sha256','expected_run_id','expected_launch_commit','expected_source_commit','local_runtime_abi','local_runtime_abi_sha256'):consumer.need(getattr(args,k,None) is not None,'required same-job identity '+k)
 consumer.verify_frozen(args.artifact_manifest,args.artifact_manifest_sha256)
 frozen=json.loads(args.artifact_manifest.read_text());source_relocation=None
 if frozen.get('schema')in('MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1',consumer.FIRST_FAULT_SCHEMA):
  source_relocation=consumer.approved_source_relocation(args,frozen)
  preflight_artifact(args,frozen,source_relocation)
 else:preflight_artifact(args,frozen)
 consumer.verify_local_build(args,frozen);consumer.verify_runtime_abi(args,frozen)
 consumer.need(frozen['profiles']==list(range(5)) and frozen['matrix_macs']==4096 and frozen['vector_lanes']==32,'same complete five-profile hardware')
 if args.profile!=0:consumer.need(all(getattr(args,k,None) is None for k in ('p0_bindings','p0_bindings_sha256','consumption_evidence','consumption_evidence_sha256')),'P1-P4 cannot request P0 exception BEFORE materialization')
 if args.profile==0:
  fields=('p0_bindings','p0_bindings_sha256','consumption_evidence','consumption_evidence_sha256')
  supplied=[getattr(args,k,None)is not None for k in fields];consumer.need(all(supplied) or not any(supplied),'P0 evidence overrides must be complete')
  if all(supplied):
   consumer.verify_frozen(args.p0_bindings,args.p0_bindings_sha256);consumer.verify_frozen(args.consumption_evidence,args.consumption_evidence_sha256)
  source_pin=frozen['common']['source_manifest'];source=args.artifact_manifest.parent/source_pin['path'];consumer.pin(dict(source_pin,path=str(source.resolve())));m=json.loads(source.read_text())
  m=candidate_hydration_view(m,source_relocation)
  consumer.need('files' in m and 'P0' in m.get('observation_policy_bindings',{}) and 'p0_retained_evidence' in m,'P0 actual producer mapping absent or retained evidence missing; no expensive prep')
  if source_relocation is None:consumer.approved_source_relocation(args,frozen)

def main():
 import argparse
 ap=argparse.ArgumentParser();ap.add_argument('--existing-output',type=P,required=True);ap.add_argument('--profile',type=int,choices=range(5),required=True);add_arguments(ap);args=ap.parse_args()
 preflight(args);connect(args,args.existing_output)
if __name__=='__main__':main()
