"""Fixed two-phase local cost diagnostic. No retry or acceptance authority."""
import argparse
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time
from candidates.qwen2_supervisor_recovery.observation import SignalScope

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'work/qwen2_m16_stage_diagnostic/cost01'
LIMITS={'REFERENCE':(60,90),'MODEL':(1200,1260)}
MEMORY=4<<30
OUTPUT=96<<20

def need(value,message):
    if not value:raise ValueError(message)

def atomic(path,value):
    need(len((json.dumps(value,sort_keys=True)+'\n').encode())<=8192,'bounded supervisor record')
    temporary=path.with_suffix(path.suffix+'.tmp')
    with temporary.open('w') as stream:
        json.dump(value,stream,sort_keys=True);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)
    fd=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)

def group_usage(group):
    cpu=rss=0;hz=os.sysconf('SC_CLK_TCK');page=os.sysconf('SC_PAGE_SIZE')
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():continue
        try:
            raw=(path/'stat').read_text();f=raw[raw.rfind(')')+2:].split()
            if int(f[2])!=group or f[0]=='Z':continue
            cpu+=sum(int(f[i]) for i in (11,12,13,14))/hz;rss+=int(f[21])*page
        except (OSError,ValueError,IndexError):pass
    return cpu,rss

def output_bytes(base):
    total=0
    for path in base.rglob('*'):
        need(not path.is_symlink(),'no output aliases')
        if path.is_file():total+=path.stat().st_size
    return total

def supervise(argv,base,phase,*,test_limits=None):
    need(phase in LIMITS,'fixed phase')
    cpu_limit,wall_limit=LIMITS[phase] if test_limits is None else test_limits
    base=Path(base);base.mkdir(parents=True,exist_ok=True)
    prefix=base/phase.lower();receipt=prefix.with_suffix('.SUPERVISOR.json')
    stdout=prefix.with_suffix('.stdout.log');stderr=prefix.with_suffix('.stderr.log')
    heartbeat=prefix.with_suffix('.HEARTBEAT.json')
    need(not any(p.exists() for p in (receipt,stdout,stderr,heartbeat)),'single-use phase')
    started=time.monotonic();child=None;code=None;reason=None;error=None;peak_cpu=peak_rss=peak_output=0
    scope=SignalScope();last_heartbeat=-10
    def limits():
        resource.setrlimit(resource.RLIMIT_CPU,(int(cpu_limit),int(cpu_limit)))
        resource.setrlimit(resource.RLIMIT_AS,(MEMORY,MEMORY))
        resource.setrlimit(resource.RLIMIT_FSIZE,(OUTPUT,OUTPUT))
    def snapshot(status):
        return dict(schema=1,scope='M16_COST_DIAGNOSTIC_ONLY',phase=phase,status=status,
          returncode=code,stop_reason=reason,error_class=error,wall_seconds=time.monotonic()-started,
          observed_group_cpu_seconds=peak_cpu,observed_group_rss_bytes=peak_rss,
          observed_output_bytes=peak_output,acceptance=False,hardware_cycles=None,
          cpu_limit_seconds=cpu_limit,wall_limit_seconds=wall_limit,
          address_space_limit_bytes=MEMORY,combined_observed_output_limit_bytes=OUTPUT)
    with stdout.open('xb') as out,stderr.open('xb') as err:
        scope.start()
        try:
            child=subprocess.Popen(argv,cwd=ROOT,stdout=out,stderr=err,start_new_session=True,preexec_fn=limits)
            scope.check()
            while child.poll() is None:
                scope.check();elapsed=time.monotonic()-started
                cpu,rss=group_usage(child.pid);size=output_bytes(base)
                peak_cpu=max(peak_cpu,cpu);peak_rss=max(peak_rss,rss);peak_output=max(peak_output,size)
                if elapsed>=wall_limit-2:reason='WALL_BUDGET'
                elif cpu>=cpu_limit-1:reason='CPU_BUDGET'
                elif rss>=MEMORY:reason='OBSERVED_RSS_BUDGET'
                elif size>=OUTPUT-(1<<20):reason='OBSERVED_OUTPUT_BUDGET'
                if reason:break
                if elapsed-last_heartbeat>=5:
                    atomic(heartbeat,snapshot('RUNNING'));last_heartbeat=elapsed
                time.sleep(.1)
            scope.check()
        except BaseException as exc:
            reason='SUPERVISOR_INTERRUPTED_OR_ERROR';error=type(exc).__name__ if type(exc).__name__ in ('OSError','ValueError','ObservedSignal') else 'OTHER'
        finally:
            scope.cleaning()
            try:
                if child is not None:
                    try:os.killpg(child.pid,signal.SIGTERM)
                    except ProcessLookupError:pass
                    try:child.wait(timeout=.3)
                    except subprocess.TimeoutExpired:pass
                    try:os.killpg(child.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    code=child.wait(timeout=1)
            finally:scope.stop()
    peak_output=max(peak_output,output_bytes(base))
    # Reserve space for both bounded final records and an atomic temporary.
    if peak_output>=OUTPUT-(64<<10) and reason is None:reason='FINAL_RECORD_OUTPUT_RESERVE'
    passed=code==0 and reason is None and peak_output<OUTPUT-(64<<10) and time.monotonic()-started<=wall_limit
    result=snapshot('COMPLETE' if passed else 'INCOMPLETE')
    atomic(receipt,result);atomic(heartbeat,result)
    print(json.dumps(result,sort_keys=True),flush=True)
    return 0 if passed else 1

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--phase',choices=tuple(LIMITS))
    a=p.parse_args(argv)
    if not a.execute:
        need(a.phase is None,'phase requires execute');print(json.dumps(dict(status='NOT_EXECUTED',scope='M16_COST_DIAGNOSTIC_ONLY')));return 0
    need(a.phase is not None,'one explicit phase')
    module='reference' if a.phase=='REFERENCE' else 'runner'
    target=BASE/('reference' if a.phase=='REFERENCE' else 'model')
    need(not target.exists(),'fresh phase output')
    command=[sys.executable,'-B','-m','candidates.qwen2_m16_stage_diagnostic.'+module,'--execute','--out',str(target)]
    if a.phase=='REFERENCE':
        prior=json.loads((BASE/'model.SUPERVISOR.json').read_text())
        need(prior.get('phase')=='MODEL' and prior.get('status')=='COMPLETE' and
             prior.get('returncode')==0 and prior.get('stop_reason') is None,'model phase must complete first')
        command += ['--model',str(BASE/'model')]
    return supervise(command,BASE,a.phase)

if __name__=='__main__':raise SystemExit(main())
