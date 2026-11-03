"""Explicit Python execution budget admission; never numerical acceptance.
V1 requires observed calibration. Cloud-only V2 admits independently reviewed
finite full-stimulus watchdogs without pretending completion bounds are known.
Neither version infers a deadline or grants numerical acceptance.
"""
import hashlib,json,pathlib,re,importlib.util
CALIBRATION='BOUNDED_CALIBRATION'
FULL='FULL_BLOCK_ACCEPTANCE'
STAGE='STAGE_COVERAGE_DIAGNOSTIC'
FIRST_FAULT='P0_FIRST_FAULT_DIAGNOSTIC'
FIRST_FAULT_SCOPE='P0_FIRST_FAULT_READONLY_SAME_FULL_M128_STIMULUS_NOT_NUMERICAL_ACCEPTANCE'
STAGE_SCOPE='STAGE_COVERAGE_DIAGNOSTIC_NOT_FULL_ACCEPTANCE'
ACCEPTED_FULL_ADMISSION_SHA256=None
FULL_POLICY='FULL_FIVE_ORIGINAL_HOST_POLICY'
FULL_V2_SCHEMA='MODEL_CANDIDATE_FIVE_M128_FULL_EXECUTION_BUDGET_V2'
FULL_V2_CONTRACT='FINITE_WATCHDOG_NOT_COMPLETION_ESTIMATE'
FULL_V3_SCHEMA='MODEL_CANDIDATE_FIVE_M128_FULL_READY_QUEUE_V3'
FULL_V3_QUEUE_POLICY='PARALLEL_INDEPENDENT_FEASIBILITY_NO_PROFILE_COMPLETION_DEPENDENCY'
# Source-reviewed absolute ceilings, not defaults or predicted completion times.
# Actual per-profile limits still require the externally approved exact budget.
FULL_V2_MAX_SECONDS=31*24*60*60
FULL_MAX_ACTIVE_CYCLES=1000000000
FULL_V2_LOG_POLICY=dict(schema='FULL_PREFILL_LOSSLESS_GZIP_LOG_V1',compressed_bytes=64<<20,raw_bytes=16<<30,line_bytes=8192)
FULL_V2_RSS_POLICY=dict(schema='FULL_PREFILL_RSS_GZIP_V1',compressed_bytes=64<<20,raw_bytes=16<<30,line_bytes=1048576,verification_wall_seconds=3600,verification_cpu_seconds=3600)
FULL_V3_LOG_SCHEMA='FULL_PREFILL_LOSSLESS_GZIP_LOG_V3'
FULL_V3_RSS_SCHEMA='FULL_PREFILL_RSS_GZIP_V3'
FULL_V3_LOG_MAX=128<<20
FULL_V3_RSS_MAX=1<<30
FULL_V2_HOST_PHASES=('postprocess','evidence_verification','summary_verification','rss_telemetry_verification')
IDS=tuple(map(str,range(5)))
D=pathlib.Path(__file__).resolve().parent

def need(v,message):
 if not v:raise ValueError(message)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def pin(v,limit):
 need(type(v)is dict and set(v)=={'path','bytes','sha256'},'exact full budget/evidence pin')
 p=pathlib.Path(v['path']);need(p.is_absolute() and p.is_file() and not any(x.is_symlink()for x in (p,*p.parents)),'regular absolute full budget/evidence')
 need(type(v['bytes'])is int and 0<v['bytes']<=limit and p.stat().st_size==v['bytes'],'bounded full budget/evidence')
 need(type(v['sha256'])is str and re.fullmatch('[0-9a-f]{64}',v['sha256'])is not None and sha(p)==v['sha256'],'full budget/evidence exact hash')
 return p

def stage_admission(binding):
 """Execution path: actual candidate invocation authority is always verified first."""
 helper_path=D/'numeric/candidate_admission.py'
 need(binding['pins'].get(str(helper_path))==sha(helper_path),'stage candidate verifier source pin')
 spec=importlib.util.spec_from_file_location('stage_candidate_review',helper_path);helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
 review=helper.verify(binding.get('model_candidate_review'),binding)
 return stage_document(binding,review)

