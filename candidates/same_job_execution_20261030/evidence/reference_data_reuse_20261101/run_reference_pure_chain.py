"""Actual readonly P0 input reuse and fresh same-root metadata; not live admission.
Executed only by a separately reviewed bounded supervisor. No child processes,
network, DUT, reference arithmetic, or invented stage receipts.
"""
import argparse,hashlib,importlib.util,json,pathlib,shutil,sys,types
P=pathlib.Path
ap=argparse.ArgumentParser()
for name in ('repo','artifact','candidate-review','reuse-binding','startup-abi','output','inspector','reference-reuse-binding'):ap.add_argument('--'+name,type=P,required=True)
for name in ('source-pins','artifact','candidate-review','reuse-binding','startup-abi','inspector','reference-reuse-binding'):ap.add_argument('--'+name+'-sha256',required=True)
a=ap.parse_args()
def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pin(p):return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def checked(path,digest,cap):
 p=path.absolute();need(p==p.resolve()and p.is_file()and all(not q.is_symlink()for q in(p,*p.parents))and 0<p.stat().st_size<=cap,'canonical bounded pinned input');need(sha(p)==digest,'input digest');return p
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def forbid(event,args):
 if event in ('subprocess.Popen','os.system','os.exec','os.posix_spawn','os.spawn')or event.startswith('socket.'):raise RuntimeError('PURE_CHAIN_NO_PROCESS_OR_NETWORK')
sys.addaudithook(forbid)
repo=a.repo.absolute();need(repo==repo.resolve()and all(not q.is_symlink()for q in(repo,*repo.parents)),'canonical source root')
E=repo/'candidates/same_job_execution_20261030';N=E/'numeric';catalog_path=checked(E/'SOURCE_PINS.json',a.source_pins_sha256,2<<20);catalog=json.loads(catalog_path.read_text());need(catalog['schema']=='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1','source catalog')
pins={}
for row in catalog['files']:
 rel=P(row['path']);need(not rel.is_absolute()and '..'not in rel.parts and str(repo/rel)not in pins,'unique source role');p=checked(repo/rel,row['sha256'],32<<20);need(p.stat().st_size==row['bytes'],'source size');pins[str(p)]=row['sha256']
artifact=checked(a.artifact,a.artifact_sha256,65536);review_path=checked(a.candidate_review,a.candidate_review_sha256,2<<20);reuse_path=checked(a.reuse_binding,a.reuse_binding_sha256,2<<20);abi=checked(a.startup_abi,a.startup_abi_sha256,2<<20);inspector_path=checked(a.inspector,a.inspector_sha256,65536)
frozen=json.loads(artifact.read_text());review=json.loads(review_path.read_text());reuse=json.loads(reuse_path.read_text())
need(frozen['schema']=='MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1','candidate artifact');need(reuse['context']['repo']==str(repo)and reuse['context']['artifact_manifest']==pin(artifact),'actual reuse source/artifact context')
out=a.output.absolute();need(out==out.resolve()and not out.exists()and all(not q.is_symlink()for q in(out,*out.parents)),'fresh same-root fixture')
sys.path.insert(0,str(N));provider=load('actual_pure_provider',N/'provider_from_frozen.py');core=load('actual_pure_reuse_core',N/'p0_provider_data_reuse.py');emitter=load('actual_pure_two_root_emitter',N/'emit_reused_p0_tsv.py');connect=load('actual_pure_connect',N/'connect_owned.py');consumer=connect.consumer;observer=load('actual_pure_contract',N/'candidate_observation_contract.py')
verified=core.verify_metadata(pin(reuse_path),reuse['context']);reference=reuse['reference_result'];old_inputroot=P(verified['input_root'])
# Preserve old immutable metadata identities; inputs are full-checked by core twice.
old_metadata_before={row['path']:pin(P(row['path']))for row in reuse['metadata'].values()}
materializer=repo/'candidates/same_job_materialization_20261029'
reference_reuse_path=checked(a.reference_reuse_binding,a.reference_reuse_binding_sha256,2<<20)
reference_context={k:reuse['context'][k]for k in ('repo','artifact_manifest','retained_materials')}
reference_module=provider.reference_reuse_module(pin(N/'reference_data_reuse.py'))
reference_module.verify_metadata(pin(reference_reuse_path),reference_context)
provider.initialize(repo,materializer,out,0,reference,pin(reference_reuse_path),reference_context,pin(N/'reference_data_reuse.py'))
reference_module.verify_materialized(reference,out,0,pin(reference_reuse_path),reference_context)
# Core has already checked these exact twelve raw-weight paths against the
# retained material domain and the independently pinned original provider argv.
payload_roots={str(P(v['data']['path']).parent.parent) for v in reuse['raw_weights'].values()}
need(len(payload_roots)==1,'unique verified original payload root');payload=P(next(iter(payload_roots)))
steps=[]
def stage(name,argv):
 # Direct actual function dispatch, no mocked verifier or pretend supervisor receipt.
 if name=='p0_provider':
  need(argv[1]==str(N/'p0_provider_data_reuse.py'),'fixed reuse executable')
  core.materialize(reuse_path,a.reuse_binding_sha256,out/'p0_provider')
 elif name=='p0_transport':
  need(argv[1]==str(N/'emit_reused_p0_tsv.py'),'fixed emitter executable')
  emitter.run(types.SimpleNamespace(provider=out/'p0_provider',output=out/'p0_transport',payload=payload,reuse_binding=reuse_path,reuse_binding_sha256=a.reuse_binding_sha256))
 else:raise ValueError('unexpected pure stage')
 steps.append(name)
