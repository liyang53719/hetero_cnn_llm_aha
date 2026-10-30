"""Only bounded scalar/hash status; never upload runtime/build/input bytes or paths."""
import argparse,hashlib,importlib.util,json,math,pathlib,re,sys
P=pathlib.Path;D=P(__file__).resolve().parent
_policy_spec=importlib.util.spec_from_file_location('samejob_profile_policy', D/'profile_policy.py');profile_policy=importlib.util.module_from_spec(_policy_spec);_policy_spec.loader.exec_module(profile_policy)
STATES={'STARTED_TIMEOUT_INCOMPLETE','STARTED_NATIVE_FAILED','COMPLETE_TERMINAL_DIAGNOSTIC_NOT_PASS','STARTED_OBSERVATION_INCOMPLETE'}
REASONS={'PYTHON_OR_ARCH','CPU_AVX512','IMAGE_VERSION','MEMAVAILABLE_13GIB','DISK_20671240864','SOURCE_PIN','JOB_DEADLINE','EXECUTION_FAILED_DETAILS_IN_STAGE_RECEIPTS'}
def read(p):
 if not p.is_file()or p.is_symlink()or p.stat().st_size>16<<20:return None
 try:return json.loads(p.read_text())
 except(ValueError,OSError):return None
def sha(p):
 with p.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def number(x):return x if type(x)in(int,float)and 0<=x<=2**63 and math.isfinite(x)else None
def hp(v):
 if not isinstance(v,dict)or not re.fullmatch('[0-9a-f]{64}',str(v.get('sha256',''))):return None
 n=v.get('bytes');return {'sha256':v['sha256'],'bytes':n}if type(n)is int and 0<=n<=4<<30 else None
