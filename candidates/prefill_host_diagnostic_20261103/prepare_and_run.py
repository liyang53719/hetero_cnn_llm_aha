"""Reviewed checkout -> original same-job binding and fresh host contract.
Additive P0 host diagnostic only. No build, download or execution on import.
The original controller owns acquisition/install/build, leases and strict cleanup.
SOURCE_PINS is bound by the separate future launch, not a self-referential hash.
"""
import argparse,hashlib,importlib.util,json,math,os,pathlib,platform,re,shutil,subprocess,sys,time
P=pathlib.Path;D=P(__file__).resolve().parent
MODE='SAME_JOB_P0_M128_HOST_DIAGNOSTIC';SCOPE=MODE+'_NOT_FULL_ACCEPTANCE'
TREE=12_081_306_272
CATALOG='candidates/same_job_execution_20261030/SOURCE_PINS.json'
SOURCE_PARENT='15054841ae1394879e30c1351dab6ded702d7a63'
REL='candidates/prefill_host_diagnostic_20261103/SOURCE_RELATION.json'
REL_SHA='0eb2261d28b1afd49692c40b578659a101a5fd5014655be18ededdc144110ddf'
DRIVER_SHA='e4b23d01ee81a738220512eb24d63b4e323723f686c8af340ad64849a00b5887'
CONTRACT='candidates/same_job_execution_20261030/numeric/MODEL_P0_PREFILL_HOST_PROFILE_SOURCE_CONTRACT.json'
CONTRACT_SHA='634ecd3e0187844b7f97ef7ca9b0d38fdd274960bccc210a2419923164e05c24'
GEN='candidates/prefill_supply_overlap_20261103/GENERATION_CONTRACT.json'
GEN_SHA='d6b8f476cb4f586ff47a44d4f2155891f15e3bac99f56e45039c459093feaabb'
OVERLAY='candidates/prefill_supply_overlap_20261103/MODEL_SOURCE_OVERLAY.json'
OVERLAY_SHA='a43e536bc0d0af808429f0730e4ad5fd6f949f4b4e1deb8194c1518eeacb521b'
REASONS={'original interpreter architecture':'PYTHON_OR_ARCH','P0 original AVX512 contract, no fallback':'CPU_AVX512','original maximum frontend RSS12GiB plus1GiB admission':'MEMAVAILABLE_13GIB','full tree plus unchanged free8GiB prerequisite':'DISK_20671240864','immutable complete source closure':'SOURCE_PIN','original first-step deadline':'CONTROL_DEADLINE'}

def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def hash_value(v):return type(v)is str and re.fullmatch('[0-9a-f]{64}',v)is not None
def unique(pairs):
 d={}
 for k,v in pairs:
  need(k not in d,'duplicate JSON member');d[k]=v
 return d
def regular(p,cap):
 p=P(p);need(p.is_absolute()and p==p.resolve()and p.is_file()and not any(q.is_symlink()for q in(p,*p.parents))and 0<p.stat().st_size<=cap,'bounded canonical file');return p
def read(p,cap=65536):return json.loads(regular(p,cap).read_text(),object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in()).throw(ValueError('nonfinite JSON')))
def pin(p):
 p=regular(p,16<<20);return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def save(p,v):
 with P(p).open('x')as f:json.dump(v,f,sort_keys=True,allow_nan=False);f.write('\n')
