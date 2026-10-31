"""Real original-provider V1 -> reviewed V3 connection. No DUT or reference math."""
import copy,hashlib,importlib.util,json,os,pathlib,sys
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

def hydrate_p0(args,out,frozen):
 """Retain actual producer text metadata; bind regenerated runtime program paths."""
 source_row=frozen['common']['source_manifest'];source=consumer.pin(dict(source_row,path=str(args.artifact_manifest.resolve().parent/source_row['path'])))
 m=json.loads(source.read_text());embedded=m['p0_retained_evidence'];consumer.need(embedded['schema']=='P0_EMBEDDED_ACTUAL_BUILD_EVIDENCE_V1','actual producer retained evidence required')
 rows={r['path']:r for r in m['files']};anchors=m['observation_policy_bindings']['P0']['anchors'];bindings={}
 for name,key in anchors.items():
  if name in ('program_manifest','commands','descriptors'):
   fn={'program_manifest':'manifest.json','commands':'host_commands.bin','descriptors':'host_descriptors.bin'}[name];bindings[name]=str(out/'p0_provider/program'/fn)
  else:bindings[name]=rows[key]['origin_path']
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
 evidence=dict(schema='P0_RETAINED_PRODUCER_EVIDENCE_V2',files=files,driver_dependency=pin(dependency_path))
 bp=retained/'BINDINGS.json';ep=retained/'EVIDENCE.json'
 for path,doc in ((bp,bindings),(ep,evidence)):
  raw=(json.dumps(doc,indent=2)+'\n').encode();consumer.need(len(raw)<=65536,'bounded P0 bindings/evidence index')
  with path.open('xb')as stream:stream.write(raw)
 args.p0_bindings=bp;args.p0_bindings_sha256=consumer.sha(bp);args.consumption_evidence=ep;args.consumption_evidence_sha256=consumer.sha(ep)

def connect(args,out):
 source_guard();out=P(out).resolve();original=out/'runtime_bundle.json';old_pin=pin(original)
 consumer.need(original.is_file() and not original.is_symlink(),'original fresh bundle required')
 old=json.loads(original.read_text());result=base(old,args.profile)
 consumer.verify_frozen(args.artifact_manifest,args.artifact_manifest_sha256)
 frozen=json.loads(args.artifact_manifest.read_text());consumer.artifact_identity(frozen)
 provenance=consumer.verify_local_build(args,frozen)
 consumer.verify_runtime_abi(args,frozen)
 p0_fields=('p0_bindings','p0_bindings_sha256','consumption_evidence','consumption_evidence_sha256')
 if args.profile==0:
  if all(getattr(args,k,None) is None for k in p0_fields):hydrate_p0(args,out,frozen)
  consumer.need(all(getattr(args,k,None) is not None for k in p0_fields),'P0 requires independently pinned bindings and retained consumption evidence')
  consumer.verify_frozen(args.p0_bindings,args.p0_bindings_sha256)
  consumer.verify_frozen(args.consumption_evidence,args.consumption_evidence_sha256)
  bindings=json.loads(args.p0_bindings.read_text())
  # Locked original corrector validates all12 bytes/roles and exact20->18 delta.
  import correct_observation_policy as correction
  p=old['profiles'][0]
  correction.apply(p['runtime']['path'],p['runtime']['sha256'],p['views']['path'],p['views']['sha256'],bindings,out/'p0_observation_correction')
  policy=out/'p0_observation_correction/OBSERVATION_POLICY.json'
  retained=out/'P0_CONSUMPTION_EVIDENCE.json'
  with retained.open('xb') as f:f.write(args.consumption_evidence.read_bytes())
  consumer.need(consumer.sha(retained)==args.consumption_evidence_sha256,'retained evidence copy')
  result=attach_bundle.assemble(old,pin(policy),pin(retained))
 else:
  consumer.need(all(getattr(args,k,None) is None for k in p0_fields),'P1-P4 cannot request P0 exception')
 abi_copy=out/'STARTUP_ABI.json'
 with abi_copy.open('xb') as f:f.write(args.local_runtime_abi.read_bytes())
 consumer.need(consumer.sha(abi_copy)==args.local_runtime_abi_sha256,'startup ABI retained exact bytes')
 result['local_runtime_abi']=pin(abi_copy)
 final=out/'runtime_bundle.v3.json';staged=out/'runtime_bundle.v3.UNADMITTED.json'
 consumer.need(not final.exists() and not staged.exists(),'fresh V3 metadata only')
 with staged.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
 # Fail closed on missing real source mapping/retained receipts/header evidence.
 consumer.load_binding(args.artifact_manifest,args.artifact_manifest_sha256,staged,args.profile)
 consumer.verify_local_build(args,frozen);consumer.pin(old_pin)
 os.link(staged,final);staged.unlink()
 argv=[sys.executable,str(HERE/'consumer_owned.py'),'--artifact-manifest',str(args.artifact_manifest),'--artifact-manifest-sha256',args.artifact_manifest_sha256,'--expected-run-id',str(args.expected_run_id),'--expected-launch-commit',args.expected_launch_commit,'--expected-source-commit',args.expected_source_commit,'--local-runtime-abi',str(abi_copy),'--local-runtime-abi-sha256',args.local_runtime_abi_sha256,'--owned-environment',str(args.owned_environment),'--owned-environment-sha256',args.owned_environment_sha256,'--runtime-bundle',str(final),'--profile',str(args.profile),'--output',str(out/'dut_result')]
 if consumer.executor_context(args) is None:
  argv+=['--local-build-result',str(args.local_build_result),'--local-build-result-sha256',args.local_build_result_sha256]
 else:
  argv+=['--builder-handoff',str(args.builder_handoff),'--builder-handoff-sha256',args.builder_handoff_sha256,'--executor-identity',str(args.executor_identity),'--executor-identity-sha256',args.executor_identity_sha256]
 argv+=['--strict-outer-supervised']
 receipt=dict(status='MATERIALIZED_AND_BOUND_NOT_DUT_EXECUTED',profile=args.profile,original_bundle=old_pin,runtime_bundle=pin(final),artifact_manifest_sha256=args.artifact_manifest_sha256,provenance=provenance,consumer_argv=argv,validate_only_argv=argv+['--validate-only'],hardware_executed=False,numerical_pass=False,raw_payloads_upload_allowed=False)
 with (out/'CONSUMER_ARGV.json').open('x') as f:json.dump(receipt,f,indent=2);f.write('\n')
 return receipt

