"""Observed descendants + original-group barrier. Not escaped-tree containment."""
import lossless_log
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
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def regular(p):
 p=Path(p).absolute()
 for q in (p,*p.parents):need(not q.is_symlink(),'symlink path '+str(q))
 need(p.is_file(),'missing file '+str(p));return p

def execute(argv,run,lock_path,caps,env,pins,inject_monitor_error=False,resource_gate=None):
 strict=helper();run=Path(run).absolute();lock_path=Path(lock_path).absolute()
 need(not run.exists() and not run.is_symlink(),'one-shot output already exists')
 for q in run.parents:need(not q.is_symlink(),'symlink output parent')
 need(lock_path.parent.is_dir() and not lock_path.is_symlink(),'lock path')
 need(hasattr(os,'pidfd_open') and hasattr(signal,'pidfd_send_signal'),'pidfd support required')
 lock=os.open(lock_path,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BaseException:os.close(lock);raise
 started=time.monotonic();work_stop=started+caps['wall_seconds'];stop=work_stop+caps['cleanup_seconds'];owner=None;log=None;telemetry=None;capture=None;leader=None;observed={};pidfds={};report={'status':'IN_PROGRESS','scope':'ORIGINAL_PROCESS_GROUP_AND_OBSERVED_DESCENDANTS_ONLY','argv':argv,'caps':caps,'worker_started':False,'errors':[],'observed_peak_rss':0,'observed_cpu_seconds':0,'peak_tree_bytes':0,'peak_file_bytes':0,'native_exit':None,'cleanup_proof':None};oldmask=signal.pthread_sigmask(signal.SIG_BLOCK,SIGNALS);oldhandlers={s:signal.getsignal(s) for s in SIGNALS};api=strict._Linux()
 def fail(e):report['errors'].append(type(e).__name__+': '+str(e))
 def interrupted(sig,frame):raise InterruptedError('signal '+str(sig))
 def limits():
  resource.setrlimit(resource.RLIMIT_CORE,(0,0))
  resource.setrlimit(resource.RLIMIT_FSIZE,(caps['file_bytes'],)*2);resource.setrlimit(resource.RLIMIT_AS,(caps['per_process_as_bytes'],)*2);resource.setrlimit(resource.RLIMIT_CPU,(caps['per_process_cpu_seconds'],)*2)
  os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
  for s in SIGNALS:signal.signal(s,signal.SIG_DFL)
  signal.pthread_sigmask(signal.SIG_UNBLOCK,SIGNALS)
 def output_sample():
  total=largest=count=stage_total=0
  roots=[run]+[Path(x).absolute() for x in caps.get('extra_watch_roots',[])]
  unique=[]
  for root in sorted(set(roots),key=lambda p:len(p.parts)):
   if not any(root.is_relative_to(q) for q in unique):unique.append(root)
  seen=set()
  for root in unique:
   for base,dirs,files in os.walk(root,followlinks=False):
    for name in dirs+files:
     p=Path(base)/name
     try:s=p.lstat()
     except FileNotFoundError:continue
     count+=1;need(count<=caps['max_entries'],'entry cap')
     if stat.S_ISLNK(s.st_mode):
      need(not p.is_relative_to(run),'output link forbidden');continue
     need(stat.S_ISDIR(s.st_mode) or stat.S_ISREG(s.st_mode),'nonregular output')
     if stat.S_ISREG(s.st_mode):
      key=(s.st_dev,s.st_ino)
      if key not in seen:
       seen.add(key);total+=s.st_size;largest=max(largest,s.st_size)
       if p.is_relative_to(run):stage_total+=s.st_size
  for root in unique:
   if root.exists():need(shutil.disk_usage(root).free>=caps.get('min_free_disk_bytes',0),'sampled disk reserve')
  report['peak_tree_bytes']=max(report['peak_tree_bytes'],total);report['peak_file_bytes']=max(report['peak_file_bytes'],largest)
  need(total<=caps.get('watch_tree_bytes',caps['tree_bytes']),'sampled aggregate writable-root cap');need(stage_total<=caps['tree_bytes'],'sampled stage output tree cap');need(largest<=caps['file_bytes'],'file cap');need(os.fstat(log.fileno()).st_size<=caps['log_bytes'],'sampled log cap')
 def process_sample():
  strict._verify_leader(owner,api,leader,boot);snapshot={};rawfields={};names=os.listdir('/proc');need(len(names)<=100000,'proc enumeration cap')
  for name in names:
   if not name.isascii() or not name.isdecimal():continue
   try:raw=(Path('/proc')/name/'stat').read_bytes()
   except FileNotFoundError:continue
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
  available=int(next(s.split()[1] for s in Path('/proc/meminfo').read_text().splitlines() if s.startswith('MemAvailable:')))*1024;reserve_warning=available<1024**3;report['minimum_MemAvailable_bytes']=min(report.get('minimum_MemAvailable_bytes',available),available);report['memory_reserve_warning_samples']=report.get('memory_reserve_warning_samples',0)+int(reserve_warning)
  telemetry.write(json.dumps({'elapsed':time.monotonic()-started,'aggregate_rss_bytes':rss,'processes':sample_rows,'MemAvailable_bytes':available,'reserve_below_1GiB_warning':reserve_warning},separators=(',',':'))+'\n');telemetry.flush();need(telemetry.tell()<=64*1024*1024,'RSS telemetry 64MiB cap')
  need(rss<=caps['rss_bytes'],'sampled observed aggregate RSS cap');need(cpu<=caps['cpu_seconds'],'sampled observed aggregate CPU cap')
 try:
  need(signal.getitimer(signal.ITIMER_REAL)==(0.,0.),'preexisting alarm')
  for s in SIGNALS:signal.signal(s,interrupted)
  signal.setitimer(signal.ITIMER_REAL,max(.001,work_stop-time.monotonic()));signal.pthread_sigmask(signal.SIG_SETMASK,oldmask-SIGNALS)
  for path,digest in pins.items():need(sha(regular(path))==digest,'input pin mismatch '+path)
  if resource_gate:
   available=int(next(s.split()[1] for s in Path('/proc/meminfo').read_text().splitlines() if s.startswith('MemAvailable:')))*1024
   need(available>=resource_gate['min_available_memory'],'locked memory gate');need(shutil.disk_usage(run.parent).free>=resource_gate['min_disk_free'],'locked disk gate')
  need(time.monotonic()<work_stop,'prelaunch work deadline');run.mkdir();(run/'home').mkdir();(run/'tmp').mkdir();log=(run/'frontend.log.gz').open('xb');telemetry=(run/'rss_samples.jsonl').open('x')
  signal.pthread_sigmask(signal.SIG_BLOCK,SIGNALS)
  p=subprocess.Popen(argv,cwd=run,env={**env,'HOME':str(run/'home'),'TMPDIR':str(run/'tmp')},stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=limits)
  owner={'process':p,'identity':None};capture=lossless_log.Capture(p.stdout,log,caps.get('raw_log_bytes',caps['log_bytes']),caps['log_bytes']);boot=api.boot();leader,_=strict._verify_leader(owner,api,None,boot);report['worker_started']=True;report['owner_identity']=dict(owner['identity']);(run/'STARTED.json').write_text(json.dumps({'owner_identity':owner['identity'],'run_started_monotonic':started,'work_stop':work_stop,'cleanup_stop':stop})+'\n');signal.pthread_sigmask(signal.SIG_SETMASK,oldmask-SIGNALS)
  if inject_monitor_error:raise OSError('injected monitor failure')
  while True:
   capture.drain();process_sample();output_sample();need(time.monotonic()<work_stop,'wall cap')
   exited=os.waitid(os.P_PID,p.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
   if exited is not None and capture.eof:report['native_exit']=exited.si_status if exited.si_code==os.CLD_EXITED else -exited.si_status;break
   time.sleep(.05)
 except BaseException as e:fail(e)
 finally:
  signal.pthread_sigmask(signal.SIG_BLOCK,SIGNALS);signal.setitimer(signal.ITIMER_REAL,0)
  for s in SIGNALS:
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
   signal.setitimer(signal.ITIMER_REAL,max(.001,stop-time.monotonic()));signal.pthread_sigmask(signal.SIG_SETMASK,oldmask-SIGNALS)
   if capture:
    if not capture.capped:
     for _ in range(64):
      if capture.eof or not capture.drain():break
    capture.finish();report['log_capture']=capture.receipt()
   if log:output_sample()
   for path,digest in pins.items():need(sha(regular(path))==digest,'post-input pin mismatch '+path)
  except BaseException as e:
   fail(e)
   if hasattr(e,'evidence'):report['cleanup_failure_evidence']=e.evidence
  finally:
   signal.pthread_sigmask(signal.SIG_BLOCK,SIGNALS);signal.setitimer(signal.ITIMER_REAL,0)
   for s in SIGNALS:
    if s in signal.sigpending():signal.sigtimedwait({s},0)
   for fd in pidfds.values():os.close(fd)
   if capture:
    try:capture.finish();report['log_capture']=capture.receipt()
    except BaseException as e:fail(e)
    capture.pipe.close()
   if log:log.close()
   if telemetry:telemetry.close()
   report['observed_processes']=list(observed.values());report['elapsed_seconds']=time.monotonic()-started;report['status']='PASS_PROCESS_ONLY' if not report['errors'] and report['native_exit']==0 and report['cleanup_proof'] else 'FAIL_OR_INCOMPLETE';report['limitations']=['Unobserved double-fork/setsid escape between samples is not contained.','Aggregate RSS/CPU/output limits are sampled; per-process RLIMIT is not aggregate cgroup containment.','Exited unobserved processes may contribute CPU not counted; reported observed CPU is a lower bound.','Advisory lock only coordinates runners using this same lock; unrelated old launchers are not excluded.','OS-level uninterruptible processes may prevent cleanup proof; this is FAIL_OR_INCOMPLETE, never a successful absence claim.']
   if run.exists():(run/'RESULT.json').write_text(json.dumps(report,indent=2)+'\n')
   for s,h in oldhandlers.items():signal.signal(s,h)
   signal.pthread_sigmask(signal.SIG_SETMASK,oldmask);fcntl.flock(lock,fcntl.LOCK_UN);os.close(lock)
 return report