def load(name,path,pins):
 path=regular(path,1<<20);need(pins.get(str(path))==sha(path),'actual source module pin')
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def source_closure(repo,expected):
 need(hash_value(expected),'independent source catalog SHA')
 path=regular(repo/CATALOG,2<<20);need(sha(path)==expected,'independently launched source catalog')
 source=read(path,2<<20);need(type(source)is dict and set(source)=={'schema','files'}and source['schema']=='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1','original source closure schema')
 need(type(source['files'])is list and 0<len(source['files'])<=4096,'bounded complete source table');pins={};total=0
 for row in source['files']:
  need(type(row)is dict and set(row)=={'path','bytes','sha256'}and type(row['path'])is str,'exact source row')
  rel=P(row['path']);need(not rel.is_absolute()and '..'not in rel.parts and str(rel)==row['path']and str(rel)not in ('.',CATALOG),'canonical relative source only')
  p=regular(repo/rel,16<<20);key=str(p)
  need(row['path']!='.github/workflows/hetero-five-m128-prefill-supply-build.yml','excluded unapproved build-transfer workflow')
  need(key not in pins and type(row['bytes'])is int and row['bytes']==p.stat().st_size and hash_value(row['sha256'])and sha(p)==row['sha256'],'immutable complete source closure')
  pins[key]=row['sha256'];total+=row['bytes'];need(total<=128<<20,'bounded total source closure')
 pins[str(path)]=expected;py=P(sys.executable).resolve();pins[str(py)]=sha(py)
 for rel,digest in ((REL,REL_SHA),(CONTRACT,CONTRACT_SHA),(GEN,GEN_SHA),(OVERLAY,OVERLAY_SHA)):
  need(pins.get(str(repo/rel))==digest,'exact diagnostic source domain')
 for name in ('prepare_and_run.py','validate_launch.py','run_samejob.py','runtime_budget.py','partial_q_phase.py','host_timing_projection.py'):
  need(str(D/name)in pins and pins[str(D/name)]==sha(D/name),'complete diagnostic entry closure')
 return pins

def diagnostic_fields(repo,pins):
 def checked(rel,digest=None):
  p=repo/rel;row=pin(p);need(pins.get(str(p))==row['sha256']and(digest is None or digest==row['sha256']),'exact diagnostic role pin');return row
 return dict(scope=SCOPE,profiles=[0],hardware_source='prefill-supply-overlap-v1',driver_sha256=DRIVER_SHA,
  source_contract=checked(CONTRACT,CONTRACT_SHA),generation_contract=checked(GEN,GEN_SHA),source_overlay=checked(OVERLAY,OVERLAY_SHA),
  source_catalog=checked(CATALOG),runner=checked('candidates/prefill_host_diagnostic_20261103/run_samejob.py'),wall_seconds=14400,max_active_cycles=3000000,bootstrap_seconds=1800)

