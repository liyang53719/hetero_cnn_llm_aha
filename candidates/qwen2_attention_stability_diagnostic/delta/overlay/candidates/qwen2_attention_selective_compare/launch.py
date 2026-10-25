"""One-use serial three-process M2 stability supervisor, no retries or native CI."""
import argparse,hashlib,json,math,os,resource,signal,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from admission import validate_review
from stability import LIMITS, ORDERS, summarize_experiment

def limits(cpu_seconds,previous_mask=()):
    signal.setitimer(signal.ITIMER_PROF,0);signal.setitimer(signal.ITIMER_REAL,0)
    signal.signal(signal.SIGPROF,signal.SIG_DFL);signal.signal(signal.SIGALRM,signal.SIG_DFL)
    signal.pthread_sigmask(signal.SIG_SETMASK,previous_mask)
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_CPU,(cpu_seconds,cpu_seconds));resource.setrlimit(resource.RLIMIT_AS,(1<<30,1<<30))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_FSIZE,(4<<20,4<<20))
def identity(pid):
    words=Path('/proc/%d/stat'%pid).read_text().split(') ',1)[1].split()
    return dict(pid=pid,start_ticks=int(words[19]),pgid=int(words[2]),session=int(words[3]),boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
def claim(config,m,sha,output):
    ledger=config.parent/'attempts';ledger.mkdir(exist_ok=True)
    if m!=2:raise ValueError('M2 only; no M128 execution')
    attempt=ledger/'M2_stability.json'
    with attempt.open('x') as f:json.dump(dict(config_sha256=sha,m=m,output=str(output.resolve()),orders=[list(x) for x in ORDERS],status='CLAIMED_ALL_THREE_NO_RETRY'),f)
    return attempt

ACTIVE=None

def kill_active_if_owned():
    if ACTIVE is None:return
    proc,owned=ACTIVE
    if proc.returncode is None and identity(proc.pid)==owned:
        os.killpg(proc.pid,signal.SIGKILL)

def cleanup_deadline_signal(signum,frame):
    # A budget interrupt already killed the verified active group first.
    try:kill_active_if_owned()
    finally:os._exit(124)

def parent_work_budget_signal(signum,frame):
    signal.setitimer(signal.ITIMER_PROF,0);signal.setitimer(signal.ITIMER_REAL,0)
    try:kill_active_if_owned()
    finally:
        # Ownership/read uncertainty must never leave the fallback guards off.
        # Only on abort: no later fork needs a higher inherited hard limit.
        resource.setrlimit(resource.RLIMIT_CPU,(6,6))
        signal.signal(signal.SIGALRM,cleanup_deadline_signal)
        signal.setitimer(signal.ITIMER_REAL,LIMITS['cleanup_wall_reserve'])
    raise TimeoutError('parent work guard; verified active group stopped before cleanup')

def install_parent_guards(budget):
    signal.signal(signal.SIGPROF,parent_work_budget_signal);signal.signal(signal.SIGALRM,parent_work_budget_signal)
    signal.setitimer(signal.ITIMER_PROF,max(.001,4-time.process_time()))
    signal.setitimer(signal.ITIMER_REAL,max(.001,87-(time.monotonic()-budget.started)))

def live_usage(owned):
    """Only the recorded worker and its currently visible same-group descendants."""
    if identity(owned['pid'])!=owned:raise ValueError('live child identity drift')
    pending=[owned['pid']];seen=set();cpu=0;rss=0;ticks=os.sysconf('SC_CLK_TCK');page=os.sysconf('SC_PAGE_SIZE')
    while pending:
        pid=pending.pop()
        if pid in seen:continue
        seen.add(pid)
        try:
            words=Path('/proc/%d/stat'%pid).read_text().split(') ',1)[1].split()
            if int(words[2])!=owned['pgid'] or int(words[3])!=owned['session']:raise ValueError('worker descendant escaped recorded group')
            # User/system plus already waited descendants; live descendants are
            # visited separately. A racing wait may conservatively overcount.
            cpu+=sum(int(words[i]) for i in (11,12,13,14))/ticks;rss+=int(words[21])*page
            for task in Path('/proc/%d/task'%pid).iterdir():
                try:pending.extend(int(p) for p in (task/'children').read_text().split())
                except FileNotFoundError:pass
        except FileNotFoundError:continue
    return cpu,rss

def same_group_descendants(owned):
    # WNOWAIT retains the leader's birth identity even after normal exit. The
    # group cannot be recycled while that verified PID is still an unreaped zombie.
    if identity(owned['pid'])!=owned:raise ValueError('cleanup leader identity drift')
    found=[]
    for path in Path('/proc').iterdir():
        if not path.name.isdigit() or int(path.name)==owned['pid']:continue
        try:
            words=(path/'stat').read_text().split(') ',1)[1].split()
            if int(words[2])==owned['pgid']:
                if int(words[3])!=owned['session']:raise ValueError('foreign session in owned group')
                found.append(dict(pid=int(path.name),start_ticks=int(words[19]),pgid=int(words[2]),session=int(words[3])))
        except FileNotFoundError:pass
    return found

class Budget:
    def __init__(self):self.started=time.monotonic()
    def snapshot(self,owned=None):
        child=resource.getrusage(resource.RUSAGE_CHILDREN);live_cpu=live_rss=0
        if owned is not None:live_cpu,live_rss=live_usage(owned)
        words=Path('/proc/self/stat').read_text().split(') ',1)[1].split()
        return dict(cpu_seconds=time.process_time()+child.ru_utime+child.ru_stime+live_cpu,wall_seconds=time.monotonic()-self.started,rss_bytes=int(words[21])*os.sysconf('SC_PAGE_SIZE')+live_rss)
    def require_work_budget(self,owned=None):
        value=self.snapshot(owned)
        if value['cpu_seconds']>=LIMITS['cpu_seconds']-LIMITS['cleanup_cpu_reserve'] or value['wall_seconds']>=LIMITS['wall_seconds']-LIMITS['cleanup_wall_reserve'] or value['rss_bytes']>=LIMITS['address_space_bytes']:
            raise TimeoutError('aggregate work budget exhausted; cleanup reserve retained')
        return value
    def allowance(self):
        used=self.require_work_budget()
        cpu=min(LIMITS['child_cpu_seconds'],math.floor(LIMITS['cpu_seconds']-LIMITS['cleanup_cpu_reserve']-used['cpu_seconds']))
        wall=min(LIMITS['child_wall_seconds'],LIMITS['wall_seconds']-LIMITS['cleanup_wall_reserve']-used['wall_seconds'])
        if cpu<1 or wall<=0:raise TimeoutError('insufficient budget; next worker not launched')
        return cpu,wall

def supervise(argv,env,out,budget):
    """Reuse recorded birth identity / group cleanup; never delete failed output."""
    global ACTIVE
    cpu_limit,wall_limit=budget.allowance();out.mkdir()
    record=dict(status='STARTED',argv=argv,cpu_seconds_limit=cpu_limit,wall_seconds_limit=wall_limit,aggregate_before=budget.snapshot());receipt=out/'PARENT.json'
    def save():receipt.write_text(json.dumps(record,indent=2)+'\n')
    started=time.monotonic();proc=None;owned=None;save()
    try:
        with (out/'worker.log').open('xb') as log:
            # Delay only budget signals across the small fork/ownership window.
            previous_mask=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGPROF,signal.SIGALRM})
            try:
                proc=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT,env=env,start_new_session=True,preexec_fn=lambda:limits(cpu_limit,previous_mask))
                owned=identity(proc.pid);ACTIVE=(proc,owned);record['child_identity']=owned
            finally:signal.pthread_sigmask(signal.SIG_SETMASK,previous_mask)
            save()
            deadline=started+wall_limit
            while True:
                remaining=deadline-time.monotonic()
                if remaining<=0:raise TimeoutError('per-child wall cap')
                # Do not reap yet: preserving the leader birth closes the
                # leader-exit/descendant-linger cleanup race without PID guesses.
                ended=os.waitid(os.P_PID,proc.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
                if ended is not None:
                    descendants=same_group_descendants(owned)
                    if descendants:record['unexpected_descendants_after_leader_exit']=descendants
                    break
                budget.require_work_budget(owned)
                time.sleep(min(.2,remaining))
    except BaseException as error:record['exception']=type(error).__name__+': '+str(error)
    finally:
        if proc is not None and proc.returncode is None:
            try:
                if identity(proc.pid)==owned:
                    os.killpg(proc.pid,signal.SIGKILL);record['cleanup_signal']='SIGKILL_OWN_VERIFIED_GROUP'
                    remaining=LIMITS['wall_seconds']-budget.snapshot()['wall_seconds']
                    if remaining<=0:raise TimeoutError('no cleanup time remains')
                    proc.wait(timeout=min(LIMITS['cleanup_wall_reserve'],remaining))
                else:record['cleanup_uncertain']='child identity changed; not signalled'
            except (OSError,subprocess.TimeoutExpired,TimeoutError) as error:record['cleanup_uncertain']=str(error)
        group_remaining=False
        if proc is not None:
            record['returncode']=proc.returncode
            cleanup_deadline=time.monotonic()+min(LIMITS['cleanup_wall_reserve'],max(0,LIMITS['wall_seconds']-budget.snapshot()['wall_seconds']))
            while True:
                try:os.killpg(proc.pid,0);group_remaining=True
                except ProcessLookupError:group_remaining=False;break
                if time.monotonic()>=cleanup_deadline:break
                time.sleep(.01)
        final=budget.snapshot();record.update(status='EXITED' if record.get('returncode')==0 and not group_remaining and 'exception' not in record and 'unexpected_descendants_after_leader_exit' not in record else 'FAILED_RETAINED',group_remaining=group_remaining,wall_seconds=time.monotonic()-started,aggregate_after=final)
        if final['cpu_seconds']>LIMITS['cpu_seconds'] or final['wall_seconds']>LIMITS['wall_seconds']:record['status']='FAILED_AGGREGATE_LIMIT_RETAINED'
        save();ACTIVE=None
    return record

def main():
    budget=Budget();install_parent_guards(budget);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});resource.setrlimit(resource.RLIMIT_AS,(1<<30,1<<30))
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--review',type=Path,required=True);p.add_argument('--review-sha',required=True);p.add_argument('--m',type=int,choices=(2,),required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--approval',type=Path,required=True);p.add_argument('--approval-sha',required=True);a=p.parse_args()
    config=a.config.resolve(strict=True);sha=hashlib.sha256(config.read_bytes()).hexdigest();values,review=validate_review(config,a.review.resolve(strict=True),a.review_sha,HERE)
    if values['arm_orders']!=[list(x) for x in ORDERS] or values['stability_limits']!=LIMITS:raise ValueError('exact rotation and aggregate caps required')
    if hashlib.sha256(a.approval.read_bytes()).hexdigest()!=a.approval_sha:raise ValueError('root GO receipt hash')
    approval=json.loads(a.approval.read_text())
    if not (approval.get('authorized') is True and approval.get('config_sha256')==sha and approval.get('review_sha256')==a.review_sha and approval.get('m')==2 and approval.get('action')=='single_three_fresh_m2_rotated_identity_stability' and approval.get('orders')==values['arm_orders'] and approval.get('native_ci_terminal_verified') is True and approval.get('concurrency_rechecked') is True and approval.get('output')==str(a.output.resolve())):raise ValueError('fresh exact root GO required')
    if any(k.startswith('LD_') for k in os.environ):raise ValueError('inherited loader override forbidden')
    python=Path(sys.executable).resolve();pin=values['files'].get(str(python))
    if pin is None or hashlib.sha256(python.read_bytes()).hexdigest()!=pin['sha256']:raise ValueError('pinned interpreter required')
    budget.require_work_budget();claim(config,a.m,sha,a.output);a.output.mkdir()
    env=dict(os.environ,PATH='/usr/bin:/bin',ORDERED_NATIVE_PARENT=str(os.getpid()),OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
    record=dict(status='STARTED',m=2,config_sha256=sha,review_sha256=a.review_sha,limits=LIMITS,orders=values['arm_orders'],automatic_retry=False,parent_identity=identity(os.getpid()),children=[]);receipt=a.output/'PARENT.json';directories=[]
    def save():receipt.write_text(json.dumps(record,indent=2)+'\n')
    save()
    try:
        for order_index,order in enumerate(ORDERS):
            budget.require_work_budget();out=a.output/('trio_'+str(order_index))
            argv=[str(python),'-B','-I','-S',str(HERE/'worker.py'),'--config',str(config),'--sha',sha,'--review',str(a.review.resolve()),'--review-sha',a.review_sha,'--m','2','--order-index',str(order_index),'--out',str(out.resolve())]
            child=supervise(argv,env,out,budget);record['children'].append(dict(order_index=order_index,execution_order=list(order),directory=str(out),parent_sha256=hashlib.sha256((out/'PARENT.json').read_bytes()).hexdigest(),status=child['status']));save()
            if child['status']!='EXITED':raise ValueError('failed/uncertain worker; no later trio or retry')
            directories.append(out)
        budget.require_work_budget();summary=summarize_experiment(directories);budget.require_work_budget()
        (a.output/'EXPERIMENT_RESULT.json').write_text(json.dumps(summary,indent=2)+'\n');record['result_sha256']=hashlib.sha256((a.output/'EXPERIMENT_RESULT.json').read_bytes()).hexdigest();record['status']='EXITED'
    except BaseException as error:record.update(status='FAILED_RETAINED',exception=type(error).__name__+': '+str(error))
    finally:
        record['aggregate_usage']=budget.snapshot()
        if record['aggregate_usage']['cpu_seconds']>LIMITS['cpu_seconds'] or record['aggregate_usage']['wall_seconds']>LIMITS['wall_seconds']:record['status']='FAILED_AGGREGATE_LIMIT_RETAINED'
        save();signal.setitimer(signal.ITIMER_PROF,0);signal.setitimer(signal.ITIMER_REAL,0)
    if record['status']!='EXITED':raise SystemExit(1)
if __name__=='__main__':main()
