"""Only bounded scalar/hash status; never upload runtime/build/input bytes or paths."""
import argparse,hashlib,importlib.util,json,math,pathlib,re,sys
P=pathlib.Path;D=P(__file__).resolve().parent
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

def summarize(work,identity):
 out=dict(schema='FIVE_M128_SAME_JOB_SAFE_SUMMARY_V1',status='INCOMPLETE',numeric_pass=False,final_rtl_replay=False,uploaded_payloads=False,profiles_registered=list(range(5)),tokens=128,matrix_macs=4096,vector_lanes=32,resource_peak_qualification='INCOMPLETE_SAMPLED',stages=[],actual_dut_reports=[])
 out['installation_resource_snapshots']=install_snapshots(work)
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
