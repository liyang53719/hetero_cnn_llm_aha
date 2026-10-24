"""Bounded normal-import-only supervisor. This cannot launch the numeric worker."""
import argparse,hashlib,json,os,resource,signal,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def identity(pid):
    fields=Path('/proc/%d/stat'%pid).read_text().split(') ',1)[1].split()
    return dict(pid=pid,start_ticks=int(fields[19]),pgid=int(fields[2]),session=int(fields[3]),boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
def limits():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_CPU,(20,20));resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,)*2)
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_FSIZE,(8<<20,8<<20))
def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--config-sha',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--optimized',action='store_true');a=p.parse_args()
    config=a.config.resolve(strict=True)
    if digest(config)!=a.config_sha:raise ValueError('exact config identity')
    c=json.loads(config.read_text());script=HERE/'cold_import.py';python=Path(sys.executable).resolve()
    for path in (script,HERE/'module_inventory.py',Path(__file__).resolve(),python):
        pin=c['files'].get(str(path))
        if pin is None or path.stat().st_size!=pin['bytes'] or digest(path)!=pin['sha256']:raise ValueError('cold executable identity '+path.name)
    if any(k.startswith('LD_') for k in os.environ):raise ValueError('loader override forbidden')
    a.output.mkdir(exist_ok=False);out=a.output.resolve();child=out/'worker'
    argv=[str(python),'-I','-S','-B',*(['-O'] if a.optimized else []),str(script),'--config',str(config),'--config-sha',a.config_sha,'--output',str(child)]
    env=dict(os.environ,PATH='/usr/bin:/bin',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
    source_hashes={str(path):digest(path) for path in (script,HERE/'module_inventory.py',Path(__file__).resolve())}
    receipt=dict(source_hashes=source_hashes,status='STARTED',config_sha256=a.config_sha,parent=identity(os.getpid()),argv=argv,limits=dict(cpus=1,address_space_bytes=256*1024**2,cpu_seconds=20,wall_seconds=25),numeric_execution=False)
    start=time.monotonic();proc=None;owned=None
    def save(): (out/'PARENT.json').write_text(json.dumps(receipt,indent=2)+'\n')
    save()
    try:
        with (out/'worker.log').open('xb') as log:
            proc=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT,env=env,start_new_session=True,preexec_fn=limits)
            owned=identity(proc.pid);receipt['child']=owned;save()
            try:receipt['exit']=proc.wait(timeout=25);receipt['timed_out']=False
            except subprocess.TimeoutExpired:receipt['timed_out']=True;raise
    except BaseException as error:receipt['error']=type(error).__name__+': '+str(error)
    finally:
        if proc is not None and proc.poll() is None:
            try:
                if identity(proc.pid)==owned:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=3);receipt['cleanup']='owned child group killed'
                else:receipt['cleanup_uncertain']='identity changed; no signal'
            except (OSError,subprocess.TimeoutExpired) as error:receipt['cleanup_uncertain']=str(error)
        remaining=False
        if proc is not None:
            receipt['exit']=proc.poll()
            try:os.killpg(proc.pid,0);remaining=True
            except ProcessLookupError:pass
        receipt.update(group_remaining=remaining,wall_seconds=time.monotonic()-start,config_unchanged=digest(config)==a.config_sha,sources_unchanged=all(digest(p)==h for p,h in source_hashes.items()))
        if not receipt['config_unchanged'] or not receipt['sources_unchanged']:receipt['error']='source/config changed during cold execution'
        receipt['status']='EXITED' if receipt.get('exit')==0 and not remaining and 'error' not in receipt else 'FAILED_RETAINED'
        save()
    if receipt['status']!='EXITED':raise SystemExit(1)
if __name__=='__main__':main()
