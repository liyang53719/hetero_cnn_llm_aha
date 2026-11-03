"""Actual same-job P0 full-M128 path, bounded host diagnostic, never FULL PASS.
No download, build, dispatch, or execution occurs at import. The independently
reviewed owning controller must supply the same live preparation budget object.
No raw model/AXI/tensor logs or payloads are exported by this module.
"""
import hashlib,importlib.util,json,math,os,pathlib,resource,sys,time,types
P=pathlib.Path
D=P(__file__).resolve().parent
MODE='SAME_JOB_P0_M128_HOST_DIAGNOSTIC';SCOPE=MODE+'_NOT_FULL_ACCEPTANCE'

def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pin(p):
 p=P(p);need(p.is_file()and not p.is_symlink(),'regular actual evidence');return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def save(p,v):
 with P(p).open('x')as f:json.dump(v,f,indent=2);f.write('\n')
def module(name,path,pins):
 path=P(path);need(pins.get(str(path))==sha(path),'actual source module pin '+name)
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def closed(r):
 return (r.get('cleanup_proof')or{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'and(r.get('log_capture')or{}).get('pipe_eof_observed')is True and(r.get('log_capture')or{}).get('gzip_finalized')is True

def actual_dut_identity(report,started,outer,artifact,bundle,window):
 """Same original Popen/group/start relationship; no required-acceptance rewrite."""
 need(closed(outer),'DUT outer cleanup and EOF must be closed')
 leader=outer.get('owner_identity');cleanup=outer['cleanup_proof'];need(type(leader)is dict and cleanup.get('owner_identity')==leader,'same outer owner identity')
 need(started['schema']=='ACTUAL_DUT_POPEN_V1'and started['binary_sha256']==artifact['common']['binary']['sha256']and started['runtime_sha256']==bundle['profiles'][0]['runtime']['sha256'],'actual model Popen bytes')
 need(type(started['pid'])is int and started['pid']>0 and started['pid']!=started['consumer_pid'],'actual distinct child')
 need(started['consumer_pid']==leader['pid']and started['consumer_start_tick']==leader['start']and started['inherited_group']==leader['group']and started['inherited_session']==cleanup['session'],'actual PID/start/group/session ancestry')
 a=report['execution_admission'];limits=a['effective_limits']
 need(a['execution_mode']==MODE and a['scope']==SCOPE and limits['max_active_cycles']==3000000 and 9000<=limits['wall_seconds']<=window['dut_wall_seconds']and 0<limits['cpu_seconds']<=limits['wall_seconds']and limits.get('diagnostic_deadline_monotonic')==window['dut_deadline_monotonic'],'actual frozen diagnostic limits')
 need(report['numerical_pass']is False and report['final_rtl_executed']is False and report['matrix_macs']==4096 and report['vector_lanes']==32,'scope and fixed hardware')

def replace_binding(argv,old,new):
 result=list(argv)
 for flag,key in (('--samejob-diagnostic-binding','path'),('--samejob-diagnostic-binding-sha256','sha256')):
  need(result.count(flag)==1,'one existing diagnostic CLI binding');i=result.index(flag)+1;need(result[i]==old[key],'exact preflight binding replaced');result[i]=new[key]
 return result

def timing_projection(log,parser,deadline):
 latest={};lines=0
 with P(log).open('r',encoding='utf-8')as f:
  for line in f:
   need(len(line)<=16384,'bounded internal diagnostic log line')
   lines+=1
   if lines%256==0:need(time.monotonic()<=deadline,'postprocess deadline')
   if line.startswith('HOST_WALL_SAMPLE_V1 '):
    row=parser.parse_line(line);old=latest.get(row['pc'])
    if old is not None:need(row['visited']>=old['visited']and row['selected']>=old['selected'],'monotonic per-PC timing counters')
    latest[row['pc']]=row
 need(time.monotonic()<=deadline,'postprocess deadline')
 return dict(schema='BOUNDED_HOST_TIMING_PROJECTION_V1',samples=[latest[k]for k in sorted(latest)],full_coverage=False,destructor_report_guaranteed=False,perturbation_measured=False,source_log_sha256=sha(log),inclusive_step_not_additive=True)


def host_process_projection(started,terminated,report,log,projector,window):
 need(terminated['schema']=='ACTUAL_DUT_TERMINATION_V1'and terminated['scope']==SCOPE and terminated['measurement_scope']=='DIRECT_DUT_CHILD_HOST_TIME_NOT_RTL_CYCLES_NOT_OUTER_STAGE'and terminated['outer_cleanup_still_required']is True,'actual host process termination scope')
 for key in ('pid','consumer_pid','binary_sha256','runtime_sha256','started_monotonic','effective_runtime_limits'):
  need(terminated[key]==started[key],'actual started/terminated '+key)
 limits=terminated['effective_runtime_limits'];need(limits==report['execution_admission']['effective_limits']and limits['diagnostic_deadline_monotonic']==window['dut_deadline_monotonic'],'actual executed and reported limits')
 for key in ('started_monotonic','cleanup_started_monotonic','reaped_monotonic','elapsed_through_reap_seconds','wait4_child_user_seconds','wait4_child_system_seconds','wait4_child_cpu_seconds'):
  v=terminated[key];need(type(v)in(int,float)and math.isfinite(v)and v>=0,'finite actual host time')
 need(terminated['started_monotonic']<=terminated['cleanup_started_monotonic']<=terminated['reaped_monotonic']and abs(terminated['elapsed_through_reap_seconds']-(terminated['reaped_monotonic']-terminated['started_monotonic']))<1e-6,'actual process elapsed interval')
 need(abs(terminated['wait4_child_cpu_seconds']-terminated['wait4_child_user_seconds']-terminated['wait4_child_system_seconds'])<1e-6,'actual waited direct-child CPU sum')
 row=report['profiles'][0]
 if row.get('exit_code')is not None:need(row['exit_code']==terminated['native_exit'],'same actual DUT exit')
 need(type(terminated['wall_deadline_triggered'])is bool and terminated['wall_deadline_triggered']==(row.get('error_class')=='TimeoutError'and row.get('error')=='DUT wall deadline'),'exact host timeout trigger')
 last=None
 with P(log).open()as f:
  for line in f:
   need(len(line)<=16384,'bounded progress line')
   if line.startswith('HOST_PROGRESS '):
    progress=projector.progress(line.rstrip('\n'));need(progress is not None,'valid actual progress')
    need(all(type(progress[k])is int and 0<=progress[k]<(1<<64)for k in projector.PROGRESS_FIELDS),'uint64 actual counters')
    if last is not None:need(progress['active_cycles']>=last['active_cycles'],'monotonic actual cycle prefix')
    last=progress
 need(last is not None and last['active_cycles']<=window['max_active_cycles'],'actual bounded observed prefix')
 elapsed=terminated['elapsed_through_reap_seconds'];need(elapsed>0,'positive process elapsed')
 return dict(scope='DIRECT_DUT_HOST_PROCESS_INCLUDING_STARTUP_AND_CLEANUP_NOT_RTL_PERFORMANCE',wall_seconds=elapsed,cpu_seconds=terminated['wait4_child_cpu_seconds'],user_cpu_seconds=terminated['wait4_child_user_seconds'],system_cpu_seconds=terminated['wait4_child_system_seconds'],native_exit=terminated['native_exit'],wall_deadline_triggered=terminated['wall_deadline_triggered'],last_logged_active_cycles=last['active_cycles'],last_logged_pc=last['pc'],last_logged_completions=last['completions'],logged_prefix_cycles_per_process_wall_second=last['active_cycles']/elapsed,rate_is_full_block=False,rate_is_new_hardware_cycle_utilization=False,logging_prefix_may_lag_actual=True)

def run(b,binding_path,binding_sha,*,preparation_budget):
 need(sha(binding_path)==binding_sha and json.loads(P(binding_path).read_text())==b,'actual owning numeric binding')
 pins=dict(b['pins']);pins[str(binding_path)]=binding_sha
 repo=P(b['repo']);numeric=repo/'candidates/same_job_execution_20261030/numeric'
 sys.path.insert(0,str(numeric));sys.path.insert(0,str(repo/'candidates/model_candidate_build_20261101'))
 bridge=module('actual_samejob_host_bridge',numeric/'samejob_host_diagnostic.py',pins)
 controller=bridge.load(b['controller_binding']);admission=bridge.admit_controller(controller)
 need(b['execution_mode']==MODE and b['diagnostic_profiles']==[0]and b['diagnostic_scope']==SCOPE,'explicit actual P0 diagnostic')
 need(b['pins']==dict(controller['pins'],**{b['controller_binding']['path']:b['controller_binding']['sha256']}),'same controller closure')
 need(preparation_budget.started==b['job_started_monotonic']==controller['job_started_monotonic'],'same live original clock object')
 preparation_budget.check()
 material=module('actual_p0_material',numeric/'provider_from_frozen.py',pins)
 tail=module('actual_material_and_environment_helpers',numeric/'numeric_tail.py',pins)
 live=module('actual_live_budget',numeric/'live_budget.py',pins)
 owner=module('actual_fresh_owner',b['owner_module'],pins)
 build=material.checked(b['build_result']);result=json.loads(build.read_text());manifest=material.checked(result['artifact']['manifest']);artifact=json.loads(manifest.read_text());root=manifest.parent
 need(build==P(controller['job_root'])/'build/frontend/BUILD_ONLY_RESULT.json','same job real build tree')
 out=P(b['output']);need(not out.exists()and out.is_relative_to(P(b['owner_root'])),'new watched diagnostic output');out.mkdir()
 for name in ('runs','phases','cache_roots','export'): (out/name).mkdir()
 export=out/'export';stage_rows=[];window=None;local_result=None
 body=dict(schema=bridge.SCHEMA,execution_mode=MODE,profile=0,controller_binding=b['controller_binding'],identity=controller['artifact_identity'],repo=str(repo),job_root=controller['job_root'],job_started_monotonic=b['job_started_monotonic'],host_diagnostic=b['host_diagnostic'],host_profile_driver=b['host_profile_driver'],pins=b['pins'],artifact_manifest=pin(manifest),build_result=b['build_result'])
 preflight=out/'PREPARATION_DIAGNOSTIC_BINDING.json';save(preflight,body);preflight_pin=pin(preflight);pins[str(preflight)]=preflight_pin['sha256']
 sys.path.insert(0,b['supervisor_dir']);import supervise_multiroot as supervisor
 need(pins.get(str(P(supervisor.__file__)))==sha(supervisor.__file__),'original actual strict supervisor')
 def stage(name,argv,seconds=120,*,dut=False):
  nonlocal window
  if not dut:seconds=preparation_budget.cap(name,seconds,30)
  else:
   need(window is not None and seconds==window['dut_wall_seconds']+300,'frozen DUT plus consumer postprocess reservation')
   seconds=math.floor(window['dut_deadline_monotonic']+300-time.monotonic());need(seconds>0,'absolute consumer stage deadline')
  environment=tail.owned_environment(b['environment'],out/'cache_roots'/name)
  # Verified by the original owning controller before preparation; no tokens.
  environment.update(GITHUB_RUN_ID=str(controller['artifact_identity']['run_id']),GITHUB_SHA=controller['artifact_identity']['launch_commit'],GITHUB_RUN_ATTEMPT='1')
  phase=out/'phases'/(name+'.json');run_dir=out/'runs'/name
  phase_body=dict(argv=list(map(str,argv)),pins=pins,owned_roots=b['owned_roots'],extra_bytes=b['phase_extra_bytes'],seconds=seconds,job_started=b['job_started_monotonic'],job_budget_seconds=21000,write_file_bytes=128<<20,tree_cap=b['tree_cap'],environment=environment,cache_root=str(out/'cache_roots'/name),admission_output=str(run_dir/'LIVE_ADMISSION.json'),preserve_free_8gib=True)
  save(phase,phase_body);localpins=dict(pins);localpins[str(phase)]=sha(phase)
  caps=dict(wall_seconds=seconds,cleanup_seconds=30,file_bytes=2<<30,tree_bytes=512<<20,log_bytes=64<<20,raw_log_bytes=128<<20,max_entries=100000,per_process_as_bytes=b['address_space_bytes'],per_process_cpu_seconds=seconds+30,rss_bytes=b['rss_bytes'],cpu_seconds=(window['dut_wall_seconds']+120 if dut else seconds+30),extra_watch_roots=b['owned_roots'],min_free_disk_bytes=8<<30,watch_tree_bytes=b['tree_cap'])
  if dut:
   caps['wall_seconds']=min(caps['wall_seconds'],math.floor(window['dut_deadline_monotonic']+300-time.monotonic()));need(caps['wall_seconds']>0,'absolute consumer stage deadline after source checks')
  before_usage=resource.getrusage(resource.RUSAGE_CHILDREN);before_cpu=time.process_time()
  r=supervisor.execute([b['python'],'-B',str(numeric/'locked_phase.py'),'--phase',str(phase),'--sha256',sha(phase)],str(run_dir),b['lock'],caps,environment,localpins,resource_gate={'min_available_memory':b['rss_bytes']+(1<<30),'min_disk_free':8<<30})
  after_usage=resource.getrusage(resource.RUSAGE_CHILDREN);supervisor_cpu=time.process_time()-before_cpu
  waited_cpu=(after_usage.ru_utime+after_usage.ru_stime)-(before_usage.ru_utime+before_usage.ru_stime)
  charged_cpu=max(waited_cpu,r['observed_cpu_seconds'])+supervisor_cpu
  accounting=dict(waited_tree_cpu_seconds=waited_cpu,observed_tree_cpu_seconds=r['observed_cpu_seconds'],supervisor_cpu_seconds=supervisor_cpu,terminal_combined_cpu_seconds=charged_cpu,terminal_complete_accounting=closed(r)and r['native_exit']==0 and not r['errors'],runtime_cpu_enforcement='ORIGINAL_SAMPLED_TREE_AND_PER_PROCESS_RLIMIT_NOT_ZERO_OVERSHOOT',scope='SOLE_DIRECT_CHILD_WITH_WAITED_DESCENDANTS_NO_DOUBLE_COUNT')
  save(out/'phases'/(name+'_CPU_ACCOUNTING.json'),accounting)
  save(out/'phases'/(name+'_SUPERVISOR_RETURN.json'),r)
  row=dict(name=name,native_exit=r['native_exit'],receipt=pin(run_dir/'RESULT.json')if(run_dir/'RESULT.json').is_file()else None,cleanup_complete=closed(r));stage_rows.append(row)
  if not closed(r):
   # Do not release a live owner lease or proceed to another phase on uncertain cleanup.
   save(out/'OWNERSHIP_INCOMPLETE.json',dict(status='HOLD_PARENT_LEASE_NO_CONTINUATION',phase=name))
   import signal
   while True:signal.pause()
  if dut:
   need(time.monotonic()<=window['dut_deadline_monotonic']+330,'absolute consumer and cleanup deadline')
   need(charged_cpu<=2*window['dut_wall_seconds']+120 and supervisor_cpu<=window['dut_wall_seconds']+120,'terminal combined DUT phase CPU cap')
  else:
   preparation_budget.check();need(r['native_exit']==0 and not r['errors'],'actual preparation stage failure '+name)
  return r
 try:
  preparation_budget.check()
  proof_args=types.SimpleNamespace(samejob_diagnostic_binding=preflight,samejob_diagnostic_binding_sha256=preflight_pin['sha256'],profile=0,expected_run_id=b['run_id'],expected_source_commit=b['source_commit'],expected_launch_commit=b['launch_commit'],artifact_manifest=manifest,artifact_manifest_sha256=sha(manifest),local_build_result=build,local_build_result_sha256=b['build_result']['sha256'],validate_only=True,execution_mode=MODE)
  # Actual source/20-stage/compiler/.d/122-port verification precedes even loader --list.
  pre_abi_context=bridge.source_context(proof_args,artifact)
  save(out/'PRE_ABI_ACTUAL_SOURCE_PROOF.json',pre_abi_context)
  preparation_budget.check()
  doc,_=owner.verify(b['owner_manifest']['path'],b['owner_manifest']['sha256'],b['owner_root'])
  need(doc['schema']=='SHARED_THREE_RUNTIME_OWNER_FRESH_JOB_V3'and doc['identity']==dict(run_id=b['run_id'],source_commit=b['source_commit'],launch_commit=b['launch_commit']),'actual same-job owner')
  stable_cache=out/'execution_cache';tail.owned_environment({},stable_cache)
  env_manifest=out/'EXECUTION_ENVIRONMENT.json';save(env_manifest,dict(schema='OWNED_EXECUTION_ENVIRONMENT_V1',identity=doc['identity'],owner_root=b['owner_root'],watched_roots=[b['owner_root']],cache_root=str(stable_cache),cache_paths={k:str(stable_cache/k.lower())for k in tail.CACHE_NAMES}));pins[str(env_manifest)]=sha(env_manifest)
  env_args=['--owned-environment',str(env_manifest),'--owned-environment-sha256',sha(env_manifest)]
  abi=out/'STARTUP_ABI.json';tool=artifact['tool_manifest'];binary=artifact['common']['binary']
  stage('abi0',[b['python'],'-B',str(numeric/'runtime_abi_owned.py'),'--binary',str(root/binary['path']),'--binary-sha256',binary['sha256'],'--tool-manifest',str(root/tool['path']),'--tool-manifest-sha256',tool['sha256'],'--output',str(abi),'--execute-reviewed-loader-list','--expected-run-id',str(b['run_id']),'--expected-source-commit',b['source_commit'],'--expected-launch-commit',b['launch_commit'],*env_args])
  identity_args=['--artifact-manifest',str(manifest),'--artifact-manifest-sha256',sha(manifest),'--expected-run-id',str(b['run_id']),'--expected-launch-commit',b['launch_commit'],'--expected-source-commit',b['source_commit'],'--local-runtime-abi',str(abi),'--local-runtime-abi-sha256',sha(abi),'--local-build-result',str(build),'--local-build-result-sha256',b['build_result']['sha256'],'--samejob-diagnostic-binding',str(preflight),'--samejob-diagnostic-binding-sha256',preflight_pin['sha256'],*env_args]
  lease_root=out/'profile0';lease_root.mkdir();profile=lease_root/'material'
  with owner.lease(b['owner_manifest']['path'],b['owner_manifest']['sha256'],b['owner_root'],0,lease_root)as selected:
   preparation_budget.check();tail.weights(b,0);runtime=selected['qwen2'];ref=material.checked(b['references']['0']);ref_doc=json.loads(ref.read_text())
   need(ref_doc['runtime_receipt_sha256']==runtime['receipt']['sha256']and ref_doc['runtime_source_pins_sha256']==runtime['sidecar']['sha256'],'actual original reference/runtime')
   initialization=out/'phases/p0_initialize_input.json';save(initialization,dict(repo=str(repo),materializer=b['materializer'],output=str(profile),profile=0,reference=b['references']['0']))
   stage('p0_initialize',[b['python'],'-B',str(numeric/'provider_from_frozen.py'),'--initialize-binding',str(initialization),'--sha256',sha(initialization)])
   material.prepare(repo,b['materializer'],profile,0,runtime['wrapper'],b['payload'],b['references']['0'],lambda label,argv:stage('p0_'+label,argv,b['provider_wall_seconds']),pins)
   stage('connect0',[b['python'],'-B',str(numeric/'connect_owned.py'),'--existing-output',str(profile),'--profile','0',*identity_args])
   connected=json.loads((profile/'CONSUMER_ARGV.json').read_text());generated=connected['consumer_argv']
   need(generated[1]==str(numeric/'consumer_owned.py')and connected['hardware_executed']is False,'actual original consumer connection')
   stage('validate_only0',connected['validate_only_argv'])
   preparation_budget.check();window=preparation_budget.freeze();window_path=out/'WINDOW.json';save(window_path,window)
   save(out/'ONE_RUNTIME_LEASE.json',dict(scope=SCOPE,restart_allowed=False,window=pin(window_path),runtime_bundle=pin(profile/'runtime_bundle.v3.json'),artifact_manifest=pin(manifest)))
   finalbody=dict(body,frozen_window=pin(window_path));runtime_binding=out/'RUNTIME_DIAGNOSTIC_BINDING.json';save(runtime_binding,finalbody);runtime_pin=pin(runtime_binding);pins[str(runtime_binding)]=runtime_pin['sha256'];pins[str(window_path)]=sha(window_path)
   argv=replace_binding(generated,preflight_pin,runtime_pin)
   dut_outer=stage('p0_dut',argv,window['dut_wall_seconds']+300,dut=True)
   host_guard=module('actual_postprocess_timer_owner',numeric.parent/'execution_mode.py',pins)
   post_seconds=min(540,math.floor(window['tail_deadline_monotonic']-time.monotonic()-300));need(post_seconds>0,'reserved postprocessing and final cleanup')
   # Keep 120s summary + 120s upload + 60s final margin inside the 900s tail.
   # These are finite reservations, not a guarantee of network upload success.
   # No child remains: reuse original exclusive current-process timers, never
   # nest these watchdogs around the strict subprocess supervisor.
   with host_guard.host_verification_budget(wall_seconds=post_seconds,cpu_seconds=min(post_seconds,300)):
    need(time.monotonic()<=window['tail_deadline_monotonic'],'owning post-DUT deadline')
    reportpath=profile/'dut_result/RESULT.json';startedpath=profile/'dut_result/profile0.started.json';log=profile/'dut_result/profile0.log';bundlepath=profile/'runtime_bundle.v3.json'
    need(reportpath.is_file()and startedpath.is_file()and log.is_file(),'actual DUT report/start/log required; supervisor failure is not diagnostic success')
    report=json.loads(reportpath.read_text());started=json.loads(startedpath.read_text());bundle=json.loads(bundlepath.read_text())
    actual_dut_identity(report,started,dut_outer,artifact,bundle,window)
    projector=module('actual_partial_q_phase',D/'partial_q_phase.py',pins);timing=module('actual_host_timing_projection',D/'host_timing_projection.py',pins)
    program=bundle['profiles'][0]['observation_policy'];program=json.loads(P(program['path']).read_text())['source_pins']['program_manifest']
    built_driver=artifact['common']['driver'];driver_pin=dict(built_driver,path=str(root/built_driver['path']))
    local_result=projector.project(consumer_pin=pin(numeric/'consumer_owned.py'),driver_pin=driver_pin,program_pin=program,bundle_pin=pin(bundlepath),log_pin=pin(log),popen_pin=pin(startedpath),outer_pin=pin(out/'runs/p0_dut/RESULT.json'),artifact_pin=pin(manifest),consumer_result_pin=pin(reportpath),actual_dir=profile/'dut_result/profile0')
    save(out/'LOCAL_PARTIAL_PHASE.json',local_result)
    summary=projector.public_summary(local_result)
    summary['integration_status']='ACTUAL_SAME_JOB_COMPILATION_SOURCE_ABI_VERIFIED_NO_FULL_ACCEPTANCE'
    sample=timing_projection(log,timing,window['tail_deadline_monotonic'])
    termination_path=profile/'dut_result/profile0.termination.json';need(termination_path.is_file()and termination_path.stat().st_size<=65536,'actual direct-child termination measurement')
    sample['host_process']=host_process_projection(started,json.loads(termination_path.read_text()),report,log,projector,window)
    sample['termination_receipt_sha256']=sha(termination_path)
    save(export/'HOST_TIMING.json',sample)
    save(export/'PHASE_SUMMARY.json',summary)
    safe=dict(status='FAILED_HOST_DIAGNOSTIC'if summary['diagnostic_failure']else'INCOMPLETE_HOST_DIAGNOSTIC',scope=SCOPE,numerical_pass=False,full_block_numerical_pass=False,final_rtl_executed=False,diagnostic_profiles=[0],registered_profiles=list(range(5)),hardware_definitions=1,window_seconds=window['dut_wall_seconds'],active_cycle_cap=window['max_active_cycles'],artifact_manifest_sha256=sha(manifest),runtime_bundle_sha256=sha(bundlepath),phase_summary_sha256=sha(export/'PHASE_SUMMARY.json'),host_timing_sha256=sha(export/'HOST_TIMING.json'),raw_payloads_uploaded=False)
    save(out/'RESULT.json',safe);save(export/'RESULT.json',safe)
    need({p.name for p in export.iterdir()}=={'RESULT.json','PHASE_SUMMARY.json','HOST_TIMING.json'}and all(p.is_file()and not p.is_symlink()for p in export.iterdir())and sum(p.stat().st_size for p in export.iterdir())<=1<<20,'exact actual three typed summaries and total byte cap')

 except BaseException as error:
  save(out/'DIAGNOSTIC_FAILURE_LOCAL.json',dict(error_class=type(error).__name__,error=str(error)))
  if not(out/'RESULT.json').exists():
   safe=dict(status='FAILED_HOST_DIAGNOSTIC',scope=SCOPE,numerical_pass=False,full_block_numerical_pass=False,final_rtl_executed=False,diagnostic_failure=True,error_class=type(error).__name__,error_sha256=hashlib.sha256(str(error).encode()).hexdigest(),raw_payloads_uploaded=False)
   save(out/'RESULT.json',safe);save(export/'RESULT.json',safe)
  raise
 finally:
  save(out/'ACTUAL_STAGES.json',stage_rows)
  need({p.name for p in export.iterdir()}<={'RESULT.json','PHASE_SUMMARY.json','HOST_TIMING.json'}and all(p.is_file()and not p.is_symlink()for p in export.iterdir())and sum(p.stat().st_size for p in export.iterdir())<=1<<20,'failed execution exports only bounded allowed subset')
  # Local only. Export is constructed from an exact typed allowlist above.
  if window is not None:need(time.monotonic()<=window['tail_deadline_monotonic'],'postprocessing exceeded owning deadline')
 return json.loads((out/'RESULT.json').read_text())
