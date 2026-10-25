"""One-use postterminal reference-only supervisor; reviewed owned-group core, no retry or CI."""
import argparse,hashlib,json,math,os,resource,signal,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from admission import validate_review
from policy import LIMITS, ARMS, PROFILE, ACTION

def limits(cpu_seconds,previous_mask=()):
    signal.setitimer(signal.ITIMER_PROF,0);signal.setitimer(signal.ITIMER_REAL,0)
    signal.signal(signal.SIGPROF,signal.SIG_DFL);signal.signal(signal.SIGALRM,signal.SIG_DFL)
    signal.pthread_sigmask(signal.SIG_SETMASK,previous_mask)
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_CPU,(cpu_seconds,cpu_seconds));resource.setrlimit(resource.RLIMIT_AS,(LIMITS['address_space_bytes'],)*2)
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_FSIZE,(LIMITS['file_bytes'],)*2)
def identity(pid):
    words=Path('/proc/%d/stat'%pid).read_text().split(') ',1)[1].split()
    return dict(pid=pid,start_ticks=int(words[19]),pgid=int(words[2]),session=int(words[3]),boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
def claim(config,m,sha,output):
    ledger=config.parent/'attempts';ledger.mkdir(exist_ok=True)
    if m!=16:raise ValueError('one true M16 component only; no full21/M128 execution')
    attempt=ledger/'M16_postterminal_reference.json'
    with attempt.open('x') as f:json.dump(dict(config_sha256=sha,m=m,output=str(output.resolve()),execution_order=list(ARMS),status='CLAIMED_ONE_REFERENCE_NO_DUT_RERUN'),f)
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
        resource.setrlimit(resource.RLIMIT_CPU,(LIMITS['parent_cpu_abort_hard'],)*2)
        signal.signal(signal.SIGALRM,cleanup_deadline_signal)
        signal.setitimer(signal.ITIMER_REAL,LIMITS['cleanup_wall_reserve'])
    raise TimeoutError('parent work guard; verified active group stopped before cleanup')

def install_parent_guards(budget):
    signal.signal(signal.SIGPROF,parent_work_budget_signal);signal.signal(signal.SIGALRM,parent_work_budget_signal)
    signal.setitimer(signal.ITIMER_PROF,max(.001,LIMITS['parent_cpu_work']-time.process_time()))
    signal.setitimer(signal.ITIMER_REAL,max(.001,LIMITS['wall_seconds']-LIMITS['cleanup_wall_reserve']-(time.monotonic()-budget.started)))

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

def require_output_budget(root):
    import stat
    totals=dict(trace_pair_bytes=0,artifact_bytes=0,audit_bytes=0,log_bytes=0,worker_metadata_bytes=0,parent_metadata_bytes=0)
    for path in Path(root).rglob('*'):
        entry=path.lstat()
        if stat.S_ISDIR(entry.st_mode):continue
        if not stat.S_ISREG(entry.st_mode) or entry.st_nlink!=1:raise ValueError('output links or special files forbidden')
        rel=path.relative_to(root);parts=rel.parts
        if path.name=='PARENT.json' or len(parts)==1:key='parent_metadata_bytes'
        elif path.name=='worker.log':key='log_bytes'
        elif len(parts)>2 and parts[1]=='streams':
            key='trace_pair_bytes'
            if entry.st_size>LIMITS['file_bytes']:raise TimeoutError('single raw stream cap')
        elif len(parts)>2 and parts[1]=='artifacts':key='artifact_bytes'
        elif len(parts)>2 and parts[1]=='audits':key='audit_bytes'
        else:key='worker_metadata_bytes'
        totals[key]+=entry.st_size
    if any(value>LIMITS[key] for key,value in totals.items()) or sum(totals.values())>LIMITS['output_bytes']:raise TimeoutError('sampled output partition/total limit exceeded; evidence preserved')
    return dict(**totals,total_bytes=sum(totals.values()),sampled_not_atomic=True)

class Budget:
    def __init__(self):
        self.started=time.monotonic();self.output_root=None
        self.peak_rss_bytes=0;self.peak_rss_elapsed=0.;self.rss_samples=0
        self.peak_live_tree_rss_bytes=0;self.live_samples=0
    def snapshot(self,owned=None):
        child=resource.getrusage(resource.RUSAGE_CHILDREN);live_cpu=live_rss=0
        if owned is not None:live_cpu,live_rss=live_usage(owned)
        words=Path('/proc/self/stat').read_text().split(') ',1)[1].split()
        value=dict(cpu_seconds=time.process_time()+child.ru_utime+child.ru_stime+live_cpu,wall_seconds=time.monotonic()-self.started,rss_bytes=int(words[21])*os.sysconf('SC_PAGE_SIZE')+live_rss)
        self.rss_samples+=1
        if value['rss_bytes']>self.peak_rss_bytes:self.peak_rss_bytes=value['rss_bytes'];self.peak_rss_elapsed=value['wall_seconds']
        if owned is not None:self.live_samples+=1;self.peak_live_tree_rss_bytes=max(self.peak_live_tree_rss_bytes,live_rss)
        value['sampled_rss_high_water']=dict(combined_parent_tree_bytes=self.peak_rss_bytes,at_elapsed_seconds=self.peak_rss_elapsed,live_tree_bytes=self.peak_live_tree_rss_bytes,samples=self.rss_samples,live_samples=self.live_samples,sampling_interval_seconds=.2,not_exact_continuous_peak=True)
        value['reaped_children_maxrss_bytes']=child.ru_maxrss*1024
        value['reaped_maxrss_is_aggregate_tree']=False
        return value
    def require_work_budget(self,owned=None):
        value=self.snapshot(owned)
        if self.output_root is not None:require_output_budget(self.output_root)
        if value['cpu_seconds']>=LIMITS['cpu_seconds']-LIMITS['cleanup_cpu_reserve'] or value['wall_seconds']>=LIMITS['wall_seconds']-LIMITS['cleanup_wall_reserve'] or value['rss_bytes']>=LIMITS['tree_rss_bytes']:
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
            deadline=started+wall_limit;last_telemetry_save=0.
            while True:
                remaining=deadline-time.monotonic()
                if remaining<=0:raise TimeoutError('per-child wall cap')
                # Do not reap yet: preserving the leader birth closes the
                # leader-exit/descendant-linger cleanup race without PID guesses.
                ended=os.waitid(os.P_PID,proc.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
                if ended is not None:
                    record['last_live_usage']=budget.require_work_budget(owned)
                    save()
                    descendants=same_group_descendants(owned)
                    if descendants:record['unexpected_descendants_after_leader_exit']=descendants
                    break
                record['last_live_usage']=budget.require_work_budget(owned)
                if time.monotonic()-last_telemetry_save>=1:
                    save();last_telemetry_save=time.monotonic()
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
    budget=Budget();install_parent_guards(budget);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});resource.setrlimit(resource.RLIMIT_AS,(LIMITS['address_space_bytes'],)*2)
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--review',type=Path,required=True);p.add_argument('--review-sha',required=True);p.add_argument('--m',type=int,choices=(16,),required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--approval',type=Path,required=True);p.add_argument('--approval-sha',required=True);a=p.parse_args()
    config=a.config.resolve(strict=True);sha=hashlib.sha256(config.read_bytes()).hexdigest();values,review=validate_review(config,a.review.resolve(strict=True),a.review_sha,HERE)
    if values['arm_order']!=list(ARMS) or values['limits']!=LIMITS:raise ValueError('exact pair and aggregate caps required')
    if hashlib.sha256(a.approval.read_bytes()).hexdigest()!=a.approval_sha:raise ValueError('root GO receipt hash')
    approval=json.loads(a.approval.read_text())
    if not (approval.get('authorized') is True and approval.get('config_sha256')==sha and approval.get('review_sha256')==a.review_sha and approval.get('m')==16 and approval.get('action')==ACTION and approval.get('arm_order')==values['arm_order'] and approval.get('limits')==LIMITS and approval.get('native_ci_terminal_verified') is True and approval.get('concurrency_rechecked') is True and approval.get('output')==str(a.output.resolve())):raise ValueError('fresh exact root GO required')
    if any(k.startswith('LD_') for k in os.environ):raise ValueError('inherited loader override forbidden')
    python=Path(sys.executable).resolve();pin=values['files'].get(str(python))
    if pin is None or hashlib.sha256(python.read_bytes()).hexdigest()!=pin['sha256']:raise ValueError('pinned interpreter required')
    budget.require_work_budget();claim(config,a.m,sha,a.output);a.output.mkdir();budget.output_root=a.output
    env=dict(os.environ,PATH='/usr/bin:/bin',ORDERED_NATIVE_PARENT=str(os.getpid()),OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
    record=dict(status='STARTED',m=16,config_sha256=sha,review_sha256=a.review_sha,limits=LIMITS,execution_order=list(ARMS),automatic_retry=False,parent_identity=identity(os.getpid()));receipt=a.output/'PARENT.json'
    def save():receipt.write_text(json.dumps(record,indent=2)+'\n')
    save()
    try:
        budget.require_work_budget();out=a.output/'pair'
        argv=[str(python),'-B','-I','-S',str(HERE/'worker.py'),'--config',str(config),'--sha',sha,'--review',str(a.review.resolve()),'--review-sha',a.review_sha,'--m','16','--out',str(out.resolve())]
        child=supervise(argv,env,out,budget);record['child']=dict(directory=str(out),parent_sha256=hashlib.sha256((out/'PARENT.json').read_bytes()).hexdigest(),status=child['status']);save()
        if child['status']!='EXITED':raise ValueError('failed/uncertain reference worker; no retry')
        budget.require_work_budget()
        result=json.loads((out/'RESULT.json').read_text())
        if result.get('status')!='PASS_POSTTERMINAL_REFERENCE_REVALIDATION_ONLY' or result.get('rows')!=16 or result.get('fullblock') is not False or result.get('reference_after_both_component_terminals') is not True or result.get('original_attempt_state')!='FAILED_RETAINED' or result.get('DUT_reexecuted') is not False:raise ValueError('incomplete exact component worker terminal')
        record['result_sha256']=hashlib.sha256((out/'RESULT.json').read_bytes()).hexdigest();record['status']='EXITED'
    except BaseException as error:record.update(status='FAILED_RETAINED',exception=type(error).__name__+': '+str(error))
    finally:
        record['aggregate_usage']=budget.snapshot()
        if record['aggregate_usage']['cpu_seconds']>LIMITS['cpu_seconds'] or record['aggregate_usage']['wall_seconds']>LIMITS['wall_seconds']:record['status']='FAILED_AGGREGATE_LIMIT_RETAINED'
        try:record['output_usage']=require_output_budget(a.output)
        except BaseException as error:record.update(status='FAILED_OUTPUT_LIMIT_RETAINED',output_limit_error=str(error))
        save()
        # Terminal receipts count too. A failed receipt is preserved, never pruned.
        try:require_output_budget(a.output)
        except BaseException as error:record.update(status='FAILED_OUTPUT_LIMIT_RETAINED',output_limit_error=str(error));save()
        signal.setitimer(signal.ITIMER_PROF,0);signal.setitimer(signal.ITIMER_REAL,0)
    if record['status']!='EXITED':raise SystemExit(1)
if __name__=='__main__':main()
