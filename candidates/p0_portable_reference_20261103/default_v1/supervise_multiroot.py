"""Observed descendants + original-group barrier. Not escaped-tree containment."""
import lossless_log
import host_checks
import threading,queue
import fcntl,hashlib,json,os,resource,signal,subprocess,sys,time,types,stat,shutil
from pathlib import Path
HELPER_SHA='30458e67e84c362ff74d69a702624e91bc3c3089600dd36a2469d9ffd6ec4047'
SIGNALS={signal.SIGINT,signal.SIGTERM,signal.SIGALRM}
DEAD={'Z','X','x'}
def need(ok,msg):
 if not ok:raise ValueError(msg)
def helper():
 p=Path(__file__).with_name('strict_cleanup.py');b=p.read_bytes();need(hashlib.sha256(b).hexdigest()==HELPER_SHA,'cleanup helper drift')
 m=types.ModuleType('admitted_cleanup');m._ADMITTED_SOURCE_SHA256=HELPER_SHA;exec(compile(b,str(p),'exec'),m.__dict__);return m
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def regular(p):
 p=Path(p).absolute()
 for q in (p,*p.parents):need(not q.is_symlink(),'symlink path '+str(q))
 need(p.is_file(),'missing file '+str(p));return p

def verify_aliases(aliases):
 for row in aliases:
  p=Path(row['path']);need(p.is_absolute() and p.is_symlink(),'JDK alias missing')
  need(os.readlink(p)==row['link'] and str(p.resolve(strict=True))==row['target'],'JDK alias mapping drift')

def _v2_validate_numeric_caps(caps):
 # Validate before opening the lock or claiming signals. In particular, no
 # malformed arithmetic operand may escape between ownership and the try.
 need(type(caps)is dict,'V2 numeric caps object')
 for key in ('wall_seconds','cleanup_seconds','cpu_seconds'):
  value=caps.get(key)
  need(type(value)in(int,float) and 0<value<=sys.float_info.max,'V2 finite positive numeric cap '+key)
 need(float(caps['wall_seconds'])+float(caps['cleanup_seconds'])<=sys.float_info.max,'V2 finite combined work and cleanup cap')
 required=('file_bytes','tree_bytes','log_bytes','max_entries','per_process_as_bytes','per_process_cpu_seconds','rss_bytes')
 optional=('raw_log_bytes','watch_tree_bytes','min_free_disk_bytes')
 for key in required+optional:
  if key in optional and key not in caps:continue
  value=caps.get(key);minimum=0 if key=='min_free_disk_bytes' else 1
  need(type(value)is int and minimum<=value<=sys.maxsize,'V2 finite integer cap '+key)

def _v2_set_owned_signal_mask(desired):
 # Alter only bits claimed by this V2 scope. Never restore an old whole mask:
 # unrelated signal changes made while the scope ran belong to their caller.
 owned=SIGNALS|{signal.SIGPROF}
 try:signal.pthread_sigmask(signal.SIG_BLOCK,owned&desired)
 finally:signal.pthread_sigmask(signal.SIG_UNBLOCK,owned-desired)

def _v2_claim_signal_ownership():
 # Only V2 opts into this stricter entry contract. Reject before installing a
 # handler or changing any timer, and preserve all rejected caller state.
 need(threading.current_thread() is threading.main_thread(),'V2 supervisor requires main thread')
 reserved=SIGNALS|{signal.SIGPROF}
 previous=signal.pthread_sigmask(signal.SIG_BLOCK,reserved)
 try:
  need(not ({signal.SIGALRM,signal.SIGPROF}&previous),'V2 watchdog signal initially blocked')
  need(not (reserved&signal.sigpending()),'V2 monitor signal initially pending')
  need(signal.getitimer(signal.ITIMER_REAL)==(0.,0.) and signal.getitimer(signal.ITIMER_PROF)==(0.,0.),'V2 watchdog timer initially active')
 except BaseException:
  _v2_set_owned_signal_mask(previous)
  raise
 return previous

