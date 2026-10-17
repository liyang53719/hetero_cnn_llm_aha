"""File-backed stage runner; retained leader + pinned absence-barrier cleanup.
Aggregate tree limit is sampled, not a filesystem quota. Individual file sizes
are kernel-limited; actual observed peak and overshoot must remain in receipt.
"""
import hashlib,os,signal,subprocess,sys,time,types
from pathlib import Path
HELPER_SHA='30458e67e84c362ff74d69a702624e91bc3c3089600dd36a2469d9ffd6ec4047'
FILE_LIMIT=64*1024*1024
TREE_LIMIT=1024*1024*1024
MAX_ENTRIES=100000
CHILD='import os,signal,sys,resource; resource.setrlimit(resource.RLIMIT_FSIZE,(67108864,67108864)); resource.setrlimit(resource.RLIMIT_AS,(4294967296,4294967296)); os.sched_setaffinity(0,{min(os.sched_getaffinity(0))}); signal.pthread_sigmask(signal.SIG_UNBLOCK,{signal.SIGALRM,signal.SIGTERM,signal.SIGINT}); os.execv(sys.argv[1],sys.argv[1:])'
def helper(path):
 b=Path(path).read_bytes()
 if hashlib.sha256(b).hexdigest()!=HELPER_SHA:raise ValueError('strict helper drift')
 m=types.ModuleType('admitted_cleanup');m.__file__=str(path);m._ADMITTED_SOURCE_SHA256=HELPER_SHA
 exec(compile(b,str(path),'exec'),m.__dict__);return m
def tree_usage(root,deadline=None):
 root=Path(root).absolute();total=0;count=0;links={'internal':0,'external':0,'dangling':0}
 for base,dirs,files in os.walk(root,followlinks=False):
  for name in dirs+files:
   if deadline is not None and time.monotonic()>=deadline:raise TimeoutError('tree scan deadline')
   p=Path(base)/name
   try:st=p.lstat()
   except FileNotFoundError:continue  # concurrently renamed temporary file
   count+=1
   if count>MAX_ENTRIES:raise ValueError('output entry cap')
   if p.is_symlink():
    # Working trees may legitimately point .venv/bin/python at a pinned system
    # interpreter. Never traverse such links or add target bytes to this tree.
    target=os.readlink(p);absolute=Path(os.path.abspath(os.path.join(str(p.parent),target)))
    links['internal' if absolute.is_relative_to(root) else 'external']+=1
    if not os.path.lexists(absolute):links['dangling']+=1
    total+=st.st_size
   elif p.is_file():
    if st.st_size>FILE_LIMIT:raise ValueError('output file cap')
    total+=st.st_size
 return {'bytes':total,'entries':count,'symlinks':links}
