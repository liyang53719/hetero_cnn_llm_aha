"""Cloud-only executor: imported build -> original runtime/reference -> five numeric consumers.
No GitHub identity, build, link or workflow; no acquired data upload.
"""
import argparse,hashlib,importlib.util,json,math,os,pathlib,platform,subprocess,sys,time
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

def numeric_module(name,path,pins):
 # Only the complete hash-checked sibling directory is added. Reject cached
 # same-name foreign modules; do not silently reuse another checkout's code.
 directory=P(path).parent
 for sibling in directory.glob('*.py'):
  need(pins.get(str(sibling))==sha(sibling),'numeric sibling source pin')
  cached=sys.modules.get(sibling.stem)
  if cached is not None:need(P(getattr(cached,'__file__','')).resolve()==sibling.resolve(),'foreign cached numeric sibling')
 before=list(sys.path)
 try:
  sys.path.insert(0,str(directory));return mod(name,path)
 finally:sys.path[:]=before

def execution_admission(b):
 path=D.parent/'execution_mode.py'
 need(b['pins'].get(str(path))==sha(path),'execution mode source pin')
 return mod('samejob_execution_mode',path).admit(b)

def transport_code(mode,qualification):
 if mode in ('BOUNDED_CALIBRATION','STAGE_COVERAGE_DIAGNOSTIC'):return 2
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
 for k in ('archives','weights','install','owner_bind','reference','provider','parent'):
  need(type(q[k])is int and q[k]>0,'reviewed finite phase budget '+k)
 need(q['archives']<=1800 and q['weights']<=7200 and q['install']<=1800 and q['owner_bind']<=1800 and q['reference']<=1800,'no unreviewed original resource expansion')
 tail=sum(cal.values())+7*q['provider']+11*120+1530+q['parent']
 materials=q['archives']+q['weights']+3*q['install']+q['owner_bind']+5*q['reference']+11*30
 total=materials+tail
 need(total<=b['job_budget_seconds'],'whole declared cloud round exceeds reviewed deadline')
 return materials,tail,total

def stage_policy(kind,seconds,roles=None):
 if kind=='archives':return dict(output_bytes=512<<20,rss_bytes=256<<20,as_bytes=1<<30,cpu_seconds=seconds)
 if kind=='weights':return dict(output_bytes=4<<30,rss_bytes=512<<20,as_bytes=1<<30,cpu_seconds=seconds)
 if kind=='reference':
  resource=roles['reference']if roles is not None else dict(rss_bytes=3<<30,as_bytes=8<<30)
  need(type(resource)is dict and set(resource)=={'rss_bytes','as_bytes'}and type(resource['rss_bytes'])is int and 0<resource['rss_bytes']<=3<<30 and type(resource['as_bytes'])is int and 0<resource['as_bytes']<=8<<30,'no expanded original reference resources')
  return dict(output_bytes=160<<20,rss_bytes=resource['rss_bytes'],as_bytes=resource['as_bytes'],cpu_seconds=1200)
 raise ValueError('unknown explicit actual output/resource profile')

def verified_p0_provider_reuse(b,budget,candidate):
 if 'p0_provider_reuse'not in b:return None
 need(candidate and budget['execution_mode']=='STAGE_COVERAGE_DIAGNOSTIC','P0 data reuse only approved candidate stage diagnostic')
 need(b['p0_provider_reuse']==budget.get('p0_provider_reuse'),'P0 reuse equals independent approved pin')
 reuse_path=D.parent/'numeric/p0_provider_data_reuse.py';need(b['pins'].get(str(reuse_path))==sha(reuse_path),'P0 pure data reuse verifier source pin')
 reused=mod('actual_p0_provider_data_reuse',reuse_path).verify_metadata(b['p0_provider_reuse'],b)
 need(reused['watch_scope']=='PURE_PROVIDER_AND_FINITE_EVIDENCE_V1' and reused['roots']==[reused['provider_root'],reused['evidence_root']],'only verified pure provider and finite evidence directories watched')
 return reused

