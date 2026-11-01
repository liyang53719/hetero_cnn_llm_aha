"""NEW BUILD_ONLY bootstrap to actual archive/link; unpublished and not executed.
Uses concrete audited materializers. No workflow dispatch, cache reuse or rerun.
"""
import argparse,hashlib,json,os,pathlib,subprocess,sys,time,shutil,re
C=pathlib.Path(__file__).resolve().parent
D=C.parent/'ci_frontend_materialization_r2_20261029'
def need(x,m):
 if not x:raise ValueError(m)
def sha(p):
 with pathlib.Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
# Safe finite projection only: never copy argv, raw errors, paths, compiler logs,
# process rows, source bodies or arbitrary report keys to Actions stdout.
BUILD_STAGE_NAMES=('jdk','compile_tools','jars','verilator','idma','matrix','fresh_host','binding')
BUILD_ERROR_CODES={
 'ValueError: wall cap':'WALL_CAP',
 'InterruptedError: signal 14':'MONITOR_SIGALRM',
 'ValueError: prelaunch work deadline':'PRELAUNCH_DEADLINE',
 'ValueError: sampled observed aggregate RSS cap':'SAMPLED_RSS_CAP',
 'ValueError: sampled observed aggregate CPU cap':'SAMPLED_CPU_CAP',
 'ValueError: locked memory gate':'PRELAUNCH_MEMORY_GATE',
 'ValueError: locked disk gate':'PRELAUNCH_DISK_GATE',
 'ValueError: entry cap':'ENTRY_CAP',
 'ValueError: file cap':'FILE_CAP',
 'ValueError: sampled aggregate writable-root cap':'AGGREGATE_TREE_CAP',
 'ValueError: sampled stage output tree cap':'STAGE_TREE_CAP',
 'ValueError: sampled disk reserve':'DISK_RESERVE',
 'ValueError: sampled log cap':'LOG_CAP',
 'ValueError: log reader failure':'LOG_READER_FAILURE',
 'ValueError: log EOF missing after cleanup':'LOG_EOF_MISSING',
 'RuntimeError: capture missing EOF; no full log claim':'LOG_EOF_MISSING',
 'ValueError: reader completion deadline':'READER_DEADLINE',
 'ValueError: reader join deadline':'READER_DEADLINE',
 'ValueError: post-cleanup deadline':'POST_CLEANUP_DEADLINE',
}
def bootstrap_stage_diagnostic(name,report,receipt_path):
 import math
 def number(v):
  return v if type(v)in(int,float)and 0<=v<=2**53 and math.isfinite(v) else None
 def boolean(v):return v if type(v)is bool else None
 def obj(v):return v if type(v)is dict else {}
 r=obj(report);errors=r.get('errors');valid_errors=type(errors)is list
 categories=sorted({BUILD_ERROR_CODES.get(e,'UNCLASSIFIED_SUPERVISOR_ERROR') if type(e)is str else 'MALFORMED_ERROR' for e in errors[:256]}) if valid_errors else ['MALFORMED_ERROR_LIST']
 if valid_errors and len(errors)>256:categories.append('ERROR_LIST_TRUNCATED')
 caps=obj(r.get('caps'));cleanup=obj(r.get('cleanup_proof'));capture=obj(r.get('log_capture'))
 native=r.get('native_exit');native=native if type(native)is int and -128<=native<=255 else None
 receipt_sha=None
 try:
  if receipt_path.is_file()and not receipt_path.is_symlink():receipt_sha=sha(receipt_path)
 except OSError:pass
 result=dict(schema='BOUNDED_BOOTSTRAP_STAGE_DIAGNOSTIC_V1',stage=name if name in BUILD_STAGE_NAMES else 'UNKNOWN_STAGE',receipt_sha256=receipt_sha,
  worker_started=boolean(r.get('worker_started')),native_exit=native,error_count=min(len(errors),2**31-1) if valid_errors else None,error_categories=categories,
  elapsed_seconds=number(r.get('elapsed_seconds')),observed_cpu_seconds=number(r.get('observed_cpu_seconds')),observed_peak_rss=number(r.get('observed_peak_rss')),peak_tree_bytes=number(r.get('peak_tree_bytes')),peak_file_bytes=number(r.get('peak_file_bytes')),
  caps={k:number(caps.get(k)) for k in ('wall_seconds','cleanup_seconds','rss_bytes','cpu_seconds','per_process_as_bytes','per_process_cpu_seconds','file_bytes','tree_bytes','watch_tree_bytes','max_entries')},
  cleanup_complete=cleanup.get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP',pipe_eof_observed=boolean(capture.get('pipe_eof_observed')),gzip_finalized=boolean(capture.get('gzip_finalized')),
  numerical_pass=False,final_rtl_replay=False)
 # native nonzero with no supervisor error is NOT classified as compiler/OOM.
 raw=json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False)
 if len(raw.encode())>8192:raise ValueError('bounded diagnostic schema overflow')
 return raw