def run(a):
 # Adapted from the original same_job_execution/prepare_and_run.py: same actual
 # host gates, packages, binding schema, fresh host contract and controller.run.
 repo=a.repo.resolve(strict=True);work=a.work
 need(repo==a.repo and D==repo/'candidates/prefill_host_diagnostic_20261103','actual checked-out entry')
 identity=read(a.identity);admission=read(a.launch_admission);clock=read(a.job_start)
 need(type(admission)is dict and set(admission)=={'schema','manifest','identity'}and admission['schema']=='SAME_JOB_DIAGNOSTIC_LAUNCH_IDENTITY_V1'and admission['identity']==identity,'same validated launch identity')
 need(set(identity)=={'run_id','source_commit','launch_commit','artifact_name','launch_manifest_path','launch_manifest_blob_sha'},'original exact six-field artifact identity')
 need(os.environ.get('GITHUB_EVENT_NAME')=='push'and os.environ.get('GITHUB_RUN_ATTEMPT')=='1'and str(identity['run_id'])==os.environ.get('GITHUB_RUN_ID')and identity['launch_commit']==os.environ.get('GITHUB_SHA'),'actual first owning job')
 exact(clock,{'schema','job_budget_seconds','run_id','launch_commit','started_monotonic'})
 need(type(identity['run_id'])is int and identity['run_id']>0 and identity['artifact_name']=='hetero-common-dut-'+str(identity['run_id'])and type(identity['launch_manifest_blob_sha'])is str and re.fullmatch('[0-9a-f]{40}',identity['launch_manifest_blob_sha'])is not None,'actual artifact identity values')
 need(clock['schema']=='SAME_JOB_START_V1'and type(clock['job_budget_seconds'])is int and clock['job_budget_seconds']==21000 and clock['run_id']==identity['run_id']and clock['launch_commit']==identity['launch_commit'],'original owning clock identity')
 started=clock['started_monotonic'];need(type(started)in(int,float)and math.isfinite(started)and 0<=time.monotonic()-started<300,'original first-step deadline')
 manifest=admission['manifest'];need(manifest['source_sha']==identity['source_commit']and manifest['source_parent']==SOURCE_PARENT,'same reviewed source parent')
 pins=source_closure(repo,manifest['source_catalog_sha256'])
 validator=load('actual_host_launch_validator',D/'validate_launch.py',pins)
 event=read(P(os.environ['GITHUB_EVENT_PATH']).resolve(),2<<20)
 validator.validate(event,manifest,os.environ['GITHUB_RUN_ATTEMPT'],identity['launch_commit'],identity['source_commit'],'A\t'+identity['launch_manifest_path']+'\n',SOURCE_PARENT)
 need(identity['launch_manifest_path']==validator.LAUNCH,'fixed unique launch path')
 git_env={k:v for k,v in os.environ.items()if k not in ('GH_TOKEN','GITHUB_TOKEN')}
 parents=subprocess.check_output(['git','-C',str(repo),'rev-list','--parents','-n','1','HEAD'],text=True,timeout=15,env=git_env).split()
 need(parents==[identity['source_commit'],SOURCE_PARENT],'actual source checkout and exact parent')
 subprocess.run(['git','-C',str(repo),'diff','--quiet','HEAD','--'],check=True,timeout=15,env=git_env)
 need(not work.exists()and work.is_absolute()and not any(q.is_symlink()for q in(work,*work.parents))and work.parent==P(os.environ['RUNNER_TEMP']).resolve(),'fresh canonical owning tree')
 need(sys.version_info[:2]==(3,12)and platform.machine()=='x86_64','original interpreter architecture')
 samejob=repo/'candidates/same_job_execution_20261030';pipeline=repo/'candidates/ci_frontend_pipeline_r2_20261029';materialization=repo/'candidates/ci_frontend_materialization_r2_20261029'
 need(pins.get(str(samejob/'profile_policy.py'))==sha(samejob/'profile_policy.py'),'profile policy pin before original prepare import')
 base=load('actual_original_prepare',samejob/'prepare_and_run.py',pins);policy=base.profile_policy
 policy.require_source_pin(pins);execution_policy=policy.policy(policy.FULL)
 policy.require_cpu({'execution_policy':execution_policy},P('/proc/cpuinfo').read_text().split())
 memory={line.split(':')[0]:int(line.split()[1])*1024 for line in P('/proc/meminfo').read_text().splitlines()if line.startswith('MemAvailable:')}
 need(memory['MemAvailable']>=13<<30,'original maximum frontend RSS12GiB plus1GiB admission')
 need(shutil.disk_usage(work.parent).free>=TREE+(8<<30),'full tree plus unchanged free8GiB prerequisite')
 gate=load('actual_original_observer_baseline',pipeline/'observer_baseline_gate.py',pins);gate.require_accepted_baseline(materialization)
 fresh=dict(schema='BOUNDED_FRESH_HOST_V1',**{k:identity[k]for k in('run_id','source_commit','launch_commit')})
 host=load('actual_original_fresh_host',materialization/'fresh_host.py',pins);host.validate_contract(fresh,identity);host.reject_injection(os.environ)
 budgets=read(samejob/'BUDGETS.json')
 b=dict(execution_policy=execution_policy,schema='ONE_JOB_FIVE_M128_CHISEL_TEST_CALIBRATION_V1',profiles=list(range(5)),tokens=128,matrix_macs=4096,vector_lanes=32,payload_uploads=False,final_rtl_replay=False,
  identity={k:identity[k]for k in('run_id','source_commit','launch_commit')},artifact_identity=identity,job_started_monotonic=started,repo=str(repo),job_root=str(work),pins=pins,
  runtime_package=str(samejob/'runtime'),numeric_package=str(samejob/'numeric'),python=str(P(sys.executable).resolve()),supervisor_dir=str(pipeline),shared_runtime_helper=str(repo/'candidates/same_job_materialization_20261029/shared_runtime.py'),pipeline=str(pipeline),materialization_dir=str(materialization),materializer=str(repo/'candidates/same_job_materialization_20261029'),dut_rss_bytes=8<<30,numeric_reserved_increment_bytes=512<<20,budgets=budgets,
  execution_mode=MODE,full_block_budget=None,diagnostic_profiles=[0],diagnostic_scope=SCOPE,fresh_host_contract=fresh,
  host_profile_driver=dict(path=str(repo/REL),sha256=REL_SHA),host_diagnostic=diagnostic_fields(repo,pins))
 bridge=load('actual_samejob_diagnostic_admission',samejob/'numeric/samejob_host_diagnostic.py',pins)
 bridge.admit_controller(b) # Real bridge checks before binding write or acquisition.
 flow=load('actual_owning_flow',samejob/'controller/flow.py',pins)
 binding=work.parent/(work.name+'-BINDING.json');save(binding,b)
 return flow.run(b,binding,sha(binding))

