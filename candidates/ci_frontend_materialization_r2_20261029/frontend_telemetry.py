"""Bounded typed diagnostics only. No raw argv, environment or logs exported."""
import pathlib,json,re,hashlib,shlex,time,math
REASONS={
'wall cap':'WALL_CAP','prelaunch work deadline':'PRELAUNCH_DEADLINE','post-cleanup deadline':'POST_CLEANUP_DEADLINE',
'sampled observed aggregate RSS cap':'RSS_CAP','sampled observed aggregate CPU cap':'CPU_CAP','sampled aggregate writable-root cap':'AGGREGATE_DISK_CAP','sampled stage output tree cap':'STAGE_DISK_CAP','sampled disk reserve':'DISK_RESERVE','file cap':'FILE_CAP','sampled log cap':'LOG_CAP','entry cap':'ENTRY_CAP','RSS telemetry 64MiB cap':'TELEMETRY_CAP','locked memory gate':'PRELAUNCH_MEMORY_GATE','locked disk gate':'PRELAUNCH_DISK_GATE','uncompressed log cap':'RAW_LOG_CAP','compressed log cap':'COMPRESSED_LOG_CAP','diagnostic line1MiB cap':'LOG_LINE_CAP','observed identities remain after group cleanup':'CLEANUP_REMAINING_IDENTITIES','reader completion deadline':'READER_COMPLETION_DEADLINE','reader join deadline':'READER_JOIN_DEADLINE','log EOF missing after cleanup':'LOG_EOF_MISSING','capture missing EOF; no full log claim':'LOG_EOF_MISSING','reader remains; retaining log/pipe/lock until process exit':'READER_STILL_ALIVE','log reader failure':'LOG_READER_FAILURE'}
def number(x,maximum=10**15):return type(x) in (int,float) and math.isfinite(x) and 0<=x<=maximum
def typed_metrics(r):
 out={}
 for k in ('observed_cpu_seconds','supervisor_cpu_seconds','parent_cpu_seconds','disk_census_total_seconds','minimum_MemAvailable_bytes','memory_reserve_warning_samples','peak_tree_bytes','peak_file_bytes','output_sample_count','output_sample_max_seconds','process_sample_count','process_sample_max_seconds','max_monitor_interval_seconds','disk_census_count','disk_census_max_seconds','disk_census_last_seconds','process_sample_max_gap_seconds','process_sample_terminal_gap_seconds'):
  if number(r.get(k)):out[k]=r[k]
 caps=r.get('caps',{}) if isinstance(r.get('caps',{}),dict) else {};out['caps']={k:caps[k] for k in ('wall_seconds','cpu_seconds','rss_bytes','tree_bytes','watch_tree_bytes','raw_log_bytes','log_bytes') if number(caps.get(k))}
 proof=r.get('cleanup_proof');out['cleanup_status']='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP' if isinstance(proof,dict) and proof.get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP' else 'NOT_PROVEN'
 codes=[]
 for err in (r.get('errors',[]) if isinstance(r.get('errors',[]),list) else [])[:32]:
  if not isinstance(err,str):codes.append('UNCLASSIFIED_SUPERVISOR_ERROR');continue
  if err.startswith('log_reader: '):err=err[len('log_reader: '):]
  if err=='InterruptedError: signal 14':codes.append('SUPERVISOR_ALARM_SIGNAL_14')
  elif err in ('InterruptedError: signal 2','InterruptedError: signal 15'):codes.append('SUPERVISOR_EXTERNAL_SIGNAL')
  else:
   message=err.split(': ',1)[-1];code=REASONS.get(message)
   if code is None:
    if message.startswith(('input pin mismatch ','post-input pin mismatch ')):code='INPUT_PIN_DRIFT'
    elif message.startswith('JDK alias'):code='JDK_ALIAS_DRIFT'
    else:code='UNCLASSIFIED_SUPERVISOR_ERROR'
   codes.append(code)
 out['supervisor_reason_codes']=codes
 join=r.get('reader_join_barrier',{})
 if isinstance(join,dict):out['reader_join_barrier']={k:join[k] for k in ('complete','alive','reader_finally_done') if type(join.get(k))is bool}
 if type(r.get('reader_started_after_popen'))is bool:out['reader_started_after_popen']=r['reader_started_after_popen']
 c=r.get('log_capture',{}) if isinstance(r.get('log_capture',{}),dict) else {};log={}
 for k in ('raw_bytes','compressed_bytes','lines','error_lines'):
  if number(c.get(k)):log[k]=c[k]
 for k in ('raw_sha256','compressed_sha256'):
  if isinstance(c.get(k),str) and re.fullmatch('[0-9a-f]{64}',c[k]):log[k]=c[k]
 for k in ('pipe_eof_observed','gzip_finalized','capture_cap_hit'):
  if type(c.get(k))is bool:log[k]=c[k]
 h=c.get('warning_histogram',{});log['warning_histogram']={k:v for k,v in sorted(((k,v) for k,v in h.items() if isinstance(k,str)),key=lambda x:x[0])[:32] if isinstance(k,str) and re.fullmatch('[A-Z][A-Z0-9_]{0,63}',k) and number(v)} if isinstance(h,dict) else {}
 out['capture_census']=log
 return out