def verified_reference_data_reuse(b,budget,candidate):
 if 'reference_data_reuse'not in b:return None
 need(candidate and budget['execution_mode']=='STAGE_COVERAGE_DIAGNOSTIC','reference reuse only approved candidate stage')
 need(b['reference_data_reuse']==budget.get('reference_data_reuse'),'reference reuse independently approved pin')
 path=D.parent/'numeric/reference_data_reuse.py';need(b['pins'].get(str(path))==sha(path),'reference data reuse checker source pin')
 reused=mod('actual_reference_data_reuse',path).verify_metadata(b['reference_data_reuse'],b)
 need(reused['scope']=='READONLY_REFERENCE_TENSOR_HARDLINKS_NOT_DUT_PASS' and reused['tree_cap']==budget.get('aggregate_tree_cap_bytes')==12037043872,'reference reuse exact approved scope/tree')
 need(len(reused['roots'])==5 and len(set(reused['roots']))==5,'five distinct verified reference roots')
 return reused

def stage_budget_watch_coverage(b,roots):
 if b.get('execution_mode')!='STAGE_COVERAGE_DIAGNOSTIC':return
 row=b['stage_coverage_budget'];path=P(row['path']);need(pin(path)==row,'stage budget immutable before watch admission')
 doc=json.loads(path.read_text())
 for evidence in doc['basis'].values():
  p=P(evidence['path'])
  need(p.is_absolute() and p==p.resolve() and any(p.is_relative_to(P(root).resolve())for root in roots),'stage calibration/review metadata must be inside admitted watched directories')

