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
def execution_request(a):
 if getattr(a,'gdn32_full_plan',None)is not None:
  path=a.gdn32_full_plan;need(a.gdn32_full_plan_sha256 is not None and sha(path)==a.gdn32_full_plan_sha256,'independently pinned new full model plan')
  need(a.execution_mode=='FULL_BLOCK_ACCEPTANCE'and a.full_block_budget is None,'new full plan never legacy approval')
  return dict(execution_mode='FULL_BLOCK_ACCEPTANCE',gdn32_full=read(path),full_block_budget=None)
 mode=getattr(a,'execution_mode','BOUNDED_CALIBRATION')
 need(mode in ('BOUNDED_CALIBRATION','FULL_BLOCK_ACCEPTANCE'),'explicit execution mode')
 path=getattr(a,'full_block_budget',None);digest=getattr(a,'full_block_budget_sha256',None)
 if mode=='BOUNDED_CALIBRATION':
  need(path is None and digest is None,'full budget not allowed in calibration')
  return dict(execution_mode=mode)
 need(path is not None and digest is not None,'full mode requires explicit reviewed budget')
 import re
 need(isinstance(digest,str)and re.fullmatch('[0-9a-f]{64}',digest),'full budget independent sha256')
 path=P(path)
 need(path.is_file()and all(not q.is_symlink()for q in(path,*path.parents))and path.stat().st_size<=65536,'bounded regular reviewed budget')
 need(sha(path)==digest,'reviewed budget pin')
 return dict(execution_mode=mode,full_block_budget=dict(path=str(path.resolve()),bytes=path.stat().st_size,sha256=digest))

