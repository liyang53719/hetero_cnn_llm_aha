"""Explicit source-bound GDN32 full M128 same-job bridge. No inherited artifact authority.
Registered five-profile hardware is compiled once per job, even for one selected
profile. All four host phases are reserved. No import-time native work/uploads.
"""
import contextlib,hashlib,importlib.util,json,math,os,pathlib,re,shutil,sys,time
P=pathlib.Path;HERE=P(__file__).resolve().parent
FULL='FULL_BLOCK_ACCEPTANCE';CALIBRATION='BOUNDED_CALIBRATION';STAGE='STAGE_COVERAGE_DIAGNOSTIC';FIRST_FAULT='P0_FIRST_FAULT_DIAGNOSTIC'
SCHEMA='GDN32_FULL_MODEL_SAME_JOB_BINDING_V1';CONTEXT='ADMITTED_SAME_JOB_GDN32_FULL_V1';SCOPE='GDN32_FULL_M128_MODEL_EVALUATION_NOT_FINAL_RTL'
PRODUCER='candidates/gdn32_first_model162_producer_20261104'
SOURCE_CONTRACT_REL='candidates/gdn32_first_model_execution_20261104/numeric/MODEL_P0_GDN32_SOURCE_CONTRACT.json'
SOURCE_CONTRACT_SHA='8ac291f2d129de351a19c95c643437a3600a01d8b40a8e55b5eafabb32975cbc'
GENERATION_SHA='df43bc8f2f68dd993a0e50b9365e68533c5ab404f2787959b27e58460b7d19eb';OVERLAY_SHA='589e1e0f522aae929d25283b180ec566683254862f9537494aec26e2bd27efe1'
HARDWARE_GENERATION='2b2f02d698f16a57ba696c52c4669a1226a68c5378efdc8ebe392cc1b9098f52'
DRIVER_SHA='e8aeaac48a407e27bcbf54db0d85867a904c67a2dce7e1d270999a8482453261'
TREE=12081306272;JOB=21000
HOST_PHASES={'postprocess':1800,'evidence_verification':1800,'summary_verification':3600,'rss_telemetry_verification':1800}
def need(v,s):
 if not v:raise ValueError(s)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pin(row,cap=16<<20):
 need(type(row)is dict and set(row)=={'path','bytes','sha256'},'exact explicit pin')
 p=P(row['path']);need(p.is_absolute()and p==p.resolve()and all(not x.is_symlink()for x in(p,*p.parents))and p.is_file(),'canonical regular file')
 need(type(row['bytes'])is int and 0<=row['bytes']<=cap and p.stat().st_size==row['bytes']and sha(p)==row['sha256'],'exact bounded file bytes');return p
def load(row,cap=16<<20):return json.loads(pin(row,cap).read_text())
def filepin(p):
 p=P(p).resolve();return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def module(path,pins,name):
 p=P(path);need(pins.get(str(p))==sha(p),'fixed executable source '+name)
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
_legacy=None
def legacy():
 global _legacy
 if _legacy is None:
  path=HERE.parent/'execution_mode.py';s=importlib.util.spec_from_file_location('gdn32_unchanged_budget_math',path);_legacy=importlib.util.module_from_spec(s);s.loader.exec_module(_legacy)
 return _legacy
def __getattr__(name):
 # Reuse arithmetic/verification only. No call to legacy.admit for GDN32.
 return getattr(legacy(),name)
def active(b):return b.get('schema')==SCHEMA or b.get('gdn32_full')is not None
def context(c):return type(c)is dict and c.get('schema')==CONTEXT and c.get('candidate_scope')==SCOPE
def finite_long(a):return False