def stage_document(binding,review):
 """Proposal-only pure document checks; does not authorize execution or call cloud admission."""
 need(binding.get('execution_context')=='CLOUD_EXECUTOR_V1' and binding.get('execution_mode')==STAGE,'stage coverage requires explicit cloud invocation')
 need(binding.get('full_block_budget') is None,'stage coverage is not full admission')
 policy_path=D/'profile_policy.py'
 need(binding['pins'].get(str(policy_path))==sha(policy_path),'stage profile policy source pin')
 policy_spec=importlib.util.spec_from_file_location('stage_profile_policy',policy_path);policy=importlib.util.module_from_spec(policy_spec);policy_spec.loader.exec_module(policy)
 policy.require_source_pin(binding['pins'])
 need(policy.checked(binding)['mode']==FULL_POLICY,'stage requires all five original-host profiles')
 artifact=json.loads(pin(binding.get('artifact_manifest'),65536).read_text())
 need(artifact.get('schema')=='MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1','stage coverage requires model candidate')
 need(review['scope']=='MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL' and review['artifact_manifest_sha256']==binding['artifact_manifest']['sha256'],'stage actual candidate review')
 request=binding.get('stage_coverage_budget');doc=json.loads(pin(request,65536).read_text())
 need(type(doc)is dict and set(doc)=={'schema','ready','scope','tokens','matrix_macs','vector_lanes','driver_sha256','artifact_manifest_sha256','model_candidate_review_sha256','basis','profiles'},'exact stage coverage budget')
 need(doc['schema']=='MODEL_CANDIDATE_STAGE_COVERAGE_BUDGET_V1' and doc['ready']is True and doc['scope']==STAGE_SCOPE,'stage coverage budget scope')
 need(all(type(doc[k])is int and doc[k]==v for k,v in [('tokens',128),('matrix_macs',4096),('vector_lanes',32)]),'unchanged stage hardware/stimulus')
 need(doc['artifact_manifest_sha256']==binding['artifact_manifest']['sha256'] and doc['model_candidate_review_sha256']==binding['model_candidate_review']['sha256'],'stage reviewed artifact identity')
 need(doc['driver_sha256']==sha(D.parent/'moe_router_score_observation_20261030/driver/host_axi_driver_non_dpi.cpp'),'stage unchanged numerical driver')
 need(type(doc['basis'])is dict and set(doc['basis'])=={'calibration_summary','independent_budget_review'},'stage observed calibration and independent budget review')
 for evidence in doc['basis'].values():pin(evidence,2<<20)
 calibration=json.loads(pin(doc['basis']['calibration_summary'],2<<20).read_text())
 need(calibration.get('schema')=='CLOUD_EXECUTION_SAFE_SUMMARY_V1' and calibration.get('status')=='VERIFIED_REAGGREGATED','stage verified calibration summary')
 need(calibration.get('execution_mode')==CALIBRATION and type(calibration.get('transport_exit_code'))is int and calibration['transport_exit_code']==2,'stage basis must be original bounded calibration')
 closed={'STARTED_TIMEOUT_INCOMPLETE','STARTED_NATIVE_FAILED','COMPLETE_TERMINAL_DIAGNOSTIC_NOT_PASS','COMPLETE_FULL128_EXACT_REFERENCE_NOT_FINAL_RTL','COMPLETE_EXACT_REFERENCE_FAILED'}
 need(type(calibration.get('profiles'))is list and all(type(x)is dict and type(x.get('profile'))is int and x.get('state')in closed for x in calibration['profiles']),'stage all profiles verified closed terminal states')
 need(type(calibration.get('profiles'))is list and len(calibration['profiles'])==5 and {x.get('profile')for x in calibration['profiles']}==set(range(5)),'stage all five closed profiles')
 need(calibration.get('artifact_manifest_sha256')==doc['artifact_manifest_sha256'] and calibration.get('model_candidate_review_sha256')==doc['model_candidate_review_sha256'] and calibration.get('candidate_scope')=='MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL','stage calibration exact candidate provenance')
 need(type(doc['profiles'])is dict and set(doc['profiles'])==set(IDS),'all five stage windows before execution')
 windows={};cycles={}
 for i in IDS:
  row=doc['profiles'][i]
  need(type(row)is dict and set(row)=={'wall_seconds','max_active_cycles','target_completed_commands'},'exact finite stage target')
  need(all(type(v)is int and v>0 for v in row.values()),'stage budget unknown or invalid')
  need(row['wall_seconds']<=18000 and row['max_active_cycles']<=1000000000 and row['target_completed_commands']<=256,'stage original watchdog ceilings and bounded target')
  windows[i]=row['wall_seconds'];cycles[i]=row['max_active_cycles']
 return dict(mode=STAGE,profile_seconds=windows,profile_max_active_cycles=cycles,reviewed_budget_sha256=request['sha256'])

def _first_fault_helper(binding):
 need(binding.get('execution_context')=='CLOUD_EXECUTOR_V1' and binding.get('execution_mode')==FIRST_FAULT,'first fault requires explicit cloud diagnostic')
 need(binding.get('full_block_budget')is None and 'stage_coverage_budget'not in binding,'first fault excludes full/stage budgets')
 policy_path=D/'profile_policy.py'
 need(binding['pins'].get(str(policy_path))==sha(policy_path),'first fault profile policy source pin')
 ps=importlib.util.spec_from_file_location('first_fault_profile_policy',policy_path);policy=importlib.util.module_from_spec(ps);ps.loader.exec_module(policy)
 policy.require_source_pin(binding['pins']);need(policy.checked(binding)['mode']==FULL_POLICY,'first fault retains five registered original-host profiles')
 need('profiles'not in binding or (type(binding['profiles'])is list and len(binding['profiles'])==5 and all(type(i)is int for i in binding['profiles']) and binding['profiles']==list(range(5))),'first fault retains all five registered hardware profiles')
 need('diagnostic_profiles'not in binding or (type(binding['diagnostic_profiles'])is list and len(binding['diagnostic_profiles'])==1 and type(binding['diagnostic_profiles'][0])is int and binding['diagnostic_profiles'][0]==0),'first fault selects only exact profile0')
 path=D/'numeric/p0_first_fault_contract.py'
 need(binding['pins'].get(str(path))==sha(path),'first fault contract verifier source pin')
 spec=importlib.util.spec_from_file_location('first_fault_contract',path);helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
 return helper

def _first_fault_result(value):
 need(type(value)is dict and set(value)=={'doc_sha','watchdog','diagnostic_profiles','scope'},'exact first fault contract result')
 need(value['scope']==FIRST_FAULT_SCOPE and type(value['doc_sha'])is str and re.fullmatch('[0-9a-f]{64}',value['doc_sha'])is not None,'first fault reviewed scope/document')
 profiles=value['diagnostic_profiles']
 need(type(profiles)is list and len(profiles)==1 and type(profiles[0])is int and profiles[0]==0,'first fault exact selected profile0')
 w=value['watchdog'];need(type(w)is dict and set(w)=={'wall_seconds','max_active_cycles'},'exact first fault watchdog')
 need(type(w['wall_seconds'])is int and 0<w['wall_seconds']<=18000 and type(w['max_active_cycles'])is int and 0<w['max_active_cycles']<=1000000000,'first fault original finite watchdog ceilings')
 return dict(mode=FIRST_FAULT,profile_seconds={'0':w['wall_seconds']},profile_max_active_cycles={'0':w['max_active_cycles']},reviewed_budget_sha256=value['doc_sha'],diagnostic_profiles=[0])

def first_fault_document(binding,review):
 """Proposal-only pure contract path. Never execution authority."""
 return _first_fault_result(_first_fault_helper(binding).verify_document(binding,review))

