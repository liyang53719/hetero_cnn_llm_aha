"""Bounded one-process compiler supervisor; source-only tests may use Python children."""
import hashlib,os,signal,stat,subprocess,sys,time,types
from pathlib import Path
HELPER_SHA='30458e67e84c362ff74d69a702624e91bc3c3089600dd36a2469d9ffd6ec4047'
LOG_LIMIT_BYTES=2*1024*1024
TREE_SOFTCAP_BYTES=64*1024*1024
FILE_HARD_LIMIT_BYTES=48*1024*1024
CHILD='import os,signal,sys,resource; resource.setrlimit(resource.RLIMIT_FSIZE,(50331648,50331648)); os.sched_setaffinity(0,{min(os.sched_getaffinity(0))}); signal.pthread_sigmask(signal.SIG_UNBLOCK,{signal.SIGALRM,signal.SIGTERM,signal.SIGINT}); os.execv(sys.argv[1],sys.argv[1:])'
def helper(path):
    b=Path(path).read_bytes()
    if hashlib.sha256(b).hexdigest()!=HELPER_SHA:raise ValueError('strict cleanup helper drift')
    m=types.ModuleType('admitted_cleanup');m.__file__=str(path);m._ADMITTED_SOURCE_SHA256=HELPER_SHA
    exec(compile(b,str(path),'exec'),m.__dict__);return m

def tree_size(root):
    total=0
    for p in Path(root).rglob('*'):
        info=p.lstat()
        if stat.S_ISLNK(info.st_mode):raise ValueError('generated tree symlink')
        if stat.S_ISREG(info.st_mode):total+=info.st_size
        elif not stat.S_ISDIR(info.st_mode):raise ValueError('generated nonregular output')
    return total

def execute(argv,*,cwd,classes,log,cleanup_helper,absolute_stop,work_stop):
    start=time.monotonic();strict=helper(cleanup_helper)
    if work_stop>absolute_stop-8:raise ValueError('reserve >=8 seconds for cleanup')
    if time.monotonic()>=work_stop:raise TimeoutError('preflight exhausted work budget')
    owner=None;error=None;proof=None;code=None;log_bytes=0;peak_sampled=0
    signals={signal.SIGTERM,signal.SIGINT,signal.SIGALRM};previous={s:signal.getsignal(s) for s in signals}
    if signal.getitimer(signal.ITIMER_REAL)!=(0.0,0.0):raise ValueError('preexisting alarm')
    def interrupted(signum,frame):raise InterruptedError('owned compiler interrupted '+str(signum))
    prior_mask=signal.pthread_sigmask(signal.SIG_BLOCK,signals)
    try:
        for s in signals:signal.signal(s,interrupted)
        signal.setitimer(signal.ITIMER_REAL,max(.001,work_stop-time.monotonic()))
        process=subprocess.Popen([sys.executable,'-I','-B','-c',CHILD]+argv,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True,
            env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8','HOME':str(cwd)})
        owner=dict(process=process,identity=None);os.set_blocking(process.stdout.fileno(),False)
        def collect():
            nonlocal log_bytes
            while True:
                if time.monotonic()>=work_stop:raise TimeoutError('collection deadline')
                try:chunk=os.read(process.stdout.fileno(),65536)
                except BlockingIOError:break
                if not chunk:break
                remaining=LOG_LIMIT_BYTES-log_bytes
                if len(chunk)>remaining:
                    if remaining:log.write(chunk[:remaining]);log_bytes+=remaining
                    log.flush();raise ValueError('hard parent log cap exceeded')
                log.write(chunk);log_bytes+=len(chunk)
            log.flush()
        def sample():
            nonlocal peak_sampled
            size=tree_size(classes);peak_sampled=max(peak_sampled,size)
            if size>TREE_SOFTCAP_BYTES:raise ValueError('sampled class tree softcap exceeded')
        signal.pthread_sigmask(signal.SIG_SETMASK,prior_mask)
        while True:
            collect();sample()
            if time.monotonic()>=work_stop:raise TimeoutError('compiler work deadline')
            result=os.waitid(os.P_PID,process.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
            if result is not None:
                collect();sample();code=result.si_status if result.si_code==os.CLD_EXITED else -result.si_status;break
            time.sleep(.02)
    except BaseException as caught:error=caught
    finally:
        signal.pthread_sigmask(signal.SIG_BLOCK,signals);signal.setitimer(signal.ITIMER_REAL,0)
        for s in signals:
            if s in signal.sigpending():signal.sigtimedwait({s},0)
        try:
            if owner is not None:
                proof=strict.cleanup_owned(owner,absolute_stop)
                strict.validate_cleanup_proof(proof,owner=owner,stop=absolute_stop)
            # Strict helper completed; bound remaining filesystem checks by
            # the same cleanup deadline before restoring caller handlers.
            if time.monotonic()>=absolute_stop:raise TimeoutError('post-cleanup check deadline')
            signal.setitimer(signal.ITIMER_REAL,max(.001,absolute_stop-time.monotonic()))
            signal.pthread_sigmask(signal.SIG_SETMASK,prior_mask)
            log.flush()
            if os.fstat(log.fileno()).st_size!=log_bytes or log_bytes>LOG_LIMIT_BYTES:error=ValueError('post-cleanup log mismatch')
            try:
                size=tree_size(classes);peak_sampled=max(peak_sampled,size)
                if size>TREE_SOFTCAP_BYTES:error=ValueError('post-cleanup class tree softcap exceeded')
            except (ValueError,OSError) as caught:
                error=caught
        finally:
            signal.pthread_sigmask(signal.SIG_BLOCK,signals)
            signal.setitimer(signal.ITIMER_REAL,0)
            for sig in signals:
                if sig in signal.sigpending():signal.sigtimedwait({sig},0)
            if owner is not None and owner['process'].stdout is not None:owner['process'].stdout.close()
            for s,h in previous.items():signal.signal(s,h)
            signal.pthread_sigmask(signal.SIG_SETMASK,prior_mask)
    return dict(compiler_started=owner is not None,exit_code=code,error=None if error is None else type(error).__name__+': '+str(error),cleanup_complete=proof is not None,
        cleanup_proof=proof,cleanup_scope=strict.SCOPE,log_bytes=log_bytes,log_hard_cap_bytes=LOG_LIMIT_BYTES,
        classes_tree_sampled_softcap_bytes=TREE_SOFTCAP_BYTES,peak_sampled_classes_bytes=peak_sampled,
        generated_file_hard_limit_bytes=FILE_HARD_LIMIT_BYTES,whole_process_memory_hard_limit=None,
        elapsed_seconds=time.monotonic()-start)
