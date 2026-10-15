#!/usr/bin/env python3
"""One supervised fresh attempt; no retries and no unreviewed budget defaults."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import signal
from datetime import datetime, timezone

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from candidates.qwen2_live_fullblock_model_m128 import gates,runner
from candidates.qwen2_live_attention_model_m128_bounded.v2.launch import group_exists,terminate_group
from candidates.qwen2_supervisor_recovery.observation import save, stage, SignalScope


def directory_bytes(path):
    return sum(p.stat().st_size for p in path.rglob('*') if p.is_file()) if path.exists() else 0


def process_group_rss(pid):
    """Linux sampled resident bytes; RLIMIT_AS separately bounds child address space."""
    total=0
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        try:
            stat=(p/'stat').read_text().rsplit(')',1)[1].split()
            if int(stat[2])==pid:
                total+=int((p/'statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE')
        except (OSError,ValueError,IndexError):
            continue
    return total


def supervise(out,data,reference,reviewed_source_manifest):
    started=time.monotonic()
    gates.require_review(reviewed_source_manifest)
    limits=gates.require_budget()
    data_path=gates.data_path(data);gates.reference_path(reference)
    out=Path(out).absolute();gates.fresh_output(out,data_path)
    gates.require(out.parent.is_dir(),'reviewed fullblock work root must already exist')
    paths={n:out.with_name(out.name+s) for n,s in
        (('receipt','.LAUNCH.json'),('stdout','.stdout.log'),('stderr','.stderr.log'),('heartbeat','.HEARTBEAT.json'))}
    gates.require(all(not p.exists() and not p.is_symlink() for p in paths.values()),'single-use fresh launch outputs required')
    deadline=started+limits['outer_wall_seconds'];cutoff=deadline-6;cleanup_deadline=deadline-1
    argv=[sys.executable,'-B',str(Path(runner.__file__).resolve()),'--actual','--data',data,
        '--reference',reference,'--out',str(out),'--reviewed-source-manifest',reviewed_source_manifest]
    receipt=dict(schema=1,status='STARTED',argv=argv,reviewed_source_manifest=reviewed_source_manifest,
        resource_limits=limits,automatic_retry=False,compile_executed=False,old_pass_inherited=False,
        fullblock_pass=False,accepted_final_launch_result=False,peak_sampled_process_group_rss_bytes=0,
        sampled_disk_bytes=0,rss_is_os_hard_cap=False,address_space_has_rlimit=True,
        total_disk_and_log_caps_are_sampled=True,per_file_bytes_has_rlimit=True)
    save(paths['receipt'],receipt)
    failure=None;cleanup_incomplete=False;returncode=None
    last_heartbeat=0.0
    def heartbeat():
        save(paths['heartbeat'],dict(schema=1,diagnostic_only=True,acceptance=False,
            utc=datetime.now(timezone.utc).isoformat(),elapsed_seconds=time.monotonic()-started,
            worker_pid=receipt.get('pid'),supervisor_pid=os.getpid(),
            supervisor_status=receipt['status'],last_stage=stage(out/'PROGRESS.jsonl'),
            peak_rss_bytes=receipt['peak_sampled_process_group_rss_bytes'],
            disk_bytes=receipt['sampled_disk_bytes'],returncode=returncode))
    heartbeat()
    environment=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
    with paths['stdout'].open('x') as stdout,paths['stderr'].open('x') as stderr:
        gates.require(time.monotonic()<cutoff,'whole-run outer admission budget expired')
        child=None
        signals=SignalScope()
        try:
            signals.start()
            child=subprocess.Popen(argv,cwd=ROOT,env=environment,stdout=stdout,stderr=stderr,start_new_session=True)
            receipt['pid']=child.pid
            signals.check()
            save(paths['receipt'],receipt)
            heartbeat()
            while child.poll() is None:
                signals.check()
                rss=process_group_rss(child.pid)
                disk=directory_bytes(out)
                logs=sum(paths[n].stat().st_size for n in ('stdout','stderr'))
                receipt['peak_sampled_process_group_rss_bytes']=max(receipt['peak_sampled_process_group_rss_bytes'],rss)
                receipt['sampled_disk_bytes']=max(receipt['sampled_disk_bytes'],disk)
                if time.monotonic()-last_heartbeat>=10:
                    heartbeat();last_heartbeat=time.monotonic()
                if time.monotonic()>=cutoff:failure='OUTER_WALL_TIMEOUT'
                elif rss>limits['rss_bytes']:failure='SAMPLED_RSS_CAP'
                elif disk>limits['output_bytes']:failure='SAMPLED_OUTPUT_CAP'
                elif logs>limits['log_bytes']:failure='SAMPLED_LOG_CAP'
                if failure:break
                time.sleep(min(limits['poll_seconds'],max(0,cutoff-time.monotonic())))
            signals.check()
            signals.cleaning()
            if failure or group_exists(child.pid):
                returncode,cleanup_incomplete=terminate_group(child,cleanup_deadline=cleanup_deadline)
            else:returncode=child.wait(timeout=max(.001,cleanup_deadline-time.monotonic()))
        except BaseException as error:
            failure=failure or 'SUPERVISOR_EXCEPTION'
            receipt['supervisor_error']=repr(error)
            signals.cleaning()
            if child is not None:
                returncode,cleanup_incomplete=terminate_group(child,cleanup_deadline=cleanup_deadline)
        finally:
            signals.stop()
    result={}
    try:result=json.loads((out/'RESULT.json').read_text())
    except (OSError,ValueError) as error:receipt['result_read_error']=repr(error)
    disk=directory_bytes(out);logs=sum(paths[n].stat().st_size for n in ('stdout','stderr'))
    if time.monotonic()>=deadline:failure=failure or 'OUTER_WALL_TIMEOUT'
    if disk>limits['output_bytes']:failure=failure or 'SAMPLED_OUTPUT_CAP'
    if logs>limits['log_bytes']:failure=failure or 'SAMPLED_LOG_CAP'
    if cleanup_incomplete:failure=failure or 'PROCESS_GROUP_CLEANUP_INCOMPLETE'
    if failure:
        result.update(status='FAILED',failure_kind=failure,acceptance_sealed=False,
            official_observed_node_pass=False,fullblock_pass=False,cleanup_incomplete=cleanup_incomplete)
        if out.is_dir():save(out/'RESULT.json',result)
    passed=not failure and returncode==0 and result.get('acceptance_sealed') is True and \
        result.get('status')=='PASS_M128_OFFICIAL_OBSERVED_FULLBLOCK_PUBLIC21' and result.get('whole_block_terminal') is True
    receipt.update(status='PASS' if passed else 'FAILED',returncode=returncode,failure_kind=failure,
        elapsed_seconds=time.monotonic()-started,cleanup_incomplete=cleanup_incomplete,
        child_status=result.get('status'),acceptance_sealed=passed,fullblock_pass=passed,
        accepted_final_launch_result=result.get('whole_block_terminal',False),
        final_output_bytes=disk,final_log_bytes=logs)
    save(paths['receipt'],receipt);heartbeat();print(json.dumps(receipt,sort_keys=True),flush=True)
    return 0 if passed else 1


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--actual',action='store_true')
    for name in ('data','reference','out','reviewed-source-manifest'):parser.add_argument('--'+name)
    args=parser.parse_args(argv)
    values=(args.data,args.reference,args.out,args.reviewed_source_manifest)
    if not args.actual:
        gates.require(all(v is None for v in values),'actual arguments require --actual')
        return runner.main([])
    gates.require(all(v is not None for v in values),'actual requires paths and independently reviewed exact manifest')
    return supervise(args.out,args.data,args.reference,args.reviewed_source_manifest)


if __name__=='__main__':raise SystemExit(main())