def execute(argv,run,lock_path,caps,env,pins,inject_monitor_error=False,resource_gate=None):
 v2_signal_ownership='rss_telemetry_policy' in caps
 if v2_signal_ownership:need(threading.current_thread() is threading.main_thread(),'V2 supervisor requires main thread')
 strict=helper();run=Path(run).absolute();lock_path=Path(lock_path).absolute()
 need(not run.exists() and not run.is_symlink(),'one-shot output already exists')
 for q in run.parents:need(not q.is_symlink(),'symlink output parent')
 need(lock_path.parent.is_dir() and not lock_path.is_symlink(),'lock path')
 need(hasattr(os,'pidfd_open') and hasattr(signal,'pidfd_send_signal'),'pidfd support required')
 if v2_signal_ownership:_v2_validate_numeric_caps(caps)
 lock=os.open(lock_path,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BaseException:os.close(lock);raise
 if v2_signal_ownership:
  try:v2_oldmask=_v2_claim_signal_ownership()
  except BaseException:
   fcntl.flock(lock,fcntl.LOCK_UN);os.close(lock);raise
 parent_cpu_started=time.process_time()
 started=time.monotonic();work_stop=started+caps['wall_seconds'];stop=work_stop+caps['cleanup_seconds'];owner=None;log=None;telemetry=None;capture=None;leader=None;observed={};pidfds={};report={'status':'IN_PROGRESS','scope':'ORIGINAL_PROCESS_GROUP_AND_OBSERVED_DESCENDANTS_ONLY','argv':argv,'caps':caps,'worker_started':False,'errors':[],'observed_peak_rss':0,'observed_cpu_seconds':0,'peak_tree_bytes':0,'peak_file_bytes':0,'native_exit':None,'cleanup_proof':None};oldmask=v2_oldmask if v2_signal_ownership else signal.pthread_sigmask(signal.SIG_BLOCK,SIGNALS);oldhandlers={s:signal.getsignal(s) for s in SIGNALS};api=strict._Linux()
 telemetry_module=None;telemetry_policy=None;telemetry_closed_in_cleanup=False
 reader=None;reader_stop=threading.Event();reader_done=threading.Event();reader_errors=queue.SimpleQueue();last_process_sample=None
 def fail(e):report['errors'].append(type(e).__name__+': '+str(e))
 def drain_reader_errors():
  while not reader_errors.empty():
   kind,message=reader_errors.get();report['errors'].append('log_reader: '+kind+': '+message)
 def log_reader():
  try:
   while not reader_stop.is_set():
    got=capture.drain()
    if capture.eof:return
    if not got:reader_stop.wait(.002)
  except BaseException as e:reader_errors.put((type(e).__name__,str(e)))
  finally:
   try:capture.finish()
   except BaseException as e:reader_errors.put((type(e).__name__,str(e)))
   finally:reader_done.set()
 def timed_output_sample():
  t=time.monotonic()
  try:output_sample()
  finally:
   elapsed=time.monotonic()-t;report['disk_census_count']=report.get('disk_census_count',0)+1;report['disk_census_total_seconds']=report.get('disk_census_total_seconds',0)+elapsed;report['disk_census_max_seconds']=max(report.get('disk_census_max_seconds',0),elapsed);report['disk_census_last_seconds']=elapsed
 def interrupted(sig,frame):raise InterruptedError('signal '+str(sig))
 def limits():
  resource.setrlimit(resource.RLIMIT_CORE,(0,0))
  resource.setrlimit(resource.RLIMIT_FSIZE,(caps['file_bytes'],)*2);resource.setrlimit(resource.RLIMIT_AS,(caps['per_process_as_bytes'],)*2);resource.setrlimit(resource.RLIMIT_CPU,(caps['per_process_cpu_seconds'],)*2)
  # New default_v1 identity: preserve the independently admitted host affinity.
  os.sched_setaffinity(0,set(caps['admitted_affinity']))
  for s in SIGNALS:signal.signal(s,signal.SIG_DFL)
  signal.pthread_sigmask(signal.SIG_UNBLOCK,SIGNALS)
 def output_sample():
  total=largest=count=stage_total=stage_largest=0
  roots=[run]+[Path(x).absolute() for x in caps.get('extra_watch_roots',[])]
  unique=[]
  for root in sorted(set(roots),key=lambda p:len(p.parts)):
   if not any(root.is_relative_to(q) for q in unique):unique.append(root)
  seen=set();run_parts=run.parts
  for root in unique:
   for base,dirs,files in os.walk(root,followlinks=False):
    base_parts=Path(base).parts
    base_in_stage=base_parts[:len(run_parts)]==run_parts
    base_is_stage_parent=base_parts==run_parts[:-1]
    for name in dirs+files:
     p=os.path.join(base,name)
     in_stage=base_in_stage or (base_is_stage_parent and name==run_parts[-1])
     try:s=os.lstat(p)
     except FileNotFoundError:continue
     count+=1;need(count<=caps['max_entries'],'entry cap')
     if stat.S_ISLNK(s.st_mode):
      need(not in_stage,'output link forbidden');continue
     need(stat.S_ISDIR(s.st_mode) or stat.S_ISREG(s.st_mode),'nonregular output')
     if stat.S_ISREG(s.st_mode):
      key=(s.st_dev,s.st_ino)
      if key not in seen:
       seen.add(key);total+=s.st_size;largest=max(largest,s.st_size)
       if in_stage:stage_total+=s.st_size;stage_largest=max(stage_largest,s.st_size)
  for root in unique:
   if root.exists():
    free=shutil.disk_usage(root).free;report['minimum_free_disk_bytes']=min(report.get('minimum_free_disk_bytes',free),free)
    need(free>=caps.get('min_free_disk_bytes',0),'sampled disk reserve')
  report['peak_stage_tree_bytes']=max(report.get('peak_stage_tree_bytes',0),stage_total)
  report['peak_tree_bytes']=max(report['peak_tree_bytes'],total);report['peak_file_bytes']=max(report['peak_file_bytes'],largest)
  need(total<=caps.get('watch_tree_bytes',caps['tree_bytes']),'sampled aggregate writable-root cap');need(stage_total<=caps['tree_bytes'],'sampled stage output tree cap');need(stage_largest<=caps['file_bytes'],'stage file cap');need(largest<=2<<30,'owned-root file cap');need(os.fstat(log.fileno()).st_size<=caps['log_bytes'],'sampled log cap')
 def process_sample():
  nonlocal last_process_sample
  now=time.monotonic()
  if last_process_sample is not None:report['process_sample_max_gap_seconds']=max(report.get('process_sample_max_gap_seconds',0),now-last_process_sample)
  last_process_sample=now;report['process_sample_count']=report.get('process_sample_count',0)+1
  strict._verify_leader(owner,api,leader,boot);snapshot={};rawfields={};names=os.listdir('/proc');need(len(names)<=100000,'proc enumeration cap')
  for name in names:
   if not name.isascii() or not name.isdecimal():continue
   try:raw=(Path('/proc')/name/'stat').read_bytes()
   except (FileNotFoundError,ProcessLookupError):
    report['proc_stat_vanished_count']=report.get('proc_stat_vanished_count',0)+1;continue
   row=strict.parse_stat(raw);snapshot[row['pid']]=row;rawfields[row['pid']]=raw[raw.rindex(b')')+1:].split()
  selected={pid for pid,row in snapshot.items() if row['group']==leader['group'] or (pid in observed and row['start']==observed[pid]['start'])}
  changed=True
  while changed:
   added={pid for pid,row in snapshot.items() if row['ppid'] in selected and row['start']>=leader['start']};changed=not added<=selected;selected|=added
  need(len(selected)<=4096,'observed process cap');rss=0;sample_rows=[]
  for pid in selected:
   row=snapshot[pid]
   if pid in observed:need(row['start']==observed[pid]['start'],'tracked PID reused within owned set')
   else:
    observed[pid]={'pid':pid,'start':row['start'],'peak_cpu_ticks':0,'ever_outside_group':False}
    try:fd=os.pidfd_open(pid)
    except ProcessLookupError:continue
    check=api.read(pid)
    if check is None or check['start']!=row['start']:os.close(fd);continue
    pidfds[pid]=fd
   f=rawfields[pid];observed[pid]['peak_cpu_ticks']=max(observed[pid]['peak_cpu_ticks'],int(f[11])+int(f[12]));observed[pid]['ever_outside_group']|=row['group']!=leader['group'];pid_rss=max(0,int(f[21]))*os.sysconf('SC_PAGE_SIZE');rss+=pid_rss;observed[pid]['peak_rss_bytes']=max(observed[pid].get('peak_rss_bytes',0),pid_rss);observed[pid]['peak_virtual_bytes']=max(observed[pid].get('peak_virtual_bytes',0),int(f[20]));sample_rows.append([pid,row['start'],row['ppid'],row['group'],pid_rss,int(f[11])+int(f[12]),int(f[20])])
  cpu=sum(r['peak_cpu_ticks'] for r in observed.values())/os.sysconf('SC_CLK_TCK');report['observed_peak_rss']=max(report['observed_peak_rss'],rss);report['observed_cpu_seconds']=cpu
  need(time.monotonic()<caps['job_deadline_monotonic'],'global wall cap')
  need(cpu+caps['prior_child_cpu_seconds']+time.process_time()-caps['job_process_cpu_started']<=3600,'global charged CPU cap')
  available=host_checks.available_memory();need(available>=1<<30,'actual memory reserve');reserve_warning=available<1024**3;report['minimum_MemAvailable_bytes']=min(report.get('minimum_MemAvailable_bytes',available),available);report['memory_reserve_warning_samples']=report.get('memory_reserve_warning_samples',0)+int(reserve_warning)
  telemetry.write(json.dumps({'elapsed':time.monotonic()-started,'aggregate_rss_bytes':rss,'processes':sample_rows,'MemAvailable_bytes':available,'reserve_below_1GiB_warning':reserve_warning},separators=(',',':'))+'\n')
  if telemetry_policy is None:telemetry.flush();need(telemetry.tell()<=64*1024*1024,'RSS telemetry 64MiB cap')
  need(rss<=caps['rss_bytes'],'sampled observed aggregate RSS cap');need(cpu<=caps['cpu_seconds'],'sampled observed aggregate CPU cap')
 try:
  need(signal.getitimer(signal.ITIMER_REAL)==(0.,0.),'preexisting alarm')
  for s in SIGNALS:signal.signal(s,interrupted)
  signal.setitimer(signal.ITIMER_REAL,max(.001,work_stop-time.monotonic()));(_v2_set_owned_signal_mask(oldmask-SIGNALS) if v2_signal_ownership else signal.pthread_sigmask(signal.SIG_SETMASK,oldmask-SIGNALS))
  verify_aliases(caps.get('jdk_aliases',[]))
  for path,digest in pins.items():need(sha(regular(path))==digest,'input pin mismatch '+path)
  if 'rss_telemetry_policy' in caps:
   telemetry_source=Path(__file__).with_name('rss_telemetry.py').absolute();telemetry_bytes=regular(telemetry_source).read_bytes()
   need(pins.get(str(telemetry_source))==hashlib.sha256(telemetry_bytes).hexdigest(),'RSS telemetry source pin')
   telemetry_module=types.ModuleType('admitted_rss_telemetry');exec(compile(telemetry_bytes,str(telemetry_source),'exec'),telemetry_module.__dict__)
   telemetry_policy=telemetry_module.policy(caps['rss_telemetry_policy'])
  if resource_gate:
   available=host_checks.available_memory()
   need(available>=resource_gate['min_available_memory'],'locked memory gate');need(shutil.disk_usage(run.parent).free>=resource_gate['min_disk_free'],'locked disk gate')
  need(time.monotonic()<work_stop,'prelaunch work deadline');run.mkdir();(run/'home').mkdir();(run/'tmp').mkdir();log=(run/'frontend.log.gz').open('xb');telemetry=telemetry_module.Writer(run/'rss_samples.jsonl.gz',telemetry_policy) if telemetry_policy is not None else (run/'rss_samples.jsonl').open('x')
  signal.pthread_sigmask(signal.SIG_BLOCK,SIGNALS)
  need(threading.active_count()==1,'preexec requires no existing reader/background threads')
  p=subprocess.Popen(argv,cwd=run,env={**env,'HOME':str(run/'home'),'TMPDIR':str(run/'tmp')},stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=limits)
  owner={'process':p,'identity':None};capture=lossless_log.Capture(p.stdout,log,caps.get('raw_log_bytes',caps['log_bytes']),caps['log_bytes']);boot=api.boot();leader,_=strict._verify_leader(owner,api,None,boot);report['worker_started']=True;report['owner_identity']=dict(owner['identity']);(run/'STARTED.json').write_text(json.dumps({'owner_identity':owner['identity'],'run_started_monotonic':started,'work_stop':work_stop,'cleanup_stop':stop})+'\n')
  # Popen/preexec completed; reader inherits blocked monitor signals.
  reader=threading.Thread(target=log_reader,name='bounded-lossless-reader',daemon=True);reader.start();report['reader_started_after_popen']=True
  (_v2_set_owned_signal_mask(oldmask-SIGNALS) if v2_signal_ownership else signal.pthread_sigmask(signal.SIG_SETMASK,oldmask-SIGNALS))
  if inject_monitor_error:raise OSError('injected monitor failure')
  while True:
   drain_reader_errors();need(not report['errors'],'log reader failure');process_sample();timed_output_sample();drain_reader_errors();need(not report['errors'],'log reader failure');need(time.monotonic()<work_stop,'wall cap')
   exited=os.waitid(os.P_PID,p.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
   if exited is not None and capture.eof:report['native_exit']=exited.si_status if exited.si_code==os.CLD_EXITED else -exited.si_status;break
   time.sleep(.05)
 except BaseException as e:fail(e)
 finally:
  signal.pthread_sigmask(signal.SIG_BLOCK,SIGNALS);signal.setitimer(signal.ITIMER_REAL,0)
  for s in ({signal.SIGALRM} if v2_signal_ownership else SIGNALS):
   if s in signal.sigpending():signal.sigtimedwait({s},0)
  try:
   if owner is not None:
    # Signal only observed stable pidfds. Keep direct leader unreaped to anchor group ownership.
    for pid,fd in pidfds.items():
     if pid!=owner['process'].pid:
      try:signal.pidfd_send_signal(fd,signal.SIGKILL)
      except ProcessLookupError:pass
    proof=strict.cleanup_owned(owner,stop);strict.validate_cleanup_proof(proof,owner=owner,stop=stop);report['cleanup_proof']=proof
    present=[]
    for pid,row in observed.items():
     actual=api.read(pid)
     if actual is not None and actual['start']==row['start']:present.append(actual)
    report['observed_remaining']=present;need(not present,'observed identities remain after group cleanup')
   need(time.monotonic()<stop,'post-cleanup deadline')
   signal.setitimer(signal.ITIMER_REAL,max(.001,stop-time.monotonic()));(_v2_set_owned_signal_mask(oldmask-SIGNALS) if v2_signal_ownership else signal.pthread_sigmask(signal.SIG_SETMASK,oldmask-SIGNALS))
   if reader:
    need(reader_done.wait(max(0.,stop-time.monotonic())),'reader completion deadline');reader.join(max(0.,stop-time.monotonic()));need(not reader.is_alive(),'reader join deadline');drain_reader_errors();need(capture.eof,'log EOF missing after cleanup');report['log_capture']=capture.receipt()
   if telemetry_policy is not None and telemetry:
    telemetry.finish();telemetry.close();telemetry_closed_in_cleanup=True;report['rss_telemetry']=telemetry.receipt()
   if log:timed_output_sample()
   verify_aliases(caps.get('jdk_aliases',[]))
   for path,digest in pins.items():need(sha(regular(path))==digest,'post-input pin mismatch '+path)
  except BaseException as e:
   fail(e)
   if hasattr(e,'evidence'):report['cleanup_failure_evidence']=e.evidence
  finally:
   signal.pthread_sigmask(signal.SIG_BLOCK,SIGNALS);signal.setitimer(signal.ITIMER_REAL,0)
   for s in ({signal.SIGALRM} if v2_signal_ownership else SIGNALS):
    if s in signal.sigpending():signal.sigtimedwait({s},0)
   reader_stop.set()
   if reader:
    reader_done.wait(max(0.,stop-time.monotonic()))
    if reader_done.is_set():reader.join(max(0.,stop-time.monotonic()))
   reader_alive=reader is not None and (not reader_done.is_set() or reader.is_alive());report['reader_join_barrier']={'complete':not reader_alive,'alive':reader_alive,'reader_finally_done':reader_done.is_set()};drain_reader_errors()
   if reader_alive:fail(RuntimeError('reader remains; retaining log/pipe/lock until process exit'))
   for fd in pidfds.values():os.close(fd)
   if capture and not reader_alive:
    if reader is None:
     try:capture.finish()
     except BaseException as e:fail(e)
    report['log_capture']=capture.receipt();capture.pipe.close()
    if not capture.eof:fail(RuntimeError('capture missing EOF; no full log claim'))
   if log and not reader_alive:log.close()
   if telemetry:
    if telemetry_policy is None:telemetry.close()
    else:
     try:telemetry.close()
     except BaseException as e:fail(e)
   if last_process_sample is not None:report['process_sample_terminal_gap_seconds']=time.monotonic()-last_process_sample
   if telemetry_policy is not None and telemetry:
    report['rss_telemetry']=telemetry.receipt()
    try:
     # Original cleanup/EOF deadline has already elapsed or completed. This
     # separate V2-only phase cannot extend group ownership cleanup or hide
     # a missing barrier. Its explicit reserve belongs to caller lifecycle.
     need(telemetry_closed_in_cleanup and not reader_alive and capture is not None and capture.eof and report['cleanup_proof'] is not None and not report.get('observed_remaining'), 'RSS verification requires completed cleanup/EOF barrier')
     verify_stop=time.monotonic()+telemetry_policy['verification_wall_seconds']
     report['rss_telemetry_verification_started_monotonic']=time.monotonic()
     signal.setitimer(signal.ITIMER_REAL,max(.001,verify_stop-time.monotonic()));(_v2_set_owned_signal_mask(oldmask-SIGNALS) if v2_signal_ownership else signal.pthread_sigmask(signal.SIG_SETMASK,oldmask-SIGNALS))
     report['rss_telemetry']=telemetry_module.verify(run/'rss_samples.jsonl.gz',report['rss_telemetry'],telemetry_policy,report.get('process_sample_count',0))
     need(time.monotonic()<=verify_stop,'RSS verification deadline')
    except BaseException as e:fail(e)
    finally:
     signal.pthread_sigmask(signal.SIG_BLOCK,SIGNALS);signal.setitimer(signal.ITIMER_REAL,0)
     for s in {signal.SIGALRM}:
      if s in signal.sigpending():signal.sigtimedwait({s},0)
   report['supervisor_cpu_seconds']=time.process_time()-parent_cpu_started;report['supervisor_cpu_scope']='Parent process including logreader; excludes child/DUT observed CPU'
   report['observed_processes']=list(observed.values());report['elapsed_seconds']=time.monotonic()-started;report['status']='PASS_PROCESS_ONLY' if not report['errors'] and report['native_exit']==0 and report['cleanup_proof'] else 'FAIL_OR_INCOMPLETE';report['limitations']=['Unobserved double-fork/setsid escape between samples is not contained.','Aggregate RSS/CPU/output limits are sampled; per-process RLIMIT is not aggregate cgroup containment.','Exited unobserved processes may contribute CPU not counted; reported observed CPU is a lower bound.','Advisory lock only coordinates runners using this same lock; unrelated old launchers are not excluded.','OS-level uninterruptible processes may prevent cleanup proof; this is FAIL_OR_INCOMPLETE, never a successful absence claim.']
   if run.exists():(run/'RESULT.json').write_text(json.dumps(report,indent=2)+'\n')
   if v2_signal_ownership and not reader_alive:fcntl.flock(lock,fcntl.LOCK_UN);os.close(lock)
   for s,h in oldhandlers.items():signal.signal(s,h)
   if v2_signal_ownership:_v2_set_owned_signal_mask(oldmask)
   else:signal.pthread_sigmask(signal.SIG_SETMASK,oldmask)
   if not v2_signal_ownership and not reader_alive:fcntl.flock(lock,fcntl.LOCK_UN);os.close(lock)
 return report
