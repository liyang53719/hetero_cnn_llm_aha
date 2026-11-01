"""Explicit Python execution budget admission; never numerical acceptance.
Full budget remains unavailable until actual calibration and independent review
are frozen in a separately source-pinned admission. No deadline is inferred.
"""
import hashlib,json,pathlib,re,importlib.util
CALIBRATION='BOUNDED_CALIBRATION'
FULL='FULL_BLOCK_ACCEPTANCE'
ACCEPTED_FULL_ADMISSION_SHA256=None
FULL_POLICY='FULL_FIVE_ORIGINAL_HOST_POLICY'
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

def admit(binding):
 mode=binding.get('execution_mode',CALIBRATION)
 need(mode in (CALIBRATION,FULL),'unknown execution mode')
 request=binding.get('full_block_budget')
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
  need(type(doc)is dict and set(doc)==common_fields|{'artifact_manifest_sha256','model_candidate_review_sha256'},'exact candidate full admission fields, no legacy baseline')
  need(doc['schema']=='MODEL_CANDIDATE_FIVE_M128_FULL_EXECUTION_BUDGET_V1','candidate requires separate full budget version')
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
 need(doc['ready']is True and doc['scope']=='WATCHDOG_ADMISSION_ONLY_NOT_NUMERICAL_ACCEPTANCE','full admission not ready')
 need(doc['tokens']==128 and doc['matrix_macs']==4096 and doc['vector_lanes']==32,'unchanged full hardware/stimulus')
 root=D.parent
 need(doc['driver_sha256']==sha(root/'moe_router_score_observation_20261030/driver/host_axi_driver_non_dpi.cpp'),'unchanged calibrated numerical driver')
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

def consumer_limits(original,admission,profile):
 """Only watchdog limits change; never stimulus, data, hardware or success predicate."""
 i=str(profile);result=dict(original);wall=admission['profile_seconds'][i]
 need(type(wall)is int and 0<wall<=original['wall_seconds'],'explicit wall within original runtime bound')
 result['wall_seconds']=wall
 if admission['mode']==FULL:
  cycles=admission['profile_max_active_cycles'][i]
  need(type(cycles)is int and 0<cycles<=original['max_active_cycles'],'explicit full cycles within original runtime bound')
  result['max_active_cycles']=cycles
 return result

def transport_exit(mode,qualification):
 need(mode in (CALIBRATION,FULL),'unknown execution mode')
 if mode==CALIBRATION:return 2
 need(type(qualification)is dict and type(qualification.get('numerical_pass'))is bool,'recomputed full qualification required')
 status=qualification.get('status')
 need(status in ('PASS_FIVE_FULL128_EXACT_REFERENCE','FAIL_EXACT_REFERENCE','INCOMPLETE'),'known aggregate qualification status')
 need(qualification['numerical_pass']is (status=='PASS_FIVE_FULL128_EXACT_REFERENCE'),'consistent aggregate qualification')
 return 0 if qualification['numerical_pass']else 1 if status=='FAIL_EXACT_REFERENCE'else 2