def admitted_inputs(b):
 need(b.get('execution_context')=='CLOUD_EXECUTOR_V1','cloud execution context only')
 for name in ('cloud_budget.py','executor_identity.py','execution_mode.py'):
  path=D.parent/name;need(b['pins'].get(str(path))==sha(path),'cloud admission helper source pin')
 budget_module=mod('actual_cloud_budget',D.parent/'cloud_budget.py');budget=budget_module.admit(b)
 budget_document=json.loads(P(b['cloud_budget']['path']).read_text())
 budget_module.verify_host(budget_document['host_identity'],b['identity'])
 for k in ('runtime_mode','archive_mode','runtime_reuse_manifest','job_budget_seconds','budgets','dut_rss_bytes','dut_address_space_bytes','numeric_reserved_increment_bytes','reserved_other_owner_bytes','consumer_address_space_bytes','stage_resources','execution_mode','full_block_budget'):
  need(b.get(k)==budget[k],'binding must exactly preserve reviewed cloud budget '+k)
 if budget['execution_mode']=='STAGE_COVERAGE_DIAGNOSTIC':
  need(b.get('stage_coverage_budget')is not None and b['stage_coverage_budget']==budget.get('stage_coverage_budget'),'binding reviewed stage coverage budget')
 else:need(b.get('stage_coverage_budget')is None and budget.get('stage_coverage_budget')is None,'stage budget forbidden in other modes')
 for k in ('executor_adaptation','workspace_loader','retained_materials','model_candidate_review','p0_provider_reuse','reference_data_reuse','aggregate_tree_cap_bytes'):
  if k in budget or k in b:need(k in budget and b.get(k)==budget[k],'binding reviewed '+k)
 identity=b['identity'];need(b.get('executor_identity')==identity,'one executor identity')
 mod('actual_cloud_identity',D.parent/'executor_identity.py').verify_current(identity)
 need(b['job_started_monotonic']==identity['started_monotonic'],'same executor clock never reset')
 def checked(row,limit):
  path=P(row['path']);need(path.is_absolute()and path==path.resolve()and all(not q.is_symlink()for q in(path,*path.parents))and path.is_file()and 0<path.stat().st_size<=limit,'bounded regular cloud input')
  need(pin(path)==row,'independent cloud input pin');return path
 identity_path=checked(b['executor_identity_pin'],65536);need(json.loads(identity_path.read_text())==identity,'executor receipt identity')
 manifest=checked(b['artifact_manifest'],65536);frozen=json.loads(manifest.read_text());handoff=checked(b['builder_handoff'],65536)
 candidate=frozen.get('schema')=='MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1'
 extra={'executor_adaptation':b['executor_adaptation']}if 'executor_adaptation'in b else {}
 hpath=D.parent/'numeric/artifact_handoff.py';reviewed=None
 if candidate:
  need(b.get('model_candidate_review')is not None,'MODEL_CANDIDATE_REVIEW_REQUIRED')
  path=D.parent/'numeric/candidate_admission.py';need(b['pins'].get(str(path))==sha(path),'model candidate admission source pin')
  reviewed=mod('flow_model_candidate_admission',path).verify(b['model_candidate_review'],b)
  need(reviewed['scope']=='MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL'and reviewed['artifact_manifest_sha256']==b['artifact_manifest']['sha256'],'actual candidate review scope/artifact')
  hpath=D.parent/'numeric/candidate_artifact_handoff.py'
  extra.update(model_candidate_review=b['model_candidate_review'],current_source_pins_pin=b['source_pins'],repo=P(b['repo']))
 else:need('model_candidate_review'not in b,'model review cannot relabel legacy artifact')
 need(b['pins'].get(str(hpath))==sha(hpath),'handoff verifier source pin')
 imported=mod('actual_imported_artifact',hpath).verify(handoff,b['builder_handoff']['sha256'],manifest,b['artifact_manifest']['sha256'],frozen,identity,**extra)
 if reviewed is not None:imported=dict(imported,model_candidate_verified=reviewed)
 need(imported['builder_identity']==b['artifact_identity'],'separate actual builder identity')
 sourcepins=D.parent/'SOURCE_PINS.json';need(pin(sourcepins)==b['source_pins'],'actual executor source closure pin')
 if 'executor_adaptation'in b:
  apath=D.parent/'executor_adaptation.py';need(b['pins'].get(str(apath))==sha(apath),'adaptation verifier source pin')
  mod('actual_executor_adaptation',apath).verify(b['executor_adaptation'],imported['builder_identity'],identity,current_source_pins_pin=b['source_pins'],repo=P(b['repo']))
  loader_path=D.parent/'numeric/workspace_loader.py';abi_path=D.parent/'numeric/runtime_abi_owned.py'
  for path in (loader_path,abi_path):need(b['pins'].get(str(path))==sha(path),'workspace ABI helper source pin')
  artifact_root=manifest.parent;binary=frozen['common']['binary'];tool=frozen['tool_manifest']
  verified=mod('actual_cloud_workspace_loader',loader_path).verify(b['workspace_loader'],artifact_root/binary['path'],binary['sha256'],artifact_root/tool['path'],tool['sha256'],mod('actual_cloud_runtime_abi',abi_path).elf_info)
  need(verified['artifact_manifest_sha256']==b['artifact_manifest']['sha256']and verified['builder_source_commit']==b['artifact_identity']['source_commit'],'workspace loader actual builder/artifact binding')
  imported=dict(imported,workspace_loader_verified=verified)
 else:need(imported['source_pins_sha256']==sha(sourcepins),'imported build reviewed source closure')
 need(subprocess.check_output(['git','-C',b['repo'],'rev-parse','HEAD'],text=True).strip()==identity['source_commit'],'actual executor source commit')
 if 'retained_materials'in b:
  retained_path=D.parent/'runtime/retained_materials.py';need(b['pins'].get(str(retained_path))==sha(retained_path),'retained materials verifier source pin')
  retained=mod('actual_retained_materials',retained_path).verify(b['retained_materials'],b)
  if candidate:need(retained['scope']=='DATA_REFERENCE_ONLY_NOT_NUMERICAL_ABI_OR_RUNTIME_PASS','candidate retained data/reference only')
  imported=dict(imported,retained_materials_verified=retained)
 reused_refs=verified_reference_data_reuse(b,budget,candidate)
 if reused_refs is not None:imported=dict(imported,reference_data_reuse_verified=reused_refs)
 if 'reference_data_reuse'in b:need(budget['runtime_mode']=='IMPORT_EXISTING_PINNED_RUNTIME'and budget['archive_mode']=='READ_EXISTING_PINNED_ARCHIVES','reference reuse requires explicitly revalidated retained runtime')
 reused=verified_p0_provider_reuse(b,budget,candidate)
 if reused is not None:imported=dict(imported,p0_provider_reuse_verified=reused)
 return budget,imported

