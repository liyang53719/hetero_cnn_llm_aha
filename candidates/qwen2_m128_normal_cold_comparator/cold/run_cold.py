"""Single-use exact-GO cold loader. No numeric mode and no automatic retries."""
import argparse,json,os,resource,signal,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from supervisor_common import (need,read_checked,file_id,sha,encoded,write_new,
    process_stat,OwnedIdentities,discover_tree,stop_owned,manifest_postflight)
from admission import validate,BOUNDS


def main():
    p=argparse.ArgumentParser()
    for name in ('config','config-sha','review','review-sha','approval','output'):
        p.add_argument('--'+name,required=True)
    p.add_argument('--go',required=True,choices=['GO'])
    a=p.parse_args();cfg=read_checked(a.config,a.config_sha)
    review=read_checked(a.review,a.review_sha);approval_raw=Path(a.approval).read_bytes()
    need(len(approval_raw)<=16384,'approval too large');approval=json.loads(approval_raw)
    validate(cfg,a.config_sha,review,a.review_sha,approval)
    need(Path(sys.executable).resolve()==Path(cfg['interpreter']),'exact Python')
    need(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode and not sys.flags.optimize,'exact -I -S -B flags')
    need(not any(k.startswith('LD_') for k in os.environ),'loader overrides forbidden')
    pre=manifest_postflight(cfg['files']);need(pre['passed'],'cold preflight pins differ')
    out=Path(a.output).resolve();need(out==Path(cfg['cold_directory'])/approval['run_id'] and not out.exists(),'fresh exact approved output')
    parent=process_stat(os.getpid());argv=[os.fsdecode(x) for x in Path('/proc/self/cmdline').read_bytes().split(b'\0') if x]
    claim={'parent_identity':parent,'config_sha256':a.config_sha,'review_sha256':a.review_sha,
        'approval_sha256':sha(approval_raw),'output':str(out),'run_id':approval['run_id'],'no_retry':True}
    claim_pin=write_new(Path(cfg['cold_directory'])/'COLD_CLAIM.json',claim)
    out.mkdir();write_new(out/'PREFLIGHT.json',pre)
    (out/'REVIEW.json').write_bytes(Path(a.review).read_bytes());(out/'APPROVAL.json').write_bytes(approval_raw)
    cpu=min(os.sched_getaffinity(0));cap=dict(claim,parent_pid=os.getpid(),parent_start_ticks=parent['start_ticks'],
        parent_argv=argv,claim_sha256=claim_pin['sha256'],affinity=[cpu])
    readfd,writefd=os.pipe();proc=None;tracked=OwnedIdentities();failure=None;started=time.monotonic()
    env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8','OPENBLAS_NUM_THREADS':'1',
         'OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1','PYTHONDONTWRITEBYTECODE':'1'}
    command=[cfg['interpreter'],'-I','-S','-B',str(Path(cfg['cold_directory'])/'cold_worker.py'),
        '--config',str(Path(a.config).resolve()),'--config-sha',a.config_sha,'--output',str(out),'--capability-fd',str(readfd)]
    def bounds():
        os.sched_setaffinity(0,{cpu});resource.setrlimit(resource.RLIMIT_AS,(BOUNDS['address_space_bytes'],)*2)
        resource.setrlimit(resource.RLIMIT_CPU,(BOUNDS['cpu_seconds'],)*2);resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    try:
        with (out/'stdout.log').open('xb') as stdout,(out/'stderr.log').open('xb') as stderr:
            proc=subprocess.Popen(command,env=env,cwd=out,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,
                start_new_session=True,pass_fds=(readfd,),preexec_fn=bounds)
            os.close(readfd);readfd=-1;os.write(writefd,encoded(cap));os.close(writefd);writefd=-1
            identity=process_stat(proc.pid);need(identity is not None,'child disappeared before birth identity')
            tracked[proc.pid]=identity['start_ticks']
            write_new(out/'LAUNCH.json',dict(command=command,environment=env,bounds=BOUNDS,child_identity=identity,parent_identity=parent))
            while proc.poll() is None:
                discover_tree(proc.pid,tracked)
                if time.monotonic()-started>BOUNDS['wall_seconds']:failure='cold_wall_exceeded';break
                time.sleep(0.02)
    except BaseException as error:
        failure='cold_parent_failure:'+type(error).__name__+':'+str(error)
    finally:
        for fd in (readfd,writefd):
            if fd>=0:os.close(fd)
        if proc is not None:
            stop_owned(proc.pid,tracked)
            try:proc.wait(timeout=3)
            except subprocess.TimeoutExpired:failure=failure or 'worker_unreaped'
    remaining=discover_tree(proc.pid,tracked) if proc else {}
    spawn_timer_to_cleanup=time.monotonic()-started
    post=manifest_postflight(cfg['files']);write_new(out/'POSTFLIGHT.json',post)
    result_path=out/'binding/EXACT_COLD_RESULT.json'
    child=json.loads(result_path.read_text()) if result_path.exists() else None
    passed=bool(proc and proc.returncode==0 and not failure and not remaining and post['passed'] and child and child['status']=='PASS_EXACT_M128_NORMAL_COLD_ONLY')
    result=dict(status='PASS_EXACT_M128_COLD_PARENT_ONLY' if passed else 'FAIL_COLD_RETAINED',passed=passed,
        config_sha256=a.config_sha,review_sha256=a.review_sha,approval_sha256=sha(approval_raw),
        returncode=proc.returncode if proc else None,failure=failure,remaining=remaining,
        spawn_timer_to_cleanup_seconds=spawn_timer_to_cleanup,
        spawn_timer_to_postflight_seconds=time.monotonic()-started,resource=BOUNDS,
        wall_limit_scope='Monitor timer begins immediately before spawn setup; 25s check ends at worker exit; cleanup and opaque postflight are separately reported',
        address_space_semantics='Per-process RLIMIT_AS 256MiB, not RSS or process-tree cap',
        cold_only=True,matrix_elf_loaded=False if passed else 'UNKNOWN_FAILURE_NOT_QUALIFIED',numeric_executed=False,
        child_result=file_id(result_path) if result_path.exists() else None)
    write_new(out/'PARENT_RESULT.json',result)
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
