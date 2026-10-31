"""Cloud executor entry from independently pinned existing receipts. Never dispatches CI.
The CLI forms its actual same-process identity only after independently approved
inputs pass; an identity from another shell/PID is not executable authority.
"""
import argparse,hashlib,importlib.util,json,os,pathlib,subprocess,sys,time
P=pathlib.Path;D=P(__file__).resolve().parent

def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(name,p):
 spec=importlib.util.spec_from_file_location(name,p);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def input_pin(path,digest,limit=65536):
 p=P(path);need(p.is_absolute()and p==p.resolve()and all(not x.is_symlink()for x in(p,*p.parents))and p.is_file()and 0<p.stat().st_size<=limit,'bounded regular independently pinned input')
 need(isinstance(digest,str)and len(digest)==64 and all(c in '0123456789abcdef'for c in digest)and sha(p)==digest,'independent input digest')
 return dict(path=str(p),bytes=p.stat().st_size,sha256=digest)
def verify_source(repo):
 repo=P(repo).resolve();need(D.is_relative_to(repo),'executor source inside checked-out repository')
 manifest=D/'SOURCE_PINS.json';need(manifest.is_file()and not manifest.is_symlink()and manifest.stat().st_size<=16<<20,'bounded source closure')
 source=json.loads(manifest.read_text());pins={}
 for row in source['files']:
  rel=P(row['path']);need(not rel.is_absolute()and '..'not in rel.parts,'source-relative pins only');p=repo/rel
  need(p.is_file()and all(not q.is_symlink()for q in(p,*p.parents))and p.stat().st_size==row['bytes']and sha(p)==row['sha256'],'immutable complete executor source closure');pins[str(p)]=row['sha256']
 pins[str(manifest)]=sha(manifest);pins[str(P(sys.executable).resolve())]=sha(P(sys.executable).resolve())
 for name in ('cloud_budget.py','executor_identity.py','execution_mode.py','profile_policy.py','prepare_cloud_execution.py','controller/cloud_flow.py','numeric/artifact_handoff.py'):
  p=D/name;need(pins.get(str(p))==sha(p),'executor source role independently pinned')
 return repo,manifest,pins

def run(a):
 repo,manifest,pins=verify_source(a.repo)
 roles={name:input_pin(getattr(a,name),getattr(a,name+'_sha256'))for name in ('executor_identity','builder_handoff','artifact_manifest','cloud_budget','execution_approval')}
 identity=json.loads(P(roles['executor_identity']['path']).read_text())
 frozen=json.loads(P(roles['artifact_manifest']['path']).read_text())
 policy=load('cloud_profile_policy',D/'profile_policy.py');policy.require_source_pin(pins)
 b=dict(schema='CLOUD_FIVE_M128_EXECUTION_BINDING_V1',execution_context='CLOUD_EXECUTOR_V1',identity=identity,executor_identity=identity,source_pins=dict(path=str(manifest),bytes=manifest.stat().st_size,sha256=sha(manifest)),executor_identity_pin=roles['executor_identity'],builder_handoff=roles['builder_handoff'],artifact_manifest=roles['artifact_manifest'],cloud_budget=roles['cloud_budget'],execution_approval=roles['execution_approval'],artifact_identity=frozen['artifact_identity'],execution_policy=policy.policy(policy.FULL),profiles=list(range(5)),tokens=128,matrix_macs=4096,vector_lanes=32,payload_uploads=False,final_rtl_replay=False,job_started_monotonic=identity['started_monotonic'],repo=str(repo),job_root=str(a.work),pins=pins,runtime_package=str(D/'runtime'),numeric_package=str(D/'numeric'),python=str(P(sys.executable).resolve()),supervisor_dir=str(repo/'candidates/ci_frontend_pipeline_r2_20261029'),shared_runtime_helper=str(repo/'candidates/same_job_materialization_20261029/shared_runtime.py'),materializer=str(repo/'candidates/same_job_materialization_20261029'))
 budget=load('cloud_reviewed_budget',D/'cloud_budget.py').admit(b)
 for key in ('runtime_mode','archive_mode','runtime_reuse_manifest','job_budget_seconds','budgets','dut_rss_bytes','dut_address_space_bytes','numeric_reserved_increment_bytes','reserved_other_owner_bytes','consumer_address_space_bytes','stage_resources','execution_mode','full_block_budget'):b[key]=budget[key]
 b['calibration_seconds']=b['budgets']['calibration_seconds']
 flow=load('cloud_real_flow',D/'controller/cloud_flow.py')
 flow.admitted_inputs(b) # budget+current controller+actual imported artifact before any output
 mode=flow.execution_admission(b);flow.reservations(b,mode)
 work=P(a.work);need(work.is_absolute()and not work.exists()and all(not x.is_symlink()for x in(work,*work.parents)),'fresh canonical execution work')
 binding=work.parent/(work.name+'-CLOUD_BINDING.json')
 with binding.open('x')as f:json.dump(b,f,indent=2);f.write('\n')
 return flow.run(b,binding,sha(binding))

