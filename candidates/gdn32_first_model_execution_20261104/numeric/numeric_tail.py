"""Actual same-job build -> ABI -> original providers -> existing comparisons.
Source-only candidate. Requires independently reviewed owning-job binding; no
acquisition/build defaults, no API artifact, no upload, no numerical PASS claim.
"""
import argparse,hashlib,importlib.util,json,os,pathlib,signal,sys,time
import live_budget
import dut_evidence
import required_acceptance
import provider_from_frozen as material
P=pathlib.Path;D=P(__file__).resolve().parent
_policy_spec=importlib.util.spec_from_file_location('samejob_profile_policy', P(__file__).resolve().parent.parent/'profile_policy.py');profile_policy=importlib.util.module_from_spec(_policy_spec);_policy_spec.loader.exec_module(profile_policy)
_mode_spec=importlib.util.spec_from_file_location('samejob_execution_mode',D.parent/'execution_mode.py');execution_mode=importlib.util.module_from_spec(_mode_spec);_mode_spec.loader.exec_module(execution_mode)

def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,v):
 with P(p).open('x') as f:json.dump(v,f,indent=2);f.write('\n')
def module(name,path,pins):
 need(pins.get(str(path))==sha(path),'admitted module');spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def complete(r):
 return (r.get('cleanup_proof') or {}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP' and (r.get('log_capture') or {}).get('pipe_eof_observed')is True and (r.get('log_capture') or {}).get('gzip_finalized')is True

PRELAUNCH_SUPERVISOR_SHA='8a7f08366b449f61ea1f18f87ced95f4b4cade4ec1e8359736e2def44c8da82a'
PRELAUNCH_ERRORS=('ValueError: locked memory gate','ValueError: locked disk gate','ValueError: prelaunch work deadline',
 'ValueError: RSS telemetry source pin','ValueError: exact RSS telemetry policy',
 'ValueError: RSS telemetry V2 opt-in schema','ValueError: finite per-profile RSS raw cap',
 'ValueError: unchanged RSS telemetry 64MiB file cap','ValueError: bounded RSS observation size',
 'ValueError: finite RSS verification verification_wall_seconds','ValueError: finite RSS verification verification_cpu_seconds',
 'ValueError: RSS verification CPU within wall budget')
def prelaunch_rejection(r,run_dir,supervisor_path):
 # This exact supervisor tests these gates before mkdir/Popen. False worker_started
 # alone is insufficient: Popen precedes the leader verification that sets it true.
 if run_dir is None or supervisor_path is None or type(r)is not dict:return False
 fields={'argv','caps','cleanup_proof','elapsed_seconds','errors','limitations','native_exit','observed_cpu_seconds','observed_peak_rss','observed_processes','peak_file_bytes','peak_tree_bytes','reader_join_barrier','scope','status','supervisor_cpu_scope','supervisor_cpu_seconds','worker_started'}
 if set(r)!=fields or r['status']!='FAIL_OR_INCOMPLETE' or r['scope']!='ORIGINAL_PROCESS_GROUP_AND_OBSERVED_DESCENDANTS_ONLY':return False
 if r['worker_started']is not False or r['native_exit']is not None or r['cleanup_proof']is not None or type(r['observed_processes'])is not list or r['observed_processes']!=[]:return False
 if type(r['errors'])is not list or len(r['errors'])!=1 or r['errors'][0]not in PRELAUNCH_ERRORS:return False
 barrier=r['reader_join_barrier']
 if type(barrier)is not dict or set(barrier)!={'complete','alive','reader_finally_done'}or barrier['complete']is not True or barrier['alive']is not False or barrier['reader_finally_done']is not False:return False
 if any(type(r[k])not in(int,float)or r[k]!=0 for k in ('observed_cpu_seconds','observed_peak_rss','peak_file_bytes','peak_tree_bytes')):return False
 try:
  output=P(run_dir);source=P(supervisor_path)
  if not output.is_absolute()or output!=output.resolve()or not output.parent.is_dir()or any(p.is_symlink()for p in(output,*output.parents))or output.exists():return False
  if not source.is_absolute()or source!=source.resolve()or any(p.is_symlink()for p in(source,*source.parents))or not source.is_file()or sha(source)!=PRELAUNCH_SUPERVISOR_SHA:return False
 except (OSError,ValueError,RuntimeError):return False
 return True

def require_cleanup(r,marker,run_dir=None,supervisor_path=None):
 if not complete(r):
  if prelaunch_rejection(r,run_dir,supervisor_path):
   marker=P(marker)
   save(marker.with_name('PRELAUNCH_REJECTED_'+marker.name),dict(status='INCOMPLETE',scope='TRUSTED_SUPERVISOR_PRELAUNCH_REJECTION_NOT_WORKER_CLEANUP',error_category=r['errors'][0].removeprefix('ValueError: '),worker_started=False,run_directory_absent=True,supervisor_sha256=PRELAUNCH_SUPERVISOR_SHA,numerical_pass=False))
   raise ValueError('trusted supervisor rejected before worker launch; INCOMPLETE')
  save(marker,dict(status='HOLD_PARENT_LEASE_NO_CONTINUATION'))
  while True:signal.pause()

def weights(b,i):
 model=('qwen2_1p5b','qwen3_5_0p8b','qwen3_5_0p8b','qwen3_5_35b_a3b','qwen3_5_35b_a3b')[i]
 layer=3 if i in (2,4) else 0
 if not profile_policy.is_selected(b):need(len(b['weights'])==70,'one complete shared70 inventory')
 else:
  profile_policy.require_profile(b,i)
  helper=module('selected_tail_weights',D.parent/'runtime/selected_acquisition.py',b['pins'])
  helper.validate_inventory(b,b['weights'])
 rows=[r for r in b['weights']if r['model']==model and f'.layers.{layer}.'in r['name']]
 need(len(rows)==(12,14,11,18,15)[i],'full block/all experts')
 for r in rows:
  p=material.checked(r['pin']);need(p.is_relative_to(P(b['payload'])),'owning shared payload')

def retained_context(b):
 if 'retained_materials'not in b:return None
 need(b.get('execution_context')=='CLOUD_EXECUTOR_V1','retained references require explicit cloud execution')
 row=b['controller_binding'];path=material.checked(row)
 need(path==path.resolve()and all(not p.is_symlink()for p in(path,*path.parents))and path.stat().st_size<=1<<20,'bounded canonical original invocation binding')
 controller=json.loads(path.read_text())
 profile_policy.require_same(b,controller)
 need(b['pins']==dict(controller['pins'],**{str(path):row['sha256']}),'tail pins are exact controller closure plus its binding')
 for key in ('identity','executor_identity','repo','artifact_manifest','builder_handoff','cloud_budget','execution_approval','retained_materials'):
  need(controller[key]==b[key],'retained tail/controller exact '+key)
 for key in ('executor_adaptation','workspace_loader','model_candidate_review','stage_coverage_budget','p0_provider_reuse','reference_data_reuse','aggregate_tree_cap_bytes'):
  need(controller.get(key)==b.get(key),'retained tail/controller optional '+key)
 if b.get('model_candidate_review')is not None:need(controller['source_pins']==b['source_pins'],'candidate tail/controller exact source catalog')
 budget=module('retained_tail_budget',D.parent/'cloud_budget.py',b['pins']);admitted=budget.admit(controller)
 need(admitted.get('retained_materials')==b['retained_materials'],'retained inputs explicitly approved for current invocation')
 helper=module('retained_tail_materials',D.parent/'runtime/retained_materials.py',b['pins'])
 verified=helper.verify(b['retained_materials'],controller)
 need(verified['payload']==b['payload']and verified['weights']==b['weights']and verified['references']==b['references'],'tail exact revalidated material inputs')
 return verified

def reference_path(b,i,retained):
 row=b['references'][str(i)];path=material.checked(row)
 if retained is None:need(path.is_relative_to(P(b['owner_root'])),'reference belongs to owning job')
 else:
  need(b.get('execution_context')=='CLOUD_EXECUTOR_V1'and 'retained_materials'in b and retained['scope']==('DATA_REFERENCE_ONLY_NOT_NUMERICAL_ABI_OR_RUNTIME_PASS'if b.get('model_candidate_review')is not None else'REVALIDATED_DATA_AND_SOFTWARE_REFERENCES_NOT_RUNTIME_OR_DUT')and retained['references'][str(i)]==row,'reference is exact independently revalidated retained entry')
 return path

def cloud_context(b):
 if b.get('execution_context')!='CLOUD_EXECUTOR_V1':
  need('executor_identity'not in b and 'builder_handoff'not in b,'explicit split context required');return None
 helper=module('cloud_tail_identity',D.parent/'executor_identity.py',b['pins']);identity=helper.verify_current(b['executor_identity'])
 need(b['identity']==identity and b['job_started_monotonic']==identity['started_monotonic'],'actual cloud controller clock')
 admitted=module('cloud_tail_budget',D.parent/'cloud_budget.py',b['pins']).admit(b)
 need(b['reserved_other_owner_bytes']==admitted['reserved_other_owner_bytes']and b['job_budget_seconds']==admitted['job_budget_seconds']and b['rss_bytes']==admitted['dut_rss_bytes']and b['address_space_bytes']==admitted['dut_address_space_bytes'],'actual cloud resource admission')
 need(b['phase_extra_bytes']==admitted['numeric_reserved_increment_bytes']and b['provider_wall_seconds']==admitted['budgets']['provider']and b['consumer_address_space_bytes']==admitted['consumer_address_space_bytes'],'tail role budgets exactly approved')
 need(admitted.get('model_candidate_review')==b.get('model_candidate_review'),'tail exact approved candidate review')
 need(admitted.get('stage_coverage_budget')==b.get('stage_coverage_budget'),'tail exact approved stage coverage budget')
 need(admitted.get('p0_provider_reuse')==b.get('p0_provider_reuse'),'tail exact approved P0 input reuse')
 need(admitted.get('reference_data_reuse')==b.get('reference_data_reuse'),'tail exact approved reference reuse')
 need(b['tree_cap']==admitted.get('aggregate_tree_cap_bytes',live_budget.TREE_CAP),'tail exact approved aggregate tree cap')
 if b.get('reference_data_reuse')is not None:need(b['execution_mode']in(execution_mode.STAGE,execution_mode.FIRST_FAULT) and b.get('model_candidate_review')is not None,'reference reuse only approved candidate stage coverage')
 if b.get('p0_provider_reuse')is not None:need(b['execution_mode']in(execution_mode.STAGE,execution_mode.FIRST_FAULT) and b.get('model_candidate_review')is not None,'P0 reuse only approved candidate stage coverage')
 if b.get('model_candidate_review')is not None:module('tail_model_candidate',D/'candidate_admission.py',b['pins']).verify(b['model_candidate_review'],b)
 need(b['execution_mode']==admitted['execution_mode']and b.get('full_block_budget')==admitted['full_block_budget']and b['calibration_seconds']==admitted['budgets']['calibration_seconds'],'tail approved mode and windows')
 retained_context(b)
 return identity

def verify_reference_with_deadline(b,helper,profile,i,context):
 # No reset or extension: byte verification shares the original controller clock.
 need(0<=time.monotonic()-b['job_started_monotonic']<=b['job_budget_seconds'],'reference verification original job deadline')
 result=helper.verify_materialized(b['references'][str(i)],profile,i,b['reference_data_reuse'],context)
 need(0<=time.monotonic()-b['job_started_monotonic']<=b['job_budget_seconds'],'reference verification exceeded original job deadline')
 return result

def validate(b):
 global execution_mode
 execution_mode=module('selected_full_mode',D/'execution_mode_dispatch.py',b['pins'])if b.get('gdn32_full')is not None else module('legacy_full_mode',D.parent/'execution_mode.py',b['pins'])
 need(b['schema']=='SAME_JOB_FIVE_M128_DIAGNOSTIC_TAIL_V1','explicit samejob tail')
 if b.get('gdn32_full')is not None:module('full_tail_bridge',D/'samejob_gdn32_full.py',b['pins']).require_tail_time(b,execution_mode.admit(b),time.monotonic())
 need(b['profiles']==list(range(5)) and b['tokens']==128 and b['matrix_macs']==4096 and b['vector_lanes']==32,'five fixed full profiles')
 need(b['upload_payloads']is False and b['final_rtl_replay']is False,'local generated Chisel test backend only')
 profile_policy.require_references(b,b['references'])
 cloud=cloud_context(b);admission=execution_mode.admit(b)
 need(b['job_started_monotonic']<=time.monotonic(),'owning job start clock, not reset after build')
 need(sum(execution_mode.profile_reserved_seconds(admission).values())+b['reserved_material_seconds']+b['reserved_cleanup_seconds']+b['reserved_parent_seconds'] <= (b['job_budget_seconds']if cloud is not None else 21000)-(time.monotonic()-b['job_started_monotonic']),'whole five round exceeds remaining job')
 if b.get('gdn32_full',{}).get('lifecycle_policy')=='FIRST_MEANINGFUL_FULL_ATTEMPT':
  need(profile_policy.eligible(b)==[1]and b['reserved_material_seconds']==540 and b['reserved_cleanup_seconds']==330 and b['reserved_parent_seconds']==600,'FIRST exact P1 real callgraph full tail')
 else:need(b['reserved_material_seconds']>=7*b['provider_wall_seconds']+11*120 and b['reserved_cleanup_seconds']>=23*60+5*30 and b['reserved_parent_seconds']>0,'all seven provider/five connect/ABI and twenty-three cleanup plus DUT/parent reservations')
 if admission.get('budget_version')==3 and 'aggregate_tree_cap_bytes'in b:
  need(cloud is not None and type(b['tree_cap'])is int and 0<b['tree_cap']<=live_budget.TREE_CAP,'reviewed ordinary FULL finite aggregate cap')
 elif b.get('reference_data_reuse')is None:need(b['tree_cap']==live_budget.TREE_CAP,'unchanged aggregate tree cap')
 else:need(cloud is not None and b['execution_mode']in(execution_mode.STAGE,execution_mode.FIRST_FAULT) and b['tree_cap']==12_037_043_872,'exact reference-data-only tree reduction')
 for k in ('rss_bytes','address_space_bytes','phase_extra_bytes','provider_wall_seconds'):
  need(type(b[k])is int and b[k]>0,'explicit reviewed resource bound '+k)
 need(b['rss_bytes']<=12*1024**3 and (b['address_space_bytes']>0 if cloud is not None else b['address_space_bytes']>=12*1024**3) and b['address_space_bytes']<=16*1024**3,'runner resource maxima')

CACHE_NAMES=('HOME','HF_HOME','HF_HUB_CACHE','TRANSFORMERS_CACHE','XDG_CACHE_HOME','TORCH_HOME','NUMBA_CACHE_DIR','MPLCONFIGDIR','TMPDIR')
def owned_environment(base,root):
 allowed={'PATH','LANG','LC_ALL','OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'}
 need(set(base)<=allowed,'no inherited credentials/loader/python/cache variables')
 root=P(root);need(not root.exists() and not root.is_symlink(),'fresh watched phase cache root');root.mkdir()
 e=dict(base,PATH='/usr/bin:/bin',LANG='C.UTF-8',LC_ALL='C.UTF-8',PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
 for name in CACHE_NAMES:
  p=root/name.lower();p.mkdir();e[name]=str(p)
 return e

def execution_profiles(b,admission):
 selected=profile_policy.eligible(b)
 if admission.get('budget_version')==3:
  ready=execution_mode.ready_queue_profiles(admission)
  need(selected==ready if profile_policy.is_selected(b)else selected==list(range(5)),'V3 exact preparation selection; registered hardware remains all five')
  return ready
 if admission['mode']==execution_mode.FIRST_FAULT:
  need(selected==list(range(5))and admission.get('diagnostic_profiles')==[0]and type(admission['diagnostic_profiles'][0])is int,'registered hardware unchanged; only integer P0 selected')
  return [0]
 return selected

def execution_command(generated,b,admission,profile):
 if admission.get('budget_version')==3:need(type(profile)is int and profile in execution_mode.ready_queue_profiles(admission),'no launch outside admitted ready set')
 need(generated[1]==str(D/'consumer_owned.py'),'explicit owned consumer handoff')
 need(not any(flag in generated for flag in ('--execution-mode','--calibration-wall-seconds','--full-block-budget','--full-block-budget-sha256','--stage-coverage-budget','--stage-coverage-budget-sha256')),'no stale or duplicate execution mode arguments')
 argv=list(generated)+['--execution-mode',admission['mode']]
 if admission['mode']==execution_mode.CALIBRATION:argv+=['--calibration-wall-seconds',str(admission['profile_seconds'][str(profile)])]
 elif admission['mode']==execution_mode.FIRST_FAULT:
  need(profile==0 and admission.get('diagnostic_profiles')==[0]and b.get('execution_context')=='CLOUD_EXECUTOR_V1'and b.get('full_block_budget')is None and b.get('stage_coverage_budget')is None,'only approved P0 first-fault diagnostic')
 elif admission['mode']==execution_mode.STAGE:
  need(b.get('execution_context')=='CLOUD_EXECUTOR_V1'and b.get('full_block_budget')is None,'stage coverage is cloud-only, not full acceptance')
  budget=b['stage_coverage_budget'];argv+=['--stage-coverage-budget',budget['path'],'--stage-coverage-budget-sha256',budget['sha256']]
 else:
  need(admission['mode']==execution_mode.FULL,'explicit execution mode')
  if b.get('gdn32_full')is None:
   budget=b['full_block_budget'];argv+=['--full-block-budget',budget['path'],'--full-block-budget-sha256',budget['sha256']]
 if b.get('execution_context')=='CLOUD_EXECUTOR_V1':
  invocation=b['controller_binding'];material.checked(invocation)
  flags=('--cloud-binding','--cloud-binding-sha256')
  if any(flag in argv for flag in flags):
   need(all(argv.count(flag)==1 for flag in flags),'exact one paired generated cloud invocation')
   need(all(argv.index(flag)+1<len(argv)for flag in flags),'generated cloud invocation values')
   need(argv[argv.index(flags[0])+1]==invocation['path']and argv[argv.index(flags[1])+1]==invocation['sha256'],'generated cloud invocation unchanged')
  else:argv+=['--cloud-binding',invocation['path'],'--cloud-binding-sha256',invocation['sha256']]
 return argv,execution_mode.consumer_phase_seconds(admission,profile)


def mode_budget_fields(admission):
 if admission.get('budget_version')==3:return dict(full_budget_sha256=admission['reviewed_budget_sha256'],**execution_mode.queue_report_fields(admission))
 if admission['mode']==execution_mode.FIRST_FAULT:return dict(full_budget_sha256=None,stage_budget_sha256=None,first_fault_document_sha256=admission['reviewed_budget_sha256'],diagnostic_profiles=[0],not_selected_profiles=[1,2,3,4])
 if admission['mode']==execution_mode.STAGE:return dict(full_budget_sha256=None,stage_budget_sha256=admission['reviewed_budget_sha256'])
 need(admission['mode']in(execution_mode.CALIBRATION,execution_mode.FULL),'explicit numeric execution mode')
 return dict(full_budget_sha256=admission['reviewed_budget_sha256'])

def report_effective_limits(original,b,admission,profile):
 expected=execution_mode.consumer_limits(original,admission,profile)
 if b.get('execution_context')=='CLOUD_EXECUTOR_V1':
  budget_module=module('cloud_tail_report_budget',D.parent/'cloud_budget.py',b['pins'])
  expected=budget_module.consumer_resource_limits(expected,budget_module.admit(b))
 return expected

def run(b,binding_path,binding_sha):
 validate(b);cloud=cloud_context(b);retained=retained_context(b);admission=execution_mode.admit(b);profile_policy.require_source_pin(b['pins']);pins=dict(b['pins']);pins[str(binding_path)]=binding_sha
 need(pins.get(str(D.parent/'execution_mode.py'))==sha(D.parent/'execution_mode.py'),'execution mode source pin')
 for helper in (('execution_mode_dispatch.py','samejob_gdn32_full.py')if b.get('gdn32_full')is not None else()):need(pins.get(str(D/helper))==sha(D/helper),'new samejob dispatch closure')
 need(not {r['pin']['path']for r in b['weights']} & set(pins),'large payload uses streaming pins, not supervisor read_bytes')
 for p,h in pins.items():need(sha(p)==h,'source pin drift')
 for name in ('supervise_multiroot.py','strict_cleanup.py','lossless_log.py'):
  path=str(P(b['supervisor_dir'])/name);need(pins.get(path)==sha(path),'exact published supervisor closure')
 for name in ('required_acceptance.py','numeric_tail.py','provider_from_frozen.py','locked_phase.py','live_budget.py','consumer_owned.py','dut_evidence.py','runtime_abi_owned.py','connect_owned.py','CONNECTION_OWNED_SOURCE_PINS.json'):
  need(pins.get(str(D/name))==sha(D/name),'controller source pin')
 out=P(b['output']);roots=live_budget.roots_checked(b['owned_roots'])
 for role in ('repo','owner_root','payload'):
  need(any(P(b[role]).resolve().is_relative_to(r)for r in roots),'unwatched required material '+role)
 build_pin=b['builder_handoff']if cloud is not None else b['build_result']
 need(any(P(build_pin['path']).resolve().is_relative_to(r)for r in roots),'unwatched build evidence')
 if cloud is None:
  build=material.checked(b['build_result']);br=json.loads(build.read_text());manifest=material.checked(br['artifact']['manifest']);frozen=json.loads(manifest.read_text())
  proof=module('same_job_proof',D/'local_build_proof.py',pins)
  if b.get('gdn32_full')is not None:module('full_tail_build',D/'samejob_gdn32_full.py',pins).verify_tail_payload(b,manifest,frozen)
  else:proof.verify(build,b['build_result']['sha256'],manifest,sha(manifest),frozen,b['run_id'],b['launch_commit'],b['source_commit'])
 else:
  build=None;manifest=material.checked(b['artifact_manifest']);frozen=json.loads(manifest.read_text())
  candidate=frozen['schema']in('MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1','MODEL_CANDIDATE_FIRST_FAULT_BUILD_ARTIFACT_V1')
  proof=module('split_build_proof',D/('candidate_artifact_handoff.py'if candidate else'artifact_handoff.py'),pins)
  kwargs=dict(executor_adaptation=b.get('executor_adaptation'))
  if candidate:kwargs.update(model_candidate_review=b.get('model_candidate_review'),current_source_pins_pin=b['source_pins'],repo=b['repo'])
  proof.verify(b['builder_handoff']['path'],b['builder_handoff']['sha256'],manifest,sha(manifest),frozen,cloud,**kwargs)
 need(not out.exists() and out.is_relative_to(P(b['owner_root'])),'fresh output inside runtime owner');out.mkdir();(out/'runs').mkdir();(out/'phases').mkdir();(out/'cache_roots').mkdir()
 save(out/'REGISTERED_FIVE.json',dict(execution_policy=profile_policy.checked(b),profiles=b['profiles'],tokens=128,execution_mode=admission['mode'],profile_seconds=admission['profile_seconds'],**mode_budget_fields(admission),scope='CHISEL_EMITTED_SV_SIMULATION_NOT_FINAL_RTL',numeric_pass=False))
 sys.path.insert(0,b['supervisor_dir']);import supervise_multiroot as supervisor
 owner=module('admitted_runtime_owner',P(b['owner_module']),pins)
 owner_doc,_=owner.verify(b['owner_manifest']['path'],b['owner_manifest']['sha256'],b['owner_root'])
 owner_schemas=(('SHARED_SELECTED_RUNTIME_OWNER_FRESH_JOB_V1','IMPORTED_SELECTED_RUNTIME_OWNER_CLOUD_V1')if profile_policy.is_selected(b)and (cloud is not None or b.get('gdn32_full')is not None) else(('SHARED_THREE_RUNTIME_OWNER_FRESH_JOB_V3','IMPORTED_THREE_RUNTIME_OWNER_CLOUD_V1')if cloud is not None else('SHARED_THREE_RUNTIME_OWNER_FRESH_JOB_V3',)))
 need(owner_doc['schema']in owner_schemas and owner_doc['identity']==(cloud if cloud is not None else dict(run_id=b['run_id'],source_commit=b['source_commit'],launch_commit=b['launch_commit'])),'fresh CI owner exact same run/source/launch, never historical V2 receipt')
 profile_policy.require_same(b,owner_doc)
 reference_reuse=None;reference_reuse_context=None;reference_reuse_source_pin=None
 if b.get('reference_data_reuse')is not None:
  reference_reuse=module('tail_reference_data_reuse',D/'reference_data_reuse.py',pins)
  reference_reuse_context={key:b[key]for key in ('repo','artifact_manifest','retained_materials')}
  if admission['mode']==execution_mode.FIRST_FAULT:reference_reuse_context['execution_mode']=execution_mode.FIRST_FAULT
  reference_reuse_source_pin=material.pin(D/'reference_data_reuse.py')
  verified_reference=reference_reuse.verify_metadata(b['reference_data_reuse'],reference_reuse_context)
  need(verified_reference['tree_cap']==b['tree_cap'],'actual reference reuse tree cap')
  need(all(any(P(p).resolve().is_relative_to(r)for r in roots)for p in verified_reference['roots']),'all reference data and evidence watched')
 common=frozen['common'];root=manifest.parent
 allstage=[];dut_records=[]
 def stage(name,argv,seconds=None,accepted=(0,),lease_out=None):
  seconds=seconds or b['provider_wall_seconds'];phase=out/'phases'/(name+'.json');run_dir=out/'runs'/name
  cache_root=out/'cache_roots'/name;e=owned_environment(b['environment'],cache_root)
  dut_profile=int(name[1:-4])if name.endswith('_dut')else None
  telemetry_policy=execution_mode.expected_rss_telemetry_policy(admission,dut_profile)if dut_profile is not None else None
  telemetry_seconds=telemetry_policy['verification_wall_seconds']if telemetry_policy is not None else 0
  admission_seconds=execution_mode.dut_admission_seconds(admission,dut_profile,b['reserved_parent_seconds'])if telemetry_policy is not None else seconds
  body=dict(argv=list(map(str,argv)),pins=pins,owned_roots=b['owned_roots'],extra_bytes=b['phase_extra_bytes'],seconds=admission_seconds,job_started=b['job_started_monotonic'],job_budget_seconds=b['job_budget_seconds']if cloud is not None else 21000,write_file_bytes=128<<20,tree_cap=b['tree_cap'],environment=e,cache_root=str(cache_root),admission_output=str(run_dir/'LIVE_ADMISSION.json'))
  log_disk_bytes=execution_mode.full_v3_log_disk_bytes(admission,dut_profile)if dut_profile is not None else 0
  if log_disk_bytes:
   body['extra_bytes']+=log_disk_bytes
   body['write_file_bytes']=max(body['write_file_bytes'],execution_mode.expected_log_policy(admission,dut_profile)['compressed_bytes'])
  finite_tree=admission.get('budget_version')==3 and 'aggregate_tree_cap_bytes'in b
  if finite_tree:body['preserve_free_8gib']=True
  save(phase,body);localpins=dict(pins);localpins[str(phase)]=sha(phase)
  caps=dict(wall_seconds=seconds+30,cleanup_seconds=30,file_bytes=2<<30,tree_bytes=512<<20,log_bytes=64<<20,raw_log_bytes=128<<20,max_entries=100000,per_process_as_bytes=b['address_space_bytes'],per_process_cpu_seconds=execution_mode.dut_parent_cpu_seconds(admission,int(name[1:-4])) if name.endswith('_dut') else seconds+30,rss_bytes=b['rss_bytes'],cpu_seconds=execution_mode.dut_aggregate_cpu_seconds(admission,dut_profile,seconds)if dut_profile is not None else seconds+30,extra_watch_roots=b['owned_roots'],min_free_disk_bytes=1_500_000_000,watch_tree_bytes=b['tree_cap'])
  if telemetry_policy is not None:caps['rss_telemetry_policy']=telemetry_policy
  if log_disk_bytes:caps['tree_bytes']+=log_disk_bytes
  if log_disk_bytes or finite_tree:caps['min_free_disk_bytes']=8<<30
  if b.get('gdn32_full')is not None:execution_mode.resource_gate(b,'DUT'if dut_profile is not None else'FLOW_STAGE',b['rss_bytes']+(1<<30),8<<30,caps['wall_seconds'])
  if b.get('gdn32_full',{}).get('lifecycle_policy')=='FIRST_MEANINGFUL_FULL_ATTEMPT'and not allstage:
   module('first_numeric_native_deadline',D/'samejob_gdn32_full.py',pins).require_tail_time(b,admission,time.monotonic())
  r=supervisor.execute([b['python'],'-B',str(D/'locked_phase.py'),'--phase',str(phase),'--sha256',sha(phase)],str(run_dir),b['lock'],caps,e,localpins,resource_gate={'min_available_memory':b['rss_bytes']+(1<<30)+(b['reserved_other_owner_bytes']if cloud is not None else 0),'min_disk_free':8<<30})
  save(out/'phases'/(name+'_SUPERVISOR_RETURN.json'),r)
  require_cleanup(r,out/('OWNERSHIP_INCOMPLETE_'+name+'.json'),run_dir,P(supervisor.__file__))
  allstage.append(dict(name=name,native_exit=r['native_exit'],receipt_sha256=sha(run_dir/'RESULT.json')))
  need(r['native_exit']in accepted and not r['errors'],'stage failed; no retry '+name)
  return r
 stable_cache=out/'execution_cache';owned_environment({},stable_cache)
 env_manifest=out/'EXECUTION_ENVIRONMENT.json'
 save(env_manifest,dict(schema='OWNED_EXECUTION_ENVIRONMENT_V1',identity=cloud if cloud is not None else dict(run_id=b['run_id'],source_commit=b['source_commit'],launch_commit=b['launch_commit']),owner_root=b['owner_root'],watched_roots=[b['owner_root']],cache_root=str(stable_cache),cache_paths={k:str(stable_cache/k.lower())for k in CACHE_NAMES}))
 pins[str(env_manifest)]=sha(env_manifest)
 env_args=['--owned-environment',str(env_manifest),'--owned-environment-sha256',sha(env_manifest)]
 if cloud is not None:
  identity_pin=b['executor_identity_pin'];material.checked(identity_pin);need(json.loads(P(identity_pin['path']).read_text())==cloud,'actual executor identity bytes');env_args+=['--executor-identity',identity_pin['path'],'--executor-identity-sha256',identity_pin['sha256']]
 abi_extra=[]
 if b.get('workspace_loader') is not None:
  for name in ('workspace_loader','executor_adaptation'):
   row=b[name];material.checked(row);abi_extra+=['--'+name.replace('_','-'),row['path'],'--'+name.replace('_','-')+'-sha256',row['sha256']]
  abi_extra+=['--artifact-manifest-sha256',sha(manifest)]
 abi=out/'STARTUP_ABI.json';tool=frozen['tool_manifest'];binary=common['binary']
 stage('startup_abi',[b['python'],'-B',str(D/'runtime_abi_owned.py'),'--binary',str(root/binary['path']),'--binary-sha256',binary['sha256'],'--tool-manifest',str(root/tool['path']),'--tool-manifest-sha256',tool['sha256'],'--output',str(abi),'--execute-reviewed-loader-list','--expected-run-id',str(b['run_id']),'--expected-source-commit',b['source_commit'],'--expected-launch-commit',b['launch_commit'],*env_args,*abi_extra],120)
 identity_args=['--artifact-manifest',str(manifest),'--artifact-manifest-sha256',sha(manifest),'--expected-run-id',str(b['run_id']),'--expected-launch-commit',b['launch_commit'],'--expected-source-commit',b['source_commit'],'--local-runtime-abi',str(abi),'--local-runtime-abi-sha256',sha(abi),*env_args]
 if cloud is None:identity_args+=['--local-build-result',str(build),'--local-build-result-sha256',b['build_result']['sha256']]
 else:identity_args+=['--builder-handoff',b['builder_handoff']['path'],'--builder-handoff-sha256',b['builder_handoff']['sha256'],'--cloud-binding',b['controller_binding']['path'],'--cloud-binding-sha256',b['controller_binding']['sha256']]
 for i in execution_profiles(b,admission):
  lease_root=out/f'profile{i}';lease_root.mkdir();profile=lease_root/'material'
  with owner.lease(b['owner_manifest']['path'],b['owner_manifest']['sha256'],b['owner_root'],i,lease_root) as selected:
   weights(b,i)
   runtime=selected[('qwen2','qwen35_08b','qwen35_08b','qwen35_35b','qwen35_35b')[i]]
   ref_path=reference_path(b,i,retained)
   ref_doc=json.loads(ref_path.read_text());need(ref_doc['runtime_receipt_sha256']==runtime['receipt']['sha256']and ref_doc['runtime_source_pins_sha256']==runtime['sidecar']['sha256'],'reference matches actual selected installed runtime/sidecar')
   def provider_stage(label,argv):return stage(f'p{i}_{label}',argv,lease_out=lease_root)
   initialization=out/'phases'/f'p{i}_initialize_input.json'
   initialize_body=dict(repo=b['repo'],materializer=b['materializer'],output=str(profile),profile=i,reference=b['references'][str(i)])
   if reference_reuse is not None:initialize_body.update(reference_data_reuse=b['reference_data_reuse'],reference_reuse_context=reference_reuse_context,reference_reuse_source_pin=reference_reuse_source_pin)
   save(initialization,initialize_body)
   stage(f'p{i}_initialize',[b['python'],'-B',str(D/'provider_from_frozen.py'),'--initialize-binding',str(initialization),'--sha256',sha(initialization)],120,lease_out=lease_root)
   material.prepare(b['repo'],b['materializer'],profile,i,runtime['wrapper'],b['payload'],b['references'][str(i)],provider_stage,pins,p0_provider_reuse=b.get('p0_provider_reuse')if i==0 else None)
   selected_identity_args=list(identity_args)
   if b.get('gdn32_full')is not None:
    full_helper=module('full_profile_binding',D/'samejob_gdn32_full.py',pins);selected_identity_args+=full_helper.write_profile_invocation(b,i,manifest,out/'phases'/f'p{i}_full_invocation.json')
   stage(f'p{i}_connect',[b['python'],'-B',str(D/'connect_owned.py'),'--existing-output',str(profile),'--profile',str(i),*selected_identity_args],120,lease_out=lease_root)
   generated=json.loads((profile/'CONSUMER_ARGV.json').read_text())['consumer_argv']
   generated,outer_seconds=execution_command(generated,b,admission,i)
   if reference_reuse is not None:verify_reference_with_deadline(b,reference_reuse,profile,i,reference_reuse_context)
   dut_outer=stage(f'p{i}_dut',generated,outer_seconds,accepted=(1,2),lease_out=lease_root)
   if reference_reuse is not None:verify_reference_with_deadline(b,reference_reuse,profile,i,reference_reuse_context)
   bundle=profile/'runtime_bundle.v3.json';bundle_doc=json.loads(bundle.read_text());runtime_sha=bundle_doc['profiles'][0]['runtime']['sha256']
   report=json.loads((profile/'dut_result/RESULT.json').read_text())
   expected_log=execution_mode.verify_consumer_admission(admission,report.get('execution_admission'),i)
   evidence_args=(profile/'dut_result',i,sha(manifest),sha(bundle),binary['sha256'],runtime_sha,material.pin(out/'runs'/f'p{i}_dut'/'RESULT.json'))
   if execution_mode.full_v2(admission):
    limits=execution_mode.host_phase_limits(admission,i,'evidence_verification')
    with execution_mode.host_verification_budget(**limits):
     execution_mode.verify_supervisor_telemetry(evidence_args[-1],admission,i,b['supervisor_dir'],b['pins'])
     diagnostic=dut_evidence.verify(*evidence_args,expected_log_policy=expected_log)
   else:diagnostic=dut_evidence.verify(*evidence_args)
   if cloud is not None:
    report=json.loads((profile/'dut_result/RESULT.json').read_text());need(report.get('executor_identity')==cloud and report.get('builder_handoff_sha256')==b['builder_handoff']['sha256'],'actual executor report not builder identity')
    if b.get('executor_adaptation') is not None:need(report.get('executor_adaptation_sha256')==b['executor_adaptation']['sha256']and report.get('workspace_loader_sha256')==b['workspace_loader']['sha256'],'actual executor adapter/loader provenance')
   if admission['mode']in(execution_mode.FULL,execution_mode.STAGE,execution_mode.FIRST_FAULT):
    report=json.loads((profile/'dut_result/RESULT.json').read_text());actual=report['execution_admission']
    need(actual['execution_mode']==admission['mode']and actual['reviewed_budget_sha256']==admission['reviewed_budget_sha256'],'actual consumer full-mode budget identity')
    scope='P0_FIRST_FAULT_READONLY_SAME_FULL_M128_STIMULUS_NOT_NUMERICAL_ACCEPTANCE'if admission['mode']==execution_mode.FIRST_FAULT else'STAGE_COVERAGE_DIAGNOSTIC_NOT_FULL_ACCEPTANCE'if admission['mode']==execution_mode.STAGE else'FULL_BLOCK_ACCEPTANCE_REQUIRED_TERMINAL_AND_REFERENCE'
    need(actual['scope']==scope and actual['outer_cleanup_proof_required']is True,'actual explicit execution scope')
    if admission['mode']==execution_mode.STAGE:need(actual.get('stage_budget_sha256')==admission['reviewed_budget_sha256'],'actual stage coverage budget identity')
    if admission['mode']==execution_mode.FIRST_FAULT:need(actual.get('first_fault_document_sha256')==admission['reviewed_budget_sha256']and actual.get('stage_budget_sha256')is None,'actual first-fault document identity')
    expected_limits=report_effective_limits(actual['original_limits'],b,admission,i)
    need(actual['effective_limits']==expected_limits,'actual full watchdog limits')
   dut_records.append(diagnostic)
   save(out/f'PROFILE_{i}_DIAGNOSTIC.json',diagnostic)
   weights(b,i)
 if b.get('gdn32_full')is not None:
  helper=module('gdn32_full_projection',D/'samejob_gdn32_full.py',pins)
  projections=[helper.project_verified_profile(b,row,frozen)for row in dut_records]
  save(out/'GDN32_PROFILE_JOB_SUMMARIES.json',dict(scope=helper.SCOPE,profile_results=projections,cohort=helper.cohort_summary(projections),all_five_required=True,uploaded_payloads=False))
 qualification=required_acceptance.aggregate(dut_records)
 save(out/'RESULT.json',dict(execution_mode=admission['mode'],**mode_budget_fields(admission),qualification=qualification,execution_policy=profile_policy.checked(b),status=qualification['status'],scope='CHISEL_GENERATED_SIMULATION_BACKEND_NOT_FINAL_RTL',stages=allstage,profiles=b['profiles'],actual_dut_reports=dut_records,numerical_pass=qualification['numerical_pass'],moe_contract='ORIGINAL_TORCH_TOPK_PENDING_SMALL_ID_ACCEPTANCE',uploaded_payloads=False))

def main():
 a=argparse.ArgumentParser();a.add_argument('--binding',type=P,required=True);a.add_argument('--binding-sha256',required=True);v=a.parse_args();need(sha(v.binding)==v.binding_sha256,'independently reviewed binding');run(json.loads(v.binding.read_text()),v.binding.resolve(),v.binding_sha256)
if __name__=='__main__':main()