def runtime_admission_fields(b):
 return {k:b[k]for k in ('execution_mode','full_block_budget','stage_coverage_budget','p0_provider_reuse','reference_data_reuse','aggregate_tree_cap_bytes','executor_adaptation','workspace_loader','retained_materials','model_candidate_review')if k in b}

def upfront_disk_admission(snapshot,evidence_path=None,binding_sha=None,tree_cap=TREE):
 need(type(tree_cap)is int and tree_cap in (TREE,12037043872),'explicit reviewed unchanged or tighter aggregate cap')
 # Existing read-only inputs already consume disk and TREE. Reserve only the
 # remaining possible aggregate growth, not TREE a second time. This is a
 # sampled planning gate; unchanged locked phase gates/watchers remain binding.
 need(snapshot.get('schema')=='SAMPLED_OWNED_LIVE_BYTES_V1'and snapshot.get('complete')is True,'complete upfront watched-root census')
 live=snapshot['bytes'];free=snapshot['free_bytes']
 need(type(live)is int and 0<=live<=tree_cap and type(free)is int and free>=0,'bounded existing watched bytes/free')
 incremental=tree_cap-live;required=incremental+(8<<30)
 if evidence_path is not None:
  # Local finite diagnostic only: no roots, arbitrary census strings or payload.
  # It is written before the unchanged free-space rejection and outside job.
  bounded=lambda v:v if type(v)is int and 0<=v<2**64 else None
  digest=binding_sha if isinstance(binding_sha,str)and len(binding_sha)==64 and all(c in '0123456789abcdef'for c in binding_sha)else None
  save(evidence_path,dict(schema='CLOUD_UPFRONT_DISK_OBSERVATION_V1',scope='SAMPLED_PLANNING_ONLY_PHASE_GATES_UNCHANGED',binding_sha256=digest,census_schema='SAMPLED_OWNED_LIVE_BYTES_V1',census_complete=True,existing_watched_bytes=bounded(live),maximum_additional_bytes=bounded(incremental),free_reserve_bytes=8<<30,required_free_bytes=bounded(required),observed_free_bytes=bounded(free),shortfall_bytes=bounded(max(0,required-free)),status='SUFFICIENT_SAMPLED_SPACE'if free>=required else'REJECTED_INSUFFICIENT_SAMPLED_SPACE',numerical_pass=False,job_created=False))
 need(free>=required,'remaining aggregate growth plus unchanged free8GiB')
 return dict(existing_watched_bytes=live,maximum_additional_bytes=incremental,free_reserve_bytes=8<<30,required_free_bytes=required,observed_free_bytes=free,scope='SAMPLED_PLANNING_ONLY_PHASE_GATES_UNCHANGED')

