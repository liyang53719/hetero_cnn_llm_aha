"""Retained-leader compiler lifecycle using the existing pinned cleanup helper."""
import hashlib,os,signal,subprocess,sys,time,types
from pathlib import Path
HELPER_SHA='30458e67e84c362ff74d69a702624e91bc3c3089600dd36a2469d9ffd6ec4047'
def helper(path):
 b=Path(path).read_bytes()
 if hashlib.sha256(b).hexdigest()!=HELPER_SHA:raise ValueError('strict helper drift')
 m=types.ModuleType('admitted_cleanup');m.__file__=str(path);m._ADMITTED_SOURCE_SHA256=HELPER_SHA
 exec(compile(b,str(path),'exec'),m.__dict__);return m
CHILD='import os,signal,sys; signal.pthread_sigmask(signal.SIG_UNBLOCK,{signal.SIGALRM,signal.SIGTERM,signal.SIGINT}); os.execv(sys.argv[1],sys.argv[1:])'
def execute(argv,*,cwd,log,cleanup_helper,absolute_stop,cleanup_seconds=8):
 start=time.monotonic();stop=absolute_stop;work_stop=stop-cleanup_seconds
 strict=helper(cleanup_helper)
 work_seconds=work_stop-time.monotonic()
 if work_seconds<=0:raise TimeoutError("absolute preflight budget exhausted")
 owner=None;error=None;proof=None;code=None
 signals={signal.SIGTERM,signal.SIGINT,signal.SIGALRM}
 previous={s:signal.getsignal(s) for s in signals}
 if signal.getitimer(signal.ITIMER_REAL)!=(0.0,0.0):raise ValueError('existing alarm')
 def interrupted(signum,frame):raise InterruptedError('compiler interrupted: '+str(signum))
 prior_mask=signal.pthread_sigmask(signal.SIG_BLOCK,signals)
 try:
  for s in signals:signal.signal(s,interrupted)
  signal.setitimer(signal.ITIMER_REAL,work_seconds)
  process=subprocess.Popen([sys.executable,'-I','-B','-c',CHILD]+argv,cwd=cwd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  owner=dict(process=process,identity=None)
  signal.pthread_sigmask(signal.SIG_SETMASK,prior_mask)
  while True:
   if time.monotonic()>=work_stop:raise TimeoutError('original compiler work deadline')
   result=os.waitid(os.P_PID,process.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
   if result is not None:
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
  finally:
   for s,h in previous.items():signal.signal(s,h)
   signal.pthread_sigmask(signal.SIG_SETMASK,prior_mask)
 return dict(exit_code=code,error=None if error is None else type(error).__name__,cleanup_complete=proof is not None,cleanup_proof=proof,cleanup_scope=strict.SCOPE,elapsed_seconds=time.monotonic()-start)
