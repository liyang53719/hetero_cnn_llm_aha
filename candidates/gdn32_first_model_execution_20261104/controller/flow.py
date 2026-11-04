"""One reviewed owning CI job: materials/reference -> one original backend -> five
same-stimulus bounded diagnostics. Only summary may leave job. NO automatic launch.
Numerical definitions and 4096 MAC stay. Fresh-host producer identity changes are explicit.
"""
import argparse,hashlib,importlib.util,json,os,pathlib,platform,subprocess,sys,time
P=pathlib.Path;D=P(__file__).resolve().parent
_policy_spec=importlib.util.spec_from_file_location('samejob_profile_policy', P(__file__).resolve().parent.parent/'profile_policy.py');profile_policy=importlib.util.module_from_spec(_policy_spec);_policy_spec.loader.exec_module(profile_policy)
TREE=12_081_306_272

def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pin(p):
 p=P(p).resolve();return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def save(p,v):
 with P(p).open('x')as f:json.dump(v,f,indent=2);f.write('\n')
def mod(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def host_diagnostic(b):
 path=D.parent/'numeric/samejob_host_diagnostic.py';need(b['pins'].get(str(path))==sha(path),'same-job diagnostic bridge source pin');return mod('samejob_host_diagnostic',path)

def gdn32_full(b):
 path=D.parent/'numeric/samejob_gdn32_full.py';need(b['pins'].get(str(path))==sha(path),'exact new full bridge source');return mod('gdn32_full_controller',path)

def execution_admission(b):
 if b.get('gdn32_full')is not None:return gdn32_full(b).admit_controller(b)
 if b.get('execution_mode')=='SAME_JOB_P0_M128_HOST_DIAGNOSTIC':return host_diagnostic(b).admit_controller(b)
 path=D.parent/'execution_mode.py'
 need(b['pins'].get(str(path))==sha(path),'execution mode source pin')
 return mod('samejob_execution_mode',path).admit(b)

def transport_code(mode,qualification):
 if mode in ('BOUNDED_CALIBRATION','SAME_JOB_P0_M128_HOST_DIAGNOSTIC'):return 2
 need(mode=='FULL_BLOCK_ACCEPTANCE','explicit full execution mode')
 need(type(qualification)is dict and type(qualification.get('numerical_pass'))is bool,'recomputed aggregate qualification')
 status=qualification.get('status')
 need(status in ('PASS_FIVE_FULL128_EXACT_REFERENCE','FAIL_EXACT_REFERENCE','INCOMPLETE'),'known aggregate status')
 need(qualification['numerical_pass']is(status=='PASS_FIVE_FULL128_EXACT_REFERENCE'),'consistent aggregate qualification')
 return 0 if qualification['numerical_pass'] else 1 if status=='FAIL_EXACT_REFERENCE' else 2

def reservations(b,admission=None):
 if b.get('gdn32_full')is not None:return gdn32_full(b).reservations(b,admission)
 if b.get('execution_mode')=='SAME_JOB_P0_M128_HOST_DIAGNOSTIC':return host_diagnostic(b).reservations(b,admission or execution_admission(b))
 q=b['budgets']
 if admission is None:
  admission={'profile_seconds':q['calibration_seconds']} if b.get('execution_mode','BOUNDED_CALIBRATION')=='BOUNDED_CALIBRATION' else execution_admission(b)
 cal=admission['profile_seconds'];need(set(cal)==set(map(str,range(5)))and all(type(x)is int and 0<x<=20000 for x in cal.values()),'all five explicit unchanged-stimulus calibration windows')
 for k in ('archives','weights','install','owner_bind','reference','provider','build','parent'):
  need(type(q[k])is int and q[k]>0,'reviewed finite phase budget '+k)
 need(q['archives']<=1800 and q['weights']<=7200 and q['install']<=1800 and q['owner_bind']<=1800 and q['reference']<=1800,'no unreviewed original resource expansion')
 tail=sum(cal.values())+7*q['provider']+11*120+1530+q['parent']
 materials=q['archives']+q['weights']+3*q['install']+q['owner_bind']+5*q['reference']+11*30
 total=materials+q['build']+tail
 need(total<=21000,'whole declared round does not fit350min: no implicit truncation or missing profiles')
 return materials,tail,total

def stage_policy(kind,seconds):
 if kind=='archives':return dict(output_bytes=512<<20,rss_bytes=256<<20,as_bytes=1<<30,cpu_seconds=seconds)
 if kind=='weights':return dict(output_bytes=4<<30,rss_bytes=512<<20,as_bytes=1<<30,cpu_seconds=seconds)
 if kind=='reference':return dict(output_bytes=160<<20,rss_bytes=3<<30,as_bytes=8<<30,cpu_seconds=1200)
 raise ValueError('unknown explicit actual output/resource profile')

def run(b,binding_path,binding_sha):
 flow_entered=time.monotonic()
 # Refuse pending observation baseline before acquisition, owner creation or any stage.
 import importlib.util
 baseline_root=D.parent.parent
 spec=importlib.util.spec_from_file_location('production_observer_baseline',baseline_root/'ci_frontend_pipeline_r2_20261029/observer_baseline_gate.py')
 gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
 if b.get('gdn32_full')is None:gate.require_accepted_baseline(baseline_root/'ci_frontend_materialization_r2_20261029')
 else:gdn32_full(b).admit_controller(b) # independent162 source authority, never old baseline alias
 profile_policy.require_source_pin(b['pins']);execution_policy=profile_policy.checked(b)
 admission=execution_admission(b)
 first=b.get('gdn32_full',{}).get('lifecycle_policy')=='FIRST_MEANINGFUL_FULL_ATTEMPT'
 original_binding=pin(binding_path);need(original_binding['sha256']==binding_sha,'FIRST original caller binding digest')
 started=b['job_started_monotonic'];need(type(started)in(int,float)and 0<=time.monotonic()-started<21000,'first workflow-step monotonic clock, never reset at flow/build boundary');materials_reserved,tail_reserved,total=reservations(b,admission)
 need(b['schema']==('GDN32_FULL_MODEL_SAME_JOB_BINDING_V1'if b.get('gdn32_full')is not None else'ONE_JOB_FIVE_M128_CHISEL_TEST_CALIBRATION_V1')and b['profiles']==list(range(5))and b['tokens']==128 and b['matrix_macs']==4096 and b['vector_lanes']==32,'exact registered same-hardware five profiles')
 need(b['payload_uploads']is False and b['final_rtl_replay']is False,'explicit local data only, Chisel simulation backend')
 identity=b['identity'];need({k:b['artifact_identity'][k]for k in identity}==identity,'same builder and runtime owning job identity');need(str(identity['run_id'])==os.environ.get('GITHUB_RUN_ID')and identity['launch_commit']==os.environ.get('GITHUB_SHA')and os.environ.get('GITHUB_RUN_ATTEMPT')=='1','actual first owning CI job')
 fresh=b.get('fresh_host_contract')
 if fresh is None:need(os.environ.get('ImageVersion')=='20261026.354.1','original bootstrap tool image gate: new image needs explicit qualification')
 else:
  host=mod('fresh_host_contract',P(b['materialization_dir'])/'fresh_host.py');host.validate_contract(fresh,identity);host.reject_injection(os.environ)
 need(sys.version_info[:2]==(3,12)and platform.machine()=='x86_64','original Python ABI before downloads or build');profile_policy.require_cpu(b,P('/proc/cpuinfo').read_text().split())
 repo=P(b['repo']).resolve();need(subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True,env={k:v for k,v in os.environ.items()if k not in ('GH_TOKEN','GITHUB_TOKEN')}).strip()==identity['source_commit'],'actual checked-out source')
 job=P(b['job_root']);need(not job.exists()and job.is_absolute()and not any(p.is_symlink()for p in(job,*job.parents)),'fresh canonical job root')
 import shutil
 if b.get('gdn32_full')is not None:gdn32_full(b).resource_gate(b,'INITIAL',13<<30,TREE+(8<<30),1)
 need(int(next(s.split()[1]for s in P('/proc/meminfo').read_text().splitlines()if s.startswith('MemAvailable:')))*1024>=13<<30,'full model MemAvailable13GiB before native')
 need(shutil.disk_usage(job.parent).free>=TREE+(8<<30),'conservative whole-job tree plus unchanged lease free8GiB before expensive work')
 job.mkdir();(job/'runs').mkdir();(job/'env').mkdir();(job/'bindings').mkdir()
 roots=[str(job),str(repo)];pins=dict(b['pins']);pins[str(binding_path)]=binding_sha
 for p,h in pins.items():need(sha(p)==h,'admitted complete source/tool drift')
 runtime=P(b['runtime_package']);numeric=P(b['numeric_package']);py=b['python'];supervisor_dir=b['supervisor_dir'];lock=str(job/'exclusive.lock')
 for p in (D/'flow.py',D/'bootstrap_samejob.py',P(py).resolve()):need(pins.get(str(p))==sha(p),'top controller and executable independently pinned')
 for base in (runtime,numeric):
  for p in base.rglob('*'):
   if p.is_file()and p.suffix in('.py','.json')and '__pycache__'not in p.parts:need(pins.get(str(p))==sha(p),'complete new runtime/controller source pin closure')
 for base in (P(supervisor_dir),):
  for name in ('supervise_multiroot.py','strict_cleanup.py','lossless_log.py'):need(pins.get(str(base/name))==sha(base/name),'published unchanged supervisor')
 sys.path.insert(0,supervisor_dir);import supervise_multiroot as supervisor
 sys.path.insert(0,str(numeric));import live_budget
 history=[];preparation_budget=None;flow_control=None
 if admission['mode']=='SAME_JOB_P0_M128_HOST_DIAGNOSTIC':
  budget_path=repo/'candidates/prefill_host_diagnostic_20261103/runtime_budget.py'
  need(pins.get(str(budget_path))==sha(budget_path),'independently pinned continuous preparation meter')
  control_done=time.monotonic();budget_module=mod('actual_host_preparation_budget',budget_path)
  preparation_budget=budget_module.PreparationBudget(started,control_done)
  flow_control=dict(job_started_monotonic=started,flow_entered_monotonic=flow_entered,control_done_monotonic=control_done,flow_source=pin(D/'flow.py'),controller_binding=pin(binding_path),checks_complete=True,not_a_native_supervisor_receipt=True)
  save(job/'bindings/HOST_DIAGNOSTIC_FLOW_CONTROL.json',flow_control)
 def stage(name,argv,seconds,rss=3,extra_pins=None,network=False,output_root=None,resource_profile=None):
  if preparation_budget is not None:seconds=preparation_budget.cap(name,seconds,30)
  need(time.monotonic()-started+seconds+30<=21000,'same original job deadline')
  policy=stage_policy(resource_profile or name,seconds)
  run_root=P(output_root)if output_root else job/'runs'/name
  need(run_root.is_absolute()and run_root.is_relative_to(job)and not run_root.exists(),'fresh actual capped output subtree')
  cache=job/'env'/name;cache.mkdir();env=dict(PATH='/usr/bin:/bin',LANG='C.UTF-8',LC_ALL='C.UTF-8',PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
  for key in ('HOME','TMPDIR','HF_HOME','HF_HUB_CACHE','TRANSFORMERS_CACHE','XDG_CACHE_HOME','TORCH_HOME','MPLCONFIGDIR','NUMBA_CACHE_DIR'):
   p=cache/key.lower();p.mkdir();env[key]=str(p)
  if network:
   for key in ('HTTPS_PROXY','HTTP_PROXY','ALL_PROXY','NO_PROXY'):
    if key in os.environ:env[key]=os.environ[key]
  stagepins=dict(pins);stagepins.update(extra_pins or {})
  caps=dict(wall_seconds=seconds,cleanup_seconds=30,file_bytes=2<<30,tree_bytes=policy['output_bytes'],watch_tree_bytes=TREE,extra_watch_roots=roots,min_free_disk_bytes=1_500_000_000,log_bytes=64<<20,raw_log_bytes=128<<20,max_entries=150000,per_process_as_bytes=policy['as_bytes'],per_process_cpu_seconds=policy['cpu_seconds'],rss_bytes=policy['rss_bytes'],cpu_seconds=policy['cpu_seconds'])
  if preparation_budget is not None:
   seconds=preparation_budget.cap(name,seconds,30);caps.update(wall_seconds=seconds,cpu_seconds=min(caps['cpu_seconds'],seconds),per_process_cpu_seconds=min(caps['per_process_cpu_seconds'],seconds))
  if b.get('gdn32_full')is not None:gdn32_full(b).resource_gate(b,'FLOW_STAGE',policy['rss_bytes']+(1<<30),8<<30,seconds)
  r=supervisor.execute(list(map(str,argv)),str(run_root),lock,caps,env,stagepins,resource_gate={'min_available_memory':policy['rss_bytes']+(1<<30),'min_disk_free':8<<30})
  if preparation_budget is not None:preparation_budget.check()
  save(job/'bindings'/(name+'_SUPERVISOR_RETURN.json'),r)
  history.append(dict(name=name,native_exit=r['native_exit'],receipt=pin(run_root/'RESULT.json')))
  return r
 def ok(r):need(r['native_exit']==0 and not r['errors']and(r.get('cleanup_proof')or{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'and(r.get('log_capture')or{}).get('pipe_eof_observed')is True and(r.get('log_capture')or{}).get('gzip_finalized')is True,'phase failed/incomplete; no retry')
 q=b['budgets']
 archives=job/'runs/archives/output';ab=job/'bindings/ARCHIVES.json';save(ab,dict(execution_policy=execution_policy,source_dir=str(runtime/'source'),pins=pins,output=str(archives)))
 ok(stage('archives',[py,'-B',runtime/'acquire_archives.py','--binding',ab,'--binding-sha256',sha(ab)],q['archives'],.25,{str(ab):sha(ab)},True))
 remaining_after_build=13500 if preparation_budget is not None else q['weights']+2*q['install']+q['owner_bind']+5*q['reference']+9*30+tail_reserved
 if b.get('gdn32_full')is not None:remaining_after_build=gdn32_full(b).remaining_after_build(b,admission)
 build_allowance=q['build']if first else gdn32_full(b).build_window(b,admission,time.monotonic(),q['install']+30+30)if b.get('gdn32_full')is not None else q['build']
 build_result=None
 def build_after_first_runtime():
  nonlocal build_result,remaining_after_build,build_allowance
  need(build_result is None,'one backend build only')
  if b.get('gdn32_full')is not None:build_allowance=gdn32_full(b).build_window(b,admission,time.monotonic(),20 if first else 30)
  # Admission observation, not a proof of future peak. Original100k watcher remains authoritative.
  if preparation_budget is not None:need(preparation_budget.cap('build_census',20,0)==20,'full bounded census fits preparation')
  else:need(21000-(time.monotonic()-started)-(build_allowance+remaining_after_build)>=20,'census only from unreserved deadline slack')
  census=live_budget.census(roots,max_entries=100000,max_seconds=20)
  if preparation_budget is not None:
   preparation_budget.check();import math;remaining_after_build=9900+math.ceil(3600-preparation_budget.charged())
  need(census.get('complete')is True and census['entries']<=100000,'whole repo/job census within existing build entry cap; not future peak proof')
  build=job/'build';bid=job/'bindings/ARTIFACT_IDENTITY.json';save(bid,b['artifact_identity'])
  effective_build=gdn32_full(b).build_window(b,admission,time.monotonic())if b.get('gdn32_full')is not None else q['build']
  need(time.monotonic()-started+effective_build+remaining_after_build<=21000,'actual build allowance plus complete full tail')
  diagnostic=admission['mode']=='SAME_JOB_P0_M128_HOST_DIAGNOSTIC'
  bootstrap=repo/'candidates/gdn32_first_model162_producer_20261104/bootstrap_model_candidate.py'if b.get('gdn32_full')is not None else repo/'candidates/model_candidate_build_20261101/bootstrap_model_candidate.py'if diagnostic else D/'bootstrap_samejob.py'
  need(pins.get(str(bootstrap))==sha(bootstrap),'actual selected bootstrap source')
  argv=[py,'-B',str(bootstrap),'--repo',str(repo),'--pipeline',b['pipeline'],'--materialization-dir',b['materialization_dir'],'--shared-owned-root',str(job),'--work',str(build),'--reviewed-repo-sha',identity['source_commit'],'--artifact-identity',str(bid),'--job-started-monotonic',str(started),'--remaining-tail-reserve-seconds',str(remaining_after_build),'--maximum-build-seconds',str(q['build']),'--execute-reviewed-once']
  if b.get('gdn32_full')is not None:argv+=['--hardware-source','gdn-chunk32-abort-v2','--samejob-gdn32-binding',str(binding_path),'--samejob-gdn32-binding-sha256',binding_sha]
  if diagnostic:argv+=['--hardware-source',b['host_diagnostic']['hardware_source'],'--samejob-host-diagnostic-binding',str(binding_path),'--samejob-host-diagnostic-binding-sha256',binding_sha,'--host-profile-driver',b['host_profile_driver']['path'],'--host-profile-driver-sha256',b['host_profile_driver']['sha256']]
  if fresh is not None:
   contract_path=job/'bindings/FRESH_HOST_CONTRACT.json';save(contract_path,fresh)
   argv+=['--fresh-host-contract',str(contract_path),'--fresh-host-contract-sha256',sha(contract_path)]
  # Original bootstrap/one_job owns all of its native strict groups and deadlines;
  # do not nest it under another supervisor or modify the four P0 producer sources.
  if preparation_budget is not None:preparation_budget.begin_build()
  try:
   with(job/'build_parent.log').open('xb')as log:code=subprocess.run(argv,stdout=log,stderr=subprocess.STDOUT).returncode
  finally:
   if preparation_budget is not None:preparation_budget.end_build()
  need(code==0,'original backend build failed, no repeat')
  build_result=build/'frontend/BUILD_ONLY_RESULT.json';need(build_result.is_file(),'actual retained shared backend result')
  need(pins.get(str(D/'deduplicate_pack.py'))==sha(D/'deduplicate_pack.py'),'independently pinned duplicate lifecycle');duplicate=mod('exact_pack_duplicate_lifecycle',D/'deduplicate_pack.py')
  if not diagnostic and b.get('gdn32_full')is None:duplicate.run(build_result,sha(build_result),job,code) # exact two stable copies, mode mismatch is NO_OP; no producer edits
 owner_root=job/'materials';ib=job/'bindings/INSTALL.json';archives_rows=json.loads((archives/'ARCHIVES.json').read_text())['archives'];ipins=dict(pins);ipins.update({r['path']:r['sha256']for r in archives_rows})
 save(ib,dict(execution_policy=execution_policy,schema='FRESH_JOB_RUNTIME_CONTROLLER_V1',identity=identity,repo=str(repo),owner_root=str(owner_root),python=py,helper=b['shared_runtime_helper'],supervisor_dir=supervisor_dir,lock=lock,owned_roots=roots,pins=ipins,archives=archives_rows,job_started_monotonic=started,install_wall_seconds=q['install'],metadata_wall_seconds=q['owner_bind'],early_build_seconds=build_allowance,remaining_job_reservation_seconds=build_allowance+q['weights']+30+5*(q['reference']+30)+tail_reserved))
 if b.get('gdn32_full')is not None:
  install_binding=json.loads(ib.read_text());install_binding['gdn32_full_samejob']=True;install_binding['controller_binding']=pin(binding_path);install_binding['remaining_job_reservation_seconds']=build_allowance+remaining_after_build
  if first:
   h=gdn32_full(b).first_helper(b);policy=h.validate_policy(b['gdn32_full']['first_attempt']);install_binding['early_build_seconds']=0;install_binding['remaining_job_reservation_seconds']=policy.min_build_window_seconds+30+remaining_after_build
  ib.write_text(json.dumps(install_binding,indent=2)+'\n')
 if preparation_budget is not None:
  install_binding=json.loads(ib.read_text());install_binding['remaining_job_reservation_seconds']=q['build']+9900;install_binding['host_diagnostic_scope']=host_diagnostic(b).SCOPE
  ib.write_text(json.dumps(install_binding,indent=2)+'\n')
 installer=mod('actual_fresh_installer',runtime/'install_job.py');installer_args=dict(after_first_install=None if first else build_after_first_runtime)
 if preparation_budget is not None:installer_args['preparation_budget']=preparation_budget
 _,_,owner=installer.run(json.loads(ib.read_text()),ib,sha(ib),**installer_args);owner_pin=pin(owner)
 if preparation_budget is not None:preparation_budget.check()
 if not first:need(build_result is not None,'one actual backend build completed')
 payload=job/'runs/weights/output';acq=repo/'candidates/five_profile_acquisition_resume_20261028/acquire_resumable.py'
 if b.get('gdn32_full')is not None:
  acquisition=job/'bindings/SELECTED_WEIGHTS.json';save(acquisition,dict(execution_policy=execution_policy,profiles=list(range(5)),tokens=128,repo=str(repo),pins=pins,output=str(payload)))
  ok(stage('weights',[py,'-B',runtime/'selected_acquisition.py','--binding',acquisition,'--sha256',sha(acquisition),'--execute'],q['weights'],.5,{str(acquisition):sha(acquisition)},network=True))
 else:ok(stage('weights',[py,'-B',acq,'--output',payload,'--execute'],q['weights'],.5,network=True))
 if preparation_budget is not None:preparation_budget.check()
 summary=json.loads((payload/'SUMMARY.json').read_text())
 if b.get('gdn32_full')is None:need(summary['tensors']==70 and summary['tensor_bytes']==3_531_306_272,'one full70 tensor acquisition')
 weights=[]
 for receipt in sorted(payload.glob('*/*.receipt.json')):
  r=json.loads(receipt.read_text());p=receipt.with_name(receipt.name.removesuffix('.receipt.json')+'.bin');need(p.stat().st_size==r['actual_bytes']and sha(p)==r['actual_sha256'],'actual acquired tensor bytes');weights.append(dict(model=receipt.parent.name,name=receipt.name.removesuffix('.receipt.json'),pin=pin(p)))
 if b.get('gdn32_full')is None:need(len(weights)==70 and sum(x['pin']['bytes']for x in weights)==3_531_306_272,'all original five block tensors and bytes')
 else:
  selected_acquisition=mod('actual_selected_acquisition',runtime/'selected_acquisition.py');selected_acquisition.verify_weights(dict(execution_policy=execution_policy,profiles=list(range(5)),tokens=128,repo=str(repo),pins=pins),weights,payload,summary=summary)

 if preparation_budget is not None:preparation_budget.check()
 reference=mod('actual_original_references',runtime/'reference_job.py')
 rb=dict(execution_policy=execution_policy,profiles=list(range(5)),tokens=128,identity=identity,repo=str(repo),output=str(owner_root/'references'),owner_root=str(owner_root),owner_module=str(runtime/'owner_fresh.py'),owner_manifest=owner_pin,pins=pins,payload=str(payload),wall_seconds=q['reference'])
 references=reference.run(rb,stage)
 if first:
  need(build_result is None and set(references)=={'1'},'FIRST materials/reference precede unique build')
  first_admission_pin=gdn32_full(b).begin_first_build(b,original_binding,pin(payload/'SUMMARY.json'),references['1'],time.monotonic())
  build_after_first_runtime()
  need(build_result is not None,'FIRST one complete structural build before runtime freeze')
  first_build_pin=pin(build_result)
  frozen_row,b=gdn32_full(b).freeze_first_runtime(b,original_binding,first_admission_pin,first_build_pin,time.monotonic())
  binding_path=P(frozen_row['path']);binding_sha=frozen_row['sha256'];admission=gdn32_full(b).admit_controller(b)
 if preparation_budget is not None:preparation_budget.check()
 tail=mod('actual_five_diagnostics',numeric/'numeric_tail.py');tb=job/'bindings/NUMERIC.json'
 body=dict(execution_policy=execution_policy,schema='SAME_JOB_FIVE_M128_DIAGNOSTIC_TAIL_V1',profiles=list(range(5)),tokens=128,matrix_macs=4096,vector_lanes=32,upload_payloads=False,final_rtl_replay=False,references=references,weights=weights,calibration_seconds=q['calibration_seconds'],job_started_monotonic=started,reserved_material_seconds=7*q['provider']+11*120,reserved_cleanup_seconds=1530,reserved_parent_seconds=q['parent'],tree_cap=TREE,rss_bytes=b['dut_rss_bytes'],address_space_bytes=12<<30,phase_extra_bytes=b['numeric_reserved_increment_bytes'],provider_wall_seconds=q['provider'],pins=pins,output=str(owner_root/'numeric'),owned_roots=roots,owner_root=str(owner_root),owner_module=str(runtime/'owner_fresh.py'),owner_manifest=owner_pin,supervisor_dir=supervisor_dir,build_result=pin(build_result),run_id=identity['run_id'],source_commit=identity['source_commit'],launch_commit=identity['launch_commit'],python=py,lock=lock,repo=str(repo),payload=str(payload),materializer=b['materializer'],environment={})
 body.update(execution_mode=admission['mode'],full_block_budget=b.get('full_block_budget'))
 if b.get('gdn32_full')is not None:body.update(gdn32_full=b['gdn32_full'],controller_binding=pin(binding_path),source_pins=b['gdn32_full']['source_catalog'])
 if first:body.update(reserved_material_seconds=540,reserved_cleanup_seconds=330,first_attempt_root_binding=original_binding,first_attempt_handoff=dict(root=original_binding,admission=first_admission_pin,build=first_build_pin))
 if admission['mode']=='SAME_JOB_P0_M128_HOST_DIAGNOSTIC':
  body.update(host_diagnostic=b['host_diagnostic'],controller_binding=pin(binding_path),diagnostic_profiles=[0],diagnostic_scope=host_diagnostic(b).SCOPE,host_profile_driver=b['host_profile_driver'],stage_history=history,flow_control=pin(job/'bindings/HOST_DIAGNOSTIC_FLOW_CONTROL.json'),preparation_budget_state=preparation_budget.snapshot(),install_controller_result=pin(owner_root/'INSTALL_CONTROLLER_RESULT.json'),install_receipt_index=pin(owner_root/'RECEIPT_INDEX.json'))
  runner_row=b['host_diagnostic']['runner'];runner_path=P(runner_row['path']);host_diagnostic(b).pin(runner_row)
  need(pins.get(str(runner_path))==runner_row['sha256'],'owning source-pinned diagnostic runner')
  runner=mod('samejob_p0_host_diagnostic_runner',runner_path)
  save(tb,body);runner.run(body,tb,sha(tb),preparation_budget=preparation_budget)
  result_path=owner_root/'numeric/RESULT.json';result=json.loads(result_path.read_text())
  need(result.get('scope')==host_diagnostic(b).SCOPE and result.get('numerical_pass')is False and result.get('full_block_numerical_pass')is False,'separate diagnostic result, never FULL aggregate')
  need(result.get('status')in ('FAILED_HOST_DIAGNOSTIC','INCOMPLETE_HOST_DIAGNOSTIC'),'typed diagnostic terminal status')
  diagnostic_code=1 if result['status']=='FAILED_HOST_DIAGNOSTIC'else 2
  save(job/'FLOW_RESULT.json',dict(identity=identity,execution_binding=pin(binding_path),execution_admission=admission,execution_mode=admission['mode'],transport_exit_code=diagnostic_code,status=result['status'],scope=host_diagnostic(b).SCOPE,numeric_result=pin(result_path),hardware_definitions=1,profiles=list(range(5)),diagnostic_profiles=[0],uploaded_payloads=False,numerical_pass=False,full_block_numerical_pass=False))
  return diagnostic_code
 save(tb,body);tail.run(body,tb,sha(tb))
 numeric_path=owner_root/'numeric/RESULT.json';numeric_result=json.loads(numeric_path.read_text())
 acceptance=mod('actual_full128_acceptance',numeric/'required_acceptance.py')
 qualification=acceptance.aggregate(numeric_result['actual_dut_reports'])
 need(numeric_result.get('qualification')==qualification and numeric_result.get('status')==qualification['status'] and numeric_result.get('numerical_pass')is qualification['numerical_pass'],'recomputed actual numeric finalization')
 code=transport_code(admission['mode'],qualification)
 save(job/'FLOW_RESULT.json',dict(identity=identity,execution_binding=pin(binding_path),execution_admission=admission,execution_mode=admission['mode'],transport_exit_code=code,qualification=qualification,first_attempt_root_binding=original_binding if first else None,execution_policy=execution_policy,status=qualification['status'],scope='CHISEL_TEST_GENERATED_SIMULATION_BACKEND_NOT_FINAL_RTL',stages=history,numeric_result=pin(numeric_path),hardware_definitions=1,profiles=list(range(5)),uploaded_payloads=False))
 return code
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--binding',type=P,required=True);a.add_argument('--binding-sha256',required=True);v=a.parse_args();need(sha(v.binding)==v.binding_sha256,'independent top binding');code=run(json.loads(v.binding.read_text()),v.binding.resolve(),v.binding_sha256);raise SystemExit(code) # mode-specific transport follows recomputed qualification

