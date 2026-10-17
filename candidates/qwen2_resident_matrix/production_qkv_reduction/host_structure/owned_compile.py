"""Retained-leader compiler lifecycle using the existing pinned cleanup helper."""
import hashlib,os,signal,subprocess,sys,time,types,json,stat
from pathlib import Path
HELPER_SHA='30458e67e84c362ff74d69a702624e91bc3c3089600dd36a2469d9ffd6ec4047'
def helper(path):
 b=Path(path).read_bytes()
 if hashlib.sha256(b).hexdigest()!=HELPER_SHA:raise ValueError('strict helper drift')
 m=types.ModuleType('admitted_cleanup');m.__file__=str(path);m._ADMITTED_SOURCE_SHA256=HELPER_SHA
 exec(compile(b,str(path),'exec'),m.__dict__);return m
LOG_LIMIT_BYTES=2*1024*1024
CHILD='import os,signal,sys,resource; resource.setrlimit(resource.RLIMIT_FSIZE,(50331648,50331648)); os.sched_setaffinity(0,{min(os.sched_getaffinity(0))}); signal.pthread_sigmask(signal.SIG_UNBLOCK,{signal.SIGALRM,signal.SIGTERM,signal.SIGINT}); os.execv(sys.argv[1],sys.argv[1:])'
def execute(argv,*,cwd,log,cleanup_helper,absolute_stop,stage_stop,progress_log=None,startup_seconds=None,cleanup_seconds=10):
 start=time.monotonic();stop=absolute_stop;work_stop=min(stage_stop,stop-cleanup_seconds)
 strict=helper(cleanup_helper)
 work_seconds=work_stop-time.monotonic()
 if work_seconds<=0:raise TimeoutError("absolute preflight budget exhausted")
 owner=None;error=None;proof=None;code=None;log_bytes=0
 signals={signal.SIGTERM,signal.SIGINT,signal.SIGALRM}
 previous={s:signal.getsignal(s) for s in signals}
 if signal.getitimer(signal.ITIMER_REAL)!=(0.0,0.0):raise ValueError('existing alarm')
 def interrupted(signum,frame):raise InterruptedError('compiler interrupted: '+str(signum))
 prior_mask=signal.pthread_sigmask(signal.SIG_BLOCK,signals)
 try:
  for s in signals:signal.signal(s,interrupted)
  startup_stop=None if startup_seconds is None else start+startup_seconds
  initial_stop=work_stop if startup_stop is None else min(work_stop,startup_stop)
  if time.monotonic()>=initial_stop:raise TimeoutError('initial stage deadline')
  signal.setitimer(signal.ITIMER_REAL,initial_stop-time.monotonic())
  process=subprocess.Popen([sys.executable,'-I','-B','-c',CHILD]+argv,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
  owner=dict(process=process,identity=None)
  os.set_blocking(process.stdout.fileno(),False)
  def collect():
   nonlocal log_bytes
   while True:
    if time.monotonic()>=work_stop:raise TimeoutError('output collection work deadline')
    try:chunk=os.read(process.stdout.fileno(),65536)
    except BlockingIOError:break
    if not chunk:break
    remaining=LOG_LIMIT_BYTES-log_bytes
    if len(chunk)>remaining:
     if remaining:log.write(chunk[:remaining]);log_bytes+=remaining
     log.flush();raise ValueError('parent output cap exceeded')
    log.write(chunk);log_bytes+=len(chunk)
   log.flush()
  signal.pthread_sigmask(signal.SIG_SETMASK,prior_mask)
  callback_seen=False
  while True:
   now=time.monotonic()
   if startup_stop is not None and not callback_seen and now>=startup_stop:
    raise TimeoutError('compiled backend callback startup deadline')
   collect()
   total_bytes=sum(p.stat().st_size for p in Path(cwd).rglob('*') if p.is_file())
   if total_bytes>64*1024*1024:raise ValueError('aggregate output sampled cap exceeded')
   if startup_stop is not None and not callback_seen:
    with Path(progress_log).open('rb') as observed:
     lines=observed.read(65536).decode('utf-8',errors='replace').splitlines()
    observed_at=time.monotonic()
    if observed_at>=startup_stop:raise TimeoutError('callback marker observed too late')
    callback_seen='QKV_PROTOCOL_SIM_READY' in lines
    if callback_seen:
     work_stop=min(work_stop,observed_at+30)
     signal.setitimer(signal.ITIMER_REAL,max(.001,work_stop-time.monotonic()))
   if time.monotonic()>=work_stop:raise TimeoutError('original compiler work deadline')
   result=os.waitid(os.P_PID,process.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
   if result is not None:
    collect()
    code=result.si_status if result.si_code==os.CLD_EXITED else -result.si_status
    break
   time.sleep(.02)
 except BaseException as caught:error=caught
 finally:
  # The original direct child is still retained; never poll/wait/reap it first.
  signal.pthread_sigmask(signal.SIG_BLOCK,signals)
  signal.setitimer(signal.ITIMER_REAL,0)
  for s in signals:
   if s in signal.sigpending():signal.sigtimedwait({s},0)
  try:
   if owner is not None:
    proof=strict.cleanup_owned(owner,stop)
    strict.validate_cleanup_proof(proof,owner=owner,stop=stop)
   log.flush()
   if os.fstat(log.fileno()).st_size!=log_bytes or log_bytes>LOG_LIMIT_BYTES:
    error=ValueError('post-cleanup parent log size mismatch')
  finally:
   if owner is not None and owner["process"].stdout is not None:owner["process"].stdout.close()
   for s,h in previous.items():signal.signal(s,h)
   signal.pthread_sigmask(signal.SIG_SETMASK,prior_mask)
 return dict(log_bytes=log_bytes,log_limit_bytes=LOG_LIMIT_BYTES,generated_file_limit_bytes=50331648,exit_code=code,error=None if error is None else type(error).__name__,cleanup_complete=proof is not None,cleanup_proof=proof,cleanup_scope=strict.SCOPE,elapsed_seconds=time.monotonic()-start)
