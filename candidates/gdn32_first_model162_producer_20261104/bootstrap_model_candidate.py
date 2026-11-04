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
 need(d['source_count']is None or (type(d['source_count'])is int and d['source_count']in (159,162)),'jar source count')
 need(d['jar_index']is None or (type(d['jar_index'])is int and 0<=d['jar_index']<107),'jar index')
 need(d['http_status']is None or (type(d['http_status'])is int and 100<=d['http_status']<=599),'jar HTTP code')
 if d['status']=='INCOMPLETE':need(type(d['reason'])is str and d['reason']in JAR_STATUS_REASONS,'jar finite failure')
 else:need(d['reason']is None and d['jar_index']is None and d['http_status']is None and d['source_count']in (159,162) and d['verified_jar_count']==107,'jar complete bytes not compiler pass')
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

def model162_build_budget(b,admission,now,remaining,declared):
 import math
 started=b['job_started_monotonic'];policy=b['gdn32_full']['lifecycle_policy'];whole=admission['job_budget_seconds'];bootstrap=admission['bootstrap_seconds']
 need(type(now)in(int,float)and type(started)in(int,float)and math.isfinite(now)and math.isfinite(started)and now>=started,'finite original same-job clock')
 need(type(declared)is int and declared==b['budgets']['build']and 0<declared<=7200 and whole==21000,'unchanged declared build/whole caps')
 need(type(remaining)is int and 0<remaining<whole and type(bootstrap)is int and 0<bootstrap<=1800,'complete immutable tail and setup reservation')
 need(policy in ('RESERVE_ALL_CAPS_BEFORE_NATIVE','CONDITIONAL_COMPLETE_TAIL_BEFORE_DUT','FIRST_MEANINGFUL_FULL_ATTEMPT'),'explicit model162 lifecycle policy')
 elapsed=now-started;first_fields={}
 if policy=='FIRST_MEANINGFUL_FULL_ATTEMPT':
  import importlib.util
  need('first_meaningful_derivation'not in b,'FIRST bootstrap requires immutable root, never derived runtime')
  path=pathlib.Path(b['repo'])/'candidates/gdn32_first_model_execution_20261104/numeric/samejob_gdn32_full.py'
  need(b['pins'].get(str(path))==sha(path),'FIRST exact source-pinned budget bridge')
  spec=importlib.util.spec_from_file_location('model162_first_budget_bridge',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  need(m.admit_controller(b)==admission,'FIRST actual root controller admission')
  h=m.first_helper(b);root=h.file_pin(m.first_root_path(b));need(h.same(h.read_json(root),b),'FIRST exact immutable original root document')
  admission_pin=h.file_pin(pathlib.Path(b['job_root'])/'bindings'/h.BUILD_FILENAME)
  initial=h._verify_build_admission(b,root,admission_pin);policy_row=h.validate_policy(b['gdn32_full']['first_attempt'])
  h.check_clock(b,m.first_clock_id(),now,initial['observed_monotonic'])
  need(remaining==h.remaining_after_build(policy_row)==initial['remaining_after_build_seconds'],'FIRST full immutable minimum DUT plus fixed tail')
  # Census/control already spent may never extend the initial one-build window.
  first_left=math.floor(initial['effective_build_seconds']+initial['census_reserved_seconds']-(now-initial['observed_monotonic']))
  effective=min(declared,initial['effective_build_seconds'],first_left,math.floor(whole-elapsed-remaining))
  need(effective>=policy_row.min_build_window_seconds,'FIRST_NO_REVIEWED_BUILD_WINDOW')
  first_fields=dict(first_root_controller_sha256=root.sha256,first_build_admission_sha256=admission_pin.sha256,first_initial_build_seconds=initial['effective_build_seconds'],first_initial_observed_monotonic=initial['observed_monotonic'],first_census_reserved_seconds=initial['census_reserved_seconds'],first_remaining_admission_seconds=first_left,first_minimum_build_seconds=policy_row.min_build_window_seconds)
 elif policy=='RESERVE_ALL_CAPS_BEFORE_NATIVE':
  need(elapsed+declared+remaining<=whole,'all declared build and full tail fit original job');effective=declared
 else:effective=min(declared,math.floor(whole-elapsed-remaining))
 need(effective>=bootstrap and effective>0,'insufficient complete full tail plus bootstrap before native')
 need(elapsed+effective+remaining<=whole,'effective build preserves every full tail second')
 return dict(schema='MODEL162_CONDITIONAL_BUILD_BUDGET_V1',lifecycle_policy=policy,declared_build_seconds=declared,effective_build_seconds=effective,full_remaining_tail_seconds=remaining,job_started_monotonic=started,elapsed_at_budget_seconds=elapsed,whole_job_seconds=whole,bootstrap_seconds=bootstrap,completion_guaranteed=False,numeric_execution_authorized=False,**first_fields)

def budget_envelope(v,now):
 if getattr(v,'samejob_gdn32_binding',None)is not None:
  import importlib.util
  need(getattr(v,'samejob_host_diagnostic_binding',None)is None and getattr(v,'host_profile_driver',None)is None and not(v.first_fault_readonly or v.terminal_finite_readonly),'isolated ordinary actual162 same-job path')
  need(v.hardware_source=='gdn-chunk32-abort-v2','explicit actual162 same-job selection')
  path=v.repo.resolve()/'candidates/gdn32_first_model_execution_20261104/numeric/samejob_gdn32_full.py'
  binding=v.samejob_gdn32_binding;need(binding.is_file()and not binding.is_symlink()and binding.stat().st_size<=2<<20 and sha(binding)==v.samejob_gdn32_binding_sha256,'owning actual162 controller binding')
  b=json.loads(binding.read_text());need(b.get('schema')=='GDN32_FULL_MODEL_SAME_JOB_BINDING_V1'and b['pins'].get(str(path))==sha(path),'exact pinned actual162 controller bridge')
  identity=json.loads(v.artifact_identity.read_text());need(b.get('artifact_identity')==identity and identity.get('source_commit')==v.reviewed_repo_sha,'same actual controller/build source identity')
  need(str(identity.get('run_id'))==os.environ.get('GITHUB_RUN_ID')and identity.get('launch_commit')==os.environ.get('GITHUB_SHA')and os.environ.get('GITHUB_RUN_ATTEMPT')=='1','actual first controller run before expanded budget')
  spec=importlib.util.spec_from_file_location('samejob_bootstrap_gdn32',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);admission=m.admit_controller(b)
  need(admission['mode']=='FULL_BLOCK_ACCEPTANCE'and admission['job_budget_seconds']==21000 and type(admission['bootstrap_seconds'])is int and 0<admission['bootstrap_seconds']<=1800,'full bounded controller admission')
  remaining=m.remaining_after_build(b,admission)
  need(type(remaining)is int and 0<remaining<21000 and v.remaining_tail_reserve_seconds==remaining,'exact immutable postbuild reservation')
  need(v.job_started_monotonic==b['job_started_monotonic'],'one original owning controller clock')
  budget=model162_build_budget(b,admission,now,remaining,v.maximum_build_seconds)
  v.declared_maximum_build_seconds=v.maximum_build_seconds;v.maximum_build_seconds=budget['effective_build_seconds'];v.model162_build_budget=budget
  need(v.work.resolve()==pathlib.Path(b['job_root'])/'build'and v.shared_owned_root.resolve()==pathlib.Path(b['job_root'])and v.repo.resolve()==pathlib.Path(b['repo']),'same owning controller tree')
  need(0<=now-v.job_started_monotonic and now-v.job_started_monotonic+v.maximum_build_seconds+remaining<=21000,'whole350min bound including all full-profile work and tail')
  return 21000,admission['bootstrap_seconds']
 need(getattr(v,'samejob_gdn32_binding_sha256',None)is None,'paired actual162 controller binding')
 if getattr(v,'samejob_host_diagnostic_binding',None)is None:
  need(getattr(v,'samejob_host_diagnostic_binding_sha256',None)is None,'paired diagnostic binding')
  need(v.remaining_tail_reserve_seconds==900 and v.maximum_build_seconds==7200 and 0<=now-v.job_started_monotonic<9000,'whole job clock and remaining tail reserve')
  need(getattr(v,'host_profile_driver',None)is None and getattr(v,'host_profile_driver_sha256',None)is None,'host profile source forbidden outside explicit same-job mode')
  return 9000,1800
 import importlib.util
 path=v.repo.resolve()/'candidates/same_job_execution_20261030/numeric/samejob_host_diagnostic.py'
 binding=v.samejob_host_diagnostic_binding;need(binding.is_file()and binding.stat().st_size<=2<<20 and sha(binding)==v.samejob_host_diagnostic_binding_sha256,'same original owning controller binding')
 b=json.loads(binding.read_text());need(b['pins'].get(str(path))==sha(path),'actual diagnostic bridge source')
 spec=importlib.util.spec_from_file_location('samejob_bootstrap_diagnostic',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);admission=m.admit_controller(b);_,tail,_=m.reservations(b,admission)
 q=b['budgets'];remaining=v.remaining_tail_reserve_seconds;need(type(remaining)is int and 9900<=remaining<=13500,'remaining continuous prep plus minimum long diagnostic and tail')
 need(dict(path=str(v.host_profile_driver),sha256=v.host_profile_driver_sha256)==b['host_profile_driver'],'same isolated host source relation')
 need(v.hardware_source==m.HARDWARE_SOURCE and not(v.first_fault_readonly or v.terminal_finite_readonly),'separate host diagnostic producer selection')
 need(v.job_started_monotonic==b['job_started_monotonic']and v.maximum_build_seconds==q['build']and v.remaining_tail_reserve_seconds==remaining,'unchanged original clock and exact remaining reservation')
 need(v.work.resolve()==pathlib.Path(b['job_root'])/'build'and v.shared_owned_root.resolve()==pathlib.Path(b['job_root'])and v.repo.resolve()==pathlib.Path(b['repo']),'same job tree and source')
 need(0<=now-v.job_started_monotonic and now-v.job_started_monotonic+v.maximum_build_seconds+remaining<=21000,'same whole350min deadline')
 return 21000,b['host_diagnostic']['bootstrap_seconds']

def main():
 global D
 a=argparse.ArgumentParser()
 for n in ['repo','pipeline','work']:a.add_argument('--'+n,type=pathlib.Path,required=True)
 a.add_argument('--shared-owned-root',type=pathlib.Path,required=True)
 a.add_argument('--materialization-dir',type=pathlib.Path,required=True);a.add_argument('--job-started-monotonic',type=float,required=True);a.add_argument('--remaining-tail-reserve-seconds',type=int,required=True);a.add_argument('--maximum-build-seconds',type=int,required=True)
 a.add_argument('--hardware-source',choices=('legacy','transposed-tile-address-v1','prefill-supply-overlap-v1','gdn-chunk32-abort-v2'),default='legacy')
 a.add_argument('--host-profile-driver',type=pathlib.Path);a.add_argument('--host-profile-driver-sha256')
 a.add_argument('--samejob-gdn32-binding',type=pathlib.Path);a.add_argument('--samejob-gdn32-binding-sha256')
 a.add_argument('--samejob-host-diagnostic-binding',type=pathlib.Path);a.add_argument('--samejob-host-diagnostic-binding-sha256')
 a.add_argument('--first-fault-readonly',action='store_true')
 a.add_argument('--terminal-finite-readonly',action='store_true')
 a.add_argument('--reviewed-repo-sha',required=True);a.add_argument('--artifact-identity',type=pathlib.Path,required=True);a.add_argument('--execute-reviewed-once',action='store_true');a.add_argument('--fresh-host-contract',type=pathlib.Path);a.add_argument('--fresh-host-contract-sha256');v=a.parse_args()
 if v.hardware_source!='gdn-chunk32-abort-v2':
  old=v.repo.resolve()/'candidates/model_candidate_build_20261101'/pathlib.Path(__file__).name
  os.execve(sys.executable,[sys.executable,'-B',str(old),*sys.argv[1:]],dict(os.environ))
 need(not(v.first_fault_readonly and v.terminal_finite_readonly),'one explicit readonly mode')
 need(v.hardware_source=='legacy' or not(v.first_fault_readonly or v.terminal_finite_readonly),'new hardware cannot use unchanged-SV diagnostic contracts')
 D=v.materialization_dir.resolve()
 whole_job_seconds,bootstrap_seconds=budget_envelope(v,time.monotonic())
 R=v.repo.resolve();P=v.pipeline.resolve();W=v.work.resolve()
 sys.path.insert(0,str(C));from candidate_generation_gate import selected_inputs
 selection=selected_inputs(R,v.hardware_source,v.first_fault_readonly,v.terminal_finite_readonly)
 identity=json.loads(v.artifact_identity.read_text())
 need(set(identity)=={'run_id','artifact_name','source_commit','launch_commit','launch_manifest_path','launch_manifest_blob_sha'},'V2 six-field artifact identity')
 need(type(identity['run_id'])is int and identity['run_id']>0 and re.fullmatch('[A-Za-z0-9_.-]{1,128}',identity['artifact_name']),'bounded run/name')
 need(all(re.fullmatch('[0-9a-f]{40}',identity[k]) for k in ('source_commit','launch_commit','launch_manifest_blob_sha')) and re.fullmatch(r'ci_launch/[A-Za-z0-9_.-]+\.json',identity['launch_manifest_path']),'exact V2 commits and launch path')
 need(identity['source_commit']==v.reviewed_repo_sha and identity['source_commit']!=identity['launch_commit'],'distinct checked-out source and launch')
 need(str(identity['run_id'])==os.environ['GITHUB_RUN_ID'] and identity['launch_commit']==os.environ['GITHUB_SHA'] and os.environ['GITHUB_RUN_ATTEMPT']=='1','actual first build run identity')
 event=json.loads(pathlib.Path(os.environ['GITHUB_EVENT_PATH']).read_text())
 need(event.get('before')==identity['source_commit'] and event.get('after')==identity['launch_commit'] and event.get('ref')=='refs/heads/main','actual reviewed two-commit push')
 need(v.execute_reviewed_once and not W.exists(),'explicit mode and fresh work root')
 need(subprocess.check_output(['git','-C',str(R),'rev-parse','HEAD'],text=True,env={k:v for k,v in os.environ.items()if k not in ('GH_TOKEN','GITHUB_TOKEN')}).strip()==v.reviewed_repo_sha,'reviewed source commit')
 need(P.is_relative_to(R) and D.is_relative_to(R),'published candidate source under reviewed checkout')
 subprocess.run(['git','-C',str(R),'diff','--quiet','HEAD','--'],check=True,env={k:v for k,v in os.environ.items()if k not in ('GH_TOKEN','GITHUB_TOKEN')})
 fresh=None
 if v.fresh_host_contract is not None or v.fresh_host_contract_sha256 is not None:
  sys.path.insert(0,str(D));import fresh_host
  fresh=fresh_host.load_contract(v.fresh_host_contract,v.fresh_host_contract_sha256,identity)
  fresh_host.reject_injection(os.environ)
 else:need(os.environ.get('ImageVersion')=='20261026.354.1','explicit new image identity required on roll')
 W.mkdir()
 if getattr(v,'model162_build_budget',None)is not None:
  with (W/'MODEL162_BUILD_BUDGET.json').open('x')as f:json.dump(v.model162_build_budget,f,sort_keys=True);f.write('\n')
  print('MODEL162_BUILD_BUDGET '+json.dumps(v.model162_build_budget,sort_keys=True,allow_nan=False),flush=True)
 sys.path.insert(0,str(P));import supervise_multiroot as supervise
 py=str(pathlib.Path('/usr/bin/python3').resolve());gh=str(pathlib.Path('/usr/bin/gh').resolve());java=pathlib.Path(os.environ['JAVA_HOME_21_X64'])/'bin/java'
 env={k:os.environ[k] for k in ['PATH','HOME','ImageVersion','ImageOS','JAVA_HOME_21_X64'] if k in os.environ};env.update(LANG='C.UTF-8',LC_ALL='C.UTF-8',MAKEFLAGS='-j1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
 if fresh is not None:
  env.update({k:os.environ[k] for k in ('GITHUB_RUN_ID','GITHUB_SHA','GITHUB_RUN_ATTEMPT')});env['PATH']='/usr/bin:/bin'
 pins={str(p):sha(p) for root in (P,D,C) for p in root.iterdir() if p.is_file() and p.suffix in ('.py','.json','.scala','.vlt','.tsv')}
 pins.update({str(selection[k]):sha(selection[k])for k in ('overlay','contract_path')})
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
  from model162_resources import before_stage,safe_failure
  phase='RESOURCE_REQUEST'
  try:
   if getattr(v,'samejob_gdn32_binding',None)is not None:before_stage({'path':str(v.samejob_gdn32_binding),'sha256':v.samejob_gdn32_binding_sha256},wall,rss,stage=name)
   phase='RUNTIME_ALIAS';check_fresh_aliases()
   phase='DEADLINE'
   need(time.monotonic()-started+wall+30<bootstrap_seconds,'bounded bootstrap shared30min budget')
   need(time.monotonic()-started+wall+30<=v.maximum_build_seconds,'each setup stays inside reviewed build budget including cleanup')
   need(time.monotonic()-v.job_started_monotonic+wall+30+v.remaining_tail_reserve_seconds<whole_job_seconds,'whole build-only deadline reserves export')
   phase='DISK';need(shutil.disk_usage(W).free>=1_500_000_000,'disk reserve')
   phase='NATIVE_ENVIRONMENT';e=dict(env)
   if token:
    need(bool(os.environ.get('GH_TOKEN')),'existing job actions-read token required');e['GH_TOKEN']=os.environ['GH_TOKEN']
  except Exception as exc:safe_failure(name,phase,exc,wall,rss);raise
  caps=dict(wall_seconds=wall,cleanup_seconds=30,file_bytes=536870912,tree_bytes=12_081_306_272,log_bytes=16_777_216,raw_log_bytes=33_554_432,max_entries=100000,per_process_as_bytes=4*1024**3,per_process_cpu_seconds=wall,rss_bytes=rss*1024**3,cpu_seconds=wall,extra_watch_roots=[str(W),str(R),str(v.shared_owned_root.resolve())],min_free_disk_bytes=1_500_000_000,watch_tree_bytes=12_081_306_272)
  try:
   try:r=supervise.execute(argv,str(W/('stage_'+name)),str(W/'bootstrap.lock'),caps,e,pins,resource_gate={'min_available_memory':(rss+1)*1024**3,'min_disk_free':1_500_000_000})
   except Exception as exc:safe_failure(name,'SUPERVISOR',exc,wall,rss,kind='SUPERVISOR');raise
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
 stage('jars',[py,'-B',str(C/'restore_model_inputs.py'),'--download-jars','--hardware-source',v.hardware_source,'--status-json',str(W/'MODEL_JAR_STATUS.json')],600)
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
 stage('binding',[py,'-B',str(C/'materialize_model_binding.py'),'--hardware-source',v.hardware_source,'--repo',str(R),'--expected-repo-sha',v.reviewed_repo_sha,'--pipeline',str(P),'--jdk-inventory',str(W/'jdk.json'),'--java',str(java),'--tools',str(W/'verilator'),'--idma',str(W/'idma/extracted/idma_export'),'--matrix',str(W/'matrix'),'--binding',str(W/'FRONTEND_BINDING.json'),'--output',str(W/'frontend')]+(['--first-fault-readonly'] if v.first_fault_readonly else [])+(['--terminal-finite-readonly'] if v.terminal_finite_readonly else [])+(['--profiled-host-diagnostic']if v.host_profile_driver is not None else []))
 # This entry owns its own stage-level process groups and aggregate memory budget.
 # Token is intentionally absent. Outer GitHub job timeout bounds all stages.
 binding=W/'FRONTEND_BINDING.json';bound=json.loads(binding.read_text());bound['mode']='BUILD_ONLY';bound['artifact_identity']=identity
 if getattr(v,'model162_build_budget',None)is not None:
  budget_path=W/'MODEL162_BUILD_BUDGET.json';bound['model162_build_budget']={'path':str(budget_path),'sha256':sha(budget_path)};bound['pins'][str(budget_path)]=sha(budget_path)
  bound['model162_controller_binding']={'path':str(v.samejob_gdn32_binding),'sha256':v.samejob_gdn32_binding_sha256};bound['pins'][str(v.samejob_gdn32_binding)]=v.samejob_gdn32_binding_sha256
 if v.host_profile_driver is not None:bound['host_profile_driver']=dict(path=str(v.host_profile_driver),sha256=v.host_profile_driver_sha256)
 tool_inventory=json.loads((W/'compile-tools.json').read_text());need(tool_inventory['schema']=='INSTALLED_GNU_BUILD_TOOLS_V1' and tool_inventory['qualification']=='IDENTITY_AND_SUPPORTED_OPTIONS_ONLY_NOT_COMPILE_OR_NUMERICAL_PASS','installed tool identity scope');bound['compile_tools']=tool_inventory['compile_tools'];bound['compile_tool_pins']=tool_inventory['pins'];bound['compile_aliases']=tool_inventory['aliases'];bound['compile_tool_manifest']=str(W/'compile-tools.json');bound['pins'][str(W/'compile-tools.json')]=sha(W/'compile-tools.json');bound['pins'].update(tool_inventory['pins'])
 if fresh is not None:
  bound['fresh_host_identity_manifest']=str(W/'fresh-host.json');bound['pins'].update(host['pins']);bound['pins'][str(W/'fresh-host.json')]=sha(W/'fresh-host.json');bound['fresh_host_aliases']=host['aliases']
 need(v.shared_owned_root.resolve().is_dir() and W.is_relative_to(v.shared_owned_root.resolve()),'same job shared disk ownership');bound['materialized_roots'].append(str(v.shared_owned_root.resolve()))
 bound['job_budget_seconds']=min(v.maximum_build_seconds-int(time.monotonic()-started),int(whole_job_seconds-(time.monotonic()-v.job_started_monotonic))-v.remaining_tail_reserve_seconds);need(bound['job_budget_seconds']>0,'actual remaining build budget');binding.write_text(json.dumps(bound,indent=2)+'\n');binding.with_suffix('.sha256').write_text(sha(binding)+'\n')
 command=[py,'-B',str(C/'one_job_model_candidate.py'),'--binding',str(W/'FRONTEND_BINDING.json'),'--binding-sha256',sha(W/'FRONTEND_BINDING.json'),'--hardware-source',v.hardware_source,'--execute-reviewed-once']
 os.execve(py,command,env)
if __name__=='__main__':main()
