"""One-use bounded launcher; no retries, downloads, compilation or CI dispatch."""
import argparse,hashlib,json,os,resource,signal,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from admission import validate_review

def limits():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_CPU,(30,30));resource.setrlimit(resource.RLIMIT_AS,(1<<30,1<<30))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_FSIZE,(4<<20,4<<20))

def identity(pid):
    words=Path('/proc/%d/stat'%pid).read_text().split(') ',1)[1].split()
    return dict(pid=pid,start_ticks=int(words[19]),pgid=int(words[2]),session=int(words[3]),boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())

def claim(config,m,sha,output):
    ledger=config.parent/'attempts';ledger.mkdir(exist_ok=True)
    if m==2:
        previous=json.loads((ledger/'M1.json').read_text());parent=json.loads((Path(previous['output'])/'PARENT.json').read_text());result=json.loads((Path(previous['output'])/'RESULT.json').read_text())
        if not (previous['config_sha256']==sha and parent['status']=='EXITED' and parent['returncode']==0 and not parent['group_remaining'] and result['status']=='PASS_REAL_NATIVE_ATTENTION_COMPONENT_ONLY' and result['m']==1):raise ValueError('M1 success prerequisite missing')
    attempt=ledger/('M%d.json'%m)
    with attempt.open('x') as f:json.dump(dict(config_sha256=sha,m=m,output=str(output.resolve()),status='CLAIMED_NO_RETRY'),f)
    return attempt

def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--review',type=Path,required=True);p.add_argument('--review-sha',required=True);p.add_argument('--m',type=int,choices=(1,2),required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    config=a.config.resolve(strict=True);sha=hashlib.sha256(config.read_bytes()).hexdigest()
    values,review=validate_review(config,a.review.resolve(strict=True),a.review_sha,HERE)
    if any(k.startswith('LD_') for k in os.environ):raise ValueError('inherited loader override forbidden')
    python=Path(sys.executable).resolve();pin=values['files'].get(str(python))
    if pin is None or hashlib.sha256(python.read_bytes()).hexdigest()!=pin['sha256']:raise ValueError('pinned interpreter required')
    claim(config,a.m,sha,a.output);a.output.mkdir()
    env=dict(os.environ,PATH='/usr/bin:/bin',ORDERED_NATIVE_PARENT=str(os.getpid()),OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
    argv=[str(python),'-B','-I',str(HERE/'worker.py'),'--config',str(config),'--sha',sha,'--review',str(a.review.resolve()),'--review-sha',a.review_sha,'--m',str(a.m),'--out',str(a.output.resolve())]
    started=time.monotonic();record=dict(status='STARTED',m=a.m,config_sha256=sha,review_sha256=a.review_sha,cpu_seconds=30,address_space_bytes=1<<30,wall_seconds_limit=45,automatic_retry=False,parent_identity=identity(os.getpid()))
    receipt=a.output/'PARENT.json';receipt.write_text(json.dumps(record,indent=2)+'\n');proc=None;owned=None
    try:
        with (a.output/'worker.log').open('wb') as log:
            proc=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT,env=env,start_new_session=True,preexec_fn=limits)
            owned=identity(proc.pid);record['child_identity']=owned;receipt.write_text(json.dumps(record,indent=2)+'\n')
            try:record['returncode']=proc.wait(timeout=45);record['timed_out']=False
            except subprocess.TimeoutExpired:
                record['timed_out']=True;raise
    except BaseException as error:
        record['exception']=type(error).__name__+': '+str(error)
    finally:
        if proc is not None and proc.poll() is None:
            # Only a still-live child with the exact recorded birth identity.
            try:
                if identity(proc.pid)==owned:
                    os.killpg(proc.pid,signal.SIGKILL);record['cleanup_signal']='SIGKILL_OWN_VERIFIED_GROUP';proc.wait(timeout=3)
                else:record['cleanup_uncertain']='child identity changed; not signalled'
            except (OSError,subprocess.TimeoutExpired) as error:record['cleanup_uncertain']=str(error)
        remaining=False
        if proc is not None:
            record['returncode']=proc.poll()
            try:os.killpg(proc.pid,0);remaining=True
            except ProcessLookupError:pass
        record.update(status='EXITED' if record.get('returncode')==0 and not remaining and 'exception' not in record else 'FAILED_RETAINED',group_remaining=remaining,wall_seconds=time.monotonic()-started)
        receipt.write_text(json.dumps(record,indent=2)+'\n')
    if record['status']!='EXITED':raise SystemExit(1)
if __name__=='__main__':main()
