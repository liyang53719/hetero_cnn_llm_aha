"""One bounded header-only repair diagnosis. No installer, weights or Torch call."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time
import shutil
from fixture_gate import FixtureMismatch, frozen, need, sha, strict_json
from host_checks import host_evidence, available_memory
from validate_source import verify_source
from run_portable import complete_native, ownership_complete
import supervise_multiroot
import header_repair_export as export

HERE=Path(__file__).resolve().parent


def empty_diagnostic():
    return dict(schema='P0_HEADER_DIAGNOSTIC_V1',status='FAIL',failure_point='NOT_STARTED',failure_code='INPUT_PIN',
                http_status=None,final_host=None,response_bytes=None,observed_header_sha256=None,header_sha_equal=None,
                geometry_checked=0,redirect_count=0)


def identity_check(identity,start,repo):
    need(os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('GITHUB_RUN_ATTEMPT')=='1' and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted','PRECHECK_PIN')
    need(set(identity)=={'schema','run_id','source_commit','launch_commit','source_manifest_sha256','nonce','failed_run_id'},'PRECHECK_PIN')
    need(identity['schema']=='P0_HEADER_REPAIR_IDENTITY_V1' and identity['run_id']==int(os.environ['GITHUB_RUN_ID']) and identity['launch_commit']==os.environ['GITHUB_SHA'] and identity['failed_run_id']==export.FAILED_RUN,'PRECHECK_PIN')
    need(identity['source_commit']!=identity['launch_commit'],'PRECHECK_PIN')
    actual=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],env={'PATH':'/usr/bin:/bin'},timeout=10,text=True).strip()
    need(actual==identity['source_commit'],'PRECHECK_PIN')
    need(set(start)=={'schema','run_id','launch_commit','started_monotonic','job_budget_seconds'} and start['schema']=='P0_HEADER_REPAIR_START_V1' and start['run_id']==identity['run_id'] and start['launch_commit']==identity['launch_commit'] and start['job_budget_seconds']==180,'PRECHECK_PIN')
    need(type(start['started_monotonic']) in (int,float) and 0<=start['started_monotonic']<=time.monotonic(),'PRECHECK_PIN')


def run(args):
    cpu_start=time.process_time();used_child=0.;identity=strict_json(args.identity);start=strict_json(args.job_start)
    work=args.output.absolute();expected=Path(os.environ.get('RUNNER_TEMP','/INVALID'))/('p0-header-repair-'+os.environ.get('GITHUB_RUN_ID','INVALID'))
    need(work==expected and not work.exists() and not work.is_symlink(),'PRECHECK_PIN')
    for p in work.parents:need(not p.is_symlink(),'PRECHECK_PIN')
    work.mkdir(mode=0o700);lock=os.open(work/'OWNER.lock',os.O_CREAT|os.O_EXCL|os.O_RDWR|os.O_NOFOLLOW,0o600);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    deadline=start['started_monotonic']+180
    host=dict(schema='P0_HEADER_REPAIR_HOST_V1',architecture=None,python_version=None,python_sha256=None,cpu_affinity_count=None,cpu_evidence_sha256=None,
              initial_free_bytes=None,minimum_free_bytes=None,effective_memory_available_bytes=None,wall_budget_seconds=180,cpu_budget_seconds=60,
              job_wall_seconds=None,job_cpu_seconds=None,rss_budget_bytes=256<<20,tree_budget_bytes=16<<20,stage_status='NOT_REACHED',
              stage_wall_seconds=None,stage_cpu_seconds=None,peak_rss_bytes=None,peak_tree_bytes=None,native_exit=None,cleanup='NOT_REACHED',pipe_eof=None,gzip_finalized=None)
    status='FAIL';reason='PRECHECK_PIN';d=empty_diagnostic()
    try:
        identity_check(identity,start,args.repo)
        pins=verify_source(args.repo,identity['source_manifest_sha256']);frozen()
        evidence,cpu_sha=host_evidence();affinity=evidence['affinity']
        host.update(architecture=evidence['architecture'],python_version=evidence['python_version'],python_sha256=evidence['python_sha256'],cpu_affinity_count=len(affinity),cpu_evidence_sha256=cpu_sha)
        (work/'CPU_EVIDENCE.json').write_text(json.dumps(evidence,sort_keys=True,separators=(',',':'))+'\n')
        (work/'OWNER.json').write_text(json.dumps(dict(identity=identity,pid=os.getpid(),stat=Path('/proc/self/stat').read_text().strip(),boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),deadline_monotonic=deadline,affinity=affinity))+'\n')
        free=shutil.disk_usage(work).free;memory=available_memory();host.update(initial_free_bytes=free,minimum_free_bytes=free,effective_memory_available_bytes=memory)
        need(free>=2<<30 and memory>=((256<<20)+(1<<30)),'RESOURCE_ADMISSION')
        remaining=deadline-time.monotonic();need(remaining>45,'LIMIT')
        pins[str(Path(sys.executable).resolve())]=host['python_sha256']
        caps=dict(wall_seconds=min(120,remaining-45),cleanup_seconds=30,cpu_seconds=20,file_bytes=1<<20,tree_bytes=16<<20,watch_tree_bytes=16<<20,
                  extra_watch_roots=[str(work)],log_bytes=512<<10,raw_log_bytes=1<<20,max_entries=5000,per_process_as_bytes=1<<30,
                  per_process_cpu_seconds=25,rss_bytes=256<<20,min_free_disk_bytes=3*(1<<29),admitted_affinity=affinity,
                  prior_child_cpu_seconds=0.,job_process_cpu_started=cpu_start,job_deadline_monotonic=deadline,job_cpu_budget_seconds=60,
                  rss_telemetry_policy=dict(schema='FULL_PREFILL_RSS_GZIP_V3',raw_bytes=1<<20,compressed_bytes=512<<10,line_bytes=1<<20,verification_wall_seconds=5,verification_cpu_seconds=5))
        env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8','PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1'}
        before=resource.getrusage(resource.RUSAGE_CHILDREN)
        report=supervise_multiroot.execute([str(Path(sys.executable).resolve()),'-S','-B',str(HERE/'header_probe.py'),'--output',str(work/'probe/output'),'--frozen',str(HERE/'FROZEN_P0.json')],
                    work/'probe',work/'probe.lock',caps,env,pins,resource_gate={'min_available_memory':(256<<20)+(1<<30),'min_disk_free':3*(1<<29)})
        after=resource.getrusage(resource.RUSAGE_CHILDREN);used_child=max(after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,report.get('observed_cpu_seconds',0.))
        owned=ownership_complete(report);native=complete_native(report)
        host.update(stage_status='PASS' if native else ('FAIL' if owned else 'INCOMPLETE'),stage_wall_seconds=report.get('elapsed_seconds'),stage_cpu_seconds=used_child+report.get('supervisor_cpu_seconds',0.),
                    peak_rss_bytes=report.get('observed_peak_rss'),peak_tree_bytes=report.get('peak_tree_bytes'),native_exit=report.get('native_exit'),cleanup=export.COMPLETE if owned else 'INCOMPLETE',
                    pipe_eof=report.get('log_capture',{}).get('pipe_eof_observed') is True,gzip_finalized=report.get('log_capture',{}).get('gzip_finalized') is True,
                    minimum_free_bytes=min(free,report.get('minimum_free_disk_bytes',free)),effective_memory_available_bytes=min(memory,report.get('minimum_MemAvailable_bytes',memory)))
        path=work/'probe/output/HEADER_DIAGNOSTIC.json'
        if path.is_file():
            try:d=export.diagnostic(strict_json(path))
            except (ValueError,OSError,KeyError,TypeError):reason='EXPORT_SCHEMA'
        if not owned:status,reason='INCOMPLETE','OWNERSHIP_INCOMPLETE'
        elif native and d['status']=='PASS_HEADER_ONLY':status,reason='PASS_HEADER_ONLY','HEADER_VERIFIED'
        elif reason!='EXPORT_SCHEMA':reason='LIMIT' if report.get('errors') else 'PROBE_FAILURE'
        need(sorted(os.sched_getaffinity(0))==affinity,'CPU_PROOF')
        need(time.monotonic()<deadline and used_child+time.process_time()-cpu_start<=60,'LIMIT')
    except BaseException as exc:
        status='INCOMPLETE' if host['stage_status']=='INCOMPLETE' else 'FAIL'
        value=exc.reason if isinstance(exc,FixtureMismatch) else 'PRECHECK_PIN'
        reason=value if value in ('PRECHECK_PIN','RESOURCE_ADMISSION','CPU_PROOF','ABI','LIMIT','OWNERSHIP_INCOMPLETE','EXPORT_SCHEMA') else 'PRECHECK_PIN'
    host.update(job_wall_seconds=time.monotonic()-start['started_monotonic'],job_cpu_seconds=used_child+time.process_time()-cpu_start)
    result=dict(schema='P0_HEADER_REPAIR_RESULT_V1',candidate_id=export.ID,status=status,reason=reason,source_manifest_sha256=identity['source_manifest_sha256'],failed_run_id=export.FAILED_RUN,run_id=identity['run_id'],
                header_exact=d['header_sha_equal'] is True,metadata_checked=d['geometry_checked'],runtime_installed=False,weights_downloaded=False,reference_executed=False,hardware_executed=False,raw_payloads_uploaded=False,original_failure_cause_proven=False)
    checks=dict(schema='P0_HEADER_REPAIR_CHECKS_V1',expected_header_bytes=38536,expected_header_sha256=export.HEADER_SHA,diagnostic=d)
    remaining=min(5.,deadline-time.monotonic());need(remaining>0 and used_child+time.process_time()-cpu_start<=60,'LIMIT')
    previous=signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(FixtureMismatch('LIMIT')));signal.setitimer(signal.ITIMER_REAL,remaining)
    try:
        export.write_exports(work,result,checks,host)
        need(time.monotonic()<deadline and used_child+time.process_time()-cpu_start<=60,'LIMIT')
        export.seal(work,identity)
        need(time.monotonic()<deadline and used_child+time.process_time()-cpu_start<=60,'LIMIT')
    finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)
    if status!='INCOMPLETE':fcntl.flock(lock,fcntl.LOCK_UN);os.close(lock)
    return 0 if status=='PASS_HEADER_ONLY' else 1


def main():
    p=argparse.ArgumentParser()
    for name in ('repo','identity','job-start','output'):p.add_argument('--'+name,type=Path,required=True)
    return run(p.parse_args())

if __name__=='__main__':sys.exit(main())