def first_fault_admission(binding):
 """Production path: N helper verifies candidate invocation authority first."""
 return _first_fault_result(_first_fault_helper(binding).admit(binding))

def admit(binding):
 mode=binding.get('execution_mode',CALIBRATION)
 need(mode in (CALIBRATION,FULL,STAGE,FIRST_FAULT),'unknown execution mode')
 request=binding.get('full_block_budget')
 if mode==FIRST_FAULT:
  path=D/'cloud_budget.py';need(binding['pins'].get(str(path))==sha(path),'first fault cloud verifier source pin')
  spec=importlib.util.spec_from_file_location('first_fault_cloud_admission',path);cloud=importlib.util.module_from_spec(spec);spec.loader.exec_module(cloud)
  approved=cloud.admit(binding);need(approved['execution_mode']==FIRST_FAULT and approved['diagnostic_profiles']==[0],'approved first fault diagnostic')
  return first_fault_admission(binding)
 if mode==STAGE:
  path=D/'cloud_budget.py';need(binding['pins'].get(str(path))==sha(path),'stage cloud verifier source pin')
  spec=importlib.util.spec_from_file_location('stage_cloud_admission',path);cloud=importlib.util.module_from_spec(spec);spec.loader.exec_module(cloud)
  approved=cloud.admit(binding);need(approved['execution_mode']==STAGE and approved['stage_coverage_budget']==binding.get('stage_coverage_budget'),'approved stage budget')
  return stage_admission(binding)
 need('stage_coverage_budget'not in binding,'stage budget forbidden in legacy modes')
 if mode==CALIBRATION:
  need(request is None,'full budget forbidden in calibration mode')
  windows=binding.get('calibration_seconds',binding.get('budgets',{}).get('calibration_seconds'))
  need(type(windows)is dict and set(windows)==set(IDS)and all(type(v)is int and 0<v<=20000 for v in windows.values()),'five explicit calibration windows')
  return dict(mode=mode,profile_seconds=dict(windows),profile_max_active_cycles=None,reviewed_budget_sha256=None)
 policy_spec=importlib.util.spec_from_file_location('full_mode_profile_policy',D/'profile_policy.py');policy=importlib.util.module_from_spec(policy_spec);policy_spec.loader.exec_module(policy)
 need(policy.checked(binding)['mode']==FULL_POLICY,'full mode requires all five original-host profiles')
 expected_full=ACCEPTED_FULL_ADMISSION_SHA256
 if binding.get('execution_context')=='CLOUD_EXECUTOR_V1':
  cloud_path=D/'cloud_budget.py'
  need(binding['pins'].get(str(cloud_path))==sha(cloud_path),'cloud admission source pin')
  cloud_spec=importlib.util.spec_from_file_location('actual_cloud_budget_for_full',cloud_path);cloud=importlib.util.module_from_spec(cloud_spec);cloud_spec.loader.exec_module(cloud)
  approved=cloud.admit(binding);need(approved['execution_mode']==FULL and approved['full_block_budget']==request,'operator approved actual full input')
  expected_full=request['sha256']
 need(expected_full is not None,'FULL_EXECUTION_BUDGET_PENDING_ACTUAL_CALIBRATION_AND_REVIEW')
 path=pin(request,65536)
 need(request['sha256']==expected_full,'full budget must equal independently reviewed admission')
 doc=json.loads(path.read_text())
 candidate=False
 if binding.get('artifact_manifest') is not None:
  artifact=json.loads(pin(binding['artifact_manifest'],65536).read_text())
  candidate=artifact['schema']=='MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1'
 common_fields={'schema','ready','scope','tokens','matrix_macs','vector_lanes','driver_sha256','basis','profiles'}
 if candidate:
  need(binding.get('execution_context')=='CLOUD_EXECUTOR_V1','candidate full budget requires approved cloud invocation')
  v3=doc.get('schema')==FULL_V3_SCHEMA
  v2=doc.get('schema')==FULL_V2_SCHEMA or v3
  if v3:common_fields=(common_fields-{'ready'})|{'selected_profiles','queue_policy'}
  extra={'budget_contract','completion_guaranteed','executor_source_commit','executor_source_pins_sha256','log_policy','rss_telemetry_policy'}if v2 else set()
  need(type(doc)is dict and set(doc)==common_fields|{'artifact_manifest_sha256','model_candidate_review_sha256'}|extra,'exact candidate full admission fields, no legacy baseline')
  need(doc['schema']in('MODEL_CANDIDATE_FIVE_M128_FULL_EXECUTION_BUDGET_V1',FULL_V2_SCHEMA,FULL_V3_SCHEMA),'candidate requires separate full budget version')
  candidate_path=D/'numeric/candidate_admission.py'
  need(binding['pins'].get(str(candidate_path))==sha(candidate_path),'candidate full admission verifier source pin')
  candidate_spec=importlib.util.spec_from_file_location('actual_candidate_for_full',candidate_path);candidate_gate=importlib.util.module_from_spec(candidate_spec);candidate_spec.loader.exec_module(candidate_gate)
  reviewed=candidate_gate.verify(binding.get('model_candidate_review'),binding)
  need(reviewed['scope']=='MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL','candidate evaluation scope only')
  need(doc['artifact_manifest_sha256']==binding['artifact_manifest']['sha256']==reviewed['artifact_manifest_sha256'],'full budget exact candidate artifact')
  need(doc['model_candidate_review_sha256']==binding['model_candidate_review']['sha256']==reviewed['model_candidate_review_sha256'],'full budget exact independent candidate review')
 else:
  need(binding.get('model_candidate_review') is None,'candidate review cannot use legacy full budget')
  need(type(doc)is dict and set(doc)==common_fields|{'hardware_baseline_sha256'},'exact full admission fields')
  need(doc['schema']=='FIVE_M128_FULL_EXECUTION_BUDGET_V1','legacy full budget version')
  need(doc['hardware_baseline_sha256']==sha(D.parent/'ci_frontend_materialization_r2_20261029/OBSERVER_BASELINE_ACCEPTANCE.json'),'same reviewed hardware observation baseline')
  v2=False
 need((doc.get('schema')==FULL_V3_SCHEMA or doc['ready']is True) and doc['scope']=='WATCHDOG_ADMISSION_ONLY_NOT_NUMERICAL_ACCEPTANCE','full admission not ready')
 need(all(type(doc[k])is int and doc[k]==v for k,v in [('tokens',128),('matrix_macs',4096),('vector_lanes',32)]),'unchanged full hardware/stimulus')
 root=D.parent
 need(doc['driver_sha256']==sha(root/'moe_router_score_observation_20261030/driver/host_axi_driver_non_dpi.cpp'),'unchanged calibrated numerical driver')
 if v2:
  return full_v3_document(binding,doc,request,approved) if v3 else full_v2_document(binding,doc,request,approved)
 need(type(doc['basis'])is dict and set(doc['basis'])=={'calibration_summary','independent_budget_review'},'actual calibration and independent budget review required')
 for evidence in doc['basis'].values():pin(evidence,2<<20)
 if candidate:
  calibration=json.loads(pin(doc['basis']['calibration_summary'],2<<20).read_text())
  need(calibration.get('artifact_manifest_sha256')==doc['artifact_manifest_sha256'] and calibration.get('model_candidate_review_sha256')==doc['model_candidate_review_sha256'] and calibration.get('candidate_scope')=='MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL','actual calibration provenance must be this reviewed candidate')
 need(type(doc['profiles'])is dict and set(doc['profiles'])==set(IDS),'all five full budgets before any execution')
 windows={};cycles={}
 for i in IDS:
  p=doc['profiles'][i]
  need(type(p)is dict and set(p)=={'wall_seconds','max_active_cycles','estimated_complete_active_cycles','estimated_required_wall_seconds'},'explicit full profile budget')
  need(all(type(v)is int and v>0 for v in p.values()),'full profile budget unknown or invalid')
  need(p['estimated_required_wall_seconds']<=p['wall_seconds']<=18000,'full wall estimate fits unchanged conservative ceiling')
  need(p['estimated_complete_active_cycles']<=p['max_active_cycles']<=1000000000,'full cycle estimate fits original driver ceiling')
  windows[i]=p['wall_seconds'];cycles[i]=p['max_active_cycles']
 return dict(mode=mode,profile_seconds=windows,profile_max_active_cycles=cycles,reviewed_budget_sha256=request['sha256'])