PREFIXES=('Vbf16_context_lane_cluster16_rev8b_b_candidate_d','Vqwen2_matrix_command_endpoint_0','VTransposedDenseDownOwner','VHostBlockTopV4')
def native_options(root):
 rows=[]
 for prefix in PREFIXES:
  p=pathlib.Path(root)/(prefix+'__hierMkArgs.f')
  if not p.is_file() or p.is_symlink() or p.stat().st_size>1024**2:continue
  data=p.read_bytes();row={'prefix':prefix,'args_sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
  try:
   tokens=shlex.split(data.decode());opts={};truncated=[]
   for flag in ('--cc','--exe','--build','--binary','--hierarchical','--no-std','--relative-includes','-Wno-fatal'):opts[flag]=flag in tokens
   for flag in ('--threads','--build-jobs','--verilate-jobs','--hierarchical-child','--output-split','--output-split-cfuncs'):
    indices=[i for i,v in enumerate(tokens) if v==flag];values=[]
    if len(indices)>8:truncated.append(flag)
    for i in indices[:8]:
     x=tokens[i+1] if i+1<len(tokens) else ''
     values.append(int(x) if re.fullmatch('[0-9]{1,9}',x) else 'INVALID_OR_MISSING')
    opts[flag]=values
   for flag in ('--top-module','--prefix','--lib-create'):
    indices=[i for i,v in enumerate(tokens) if v==flag]
    if len(indices)>8:truncated.append(flag)
    values=[tokens[i+1] if i+1<len(tokens) else '' for i in indices[:8]];opts[flag]=[x if re.fullmatch('[A-Za-z_][A-Za-z0-9_$]{0,127}',x) else 'INVALID_OR_MISSING' for x in values]
   row.update(options=opts,truncated_option_lists=truncated,sv_file_arguments=sum(x.endswith('.sv') for x in tokens),cpp_file_arguments=sum(x.endswith('.cpp') for x in tokens),include_arguments=sum(x.startswith('+incdir+') for x in tokens),define_arguments=sum(x.startswith('+define+') for x in tokens))
  except (ValueError,UnicodeError):row['parse_status']='UNPARSEABLE_ARGS_DIAGNOSTIC'
  rows.append(row)
 return rows

def output_inventory(root):
 root=pathlib.Path(root);out={'status':'UNAVAILABLE','files':0,'bytes':0};t=time.monotonic();h=hashlib.sha256();largest=[]
 if not root.is_dir() or root.is_symlink():return out
 try:
  paths=[];entries=0
  for p in root.rglob('*'):
   entries+=1
   if entries>20000 or time.monotonic()-t>20:raise ValueError('bounded census')
   if p.is_symlink():raise ValueError('symlink in generated output')
   if p.is_file():paths.append(p)
  for p in sorted(paths):
   if time.monotonic()-t>20 or out['bytes']>8*1024**3:raise ValueError('bounded census')
   rel=str(p.relative_to(root))
   if not re.fullmatch('[A-Za-z0-9_./$-]{1,256}',rel):raise ValueError('output name')
   before=p.stat();size=before.st_size
   if out['bytes']+size>8*1024**3:raise ValueError('aggregate inventory bound')
   if size>512*1024**2:raise ValueError('file inventory bound')
   fh=hashlib.sha256();read_bytes=0
   with p.open('rb') as f:
    for block in iter(lambda:f.read(65536),b''):
     read_bytes+=len(block)
     if read_bytes>size or read_bytes>512*1024**2:raise ValueError('growing file bound')
     if time.monotonic()-t>20:raise ValueError('bounded hashing')
     fh.update(block)
   after=p.stat()
   if read_bytes!=size or (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns):raise ValueError('output changed during inventory')
   sha=fh.hexdigest()
   h.update((rel+'\0'+str(size)+'\0'+sha+'\n').encode());out['files']+=1;out['bytes']+=size;largest.append({'relative_path':rel,'bytes':size,'sha256':sha});largest=sorted(largest,key=lambda x:(-x['bytes'],x['relative_path']))[:5]
  out['status']='COMPLETE_GENERATED_FILE_HASH_INVENTORY_ONLY'
 except (OSError,ValueError):out['status']='INCOMPLETE_BOUNDED_GENERATED_FILE_INVENTORY'
 out.update(inventory_sha256=h.hexdigest(),largest_files=largest,seconds=time.monotonic()-t)
 return out