def add_arguments(ap):
 ap.add_argument('--owned-environment',type=P,required=True);ap.add_argument('--owned-environment-sha256',required=True)
 ap.add_argument('--artifact-manifest',type=P);ap.add_argument('--artifact-manifest-sha256')
 ap.add_argument('--local-build-result',type=P);ap.add_argument('--local-build-result-sha256')
 ap.add_argument('--builder-handoff',type=P);ap.add_argument('--builder-handoff-sha256')
 ap.add_argument('--executor-identity',type=P);ap.add_argument('--executor-identity-sha256')
 ap.add_argument('--expected-run-id',type=int);ap.add_argument('--expected-launch-commit');ap.add_argument('--expected-source-commit')
 ap.add_argument('--local-runtime-abi',type=P);ap.add_argument('--local-runtime-abi-sha256')
 ap.add_argument('--p0-bindings',type=P);ap.add_argument('--p0-bindings-sha256')
 ap.add_argument('--consumption-evidence',type=P);ap.add_argument('--consumption-evidence-sha256')

def preflight_artifact(args,frozen):
 root=args.artifact_manifest.resolve().parent;identity=consumer.artifact_identity(frozen)
 consumer.need(set(frozen['common'])=={'binary','sv','source_manifest','driver','build_receipt'},'complete common identity')
 paths={}
 for name,row in dict(frozen['common'],tool_manifest=frozen['tool_manifest']).items():
  rel=P(row['path']);consumer.need(not rel.is_absolute() and '..' not in rel.parts and str(rel) not in ('','.'),'relative artifact member')
  full=root/rel;consumer.need(full.resolve().is_relative_to(root),'artifact member escape');paths[name]=consumer.pin(dict(row,path=str(full)))
 consumer.need(frozen['common']['driver']['sha256']==consumer.V3_DRIVER_SHA256,'original V3 driver')
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
 frozen=json.loads(args.artifact_manifest.read_text());preflight_artifact(args,frozen);consumer.verify_local_build(args,frozen);consumer.verify_runtime_abi(args,frozen)
 consumer.need(frozen['profiles']==list(range(5)) and frozen['matrix_macs']==4096 and frozen['vector_lanes']==32,'same complete five-profile hardware')
 if args.profile!=0:consumer.need(all(getattr(args,k,None) is None for k in ('p0_bindings','p0_bindings_sha256','consumption_evidence','consumption_evidence_sha256')),'P1-P4 cannot request P0 exception BEFORE materialization')
 if args.profile==0:
  fields=('p0_bindings','p0_bindings_sha256','consumption_evidence','consumption_evidence_sha256')
  supplied=[getattr(args,k,None)is not None for k in fields];consumer.need(all(supplied) or not any(supplied),'P0 evidence overrides must be complete')
  if all(supplied):
   consumer.verify_frozen(args.p0_bindings,args.p0_bindings_sha256);consumer.verify_frozen(args.consumption_evidence,args.consumption_evidence_sha256)
  source_pin=frozen['common']['source_manifest'];source=args.artifact_manifest.parent/source_pin['path'];consumer.pin(dict(source_pin,path=str(source.resolve())));m=json.loads(source.read_text())
  consumer.need('files' in m and 'P0' in m.get('observation_policy_bindings',{}) and 'p0_retained_evidence' in m,'P0 actual producer mapping absent or retained evidence missing; no expensive prep')

def main():
 import argparse
 ap=argparse.ArgumentParser();ap.add_argument('--existing-output',type=P,required=True);ap.add_argument('--profile',type=int,choices=range(5),required=True);add_arguments(ap);args=ap.parse_args()
 preflight(args);connect(args,args.existing_output)
if __name__=='__main__':main()