def run(b,binding_path,binding_sha):
 # Budget/identity/source/artifact gates occur before any owned directory or stage.
 budget,imported=admitted_inputs(b)
 tree_cap=budget.get('aggregate_tree_cap_bytes',TREE)
 need(b.get('aggregate_tree_cap_bytes',TREE)==tree_cap,'same approved aggregate cap')
 profile_policy.require_source_pin(b['pins']);execution_policy=profile_policy.checked(b)
 need(execution_policy['mode']==profile_policy.FULL,'all five original profiles on cloud executor')
 admission=execution_admission(b)
 limit=b['job_budget_seconds'];need(type(limit)is int and 0<limit<=2**31-1,'finite admitted cloud deadline')
 started=b['job_started_monotonic'];need(type(started)in(int,float)and math.isfinite(started)and 0<=time.monotonic()-started<limit,'original cloud executor monotonic clock');materials_reserved,tail_reserved,total=reservations(b,admission)
 need(time.monotonic()-started+total<=limit,'full declared cloud round fits actual remaining deadline')
 need(b['schema']=='CLOUD_FIVE_M128_EXECUTION_BINDING_V1'and b['profiles']==list(range(5))and b['tokens']==128 and b['matrix_macs']==4096 and b['vector_lanes']==32,'exact registered same-hardware five profiles')
 need(b['payload_uploads']is False and b['final_rtl_replay']is False,'explicit local data only, Chisel simulation backend')
 identity=b['identity'];builder=b['artifact_identity']
 need(sys.version_info[:2]==(3,12)and platform.machine()=='x86_64','original Python ABI before downloads or build');profile_policy.require_cpu(b,P('/proc/cpuinfo').read_text().split())
 repo=P(b['repo']).resolve();need(subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()==identity['source_commit'],'actual checked-out source')
 job=P(b['job_root']);need(not job.exists()and job.is_absolute()and not any(p.is_symlink()for p in(job,*job.parents)),'fresh canonical job root')
 roots=list(dict.fromkeys([str(job),str(repo),*[str(P(b[k]['path']).parent)for k in ('artifact_manifest','builder_handoff','executor_identity_pin','cloud_budget','execution_approval','executor_adaptation','workspace_loader','retained_materials','model_candidate_review','stage_coverage_budget')if k in b]]));pins=dict(b['pins']);pins[str(binding_path)]=binding_sha
 if 'model_candidate_review'in b:
  need('model_candidate_verified'in imported,'reviewed candidate before watch');roots.extend(imported['model_candidate_verified']['roots']);roots=list(dict.fromkeys(roots))
 if 'reference_data_reuse'in b:
  need('reference_data_reuse_verified'in imported,'reference roots verified before watch admission');roots.extend(imported['reference_data_reuse_verified']['roots']);roots=list(dict.fromkeys(roots))
 if 'p0_provider_reuse'in b:
  need('p0_provider_reuse_verified'in imported,'P0 pure data roots verified before watch admission');roots.extend(imported['p0_provider_reuse_verified']['roots']);roots=list(dict.fromkeys(roots))
 if 'workspace_loader'in b:
  need('workspace_loader_verified'in imported,'validated workspace loader root before watch admission');roots.append(imported['workspace_loader_verified']['root']);roots=list(dict.fromkeys(roots))
 if 'retained_materials'in b:
  need('retained_materials_verified'in imported,'retained material inputs verified before watch');roots.extend(imported['retained_materials_verified']['roots']);roots=list(dict.fromkeys(roots))
 for p,h in pins.items():need(sha(p)==h,'admitted complete source/tool drift')
 runtime=P(b['runtime_package']);numeric=P(b['numeric_package']);py=b['python'];supervisor_dir=b['supervisor_dir'];lock=str(job/'exclusive.lock')
 if b['runtime_mode']=='IMPORT_EXISTING_PINNED_RUNTIME':
  reuse_path=runtime/'runtime_reuse.py';need(pins.get(str(reuse_path))==sha(reuse_path),'runtime reuse source pin')
  reuse=mod('cloud_imported_runtime',reuse_path);reuse_binding=dict(b,helper=b['shared_runtime_helper'],source_dir=str(runtime/'source'))
  inventory,_=reuse.manifest(reuse_binding)
  roots+=list(dict.fromkeys([e['import_root']for e in inventory['entries'].values()]+[str(P(v['path']).parent)for v in inventory['archives']]+[str(P(b['runtime_reuse_manifest']['path']).parent)]))
  roots=list(dict.fromkeys(roots))
 for p in (D/'cloud_flow.py',D.parent/'prepare_cloud_execution.py',P(py).resolve()):need(pins.get(str(p))==sha(p),'top controller and executable independently pinned')
 for base in (runtime,numeric):
  for p in base.rglob('*'):
   if p.is_file()and p.suffix in('.py','.json')and '__pycache__'not in p.parts:need(pins.get(str(p))==sha(p),'complete new runtime/controller source pin closure')
 for base in (P(supervisor_dir),):
  for name in ('supervise_multiroot.py','strict_cleanup.py','lossless_log.py'):need(pins.get(str(base/name))==sha(base/name),'published unchanged supervisor')
 census_path=numeric/'live_budget.py';need(pins.get(str(census_path))==sha(census_path),'original bounded live census source pin')
 stage_budget_watch_coverage(b,roots)
 existing_roots=[r for r in roots if P(r)!=job]
 snapshot=mod('cloud_upfront_live_budget',census_path).census(existing_roots,max_entries=150000,max_seconds=60)
 import shutil
 snapshot=dict(snapshot,free_bytes=min(snapshot['free_bytes'],shutil.disk_usage(job.parent).free))
 disk_admission=upfront_disk_admission(snapshot,P(binding_path).with_name(P(binding_path).name+'.UPFRONT_DISK.json'),binding_sha,tree_cap=tree_cap)
 job.mkdir();(job/'runs').mkdir();(job/'env').mkdir();(job/'bindings').mkdir()
 sys.path.insert(0,supervisor_dir);import supervise_multiroot as supervisor
 history=[]
 def stage(name,argv,seconds,rss=3,extra_pins=None,network=False,output_root=None,resource_profile=None):
  need(time.monotonic()-started+seconds+30<=limit,'same admitted cloud job deadline')
  policy=stage_policy(resource_profile or name,seconds,b['stage_resources'])
  run_root=P(output_root)if output_root else job/'runs'/name
  need(run_root.is_absolute()and run_root.is_relative_to(job)and not run_root.exists(),'fresh actual capped output subtree')
  cache=job/'env'/name;cache.mkdir();env=dict(PATH='/usr/bin:/bin',LANG='C.UTF-8',LC_ALL='C.UTF-8',PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
  for key in ('HOME','TMPDIR','HF_HOME','HF_HUB_CACHE','TRANSFORMERS_CACHE','XDG_CACHE_HOME','TORCH_HOME','MPLCONFIGDIR','NUMBA_CACHE_DIR'):
   p=cache/key.lower();p.mkdir();env[key]=str(p)
  if network:
   for key in ('HTTPS_PROXY','HTTP_PROXY','ALL_PROXY','NO_PROXY'):
    if key in os.environ:env[key]=os.environ[key]
  stagepins=dict(pins);stagepins.update(extra_pins or {})
  caps=dict(wall_seconds=seconds,cleanup_seconds=30,file_bytes=2<<30,tree_bytes=policy['output_bytes'],watch_tree_bytes=tree_cap,extra_watch_roots=roots,min_free_disk_bytes=1_500_000_000,log_bytes=64<<20,raw_log_bytes=128<<20,max_entries=150000,per_process_as_bytes=policy['as_bytes'],per_process_cpu_seconds=policy['cpu_seconds'],rss_bytes=policy['rss_bytes'],cpu_seconds=policy['cpu_seconds'])
  r=supervisor.execute(list(map(str,argv)),str(run_root),lock,caps,env,stagepins,resource_gate={'min_available_memory':policy['rss_bytes']+(1<<30)+b['reserved_other_owner_bytes'],'min_disk_free':8<<30})
  save(job/'bindings'/(name+'_SUPERVISOR_RETURN.json'),r)
  history.append(dict(name=name,native_exit=r['native_exit'],receipt=pin(run_root/'RESULT.json')))
  return r
 def ok(r):need(r['native_exit']==0 and not r['errors']and(r.get('cleanup_proof')or{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'and(r.get('log_capture')or{}).get('pipe_eof_observed')is True and(r.get('log_capture')or{}).get('gzip_finalized')is True,'phase failed/incomplete; no retry')
 q=b['budgets']
 archives=job/'runs/archives/output';ab=job/'bindings/ARCHIVES.json'
 if b['runtime_mode']=='IMPORT_EXISTING_PINNED_RUNTIME':
  archive_binding=dict(b,helper=b['shared_runtime_helper'],source_dir=str(runtime/'source'),output=str(archives))
  save(ab,archive_binding);archive_tool=runtime/'reuse_archives.py';archive_network=False
 else:
  save(ab,dict(source_dir=str(runtime/'source'),pins=pins,output=str(archives)));archive_tool=runtime/'acquire_archives.py';archive_network=True
 ok(stage('archives',[py,'-B',archive_tool,'--binding',ab,'--binding-sha256',sha(ab)],q['archives'],.25,{str(ab):sha(ab)},archive_network))
 owner_root=job/'materials';ib=job/'bindings/INSTALL.json';archives_rows=json.loads((archives/'ARCHIVES.json').read_text())['archives'];ipins=dict(pins);ipins.update({r['path']:r['sha256']for r in archives_rows})
 install_binding=dict(execution_context='CLOUD_EXECUTOR_V1',reserved_other_owner_bytes=b['reserved_other_owner_bytes'],stage_resources=b['stage_resources'],job_budget_seconds=limit,execution_policy=execution_policy,schema='FRESH_JOB_RUNTIME_CONTROLLER_V1',identity=identity,repo=str(repo),owner_root=str(owner_root),python=py,helper=b['shared_runtime_helper'],supervisor_dir=supervisor_dir,lock=lock,owned_roots=roots,pins=ipins,archives=archives_rows,job_started_monotonic=started,install_wall_seconds=q['install'],metadata_wall_seconds=q['owner_bind'],early_build_seconds=0,remaining_job_reservation_seconds=q['weights']+30+5*(q['reference']+30)+tail_reserved)
 install_binding.update(runtime_admission_fields(b))
 if b['runtime_mode']=='IMPORT_EXISTING_PINNED_RUNTIME':
  install_binding.update(job_root=str(job),runtime_reuse_manifest=b['runtime_reuse_manifest'],source_dir=str(runtime/'source'),artifact_manifest=b['artifact_manifest'],cloud_budget=b['cloud_budget'],execution_approval=b['execution_approval'],archive_binding=pin(ab),archive_validation_receipt=pin(job/'runs/archives/RESULT.json'),archive_output_manifest=pin(archives/'ARCHIVES.json'))
  installer=mod('actual_runtime_revalidator',runtime/'runtime_reuse.py');owner_module=runtime/'runtime_reuse.py'
 else:
  installer=mod('actual_fresh_installer',runtime/'install_job.py');owner_module=runtime/'owner_fresh.py'
 save(ib,install_binding);_,_,owner=installer.run(json.loads(ib.read_text()),ib,sha(ib));owner_pin=pin(owner)
 if 'retained_materials'in b:
  retained=imported['retained_materials_verified'];payload=P(retained['payload']);weights=retained['weights'];references=retained['references']
 else:
  payload=job/'runs/weights/output';acq=repo/'candidates/five_profile_acquisition_resume_20261028/acquire_resumable.py'
  ok(stage('weights',[py,'-B',acq,'--output',payload,'--execute'],q['weights'],.5,network=True))
  summary=json.loads((payload/'SUMMARY.json').read_text());need(summary['tensors']==70 and summary['tensor_bytes']==3_531_306_272,'one full70 tensor acquisition')
  weights=[]
  for receipt in sorted(payload.glob('*/*.receipt.json')):
   r=json.loads(receipt.read_text());p=receipt.with_name(receipt.name.removesuffix('.receipt.json')+'.bin');need(p.stat().st_size==r['actual_bytes']and sha(p)==r['actual_sha256'],'actual acquired tensor bytes');weights.append(dict(model=receipt.parent.name,name=receipt.name.removesuffix('.receipt.json'),pin=pin(p)))
  need(len(weights)==70 and sum(x['pin']['bytes']for x in weights)==3_531_306_272,'all original five block tensors and bytes')
 
  reference=mod('actual_original_references',runtime/'reference_job.py')
  rb=dict(execution_context='CLOUD_EXECUTOR_V1',reserved_other_owner_bytes=b['reserved_other_owner_bytes'],stage_resources=b['stage_resources'],job_budget_seconds=limit,execution_policy=execution_policy,profiles=list(range(5)),tokens=128,identity=identity,repo=str(repo),output=str(owner_root/'references'),owner_root=str(owner_root),owner_module=str(owner_module),owner_manifest=owner_pin,pins=pins,payload=str(payload),wall_seconds=q['reference'])
  references=reference.run(rb,stage)
 tail=numeric_module('actual_five_diagnostics',numeric/'numeric_tail.py',pins);tb=job/'bindings/NUMERIC.json'
 body=dict(execution_policy=execution_policy,schema='SAME_JOB_FIVE_M128_DIAGNOSTIC_TAIL_V1',profiles=list(range(5)),tokens=128,matrix_macs=4096,vector_lanes=32,upload_payloads=False,final_rtl_replay=False,references=references,weights=weights,calibration_seconds=q['calibration_seconds'],job_started_monotonic=started,reserved_material_seconds=7*q['provider']+11*120,reserved_cleanup_seconds=1530,reserved_parent_seconds=q['parent'],tree_cap=tree_cap,rss_bytes=b['dut_rss_bytes'],address_space_bytes=b['dut_address_space_bytes'],reserved_other_owner_bytes=b['reserved_other_owner_bytes'],consumer_address_space_bytes=b['consumer_address_space_bytes'],phase_extra_bytes=b['numeric_reserved_increment_bytes'],provider_wall_seconds=q['provider'],pins=pins,output=str(owner_root/'numeric'),owned_roots=roots,owner_root=str(owner_root),owner_module=str(owner_module),owner_manifest=owner_pin,supervisor_dir=supervisor_dir,execution_context='CLOUD_EXECUTOR_V1',identity=identity,executor_identity=identity,executor_identity_pin=b['executor_identity_pin'],builder_handoff=b['builder_handoff'],artifact_manifest=b['artifact_manifest'],cloud_budget=b['cloud_budget'],execution_approval=b['execution_approval'],controller_binding=pin(binding_path),job_budget_seconds=limit,run_id=builder['run_id'],source_commit=builder['source_commit'],launch_commit=builder['launch_commit'],python=py,lock=lock,repo=str(repo),payload=str(payload),materializer=b['materializer'],environment={})
 body.update({k:b[k]for k in ('executor_adaptation','workspace_loader','retained_materials','model_candidate_review','p0_provider_reuse','reference_data_reuse','aggregate_tree_cap_bytes')if k in b})
 if 'model_candidate_review'in b:body['source_pins']=b['source_pins']
 body.update(execution_mode=admission['mode'],full_block_budget=b.get('full_block_budget'))
 if admission['mode']=='STAGE_COVERAGE_DIAGNOSTIC':body['stage_coverage_budget']=b['stage_coverage_budget']
 save(tb,body);tail.run(body,tb,sha(tb))
 numeric_path=owner_root/'numeric/RESULT.json';numeric_result=json.loads(numeric_path.read_text())
 acceptance=mod('actual_full128_acceptance',numeric/'required_acceptance.py')
 qualification=acceptance.aggregate(numeric_result['actual_dut_reports'])
 need(numeric_result.get('qualification')==qualification and numeric_result.get('status')==qualification['status'] and numeric_result.get('numerical_pass')is qualification['numerical_pass'],'recomputed actual numeric finalization')
 code=transport_code(admission['mode'],qualification)
 save(job/'FLOW_RESULT.json',dict(execution_context='CLOUD_EXECUTOR_V1',identity=identity,executor_identity=identity,artifact_identity=builder,builder_identity=builder,source_pins=b['source_pins'],executor_identity_pin=b['executor_identity_pin'],builder_handoff=b['builder_handoff'],artifact_manifest=b['artifact_manifest'],cloud_budget=b['cloud_budget'],execution_approval=b['execution_approval'],job_budget_seconds=limit,execution_binding=pin(binding_path),execution_admission=admission,execution_mode=admission['mode'],transport_exit_code=code,qualification=qualification,execution_policy=execution_policy,status=qualification['status'],scope='MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL'if 'model_candidate_review'in b else 'CHISEL_TEST_GENERATED_SIMULATION_BACKEND_NOT_FINAL_RTL',stages=history,retained_materials_scope=imported.get('retained_materials_verified',{}).get('scope'),upfront_disk_admission=disk_admission,numeric_result=pin(numeric_path),hardware_definitions=1,profiles=list(range(5)),uploaded_payloads=False,**{k:b[k]for k in ('executor_adaptation','workspace_loader','retained_materials','model_candidate_review','p0_provider_reuse','reference_data_reuse','aggregate_tree_cap_bytes')if k in b},**(dict(stage_coverage_budget=b['stage_coverage_budget'],stage_coverage_budget_sha256=b['stage_coverage_budget']['sha256'],execution_scope='STAGE_COVERAGE_DIAGNOSTIC_NOT_FULL_ACCEPTANCE')if admission['mode']=='STAGE_COVERAGE_DIAGNOSTIC'else {})))
 return code
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--binding',type=P,required=True);a.add_argument('--binding-sha256',required=True);v=a.parse_args();need(sha(v.binding)==v.binding_sha256,'independent top binding');code=run(json.loads(v.binding.read_text()),v.binding.resolve(),v.binding_sha256);raise SystemExit(code) # mode-specific transport follows recomputed qualification