def full_v2_document(binding,doc,request,cloud):
 """Full-stimulus finite attempt. This does not turn a lower bound or historical
 host throughput into a promised completion time, nor authorize a short probe.
 The external cloud approval and ordinary candidate review were checked first.
 """
 need(doc['schema']==FULL_V2_SCHEMA,'explicit V2 full document')
 need(type(doc['profiles'])is dict and set(doc['profiles'])==set(IDS),'all five full watchdogs before any execution')
 return _full_finite_document(binding,doc,request,cloud,doc['profiles'],2)

def full_v3_selection(doc):
 need(doc.get('schema')==FULL_V3_SCHEMA and doc.get('queue_policy')==FULL_V3_QUEUE_POLICY,'explicit V3 independent ready queue')
 selected=doc.get('selected_profiles')
 need(type(selected)is list and 0<len(selected)<=5 and all(type(i)is int and 0<=i<5 for i in selected) and selected==sorted(set(selected)),'exact nonempty ordered selected subset')
 need(type(doc.get('profiles'))is dict and set(doc['profiles'])==set(IDS),'all five queue inventory rows required')
 return selected

def full_v3_document(binding,doc,request,cloud):
 selected=full_v3_selection(doc);rows={};blocked={}
 for i in IDS:
  row=doc['profiles'][i]
  if int(i)in selected:
   need(type(row)is dict and set(row)=={'state','watchdog'} and row['state']=='READY_FULL_PREFILL','selected profile needs actual ready watchdog')
   rows[i]=row['watchdog']
  else:
   need(type(row)is dict and set(row)=={'state','reason','analysis'} and row['state']=='BLOCKED_NOT_RUN','unselected profile blocked without fake executable values')
   need(type(row['reason'])is str and 0<len(row['reason'].strip())<=4096,'exact nonempty blocked reason')
   pin(row['analysis'],2<<20)
   blocked[i]=dict(row)
 result=_full_finite_document(binding,doc,request,cloud,rows,3)
 result.update(selected_profiles=list(selected),blocked_profiles=blocked,queue_policy=FULL_V3_QUEUE_POLICY)
 return result