def budget_shape(b):
 d=b['gdn32_full'];selected=d['selected_profiles']
 need(type(selected)is list and selected==sorted(set(selected))and selected and all(type(i)is int and 0<=i<5 for i in selected),'explicit independent selected profiles')
 need(d['registered_profiles']==list(range(5))and d['tokens']==128 and d['hardware_generation_sha256']==HARDWARE_GENERATION,'full fixed hardware source inventory')
 need(d['model_generation_sha256']==GENERATION_SHA and d['source_overlay_sha256']==OVERLAY_SHA and d['source_contract_sha256']==SOURCE_CONTRACT_SHA,'new exact162 model source identity')
 need(d['job_budget_seconds']==JOB and d['scope']==SCOPE and d['completion_guaranteed']is False,'finite same-job model scope')
 need(d['execution_policy']=='FULL_PROGRAM_FINITE_WATCHDOG_NO_SHORT_FALLBACK','full program never shortened diagnostic')
 need(d['lifecycle_policy']in('RESERVE_ALL_CAPS_BEFORE_NATIVE','CONDITIONAL_COMPLETE_TAIL_BEFORE_DUT','FIRST_MEANINGFUL_FULL_ATTEMPT'),'explicit lifecycle policy')
 need(type(d['bootstrap_seconds'])is int and 0<d['bootstrap_seconds']<=1800,'bounded setup within build')
 need(type(d['profiles'])is dict and set(d['profiles'])==set(map(str,selected)),'selected full watchdogs only')
 a=dict(mode=FULL,budget_version=3,budget_contract='FINITE_WATCHDOG_NOT_COMPLETION_ESTIMATE',completion_guaranteed=False,selected_profiles=selected,blocked_profiles={str(i):dict(state='BLOCKED_NOT_RUN',reason='INDEPENDENT_PROFILE_JOB',analysis='No result inferred from another job')for i in range(5)if i not in selected},queue_policy='PARALLEL_INDEPENDENT_FEASIBILITY_NO_PROFILE_COMPLETION_DEPENDENCY',dut_rss_bytes=8<<30,dut_address_space_bytes=12<<30,job_budget_seconds=JOB,bootstrap_seconds=d['bootstrap_seconds'],gdn32_full=True)
 a['log_policy']=dict(legacy().FULL_V2_LOG_POLICY);a['rss_telemetry_policy']=dict(legacy().FULL_V2_RSS_POLICY)
 keys=['seconds','cpu_seconds','max_active_cycles','log_raw_bytes','rss_telemetry_raw_bytes','log_compressed_bytes','rss_telemetry_compressed_bytes']+[phase+'_'+kind+'_seconds'for phase in HOST_PHASES for kind in('wall','cpu')]
 for k in keys:a['profile_'+k]={}
 for i,row in d['profiles'].items():
  need(type(row)is dict and set(row)=={'wall_seconds','cpu_seconds','max_active_cycles','log_raw_bytes','rss_telemetry_raw_bytes','log_compressed_bytes','rss_telemetry_compressed_bytes'}|{p+'_'+k+'_seconds'for p in HOST_PHASES for k in('wall','cpu')},'full lifecycle exact fields')
  need(all(type(v)is int and v>0 for v in row.values()),'positive finite integral caps')
  need(row['max_active_cycles']==1000000000,'original full program cycle ceiling not 3M diagnostic')
  need(row['cpu_seconds']<=row['wall_seconds']<=JOB,'one CPU bounded full watchdog')
  need(row['log_raw_bytes']<=16<<30 and row['rss_telemetry_raw_bytes']<=16<<30 and row['log_compressed_bytes']<=64<<20 and row['rss_telemetry_compressed_bytes']<=64<<20,'original fixed bounded log quotas')
  for phase,seconds in HOST_PHASES.items():need(row[phase+'_wall_seconds']==seconds and row[phase+'_cpu_seconds']==seconds,'preserve reviewed9000 host phase seconds')
  for k in keys:a['profile_'+k][i]=row['wall_seconds'if k=='seconds'else k]
 a['reviewed_budget_sha256']=hashlib.sha256(json.dumps(d,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 legacy().ready_queue_profiles(a)
 return a

def reservations(b,a=None):
 a=a or budget_shape(b);q=b['budgets'];selected=a['selected_profiles'];families=len({('qwen2','qwen35_08b','qwen35_08b','qwen35_35b','qwen35_35b')[i]for i in selected})
 for k in('archives','weights','install','owner_bind','reference','provider','build','parent'):need(type(q[k])is int and q[k]>0,'explicit phase cap')
 need(q['build']==7200 and q['archives']==600 and q['weights']==3600 and q['install']==180 and q['owner_bind']==120 and q['reference']==180 and q['provider']==180 and q['parent']==600,'unchanged original phase caps')
 if first_attempt(b):
  materials=q['archives']+q['weights']+q['install']+q['owner_bind']+q['reference']+5*30
  tail=remaining_after_build(b,a);return materials,tail,materials+q['build']+30+tail
 materials=q['archives']+q['weights']+families*q['install']+q['owner_bind']+len(selected)*q['reference']+11*30
 # Keep original seven provider/eleven connect/23cleanup envelope, do not hide it.
 tail=sum(legacy().profile_reserved_seconds(a).values())+7*q['provider']+11*120+1530+q['parent']
 return materials,tail,materials+q['build']+tail

def remaining_after_build(b,a):
 if first_attempt(b):
  h=first_helper(b)
  return b['gdn32_full']['profiles']['1']['wall_seconds']+h.FIXED_TAIL_SECONDS if 'first_meaningful_derivation'in b else h.remaining_after_build(h.validate_policy(b['gdn32_full']['first_attempt']))
 q=b['budgets'];families=len({('qwen2','qwen35_08b','qwen35_08b','qwen35_35b','qwen35_35b')[i]for i in a['selected_profiles']})
 return q['weights']+max(0,families-1)*q['install']+q['owner_bind']+len(a['selected_profiles'])*q['reference']+9*30+reservations(b,a)[1]

def admit_controller(b):
 need(b['schema']==SCHEMA and b['execution_mode']==FULL and b['profiles']==list(range(5))and b['tokens']==128 and b['matrix_macs']==4096 and b['vector_lanes']==32,'explicit full five hardware identity')
 need(b['payload_uploads']is False and b['final_rtl_replay']is False,'simulation only no uploads')
 need(all(b.get(k)is None for k in('cloud_binding','builder_handoff','model_candidate_review','host_diagnostic','host_profile_driver','finite_long_policy','stage_coverage_budget')),'no borrowed old approval domain')
 a=budget_shape(b);repo=P(b['repo']);pins=b['pins']
 if first_attempt(b):verify_first_controller(b)
 for rel,want in[(PRODUCER+'/GENERATION_CONTRACT.json',GENERATION_SHA),(PRODUCER+'/MODEL_SOURCE_OVERLAY.json',OVERLAY_SHA),(SOURCE_CONTRACT_REL,SOURCE_CONTRACT_SHA)]:need(pins.get(str(repo/rel))==want and sha(repo/rel)==want,'exact source contract closure')
 need(pins.get(str(HERE))is None and pins.get(str(P(__file__).resolve()))==sha(__file__),'explicit bridge module pin')
 need(b['dut_rss_bytes']==8<<30 and b['numeric_reserved_increment_bytes']==512<<20,'ordinary samejob memory unchanged no cloud alias')
 total=reservations(b,a)[2]
 if b['gdn32_full']['lifecycle_policy']=='RESERVE_ALL_CAPS_BEFORE_NATIVE':need(total<=JOB,'FULL_LIFECYCLE_CAPS_EXCEED_JOB_NO_NATIVE')
 a['maximum_phase_caps_seconds']=total;a['all_caps_fit_job']=total<=JOB
 return a

def admit(b):
 if b.get('schema')==SCHEMA:return admit_controller(b)
 if b.get('gdn32_full')is not None:
  c=load(b['controller_binding']);a=admit_controller(c);need(b['gdn32_full']==c['gdn32_full']and b['job_started_monotonic']==c['job_started_monotonic'],'same full controller and original clock');return a
 return legacy().admit(b)

def require_tail_time(b,a,now):
 need(type(now)in(int,float)and math.isfinite(now),'finite observed clock')
 if first_attempt(b):
  c=load(b['controller_binding']);h=first_helper(c);first_handoff(c,b.get('first_attempt_handoff'));need(0<=now-c['first_meaningful_derivation']['freeze_monotonic']<=h.CONTROL_SECONDS,'FIRST_POST_FREEZE_CONTROL_WINDOW_EXPIRED')
 remaining=JOB-(now-b['job_started_monotonic']);required=sum(legacy().profile_reserved_seconds(a).values())+b['reserved_material_seconds']+b['reserved_cleanup_seconds']+b['reserved_parent_seconds']
 need(remaining>=required,'INSUFFICIENT_COMPLETE_FULL_TAIL_NO_DUT_START');return required

def load_binding(args):
 path=getattr(args,'samejob_full_binding',None);digest=getattr(args,'samejob_full_binding_sha256',None);need(path is not None and digest is not None,'paired full same-job invocation')
 row=dict(path=str(path),bytes=P(path).stat().st_size,sha256=digest);b=load(row);c=load(b['controller_binding']);a=admit_controller(c)
 if first_attempt(c):first_handoff(c,b.get('first_attempt_handoff'))
 need(b['schema']=='GDN32_FULL_PROFILE_INVOCATION_V1'and b['profile']==args.profile and args.profile in a['selected_profiles'],'exact selected full profile')
 need(b['identity']==c['artifact_identity']and b['repo']==c['repo']and b['job_root']==c['job_root']and b['gdn32_full']==c['gdn32_full'],'exact owning source/controller')
 need(b['pins']==dict(c['pins'],**{b['controller_binding']['path']:b['controller_binding']['sha256']}),'exact controller closure plus binding')
 need(str(b['identity']['run_id'])==os.environ.get('GITHUB_RUN_ID')and b['identity']['launch_commit']==os.environ.get('GITHUB_SHA')and os.environ.get('GITHUB_RUN_ATTEMPT')=='1','actual first same-job identity')
 need(args.expected_run_id==b['identity']['run_id']and args.expected_source_commit==b['identity']['source_commit']and args.expected_launch_commit==b['identity']['launch_commit'],'actual builder expectation')
 need(str(args.artifact_manifest)==b['artifact_manifest']['path']and args.artifact_manifest_sha256==b['artifact_manifest']['sha256']and str(args.local_build_result)==b['build_result']['path']and args.local_build_result_sha256==b['build_result']['sha256'],'actual local build handoff')
 need(P(path).is_relative_to(P(b['job_root']))and 0<=time.monotonic()-c['job_started_monotonic']<JOB,'local binding original lifecycle')
 need(all(getattr(args,k,None)is None for k in('cloud_binding','samejob_diagnostic_binding','builder_handoff','stage_coverage_budget','calibration_wall_seconds')),'no foreign runtime authority')
 return b,row,a

@contextlib.contextmanager
def producer_imports(repo,pins):
 root=P(repo)/PRODUCER;names=('first_fault_policy','finite_watchdog_policy','host_profile_policy','first_fault_probe','terminal_finite_probe','first_fault_compilation','candidate_generation_gate','model_source_evidence','candidate_dependency_proof','model162_driver_policy')
 previous={n:sys.modules.get(n)for n in names};oldpath=list(sys.path)
 try:
  sys.path.insert(0,str(root))
  for name in names:
   p=root/(name+'.py')
   if not p.exists():p=P(repo)/'candidates/model_candidate_build_20261101'/(name+'.py')
   sys.modules[name]=module(p,pins,'gdn32_producer_'+name)
  yield root
 finally:
  sys.path[:]=oldpath
  for name,m in previous.items():
   if m is None:sys.modules.pop(name,None)
   else:sys.modules[name]=m

def verify_candidate_payload(root,identity,digest,repo,pins):
 with producer_imports(repo,pins)as source:
  pack=module(source/'pack_model_candidate.py',pins,'gdn32_actual_pack')
  return pack.verify_candidate_seven(root,identity,digest)

def verify_build(args,frozen):
 b,row,a=load_binding(args);artifact=pin(b['artifact_manifest'],65536);resultpath=pin(b['build_result'],65536);r=json.loads(resultpath.read_text())
 need(resultpath==P(b['job_root'])/'build/frontend/BUILD_ONLY_RESULT.json'and artifact==resultpath.parent/'model_candidate_artifact/frozen_artifact.json','same freshly built local tree')
 need(r['artifact']['manifest']==b['artifact_manifest']and frozen==json.loads(artifact.read_text())and frozen['artifact_identity']==b['identity'],'actual producer identity no fabricated PASS')
 need(frozen['schema']=='MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1'and frozen['profiles']==list(range(5))and frozen['common']['driver']['sha256']==DRIVER_SHA,'full registered hardware original driver')
 proof=verify_candidate_payload(artifact.parent,b['identity'],b['artifact_manifest']['sha256'],b['repo'],b['pins'])
 need(proof['files']==7 and proof['numerical_pass']is False and proof['final_rtl_replay']is False,'model build is not numerical acceptance')
 expected=b['gdn32_full'].get('expected_cohort_sv_sha256');actual=frozen['common']['sv']['sha256']
 need(expected is None or re.fullmatch('[0-9a-f]{64}',expected)is not None and actual==expected,'same SV cohort across independent full jobs')
 return dict(status='GDN32_SAME_JOB_STRUCTURAL_BUILD_VERIFIED_NOT_NUMERICAL',scope=SCOPE,artifact_manifest_sha256=b['artifact_manifest']['sha256'],controller_binding_sha256=b['controller_binding']['sha256'],compilation=proof,sv_sha256=actual,cohort_sv_established=expected is not None,numerical_pass=False)

def source_context(args,frozen):
 b,row,a=load_binding(args);proof=verify_build(args,frozen);root=P(b['artifact_manifest']['path']).parent;sr=frozen['common']['source_manifest'];s=load(dict(sr,path=str(root/sr['path'])))
 closure=s['model_candidate_observation']['source_closure'];need(closure['generation_contract_sha256']==GENERATION_SHA and closure['source_overlay']['sha256']==OVERLAY_SHA and closure['source_count']==162,'actual new162 structural source closure')
 need(s['driver_sha256']==DRIVER_SHA and 'readonly_probe'not in s and 'finite_watchdog_driver'not in s,'ordinary original full numerical driver')
 contract=filepin(P(b['repo'])/SOURCE_CONTRACT_REL);need(contract['sha256']==SOURCE_CONTRACT_SHA and s['model_source_evidence']['contract']['sha256']==SOURCE_CONTRACT_SHA,'actual source evidence fixed contract')
 checker=HERE/'candidate_observation_contract.py';catalog=b['gdn32_full']['source_catalog'];pin(catalog,4<<20)
 result=dict(schema=CONTEXT,candidate_scope=SCOPE,full_binding=row,controller_binding=b['controller_binding'],artifact_manifest=b['artifact_manifest'],source_manifest_sha256=sr['sha256'],model_source_contract=contract,builder_identity=b['identity'],repo=b['repo'],current_source_pins_pin=catalog,candidate_observation_checker=filepin(checker),builder_source_commit=b['identity']['source_commit'],artifact_manifest_sha256=b['artifact_manifest']['sha256'],anchors={},local_build_proof=proof)
 m=module(checker,b['pins'],'gdn32_source_observer');result['anchors']=m.relocation_records(s,b['repo'],b['pins'],load(catalog,4<<20),result)
 need(all(x['origin_path']==x['local']['path']for x in result['anchors'].values()),'same-job exact source paths');return result

def admitted_context(c):
 need(context(c),'explicit new full source authority');b=load(c['full_binding']);controller=load(b['controller_binding']);admit_controller(controller)
 if first_attempt(controller):first_handoff(controller,b.get('first_attempt_handoff'))
 need(b['schema']=='GDN32_FULL_PROFILE_INVOCATION_V1'and b['gdn32_full']==controller['gdn32_full']and b['artifact_manifest']==c['artifact_manifest']and b['identity']==c['builder_identity'],'same immutable full invocation')
 need(c['model_source_contract']['sha256']==SOURCE_CONTRACT_SHA and c['current_source_pins_pin']==controller['gdn32_full']['source_catalog'],'full source catalog exact');return b

def verify_tail_payload(b,manifest,frozen):
 c=load(b['controller_binding']);a=admit_controller(c)
 need(b['gdn32_full']==c['gdn32_full']and b['job_started_monotonic']==c['job_started_monotonic'],'same full tail controller')
 require_tail_time(b,a,time.monotonic())
 need(frozen['artifact_identity']==c['artifact_identity']and frozen['profiles']==list(range(5)),'one hardware all profiles fresh owning artifact')
 root=P(manifest).parent;proof=verify_candidate_payload(root,frozen['artifact_identity'],sha(manifest),b['repo'],b['pins'])
 need(proof['files']==7 and proof['numerical_pass']is False and proof['final_rtl_replay']is False,'actual producer structural verification not PASS')
 sr=frozen['common']['source_manifest'];source=load(dict(sr,path=str(root/sr['path'])))
 closure=source['model_candidate_observation']['source_closure'];need(closure['source_count']==162 and closure['generation_contract_sha256']==GENERATION_SHA and closure['source_overlay']['sha256']==OVERLAY_SHA,'actual162 normalized source proof')
 need(source['model_source_evidence']['contract']['sha256']==SOURCE_CONTRACT_SHA and frozen['common']['driver']['sha256']==DRIVER_SHA,'new reviewed driver and source roles')
 expected=b['gdn32_full'].get('expected_cohort_sv_sha256')
 need(expected is None or frozen['common']['sv']['sha256']==expected,'cross-job actual SV cohort mismatch')
 return proof

def write_profile_invocation(b,i,manifest,path):
 c=load(b['controller_binding']);a=admit_controller(c);need(i in a['selected_profiles'],'selected independent profile only')
 need(b['gdn32_full']==c['gdn32_full'],'immutable selected scope')
 row=dict(schema='GDN32_FULL_PROFILE_INVOCATION_V1',profile=i,controller_binding=b['controller_binding'],gdn32_full=c['gdn32_full'],identity=c['artifact_identity'],repo=c['repo'],job_root=c['job_root'],job_started_monotonic=c['job_started_monotonic'],artifact_manifest=filepin(manifest),build_result=b['build_result'],pins=dict(c['pins'],**{b['controller_binding']['path']:b['controller_binding']['sha256']}))
 if first_attempt(c):row['first_attempt_handoff']=first_handoff(c,b.get('first_attempt_handoff'))
 path=P(path);need(path.is_relative_to(P(c['job_root']))and not path.exists(),'fresh local exact full invocation')
 with path.open('x')as f:json.dump(row,f,sort_keys=True)
 return ['--samejob-full-binding',str(path),'--samejob-full-binding-sha256',sha(path)]

def cohort_summary(records):
 """Project already verified owning-job results; never assert absent profiles.
 Caller must bind each record to its actual run/source/launch safe summary.
 No binary identity equality is assumed across separately linked binaries.
 """
 need(type(records)is list and len(records)<=5,'at most five completed profile jobs')
 profiles={};sv=set()
 for r in records:
  need(type(r)is dict and r.get('schema')=='GDN32_VERIFIED_PROFILE_JOB_SUMMARY_V1','exact actual job projection')
  i=r['profile'];need(type(i)is int and 0<=i<5 and i not in profiles,'unique profile result')
  need(r['hardware_generation_sha256']==HARDWARE_GENERATION and r['model_generation_sha256']==GENERATION_SHA and r['driver_sha256']==DRIVER_SHA and r['tokens']==128 and r['matrix_macs']==4096 and r['vector_lanes']==32 and r['typed_ports']==122,'same full hardware interface and capacity')
  need(re.fullmatch('[0-9a-f]{64}',r['sv_sha256'])is not None and r['final_rtl_acceptance']is False,'actual generated model SV digest, not finalRTL')
  need(r['status']in('PASS_FULL128_EXACT_REFERENCE','FAIL_EXACT_REFERENCE','INCOMPLETE'),'actual full profile status')
  sv.add(r['sv_sha256']);profiles[i]=r
 need(len(sv)<=1,'SAME_GENERATED_SV_HASH_REQUIRED_ACROSS_PROFILES')
 complete=set(profiles)==set(range(5))and all(r['status']=='PASS_FULL128_EXACT_REFERENCE'and r['outer_cleanup_verified']is True for r in records)
 return dict(scope=SCOPE,profiles_observed=sorted(profiles),profiles_missing=[i for i in range(5)if i not in profiles],sv_sha256=next(iter(sv))if sv else None,same_binary_claim=False,status='PASS_FIVE_FULL128_EXACT_REFERENCE'if complete else'FAIL_EXACT_REFERENCE'if any(r['status']=='FAIL_EXACT_REFERENCE'for r in records)else'INCOMPLETE',numerical_pass=complete,final_rtl_acceptance=False)

def build_window(b,a,now,prebuild_seconds=0):
 """Never enlarge7200. Conditional mode consumes only unreserved actual slack."""
 need(type(now)in(int,float)and math.isfinite(now),'finite current build clock')
 if first_attempt(b):return first_build_window(b,now,prebuild_seconds)
 elapsed=now-b['job_started_monotonic'];need(0<=elapsed<JOB,'original whole-job clock')
 need(type(prebuild_seconds)is int and prebuild_seconds>=0,'explicit remaining prebuild reservation')
 left=math.floor(JOB-elapsed-remaining_after_build(b,a)-prebuild_seconds)
 if b['gdn32_full']['lifecycle_policy']=='RESERVE_ALL_CAPS_BEFORE_NATIVE':need(left>=b['budgets']['build'],'declared full build plus complete tail does not fit')
 effective=min(b['budgets']['build'],left)
 need(effective>=a['bootstrap_seconds'],'INSUFFICIENT_COMPLETE_TAIL_AND_BUILD_WINDOW_NO_NATIVE')
 return effective


def resource_gate(b,phase,min_memory,min_disk,stage_seconds):
 """Fresh bounded observations before native work; summary contains no paths.
 Initial gate keeps13GiB/20.67GB. Later gates preserve their own original
 stage lease, separately from continuous1.5GB supervisor floor.
 """
 allowed={'INITIAL','MODEL_BUILD','ARCHIVES','WEIGHTS','INSTALL','OWNER_BIND','REFERENCE','PROVIDER','CONNECT','DUT','POSTPROCESS','EVIDENCE','SUMMARY','RSS_TELEMETRY','FLOW_STAGE'}
 need(phase in allowed,'fixed resource phase')
 need(all(type(v)is int and v>0 for v in(min_memory,min_disk,stage_seconds)),'positive finite resource requirements')
 if b.get('schema')!=SCHEMA:b=load(b['controller_binding'])
 a=admit_controller(b);remaining=math.floor(JOB-(time.monotonic()-b['job_started_monotonic']))
 tail=remaining_after_build(b,a)if first_attempt(b)else sum(legacy().profile_reserved_seconds(a).values())+7*b['budgets']['provider']+11*120+1530+b['budgets']['parent']
 record=dict(schema='GDN32_FRESH_RESOURCE_GATE_V1',phase=phase,status='REFUSED',code='OBSERVATION_UNAVAILABLE',mem_total_bytes=None,mem_available_bytes=None,disk_free_bytes=None,required_memory_bytes=min_memory,required_disk_bytes=min_disk,tree_reserved_bytes=TREE,supervisor_runtime_disk_floor_bytes=1500000000,remaining_wall_seconds=remaining,declared_stage_wall_seconds=stage_seconds,complete_numeric_tail_reserved_seconds=tail,native_started_by_gate=False)
 try:
  mem={line.split(':')[0]:int(line.split()[1])*1024 for line in P('/proc/meminfo').read_text().splitlines()if line.startswith(('MemTotal:','MemAvailable:'))}
  record.update(mem_total_bytes=mem['MemTotal'],mem_available_bytes=mem['MemAvailable'],disk_free_bytes=shutil.disk_usage(P(b['job_root']).parent).free)
  code='MEMORY_TOTAL'if mem['MemTotal']<min_memory else'MEMORY_AVAILABLE'if mem['MemAvailable']<min_memory else'DISK_FREE'if record['disk_free_bytes']<min_disk else'JOB_WALL'if remaining<stage_seconds else'OK'
  record.update(code=code,status='ADMITTED'if code=='OK'else'REFUSED')
 except(OSError,ValueError,KeyError,IndexError):pass
 print(json.dumps(record,sort_keys=True),flush=True)
 need(record['status']=='ADMITTED','GDN32_RESOURCE_'+record['code'])
 return record

def project_verified_profile(b,record,frozen):
 """Called only after unchanged dut_evidence.verify; recheck pinned report/outer.
 Local raw receipts stay in job. Returned projection is safe summary only.
 """
 c=load(b['controller_binding']);a=admit_controller(c);i=record['profile'];need(i in a['selected_profiles'],'selected observed profile')
 report=load(record['report']);outer=load(record['outer']);load(record['startup'])
 need(outer.get('worker_started')is True and outer.get('errors')==[] and outer.get('native_exit')in(1,2),'actual outer terminal receipt')
 clean=outer.get('cleanup_proof')or{};capture=outer.get('log_capture')or{}
 need(clean.get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'and capture.get('pipe_eof_observed')is True and capture.get('gzip_finalized')is True,'actual complete cleanup and log')
 acceptance=module(HERE/'required_acceptance.py',b['pins'],'gdn32_project_acceptance')
 need(len(report['profiles'])==1 and report['profiles'][0]['profile']==i,'actual single full profile report')
 q=acceptance.evaluate(report['profiles'][0],outer_verified=True);need(q==record['qualification'],'recomputed exact reference qualification')
 common=record['common_artifact_identity'];need(common['driver_sha256']==DRIVER_SHA and common['sv_sha256']==frozen['common']['sv']['sha256']and common['binary_sha256']==frozen['common']['binary']['sha256'],'actual same local build identity')
 return dict(schema='GDN32_VERIFIED_PROFILE_JOB_SUMMARY_V1',profile=i,identity=c['artifact_identity'],hardware_generation_sha256=HARDWARE_GENERATION,model_generation_sha256=GENERATION_SHA,driver_sha256=DRIVER_SHA,tokens=128,matrix_macs=4096,vector_lanes=32,typed_ports=122,sv_sha256=common['sv_sha256'],binary_sha256=common['binary_sha256'],artifact_manifest_sha256=common['artifact_manifest_sha256'],status=q['status'],outer_cleanup_verified=True,report_sha256=record['report']['sha256'],outer_receipt_sha256=record['outer']['sha256'],final_rtl_acceptance=False)

def require_consumer_window(args,now):
 """Direct CLI re-entry cannot bypass complete remaining lifecycle gate."""
 b,row,a=load_binding(args);c=load(b['controller_binding']);i=args.profile
 if first_attempt(c):need('first_meaningful_derivation'in c,'FIRST_RUNTIME_NOT_FROZEN')
 required=legacy().profile_reserved_seconds(a)[str(i)]+c['budgets']['parent']+60
 remaining=JOB-(now-c['job_started_monotonic'])
 record=dict(schema='GDN32_CONSUMER_DEADLINE_V1',phase='DUT_PRE_EXECUTE',remaining_wall_seconds=math.floor(remaining),complete_profile_and_parent_reserved_seconds=required,status='ADMITTED'if remaining>=required else'REFUSED',native_started=False)
 print(json.dumps(record,sort_keys=True),flush=True)
 need(remaining>=required,'INSUFFICIENT_FULL_PROFILE_AND_HOST_TAIL_NO_DUT_START')
 resource_gate(c,'DUT',9<<30,8<<30,required)
 if first_attempt(c):claim_first_dut(b,time.monotonic())
 return required


_first_cached=None
def first_attempt(b):return type(b.get('gdn32_full'))is dict and b['gdn32_full'].get('lifecycle_policy')=='FIRST_MEANINGFUL_FULL_ATTEMPT'
def first_clock_id():return P('/proc/sys/kernel/random/boot_id').read_text().strip()
def first_helper(b):
 global _first_cached
 path=HERE/'first_meaningful_attempt.py';need(b['pins'].get(str(path))==sha(path),'FIRST source helper pin')
 if _first_cached is None:
  spec=importlib.util.spec_from_file_location('gdn32_first_budget_pinned',path);m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m);_first_cached=m
 return _first_cached

def first_root_path(b):
 job=P(b['job_root']);return job.parent/(job.name+'-BINDING.json')
def first_verification(b,now,handoff):
 h=first_helper(b);first_handoff(b,handoff);root=h.Pin.parse(handoff['root']);admission=h.Pin.parse(handoff['admission']);build=h.Pin.parse(handoff['build']);need(root.path==str(first_root_path(b)),'FIRST fixed original root path')
 return dict(expected_root_pin=root,expected_build_admission_pin=admission,expected_build_result_pin=build,clock_id=first_clock_id(),observed_monotonic=now,last_observed_monotonic=b['first_meaningful_derivation']['freeze_monotonic'])
def verify_first_controller(b):
 h=first_helper(b);need(b['first_attempt_clock_id']==first_clock_id(),'FIRST original monotonic epoch')
 if 'first_meaningful_derivation'not in b:return h.validate_root(b)
 pin=h.file_pin(P(b['job_root'])/'bindings'/h.DERIVED_FILENAME)
 d=b['first_meaningful_derivation'];internal=dict(root=d['parent_controller'],admission=d['build_admission'],build=d['build_result'])
 # Structural recomputation only; actual consumer independently supplies owning handoff.
 h.verify_derived_document(b,expected_derived_pin=pin,**first_verification(b,time.monotonic(),internal));return h.validate_policy(b['gdn32_full']['first_attempt'])
def first_build_window(b,now,prebuild_seconds):
 h=first_helper(b);need('first_meaningful_derivation'not in b,'FIRST no build after runtime frozen')
 path=P(b['job_root'])/'bindings'/h.BUILD_FILENAME
 if not path.exists():return h.build_window(b,now,last_observed_monotonic=b['job_started_monotonic'])
 admission=h._verify_build_admission(b,h.file_pin(first_root_path(b)),h.file_pin(path))
 cap=min(admission['effective_build_seconds'],math.floor(JOB-(now-b['job_started_monotonic'])-remaining_after_build(b,None)-prebuild_seconds))
 policy=h.validate_policy(b['gdn32_full']['first_attempt']);need(cap>=policy.min_build_window_seconds,'FIRST_NO_REVIEWED_BUILD_WINDOW');return cap

def first_budget_summary(b,phase,now,status,code,seconds=None):
 h=first_helper(b);policy=h.validate_policy(b['gdn32_full']['first_attempt'])
 row=dict(schema='GDN32_FIRST_WINDOW_GATE_V1',phase=phase,status=status,code=code,remaining_wall_seconds=math.floor(JOB-(now-b['job_started_monotonic'])),fixed_tail_seconds=h.FIXED_TAIL_SECONDS,census_reserved_seconds=h.CENSUS_SECONDS,post_freeze_control_seconds=h.CONTROL_SECONDS,min_dut_wall_seconds=policy.min_dut_wall_seconds,max_dut_wall_seconds=policy.max_dut_wall_seconds,min_build_window_seconds=policy.min_build_window_seconds,derived_stage_seconds=seconds,native_started_by_gate=False)
 print(json.dumps(row,sort_keys=True),flush=True)
def begin_first_build(b,root_pin,materials,reference,now):
 h=first_helper(b);root=h.Pin.parse(root_pin);need(root.path==str(first_root_path(b)),'FIRST fixed owning root');h.read_json(root)
 try:
  row=h.begin_build(root,material_reference_pins={'materials':materials,'reference':reference},clock_id=first_clock_id(),observed_monotonic=now,last_observed_monotonic=b['job_started_monotonic']).row()
 except (ValueError,OSError):
  first_budget_summary(b,'FIRST_BUILD_ADMISSION',now,'REFUSED','BUILD_WINDOW_OR_IMMUTABLE_BINDING');raise
 first_budget_summary(b,'FIRST_BUILD_ADMISSION',now,'ADMITTED','OK',load(row)['effective_build_seconds']);return row
def freeze_first_runtime(b,root_pin,admission_pin,build_pin,now):
 h=first_helper(b);root=h.Pin.parse(root_pin);admission=h.Pin.parse(admission_pin);build=h.Pin.parse(build_pin);record=h.read_json(admission)
 try:
  frozen=h.freeze_controller(root,admission,build,clock_id=first_clock_id(),freeze_monotonic=now,last_observed_monotonic=record['observed_monotonic']);derived=h.read_json(frozen)
 except (ValueError,OSError):
  first_budget_summary(b,'FIRST_RUNTIME_FREEZE',now,'REFUSED','RUNTIME_WINDOW_OR_IMMUTABLE_BINDING');raise
 first_budget_summary(b,'FIRST_RUNTIME_FREEZE',now,'ADMITTED','OK',derived['gdn32_full']['profiles']['1']['wall_seconds']);return frozen.row(),derived
def first_handoff(c,handoff):
 need(type(handoff)is dict and set(handoff)=={'root','admission','build'},'FIRST externally pinned flow handoff')
 d=c['first_meaningful_derivation']
 for role,key in (('root','parent_controller'),('admission','build_admission'),('build','build_result')):
  need(handoff[role]==d[key],'FIRST handoff matches immutable derived provenance');load(handoff[role])
 return handoff
def claim_first_dut(b,now):
 c=load(b['controller_binding']);h=first_helper(c);return h.claim_dut_start(h.Pin.parse(b['controller_binding']),**first_verification(c,now,b.get('first_attempt_handoff'))).row()