JAR_STATUS_REASONS={'SOURCE_OR_CONTRACT_REJECTED','JAR_INVENTORY_REJECTED','JAR_CACHE_REJECTED','JAR_MISSING','JAR_CONTENT_REJECTED','JAR_HTTP_ERROR','JAR_NETWORK_ERROR','JAR_TIMEOUT','JAR_IO_ERROR','UNCLASSIFIED_FAILURE'}
def project_jar_status(d):
 keys={'schema','status','reason','jar_index','http_status','source_count','required_jar_count','verified_jar_count','download_requested','verify_only','compiler_executed','numerical_pass'}
 need(type(d)is dict and set(d)==keys,'jar status exact fields')
 need(d['schema']=='MODEL_CANDIDATE_JAR_INPUT_STATUS_V1'and d['status']in {'INCOMPLETE','SOURCE_AND_ALL_JAR_BYTES_VERIFIED'},'jar bootstrap status')
 need(d['download_requested']is True and d['verify_only']is False and d['compiler_executed']is False and d['numerical_pass']is False,'jar scope only')
 need(type(d['required_jar_count'])is int and d['required_jar_count']==107 and type(d['verified_jar_count'])is int and 0<=d['verified_jar_count']<=107,'jar bounded counts')
 need(d['source_count']is None or (type(d['source_count'])is int and d['source_count']==159),'jar source count')
 need(d['jar_index']is None or (type(d['jar_index'])is int and 0<=d['jar_index']<107),'jar index')
 need(d['http_status']is None or (type(d['http_status'])is int and 100<=d['http_status']<=599),'jar HTTP code')
 if d['status']=='INCOMPLETE':need(type(d['reason'])is str and d['reason']in JAR_STATUS_REASONS,'jar finite failure')
 else:need(d['reason']is None and d['jar_index']is None and d['http_status']is None and d['source_count']==159 and d['verified_jar_count']==107,'jar complete bytes not compiler pass')
 need(d['http_status']is None or d['reason']=='JAR_HTTP_ERROR','HTTP category binding')
 return d

def read_jar_status(path):
 try:
  need(path.is_file()and all(not p.is_symlink()for p in(path,*path.parents))and 0<path.stat().st_size<=2048,'bounded jar metadata')
  def unique(rows):
   d={}
   for k,v in rows:
    need(k not in d,'duplicate jar field');d[k]=v
   return d
  result=project_jar_status(json.loads(path.read_text(),object_pairs_hook=unique))
 except Exception:result={'schema':'MODEL_CANDIDATE_JAR_INPUT_STATUS_UNAVAILABLE_V1','compiler_executed':False,'numerical_pass':False}
 raw=json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False)
 need(len(raw.encode())<=2048,'bounded safe jar projection');return raw

def record_bootstrap_diagnostic(name,report,work):
 # Projection only, not a replacement supervisor receipt or acceptance evidence.
 raw=bootstrap_stage_diagnostic(name,report,work/('stage_'+name)/'RESULT.json')
 print('BOOTSTRAP_STAGE_DIAGNOSTIC '+raw,flush=True)
 if name=='jars':print('MODEL_JAR_STATUS '+read_jar_status(work/'MODEL_JAR_STATUS.json'),flush=True)
 if name not in BUILD_STAGE_NAMES:return
 try:
  with (work/(name+'_SUPERVISOR_RETURN_DIAGNOSTIC.json')).open('x') as f:f.write(raw+'\n')
 except OSError:
  print('BOOTSTRAP_DIAGNOSTIC_LOCAL_WRITE_UNAVAILABLE',flush=True)

