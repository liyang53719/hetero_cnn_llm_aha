"""Single fixed launch: process-group wall/CPU and observed directory budgets."""
import datetime,hashlib,json,os,pathlib,signal,subprocess,sys,time
sys.path.insert(0,str(pathlib.Path.cwd()))
from candidates.qwen2_supervisor_recovery.observation import SignalScope

def supervise(argv,out,log,err,receipt,*,wall=29):
    out,log,err,receipt=map(pathlib.Path,(out,log,err,receipt))
    if out.exists() or any(p.exists() for p in (log,err,receipt)):raise ValueError('fresh supervisor namespace')
    started=datetime.datetime.now(datetime.timezone.utc).isoformat();begin=time.monotonic();hz=os.sysconf('SC_CLK_TCK')
    def group_cpu(group):
        total=0
        for p in pathlib.Path('/proc').iterdir():
            if not p.name.isdigit():continue
            try:
                text=(p/'stat').read_text();fields=text[text.rfind(')')+2:].split()
                if int(fields[2])==group:total+=sum(int(fields[i]) for i in (11,12,13,14))
            except (OSError,ValueError,IndexError):pass
        return total/hz
    def output_bytes():
        return sum(p.stat().st_size for p in out.rglob('*') if p.is_file())+sum(p.stat().st_size for p in (log,err) if p.exists())
    reason=None;peak_cpu=peak_output=0;proc=None;code=None;error=None;signals=SignalScope()
    with log.open('xb') as stdout,err.open('xb') as stderr:
        signals.start()
        try:
            proc=subprocess.Popen(argv,cwd=pathlib.Path.cwd(),stdout=stdout,stderr=stderr,start_new_session=True)
            signals.check()
            print(json.dumps({'pid':proc.pid,'pgid':proc.pid,'out':str(out),'started_utc':started}),flush=True)
            while proc.poll() is None:
                signals.check();elapsed=time.monotonic()-begin;cpu=group_cpu(proc.pid);size=output_bytes()
                peak_cpu=max(peak_cpu,cpu);peak_output=max(peak_output,size)
                if elapsed>=wall:reason='WALL_BUDGET'
                elif cpu>=19:reason='CPU_GROUP_BUDGET'
                elif size>=7<<20:reason='OBSERVED_OUTPUT_BUDGET'
                if reason:break
                time.sleep(.05)
            signals.check()
        except BaseException as e:
            error=type(e).__name__;reason='SUPERVISOR_INTERRUPTED_OR_ERROR'
        finally:
            signals.cleaning()
            try:
                if proc is not None:
                    try:os.killpg(proc.pid,signal.SIGTERM)
                    except ProcessLookupError:pass
                    try:proc.wait(timeout=.3)
                    except subprocess.TimeoutExpired:pass
                    # Always clear descendants, even after normal parent exit.
                    try:os.killpg(proc.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    code=proc.wait()
            finally:signals.stop()
    final=output_bytes()
    r=dict(argv=argv,pid=None if proc is None else proc.pid,started_utc=started,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
      returncode=code,stop_reason=reason,supervisor_error=error,wall_seconds=time.monotonic()-begin,observed_group_cpu_seconds_peak=peak_cpu,
      output_bytes_including_logs=final,output_under_8MiB=final<(8<<20),source_sha256=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
      limits=dict(external_wall_seconds=wall+1,group_cpu_stop_seconds=19,per_process_cpu_rlimit_seconds=20,address_space_rlimit_bytes=2<<30,
        observed_output_stop_bytes=7<<20,total_output_budget_bytes=8<<20,output_is_filesystem_hard_quota=False,poll_interval_seconds=.05))
    receipt.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps(r),flush=True)
    return 0 if code==0 and reason is None and final<8<<20 else 1

if __name__=='__main__':
    root=pathlib.Path.cwd();base=root/'work/qwen2_quiescent_ports_candidate';out=base/'compare01'
    argv=[sys.executable,'-B','-m','candidates.qwen2_quiescent_ports_candidate.check_small','--execute','--out',str(out)]
    sys.exit(supervise(argv,out,base/'compare01.stdout.log',base/'compare01.stderr.log',base/'compare01.SUPERVISOR.json'))
