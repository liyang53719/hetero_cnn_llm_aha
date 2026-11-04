"""New-source launch binding -> fresh capability -> reviewed FULL plan -> original flow.
No default finite DUT window; no artifact upload, model arithmetic or host waiver.
"""
import argparse,contextlib,hashlib,importlib.util,json,math,os,pathlib,platform,re,shutil,subprocess,sys,time
P=pathlib.Path;HERE=P(__file__).resolve().parent
MODEL='candidates/gdn32_first_model_execution_20261104'
HW='2b2f02d698f16a57ba696c52c4669a1226a68c5378efdc8ebe392cc1b9098f52'
GEN='31dc0fabfd5d06d40eccf7194902bee245b8c98e25488b8993b676cae1fd90d3'
DRIVER='e8aeaac48a407e27bcbf54db0d85867a904c67a2dce7e1d270999a8482453261'
CAT='b22a9cdc3ccedcf2c1517b7f1da16d479a73fd5ce23ee7258231d78925c19de5'
SOURCE_COUNT=1211
FIRST='FIRST_MEANINGFUL_FULL_ATTEMPT'
FIRST_PLAN_REL=MODEL+'/FIRST_REVIEWED_WINDOW_PLAN.json'
FIRST_PLAN_SHA='323ebf74bce5c35ba3eb956aa6efd7ba48a69ccbf9e843a6184a57684a60e47a'
FIRST_HELPER_REL=MODEL+'/numeric/first_meaningful_attempt.py'
FIRST_HELPER_SHA='0a7353c734d38169739ef4b67ca56e5091f6b643836f21fe48fbd7c1f24cf95b'
NONCE='gdn32-first-meaningful-p1-20261104-retry1';JOB=21000;DISK=20671240864
MISSING=('NEW_ARTIFACT_FULL_RATE_EVIDENCE','REVIEWED_FULL_LIFECYCLE_WINDOW','LONG_LIFECYCLE_ENVIRONMENT_OR_PROVEN_FIT')
PHASE='ENTRY'
DIAGNOSTIC_HELPER_SHA='f600f3d8c39503e05979b3c274e93bde594743a093bcdb3fabb990560568dc79'
_diagnostic_helper=None
class Refusal(ValueError):pass
def need(v,code):
 if not v:raise Refusal(code)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p,cap=16<<20):
 p=P(p);need(p.is_file()and not any(x.is_symlink()for x in(p,*p.parents))and p.stat().st_size<=cap,'INPUT_FILE')
 def pairs(rows):
  result={}
  for k,v in rows:need(k not in result,'DUPLICATE_JSON_KEY');result[k]=v
  return result
 return json.loads(p.read_text(),object_pairs_hook=pairs,parse_constant=lambda _:need(False,'NONFINITE_JSON'))
def write(p,d):
 with P(p).open('x')as f:json.dump(d,f,sort_keys=True);f.write('\n')