PUBLIC_REASONS=frozenset(('JOB_DID_NOT_REACH_VALIDATED_EXPORT','LAUNCH_REJECTED','LAUNCH_OR_CHECKOUT_REJECTED','PYTHON_OR_ARCH','CPU_AVX512','MEMAVAILABLE_13GIB','DISK_20671240864','SOURCE_PIN','CONTROL_DEADLINE','PREPARATION_OR_EXECUTION_REJECTED','EXPORT_SCHEMA_REJECTED','DIAGNOSTIC_RESULT_FAILED','DIAGNOSTIC_TRANSPORT_ONLY'))

def entry_state(path):
 d=read(path,4096);exact(d,{'schema','status','reason_code','execution_mode','numerical_pass','raw_payloads_uploaded'})
 need(d['schema']=='P0_HOST_DIAGNOSTIC_SAFE_ENTRY_V1'and d['execution_mode']==MODE and d['status']in ('NOT_STARTED','FAILED','DIAGNOSTIC_TRANSPORT_ONLY')and d['reason_code']in PUBLIC_REASONS,'typed internal entry state')
 flags(d,('numerical_pass','raw_payloads_uploaded'));return d

def safe_entry(path,reason,status='FAILED'):
 need(reason in PUBLIC_REASONS and status in ('FAILED','DIAGNOSTIC_TRANSPORT_ONLY'),'fixed internal reason/status')
 path=P(path);regular(path,4096)
 try:prior=entry_state(path)
 except Exception:prior=None;reason='EXPORT_SCHEMA_REJECTED';status='FAILED'
 # First concrete failure survives later cleanup/export failures. Internal only.
 if prior is not None and prior['status']=='FAILED':return
 value=dict(schema='P0_HOST_DIAGNOSTIC_SAFE_ENTRY_V1',status=status,reason_code=reason,execution_mode=MODE,numerical_pass=False,raw_payloads_uploaded=False)
 tmp=path.with_suffix('.tmp');save(tmp,value);tmp.replace(path)

def uint(v,cap=(1<<64)-1):need(type(v)is int and 0<=v<=cap,'public bounded integer');return v
def flags(d,names):
 for k in names:need(d.get(k)is False,'no acceptance or payload claim')