def _full_finite_document(binding,doc,request,cloud,rows,version):
 need(binding.get('execution_context')=='CLOUD_EXECUTOR_V1'and binding.get('execution_mode')==FULL,'V2 full budget is cloud-only')
 need(doc['budget_contract']==FULL_V2_CONTRACT and doc['completion_guaranteed']is False,'V2 watchdog never guarantees completion')
 log=doc['log_policy']
 need(type(log)is dict and log==FULL_V2_LOG_POLICY and all(type(log[k])is int for k in ('compressed_bytes','raw_bytes','line_bytes')),'V2 exact bounded lossless log policy')
 rss=doc['rss_telemetry_policy']
 need(type(rss)is dict and rss==FULL_V2_RSS_POLICY and all(type(rss[k])is int for k in rss if k!='schema'),'V2 exact bounded lossless RSS telemetry policy')
 need(doc['executor_source_commit']==binding['identity']['source_commit'],'V2 exact reviewed executor source')
 catalog=binding.get('source_pins');pin(catalog,2<<20)
 need(doc['executor_source_pins_sha256']==catalog['sha256'],'V2 exact reviewed executor catalog')
 need(type(cloud)is dict and cloud['execution_mode']==FULL and cloud['full_block_budget']==request,'V2 externally approved full watchdog')
 # Keep the current cloud envelopes rather than silently inheriting V1 full
 # mode's larger historical maxima. CPU affinity is still the supervisor's one.
 for key,ceiling in (('dut_rss_bytes',2<<30),('dut_address_space_bytes',2684354560)):
  need(type(cloud[key])is int and 0<cloud[key]<=ceiling,'V2 preserved RSS2GiB/AS2.5GiB resource envelope')
 need(cloud['consumer_address_space_bytes']==512<<20 and cloud['reserved_other_owner_bytes']==5<<30,'V2 preserved consumer and other-owner reservations')
 need(type(doc['basis'])is dict and set(doc['basis'])=={'cycle_analysis','host_rate_evidence','independent_budget_review'},'V2 explicit analysis, host-rate uncertainty and independent review')
 for evidence in doc['basis'].values():pin(evidence,2<<20)
 windows={};cpus={};cycles={};raw_bytes={};rss_raw={};log_caps={};rss_caps={}
 host={name+'_'+kind+'_seconds':{}for name in FULL_V2_HOST_PHASES for kind in ('wall','cpu')}
 for i,row in rows.items():
  cap_fields={'log_compressed_bytes','rss_telemetry_compressed_bytes'} if version==3 and type(row)is dict and cap_fields_present(row) else set()
  need(type(row)is dict and set(row)=={'wall_seconds','cpu_seconds','max_active_cycles','log_raw_bytes','rss_telemetry_raw_bytes'}|set(host)|cap_fields,'exact V2 finite full watchdog; no invented completion estimate')
  if version==3:
   log_caps[i]=row.get('log_compressed_bytes',log['compressed_bytes']);rss_caps[i]=row.get('rss_telemetry_compressed_bytes',rss['compressed_bytes'])
   need(type(log_caps[i])is int and 0<log_caps[i]<=FULL_V3_LOG_MAX and type(rss_caps[i])is int and 0<rss_caps[i]<=FULL_V3_RSS_MAX,'finite independently reviewed V3 compressed quotas')
  need(all(type(value)is int and value>0 for value in row.values()),'V2 strictly positive integer watchdogs')
  need(row['cpu_seconds']<=row['wall_seconds']<=FULL_V2_MAX_SECONDS,'V2 finite CPU/wall bounds for one CPU')
  need(row['max_active_cycles']<=FULL_MAX_ACTIVE_CYCLES,'V2 unchanged binary cycle watchdog ceiling')
  need(row['log_raw_bytes']<=log['raw_bytes'],'V2 explicit per-profile raw log ceiling')
  need(row['rss_telemetry_raw_bytes']<=rss['raw_bytes'],'V2 explicit per-profile raw RSS telemetry ceiling')
  rss_raw[i]=row['rss_telemetry_raw_bytes']
  for phase in FULL_V2_HOST_PHASES:
   wall=phase+'_wall_seconds';cpu=phase+'_cpu_seconds'
   need(row[cpu]<=row[wall]<=3600,'V2 independent finite host-phase CPU/wall reservation')
   host[wall][i]=row[wall];host[cpu][i]=row[cpu]
  raw_bytes[i]=row['log_raw_bytes']
  windows[i]=row['wall_seconds'];cpus[i]=row['cpu_seconds'];cycles[i]=row['max_active_cycles']
 return dict(**(dict(profile_log_compressed_bytes=log_caps,profile_rss_telemetry_compressed_bytes=rss_caps)if version==3 else {}),mode=FULL,budget_version=version,dut_rss_bytes=cloud['dut_rss_bytes'],dut_address_space_bytes=cloud['dut_address_space_bytes'],budget_contract=FULL_V2_CONTRACT,completion_guaranteed=False,log_policy=dict(log),rss_telemetry_policy=dict(rss),profile_rss_telemetry_raw_bytes=rss_raw,profile_log_raw_bytes=raw_bytes,**{'profile_'+name:values for name,values in host.items()},profile_seconds=windows,profile_cpu_seconds=cpus,profile_max_active_cycles=cycles,reviewed_budget_sha256=request['sha256'])

def cap_fields_present(row):
 return bool({'log_compressed_bytes','rss_telemetry_compressed_bytes'}&set(row))

def full_v2(admission):
 if 'budget_version'not in admission:return False
 need(type(admission['budget_version'])is int and admission['budget_version']in(2,3) and admission['mode']==FULL,'only explicit V2/V3 full execution')
 if admission['budget_version']==3:ready_queue_profiles(admission)
 need(admission.get('budget_contract')==FULL_V2_CONTRACT and admission.get('completion_guaranteed')is False,'V2 finite watchdog admission contract')
 return True

def ready_queue_profiles(admission):
 """Exact selection boundary; no implicit queue expansion or blocked budgets."""
 need(type(admission.get('budget_version'))is int and admission['budget_version']==3 and admission.get('mode')==FULL,'explicit V3 full admission')
 selected=admission.get('selected_profiles')
 need(type(selected)is list and 0<len(selected)<=5 and all(type(i)is int and 0<=i<5 for i in selected)and selected==sorted(set(selected)),'exact admitted selected subset')
 need(admission.get('queue_policy')==FULL_V3_QUEUE_POLICY,'independent parallel queue feasibility')
 blocked=admission.get('blocked_profiles')
 need(type(blocked)is dict and set(blocked)==set(IDS)-set(map(str,selected)),'exact blocked complement')
 for row in blocked.values():
  need(type(row)is dict and set(row)=={'state','reason','analysis'} and row['state']=='BLOCKED_NOT_RUN','blocked inventory never PASS')
 keys=['log_compressed_bytes','rss_telemetry_compressed_bytes','seconds','cpu_seconds','max_active_cycles','log_raw_bytes','rss_telemetry_raw_bytes']+[phase+'_'+kind+'_seconds'for phase in FULL_V2_HOST_PHASES for kind in ('wall','cpu')]
 for name in keys:need(type(admission.get('profile_'+name))is dict and set(admission['profile_'+name])==set(map(str,selected)),'only actually selected watchdogs')
 return list(selected)

