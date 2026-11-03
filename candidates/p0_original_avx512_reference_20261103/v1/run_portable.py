#!/usr/bin/env python3
"""One isolated CI job, one original AVX512 reference attempt, no DUT or EDA entrypoint."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import platform
import resource
import signal
import subprocess
import sys
import time
import uuid
import shutil
from fixture_gate import FixtureMismatch, frozen, sha, strict_json, need, FROZEN_SHA256
from host_checks import available_memory, host_evidence, admit_avx512
from validate_source import verify_source, RELATIVE
from safe_export import STAGE_BUDGETS, CANDIDATE_ID, COMPLETE_CLEANUP, write_exports, validate_exports, REASONS
import supervise_multiroot
from export_seal import seal_export

HERE = Path(__file__).resolve().parent
GIB = 1 << 30
MIB = 1 << 20
AS = {'runtime':4*GIB, 'weights':2*GIB, 'reference':8*GIB, 'rope':4*GIB, 'finalize':2*GIB}


def initial_stage(name):
    wall, cpu, rss, disk = STAGE_BUDGETS[name]
    return dict(name=name, status='NOT_REACHED', wall_seconds=None, cpu_seconds=None,
                peak_rss_bytes=None, disk_bytes=None, wall_budget_seconds=wall,
                cpu_budget_seconds=cpu, rss_budget_bytes=rss, disk_budget_bytes=disk,
                native_exit=None, cleanup='NOT_REACHED', pipe_eof='NOT_REACHED', gzip_finalized='NOT_REACHED')


def complete_native(report):
    return (report.get('native_exit') == 0 and report.get('errors') == [] and
            report.get('status') == 'PASS_PROCESS_ONLY' and
            (report.get('cleanup_proof') or {}).get('status') == COMPLETE_CLEANUP and
            report.get('observed_remaining') == [] and
            report.get('log_capture', {}).get('pipe_eof_observed') is True and
            report.get('log_capture', {}).get('gzip_finalized') is True and
            report.get('reader_join_barrier', {}).get('complete') is True and
            report.get('rss_telemetry', {}).get('all_written_bytes_verified') is True)


def ownership_complete(report):
    return ((report.get('cleanup_proof') or {}).get('status') == COMPLETE_CLEANUP and
            report.get('observed_remaining') == [] and
            report.get('reader_join_barrier', {}).get('complete') is True and
            report.get('log_capture', {}).get('pipe_eof_observed') is True and
            report.get('log_capture', {}).get('gzip_finalized') is True)


def stage_summary(name, report, charged):
    row = initial_stage(name)
    cleanup = (report.get('cleanup_proof') or {}).get('status') == COMPLETE_CLEANUP
    row.update(status='PASS' if complete_native(report) else ('FAIL' if ownership_complete(report) else 'INCOMPLETE'),
               wall_seconds=report.get('elapsed_seconds'), cpu_seconds=charged,
               peak_rss_bytes=report.get('observed_peak_rss'), disk_bytes=report.get('peak_stage_tree_bytes'),
               native_exit=report.get('native_exit'), cleanup=COMPLETE_CLEANUP if cleanup else 'INCOMPLETE',
               pipe_eof='COMPLETE' if report.get('log_capture', {}).get('pipe_eof_observed') is True else 'INCOMPLETE',
               gzip_finalized='COMPLETE' if report.get('log_capture', {}).get('gzip_finalized') is True else 'INCOMPLETE')
    wall, cpu, rss, disk = STAGE_BUDGETS[name]
    if row['status'] == 'PASS' and not all(v is not None and v <= limit for v, limit in zip((row['wall_seconds'], charged, row['peak_rss_bytes'], row['disk_bytes']), (wall, cpu, rss, disk))):
        row['status'] = 'FAIL'
    return row


def check_identity(identity, job_start, repo):
    need(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('GITHUB_RUN_ATTEMPT') == '1', 'PRECHECK_PIN')
    need(os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted', 'RESOURCE_ADMISSION')
    fields = {'schema', 'run_id', 'source_commit', 'launch_commit', 'source_manifest_sha256', 'nonce', 'default_failed_run_id'}
    need(set(identity) == fields and identity['schema'] == 'P0_AVX512_ONE_SHOT_IDENTITY_V1', 'PRECHECK_PIN')
    need(type(identity['default_failed_run_id']) is int and identity['default_failed_run_id'] == 41734412224, 'PRECHECK_PIN')
    need(identity['run_id'] == int(os.environ['GITHUB_RUN_ID']) and identity['launch_commit'] == os.environ['GITHUB_SHA'], 'PRECHECK_PIN')
    need(identity['source_commit'] != identity['launch_commit'], 'PRECHECK_PIN')
    actual = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], env={'PATH':'/usr/bin:/bin'}, timeout=10, text=True).strip()
    need(actual == identity['source_commit'], 'PRECHECK_PIN')
    need(set(job_start) == {'schema', 'run_id', 'launch_commit', 'started_monotonic', 'job_budget_seconds'}, 'PRECHECK_PIN')
    need(job_start['schema'] == 'P0_AVX512_JOB_START_V1' and job_start['run_id'] == identity['run_id'] and job_start['launch_commit'] == identity['launch_commit'] and job_start['job_budget_seconds'] == 3600, 'PRECHECK_PIN')
    need(type(job_start['started_monotonic']) in (float, int) and 0 <= job_start['started_monotonic'] <= time.monotonic(), 'PRECHECK_PIN')


def run(args):
    process_cpu_start = time.process_time()
    child_cpu = 0.0
    identity = strict_json(args.identity)
    job_start = strict_json(args.job_start)
    candidate_id = CANDIDATE_ID
    repo = args.repo.absolute()
    work = args.output.absolute()
    expected_root = Path(os.environ.get('RUNNER_TEMP', '/INVALID')) / ('p0-original-avx512-' + os.environ.get('GITHUB_RUN_ID', 'INVALID'))
    need(work == expected_root and not work.exists() and not work.is_symlink(), 'PRECHECK_PIN')
    for parent in work.parents:
        need(not parent.is_symlink(), 'PRECHECK_PIN')
    work.mkdir(mode=0o700)
    (work / 'runs').mkdir()
    lock = os.open(work / 'OWNER.lock', os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    stages = {name:initial_stage(name) for name in STAGE_BUDGETS}
    host = dict(schema='P0_PORTABLE_REFERENCE_HOST_V1', architecture=None, python_implementation=None,
                python_version=None, python_sha256=None, cpu_affinity_count=None, cpu_evidence_sha256=None,
                isa={k:None for k in ('sse2','avx','avx2','avx512f')}, requested_capability='avx512',
                observed_capability=None, requested_threads=4, observed_threads=None, requested_interop=1,
                observed_interop=None, initial_free_bytes=None, minimum_free_bytes=None, mem_available_bytes=None,
                stages=list(stages.values()), job_wall_seconds=None, job_cpu_seconds=None,
                job_wall_budget_seconds=3600, job_cpu_budget_seconds=3600)
    status, reason, runtime_sha = 'FAIL', 'PRECHECK_PIN', None
    runtime = work / 'runs/runtime/output'
    weights = work / 'runs/weights/output'
    reference = work / 'runs/reference/output'
    rope = work / 'runs/rope/output'
    affinity = None
    deadline = job_start['started_monotonic'] + 3600
    pins = {}
    stage_name = None
    try:
        check_identity(identity, job_start, repo)
        pins = verify_source(repo, identity['source_manifest_sha256'])
        f = frozen()
        evidence, cpu_sha = host_evidence()
        affinity = evidence['affinity']
        host.update({k:evidence[k] for k in ('architecture','python_implementation','python_version','python_sha256')})
        host.update(cpu_affinity_count=len(affinity), cpu_evidence_sha256=cpu_sha,
                    isa={k:k in evidence['flags_intersection'] for k in host['isa']})
        admit_avx512(evidence)
        (work / 'CPU_EVIDENCE.json').write_text(json.dumps(evidence, sort_keys=True, separators=(',', ':')) + '\n')
        owner = dict(schema='P0_AVX512_OWNED_ROOT_V1', candidate_id=candidate_id, run_id=identity['run_id'],
                     source_commit=identity['source_commit'], launch_commit=identity['launch_commit'],
                     repair_lineage={key:identity[key] for key in ('default_failed_run_id',) if key in identity},
                     pid=os.getpid(), process_stat=Path('/proc/self/stat').read_text().strip(),
                     boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                     nonce=uuid.uuid4().hex, job_started_monotonic=job_start['started_monotonic'],
                     deadline_monotonic=deadline, exact_affinity=affinity, old_owner_resources_borrowed=False)
        (work / 'OWNER.json').write_text(json.dumps(owner) + '\n')
        host['initial_free_bytes'] = host['minimum_free_bytes'] = shutil.disk_usage(work).free
        host['mem_available_bytes'] = available_memory()
        need(host['initial_free_bytes'] >= 8*GIB and host['mem_available_bytes'] >= 4*GIB, 'RESOURCE_ADMISSION')
        pins[str(Path(sys.executable).resolve())] = host['python_sha256']
        env = {'PATH':'/usr/bin:/bin', 'LANG':'C.UTF-8', 'LC_ALL':'C.UTF-8', 'PYTHONDONTWRITEBYTECODE':'1',
               'PYTHONNOUSERSITE':'1', 'ATEN_CPU_CAPABILITY':'avx512', 'OMP_NUM_THREADS':'4',
               'MKL_NUM_THREADS':'4', 'OPENBLAS_NUM_THREADS':'4', 'NUMEXPR_NUM_THREADS':'4',
               'PIP_CONFIG_FILE':'/dev/null', 'PIP_NO_INPUT':'1', 'HF_HUB_OFFLINE':'1', 'TRANSFORMERS_OFFLINE':'1'}
        def launch(name, argv):
            nonlocal child_cpu, stage_name
            stage_name = name
            wall, cpu, rss, tree = STAGE_BUDGETS[name]
            need(sorted(os.sched_getaffinity(0)) == affinity, 'CPU_PROOF')
            need(available_memory() >= rss+GIB and shutil.disk_usage(work).free >= 3*GIB//2, 'RESOURCE_ADMISSION')
            remaining = deadline-time.monotonic()
            cpu_remaining = 3600-child_cpu-(time.process_time()-process_cpu_start)
            need(remaining > 45 and cpu_remaining > 5, 'LIMIT')
            caps = dict(wall_seconds=min(wall-40, remaining-45), cleanup_seconds=30,
                        cpu_seconds=min(cpu-1, cpu_remaining-5), file_bytes=(128*MIB if name in ('reference','rope') else 2*GIB),
                        tree_bytes=tree, watch_tree_bytes=6*GIB, extra_watch_roots=[str(work)],
                        log_bytes=16*MIB, raw_log_bytes=32*MIB, max_entries=150000,
                        per_process_as_bytes=AS[name], per_process_cpu_seconds=max(1,int(min(cpu,cpu_remaining))),
                        rss_bytes=rss, min_free_disk_bytes=3*GIB//2, admitted_affinity=affinity,
                        prior_child_cpu_seconds=child_cpu, job_process_cpu_started=process_cpu_start,
                        job_deadline_monotonic=deadline,
                        rss_telemetry_policy=dict(schema='FULL_PREFILL_RSS_GZIP_V3', raw_bytes=32*MIB,
                        compressed_bytes=16*MIB, line_bytes=MIB, verification_wall_seconds=5, verification_cpu_seconds=5))
            before = resource.getrusage(resource.RUSAGE_CHILDREN)
            report = supervise_multiroot.execute(argv, work/'runs'/name, work/('stage-'+name+'.lock'), caps, env, pins,
                                                resource_gate={'min_available_memory':rss+GIB, 'min_disk_free':3*GIB//2})
            after = resource.getrusage(resource.RUSAGE_CHILDREN)
            waited = (after.ru_utime+after.ru_stime)-(before.ru_utime+before.ru_stime)
            used = max(waited, report.get('observed_cpu_seconds', 0.0))
            child_cpu += used
            charged = used+report.get('supervisor_cpu_seconds', 0.0)
            stages[name] = stage_summary(name, report, charged)
            host['minimum_free_bytes'] = min(host['minimum_free_bytes'], report.get('minimum_free_disk_bytes', host['minimum_free_bytes']))
            host['mem_available_bytes'] = min(host['mem_available_bytes'], report.get('minimum_MemAvailable_bytes', host['mem_available_bytes']))
            if stages[name]['status'] != 'PASS':
                failure = work/'runs'/name/'output/FAILURE.json'
                cause = {'runtime':'INSTALL','weights':'WEIGHT_HASH','reference':'REFERENCE_HASH','rope':'ROPE_HASH','finalize':'PRECHECK_PIN'}[name]
                if failure.is_file():
                    try:
                        value = strict_json(failure)
                        if value.get('reason') in REASONS:
                            cause = value['reason']
                    except (ValueError, OSError):
                        pass  # A torn private failure record is never evidence of success.
                if report.get('errors') and not failure.is_file():
                    cause = 'RESOURCE_ADMISSION' if any(text.endswith(('locked memory gate','locked disk gate','RESOURCE_ADMISSION')) for text in report['errors'] if type(text) is str) else 'LIMIT'
                incomplete = not ownership_complete(report)
                if incomplete and not failure.is_file():
                    cause = 'OWNERSHIP_INCOMPLETE'
                error = FixtureMismatch(cause)
                error.incomplete = incomplete
                raise error
            need(time.monotonic() < deadline and child_cpu+time.process_time()-process_cpu_start <= 3600, 'LIMIT')
            need(sorted(os.sched_getaffinity(0)) == affinity, 'CPU_PROOF')
        py = str(Path(sys.executable).resolve())
        launch('runtime',[py,'-S','-B',str(HERE/'prepare_runtime.py'),'--output',str(runtime),'--frozen',str(HERE/'FROZEN_P0.json')])
        runtime_sha = sha(runtime/'RUNTIME_RECEIPT.json')
        runtime_receipt = strict_json(runtime/'RUNTIME_RECEIPT.json')
        host.update(observed_capability=runtime_receipt['observed_capability'], observed_threads=runtime_receipt['threads'], observed_interop=runtime_receipt['interop_threads'])
        need(runtime_receipt['schema'] == 'P0_AVX512_FRESH_RUNTIME_V1' and host['observed_capability'] == 'AVX512' and host['observed_threads'] == 4 and host['observed_interop'] == 1, 'CPU_PROOF')
        pins[str(runtime/'RUNTIME_RECEIPT.json')] = runtime_sha
        pins[str(runtime/'python')] = sha(runtime/'python')
        pins[str(runtime/'SOURCE_SIDECAR.json')] = f['runtime_sidecar']['sha256']
        launch('weights',[py,'-S','-B',str(HERE/'acquire_weights.py'),'--output',str(weights),'--frozen',str(HERE/'FROZEN_P0.json')])
        launch('reference',[str(runtime/'python'),str(HERE/'run_reference.py'),'--profile','0','--payload',str(weights),'--config',str(HERE/'config.json'),
               '--runtime-receipt',str(runtime/'RUNTIME_RECEIPT.json'),'--runtime-receipt-sha256',runtime_sha,
               '--runtime-source-pins',str(runtime/'SOURCE_SIDECAR.json'),'--runtime-source-pins-sha256',f['runtime_sidecar']['sha256'],
               '--output',str(reference),'--execute-reviewed'])
        rr = strict_json(reference/'RESULT.json')
        need(rr['affinity'] == affinity and rr['observed_dispatch'] == 'AVX512' and rr['actual_threads'] == 4 and rr['actual_interop'] == 1, 'CPU_PROOF')
        launch('rope',[str(runtime/'python'),str(HERE/'generate_p0_rope.py'),'--config',str(HERE/'config.json'),'--reference',str(reference),'--output',str(rope),'--site',str(runtime/'site-packages')])
        need(strict_json(rope/'RESULT.json')['affinity'] == affinity, 'CPU_PROOF')
        launch('finalize',[py,'-S','-B',str(HERE/'finalize.py'),'--repo',str(repo),'--work',str(work),'--output',str(work/'runs/finalize/output'),
              '--source-sha256',identity['source_manifest_sha256'],'--runtime-sha256',runtime_sha])
        status, reason = 'PASS_EXACT_VISIBLE_FIXTURE', None
    except BaseException as exc:
        reason = exc.reason if isinstance(exc, FixtureMismatch) else 'PRECHECK_PIN'
        status = 'INCOMPLETE' if reason == 'OWNERSHIP_INCOMPLETE' or getattr(exc, 'incomplete', False) else 'FAIL'
    # Never continue calculations after a failure. Export reconstruction is metadata-only.
    host['stages'] = list(stages.values())
    checks = {}
    metadata_valid = True
    for root in (reference, rope):
        p = root/'CHECKS_INTERNAL.json'
        if p.is_file():
            try:
                partial = strict_json(p)
                need(type(partial) is dict and not (set(partial) & set(checks)), 'EXPORT_SCHEMA')
                checks.update(partial)
            except (ValueError, OSError):
                metadata_valid = False
                break
    wc = dict(checked=0, mismatch_count=0)
    if (weights/'WEIGHT_CHECKS.json').is_file():
        try:
            wc = strict_json(weights/'WEIGHT_CHECKS.json')
            need(set(wc) == {'schema','checked','mismatch_count'} and wc['schema'] == 'P0_WEIGHT_CHECKS_V1' and type(wc['checked']) is int and 0 <= wc['checked'] <= 12 and type(wc['mismatch_count']) is int and 0 <= wc['mismatch_count'] <= 1, 'EXPORT_SCHEMA')
        except (ValueError, OSError, KeyError, TypeError):
            wc = dict(checked=0, mismatch_count=0)
            metadata_valid = False
    if not metadata_valid and status == 'PASS_EXACT_VISIBLE_FIXTURE':
        status, reason = 'FAIL', 'EXPORT_SCHEMA'
    f = frozen()
    expected = dict(f['frozen_fixture']['tensor_records'])
    expected['rope1024'] = f['frozen_fixture']['rope1024']
    rows = []
    for name, pin in expected.items():
        source = checks.get(name)
        row = dict(name=name,status='NOT_REACHED',expected_bytes=pin['bytes'],observed_bytes=None,
                   expected_sha256=pin['sha256'],observed_sha256=None,shape_equal=None,dtype_equal=None)
        if source is not None:
            # Only these safe typed fields, never copy arbitrary receipt keys.
            for key in ('status','observed_bytes','observed_sha256','shape_equal','dtype_equal'):
                row[key] = source[key]
        rows.append(row)
    mismatch = next((r['name'] for r in rows if r['status']=='MISMATCH'),None)
    result = dict(schema='P0_PORTABLE_REFERENCE_RESULT_V1',candidate_id=candidate_id,status=status,reason=reason,
                  candidate_source_sha256=identity['source_manifest_sha256'],frozen_manifest_sha256=FROZEN_SHA256,
                  runtime_receipt_sha256=runtime_sha,weight_expected=12,weight_checked=wc['checked'],tensor_expected=25,
                  tensor_checked=sum(r['status']!='NOT_REACHED' for r in rows),first_mismatch_name=mismatch,
                  all_visible_exact=all(r['status']=='PASS' for r in rows),hardware_executed=False,dut_numerical_pass=False,
                  raw_payloads_uploaded=False,internal_op_order_proven=False)
    check_record = dict(schema='P0_PORTABLE_REFERENCE_CHECKS_V1',frozen_manifest_sha256=FROZEN_SHA256,
                        weight_checked=wc['checked'],weight_mismatch_count=wc['mismatch_count'],checks=rows)
    # Final export is bounded by both the original job deadline and a five-second local timer.
    host['job_wall_seconds'] = time.monotonic()-job_start['started_monotonic']
    host['job_cpu_seconds'] = child_cpu+time.process_time()-process_cpu_start
    remaining = min(5.0, deadline-time.monotonic())
    need(remaining > 0 and child_cpu+time.process_time()-process_cpu_start <= 3600, 'LIMIT')
    previous = signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(FixtureMismatch('LIMIT')))
    signal.setitimer(signal.ITIMER_REAL, remaining)
    try:
        write_exports(work/'export', result, check_record, host, HERE/'FROZEN_P0.json')
        need(time.monotonic() < deadline and child_cpu+time.process_time()-process_cpu_start <= 3600, 'LIMIT')
        seal_export(work, identity, status, reason, time.monotonic()-job_start['started_monotonic'],
                    child_cpu+time.process_time()-process_cpu_start)
        need(time.monotonic() < deadline and child_cpu+time.process_time()-process_cpu_start <= 3600, 'LIMIT')
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,previous)
    if status != 'INCOMPLETE':
        fcntl.flock(lock, fcntl.LOCK_UN)
        os.close(lock)
    return 0 if status == 'PASS_EXACT_VISIBLE_FIXTURE' else 1


def main():
    ap = argparse.ArgumentParser()
    for name in ('repo','identity','job-start','output'):
        ap.add_argument('--'+name, type=Path, required=True)
    args=ap.parse_args()
    return run(args)

if __name__ == '__main__':
    sys.exit(main())