def pin(p):return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def emit(d):print(json.dumps(d,sort_keys=True,allow_nan=False),flush=True)
def module(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m

def check_identity(repo,identity,clock):
 need(type(GEN)is str and re.fullmatch('[0-9a-f]{64}',GEN)and type(CAT)is str and re.fullmatch('[0-9a-f]{64}',CAT)and type(SOURCE_COUNT)is int and SOURCE_COUNT>0,'SOURCE_IDENTITY_UNFINALIZED')
 need(identity['schema']=='GDN32_FULL_MODEL_JOB_IDENTITY_V1'and identity['nonce']==NONCE,'LAUNCH_IDENTITY')
 need(identity['hardware_generation_sha256']==HW and identity['model_generation_sha256']==GEN,'GENERATION_IDENTITY')
 need(type(identity['selected_profile'])is int and 0<=identity['selected_profile']<5,'PROFILE_SELECTION')
 need(str(identity['run_id'])==os.environ.get('GITHUB_RUN_ID')and identity['launch_commit']==os.environ.get('GITHUB_SHA')and os.environ.get('GITHUB_RUN_ATTEMPT')=='1','ACTUAL_FIRST_JOB')
 need(clock['schema']=='SAME_JOB_START_V1'and clock['run_id']==identity['run_id']and clock['launch_commit']==identity['launch_commit']and clock['job_budget_seconds']==JOB,'ORIGINAL_JOB_CLOCK')
 need(type(clock['started_monotonic'])in(int,float)and math.isfinite(clock['started_monotonic'])and 0<=time.monotonic()-clock['started_monotonic']<JOB,'JOB_DEADLINE')
 need(subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()==identity['source_commit'],'SOURCE_CHECKOUT')
 need(HERE==repo/'candidates/gdn32_first_retry1_launch_20261104','SOURCE_ENTRY_LOCATION')

def capabilities(profile,work,clock):
 remaining=math.floor(JOB-(time.monotonic()-clock['started_monotonic']))
 row=dict(schema='GDN32_FULL_LAUNCH_CAPABILITY_V1',phase='PRE_NATIVE',selected_profile=profile,status='REFUSED',code='OBSERVATION_UNAVAILABLE',mem_total_bytes=None,mem_available_bytes=None,disk_free_bytes=None,required_memory_bytes=13<<30,required_disk_bytes=DISK,remaining_wall_seconds=remaining,p0_avx512_required=profile==0,avx512_present=None,native_model_started=False,dut_started=False)
 try:
  mem={line.split(':')[0]:int(line.split()[1])*1024 for line in P('/proc/meminfo').read_text().splitlines()if line.startswith(('MemTotal:','MemAvailable:'))};flags=P('/proc/cpuinfo').read_text().split();free=shutil.disk_usage(work.parent).free
  row.update(mem_total_bytes=mem['MemTotal'],mem_available_bytes=mem['MemAvailable'],disk_free_bytes=free,avx512_present='avx512f'in flags)
  code='PYTHON_ABI'if sys.version_info[:2]!=(3,12)or platform.machine()!='x86_64'else'P0_REQUIRES_AVX512'if profile==0 and not row['avx512_present']else'MEMORY_AVAILABLE'if mem['MemAvailable']<13<<30 else'DISK_FREE'if free<DISK else'JOB_DEADLINE'if remaining<=0 else'OK'
  row.update(code=code,status='ADMITTED'if code=='OK'else'REFUSED')
 except(OSError,KeyError,IndexError,ValueError):pass
 emit(row);need(row['status']=='ADMITTED',row['code']);return row

def source_closure(repo,plan):
 need(type(CAT)is str and re.fullmatch('[0-9a-f]{64}',CAT)and type(SOURCE_COUNT)is int and SOURCE_COUNT>0,'SOURCE_CATALOG_UNFINALIZED')
 catalog=repo/MODEL/'GDN32_FULL_SOURCE_PINS.json';need(sha(catalog)==CAT==plan['source_catalog_sha256'],'SOURCE_CATALOG_IDENTITY')
 rows=read(catalog)['files'];need(len(rows)==SOURCE_COUNT,'SOURCE_CATALOG_COUNT');seen=set()
 for r in rows:
  rel=P(r['path']);need(not rel.is_absolute()and'..'not in rel.parts and str(rel)not in seen,'SOURCE_CATALOG_PATH');seen.add(str(rel));p=repo/rel
  regular=p.is_file()and not any(x.is_symlink()for x in(p,*p.parents));actual=sha(p)if regular else None;size=p.stat().st_size if regular else None
  if not regular or size!=r['bytes']or actual!=r['sha256']:
   emit(dict(schema='GDN32_SOURCE_PIN_FAILURE_V1',phase='SOURCE_CLOSURE',source_role=str(rel)if re.fullmatch('[A-Za-z0-9_./-]{1,512}',str(rel))else'REDACTED',expected_sha256=r['sha256'],actual_sha256=actual,expected_bytes=r['bytes'],actual_bytes=size,native_model_started=False,dut_started=False))
   raise Refusal('SOURCE_PIN_DRIFT')
 return catalog

def reviewed_basis(repo,basis_row,profile,watchdog,expected_sv):
 def pinned(row):
  need(type(row)is dict and set(row)=={'source_path','sha256'},'FULL_BASIS_PIN_SCHEMA')
  rel=P(row['source_path']);need(not rel.is_absolute()and'..'not in rel.parts,'FULL_BASIS_PATH')
  path=repo/rel;doc=read(path,2<<20);need(sha(path)==row['sha256'],'FULL_BASIS_DIGEST');return doc
 basis=pinned(basis_row)
 need(basis['schema']=='GDN32_FULL_WINDOW_REVIEW_V1'and basis['profile']==profile and basis['tokens']==128,'FULL_BASIS_PROFILE')
 need(basis['hardware_generation_sha256']==HW and basis['model_generation_sha256']==GEN and basis['source_catalog_sha256']==CAT,'FULL_BASIS_IDENTITY')
 need(basis['watchdog']==watchdog and basis['job_budget_seconds']==JOB and basis['host_phase_seconds']==9000 and basis['completion_guaranteed']is False,'FULL_BASIS_WINDOW')
 rate=pinned(basis['actual_rate_evidence']);review=pinned(basis['independent_lifecycle_review'])
 need(rate['schema']=='ACTUAL_GDN32_HOST_RATE_EVIDENCE_V1'and rate['hardware_generation_sha256']==HW and rate['model_generation_sha256']==GEN and rate['profile']==profile,'ACTUAL_NEW_ARTIFACT_RATE')
 need(rate['scope']=='ACTUAL_FULL_MODEL_PROGRAM_PATH'and rate['source_catalog_sha256']==CAT and rate['driver_sha256']==DRIVER,'ACTUAL_RATE_FULL_PATH')
 need(rate['synthetic']is False and type(rate['run_id'])is int and rate['run_id']>0 and type(rate['source_commit'])is str and re.fullmatch('[0-9a-f]{40}',rate['source_commit'])and type(rate['sv_sha256'])is str and re.fullmatch('[0-9a-f]{64}',rate['sv_sha256']),'ACTUAL_RATE_PROVENANCE')
 need(rate['cpu_affinity_count']==1 and rate['threads']==1 and rate['cpp_policy']=='O1'and type(rate['completed_cycles'])is int and rate['completed_cycles']>0 and type(rate['elapsed_seconds'])in(int,float)and math.isfinite(rate['elapsed_seconds'])and rate['elapsed_seconds']>0,'ACTUAL_RATE_MEASUREMENTS')
 need(expected_sv is None or expected_sv==rate['sv_sha256'],'RATE_COHORT_SV')
 need(review['schema']=='GDN32_FULL_LIFECYCLE_REVIEW_V1'and review['profile']==profile and review['model_generation_sha256']==GEN and review['watchdog']==watchdog and review['host_phase_seconds']==9000 and review['job_budget_seconds']==JOB,'INDEPENDENT_LIFECYCLE_IDENTITY')
 cycles=review['full_program_cycle_bound'];seconds=review['required_dut_wall_seconds']
 need(type(cycles)is int and 0<cycles<=watchdog['max_active_cycles']and type(seconds)is int and 0<seconds<=watchdog['wall_seconds'],'FULL_PROGRAM_REQUIRED_WINDOW')
 need(seconds>=math.ceil(cycles*rate['elapsed_seconds']/rate['completed_cycles']),'MEASURED_RATE_WINDOW_DOES_NOT_FIT')
 need(review['mem_available_min_bytes']>=13<<30 and review['disk_free_min_bytes']>=DISK and review['max_build_seconds']==7200,'ORIGINAL_RESOURCE_REQUIREMENTS')
 return rate['sv_sha256']

def first_policy(doc,identity,catalog,repo,clock):
 """Explicit first continuous P1 attempt, not a rate-derived completion claim."""
 need(identity['selected_profile']==1 and type(identity['selected_profile'])is int and doc['first_profile']==1 and type(doc['first_profile'])is int,'FIRST_P1_ONLY')
 need(doc['approval']==FIRST and doc['lifecycle_policy']==FIRST and doc['missing_requirements']==[],'FIRST_EXPLICIT_POLICY')
 need(type(clock)is dict and clock.get('schema')=='SAME_JOB_START_V1'and clock.get('run_id')==identity['run_id']and clock.get('launch_commit')==identity['launch_commit']and clock.get('job_budget_seconds')==JOB,'FIRST_ORIGINAL_CLOCK')
 started=clock.get('started_monotonic');need(type(started)in(int,float)and math.isfinite(started)and 0<=time.monotonic()-started<JOB,'FIRST_ORIGINAL_CLOCK')
 need(type(CAT)is str and re.fullmatch('[0-9a-f]{64}',CAT)and doc['source_catalog_sha256']==CAT==sha(catalog),'SOURCE_CATALOG_UNFINALIZED')
 need(type(doc['profile_windows'])is dict and set(doc['profile_windows'])==set(map(str,range(5))),'FIRST_PROFILE_INVENTORY')
 for key,row in doc['profile_windows'].items():
  need(type(row)is dict and set(row)=={'approved','watchdog','basis'},'FIRST_WINDOW_FIELDS')
  if key!='1':need(row=={'approved':False,'watchdog':None,'basis':None},'FIRST_OTHER_PROFILE_BLOCKED')
 row=doc['profile_windows']['1'];need(row['approved']is True,'FIRST_APPROVAL')
 need(all(type(v)is str and re.fullmatch('[0-9a-f]{64}',v)for v in(FIRST_PLAN_SHA,FIRST_HELPER_SHA)),'FIRST_SOURCE_PINS_UNFINALIZED')
 need(row['basis']=={'source_path':FIRST_PLAN_REL,'sha256':FIRST_PLAN_SHA},'FIRST_REVIEWED_PLAN_PIN')
 path=repo/FIRST_PLAN_REL;review=read(path,65536);need(sha(path)==FIRST_PLAN_SHA,'FIRST_REVIEWED_PLAN_PIN')
 helper_path=repo/FIRST_HELPER_REL;need(sha(helper_path)==FIRST_HELPER_SHA,'FIRST_HELPER_PIN')
 rows=read(catalog)['files'];pins={r['path']:r for r in rows}
 for rel,want in((FIRST_PLAN_REL,FIRST_PLAN_SHA),(FIRST_HELPER_REL,FIRST_HELPER_SHA)):
  need(rel in pins and pins[rel]['sha256']==want and pins[rel]['bytes']==(repo/rel).stat().st_size,'FIRST_CATALOG_MEMBERSHIP')
 need(review['schema']=='GDN32_FIRST_REVIEWED_WINDOW_PLAN_V1'and review['selected_profiles']==[1],'FIRST_REVIEWED_PLAN_SCOPE')
 for key,value in(('min_dut_wall_seconds',3000),('max_dut_wall_seconds',7200),('min_build_window_seconds',5537),('census_reserved_seconds',30),('post_freeze_control_seconds',60),('maximum_material_elapsed_seconds_at_build_admission',1903)):
  need(type(review.get(key))is int and review[key]==value,'FIRST_REVIEWED_BUDGET')
 goal=dict(pc_at_least=7,completions_at_least=7,reset_after_start_allowed=False,necessary_active_cycles=21516288,completion_guaranteed=False)
 need(review['meaningful_goal']==goal and review['numerical_or_final_rtl_acceptance']is False,'FIRST_MEANINGFUL_GOAL')
 h=module('source_pinned_first_attempt',helper_path)
 need(h.FIRST==FIRST and h.JOB_SECONDS==JOB and h.FIXED_TAIL_SECONDS==10470 and h.CENSUS_SECONDS==30 and h.CONTROL_SECONDS==60 and sum(h.HOST_PHASES.values())==9000,'FIRST_HELPER_BUDGET_IDENTITY')
 policy=h.FirstPolicy(review['min_dut_wall_seconds'],review['max_dut_wall_seconds'],review['min_build_window_seconds'],h.file_pin(path))
 expected=dict(wall_seconds=7200,cpu_seconds=7200,max_active_cycles=1000000000,log_raw_bytes=16<<30,rss_telemetry_raw_bytes=16<<30,log_compressed_bytes=64<<20,rss_telemetry_compressed_bytes=64<<20)
 for phase,seconds in h.HOST_PHASES.items():
  for kind in('wall','cpu'):expected[phase+'_'+kind+'_seconds']=seconds
 need(row['watchdog']==expected and all(type(v)is int for v in row['watchdog'].values()),'FIRST_ORIGINAL_WATCHDOG_CAPS')
 need(type(doc['bootstrap_seconds'])is int and 0<doc['bootstrap_seconds']<=1800 and doc['bootstrap_seconds']<=policy.min_build_window_seconds,'FIRST_BOOTSTRAP_CAP')
 return policy.row()

def full_plan(doc,identity,catalog,repo,clock=None):
 need(doc['schema']=='GDN32_FULL_MODEL_SOURCE_PLAN_V1'and doc['scope']=='FULL_M128_MODEL_EVALUATION_NOT_FINAL_RTL','FULL_PLAN_SCHEMA')
 need(doc['registered_profiles']==list(range(5))and doc['tokens']==128 and doc['hardware_generation_sha256']==HW and doc['model_generation_sha256']==GEN,'FULL_PLAN_HARDWARE')
 need(doc['job_budget_seconds']==JOB and doc['completion_guaranteed']is False and doc['payload_uploads']is False and doc['final_rtl_acceptance']is False,'FULL_PLAN_SCOPE')
 i=identity['selected_profile'];row=doc['profile_windows'][str(i)]
 is_first=doc['approval']==FIRST
 if (not is_first and doc['approval']!='REVIEWED_FINITE_FULL_ATTEMPT')or row['approved']is not True:
  emit(dict(schema='GDN32_FULL_PLAN_ADMISSION_V1',status='REFUSED',code='FULL_PLAN_NOT_APPROVED',selected_profile=i,missing_requirements=[k for k in MISSING if k in doc['missing_requirements']],native_model_started=False,dut_started=False))
  raise Refusal('FULL_PLAN_NOT_APPROVED')
 need(doc['missing_requirements']==[]and type(doc['first_profile'])is int and 0<=doc['first_profile']<5,'FULL_PLAN_REVIEW_INCOMPLETE')
 expected=identity['expected_cohort_sv_sha256'];need((expected is None and i==doc['first_profile'])or(type(expected)is str and re.fullmatch('[0-9a-f]{64}',expected)),'COHORT_SV_REQUIRED')
 first=first_policy(doc,identity,catalog,repo,clock)if is_first else None
 if not is_first:expected=reviewed_basis(repo,row['basis'],i,row['watchdog'],expected)
 # Preserve the frozen actual FULL admission and its exact host/resource caps.
 helper=module('fixed_full_bridge',repo/MODEL/'numeric/samejob_gdn32_full.py')
 d=dict(selected_profiles=[i],registered_profiles=list(range(5)),tokens=128,hardware_generation_sha256=HW,model_generation_sha256=GEN,source_overlay_sha256=helper.OVERLAY_SHA,source_contract_sha256=helper.SOURCE_CONTRACT_SHA,job_budget_seconds=JOB,scope=helper.SCOPE,completion_guaranteed=False,execution_policy='FULL_PROGRAM_FINITE_WATCHDOG_NO_SHORT_FALLBACK',lifecycle_policy=doc['lifecycle_policy'],bootstrap_seconds=doc['bootstrap_seconds'],profiles={str(i):row['watchdog']},source_catalog=pin(catalog),expected_cohort_sv_sha256=expected)
 if is_first:d['first_attempt']=first
 helper.budget_shape({'gdn32_full':d});return d

def safe_first_window(d):
 """Only the source's finite FIRST gate vocabulary may reach stdout."""
 fixed=dict(fixed_tail_seconds=10470,census_reserved_seconds=30,post_freeze_control_seconds=60,min_dut_wall_seconds=3000,max_dut_wall_seconds=7200,min_build_window_seconds=5537)
 phases={'FIRST_BUILD_ADMISSION':('BUILD_WINDOW_OR_IMMUTABLE_BINDING',5537),'FIRST_RUNTIME_FREEZE':('RUNTIME_WINDOW_OR_IMMUTABLE_BINDING',3000)}
 if type(d)is not dict or d.get('schema')!='GDN32_FIRST_WINDOW_GATE_V1' or type(d.get('phase'))is not str or d['phase']not in phases or d.get('native_started_by_gate')is not False:return None
 if any(type(d.get(k))is not int or d[k]!=v for k,v in fixed.items()):return None
 remaining=d.get('remaining_wall_seconds');seconds=d.get('derived_stage_seconds');reason,floor=phases[d['phase']]
 if type(remaining)is not int or not -21000<=remaining<=21000:return None
 admitted=d.get('status')=='ADMITTED'and d.get('code')=='OK'and type(seconds)is int and floor<=seconds<=7200
 refused=d.get('status')=='REFUSED'and d.get('code')==reason and seconds is None
 if not(admitted or refused):return None
 return dict(schema='GDN32_FIRST_WINDOW_GATE_V1',phase=d['phase'],status=d['status'],code=d['code'],remaining_wall_seconds=remaining,derived_stage_seconds=seconds,native_started_by_gate=False,**fixed)

def safe_first_target(summary,selected):
 """Project only the same source-verified P1 observations, never numerical PASS."""
 q=summary.get('numeric_qualification')if type(summary)is dict else None
 if type(selected)is not int or selected!=1 or type(q)is not dict or q.get('status')!='VERIFIED_REAGGREGATED':return None
 # summarize_same_job moves verified full_execution_progress to execution_progress
 # and removes the nested key before returning its final safe summary envelope.
 progress=summary.get('execution_progress')
 if type(progress)is not dict or progress.get('scope')!='POST_CLEANUP_SAME_JOB_LOCAL_LOG_OBSERVATIONS_ONLY' or progress.get('numerical_pass')is not False:return None
 rows=progress.get('profiles')
 if type(rows)is not list or not 1<=len(rows)<=5:return None
 rows=[r for r in rows if type(r)is dict and type(r.get('profile'))is int and r['profile']==1]
 if len(rows)!=1:return None
 row=rows[0];target=row.get('first_meaningful_target')
 if type(target)is not dict or target.get('schema')!='GDN32_FIRST_MEANINGFUL_TARGET_V1' or type(target.get('profile'))is not int or target['profile']!=1:return None
 constants={'necessary_active_cycles':21516288,'full_program_commands':17,'tokens':128}
 if any(type(target.get(k))is not int or target[k]!=v for k,v in constants.items()):return None
 if any(target.get(k)is not False for k in('numerical_pass','final_rtl_acceptance','completion_guaranteed')):return None
 last=row.get('last');valid=row.get('status')=='OBSERVED_PARTIAL_NOT_NUMERICAL_PASS'and type(last)is dict
 pc=last.get('pc')if valid else None;completions=last.get('completions')if valid else None
 if valid and any(type(v)is not int or not 0<=v<2**64 for v in(pc,completions)):return None
 if target.get('observed_pc')!=pc or target.get('observed_completions')!=completions:return None
 if valid:
  if any(type(target.get(k))is not int for k in('observed_pc','observed_completions')):return None
 elif any(target.get(k)is not None for k in('observed_pc','observed_completions')):return None
 reached=valid and pc>=7 and completions>=7 and row.get('observed_reset_after_start')is False
 label='TARGET_REACHED_NOT_FULL'if reached else'TARGET_NOT_REACHED'
 attempt='INCOMPLETE_TIMEOUT'if row.get('log_termination_reason')=='WALL_TIMEOUT'else'REQUIRES_ORIGINAL_NUMERICAL_QUALIFICATION'
 if target.get('target_status')!=label or target.get('attempt_status')!=attempt:return None
 return dict(schema='GDN32_FIRST_MEANINGFUL_TARGET_V1',profile=1,target_status=label,attempt_status=attempt,observed_pc=pc,observed_completions=completions,numerical_pass=False,final_rtl_acceptance=False,completion_guaranteed=False,**constants)

def diagnostic_helper():
 global _diagnostic_helper
 path=HERE/'safe_build_diagnostics.py'
 need(path.is_file()and not any(p.is_symlink()for p in(path,*path.parents))and 0<path.stat().st_size<=65536 and sha(path)==DIAGNOSTIC_HELPER_SHA,'DIAGNOSTIC_HELPER_PIN')
 if _diagnostic_helper is None:_diagnostic_helper=module('fixed_safe_build_diagnostics',path)
 return _diagnostic_helper

class SafeStageStream:
 """Forward only bounded fixed diagnostics/resource records, never raw text."""
 def __init__(self):
  self.helper=diagnostic_helper();self.lines=self.helper.BoundedLines();self.forwarded=0;self.output_bytes=0
 def write(self,text):
  size=len(text)if type(text)is str else 0
  for line in self.lines.feed(text):
   if self.forwarded>=self.helper.MAX_OUTPUT_RECORDS:continue
   raw=self.helper.project_line(line)
   if raw is None:
    if len(line.encode('utf-8'))>8192:continue
    try:d=json.loads(line,object_pairs_hook=self.helper.unique,parse_constant=self.helper.invalid_constant)
    except(ValueError,TypeError,RecursionError):continue
    if type(d)is not dict or d.get('schema')not in('GDN32_FRESH_RESOURCE_GATE_V1','GDN32_PRE_NATIVE_CAPABILITY_V1','GDN32_CONSUMER_DEADLINE_V1','GDN32_FIRST_WINDOW_GATE_V1'):continue
    if d['schema']=='GDN32_FIRST_WINDOW_GATE_V1':
     safe=safe_first_window(d)
     if safe is None:continue
    else:
     allowed={'mem_total_bytes','mem_available_bytes','disk_free_bytes','required_memory_bytes','required_disk_bytes','tree_reserved_bytes','supervisor_runtime_disk_floor_bytes','remaining_wall_seconds','declared_stage_wall_seconds','complete_numeric_tail_reserved_seconds','complete_profile_and_parent_reserved_seconds','native_started_by_gate','native_started','dut_started','p0_avx512_required','avx512_present'}
     safe={k:v for k,v in d.items()if k in allowed and(type(v)is bool or type(v)is int and -21000<=v<=2**63 or v is None)}
     for k in('schema','phase','status','code'):
      if type(d.get(k))is str and re.fullmatch('[A-Z0-9_]{1,80}',d[k]):safe[k]=d[k]
    raw=json.dumps(safe,sort_keys=True,allow_nan=False)
   encoded=(raw+'\n').encode('utf-8')
   if self.output_bytes+len(encoded)>self.helper.MAX_OUTPUT_BYTES:continue
   sys.__stdout__.write(raw+'\n');sys.__stdout__.flush();self.forwarded+=1;self.output_bytes+=len(encoded)
  return size
 def flush(self):pass

def summarize_results(repo,work,identity):
 # Reuse the frozen source-pinned evidence readers and their9000s host envelope.
 helper_path=repo/MODEL/'summarize_same_job.py';catalog=repo/MODEL/'GDN32_FULL_SOURCE_PINS.json'
 need(sha(catalog)==CAT,'SUMMARY_CATALOG_PIN')
 rows=read(catalog)['files'];expected=next(r['sha256']for r in rows if r['path']==str(helper_path.relative_to(repo)))
 need(sha(helper_path)==expected,'SUMMARY_SOURCE_PIN')
 helper=module('fixed_safe_summary',helper_path)
 with contextlib.redirect_stdout(SafeStageStream()),contextlib.redirect_stderr(SafeStageStream()):summary=helper.summarize(work,identity)
 selected=identity['selected_profile'];q=summary.get('numeric_qualification')or{};verified=q.get('status')=='VERIFIED_REAGGREGATED'
 profiles=[]
 if verified:
  for row in q.get('profiles',[]):
   if row.get('profile')!=selected:continue
   qual=row.get('qualification')or{};common=row.get('common_artifact_identity')or{}
   profiles.append(dict(profile=selected,status=qual.get('status')if qual.get('status')in('PASS_FULL128_EXACT_REFERENCE','FAIL_EXACT_REFERENCE','INCOMPLETE')else'INCOMPLETE',sv_sha256=common.get('sv_sha256')if type(common.get('sv_sha256'))is str and re.fullmatch('[0-9a-f]{64}',common['sv_sha256'])else None,driver_sha256=common.get('driver_sha256')if type(common.get('driver_sha256'))is str and re.fullmatch('[0-9a-f]{64}',common['driver_sha256'])else None))
 stages=[]
 for row in summary.get('stages',[])[:40]:
  if type(row)is not dict:continue
  item={k:v for k,v in row.items()if k in('native_exit','errors','wall_seconds','observed_cpu_seconds','observed_peak_rss','cleanup_complete','pipe_eof','gzip_finalized')and(type(v)is bool or type(v)in(int,float)and math.isfinite(v)and abs(v)<=2**63 or v is None)}
  if type(row.get('phase'))is str and re.fullmatch('[a-z0-9_]{1,48}',row['phase']):item['phase']=row['phase']
  stages.append(item)
 result=dict(schema='GDN32_FULL_MODEL_SAFE_RESULT_V1',selected_profile=selected,status='EVIDENCE_REVERIFIED'if verified else'INCOMPLETE_OR_FAILED',profiles=profiles,stages=stages,all_five_required=True,numerical_pass=False,final_rtl_acceptance=False,payload_uploaded=False)
 target=safe_first_target(summary,selected)
 if target is not None:result['first_meaningful_target']=target
 emit(result)
 # Resource records written by original producer are local only; forward allowlist.
 log=work/'build_parent.log'
 if log.is_file()and not log.is_symlink():
  stream=SafeStageStream()
  with log.open('rb')as f:
   read_bytes=0
   while read_bytes<8<<20:
    raw=f.readline(stream.helper.MAX_LINE_BYTES+1)
    if not raw:break
    read_bytes+=len(raw)
    stream.write(raw.decode('utf-8','replace'))
 return result

def run(args):
 global PHASE
 PHASE='IDENTITY'
 repo=args.repo.resolve();work=args.work;identity=read(args.identity,16384);clock=read(args.job_start,4096)
 check_identity(repo,identity,clock)
 need(work.is_absolute()and not work.exists()and not any(p.is_symlink()for p in(work,*work.parents)),'FRESH_JOB_ROOT')
 PHASE='PRE_NATIVE_CAPABILITY'
 capabilities(identity['selected_profile'],work,clock)
 PHASE='SOURCE_CLOSURE'
 planpath=HERE/'FULL_PLAN.json';need(sha(planpath)==identity['plan_sha256'],'IMMUTABLE_PLAN_PIN');doc=read(planpath,65536);catalog=source_closure(repo,doc)
 PHASE='FULL_PLAN'
 selected=full_plan(doc,identity,catalog,repo,clock)
 projected=work.parent/(work.name+'-FULL-PLAN.json');write(projected,selected)
 artifact={k:identity[k]for k in('run_id','source_commit','launch_commit','artifact_name','launch_manifest_path','launch_manifest_blob_sha')}
 artifactpath=work.parent/(work.name+'-ARTIFACT-IDENTITY.json');write(artifactpath,artifact)
 from types import SimpleNamespace
 prepare=module('fixed_full_prepare',repo/MODEL/'prepare_and_run.py')
 call=SimpleNamespace(repo=repo,work=work,identity=artifactpath,job_start=args.job_start,gdn32_full_plan=projected,gdn32_full_plan_sha256=sha(projected),execution_mode='FULL_BLOCK_ACCEPTANCE',full_block_budget=None,fresh_host_profile=True)
 PHASE='ORIGINAL_FULL_FLOW'
 emit(dict(schema='GDN32_FULL_LAUNCH_STAGE_V1',phase='ORIGINAL_FULL_FLOW',selected_profile=identity['selected_profile'],status='STARTING',completion_guaranteed=False))
 # Frozen pipeline owns its original native supervisors. No nested DUT wrapper.
 try:
  with contextlib.redirect_stdout(SafeStageStream()),contextlib.redirect_stderr(SafeStageStream()):code=prepare.run(call)
 finally:
  PHASE='SUMMARY'
  summarize_results(repo,work,identity)
  PHASE='ORIGINAL_FULL_FLOW'
 return code

def main():
 parser=argparse.ArgumentParser()
 for key in('repo','identity','job-start','work'):parser.add_argument('--'+key,type=P,required=True)
 args=parser.parse_args();code=1
 try:code=run(args)
 except Refusal as e:emit(dict(schema='GDN32_FULL_LAUNCH_RESULT_V1',status='REFUSED',phase=PHASE,code=str(e),numerical_pass=False))
 except Exception as e:emit(dict(schema='GDN32_FULL_LAUNCH_RESULT_V1',status='FAILED',phase=PHASE,code='STAGE_FAILED',error_class=type(e).__name__ if type(e).__name__ in('ValueError','OSError','RuntimeError','TimeoutError','KeyError')else'OTHER',numerical_pass=False))
 raise SystemExit(code)
if __name__=='__main__':main()