def queue_report_fields(admission):
 if admission.get('budget_version')!=3:return {}
 return dict(budget_version=3,profiles_registered=list(range(5)),selected_profiles=ready_queue_profiles(admission),blocked_profiles=admission['blocked_profiles'],queue_policy=FULL_V3_QUEUE_POLICY)

def profile_wall_ceiling(admission):
 return FULL_V2_MAX_SECONDS if full_v2(admission) else 20000

def dut_parent_cpu_seconds(admission,profile):
 """The consumer is exec'd under this hard ceiling before it forks the DUT.
 Its child must never try to raise an inherited 18000s RLIMIT_CPU. Thirty seconds
 preserve preflight allowance; explicit postprocessing CPU is separate.
 """
 if not full_v2(admission):return 18000
 wall=admission['profile_seconds'][str(profile)];cpu=admission['profile_cpu_seconds'][str(profile)]
 need(type(wall)is int and type(cpu)is int and 0<cpu<=wall<=FULL_V2_MAX_SECONDS,'finite V2 inherited CPU ceiling')
 return cpu+admission['profile_postprocess_cpu_seconds'][str(profile)]+30

def install_full_v2_parent_cpu_limit(admission,job_seconds):
 """Finite lifecycle ceiling before any worker starts. Never raise an inherited
 hard limit. The strict per-phase supervisor continues enforcing its own caps.
 """
 import resource
 need(full_v2(admission),'parent CPU adaptation is V2-only')
 need(type(job_seconds)is int and 0<job_seconds<=2**31-1,'finite reviewed lifecycle CPU limit')
 need(max(dut_parent_cpu_seconds(admission,int(i))for i in admission['profile_seconds'])<=job_seconds,'lifecycle CPU contains every inherited phase bound')
 old_soft,old_hard=resource.getrlimit(resource.RLIMIT_CPU)
 need(old_hard==resource.RLIM_INFINITY or job_seconds<=old_hard,'inherited CPU hard limit insufficient for reviewed full lifecycle')
 usage=resource.getrusage(resource.RUSAGE_SELF)
 need(usage.ru_utime+usage.ru_stime<job_seconds,'parent CPU already exceeds full lifecycle')
 resource.setrlimit(resource.RLIMIT_CPU,(job_seconds,job_seconds))
 return dict(schema='FULL_PREFILL_PARENT_CPU_LIMIT_V1',job_cpu_seconds=job_seconds,previous_soft=old_soft,previous_hard=old_hard,inherited_hard_raised=False)

def expected_log_policy(admission,profile):
 if not full_v2(admission):return None
 value=dict(admission['log_policy'],raw_bytes=admission['profile_log_raw_bytes'][str(profile)])
 if admission['budget_version']==3:
  value.update(compressed_bytes=admission['profile_log_compressed_bytes'][str(profile)])
  if value['compressed_bytes']>FULL_V2_LOG_POLICY['compressed_bytes']:value['schema']=FULL_V3_LOG_SCHEMA
 return value

def expected_rss_telemetry_policy(admission,profile):
 if not full_v2(admission):return None
 i=str(profile)
 value=dict(admission['rss_telemetry_policy'],raw_bytes=admission['profile_rss_telemetry_raw_bytes'][i],verification_wall_seconds=admission['profile_rss_telemetry_verification_wall_seconds'][i],verification_cpu_seconds=admission['profile_rss_telemetry_verification_cpu_seconds'][i])
 if admission['budget_version']==3:
  value.update(compressed_bytes=admission['profile_rss_telemetry_compressed_bytes'][i])
  if value['compressed_bytes']!=FULL_V2_RSS_POLICY['compressed_bytes']:value['schema']=FULL_V3_RSS_SCHEMA
 return value

def full_v3_log_disk_bytes(admission,profile=None):
 if admission.get('budget_version')!=3:return 0
 selected=ready_queue_profiles(admission)
 if profile is not None:
  need(type(profile)is int and profile in selected,'selected V3 disk reservation')
  selected=[profile]
 total=0
 for i in selected:
  log=admission['profile_log_compressed_bytes'][str(i)];rss=admission['profile_rss_telemetry_compressed_bytes'][str(i)]
  need(type(log)is int and 0<log<=FULL_V3_LOG_MAX and type(rss)is int and 0<rss<=FULL_V3_RSS_MAX,'finite V3 disk quota')
  total+=log+rss
 return total

def host_phase_limits(admission,profile,phase):
 need(phase in FULL_V2_HOST_PHASES,'known bounded host phase')
 if not full_v2(admission):return None
 i=str(profile)
 return dict(wall_seconds=admission['profile_'+phase+'_wall_seconds'][i],cpu_seconds=admission['profile_'+phase+'_cpu_seconds'][i])

def verify_consumer_admission(admission,reported,profile):
 """Use the independent admission, never a report's self-selected log version."""
 need(type(reported)is dict and reported.get('execution_mode')==admission['mode'] and reported.get('reviewed_budget_sha256')==admission['reviewed_budget_sha256'],'actual independently admitted consumer mode/budget')
 if full_v2(admission):
  need(type(reported.get('budget_version'))is int and reported['budget_version']==admission['budget_version'],'actual expected full V2/V3 consumer version')
  expected=expected_log_policy(admission,profile);actual=reported.get('log_policy')
  need(type(actual)is dict and actual==expected and all(type(actual[k])is type(expected[k])for k in expected),'actual independently admitted per-profile log policy')
  expected=host_phase_limits(admission,profile,'postprocess');actual=reported.get('postprocess_limits')
  need(type(actual)is dict and actual==expected and all(type(actual[k])is int for k in expected),'actual independently admitted postprocess limits')
 else:
  need('budget_version'not in reported and 'log_policy'not in reported and 'postprocess_limits'not in reported,'legacy admission cannot claim V2 log or postprocess policy')
 return expected_log_policy(admission,profile)