def stage_resources(r):
 # Reuse original published classifier, not new monitoring logic or raw errors.
 path=D.parent/'ci_frontend_materialization_r2_20261029/frontend_telemetry.py'
 spec=importlib.util.spec_from_file_location('original_stage_telemetry',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 out=module.typed_metrics(r);caps=r.get('caps')or{}
 if not isinstance(caps,dict):caps={}
 for key in ('cleanup_seconds','file_bytes','min_free_disk_bytes','max_entries','per_process_as_bytes','per_process_cpu_seconds'):
  if number(caps.get(key))is not None:out['caps'][key]=caps[key]
 errors=r.get('errors');errors=errors if isinstance(errors,list)else[]
 out['error_evidence']=[];out['errors_truncated']=len(errors)>32
 for i,e in enumerate(errors[:32]):
  raw=e.encode('utf-8')if isinstance(e,str)else json.dumps(e,sort_keys=True).encode('utf-8')
  out['error_evidence'].append(dict(code=out['supervisor_reason_codes'][i],raw_bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
 out['worker_started']=r.get('worker_started')is True
 # The old monitor does not retain measured admission-free/MemAvailable values.
 out['initial_resource_observations']='NOT_RECORDED_BY_ORIGINAL_SUPERVISOR'
 return out

def install_snapshots(work):
 rows=[]
 reasons={'OBSERVED','NOT_OBSERVED','CLEANUP_OR_EOF_UNPROVEN','NO_UNRESERVED_DEADLINE_SLACK','OWNERSHIP_LOCK_BUSY','CENSUS_ENTRY_CAP','CENSUS_DEADLINE','CENSUS_UNAVAILABLE'}
 for key in ('qwen2','qwen35_08b','qwen35_35b'):
  for when in ('before','after'):
   label='install_'+key+'_'+when;p=work/'materials/results'/(label+'_RESOURCE.json')
   if not p.exists()and not p.is_symlink():continue
   base=dict(label=label,status='INVALID_FIELDS',resource_peak_qualification='INCOMPLETE_SAMPLED')
   try:
    if p.is_symlink()or not p.is_file()or p.stat().st_size>4096:raise ValueError('snapshot bound')
    r=read(p);base['receipt_sha256']=sha(p)
    expected='BEFORE_NATIVE'if when=='before'else'AFTER_CLEANUP_NOT_FAILURE_INSTANT'
    if not isinstance(r,dict)or r.get('schema')!='INSTALL_WHOLE_ROOT_SNAPSHOT_V1'or r.get('label')!=label or r.get('observation')!=expected or r.get('scope')!='WHOLE_JOB_AND_REPO_INODE_DEDUPLICATED'or r.get('resource_peak_qualification')!='INCOMPLETE_SAMPLED'or r.get('status')not in ('COMPLETE','UNAVAILABLE')or r.get('reason')not in reasons:raise ValueError('snapshot schema')
    selected=dict(observation=expected,scope=r['scope'],reason=r['reason'])
    if r['status']=='COMPLETE':
     if r['reason']!='OBSERVED':raise ValueError('complete reason')
     for k in ('bytes','files','entries','free_bytes','symlinks_not_followed'):
      if type(r.get(k))is not int or number(r[k])is None:raise ValueError('integer metric')
      selected[k]=r[k]
     for k in ('started_monotonic','finished_monotonic','elapsed_seconds'):
      if number(r.get(k))is None:raise ValueError('time metric')
      selected[k]=r[k]
     if selected['finished_monotonic']<selected['started_monotonic']:raise ValueError('time order')
    else:
     if r['reason']=='OBSERVED':raise ValueError('unavailable observed')
     if 'error_sha256'in r:
      if not re.fullmatch('[0-9a-f]{64}',str(r['error_sha256']))or type(r.get('error_bytes'))is not int or number(r['error_bytes'])is None:raise ValueError('error pin')
      selected.update(error_sha256=r['error_sha256'],error_bytes=r['error_bytes'])
    base.update(status=r['status'],**selected)
   except (OSError,ValueError,TypeError,KeyError):pass
   rows.append(base)
 return rows

def pack_deduplication(work):
 # One fixed journal; absence is not proof that the operation never started.
 out=dict(status='NOT_OBSERVED',scope='LIFECYCLE_JOURNAL_ONLY_NOT_NUMERICAL_PASS',physical_space_saved='NOT_MEASURED')
 p=work/'PACK_DEDUPLICATION.json'
 try:
  if not p.exists()and not p.is_symlink():return out
  out['status']='INVALID_FIELDS'
  if p.is_symlink()or not p.is_file()or p.stat().st_size>65536:return out
  with p.open('rb')as f:raw=f.read(65537)
  if len(raw)>65536:return out
  out['receipt_sha256']=hashlib.sha256(raw).hexdigest()
  r=json.loads(raw)
  states={'PREPARED','NO_OP_WRITER_CENSUS_UNAVAILABLE','NO_OP_MODE_MISMATCH','VERIFIED_BACKUPS_RETAINED','RECOVERY_REQUIRED','ROLLED_BACK','COMPLETE'}
  pair_states={'PENDING','UNCHANGED_NOT_DEDUPLICATED','REPLACED_BACKUP_RETAINED','BOTH_PATHS_RETAINED_SAME_INODE'}
  if not isinstance(r,dict)or r.get('schema')!='EXACT_TWO_COPY_DEDUPLICATION_V1'or r.get('scope')!='LIFECYCLE_ONLY_NOT_NUMERICAL_PASS'or r.get('status')not in states or r.get('physical_space_saved')!='NOT_MEASURED':return out
  saved=r.get('logical_saved_bytes');build=r.get('build_result_sha256');pairs=r.get('pairs')
  if type(saved)is not int or not 0<=saved<=362153111 or (r['status']!='COMPLETE'and saved!=0):return out
  if not isinstance(build,str)or not re.fullmatch('[0-9a-f]{64}',build):return out
  if not isinstance(pairs,list)or len(pairs)!=2:return out
  selected=[]
  for row in pairs:
   if not isinstance(row,dict)or row.get('role')not in ('sv','binary')or row.get('status')not in pair_states:return out
   selected.append(dict(role=row['role'],status=row['status']))
  if {x['role']for x in selected}!={'sv','binary'}:return out
  if r['status']=='COMPLETE'and any(x['status']!='BOTH_PATHS_RETAINED_SAME_INODE'for x in selected):return out
  census=r.get('writer_census')
  if r['status']=='NO_OP_WRITER_CENSUS_UNAVAILABLE'or isinstance(census,dict)and census.get('status')=='UNAVAILABLE':
   if r['status']not in {'NO_OP_WRITER_CENSUS_UNAVAILABLE','RECOVERY_REQUIRED','ROLLED_BACK'}:return out
   reasons={'PERMISSION_DENIED','PROCESS_OR_FD_DISAPPEARED','IO_UNAVAILABLE','DEADLINE','PROCESS_CAP','FD_CAP','MAPS_CAP','MALFORMED_PROC_METADATA'}
   if not isinstance(census,dict)or census.get('status')!='UNAVAILABLE'or census.get('reason')not in reasons or census.get('writers_absent_established')is not False or type(r.get('artifact_mutation_started'))is not bool:return out
   if r['status']=='NO_OP_WRITER_CENSUS_UNAVAILABLE'and(r['artifact_mutation_started']is not False or any(x['status']!='UNCHANGED_NOT_DEDUPLICATED'for x in selected)):return out
   if r['status']in {'RECOVERY_REQUIRED','ROLLED_BACK'}and r['artifact_mutation_started']is not True:return out
   out.update(writer_census=dict(status='UNAVAILABLE',reason=census['reason'],writers_absent_established=False),artifact_mutation_started=r['artifact_mutation_started'])
  out.update(status=r['status'],logical_saved_bytes=saved,build_result_sha256=build,pairs=selected)
 except (OSError,ValueError,TypeError,KeyError):out['status']='INVALID_FIELDS'
 return out

def fresh_host_projection(work,identity):
 # Fixed paths only. Receipt observations are not host or numerical qualification.
 out=dict(scope='IDENTITY_AND_PROCESS_OBSERVATIONS_ONLY_NOT_HOST_OR_NUMERICAL_PASS',host_qualified=False,numeric_pass=False)
 parent={'GNU_RUNTIME_ADMISSION':'GNU_RUNTIME_DEPENDENCIES_UNQUALIFIED','BOOTSTRAP_ALIAS':'RUNTIME_ALIAS_REJECTED','HOST_RECEIPT_ADMISSION':'FRESH_HOST_RECEIPT_REJECTED'}
 native={'UNCLASSIFIED_EXCEPTION','ELF_DEPENDENCY_UNRESOLVED','ELF_DEPENDENCY_ROOT_REJECTED','SEARCH_PATH_INJECTION_REJECTED','CONTRACT_REJECTED','JDK_QUERY_ROOT_REJECTED','QUERY_TIMEOUT','QUERY_FAILED','FILESYSTEM_UNAVAILABLE'}
 specs=(('stage','stage_fresh_host/RESULT.json',16<<20),('identity','fresh-host.json',16<<20),('parent_failure','FRESH_HOST_PARENT_FAILURE.json',4096),('native_failure','FRESH_HOST_NATIVE_FAILURE.json',4096))
 for role,name,limit in specs:
  path=work/'build'/name;row=dict(state='UNOBSERVED_NOT_QUALIFIED');out[role]=row
  try:
   if not path.exists()and not path.is_symlink():continue
   row['state']='INVALID_NOT_QUALIFIED'
   if path.is_symlink()or (work/'build').is_symlink()or path.parent.is_symlink()or not path.is_file()or path.stat().st_size>limit:continue
   r=read(path)
   if not isinstance(r,dict):continue
   digest=sha(path)
   if role=='identity':
    c=r.get('contract');pins=r.get('pins')
    if r.get('schema')!='BOUNDED_FRESH_HOST_IDENTITY_V1'or r.get('qualification')!='IDENTITY_ONLY_PENDING_ORIGINAL_BUILD_AND_NUMERICAL_GATES'or r.get('old_pass_transfer')is not False:continue
    if not isinstance(c,dict)or set(c)!={'schema','run_id','source_commit','launch_commit'}or c['schema']!='BOUNDED_FRESH_HOST_V1':continue
    if type(c['run_id'])is not int or c['run_id']<=0 or type(identity.get('run_id'))is not int:continue
    if any(not isinstance(c[k],str)or not re.fullmatch('[0-9a-f]{40}',c[k])for k in ('source_commit','launch_commit'))or c['source_commit']==c['launch_commit']:continue
    if any(c[k]!=identity.get(k)for k in ('run_id','source_commit','launch_commit')):continue
    if not isinstance(pins,dict)or not 0<len(pins)<=10000 or any(not isinstance(k,str)or not isinstance(v,str)or not re.fullmatch('[0-9a-f]{64}',v)for k,v in pins.items()):continue
    row.update(state='OBSERVED_IDENTITY_ONLY_NOT_QUALIFIED',receipt_sha256=digest,contract_identity_matches=True,pin_count=len(pins))
   elif role=='stage':
    cap=r.get('log_capture')or{};cleanup=r.get('cleanup_proof')or{};code=r.get('native_exit')
    if 'native_exit'not in r or (code is not None and(type(code)is not int or not -255<=code<=255))or not isinstance(cap,dict)or not isinstance(cleanup,dict)or not isinstance(r.get('errors'),list):continue
    row.update(state='OBSERVED_PROCESS_ONLY_NOT_QUALIFIED',receipt_sha256=digest,native_exit=code,errors=len(r['errors']),wall_seconds=number(r.get('elapsed_seconds')),observed_cpu_seconds=number(r.get('observed_cpu_seconds')),observed_peak_rss=number(r.get('observed_peak_rss')),cleanup_complete=cleanup.get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP',pipe_eof=cap.get('pipe_eof_observed')is True,gzip_finalized=cap.get('gzip_finalized')is True,resources=stage_resources(r))
   else:
    if r.get('status')!='FAILED'or r.get('numeric_pass')is not False:continue
    if role=='parent_failure':
     if r.get('schema')!='FRESH_HOST_PARENT_FAILURE_V1'or r.get('phase')not in parent or r.get('reason')!=parent[r['phase']]:continue
    elif r.get('schema')!='FRESH_HOST_NATIVE_FAILURE_V1'or r.get('phase')!='BOUNDED_HOST_INVENTORY'or r.get('reason')not in native:continue
    details={}
    if role=='native_failure'and any(k in r for k in ('query_role','rejection_kind','had_parent_component')):
     query=r.get('query_role')
     if not isinstance(query,str)or query not in {'SYSTEM_TOOL','JDK_EXECUTABLE','JDK_LIBRARY','VERILATOR_BINARY','PYTHON_EXTENSION','UNKNOWN'}:continue
     details['query_role']=query
     if 'rejection_kind'in r or 'had_parent_component'in r:
      kind=r.get('rejection_kind');parent_component=r.get('had_parent_component')
      if not isinstance(kind,str)or kind not in {'UNRESOLVED_LIBRARY','EMPTY_DEPENDENCY_LIST','MISSING_TARGET','NONREGULAR_TARGET','CANONICAL_ROOT_REJECTED'}or type(parent_component)is not bool:continue
      details.update(rejection_kind=kind,had_parent_component=parent_component)
    row.update(state='OBSERVED_FAILURE_NOT_QUALIFIED',receipt_sha256=digest,status='FAILED',phase=r['phase'],reason=r['reason'],**details)
  except (OSError,ValueError,TypeError,KeyError,AttributeError,ImportError):
   # Partial projection must not accidentally advertise a validated receipt.
   out[role]=dict(state='INVALID_NOT_QUALIFIED')
 return out

def execution_policy_summary(work):
 # Select only exact versioned policy; no arbitrary binding fields/paths exported.
 binding=read(work.parent/(work.name+'-BINDING.json'))
 failure=read(work.parent/(work.name+'-CONTROLLER_FAILURE.json'))
 rows=[r for r in (binding,failure)if isinstance(r,dict)and 'execution_policy'in r]
 if not rows:return dict(state='UNOBSERVED_NOT_QUALIFIED')
 try:
  value=profile_policy.checked(rows[0])
  for row in rows[1:]:profile_policy.require_same(rows[0],row)
  return dict(state='DECLARED_NOT_QUALIFIED',policy=value,profiles_registered=value['registered_profiles'],profiles_eligible=value['eligible_profiles'])
 except (ValueError,TypeError,KeyError):return dict(state='INVALID_OR_CONFLICTING_NOT_QUALIFIED')

def summarize(work,identity):
 out=dict(schema='FIVE_M128_SAME_JOB_SAFE_SUMMARY_V1',status='INCOMPLETE',numeric_pass=False,final_rtl_replay=False,uploaded_payloads=False,profiles_registered=list(range(5)),tokens=128,matrix_macs=4096,vector_lanes=32,resource_peak_qualification='INCOMPLETE_SAMPLED',stages=[],actual_dut_reports=[])
 out['vector_lanes_semantics']='DECLARED_ARTIFACT_TAG_NOT_VERIFIED_PHYSICAL_ISSUE_LANES'
 out['vector_ii1_verified']=False
 out['fresh_host']=fresh_host_projection(work,identity)
 out['execution_selection']=execution_policy_summary(work)
 out['installation_resource_snapshots']=install_snapshots(work)
 out['pack_deduplication']=pack_deduplication(work)
 for k in ('source_commit','launch_commit'):
  h=identity.get(k);out[k]=h if isinstance(h,str)and re.fullmatch('[0-9a-f]{40}',h)else None
 out['run_id']=identity.get('run_id')if type(identity.get('run_id'))is int else None
 failure=read(work.parent/(work.name+'-CONTROLLER_FAILURE.json'))or{}
 out['failure_reason']=failure.get('reason_code')if failure.get('reason_code')in REASONS else 'UNKNOWN_OR_NOT_FAILED'
 # Exact known stage roles only. No arbitrary recursive source/payload traversal.
 roles=[('archive',work/'runs/archives'),('weights',work/'runs/weights')]
 roles += [('install_'+k,work/'materials/runs'/k)for k in('qwen2','qwen35_08b','qwen35_35b','bind')]
 roles += [(f'reference{i}',work/f'materials/references/profile{i}/actual')for i in range(5)]
 numeric=work/'materials/numeric'
 roles += [(name,numeric/'runs'/name)for name in('startup_abi','p0_p0_rope','p0_p0_provider','p0_p0_transport','p1_p12_provider','p2_p12_provider','p3_p34_provider','p4_p34_provider')]
 for i in range(5):
  for suffix in('initialize','connect','dut'):roles.append((f'p{i}_{suffix}',numeric/'runs'/f'p{i}_{suffix}'))
 for name,folder in roles:
  p=folder/'RESULT.json';r=read(p)
  if not isinstance(r,dict):continue
  cap=r.get('log_capture')or{};cleanup=r.get('cleanup_proof')or{}
  out['stages'].append(dict(phase=name,receipt_sha256=sha(p),native_exit=r.get('native_exit')if type(r.get('native_exit'))is int else None,errors=len(r['errors'])if isinstance(r.get('errors'),list)else None,wall_seconds=number(r.get('elapsed_seconds')),observed_cpu_seconds=number(r.get('observed_cpu_seconds')),observed_peak_rss=number(r.get('observed_peak_rss')),process_sample_count=number(r.get('process_sample_count')),cleanup_complete=cleanup.get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP',pipe_eof=cap.get('pipe_eof_observed')is True,gzip_finalized=cap.get('gzip_finalized')is True,resources=stage_resources(r)))
 for i in range(5):
  p=numeric/f'PROFILE_{i}_DIAGNOSTIC.json';r=read(p)
  if not isinstance(r,dict)or r.get('profile')!=i or r.get('state')not in STATES or r.get('numerical_pass')is not False:continue
  selected={k:hp(r.get(k))for k in('report','startup','outer')}
  if all(selected.values()):out['actual_dut_reports'].append(dict(profile=i,state=r['state'],receipt_sha256=sha(p),**selected))
 # Reuse reviewed exact build exporter; it already strips paths and caps text.
 materialization=D.parent/'ci_frontend_materialization_r2_20261029'
 if (work/'build').exists()and(materialization/'summarize_build_only.py').is_file():
  try:
   sys.path.insert(0,str(materialization));spec=importlib.util.spec_from_file_location('original_safe_build_summary',materialization/'summarize_build_only.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
   out['build']=json.loads(m.encode_build_summary(m.build_summary(work/'build',out['source_commit'])))
  except Exception:out['build_summary_state']='UNAVAILABLE_NOT_PASS'
 return out
def encode(v):
 raw=json.dumps(v,ensure_ascii=True,sort_keys=True,indent=2)+'\n'
 if len(raw.encode())>65536:
  v['optional_build_details_truncated']=True
  for row in v.get('build',{}).get('stages',[]):
   for k in list(row):
    if k not in{'telemetry','stage','name','native_exit','elapsed_seconds','observed_peak_rss','error_count','observed_cpu_seconds','supervisor_cpu_seconds','parent_cpu_seconds','disk_census_total_seconds','minimum_MemAvailable_bytes','memory_reserve_warning_samples','peak_tree_bytes','peak_file_bytes','output_sample_count','output_sample_max_seconds','process_sample_count','process_sample_max_seconds','max_monitor_interval_seconds','disk_census_count','disk_census_max_seconds','disk_census_last_seconds','process_sample_max_gap_seconds','process_sample_terminal_gap_seconds','caps','cleanup_status','supervisor_reason_codes','reader_join_barrier','reader_started_after_popen','capture_census'}:del row[k]
  raw=json.dumps(v,ensure_ascii=True,sort_keys=True)+'\n'
 if len(raw.encode())>65536:raise ValueError('bounded summary exceeded; never upload unbounded output')
 return raw
if __name__=='__main__':
 p=argparse.ArgumentParser()
 for k in('work','identity','output'):p.add_argument('--'+k,type=P,required=True)
 a=p.parse_args();raw=encode(summarize(a.work,read(a.identity)or{}))
 with a.output.open('x')as f:f.write(raw)