def run(a):
 # Refuse pending observation baseline before acquisition, owner creation or any stage.
 import importlib.util
 baseline_root=D.parent
 spec=importlib.util.spec_from_file_location('production_observer_baseline',baseline_root/'ci_frontend_pipeline_r2_20261029/observer_baseline_gate.py')
 gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
 request=execution_request(a)
 if 'gdn32_full'not in request:gate.require_accepted_baseline(baseline_root/'ci_frontend_materialization_r2_20261029')
 execution_policy=profile_policy.selected_policy(request['gdn32_full']['selected_profiles'])if 'gdn32_full'in request else profile_policy.policy(getattr(a,'execution_policy',profile_policy.FULL))
 repo=a.repo.resolve();work=a.work;identity=read(a.identity);clock=read(a.job_start)
 need(str(clock['run_id'])==os.environ['GITHUB_RUN_ID']and os.environ.get('GITHUB_RUN_ATTEMPT')=='1'and clock['launch_commit']==os.environ['GITHUB_SHA'],'first-step clock belongs same first run')
 need(clock['schema']=='SAME_JOB_START_V1'and clock['job_budget_seconds']==21000,'first-step clock schema');started=clock['started_monotonic'];need(type(started)in(int,float)and 0<=time.monotonic()-started<21000,'original first-step deadline')
 need(not work.exists()and work.is_absolute()and not any(p.is_symlink()for p in(work,*work.parents)),'fresh canonical owning tree')
 need(D.is_relative_to(repo),'source package under checked-out repo')
 # Emit only fixed typed observations before any acquisition/build. No env/path dump.
 if 'gdn32_full'in request:
  mem={line.split(':')[0]:int(line.split()[1])*1024 for line in P('/proc/meminfo').read_text().splitlines()if line.startswith(('MemTotal:','MemAvailable:'))}
  flags=P('/proc/cpuinfo').read_text().split();free=shutil.disk_usage(work.parent).free
  avx_required=0 in request['gdn32_full']['selected_profiles'];avx_present='avx512f'in flags
  code='PYTHON_ABI'if sys.version_info[:2]!=(3,12)or platform.machine()!='x86_64'else'P0_REQUIRES_AVX512'if avx_required and not avx_present else'MEMORY_AVAILABLE'if mem['MemAvailable']<13<<30 else'DISK_FREE'if free<TREE+(8<<30)else'OK'
  print(json.dumps(dict(schema='GDN32_PRE_NATIVE_CAPABILITY_V1',phase='PREPARE',code=code,status='ADMITTED'if code=='OK'else'REFUSED',mem_total_bytes=mem['MemTotal'],mem_available_bytes=mem['MemAvailable'],disk_free_bytes=free,required_memory_bytes=13<<30,required_disk_bytes=TREE+(8<<30),remaining_wall_seconds=int(21000-(time.monotonic()-started)),p0_avx512_required=avx_required,avx512_present=avx_present,native_started=False,dut_started=False),sort_keys=True),flush=True)
  need(code=='OK','GDN32_PRE_NATIVE_'+code)
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
 catalog=P(request['gdn32_full']['source_catalog']['path'])if 'gdn32_full'in request else D/'SOURCE_PINS.json'
 if 'gdn32_full'in request:
  row=request['gdn32_full']['source_catalog'];need(catalog.is_relative_to(repo)and catalog.stat().st_size==row['bytes']and sha(catalog)==row['sha256'],'explicit new full source catalog')
 source=read(catalog);pins={}
 for row in source['files']:
  rel=P(row['path']);need(not rel.is_absolute()and'..'not in rel.parts,'source-relative pins only');p=repo/rel
  need(p.is_file()and not p.is_symlink()and p.stat().st_size==row['bytes']and sha(p)==row['sha256'],'immutable complete source closure');pins[str(p.resolve())]=row['sha256']
 for p in (catalog,P(sys.executable).resolve()):pins[str(p)]=sha(p)
 profile_policy.require_source_pin(pins)
 # No inherited local owner/weights/receipts: every material path is NEW in work.
 runtime=D/'runtime';numeric=D/'numeric';controller=D/'controller';pipeline=repo/'candidates/ci_frontend_pipeline_r2_20261029';materialization=repo/'candidates/ci_frontend_materialization_r2_20261029'
 budgets=read(D/'BUDGETS.json')
 b=dict(execution_policy=execution_policy,schema='ONE_JOB_FIVE_M128_CHISEL_TEST_CALIBRATION_V1',profiles=list(range(5)),tokens=128,matrix_macs=4096,vector_lanes=32,payload_uploads=False,final_rtl_replay=False,identity={k:identity[k]for k in('run_id','source_commit','launch_commit')},artifact_identity=identity,job_started_monotonic=started,repo=str(repo),job_root=str(work),pins=pins,runtime_package=str(runtime),numeric_package=str(numeric),python=str(P(sys.executable).resolve()),supervisor_dir=str(pipeline),shared_runtime_helper=str(repo/'candidates/same_job_materialization_20261029/shared_runtime.py'),pipeline=str(pipeline),materialization_dir=str(materialization),materializer=str(repo/'candidates/same_job_materialization_20261029'),dut_rss_bytes=8<<30,numeric_reserved_increment_bytes=512<<20,budgets=budgets)
 b.update(request)
 if 'gdn32_full'in request:b['schema']='GDN32_FULL_MODEL_SAME_JOB_BINDING_V1'
 spec=importlib.util.spec_from_file_location('samejob_execution_mode',D/'execution_mode.py');mode=importlib.util.module_from_spec(spec);spec.loader.exec_module(mode)
 need(pins.get(str(D/'execution_mode.py'))==sha(D/'execution_mode.py'),'execution mode source pin')
 if 'gdn32_full'in request:
  path=numeric/'samejob_gdn32_full.py';need(pins.get(str(path))==sha(path),'new full bridge independently pinned');spec=importlib.util.spec_from_file_location('actual_gdn32_full_admission',path);full=importlib.util.module_from_spec(spec);spec.loader.exec_module(full);admission=full.admit_controller(b)
 else:admission=mode.admit(b) # no old model authority reused
 spec=importlib.util.spec_from_file_location('actual_owning_flow',controller/'flow.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 if admission['mode']==mode.FULL:
  _,_,total=m.reservations(b,admission)
  if 'gdn32_full'not in request or request['gdn32_full']['lifecycle_policy']=='RESERVE_ALL_CAPS_BEFORE_NATIVE':need(total<=21000-(time.monotonic()-started),'reviewed full round exceeds remaining original deadline')
  else:full.build_window(b,admission,time.monotonic())
 if fresh is not None:
  sys.path.insert(0,str(materialization));from fresh_host import validate_contract,reject_injection
  validate_contract(fresh,identity);reject_injection(os.environ);b['fresh_host_contract']=fresh
 binding=work.parent/(work.name+'-BINDING.json')
 with binding.open('x')as f:json.dump(b,f,indent=2);f.write('\n')
 return m.run(b,binding,sha(binding))
if __name__=='__main__':
 p=argparse.ArgumentParser()
 for x in('repo','identity','job-start','work'):p.add_argument('--'+x,type=P,required=True)
 p.add_argument('--gdn32-full-plan',type=P)
 p.add_argument('--gdn32-full-plan-sha256')
 p.add_argument('--execution-policy',choices=(profile_policy.FULL,profile_policy.DEFER),default=profile_policy.FULL)
 p.add_argument('--execution-mode',choices=('BOUNDED_CALIBRATION','FULL_BLOCK_ACCEPTANCE'),default='BOUNDED_CALIBRATION')
 p.add_argument('--full-block-budget',type=P)
 p.add_argument('--full-block-budget-sha256')
 p.add_argument('--fresh-host-profile',action='store_true',help='explicit bounded fresh host identity before original build; not CPU waiver')
 a=p.parse_args()
 try:transport=run(a)
 except Exception as e:
  # Deliberately no exception text/path/environment echo into the public summary.
  receipt=a.work.parent/(a.work.name+'-CONTROLLER_FAILURE.json')
  with receipt.open('x')as f:json.dump(dict(execution_policy=profile_policy.policy(a.execution_policy),status='NO_GO_OR_FAILED',exception_class=type(e).__name__,reason_code=FAILURE_CODES.get(str(e),'EXECUTION_FAILED_DETAILS_IN_STAGE_RECEIPTS'),numeric_pass=False),f)
  raise
 raise SystemExit(transport) # actual mode and independently recomputed qualification decide transport