def exact(d,keys):need(type(d)is dict and set(d)==set(keys),'exact public output fields')
def result_summary(d):
 common={'status','scope','numerical_pass','full_block_numerical_pass','final_rtl_executed','raw_payloads_uploaded'}
 flags(d,common-{'status','scope'});need(d['scope']==SCOPE and d['status']in ('FAILED_HOST_DIAGNOSTIC','INCOMPLETE_HOST_DIAGNOSTIC'),'bounded diagnostic status')
 if 'reason_code'in d:
  exact(d,common|{'schema','diagnostic_failure','reason_code'});need(d['schema']=='P0_HOST_DIAGNOSTIC_SAFE_FAILURE_V1'and d['status']=='FAILED_HOST_DIAGNOSTIC'and d['diagnostic_failure']is True and d['reason_code']in PUBLIC_REASONS,'fixed safe failure summary');return dict(d)
 if 'error_class'in d:
  exact(d,common|{'diagnostic_failure','error_class','error_sha256'});need(d['status']=='FAILED_HOST_DIAGNOSTIC'and d['diagnostic_failure']is True and hash_value(d['error_sha256']),'typed failure only')
  out=dict(d);out['error_class']=d['error_class']if d['error_class']in ('ValueError','RuntimeError','OSError','FileNotFoundError','KeyError','TimeoutError','MemoryError','AssertionError','KeyboardInterrupt','SystemExit')else 'OTHER';return out
 exact(d,common|{'diagnostic_profiles','registered_profiles','hardware_definitions','window_seconds','active_cycle_cap','artifact_manifest_sha256','runtime_bundle_sha256','phase_summary_sha256','host_timing_sha256'})
 need(d['diagnostic_profiles']==[0]and d['registered_profiles']==list(range(5))and all(type(x)is int for x in d['diagnostic_profiles']+d['registered_profiles']),'fixed profile identities')
 need(uint(d['hardware_definitions'])==1 and 9000<=uint(d['window_seconds'])<=14400 and uint(d['active_cycle_cap'])==3000000,'fixed diagnostic limits')
 for k in ('artifact_manifest_sha256','runtime_bundle_sha256','phase_summary_sha256','host_timing_sha256'):need(hash_value(d[k]),'public exact digest')
 return dict(d)

def host_timing(d):
 exact(d,{'schema','samples','full_coverage','destructor_report_guaranteed','perturbation_measured','source_log_sha256','inclusive_step_not_additive','host_process','termination_receipt_sha256'})
 need(hash_value(d['termination_receipt_sha256']),'actual termination receipt hash')
 process=d['host_process'];exact(process,{'scope','wall_seconds','cpu_seconds','user_cpu_seconds','system_cpu_seconds','native_exit','wall_deadline_triggered','last_logged_active_cycles','last_logged_pc','last_logged_completions','logged_prefix_cycles_per_process_wall_second','rate_is_full_block','rate_is_new_hardware_cycle_utilization','logging_prefix_may_lag_actual'})
 need(process['scope']=='DIRECT_DUT_HOST_PROCESS_INCLUDING_STARTUP_AND_CLEANUP_NOT_RTL_PERFORMANCE','actual process timing scope')
 for k in ('wall_seconds','cpu_seconds','user_cpu_seconds','system_cpu_seconds'):need(type(process[k])in(int,float)and math.isfinite(process[k])and 0<=process[k]<=42000,'bounded finite host process measurement')
 rate=process['logged_prefix_cycles_per_process_wall_second'];need(type(rate)in(int,float)and math.isfinite(rate)and rate>=0,'finite logged prefix rate')
 need(process['wall_seconds']>0 and process['wall_seconds']<=21000 and abs(process['cpu_seconds']-process['user_cpu_seconds']-process['system_cpu_seconds'])<1e-6,'actual time accounting')
 need(type(process['native_exit'])is int and -255<=process['native_exit']<=255 and type(process['wall_deadline_triggered'])is bool,'typed actual termination')
 uint(process['last_logged_active_cycles'],3000000);uint(process['last_logged_pc'],63);uint(process['last_logged_completions'])
 need(abs(process['logged_prefix_cycles_per_process_wall_second']-process['last_logged_active_cycles']/process['wall_seconds'])<1e-6,'logged-prefix rate only')
 flags(process,('rate_is_full_block','rate_is_new_hardware_cycle_utilization'));need(process['logging_prefix_may_lag_actual']is True,'prefix cannot claim full cycle coverage')
 need(d['schema']=='BOUNDED_HOST_TIMING_PROJECTION_V1'and hash_value(d['source_log_sha256'])and d['inclusive_step_not_additive']is True,'host timing scope')
 flags(d,('full_coverage','destructor_report_guaranteed','perturbation_measured'))
 need(type(d['samples'])is list and len(d['samples'])<=64,'bounded host timing samples')
 parts=('eval_low_before','eval_rising','eval_falling','readonly_offer','mutable_offer','readonly_validation','mutable_validation','step')
 nums={'pc','visited','selected','completed_selected','failed_selected','in_flight_selected','sample_log2','invalid_pc_steps','clock_regressions'}|{p+s for p in parts for s in ('_calls','_ns','_max_ns')}
 fixed=dict(scope='SAMPLED_HOST_ELAPSED_NS_NOT_DUT_CPU_OR_RTL_CYCLES',sampling_guarantee='DETERMINISTIC_HASH_SELECTION_NOT_FIXED_COUNT_OR_UNBIASED_CI',clock_overhead_calibrated=False,unmeasured_scope='allocation checks outside read spans; write/stability/collector/output/log costs within Step residual; build/load/reference/finaldump outside Step')
 seen=set()
 for sample in d['samples']:
  exact(sample,nums|set(fixed)|{'reason','unattributed_step_residual_ns'})
  for k in nums:uint(sample[k])
  need(sample['pc']<64 and sample['pc']not in seen and sample['sample_log2']==10 and sample['in_flight_selected']in (0,1),'fixed sample identity');seen.add(sample['pc'])
  need(sample['reason']in ('reset','running','completion','terminal','simulation_destructor')and all(type(sample[k])is type(v)and sample[k]==v for k,v in fixed.items()),'typed timing labels')
  if sample['unattributed_step_residual_ns']is not None:uint(sample['unattributed_step_residual_ns'])
 return d

