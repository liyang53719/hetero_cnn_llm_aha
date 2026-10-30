"""Bounded frontend/Make/single-driver-TU qualification, never archive/link/numerics.
Same first-step whole-job clock; original materializers and native supervisors.
"""
import argparse,hashlib,json,os,pathlib,subprocess,sys,time,shutil,re
D=pathlib.Path(__file__).resolve().parent
def need(x,m):
 if not x:raise ValueError(m)
def sha(p):
 with pathlib.Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 global D
 parent_started=time.monotonic()
 Q=pathlib.Path(__file__).resolve().parent
 a=argparse.ArgumentParser()
 for n in ('repo','identity','job-start','work'):a.add_argument('--'+n,type=pathlib.Path,required=True)
 a.add_argument('--execute-reviewed-once',action='store_true');v=a.parse_args()
 R=v.repo.resolve();P=R/'candidates/ci_frontend_pipeline_r2_20261029';D=R/'candidates/ci_frontend_materialization_r2_20261029';W=v.work
 need(W.is_absolute() and not W.exists() and not any(p.is_symlink() for p in (W,*W.parents)),'fresh canonical owned work root')
 clock=json.loads(v.job_start.read_text())
 need(clock['schema']=='SAME_JOB_START_V1' and clock['job_budget_seconds']==21000,'exact whole-job first-step budget')
 v.job_started_monotonic=clock['started_monotonic']
 need(type(v.job_started_monotonic) in (int,float) and 0<=time.monotonic()-v.job_started_monotonic<21000,'first-step monotonic clock never reset')
 v.artifact_identity=v.identity;v.reviewed_repo_sha=json.loads(v.identity.read_text())['source_commit']
 v.shared_owned_root=W;v.maximum_build_seconds=15780;v.remaining_tail_reserve_seconds=12000+600
 identity=json.loads(v.artifact_identity.read_text())
 need(set(identity)=={'run_id','artifact_name','source_commit','launch_commit','launch_manifest_path','launch_manifest_blob_sha'},'V2 six-field artifact identity')
 need(type(identity['run_id'])is int and identity['run_id']>0 and re.fullmatch('[A-Za-z0-9_.-]{1,128}',identity['artifact_name']),'bounded run/name')
 need(all(re.fullmatch('[0-9a-f]{40}',identity[k]) for k in ('source_commit','launch_commit','launch_manifest_blob_sha')) and re.fullmatch(r'ci_launch/[A-Za-z0-9_.-]+\.json',identity['launch_manifest_path']),'exact V2 commits and launch path')
 need(identity['source_commit']==v.reviewed_repo_sha and identity['source_commit']!=identity['launch_commit'],'distinct checked-out source and launch')
 need(clock['run_id']==identity['run_id'] and clock['launch_commit']==identity['launch_commit'],'clock/source owning identity')
 need(str(identity['run_id'])==os.environ['GITHUB_RUN_ID'] and identity['launch_commit']==os.environ['GITHUB_SHA'] and os.environ['GITHUB_RUN_ATTEMPT']=='1','actual first build run identity')
 event=json.loads(pathlib.Path(os.environ['GITHUB_EVENT_PATH']).read_text())
 need(event.get('before')==identity['source_commit'] and event.get('after')==identity['launch_commit'] and event.get('ref')=='refs/heads/main','actual reviewed two-commit push')
 need(v.execute_reviewed_once and not W.exists(),'explicit mode and fresh work root')
 need(subprocess.check_output(['git','-C',str(R),'rev-parse','HEAD'],text=True).strip()==v.reviewed_repo_sha,'reviewed source commit')
 need(P.is_relative_to(R) and D.is_relative_to(R),'published candidate source under reviewed checkout')
 subprocess.run(['git','-C',str(R),'diff','--quiet','HEAD','--'],check=True)
 # Source closure is reviewed separately from generated observations.
 need(Q.is_relative_to(R),'qualification package belongs source checkout')
 closure=json.loads((Q/'SOURCE_PINS.json').read_text());source_pins={}
 for row in closure['files']:
  rel=pathlib.Path(row['path']);need(not rel.is_absolute() and '..' not in rel.parts,'relative source closure')
  path=R/rel;need(path.is_file() and not path.is_symlink() and path.stat().st_size==row['bytes'] and sha(path)==row['sha256'],'complete reviewed source closure')
  source_pins[str(path.resolve())]=row['sha256']
 import platform
 need(sys.version_info[:2]==(3,12) and platform.machine()=='x86_64','original Python and host architecture')
 available=int(next(x for x in pathlib.Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')).split()[1])*1024
 need(available>=13<<30,'original12GiB frontend plus1GiB memory admission')
 need(shutil.disk_usage(W.parent).free>=12_081_306_272+(8<<30),'original aggregate tree plus8GiB reserve')
 fresh=dict(schema='BOUNDED_FRESH_HOST_V1',**{k:identity[k] for k in ('run_id','source_commit','launch_commit')})
 sys.path.insert(0,str(D));import fresh_host
 fresh_host.validate_contract(fresh,identity);fresh_host.reject_injection(os.environ)
 need(time.monotonic()-parent_started<=300,'bounded initial identity/source/resource validation')
 need(time.monotonic()-v.job_started_monotonic+15780+600<21000,'complete execution and publication reservation')
 parent_started=time.monotonic()
 W.mkdir();
 v.fresh_host_contract=W/'HOST_CONTRACT.json'
 with v.fresh_host_contract.open('x') as f:json.dump(fresh,f);f.write('\n')
 v.fresh_host_contract_sha256=sha(v.fresh_host_contract)
 sys.path.insert(0,str(P));import supervise_multiroot as supervise
 py=str(pathlib.Path('/usr/bin/python3').resolve());gh=str(pathlib.Path('/usr/bin/gh').resolve());java=pathlib.Path(os.environ['JAVA_HOME_21_X64'])/'bin/java'
 env={k:os.environ[k] for k in ['PATH','HOME','ImageVersion','ImageOS','JAVA_HOME_21_X64'] if k in os.environ};env.update(LANG='C.UTF-8',LC_ALL='C.UTF-8',MAKEFLAGS='-j1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
 if fresh is not None:
  env.update({k:os.environ[k] for k in ('GITHUB_RUN_ID','GITHUB_SHA','GITHUB_RUN_ATTEMPT')});env['PATH']='/usr/bin:/bin'
 pins={str(p):sha(p) for root in (P,D) for p in root.iterdir() if p.is_file() and p.suffix in ('.py','.json','.scala','.vlt','.tsv')}
 pins.update(source_pins);pins[str(Q/'SOURCE_PINS.json')]=sha(Q/'SOURCE_PINS.json')
 pins[str(pathlib.Path(__file__).resolve())]=sha(__file__)
 pins.update({py:sha(py),gh:sha(gh),'/usr/bin/dpkg-deb':sha('/usr/bin/dpkg-deb')})
 if fresh is not None:pins[str(v.fresh_host_contract.resolve())]=v.fresh_host_contract_sha256
 restore=R/'candidates/fresh_original_top_recovery_20261028/restore_inputs.py';pins[str(restore)]=sha(restore)
 need(time.monotonic()-parent_started<=300,'bounded bootstrap contract/tool preparation')
 stages=[];started=time.monotonic();fresh_aliases={}
 def parent_failure(phase,reason):
  if fresh is None:return
  try:
   with (W/'FRESH_HOST_PARENT_FAILURE.json').open('x') as f:json.dump(dict(schema='FRESH_HOST_PARENT_FAILURE_V1',status='FAILED',phase=phase,reason=reason,numeric_pass=False),f);f.write('\n')
  except OSError:pass # retain original exception; missing receipt is unobserved
 def check_fresh_aliases():
  try:
   for path,target in fresh_aliases.items():need(str(pathlib.Path(path).resolve(strict=True))==target,'fresh runtime alias drift in bootstrap stage')
  except Exception:
   parent_failure('BOOTSTRAP_ALIAS','RUNTIME_ALIAS_REJECTED');raise
 def stage(name,argv,wall=300,rss=1,token=False):
  check_fresh_aliases()
  need(time.monotonic()-started+wall+30<1800,'bounded bootstrap shared30min budget')
  need(time.monotonic()-started+wall+30<=v.maximum_build_seconds,'each setup stays inside reviewed build budget including cleanup')
  need(time.monotonic()-v.job_started_monotonic+wall+30+v.remaining_tail_reserve_seconds<21000,'same whole job reserves frontend and bounded publication')
  need(shutil.disk_usage(W).free>=1_500_000_000,'disk reserve')
  e=dict(env)
  if token:
   need(bool(os.environ.get('GH_TOKEN')),'existing job actions-read token required');e['GH_TOKEN']=os.environ['GH_TOKEN']
  caps=dict(wall_seconds=wall,cleanup_seconds=30,file_bytes=536870912,tree_bytes=12_081_306_272,log_bytes=16_777_216,raw_log_bytes=33_554_432,max_entries=100000,per_process_as_bytes=4*1024**3,per_process_cpu_seconds=wall,rss_bytes=rss*1024**3,cpu_seconds=wall,extra_watch_roots=[str(W),str(R),str(v.shared_owned_root.resolve())],min_free_disk_bytes=1_500_000_000,watch_tree_bytes=12_081_306_272)
  try:
   r=supervise.execute(argv,str(W/('stage_'+name)),str(W/'bootstrap.lock'),caps,e,pins,resource_gate={'min_available_memory':(rss+1)*1024**3,'min_disk_free':1_500_000_000})
  finally:
   check_fresh_aliases()
  complete=(r.get('native_exit')==0 and not r.get('errors') and r.get('cleanup_proof',{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP' and r.get('log_capture',{}).get('pipe_eof_observed') is True and r.get('log_capture',{}).get('gzip_finalized') is True)
  stages.append(dict(name=name,native_exit=r.get('native_exit'),elapsed_seconds=r.get('elapsed_seconds'),observed_peak_rss=r.get('observed_peak_rss'),error_count=len(r.get('errors') or []),complete=complete));(W/'bootstrap_stages.json').write_text(json.dumps(stages,indent=2)+'\n')
  need(complete,'bootstrap failed '+name)
 fresh_args=[] if fresh is None else ['--fresh-host-contract',str(v.fresh_host_contract),'--fresh-host-contract-sha256',v.fresh_host_contract_sha256]
 stage('jdk',[py,'-B',str(D/'inventory_runner_jdk.py'),'--java-home',str(java.parent.parent),'--output',str(W/'jdk.json'),*fresh_args])
 if fresh is not None:
  stage('compile_tools',[py,'-B',str(P/'inventory_compile_tools.py'),'--output',str(W/'compile-tools.json')])
  try:fresh_host.validate_compile_inventory(json.loads((W/'compile-tools.json').read_text()))
  except Exception:
   parent_failure('GNU_RUNTIME_ADMISSION','GNU_RUNTIME_DEPENDENCIES_UNQUALIFIED');raise
 stage('jars',[py,'-B',str(R/'candidates/fresh_original_top_recovery_20261028/restore_inputs.py'),'--download-jars'],600)
 stage('verilator',[py,'-B',str(D/'materialize_verilator.py'),'--output',str(W/'verilator'),'--execute-reviewed-acquisition'])
 stage('idma',[py,'-B',str(D/'acquire_idma_artifact.py'),'--gh',gh,'--gh-sha256',sha(gh),'--output',str(W/'idma'),'--execute-reviewed-acquisition'],240,token=True)
 stage('matrix',[py,'-B',str(D/'recover_matrix_portable.py'),'--repo',str(R),'--output',str(W/'matrix')])
 if fresh is None:stage('compile_tools',[py,'-B',str(P/'inventory_compile_tools.py'),'--output',str(W/'compile-tools.json')])
 if fresh is not None:
  stage('fresh_host',[py,'-B',str(D/'fresh_host.py'),'--contract',str(v.fresh_host_contract),'--contract-sha256',v.fresh_host_contract_sha256,'--java-home',str(java.parent.parent),'--verilator-root',str(W/'verilator'),'--output',str(W/'fresh-host.json')])
  try:
   host=json.loads((W/'fresh-host.json').read_text());need(host['schema']=='BOUNDED_FRESH_HOST_IDENTITY_V1' and host['contract']==fresh and host['old_pass_transfer']is False,'fresh scoped identity only')
   for path,h in host['pins'].items():need(sha(path)==h,'fresh runtime drift')
   for path,target in host['aliases'].items():need(str(pathlib.Path(path).resolve(strict=True))==target,'fresh runtime alias drift')
   fresh_aliases=dict(host['aliases']);pins.update(host['pins']);pins[str(W/'fresh-host.json')]=sha(W/'fresh-host.json')
  except Exception:
   parent_failure('HOST_RECEIPT_ADMISSION','FRESH_HOST_RECEIPT_REJECTED');raise
 stage('binding',[py,'-B',str(D/'materialize_observer_frontend_binding.py'),'--repo',str(R),'--expected-repo-sha',v.reviewed_repo_sha,'--pipeline',str(P),'--jdk-inventory',str(W/'jdk.json'),'--java',str(java),'--tools',str(W/'verilator'),'--idma',str(W/'idma/extracted/idma_export'),'--matrix',str(W/'matrix'),'--canonical',str(R/'candidates/observer_ir_only_20261030/evidence/run41114764250/observed-canonical.tsv'),'--binding',str(W/'FRONTEND_BINDING.json'),'--output',str(W/'frontend')])
 # This entry owns its own stage-level process groups and aggregate memory budget.
 # Token is intentionally absent. Outer GitHub job timeout bounds all stages.
 parent_started=time.monotonic()
 binding=W/'FRONTEND_BINDING.json';bound=json.loads(binding.read_text());bound['mode']='FRONTEND_ONLY';bound['artifact_identity']=identity
 tool_inventory=json.loads((W/'compile-tools.json').read_text());need(tool_inventory['schema']=='INSTALLED_GNU_BUILD_TOOLS_V1' and tool_inventory['qualification']=='IDENTITY_AND_SUPPORTED_OPTIONS_ONLY_NOT_COMPILE_OR_NUMERICAL_PASS','installed tool identity scope');bound['compile_tools']=tool_inventory['compile_tools'];bound['compile_tool_pins']=tool_inventory['pins'];bound['compile_aliases']=tool_inventory['aliases'];bound['compile_tool_manifest']=str(W/'compile-tools.json');bound['pins'][str(W/'compile-tools.json')]=sha(W/'compile-tools.json');bound['pins'].update(tool_inventory['pins'])
 if fresh is not None:
  bound['fresh_host_identity_manifest']=str(W/'fresh-host.json');bound['pins'].update(host['pins']);bound['pins'][str(W/'fresh-host.json')]=sha(W/'fresh-host.json');bound['fresh_host_aliases']=host['aliases']
 need(v.shared_owned_root.resolve().is_dir() and W.is_relative_to(v.shared_owned_root.resolve()),'same job shared disk ownership');bound['materialized_roots'].append(str(v.shared_owned_root.resolve()))
 # Both clocks are enforced downstream. Inner12000 is not the whole21000 job.
 need(time.monotonic()-v.job_started_monotonic+12000+600<21000,'whole job retains full frontend and publication reservation')
 bound['job_budget_seconds']=12000;bound['whole_job_budget_seconds']=21000;bound['job_started_monotonic']=v.job_started_monotonic
 bound['pins'].update(pins)
 binding.write_text(json.dumps(bound,indent=2)+'\n');binding.with_suffix('.sha256').write_text(sha(binding)+'\n')
 command=[py,'-B',str(P/'frontend_qualify_only.py'),'--binding',str(binding),'--binding-sha256',sha(binding),'--execute-reviewed-once']
 need(time.monotonic()-parent_started<=300,'bounded binding augmentation')
 os.execve(py,command,env)
if __name__=='__main__':main()
