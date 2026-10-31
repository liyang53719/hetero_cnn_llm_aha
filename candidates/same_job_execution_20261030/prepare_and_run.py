"""Immutable checked-out source -> actual job binding. No dispatch, no payload upload."""
import argparse,hashlib,importlib.util,json,os,pathlib,platform,shutil,sys,time
P=pathlib.Path;D=P(__file__).resolve().parent
_policy_spec=importlib.util.spec_from_file_location('samejob_profile_policy', P(__file__).resolve().parent/'profile_policy.py');profile_policy=importlib.util.module_from_spec(_policy_spec);_policy_spec.loader.exec_module(profile_policy)
TREE=12_081_306_272
FAILURE_CODES={'original interpreter architecture':'PYTHON_OR_ARCH','P0 original AVX512 contract, no fallback':'CPU_AVX512','original reviewed image only':'IMAGE_VERSION','original maximum frontend RSS12GiB plus1GiB admission':'MEMAVAILABLE_13GIB','full tree plus unchanged free8GiB prerequisite':'DISK_20671240864','immutable complete source closure':'SOURCE_PIN','original first-step deadline':'JOB_DEADLINE'}

def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):
 need(p.stat().st_size<=16<<20,'bounded source metadata');return json.loads(p.read_text())
def run(a):
 # Refuse pending observation baseline before acquisition, owner creation or any stage.
 import importlib.util
 baseline_root=D.parent
 spec=importlib.util.spec_from_file_location('production_observer_baseline',baseline_root/'ci_frontend_pipeline_r2_20261029/observer_baseline_gate.py')
 gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
 gate.require_accepted_baseline(baseline_root/'ci_frontend_materialization_r2_20261029')
 execution_policy=profile_policy.policy(getattr(a,'execution_policy',profile_policy.FULL))
 repo=a.repo.resolve();work=a.work;identity=read(a.identity);clock=read(a.job_start)
 need(str(clock['run_id'])==os.environ['GITHUB_RUN_ID']and os.environ.get('GITHUB_RUN_ATTEMPT')=='1'and clock['launch_commit']==os.environ['GITHUB_SHA'],'first-step clock belongs same first run')
 need(clock['schema']=='SAME_JOB_START_V1'and clock['job_budget_seconds']==21000,'first-step clock schema');started=clock['started_monotonic'];need(type(started)in(int,float)and 0<=time.monotonic()-started<21000,'original first-step deadline')
 need(not work.exists()and work.is_absolute()and not any(p.is_symlink()for p in(work,*work.parents)),'fresh canonical owning tree')
 need(D.is_relative_to(repo),'source package under checked-out repo')
 # Fail before any acquisition/build on inadequate actual resources or CPU.
 need(sys.version_info[:2]==(3,12)and platform.machine()=='x86_64','original interpreter architecture')
 profile_policy.require_cpu({'execution_policy':execution_policy},P('/proc/cpuinfo').read_text().split())
 fresh=None
 if getattr(a,'fresh_host_profile',False):
  fresh=dict(schema='BOUNDED_FRESH_HOST_V1',**{k:identity[k] for k in ('run_id','source_commit','launch_commit')})
 else:need(os.environ.get('ImageVersion')=='20261026.354.1','original reviewed image only')
 memory={line.split(':')[0]:int(line.split()[1])*1024 for line in P('/proc/meminfo').read_text().splitlines()if line.startswith('MemAvailable:')}
 need(memory['MemAvailable']>=13<<30,'original maximum frontend RSS12GiB plus1GiB admission')
 need(shutil.disk_usage(work.parent).free>=TREE+(8<<30),'full tree plus unchanged free8GiB prerequisite')
 source=read(D/'SOURCE_PINS.json');pins={}
 for row in source['files']:
  rel=P(row['path']);need(not rel.is_absolute()and'..'not in rel.parts,'source-relative pins only');p=repo/rel
  need(p.is_file()and not p.is_symlink()and p.stat().st_size==row['bytes']and sha(p)==row['sha256'],'immutable complete source closure');pins[str(p.resolve())]=row['sha256']
 for p in (D/'SOURCE_PINS.json',P(sys.executable).resolve()):pins[str(p)]=sha(p)
 profile_policy.require_source_pin(pins)
 # No inherited local owner/weights/receipts: every material path is NEW in work.
 runtime=D/'runtime';numeric=D/'numeric';controller=D/'controller';pipeline=repo/'candidates/ci_frontend_pipeline_r2_20261029';materialization=repo/'candidates/ci_frontend_materialization_r2_20261029'
 budgets=read(D/'BUDGETS.json')
 b=dict(execution_policy=execution_policy,schema='ONE_JOB_FIVE_M128_CHISEL_TEST_CALIBRATION_V1',profiles=list(range(5)),tokens=128,matrix_macs=4096,vector_lanes=32,payload_uploads=False,final_rtl_replay=False,identity={k:identity[k]for k in('run_id','source_commit','launch_commit')},artifact_identity=identity,job_started_monotonic=started,repo=str(repo),job_root=str(work),pins=pins,runtime_package=str(runtime),numeric_package=str(numeric),python=str(P(sys.executable).resolve()),supervisor_dir=str(pipeline),shared_runtime_helper=str(repo/'candidates/same_job_materialization_20261029/shared_runtime.py'),pipeline=str(pipeline),materialization_dir=str(materialization),materializer=str(repo/'candidates/same_job_materialization_20261029'),dut_rss_bytes=8<<30,numeric_reserved_increment_bytes=512<<20,budgets=budgets)
 if fresh is not None:
  sys.path.insert(0,str(materialization));from fresh_host import validate_contract,reject_injection
  validate_contract(fresh,identity);reject_injection(os.environ);b['fresh_host_contract']=fresh
 binding=work.parent/(work.name+'-BINDING.json')
 with binding.open('x')as f:json.dump(b,f,indent=2);f.write('\n')
 spec=importlib.util.spec_from_file_location('actual_owning_flow',controller/'flow.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.run(b,binding,sha(binding))
if __name__=='__main__':
 p=argparse.ArgumentParser()
 for x in('repo','identity','job-start','work'):p.add_argument('--'+x,type=P,required=True)
 p.add_argument('--execution-policy',choices=(profile_policy.FULL,profile_policy.DEFER),default=profile_policy.FULL)
 p.add_argument('--fresh-host-profile',action='store_true',help='explicit bounded fresh host identity before original build; not CPU waiver')
 a=p.parse_args()
 try:run(a)
 except Exception as e:
  # Deliberately no exception text/path/environment echo into the public summary.
  receipt=a.work.parent/(a.work.name+'-CONTROLLER_FAILURE.json')
  with receipt.open('x')as f:json.dump(dict(execution_policy=profile_policy.policy(a.execution_policy),status='NO_GO_OR_FAILED',exception_class=type(e).__name__,reason_code=FAILURE_CODES.get(str(e),'EXECUTION_FAILED_DETAILS_IN_STAGE_RECEIPTS'),numeric_pass=False),f)
  raise
 raise SystemExit(2) # diagnostic calibration is never numeric PASS