def verify_supervisor_telemetry(outer_pin,admission,profile,supervisor_dir,pins):
 """Rebind the strict supervisor's complete proof to actual compressed bytes.
 The supervisor already decoded all samples under its separate budget. This
 bounded reread does not consume another full raw-file verification pass.
 """
 import types
 expected=expected_rss_telemetry_policy(admission,profile)
 need(expected is not None,'explicit V2 supervisor telemetry expected')
 path=pin(outer_pin,16<<20);outer=json.loads(path.read_text())
 caps=outer.get('caps',{})
 need(type(caps)is dict and all(type(caps.get(k))is int for k in ('wall_seconds','cleanup_seconds','cpu_seconds','per_process_cpu_seconds','rss_bytes','per_process_as_bytes')),'typed actual supervisor resource ceilings')
 need(type(caps)is dict and caps.get('wall_seconds')==consumer_phase_seconds(admission,profile)+30 and caps.get('cleanup_seconds')==30 and caps.get('cpu_seconds')==dut_aggregate_cpu_seconds(admission,profile,0) and caps.get('per_process_cpu_seconds')==dut_parent_cpu_seconds(admission,profile),'actual finite supervisor time and cleanup ceilings')
 need(caps.get('rss_bytes')==admission['dut_rss_bytes'] and caps.get('per_process_as_bytes')==admission['dut_address_space_bytes'],'actual unchanged supervisor RSS/address-space ceilings')
 helper=pathlib.Path(supervisor_dir)/'rss_telemetry.py'
 need(helper.is_file() and not any(q.is_symlink()for q in(helper,*helper.parents)),'regular RSS telemetry verifier')
 need(0<helper.stat().st_size<=1<<20,'bounded RSS telemetry verifier source')
 raw=helper.read_bytes();need(pins.get(str(helper))==hashlib.sha256(raw).hexdigest(),'source-pinned RSS receipt verifier')
 module=types.ModuleType('reviewed_full_rss_receipt');module.__file__=str(helper);exec(compile(raw,str(helper),'exec'),module.__dict__)
 need(module.policy(caps.get('rss_telemetry_policy'))==expected,'actual independently admitted supervisor telemetry policy')
 return module.check_receipt(path.with_name('rss_samples.jsonl.gz'),outer.get('rss_telemetry'),expected,outer.get('process_sample_count'))

def profile_reserved_seconds(admission):
 values=dict(admission['profile_seconds'])
 if full_v2(admission):
  for i in values:values[i]+=sum(admission['profile_'+phase+'_wall_seconds'][i]for phase in FULL_V2_HOST_PHASES)
 return values

def consumer_phase_seconds(admission,profile):
 i=str(profile);seconds=admission['profile_seconds'][i]+30
 if full_v2(admission):seconds+=admission['profile_postprocess_wall_seconds'][i]
 return seconds

def dut_admission_seconds(admission,profile,parent_seconds):
 """Reserve all deferred summary work before a new full DUT process starts.
 This is a remaining-job admission reserve, not a work-wall extension.
 """
 need(full_v2(admission),'explicit V2 lifecycle reserve')
 need(type(parent_seconds)is int and 0<parent_seconds<=600,'existing reviewed parent reserve')
 i=str(profile)
 return consumer_phase_seconds(admission,profile)+admission['profile_rss_telemetry_verification_wall_seconds'][i]+admission['profile_evidence_verification_wall_seconds'][i]+sum(admission['profile_summary_verification_wall_seconds'].values())+parent_seconds

def dut_aggregate_cpu_seconds(admission,profile,legacy_seconds):
 if not full_v2(admission):return legacy_seconds+30
 i=str(profile)
 return admission['profile_cpu_seconds'][i]+admission['profile_postprocess_cpu_seconds'][i]+60

class HostVerificationBudgetExceeded(RuntimeError):pass