def tree_bytes(root,deadline=None):return tree_usage(root,deadline)['bytes']
def _execute(argv,*,cwd,env,out,err,root,absolute_stop,stage_stop,so,se,stdout_limit=FILE_LIMIT,tree_limit=TREE_LIMIT):
 strict=helper(Path(__file__).with_name('strict_cleanup.py'));owner=None;proof=None;error=None;code=None;peak=0
 work_stop=min(stage_stop,absolute_stop-10);signals={signal.SIGTERM,signal.SIGINT,signal.SIGALRM};old={s:signal.getsignal(s) for s in signals}
 def interrupted(sig,frame):raise InterruptedError('stage interrupted '+str(sig))
 # Acquire files before mutating signal state: xb failure must leave caller intact.
 mask=signal.pthread_sigmask(signal.SIG_BLOCK,signals)
 try:
  for s in signals:signal.signal(s,interrupted)
  if time.monotonic()>=work_stop:raise TimeoutError('original work deadline')
  signal.setitimer(signal.ITIMER_REAL,work_stop-time.monotonic())
  p=subprocess.Popen([sys.executable,'-I','-B','-c',CHILD]+argv,cwd=cwd,env=env,stdout=so,stderr=se,start_new_session=True)
  owner={'process':p,'identity':None};signal.pthread_sigmask(signal.SIG_SETMASK,mask)
  while True:
   size=tree_bytes(root,work_stop);peak=max(peak,size)
   if size>tree_limit:raise ValueError('aggregate tree sampled limit exceeded')
   if os.fstat(so.fileno()).st_size>stdout_limit or os.fstat(se.fileno()).st_size>2*1024*1024:raise ValueError('stage log cap')
   if time.monotonic()>=work_stop:raise TimeoutError('original work deadline')
   r=os.waitid(os.P_PID,p.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
   if r is not None:
    code=r.si_status if r.si_code==os.CLD_EXITED else -r.si_status;break
   time.sleep(.05)
 except BaseException as e:error=repr(e)
 finally:
  signal.pthread_sigmask(signal.SIG_BLOCK,signals);signal.setitimer(signal.ITIMER_REAL,0)
  for s in signals:
   if s in signal.sigpending():signal.sigtimedwait({s},0)
  try:
   if owner is not None:
    proof=strict.cleanup_owned(owner,absolute_stop)
    strict.validate_cleanup_proof(proof,owner=owner,stop=absolute_stop)
   # The original absolute deadline also protects all post-absence scans.
   if time.monotonic()>=absolute_stop:raise TimeoutError('post-cleanup deadline')
   signal.setitimer(signal.ITIMER_REAL,absolute_stop-time.monotonic())
   signal.pthread_sigmask(signal.SIG_SETMASK,mask)
   try:
    usage=tree_usage(root,absolute_stop);size=usage['bytes'];peak=max(peak,size)
    if size>tree_limit or os.fstat(so.fileno()).st_size>stdout_limit or os.fstat(se.fileno()).st_size>2*1024*1024:error='post-cleanup output limit exceeded'
   except BaseException as post_error:error=repr(post_error)
  finally:
   signal.pthread_sigmask(signal.SIG_BLOCK,signals);signal.setitimer(signal.ITIMER_REAL,0)
   for s in signals:
    if s in signal.sigpending():signal.sigtimedwait({s},0)
   for s,h in old.items():signal.signal(s,h)
   signal.setitimer(signal.ITIMER_REAL,max(.001,absolute_stop-time.monotonic()))
   signal.pthread_sigmask(signal.SIG_SETMASK,mask)
 return {'argv':argv,'cwd':str(cwd),'exit':code,'error':error,'cleanup_complete':proof is not None,'cleanup_proof':proof,'cleanup_scope':strict.SCOPE,'working_tree_symlinks':usage['symlinks'] if 'usage' in locals() else None,'peak_sampled_tree_bytes':peak,'tree_limit_bytes':tree_limit,'tree_limit_kind':'sampled_soft_limit_not_quota','file_hard_limit_bytes':FILE_LIMIT,'stdout_bytes':Path(out).stat().st_size,'stderr_bytes':Path(err).stat().st_size}

def execute(argv,*,cwd,env,out,err,root,absolute_stop,stage_stop,stdout_limit=FILE_LIMIT,tree_limit=TREE_LIMIT):
 # Original-stop protection includes helper load and both xb opens. Only the
 # inner spawn/ownership and cleanup proof sections block signals.
 if signal.getitimer(signal.ITIMER_REAL)!=(0.0,0.0):raise ValueError('existing alarm')
 signals={signal.SIGINT,signal.SIGTERM,signal.SIGALRM}
 old={s:signal.getsignal(s) for s in signals}
 mask=signal.pthread_sigmask(signal.SIG_BLOCK,set())
 def deadline(sig,frame):raise TimeoutError('original stage ownership deadline')
 try:
  signal.signal(signal.SIGALRM,deadline)
  signal.setitimer(signal.ITIMER_REAL,max(.001,absolute_stop-time.monotonic()))
  signal.pthread_sigmask(signal.SIG_UNBLOCK,{signal.SIGALRM})
  so=None;se=None
  try:
   so=open(out,'xb');se=open(err,'xb')
   return _execute(argv,cwd=cwd,env=env,out=out,err=err,root=root,absolute_stop=absolute_stop,stage_stop=stage_stop,so=so,se=se,stdout_limit=stdout_limit,tree_limit=tree_limit)
  finally:
   # Even cleanup proof exceptions must re-arm before file-resource close.
   signal.signal(signal.SIGALRM,deadline)
   signal.setitimer(signal.ITIMER_REAL,max(.001,absolute_stop-time.monotonic()))
   signal.pthread_sigmask(signal.SIG_UNBLOCK,{signal.SIGALRM})
   try:
    if se is not None:se.close()
   finally:
    if so is not None:so.close()
 finally:
  signal.pthread_sigmask(signal.SIG_BLOCK,signals)
  signal.setitimer(signal.ITIMER_REAL,0)
  for sig in signals:
   if sig in signal.sigpending():signal.sigtimedwait({sig},0)
  for sig,handler in old.items():signal.signal(sig,handler)
  signal.pthread_sigmask(signal.SIG_SETMASK,mask)