# PHASE_SUMMARY schema is separately validated below; no raw local projector data.
def phase_summary(d):
 required={'schema','scope','status','termination','termination_state','profile','tokens','numerical_pass','full_block_numerical_pass','final_rtl_executed','integration_status','diagnostic_failure'}
 extra={'qraw','qr','completed_phase_count','phase_closure','bytes_read','termination_source_sha256','artifact_manifest_sha256','runtime_bundle_sha256','outer_result_sha256','source_comparison_sha256','driver_sha256'}
 need(type(d)is dict and required<=set(d)<=required|extra,'exact partial public fields')
 need(d['schema']=='P0_Q_PARTIAL_PUBLIC_SUMMARY_V1'and d['scope']=='PARTIAL_PHASE_NUMERIC_P0_M128_QR_NOT_FULL_BLOCK_OR_FINAL_RTL','partial-only scope')
 need(d['status']in ('PARTIAL_PHASE_NOT_EVALUATED','PARTIAL_PHASE_NUMERIC','PARTIAL_PHASE_NUMERIC_WITH_FAULT','PARTIAL_PHASE_NUMERIC_WITH_RESOURCE_LIMIT'),'fixed partial status')
 need(uint(d['profile'])==0 and uint(d['tokens'])==128 and type(d['diagnostic_failure'])is bool,'fixed partial identity')
 flags(d,('numerical_pass','full_block_numerical_pass','final_rtl_executed'))
 need(d['integration_status']in ('NOT_CONNECTED_TO_REVIEWED_SAMEJOB_SOURCE_CONTEXT_OR_BUILD_PROOF','ACTUAL_SAME_JOB_COMPILATION_SOURCE_ABI_VERIFIED_NO_FULL_ACCEPTANCE'),'typed integration scope')
 states={'TIMEOUT':'INCOMPLETE','WATCHDOG_CYCLE_LIMIT':'INCOMPLETE','FAULT':'FAULT','RESOURCE_LIMIT':'RESOURCE_LIMIT','PROCESS_COMPLETE_NOT_FULL_ACCEPTANCE':'PROCESS_COMPLETE_NOT_FULL_ACCEPTANCE'}
 need(d['termination']in states and d['termination_state']==states[d['termination']],'typed partial termination')
 if d['termination']in ('FAULT','RESOURCE_LIMIT'):need(d['diagnostic_failure']is True,'fault cannot become success')
 for k in extra:
  if k.endswith('_sha256')and k in d:need(hash_value(d[k]),'partial public hash')
 if 'bytes_read'in d:uint(d['bytes_read'],64<<20)
 if 'qraw'not in d:
  need(not({'qr','completed_phase_count','phase_closure'}&set(d))and d['status']=='PARTIAL_PHASE_NOT_EVALUATED','no invented phase');return d
 need({'qr','completed_phase_count','phase_closure'}<=set(d),'paired phase availability')
 size=128*1536*4;completed=[]
 for name,pc in (('qraw',1),('qr',2)):
  item=d[name];need(type(item)is dict and item.get('status')in ('COMPLETED','NOT_REACHED','NOT_CLOSED')and uint(item.get('pc'))==pc,'typed phase availability')
  keys={'pc','status'}
  if item['status']=='COMPLETED':
   completed.append(name)
   if name=='qraw':
    keys|={'bytes','sha256','nonfinite_elements','numerical_comparison_performed'};need(uint(item['bytes'])==size and hash_value(item['sha256'])and item['numerical_comparison_performed']is False,'qraw finite-only');uint(item['nonfinite_elements'],size//4)
   else:
    keys|={'phase_exact_match','comparison'};need(type(item['phase_exact_match'])is bool,'phase comparison flag');c=item['comparison'];exact(c,{'bytes','byte_mismatches','actual_nonfinite_elements','reference_nonfinite_elements','actual_sha256','expected_layout_sha256','first_mismatch_byte'})
    need(uint(c['bytes'])==size and hash_value(c['actual_sha256'])and hash_value(c['expected_layout_sha256']),'comparison hashes')
    for k in ('byte_mismatches','actual_nonfinite_elements','reference_nonfinite_elements'):uint(c[k],size)
    if c['first_mismatch_byte']is not None:uint(c['first_mismatch_byte'],size-1)
    need(item['phase_exact_match']is(c['byte_mismatches']==c['actual_nonfinite_elements']==c['reference_nonfinite_elements']==0),'comparison status')
  exact(item,keys)
 need(uint(d['completed_phase_count'],2)==len(completed)and('qr'not in completed or 'qraw'in completed),'phase count')
 need((d['status']=='PARTIAL_PHASE_NOT_EVALUATED')is(not completed),'phase availability status')
 numeric_failure=('qraw'in completed and d['qraw']['nonfinite_elements']!=0)or('qr'in completed and not d['qr']['phase_exact_match'])
 need(d['diagnostic_failure']is(d['termination']in ('FAULT','RESOURCE_LIMIT')or numeric_failure),'no hidden diagnostic failure')
 need(type(d['phase_closure'])is dict and set(d['phase_closure'])<=set(completed),'closed phases only')
 progress=set('cycles active_cycles pc completions read_bursts read_beats read_acks write_bursts write_beats write_acks write_ack_bytes pipeline_issues pipeline_stalls idma_transfers idma_cache_hits idma_streamed_read_beats idma_streamed_write_beats owner_jobs useful_macs executed_macs host_write_bytes memory_accepted_0 memory_returned_0 memory_accepted_1 memory_returned_1 reset_required'.split())
 for name,row in d['phase_closure'].items():
  exact(row,{'pc','output_cycle','phase_active_cycles','completion','safe_successor'})
  for k in ('pc','output_cycle','phase_active_cycles'):uint(row[k])
  need(row['pc']=={'qraw':1,'qr':2}[name],'closed phase identity')
  for k in ('completion','safe_successor'):
   sample=row[k];exact(sample,progress|{'kind'});need(sample['kind']in ('running','completion','terminal'),'closed progress label')
   for key in progress:uint(sample[key])
 return d

def fresh_export(out,encoded):
 # All inputs are already fully validated in memory. Never reuse a stale export.
 out=P(out);need(out.is_absolute()and not out.exists()and out.parent.is_dir()and not any(p.is_symlink()for p in(out,*out.parents)),'fresh canonical safe export')
 need(set(encoded)<={'RESULT.json','PHASE_SUMMARY.json','HOST_TIMING.json'}and encoded and sum(map(len,encoded.values()))<=1<<20,'only three bounded typed outputs')
 out.mkdir()
 for name,data in encoded.items():
  with(out/name).open('xb')as f:f.write(data)
 return 0

def failure_export(a,reason):
 need(reason in PUBLIC_REASONS,'fixed safe failure reason')
 value=dict(schema='P0_HOST_DIAGNOSTIC_SAFE_FAILURE_V1',status='FAILED_HOST_DIAGNOSTIC',scope=SCOPE,numerical_pass=False,full_block_numerical_pass=False,final_rtl_executed=False,diagnostic_failure=True,reason_code=reason,raw_payloads_uploaded=False)
 result_summary(value)
 return fresh_export(a.safe_export,{'RESULT.json':(json.dumps(value,indent=2,allow_nan=False)+'\n').encode()})

def summarize(a):
 # Only runner-created typed JSON. Never tar/glob a work tree or print raw errors.
 before=entry_state(a.entry_summary)
 if before['status']=='FAILED':return failure_export(a,before['reason_code'])
 origin=a.work/'materials/numeric/export'
 need(origin.is_dir()and origin==origin.resolve()and not any(p.is_symlink()for p in(origin,*origin.parents)),'actual runner export')
 names={p.name for p in origin.iterdir()};allowed={'RESULT.json','PHASE_SUMMARY.json','HOST_TIMING.json'}
 need(names and names<=allowed,'only exact typed runner filenames')
 need(sum(regular(origin/name,1<<20).stat().st_size for name in names)<=1<<20,'total bounded runner export')
 validators={'RESULT.json':result_summary,'PHASE_SUMMARY.json':phase_summary,'HOST_TIMING.json':host_timing}
 values={name:validators[name](read(origin/name,1<<20))for name in sorted(names)}
 result=values.get('RESULT.json');need(result is not None,'no closed result without authoritative failure')
 if 'error_class'not in result and 'reason_code'not in result:
  need(names==allowed,'normal result requires all typed summaries')
  need(values['PHASE_SUMMARY.json']['integration_status']=='ACTUAL_SAME_JOB_COMPILATION_SOURCE_ABI_VERIFIED_NO_FULL_ACCEPTANCE','actual closed same-job source and ABI context')
  need(sha(origin/'PHASE_SUMMARY.json')==result['phase_summary_sha256']and sha(origin/'HOST_TIMING.json')==result['host_timing_sha256'],'runner exact exported summaries')
 encoded={name:(json.dumps(value,indent=2,allow_nan=False)+'\n').encode()for name,value in values.items()}
 if 'error_class'not in result and 'reason_code'not in result:
  # The runner uses this exact serializer. Never silently invalidate linked hashes.
  for name,key in (('PHASE_SUMMARY.json','phase_summary_sha256'),('HOST_TIMING.json','host_timing_sha256')):
   need(hashlib.sha256(encoded[name]).hexdigest()==result[key],'canonical typed summary keeps runner hashes')
 if result['status']=='FAILED_HOST_DIAGNOSTIC':safe_entry(a.entry_summary,'DIAGNOSTIC_RESULT_FAILED')
 else:safe_entry(a.entry_summary,'DIAGNOSTIC_TRANSPORT_ONLY','DIAGNOSTIC_TRANSPORT_ONLY')
 return fresh_export(a.safe_export,encoded)

def cli():
 p=argparse.ArgumentParser();p.add_argument('--summarize',action='store_true')
 for name in ('repo','identity','job-start','launch-admission'):p.add_argument('--'+name,type=P)
 for name in ('work','safe-export','entry-summary'):p.add_argument('--'+name,type=P,required=True)
 a=p.parse_args()
 try:
  if a.summarize:return summarize(a)
  need(all(getattr(a,k)is not None for k in ('repo','identity','job_start','launch_admission')),'explicit owning input paths')
  code=run(a);need(type(code)is int and code in (1,2),'diagnostic transport never acceptance');return code
 except Exception as e:
  reason='EXPORT_SCHEMA_REJECTED'if a.summarize else REASONS.get(str(e),'PREPARATION_OR_EXECUTION_REJECTED')
  try:
   safe_entry(a.entry_summary,reason);reason=entry_state(a.entry_summary)['reason_code']
  except Exception:pass # No arbitrary input escapes through a fallback reason.
  if a.summarize:
   try:return failure_export(a,reason)
   except Exception:return 1 # Failed seal has NO artifact upload, never reuse it.
  return 1
if __name__=='__main__':raise SystemExit(cli())