class host_verification_budget:
 """Owned current-process wall/CPU timers with strict nested deadlines.
 Foreign timers, blocked watchdogs and pre-existing pending signals reject.
 This is not a process-tree/cgroup hard CPU limit.
 """
 _active=[]
 def __init__(self,wall_seconds,cpu_seconds):
  need(type(wall_seconds)is int and type(cpu_seconds)is int and 0<cpu_seconds<=wall_seconds<=86400,'explicit bounded host verification wall/CPU')
  self.wall=wall_seconds;self.cpu=cpu_seconds;self.running=False;self.expired=False
 def __enter__(self):
  import signal,threading,time
  need(not self.running and threading.current_thread()is threading.main_thread(),'host verification main-thread ownership')
  self.signal=signal;self.time=time;self.signals={signal.SIGALRM,signal.SIGPROF}
  self.entry_mask=signal.pthread_sigmask(signal.SIG_BLOCK,self.signals)
  changed=False
  try:
   need(not self.signals.intersection(self.entry_mask),'unblocked host watchdog signals required')
   need(not self.signals.intersection(signal.sigpending()),'no pending external host watchdog signal')
   self.parent=self._active[-1]if self._active else None
   self.old={timer:signal.getitimer(timer)for timer in(signal.ITIMER_REAL,signal.ITIMER_PROF)}
   self.handlers={signum:signal.getsignal(signum)for signum in self.signals}
   if self.parent is None:
    need(all(value==(0.,0.)for value in self.old.values()),'unused or explicitly owned host watchdog timers')
   else:
    need(self.parent.running and not self.parent.expired and self.parent._owns_watchdogs()and all(handler is self.parent.handler for handler in self.handlers.values())and all(value[0]>0 and value[1]==0 for value in self.old.values()),'same active host watchdog owner')
   self.started=time.monotonic();self.cpu_started=time.process_time()
   self.wall_deadline=min(self.started+self.wall,self.parent.wall_deadline)if self.parent else self.started+self.wall
   self.cpu_deadline=min(self.cpu_started+self.cpu,self.parent.cpu_deadline)if self.parent else self.cpu_started+self.cpu
   need(self.wall_deadline>self.started and self.cpu_deadline>self.cpu_started,'unexpired enclosing host verification budget')
   def expired(signum,frame):
    self.expired=True
    raise HostVerificationBudgetExceeded('host verification '+('wall'if signum==signal.SIGALRM else 'CPU')+' budget exhausted')
   self.handler=expired;changed=True
   for signum in self.signals:signal.signal(signum,self.handler)
   self.running=True;self._active.append(self)
   signal.setitimer(signal.ITIMER_REAL,self.wall_deadline-time.monotonic())
   signal.setitimer(signal.ITIMER_PROF,self.cpu_deadline-time.process_time())
   self._restore_owned_mask()
   return self
  except BaseException:
   if changed:self._restore()
   else:self._restore_owned_mask()
   raise
 def _restore_owned_mask(self):
  signal=self.signal
  # Change only owned bits; a reentrant unrelated handler may change its own
  # mask at any call boundary, so never write a whole-mask snapshot back.
  blocked=self.entry_mask&self.signals;unblocked=self.signals-self.entry_mask
  try:
   if blocked:signal.pthread_sigmask(signal.SIG_BLOCK,blocked)
  finally:
   if unblocked:signal.pthread_sigmask(signal.SIG_UNBLOCK,unblocked)
 def _owns_watchdogs(self):
  signal=self.signal
  if any(signal.getsignal(signum)is not self.handler for signum in self.signals):return False
  pending=signal.sigpending()
  for timer,clock,deadline,signum in ((signal.ITIMER_REAL,self.time.monotonic,self.wall_deadline,signal.SIGALRM),(signal.ITIMER_PROF,self.time.process_time,self.cpu_deadline,signal.SIGPROF)):
   before=clock();remaining,interval=signal.getitimer(timer);after=clock()
   if interval!=0:return False
   if remaining==0:
    if not(self.expired or signum in pending or after>=deadline):return False
   elif not max(0,deadline-after)-.02<=remaining<=max(0,deadline-before)+.02:return False
  return True
 def _restore(self):
  signal=self.signal
  signal.pthread_sigmask(signal.SIG_BLOCK,self.signals)
  try:
   self.ownership_lost=not self._owns_watchdogs()
   signal.setitimer(signal.ITIMER_REAL,0);signal.setitimer(signal.ITIMER_PROF,0)
   for signum in self.signals:
    if signum in signal.sigpending():
     self.expired=True
     signal.sigtimedwait({signum},0)
   wall_now=self.time.monotonic();cpu_now=self.time.process_time()
   self.expired=self.expired or wall_now>=self.wall_deadline or cpu_now>=self.cpu_deadline
   if self.parent is not None:
    self.parent.expired=self.parent.expired or wall_now>=self.parent.wall_deadline or cpu_now>=self.parent.cpu_deadline
   for signum,handler in self.handlers.items():signal.signal(signum,handler)
   if self.running:
    need(bool(self._active)and self._active[-1]is self,'LIFO host watchdog ownership')
    self._active.pop();self.running=False
   if self.parent is not None:
    # Restore its original absolute deadlines, never a fresh allowance.
    # An expired parent is rearmed immediately under its OWN handler.
    signal.setitimer(signal.ITIMER_REAL,max(.000001,self.parent.wall_deadline-self.time.monotonic()))
    signal.setitimer(signal.ITIMER_PROF,max(.000001,self.parent.cpu_deadline-self.time.process_time()))
  finally:
   self._restore_owned_mask()
 def __exit__(self,*exc):
  import threading
  need(threading.current_thread()is threading.main_thread()and self.running and bool(self._active)and self._active[-1]is self,
       'active main-thread LIFO host verification owner required')
  self._restore()
  if exc[0]is None and self.ownership_lost:raise HostVerificationBudgetExceeded('host watchdog ownership changed')
  if exc[0]is None and self.expired:raise HostVerificationBudgetExceeded('host verification budget exhausted')
  return False

def consumer_limits(original,admission,profile):
 """Only watchdog limits change; never stimulus, data, hardware or success predicate."""
 if admission['mode']==FIRST_FAULT:need(type(profile)is int and profile==0 and admission.get('diagnostic_profiles')==[0],'first fault consumer profile0 only')
 if admission.get('budget_version')==3:need(type(profile)is int and profile in ready_queue_profiles(admission),'profile not independently admitted ready')
 i=str(profile);result=dict(original);wall=admission['profile_seconds'][i]
 if full_v2(admission):
  need(type(wall)is int and 0<wall<=FULL_V2_MAX_SECONDS,'explicit V2 finite wall')
  cpu=admission['profile_cpu_seconds'][i]
  need(type(cpu)is int and 0<cpu<=wall,'explicit V2 finite CPU within wall')
  result['cpu_seconds']=cpu
 else:need(type(wall)is int and 0<wall<=original['wall_seconds'],'explicit wall within original runtime bound')
 result['wall_seconds']=wall
 if admission['mode']in(FULL,STAGE,FIRST_FAULT):
  cycles=admission['profile_max_active_cycles'][i]
  need(type(cycles)is int and 0<cycles<=original['max_active_cycles'],'explicit full cycles within original runtime bound')
  result['max_active_cycles']=cycles
 return result

def transport_exit(mode,qualification):
 need(mode in (CALIBRATION,FULL,STAGE,FIRST_FAULT),'unknown execution mode')
 if mode in(CALIBRATION,STAGE,FIRST_FAULT):return 2
 need(type(qualification)is dict and type(qualification.get('numerical_pass'))is bool,'recomputed full qualification required')
 status=qualification.get('status')
 need(status in ('PASS_FIVE_FULL128_EXACT_REFERENCE','FAIL_EXACT_REFERENCE','INCOMPLETE'),'known aggregate qualification status')
 need(qualification['numerical_pass']is (status=='PASS_FIVE_FULL128_EXACT_REFERENCE'),'consistent aggregate qualification')
 return 0 if qualification['numerical_pass']else 1 if status=='FAIL_EXACT_REFERENCE'else 2