def prepare_identity(a):
 supplied=getattr(a,'executor_identity',None);digest=getattr(a,'executor_identity_sha256',None)
 if supplied is not None or digest is not None:
  need(supplied is not None and digest is not None,'paired explicit executor identity pin');return
 repo,manifest,pins=verify_source(a.repo)
 host=input_pin(a.host_identity,a.host_identity_sha256)
 roles={name:input_pin(getattr(a,name),getattr(a,name+'_sha256'))for name in ('builder_handoff','artifact_manifest','cloud_budget','execution_approval')}
 approval=json.loads(P(roles['execution_approval']['path']).read_text())
 stat=P('/proc/self/stat').read_text().rsplit(')',1)[1].split()
 identity=dict(schema='CLOUD_EXECUTOR_IDENTITY_V1',source_commit=approval['source_commit'],execution_id=approval['execution_id'],host_identity_sha256=host['sha256'],boot_id=P('/proc/sys/kernel/random/boot_id').read_text().strip(),controller_pid=os.getpid(),start_tick=int(stat[19]),started_monotonic=time.monotonic())
 # This externally supplied approval SHA, not a generated JSON flag, is authority.
 policy=load('cloud_identity_policy',D/'profile_policy.py');policy.require_source_pin(pins)
 stub=dict(execution_context='CLOUD_EXECUTOR_V1',identity=identity,execution_policy=policy.policy(policy.FULL),pins=pins,**roles)
 budget_module=load('cloud_identity_budget',D/'cloud_budget.py');admitted=budget_module.admit(stub)
 budget_document=json.loads(P(roles['cloud_budget']['path']).read_text())
 budget_module.verify_host(budget_document['host_identity'],identity)
 stub.update(admitted)
 load('cloud_identity_live',D/'executor_identity.py').verify_current(identity)
 need(subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()==identity['source_commit'],'actual immutable executor source commit')
 mode=load('cloud_identity_mode',D/'execution_mode.py').admit(stub)
 _,_,total=load('cloud_identity_flow',D/'controller/cloud_flow.py').reservations(stub,mode)
 frozen=json.loads(P(roles['artifact_manifest']['path']).read_text())
 imported=load('cloud_identity_handoff',D/'numeric/artifact_handoff.py').verify(roles['builder_handoff']['path'],roles['builder_handoff']['sha256'],roles['artifact_manifest']['path'],roles['artifact_manifest']['sha256'],frozen,identity)
 need(imported['source_pins_sha256']==sha(manifest),'reviewed imported source closure')
 need(time.monotonic()-identity['started_monotonic']+total<=admitted['job_budget_seconds'],'actual remaining cloud deadline before identity publication')
 work=P(a.work);need(work.is_absolute()and not work.exists()and all(not p.is_symlink()for p in(work,*work.parents)),'fresh canonical executor work')
 target=work.parent/(work.name+'-EXECUTOR_IDENTITY.json')
 with target.open('x')as f:json.dump(identity,f,indent=2);f.write('\n')
 a.executor_identity=target;a.executor_identity_sha256=sha(target)

def main():
 p=argparse.ArgumentParser()
 p.add_argument('--repo',type=P,required=True);p.add_argument('--work',type=P,required=True)
 for role in ('builder-handoff','artifact-manifest','cloud-budget','execution-approval'):
  p.add_argument('--'+role,type=P,required=True);p.add_argument('--'+role+'-sha256',required=True)
 for role in ('executor-identity','host-identity'):
  p.add_argument('--'+role,type=P);p.add_argument('--'+role+'-sha256')
 a=p.parse_args()
 if a.executor_identity is None:need(a.host_identity is not None and a.host_identity_sha256 is not None,'reviewed host pin required to form current executor identity')
 prepare_identity(a);return run(a)
if __name__=='__main__':raise SystemExit(main())
