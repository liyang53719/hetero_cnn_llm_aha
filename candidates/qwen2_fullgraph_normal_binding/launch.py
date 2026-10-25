"""Bounded, once-only launcher for normal import, not a task execution launcher."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time


def save(path, data):
    with path.open('x') as f:
        json.dump(data,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())


EXPECTED_CONFIG_SHA = "c9da94d12ab2a85e28bd31576ec633df86ec8ecf04cb2f8110a85c48e63fda60"


def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument('--config',required=True,type=Path)
    ap.add_argument('--config-sha',required=True)
    ap.add_argument('--output',required=True,type=Path)
    args=ap.parse_args(argv)
    if args.config_sha != EXPECTED_CONFIG_SHA:raise ValueError('only reviewed exact cold config allowed')
    raw=args.config.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=args.config_sha:raise ValueError('exact config hash')
    cfg=json.loads(raw)
    bounds=dict(cpus=1,address_space_bytes=256*1024**2,cpu_seconds=20,wall_seconds=25)
    if cfg['resource']!=bounds or cfg['actual_numeric_authorized'] is not False:
        raise ValueError('cold-only fixed resource profile required')
    wrapper=Path(__file__).resolve().with_name('adapter.py')
    pin=cfg['candidate_files'][str(wrapper)]
    if hashlib.sha256(wrapper.read_bytes()).hexdigest()!=pin['sha256']:
        raise ValueError('wrapper source changed')
    out=args.output.resolve();out.mkdir(exist_ok=False)
    cpu=min(os.sched_getaffinity(0))
    command=[sys.executable,'-I','-S','-B',str(wrapper),'--config',str(args.config.resolve()),
             '--config-sha',args.config_sha,'--output',str(out/'child')]
    env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8',
         'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1',
         'PYTHONDONTWRITEBYTECODE':'1'}
    save(out/'CLAIM.json',dict(config_sha256=args.config_sha,command=command,bounds=bounds,cpu=cpu,
        launcher_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        environment=env,launching_parent_pid=os.getpid(),wall_start=time.time()))
    def child_limits():
        os.sched_setaffinity(0,{cpu})
        resource.setrlimit(resource.RLIMIT_AS,(bounds['address_space_bytes'],)*2)
        resource.setrlimit(resource.RLIMIT_CPU,(bounds['cpu_seconds'],)*2)
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    started=time.monotonic();timed_out=False
    with (out/'stdout.log').open('xb') as stdout,(out/'stderr.log').open('xb') as stderr:
        process=subprocess.Popen(command,stdout=stdout,stderr=stderr,env=env,
                                 start_new_session=True,preexec_fn=child_limits)
        save(out/'IDENTITY.json',dict(pid=process.pid,pgid=os.getpgid(process.pid),
            proc_stat=Path('/proc/%d/stat'%process.pid).read_text(),command=command))
        try:code=process.wait(timeout=bounds['wall_seconds'])
        except subprocess.TimeoutExpired:
            timed_out=True
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            code=process.wait()
    try:os.killpg(process.pid,0);group_exists=True
    except ProcessLookupError:group_exists=False
    child_result=out/'child/ADAPTER_RESULT.json'
    status=json.loads(child_result.read_text()).get('status') if child_result.is_file() else None
    result=dict(exit_code=code,timed_out=timed_out,group_exists=group_exists,
        wall_seconds=time.monotonic()-started,child_status=status,
        child_result_sha256=hashlib.sha256(child_result.read_bytes()).hexdigest() if child_result.is_file() else None,
        status='PASS_NORMAL_BINDING_ADAPTER_WRAPPER' if code==0 and not timed_out and not group_exists and status=='PASS_NORMAL_FULLGRAPH_BINDING_ONLY' else 'FAIL_COLD_WRAPPER',
        native_task_executed=False,numeric_acceptance=False)
    save(out/'PARENT_RESULT.json',result)
    return int(result['status']!='PASS_NORMAL_BINDING_ADAPTER_WRAPPER')

if __name__=='__main__':raise SystemExit(main())
