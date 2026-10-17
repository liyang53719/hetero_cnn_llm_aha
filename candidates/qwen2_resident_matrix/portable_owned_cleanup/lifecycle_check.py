"""Explicitly invoked stdlib-only lifecycle evidence, one attempt per case.

Run only after exact source review. No numerical/native/compiler work. Failure
is preserved; fixture teardown never changes it to successful cleanup.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import types

SOURCE=Path(__file__).with_name('strict_cleanup.py')
BUFFER=SOURCE.read_bytes()
strict=types.ModuleType('strict_cleanup')
strict.__file__=str(SOURCE)
strict._ADMITTED_SOURCE_SHA256=hashlib.sha256(BUFFER).hexdigest()
exec(compile(BUFFER,str(SOURCE),'exec'),strict.__dict__)

FIXTURE=r'''
import json,os,pathlib,sys,time
out=pathlib.Path(sys.argv[1]); mode=sys.argv[2]; nonce=sys.argv[3]
def identity(pid):
    raw=pathlib.Path('/proc/%d/stat'%pid).read_bytes(); fields=raw[raw.rindex(b')')+1:].split()
    return dict(pid=pid,ppid=int(fields[1]),group=int(fields[2]),session=int(fields[3]),start=int(fields[19]),state=fields[0].decode('ascii'))
child=os.fork()
if child==0:
    time.sleep(8)
    os._exit(0)
manifest=dict(nonce=nonce,created_ns=time.monotonic_ns(),leader=identity(os.getpid()),descendant=identity(child))
temporary=out.with_suffix('.tmp');temporary.write_text(json.dumps(manifest));temporary.replace(out)
if mode=='zero':sys.exit(0)
if mode=='nonzero':sys.exit(7)
time.sleep(8)
'''


def require(ok,message):
    if not ok:raise RuntimeError(message)


def one_case(mode,root):
    started=time.monotonic();stop=started+10;work_stop=stop-6
    nonce=os.urandom(16).hex();manifest_path=root/(mode+'.manifest.json')
    report=dict(mode=mode,started=started,work_stop=work_stop,stop=stop,source_sha256=strict.SOURCE_SHA256,
                status='IN_PROGRESS',attempt=1)
    process=subprocess.Popen([sys.executable,'-I','-B']+(['-O'] if not __debug__ else [])+['-c',FIXTURE,str(manifest_path),mode,nonce],start_new_session=True,
                             stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    owner=dict(process=process,identity=None);report['leader_pid']=process.pid
    api=strict._Linux()
    try:
        while not manifest_path.exists():
            require(time.monotonic()<work_stop,'fixture readiness timeout')
            time.sleep(.002)
        with manifest_path.open('rb') as stream:raw=stream.read(16385)
        require(len(raw)<=16384,'bounded fixture manifest');manifest=json.loads(raw)
        report['manifest']=manifest
        require(manifest['nonce']==nonce and started*1e9<=manifest['created_ns']<work_stop*1e9,'fixture readiness binding')
        for key in ('leader','descendant'):
            strict._identity(manifest[key],captured=True)
            require(manifest[key]['group']==process.pid and manifest[key]['session']==process.pid,'fixture group/session')
        require(manifest['leader']['pid']==process.pid and manifest['leader']['ppid']==os.getpid(),'fixture direct owner')
        require(manifest['descendant']['ppid']==process.pid,'fixture descendant parent')
        owner['identity']={key:manifest['leader'][key] for key in strict.OWNER_KEYS}
        # WNOWAIT leaves the original leader retained on every work outcome.
        if mode=='timeout':
            try:
                while time.monotonic()<work_stop:time.sleep(min(.005,max(0,work_stop-time.monotonic())))
                raise InterruptedError('fixture original work deadline')
            except InterruptedError as error:
                require(type(error) is InterruptedError and str(error)=='fixture original work deadline','exact fixture timeout')
                report['work_outcome']=dict(type=type(error).__name__,message=str(error),at=time.monotonic())
        else:
            while True:
                require(time.monotonic()<work_stop,'fixture exit timeout')
                observed=os.waitid(os.P_PID,process.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
                if observed is not None:
                    require(observed.si_code==os.CLD_EXITED and observed.si_status==(0 if mode=='zero' else 7),'exact fixture exit')
                    report['work_outcome']=dict(type='direct_exit_observed_WNOWAIT',code=observed.si_status,at=time.monotonic())
                    break
                time.sleep(.002)
        prior_alarm=signal.getsignal(signal.SIGALRM);prior_mask=signal.pthread_sigmask(signal.SIG_BLOCK,set())
        require(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0),'no work timer at cleanup entry')
        report['cleanup_entered']=time.monotonic()
        proof=strict.cleanup_owned(owner,stop)
        report['cleanup_returned']=time.monotonic()
        strict.validate_cleanup_proof(proof,owner=owner,stop=stop)
        require(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0) and signal.getsignal(signal.SIGALRM)==prior_alarm and
                signal.pthread_sigmask(signal.SIG_BLOCK,set())==prior_mask,'cleanup alarm/handler/mask restored')
        report['proof']=proof;report['observations']=owner['strict_cleanup_observation']
        require(report['cleanup_returned']<stop,'cleanup returned before original stop')
        # Independently bound confirmation to the exact original stop too.
        api.arm(stop,time.monotonic)
        try:
            tracked={manifest[key]['pid']:manifest[key] for key in ('leader','descendant')}
            scan=api.scan(tracked,process.pid,stop,time.monotonic);report['after_return_scan']=scan
            require(scan['complete'] is True and not scan['members'],'complete empty original group after return')
            require(all(current is None or current['start']!=tracked[int(pid)]['start']
                        for pid,current in scan['captured'].items()),'original identities absent after return')
            require(time.monotonic()<stop,'post-return check within original stop')
        finally:api.disarm()
        require(process.returncode==(0 if mode=='zero' else 7 if mode=='nonzero' else -signal.SIGKILL),'exact final direct status')
        report['status']='PASS'
    except BaseException as error:
        report['status']='FAIL';report['error']=type(error).__name__+': '+str(error)
        report['observations']=owner.get('strict_cleanup_observation')
        if isinstance(error,strict.CleanupFailure):report['cleanup_failure_evidence']=error.evidence
        raise
    finally:
        # No group signal, new cleanup budget, retry, or descendant reaping here.
        # A retained failed child is left explicit for supervisor diagnosis; the
        # fixture has its own 8-second lifetime independent of helper success.
        report['finished']=time.monotonic();report['direct_returncode']=process.returncode
        report['fixture_teardown']=dict(group_signals=0,descendants_reaped=False,retry=False)
        (root/(mode+'.json')).write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
        for stream in (process.stdout,process.stderr):stream.close()
    return report


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    results=[]
    for mode in ('zero','nonzero','timeout'):
        result=one_case(mode,args.output);results.append(dict(mode=mode,status=result['status']))
        print(json.dumps(results[-1]),flush=True)
    summary=dict(schema=1,mode='optimized' if not __debug__ else 'normal',source_sha256=strict.SOURCE_SHA256,
                 lifecycle_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),cases=results)
    (args.output/'SUMMARY.json').write_text(json.dumps(summary,sort_keys=True,indent=2)+'\n')
    print(json.dumps(summary,sort_keys=True),flush=True)


if __name__=='__main__':main()