def main():
 global D
 a=argparse.ArgumentParser()
 for n in ['repo','pipeline','work']:a.add_argument('--'+n,type=pathlib.Path,required=True)
 a.add_argument('--shared-owned-root',type=pathlib.Path,required=True)
 a.add_argument('--materialization-dir',type=pathlib.Path,required=True);a.add_argument('--job-started-monotonic',type=float,required=True);a.add_argument('--remaining-tail-reserve-seconds',type=int,required=True);a.add_argument('--maximum-build-seconds',type=int,required=True)
 a.add_argument('--reviewed-repo-sha',required=True);a.add_argument('--artifact-identity',type=pathlib.Path,required=True);a.add_argument('--execute-reviewed-once',action='store_true');a.add_argument('--fresh-host-contract',type=pathlib.Path);a.add_argument('--fresh-host-contract-sha256');v=a.parse_args()
 D=v.materialization_dir.resolve()
 need(v.remaining_tail_reserve_seconds==900 and v.maximum_build_seconds==7200 and 0<=time.monotonic()-v.job_started_monotonic<9000,'whole job clock and remaining tail reserve')
 R=v.repo.resolve();P=v.pipeline.resolve();W=v.work.resolve()
 sys.path.insert(0,str(C));from candidate_generation_gate import load_contract,GENERATION_CONTRACT_SHA256
 load_contract(C/'GENERATION_CONTRACT.json',GENERATION_CONTRACT_SHA256)
 identity=json.loads(v.artifact_identity.read_text())
 need(set(identity)=={'run_id','artifact_name','source_commit','launch_commit','launch_manifest_path','launch_manifest_blob_sha'},'V2 six-field artifact identity')
 need(type(identity['run_id'])is int and identity['run_id']>0 and re.fullmatch('[A-Za-z0-9_.-]{1,128}',identity['artifact_name']),'bounded run/name')
 need(all(re.fullmatch('[0-9a-f]{40}',identity[k]) for k in ('source_commit','launch_commit','launch_manifest_blob_sha')) and re.fullmatch(r'ci_launch/[A-Za-z0-9_.-]+\.json',identity['launch_manifest_path']),'exact V2 commits and launch path')
 need(identity['source_commit']==v.reviewed_repo_sha and identity['source_commit']!=identity['launch_commit'],'distinct checked-out source and launch')
 need(str(identity['run_id'])==os.environ['GITHUB_RUN_ID'] and identity['launch_commit']==os.environ['GITHUB_SHA'] and os.environ['GITHUB_RUN_ATTEMPT']=='1','actual first build run identity')
 event=json.loads(pathlib.Path(os.environ['GITHUB_EVENT_PATH']).read_text())
 need(event.get('before')==identity['source_commit'] and event.get('after')==identity['launch_commit'] and event.get('ref')=='refs/heads/main','actual reviewed two-commit push')
 need(v.execute_reviewed_once and not W.exists(),'explicit mode and fresh work root')
 need(subprocess.check_output(['git','-C',str(R),'rev-parse','HEAD'],text=True).strip()==v.reviewed_repo_sha,'reviewed source commit')
 need(P.is_relative_to(R) and D.is_relative_to(R),'published candidate source under reviewed checkout')
 subprocess.run(['git','-C',str(R),'diff','--quiet','HEAD','--'],check=True)
 fresh=None
 if v.fresh_host_contract is not None or v.fresh_host_contract_sha256 is not None:
  sys.path.insert(0,str(D));import fresh_host
  fresh=fresh_host.load_contract(v.fresh_host_contract,v.fresh_host_contract_sha256,identity)
  fresh_host.reject_injection(os.environ)
 else:need(os.environ.get('ImageVersion')=='20261026.354.1','explicit new image identity required on roll')
 W.mkdir();sys.path.insert(0,str(P));import supervise_multiroot as supervise
 py=str(pathlib.Path('/usr/bin/python3').resolve());gh=str(pathlib.Path('/usr/bin/gh').resolve());java=pathlib.Path(os.environ['JAVA_HOME_21_X64'])/'bin/java'
 env={k:os.environ[k] for k in ['PATH','HOME','ImageVersion','ImageOS','JAVA_HOME_21_X64'] if k in os.environ};env.update(LANG='C.UTF-8',LC_ALL='C.UTF-8',MAKEFLAGS='-j1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
 if fresh is not None:
  env.update({k:os.environ[k] for k in ('GITHUB_RUN_ID','GITHUB_SHA','GITHUB_RUN_ATTEMPT')});env['PATH']='/usr/bin:/bin'
 pins={str(p):sha(p) for root in (P,D,C) for p in root.iterdir() if p.is_file() and p.suffix in ('.py','.json','.scala','.vlt','.tsv')}
 pins[str(pathlib.Path(__file__).resolve())]=sha(__file__)
 pins.update({py:sha(py),gh:sha(gh),'/usr/bin/dpkg-deb':sha('/usr/bin/dpkg-deb')})
 if fresh is not None:pins[str(v.fresh_host_contract.resolve())]=v.fresh_host_contract_sha256
 restore=C/'restore_model_inputs.py';pins[str(restore)]=sha(restore)
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
  need(time.monotonic()-v.job_started_monotonic+wall+30+v.remaining_tail_reserve_seconds<9000,'whole build-only deadline reserves export')
  need(shutil.disk_usage(W).free>=1_500_000_000,'disk reserve')
  e=dict(env)
  if token:
   need(bool(os.environ.get('GH_TOKEN')),'existing job actions-read token required');e['GH_TOKEN']=os.environ['GH_TOKEN']
  caps=dict(wall_seconds=wall,cleanup_seconds=30,file_bytes=536870912,tree_bytes=12_081_306_272,log_bytes=16_777_216,raw_log_bytes=33_554_432,max_entries=100000,per_process_as_bytes=4*1024**3,per_process_cpu_seconds=wall,rss_bytes=rss*1024**3,cpu_seconds=wall,extra_watch_roots=[str(W),str(R),str(v.shared_owned_root.resolve())],min_free_disk_bytes=1_500_000_000,watch_tree_bytes=12_081_306_272)
  try:
   r=supervise.execute(argv,str(W/('stage_'+name)),str(W/'bootstrap.lock'),caps,e,pins,resource_gate={'min_available_memory':(rss+1)*1024**3,'min_disk_free':1_500_000_000})
   record_bootstrap_diagnostic(name,r,W)
  finally:
   check_fresh_aliases()
  stages.append({k:r[k] for k in ['status','native_exit','elapsed_seconds','observed_peak_rss']});(W/'bootstrap_stages.json').write_text(json.dumps(stages,indent=2)+'\n')
  need(r['native_exit']==0 and not r['errors'] and r['cleanup_proof'],'bootstrap failed '+name)
 fresh_args=[] if fresh is None else ['--fresh-host-contract',str(v.fresh_host_contract),'--fresh-host-contract-sha256',v.fresh_host_contract_sha256]
 stage('jdk',[py,'-B',str(D/'inventory_runner_jdk.py'),'--java-home',str(java.parent.parent),'--output',str(W/'jdk.json'),*fresh_args])
 if fresh is not None:
  stage('compile_tools',[py,'-B',str(P/'inventory_compile_tools.py'),'--output',str(W/'compile-tools.json')])
  try:fresh_host.validate_compile_inventory(json.loads((W/'compile-tools.json').read_text()))
  except Exception:
   parent_failure('GNU_RUNTIME_ADMISSION','GNU_RUNTIME_DEPENDENCIES_UNQUALIFIED');raise
 stage('jars',[py,'-B',str(C/'restore_model_inputs.py'),'--download-jars','--status-json',str(W/'MODEL_JAR_STATUS.json')],600)
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
 stage('binding',[py,'-B',str(C/'materialize_model_binding.py'),'--repo',str(R),'--expected-repo-sha',v.reviewed_repo_sha,'--pipeline',str(P),'--jdk-inventory',str(W/'jdk.json'),'--java',str(java),'--tools',str(W/'verilator'),'--idma',str(W/'idma/extracted/idma_export'),'--matrix',str(W/'matrix'),'--binding',str(W/'FRONTEND_BINDING.json'),'--output',str(W/'frontend')])
 # This entry owns its own stage-level process groups and aggregate memory budget.
 # Token is intentionally absent. Outer GitHub job timeout bounds all stages.
 binding=W/'FRONTEND_BINDING.json';bound=json.loads(binding.read_text());bound['mode']='BUILD_ONLY';bound['artifact_identity']=identity
 tool_inventory=json.loads((W/'compile-tools.json').read_text());need(tool_inventory['schema']=='INSTALLED_GNU_BUILD_TOOLS_V1' and tool_inventory['qualification']=='IDENTITY_AND_SUPPORTED_OPTIONS_ONLY_NOT_COMPILE_OR_NUMERICAL_PASS','installed tool identity scope');bound['compile_tools']=tool_inventory['compile_tools'];bound['compile_tool_pins']=tool_inventory['pins'];bound['compile_aliases']=tool_inventory['aliases'];bound['compile_tool_manifest']=str(W/'compile-tools.json');bound['pins'][str(W/'compile-tools.json')]=sha(W/'compile-tools.json');bound['pins'].update(tool_inventory['pins'])
 if fresh is not None:
  bound['fresh_host_identity_manifest']=str(W/'fresh-host.json');bound['pins'].update(host['pins']);bound['pins'][str(W/'fresh-host.json')]=sha(W/'fresh-host.json');bound['fresh_host_aliases']=host['aliases']
 need(v.shared_owned_root.resolve().is_dir() and W.is_relative_to(v.shared_owned_root.resolve()),'same job shared disk ownership');bound['materialized_roots'].append(str(v.shared_owned_root.resolve()))
 bound['job_budget_seconds']=min(v.maximum_build_seconds-int(time.monotonic()-started),int(9000-(time.monotonic()-v.job_started_monotonic))-v.remaining_tail_reserve_seconds);need(bound['job_budget_seconds']>0,'actual remaining build budget');binding.write_text(json.dumps(bound,indent=2)+'\n');binding.with_suffix('.sha256').write_text(sha(binding)+'\n')
 command=[py,'-B',str(C/'one_job_model_candidate.py'),'--binding',str(W/'FRONTEND_BINDING.json'),'--binding-sha256',sha(W/'FRONTEND_BINDING.json'),'--execute-reviewed-once']
 os.execve(py,command,env)
if __name__=='__main__':main()
