"""Actual closed P0 inputs, pure validators only; no execution authority."""
import pathlib,json,hashlib,importlib.util,sys,shutil,types,resource,argparse
P=pathlib.Path
resource.setrlimit(resource.RLIMIT_AS,(1<<30,1<<30));resource.setrlimit(resource.RLIMIT_CPU,(60,60))
ap=argparse.ArgumentParser()
for key in ('repo','payload','original-material','output','review','startup-abi','inspector','bundle'):ap.add_argument('--'+key,type=P,required=True)
z=ap.parse_args()
ROOT=P.cwd();repo=z.repo.resolve();N=repo/'candidates/same_job_execution_20261030/numeric'
payload=z.payload.resolve();original=z.original_material.resolve();out=z.output.resolve();out.mkdir()
def need(ok,message):
 if not ok:raise ValueError(message)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pin(p):return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def load(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def audit(event,args):
 if event in ('subprocess.Popen','os.system','os.exec','os.posix_spawn','os.spawn')or event.startswith('socket.'):raise RuntimeError('PURE_NO_EXECUTION_OR_NETWORK')
sys.addaudithook(audit)
cp=repo/'candidates/same_job_execution_20261030/SOURCE_PINS.json';catalog=json.loads(cp.read_text());pins={}
for row in catalog['files']:
 p=repo/row['path'];need(p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],'catalog drift');pins[str(p)]=row['sha256']
sys.path.insert(0,str(N));con=load('actual_pure_connect',N/'connect_owned.py');c=con.consumer;con.source_guard();obs=load('actual_pure_observer',N/'candidate_observation_contract.py')
artifact=payload/'frozen_artifact.json';frozen=json.loads(artifact.read_text());sourcepath=payload/'source_manifest.json';source=json.loads(sourcepath.read_text());rp=z.review.resolve();review=json.loads(rp.read_text())
context=dict(artifact_manifest=pin(artifact),source_manifest_sha256=sha(sourcepath),candidate_scope=obs.SCOPE,model_candidate_review=pin(rp),model_source_contract=review['source_contract'],builder_identity=frozen['artifact_identity'],repo=str(repo),current_source_pins_pin=pin(cp),candidate_observation_checker=pin(N/'candidate_observation_contract.py'))
context.update(schema='ADMITTED_CLOUD_P0_SOURCE_RELOCATION_V1',builder_source_commit=frozen['artifact_identity']['source_commit'],artifact_manifest_sha256=sha(artifact),anchors=obs.relocation_records(source,str(repo),pins,catalog,context))
oldpath=original/'runtime_bundle.json';oldpin=pin(oldpath);old=json.loads(oldpath.read_text());con.base(old,0)
program=out/'p0_provider/program';program.mkdir(parents=True)
for name in ('manifest.json','host_commands.bin','host_descriptors.bin'):
 src=original/'p0_provider/program'/name;shutil.copyfile(src,program/name);need(sha(src)==sha(program/name),'copied program drift')
a=types.SimpleNamespace(artifact_manifest=artifact)
con.hydrate_p0(a,out,frozen,context)
# Pure fixture keeps original views and their exact original program paths.
bindings=json.loads(a.p0_bindings.read_text())
for role,name in [('program_manifest','manifest.json'),('commands','host_commands.bin'),('descriptors','host_descriptors.bin')]:
 need(sha(P(bindings[role]))==sha(original/'p0_provider/program'/name),'original program drift')
 bindings[role]=str(original/'p0_provider/program'/name)
a.p0_bindings.write_text(json.dumps(bindings,indent=2)+'\n')
correction=con.candidate_contract(context).corrector(context);p=old['profiles'][0]
correction.apply(p['runtime']['path'],p['runtime']['sha256'],p['views']['path'],p['views']['sha256'],json.loads(a.p0_bindings.read_text()),out/'p0_observation_correction')
retained=out/'P0_CONSUMPTION_EVIDENCE.json';shutil.copyfile(a.consumption_evidence,retained)
result=con.attach_bundle.assemble(old,pin(out/'p0_observation_correction/OBSERVATION_POLICY.json'),pin(retained))
abi=z.startup_abi.resolve();shutil.copyfile(abi,out/'STARTUP_ABI.json');result['local_runtime_abi']=pin(out/'STARTUP_ABI.json')
bundle=z.bundle.absolute();need(not bundle.exists() and not bundle.is_symlink() and bundle==bundle.resolve(),'fresh canonical bundle only')
with bundle.open('x')as stream:stream.write(json.dumps(result,indent=2)+'\n')
b,_=c.load_binding(artifact,sha(artifact),bundle,0,context)
pre=load('pure_inspection',z.inspector.resolve());spans=pre.inspect(c,b,0)
need(pin(oldpath)==oldpin,'original bundle drift')
safe=dict(scope='ACTUAL_INPUT_AND_PROVENANCE_ONLY_NOT_LIVE_ADMISSION',status='PURE_COMPLETE_P0_CONNECTION_CHECKED',source_catalog=pin(cp),artifact_manifest=pin(artifact),model_candidate_review=pin(rp),bundle=pin(bundle),actual_source_roles=len(context['anchors']),full_final_spans=spans,original_bundle_unchanged=True,real_hydrate_corrector_assemble_load_binding=True,pure_fixture_common_ancestor_root_not_production_materialization=True,program_paths_retained_readonly_from_actual_views=True,execution_admitted=False,live_owner_checked=False,resource_admission_checked=False,dut_executed=False,numerical_pass=False)
(out/'SAFE_RESULT.json').write_text(json.dumps(safe,indent=2)+'\n');print(json.dumps(safe))