provider.prepare(repo,materializer,out,0,'NO_SUBPROCESS_PURE_FUNCTION_DISPATCH',payload,reference,stage,pins,p0_provider_reuse=pin(reuse_path))
need(steps==['p0_provider','p0_transport'],'one reuse/materialization sequence')
need(not(out/'p0_provider/input_only').exists(),'no duplicate or alias input directory')
source_row=frozen['common']['source_manifest'];source_path=checked(artifact.parent/source_row['path'],source_row['sha256'],16<<20);source=json.loads(source_path.read_text())
context=dict(artifact_manifest=pin(artifact),source_manifest_sha256=source_row['sha256'],candidate_scope=observer.SCOPE,model_candidate_review=pin(review_path),model_source_contract=review['source_contract'],builder_identity=frozen['artifact_identity'],repo=str(repo),current_source_pins_pin=pin(catalog_path),candidate_observation_checker=pin(N/'candidate_observation_contract.py'))
context.update(schema='ADMITTED_CLOUD_P0_SOURCE_RELOCATION_V1',builder_source_commit=frozen['artifact_identity']['source_commit'],artifact_manifest_sha256=a.artifact_sha256,anchors=observer.relocation_records(source,str(repo),pins,catalog,context))
connect.source_guard();old=json.loads((out/'runtime_bundle.json').read_text());connect.base(old,0);args=types.SimpleNamespace(artifact_manifest=artifact);connect.hydrate_p0(args,out,frozen,context)
correction=connect.candidate_contract(context).corrector(context);p=old['profiles'][0];correction.apply(p['runtime']['path'],p['runtime']['sha256'],p['views']['path'],p['views']['sha256'],json.loads(args.p0_bindings.read_text()),out/'p0_observation_correction')
retained=out/'P0_CONSUMPTION_EVIDENCE.json';shutil.copyfile(args.consumption_evidence,retained);result=connect.attach_bundle.assemble(old,pin(out/'p0_observation_correction/OBSERVATION_POLICY.json'),pin(retained))
shutil.copyfile(abi,out/'STARTUP_ABI.json');result['local_runtime_abi']=pin(out/'STARTUP_ABI.json');bundle=out/'runtime_bundle.v3.UNADMITTED.json'
with bundle.open('x')as stream:json.dump(result,stream,indent=2);stream.write('\n')
b,_=consumer.load_binding(artifact,a.artifact_sha256,bundle,0,context);inspector=load('actual_pure_inspector',inspector_path);spans=inspector.inspect(consumer,b,0)
reference_module.verify_materialized(reference,out,0,pin(reference_reuse_path),reference_context)
need(all(pin(P(p))==row for p,row in old_metadata_before.items()),'old provider metadata changed')
for key in ('runtime','views','reference_result','provider_receipt','observation_policy','original_runtime','consumption_evidence'):need(P(result['profiles'][0][key]['path']).is_relative_to(out),'fresh fixture containment')
safe=dict(scope='ACTUAL_INPUT_REUSE_FRESH_SAME_ROOT_PURE_CONNECTION_NOT_LIVE_ADMISSION',status='PURE_REUSE_TO_BINDING_CHECKED',source_catalog_sha256=a.source_pins_sha256,artifact_manifest_sha256=a.artifact_sha256,reuse_binding_sha256=a.reuse_binding_sha256,candidate_review_sha256=a.candidate_review_sha256,bundle_sha256=sha(bundle),fresh_same_materialization_root=True,reference_data_reuse_sha256=a.reference_reuse_binding_sha256,reference_tensors_linked_and_rehashed=True,reference_metadata_fresh=True,program_paths_hand_rebased=False,common_ancestor_workaround=False,readonly_inputs_reused=sum(v['bytes']for v in verified['inputs'].values()),input_files_copied_or_aliased=0,old_metadata_unchanged=True,actual_full_transform_and_raw_probes=True,actual_hydrate_corrector_assemble_load_binding=True,full_final_spans=spans,coverage_acceptance=b['coverage_policy']['coverage_acceptance'],startup_abi_copied_as_historical_bytes_only=True,execution_admitted=False,live_owner_checked=False,resource_admission_checked=False,dut_executed=False,numerical_pass=False)
with (out/'PURE_SAFE_RESULT.json').open('x')as stream:json.dump(safe,stream,indent=2);stream.write('\n')
print(json.dumps(safe))
