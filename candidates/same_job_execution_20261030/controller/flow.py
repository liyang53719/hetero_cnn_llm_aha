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

def execution_admission(b):
 path=D.parent/'execution_mode.py'
 need(b['pins'].get(str(path))==sha(path),'execution mode source pin')
 return mod('samejob_execution_mode',path).admit(b)

def transport_code(mode,qualification):
 if mode=='BOUNDED_CALIBRATION':return 2
 need(mode=='FULL_BLOCK_ACCEPTANCE','explicit full execution mode')
 need(type(qualification)is dict and type(qualification.get('numerical_pass'))is bool,'recomputed aggregate qualification')
 status=qualification.get('status')
 need(status in ('PASS_FIVE_FULL128_EXACT_REFERENCE','FAIL_EXACT_REFERENCE','INCOMPLETE'),'known aggregate status')
 need(qualification['numerical_pass']is(status=='PASS_FIVE_FULL128_EXACT_REFERENCE'),'consistent aggregate qualification')
 return 0 if qualification['numerical_pass'] else 1 if status=='FAIL_EXACT_REFERENCE' else 2

def reservations(b,admission=None):
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
 # Refuse pending observation baseline before acquisition, owner creation or any stage.
 import importlib.util
 baseline_root=D.parent.parent
 spec=importlib.util.spec_from_file_location('production_observer_baseline',baseline_root/'ci_frontend_pipeline_r2_20261029/observer_baseline_gate.py')
 gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
 gate.require_accepted_baseline(baseline_root/'ci_frontend_materialization_r2_20261029')
 profile_policy.require_source_pin(b['pins']);execution_policy=profile_policy.checked(b)
 admission=execution_admission(b)
 started=b['job_started_monotonic'];need(type(started)in(int,float)and 0<=time.monotonic()-started<21000,'first workflow-step monotonic clock, never reset at flow/build boundary');materials_reserved,tail_reserved,total=reservations(b,admission)
 need(b['schema']=='ONE_JOB_FIVE_M128_CHISEL_TEST_CALIBRATION_V1'and b['profiles']==list(range(5))and b['tokens']==128 and b['matrix_macs']==4096 and b['vector_lanes']==32,'exact registered same-hardware five profiles')
 need(b['payload_uploads']is False and b['final_rtl_replay']is False,'explicit local data only, Chisel simulation backend')
 identity=b['identity'];need({k:b['artifact_identity'][k]for k in identity}==identity,'same builder and runtime owning job identity');need(str(identity['run_id'])==os.environ.get('GITHUB_RUN_ID')and identity['launch_commit']==os.environ.get('GITHUB_SHA')and os.environ.get('GITHUB_RUN_ATTEMPT')=='1','actual first owning CI job')
 fresh=b.get('fresh_host_contract')
 if fresh is None:need(os.environ.get('ImageVersion')=='20261026.354.1','original bootstrap tool image gate: new image needs explicit qualification')
 else:
  host=mod('fresh_host_contract',P(b['materialization_dir'])/'fresh_host.py');host.validate_contract(fresh,identity);host.reject_injection(os.environ)
 need(sys.version_info[:2]==(3,12)and platform.machine()=='x86_64','original Python ABI before downloads or build');profile_policy.require_cpu(b,P('/proc/cpuinfo').read_text().split())
 repo=P(b['repo']).resolve();need(subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()==identity['source_commit'],'actual checked-out source')
 job=P(b['job_root']);need(not job.exists()and job.is_absolute()and not any(p.is_symlink()for p in(job,*job.parents)),'fresh canonical job root')
 import shutil
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
 history=[]
 def stage(name,argv,seconds,rss=3,extra_pins=None,network=False,output_root=None,resource_profile=None):
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
  r=supervisor.execute(list(map(str,argv)),str(run_root),lock,caps,env,stagepins,resource_gate={'min_available_memory':policy['rss_bytes']+(1<<30),'min_disk_free':8<<30});history.append(dict(name=name,native_exit=r['native_exit'],receipt=pin(run_root/'RESULT.json')))
  return r
 def ok(r):need(r['native_exit']==0 and not r['errors']and(r.get('cleanup_proof')or{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'and(r.get('log_capture')or{}).get('pipe_eof_observed')is True and(r.get('log_capture')or{}).get('gzip_finalized')is True,'phase failed/incomplete; no retry')
 q=b['budgets']
 archives=job/'runs/archives/output';ab=job/'bindings/ARCHIVES.json';save(ab,dict(source_dir=str(runtime/'source'),pins=pins,output=str(archives)))
 ok(stage('archives',[py,'-B',runtime/'acquire_archives.py','--binding',ab,'--binding-sha256',sha(ab)],q['archives'],.25,{str(ab):sha(ab)},True))
 remaining_after_build=q['weights']+2*q['install']+q['owner_bind']+5*q['reference']+9*30+tail_reserved
 build_result=None
 def build_after_first_runtime():
  nonlocal build_result
  need(build_result is None,'one backend build only')
  # Admission observation, not a proof of future peak. Original100k watcher remains authoritative.
  need(21000-(time.monotonic()-started)-(q['build']+remaining_after_build)>=20,'census only from unreserved deadline slack')
  census=live_budget.census(roots,max_entries=100000,max_seconds=20)
  need(census.get('complete')is True and census['entries']<=100000,'whole repo/job census within existing build entry cap; not future peak proof')
  build=job/'build';bid=job/'bindings/ARTIFACT_IDENTITY.json';save(bid,b['artifact_identity'])
  need(time.monotonic()-started+q['build']+remaining_after_build<=21000,'full remaining build+five diagnostics reservation')
  argv=[py,'-B',str(D/'bootstrap_samejob.py'),'--repo',str(repo),'--pipeline',b['pipeline'],'--materialization-dir',b['materialization_dir'],'--shared-owned-root',str(job),'--work',str(build),'--reviewed-repo-sha',identity['source_commit'],'--artifact-identity',str(bid),'--job-started-monotonic',str(started),'--remaining-tail-reserve-seconds',str(remaining_after_build),'--maximum-build-seconds',str(q['build']),'--execute-reviewed-once']
  if fresh is not None:
   contract_path=job/'bindings/FRESH_HOST_CONTRACT.json';save(contract_path,fresh)
   argv+=['--fresh-host-contract',str(contract_path),'--fresh-host-contract-sha256',sha(contract_path)]
  # Original bootstrap/one_job owns all of its native strict groups and deadlines;
  # do not nest it under another supervisor or modify the four P0 producer sources.
  with(job/'build_parent.log').open('xb')as log:code=subprocess.run(argv,stdout=log,stderr=subprocess.STDOUT).returncode
  need(code==0,'original backend build failed, no repeat')
  build_result=build/'frontend/BUILD_ONLY_RESULT.json';need(build_result.is_file(),'actual retained shared backend result')
  need(pins.get(str(D/'deduplicate_pack.py'))==sha(D/'deduplicate_pack.py'),'independently pinned duplicate lifecycle');duplicate=mod('exact_pack_duplicate_lifecycle',D/'deduplicate_pack.py')
  duplicate.run(build_result,sha(build_result),job,code) # exact two stable copies, mode mismatch is NO_OP; no producer edits
 owner_root=job/'materials';ib=job/'bindings/INSTALL.json';archives_rows=json.loads((archives/'ARCHIVES.json').read_text())['archives'];ipins=dict(pins);ipins.update({r['path']:r['sha256']for r in archives_rows})
 save(ib,dict(execution_policy=execution_policy,schema='FRESH_JOB_RUNTIME_CONTROLLER_V1',identity=identity,repo=str(repo),owner_root=str(owner_root),python=py,helper=b['shared_runtime_helper'],supervisor_dir=supervisor_dir,lock=lock,owned_roots=roots,pins=ipins,archives=archives_rows,job_started_monotonic=started,install_wall_seconds=q['install'],metadata_wall_seconds=q['owner_bind'],early_build_seconds=q['build'],remaining_job_reservation_seconds=q['build']+q['weights']+30+5*(q['reference']+30)+tail_reserved))
 installer=mod('actual_fresh_installer',runtime/'install_job.py');_,_,owner=installer.run(json.loads(ib.read_text()),ib,sha(ib),after_first_install=build_after_first_runtime);owner_pin=pin(owner)
 need(build_result is not None,'one actual backend build completed')
 payload=job/'runs/weights/output';acq=repo/'candidates/five_profile_acquisition_resume_20261028/acquire_resumable.py'
 ok(stage('weights',[py,'-B',acq,'--output',payload,'--execute'],q['weights'],.5,network=True))
 summary=json.loads((payload/'SUMMARY.json').read_text());need(summary['tensors']==70 and summary['tensor_bytes']==3_531_306_272,'one full70 tensor acquisition')
 weights=[]
 for receipt in sorted(payload.glob('*/*.receipt.json')):
  r=json.loads(receipt.read_text());p=receipt.with_name(receipt.name.removesuffix('.receipt.json')+'.bin');need(p.stat().st_size==r['actual_bytes']and sha(p)==r['actual_sha256'],'actual acquired tensor bytes');weights.append(dict(model=receipt.parent.name,name=receipt.name.removesuffix('.receipt.json'),pin=pin(p)))
 need(len(weights)==70 and sum(x['pin']['bytes']for x in weights)==3_531_306_272,'all original five block tensors and bytes')

 reference=mod('actual_original_references',runtime/'reference_job.py')
 rb=dict(execution_policy=execution_policy,profiles=list(range(5)),tokens=128,identity=identity,repo=str(repo),output=str(owner_root/'references'),owner_root=str(owner_root),owner_module=str(runtime/'owner_fresh.py'),owner_manifest=owner_pin,pins=pins,payload=str(payload),wall_seconds=q['reference'])
 references=reference.run(rb,stage)
 tail=mod('actual_five_diagnostics',numeric/'numeric_tail.py');tb=job/'bindings/NUMERIC.json'
 body=dict(execution_policy=execution_policy,schema='SAME_JOB_FIVE_M128_DIAGNOSTIC_TAIL_V1',profiles=list(range(5)),tokens=128,matrix_macs=4096,vector_lanes=32,upload_payloads=False,final_rtl_replay=False,references=references,weights=weights,calibration_seconds=q['calibration_seconds'],job_started_monotonic=started,reserved_material_seconds=7*q['provider']+11*120,reserved_cleanup_seconds=1530,reserved_parent_seconds=q['parent'],tree_cap=TREE,rss_bytes=b['dut_rss_bytes'],address_space_bytes=12<<30,phase_extra_bytes=b['numeric_reserved_increment_bytes'],provider_wall_seconds=q['provider'],pins=pins,output=str(owner_root/'numeric'),owned_roots=roots,owner_root=str(owner_root),owner_module=str(runtime/'owner_fresh.py'),owner_manifest=owner_pin,supervisor_dir=supervisor_dir,build_result=pin(build_result),run_id=identity['run_id'],source_commit=identity['source_commit'],launch_commit=identity['launch_commit'],python=py,lock=lock,repo=str(repo),payload=str(payload),materializer=b['materializer'],environment={})
 body.update(execution_mode=admission['mode'],full_block_budget=b.get('full_block_budget'))
 save(tb,body);tail.run(body,tb,sha(tb))
 numeric_path=owner_root/'numeric/RESULT.json';numeric_result=json.loads(numeric_path.read_text())
 acceptance=mod('actual_full128_acceptance',numeric/'required_acceptance.py')
 qualification=acceptance.aggregate(numeric_result['actual_dut_reports'])
 need(numeric_result.get('qualification')==qualification and numeric_result.get('status')==qualification['status'] and numeric_result.get('numerical_pass')is qualification['numerical_pass'],'recomputed actual numeric finalization')
 code=transport_code(admission['mode'],qualification)
 save(job/'FLOW_RESULT.json',dict(identity=identity,execution_binding=pin(binding_path),execution_admission=admission,execution_mode=admission['mode'],transport_exit_code=code,qualification=qualification,execution_policy=execution_policy,status=qualification['status'],scope='CHISEL_TEST_GENERATED_SIMULATION_BACKEND_NOT_FINAL_RTL',stages=history,numeric_result=pin(numeric_path),hardware_definitions=1,profiles=list(range(5)),uploaded_payloads=False))
 return code
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--binding',type=P,required=True);a.add_argument('--binding-sha256',required=True);v=a.parse_args();need(sha(v.binding)==v.binding_sha256,'independent top binding');code=run(json.loads(v.binding.read_text()),v.binding.resolve(),v.binding_sha256);raise SystemExit(code) # mode-specific transport follows recomputed qualification

