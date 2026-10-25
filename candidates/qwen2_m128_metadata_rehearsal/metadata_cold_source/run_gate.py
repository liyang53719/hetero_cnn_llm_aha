"""Single-use exact M128 metadata-only cold launcher. No execution on import."""
import argparse
import json
import math
import os
from pathlib import Path
import resource
import subprocess
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parent))
from admission import ACTION, SCOPE, RESOURCES, validate
from supervisor import (need, read_checked, file_id, sha, encoded, write_new,
    process_stat, OwnedIdentities, discover_tree, stop_owned, manifest_postflight,
    terminal_output_snapshot, terminal_limit_reason, finalize_terminal_output,
    TreeCpuSamples, artifact_manifest)

WORKER_STATUS = 'PASS_M128_METADATA_COLD_ONLY'


def worker_result_passed(result, config_sha):
    return bool(type(result) is dict and result.get('status') == WORKER_STATUS and
        result.get('passed') is True and result.get('observed_domain_passed') is False and
        result.get('full29_numeric_pass') is False and result.get('hardware_acceptance') is False and
        result.get('actual_terminal_verified') is False and result.get('event_protocol_passed') is False and
        result.get('matrix_elf_loaded') is False and result.get('services_constructed') is False and
        result.get('metadata_persisted') is True and result.get('provider_count') == 14 and
        result.get('provider_bytes') == 94916608 and result.get('commands') == 21 and
        result.get('oracle', {}).get('state') == 'SEALED' and
        result.get('config_sha256') == config_sha)


def reaped_cpu_limit_reason(usage_before, usage_after):
    """Post-exit RUSAGE_CHILDREN delta, not a kernel aggregate CPU quota."""
    user = usage_after.ru_utime - usage_before.ru_utime
    system = usage_after.ru_stime - usage_before.ru_stime
    seconds = user + system
    if any(not math.isfinite(value) or value < 0 for value in (user, system, seconds)):
        return 'terminal_reaped_aggregate_cpu_invalid'
    return 'terminal_reaped_aggregate_cpu_exceeded' if seconds > RESOURCES['cpu_seconds'] else None


def runtime_environment(out):
    return {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
        'HOME': str(out / 'home'), 'TMPDIR': str(out / 'tmp'),
        'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1',
        'NUMEXPR_NUM_THREADS': '1', 'VECLIB_MAXIMUM_THREADS': '1', 'BLIS_NUM_THREADS': '1',
        'PYTHONDONTWRITEBYTECODE': '1', 'HF_HUB_OFFLINE': '1',
        'TRANSFORMERS_OFFLINE': '1', 'HF_DATASETS_OFFLINE': '1',
        'HF_HUB_DISABLE_TELEMETRY': '1', 'DO_NOT_TRACK': '1'}


def child_bounds(cpu):
    os.sched_setaffinity(0, {cpu})
    resource.setrlimit(resource.RLIMIT_AS, (RESOURCES['address_space_bytes'],) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (RESOURCES['cpu_seconds'],) * 2)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def enable_subreaper():
    # Launcher libc only, not the DUT ELF. Not called by preparation/mock tests.
    import ctypes
    libc = ctypes.CDLL(None, use_errno=True)
    need(libc.prctl(36, 1, 0, 0, 0) == 0, 'PR_SET_CHILD_SUBREAPER failed')


def cleanup_worker(proc, tracked, cpu_samples):
    started = time.monotonic()
    until = started + RESOURCES['cleanup_seconds']
    killed = []
    reaped = []
    if proc is None:
        return dict(remaining={}, killed=[], reaped=[], seconds=0, timed_out=False)
    cpu_samples.observe(tracked)
    killed += stop_owned(proc.pid, tracked)
    try:
        proc.wait(timeout=max(0, until - time.monotonic()))
    except subprocess.TimeoutExpired:
        pass
    while time.monotonic() < until:
        active = discover_tree(proc.pid, tracked)
        cpu_samples.observe(tracked)
        try:
            pid, status = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            pid = 0
        if pid:
            reaped.append(dict(pid=pid, wait_status=status))
            continue
        if not active:
            break
        killed += stop_owned(proc.pid, tracked)
        time.sleep(0.02)
    remaining = discover_tree(proc.pid, tracked)
    cpu_samples.observe(tracked)
    return dict(remaining=remaining, killed=sorted(set(killed)), reaped=reaped,
                seconds=time.monotonic() - started,
                timed_out=bool(remaining or proc.returncode is None))


def launch(a):
    need(a.go == 'GO', 'explicit GO required; no environment override')
    overall_started = time.monotonic()
    config_path = Path(a.config).resolve(strict=True)
    config = read_checked(config_path, a.config_sha)
    review_path = Path(a.review).resolve(strict=True)
    review_raw = review_path.read_bytes()
    need(len(review_raw) <= 1048576 and sha(review_raw) == a.review_sha,
         'bounded exact review bytes')
    review = json.loads(review_raw)
    approval_raw = Path(a.approval).resolve(strict=True).read_bytes()
    need(len(approval_raw) <= 16384, 'bounded root approval')
    approval = json.loads(approval_raw)
    validate(config, a.config_sha, review, a.review_sha, approval)
    need(Path(sys.executable).resolve() == Path(config['interpreter']), 'fixed cold-qualified interpreter')
    need(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode and
         not sys.flags.optimize, 'launcher requires exact -I -S -B, no -O')
    need(not any(key.startswith('LD_') for key in os.environ), 'loader overrides forbidden')
    out = Path(a.output).resolve()
    need(out == Path(config['gate_directory']) / approval['run_id'] and not out.exists(),
         'fresh exact approved output directory')
    preflight = manifest_postflight(config['files'])
    preflight['scope'] = 'opaque complete manifest hash before any worker spawn; outside worker timer'
    need(preflight['passed'], 'opaque preflight manifest drift')
    parent = process_stat(os.getpid())
    need(parent is not None, 'live parent birth required')
    parent_argv = [os.fsdecode(x) for x in Path('/proc/self/cmdline').read_bytes().split(b'\0') if x]
    claim_path = Path(config['gate_directory']) / 'EXACT_METADATA_COLD_CLAIM.json'
    ledger = dict(action=ACTION, scope=SCOPE, parent_identity=parent,
        config_sha256=a.config_sha, review_sha256=a.review_sha,
        approval_sha256=sha(approval_raw), output=str(out), run_id=approval['run_id'],
        maximum_invocations=1, no_retry=True, go='GO')
    claim_id = write_new(claim_path, ledger)
    # The claim is permanently consumed even if a subsequent startup step fails.
    out.mkdir(mode=0o700)
    for name in ('home', 'tmp'):
        (out / name).mkdir(mode=0o700)
    write_new(out / 'PREFLIGHT.json', preflight)
    for name, raw in (('REVIEW.json', review_raw), ('APPROVAL.json', approval_raw)):
        with (out / name).open('xb') as stream:
            stream.write(raw)
    cpu = min(os.sched_getaffinity(0))
    cap = dict(ledger, parent_pid=os.getpid(), parent_start_ticks=parent['start_ticks'],
               parent_argv=parent_argv, claim_sha256=claim_id['sha256'], affinity=[cpu])
    cap_raw = encoded(cap)
    need(len(cap_raw) <= 16384, 'bounded launch capability')
    readfd, writefd = -1, -1
    proc = None
    tracked = OwnedIdentities()
    cpu_samples = TreeCpuSamples()
    peak_rss = 0
    failure = None
    worker_started = None
    worker_end = None
    command = None
    cleanup = dict(remaining={}, killed=[], reaped=[], seconds=0, timed_out=False)
    env = runtime_environment(out)
    usage_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    try:
        enable_subreaper()
        readfd, writefd = os.pipe()
        command = [config['interpreter'], '-I', '-S', '-B',
            str(Path(config['gate_directory']) / 'worker.py'),
            '--config', str(config_path), '--config-sha', a.config_sha,
            '--output', str(out), '--cap-fd', str(readfd),
            '--parent-pid', str(os.getpid()), '--parent-start-ticks', str(parent['start_ticks'])]
        with (out / 'stdout.log').open('xb') as stdout, (out / 'stderr.log').open('xb') as stderr:
            worker_started = time.monotonic()
            proc = subprocess.Popen(command, env=env, cwd=out, stdin=subprocess.DEVNULL,
                stdout=stdout, stderr=stderr, start_new_session=True,
                pass_fds=(readfd,), preexec_fn=lambda: child_bounds(cpu))
            os.close(readfd)
            readfd = -1
            identity = process_stat(proc.pid)
            need(identity is not None and identity['ppid'] == parent['pid'],
                 'fresh worker PID/birth identity')
            tracked[proc.pid] = identity['start_ticks']
            need(os.write(writefd, cap_raw) == len(cap_raw), 'complete capability pipe transfer')
            os.close(writefd)
            writefd = -1
            write_new(out / 'LAUNCH.json', dict(command=command, environment=env,
                resources=RESOURCES, worker_identity=identity, parent_identity=parent,
                worker_affinity=[cpu], preflight_outside_worker_timer=True,
                rlimit_cpu_is_per_process_not_aggregate_tree=True))
            while True:
                active = discover_tree(proc.pid, tracked)
                peak_rss = max(peak_rss, sum(row['rss_bytes'] for row in active.values()))
                sampled_cpu = cpu_samples.observe(tracked)
                snapshot = terminal_output_snapshot(out)
                if peak_rss > RESOURCES['tree_rss_bytes']:
                    failure = 'sampled_tree_rss_exceeded'
                elif sampled_cpu > RESOURCES['cpu_seconds']:
                    failure = 'sampled_tree_cpu_exceeded'
                elif time.monotonic() - worker_started > RESOURCES['wall_seconds']:
                    failure = 'worker_wall_exceeded'
                else:
                    failure = terminal_limit_reason(snapshot, RESOURCES)
                returncode = proc.poll()
                if failure or returncode is not None:
                    break
                time.sleep(0.05)
    except BaseException as exc:
        failure = failure or 'launcher_exception:' + type(exc).__name__ + ':' + str(exc)
    finally:
        worker_end = time.monotonic()
        for fd in (readfd, writefd):
            if fd >= 0:
                os.close(fd)
        try:
            cleanup = cleanup_worker(proc, tracked, cpu_samples)
        except BaseException as exc:
            failure = failure or 'cleanup_exception:' + type(exc).__name__ + ':' + str(exc)
            cleanup = dict(remaining={'uncertain': True}, killed=[], reaped=[],
                           seconds=None, timed_out=True)
        if cleanup['timed_out']:
            failure = failure or 'worker_tree_cleanup_timeout'
        if proc is None:
            failure = failure or 'worker_not_started'
    usage_after = resource.getrusage(resource.RUSAGE_CHILDREN)
    final_cpu_samples = cpu_samples.report()
    if final_cpu_samples['sampled_aggregate_cpu_seconds'] > RESOURCES['cpu_seconds']:
        failure = failure or 'terminal_sampled_tree_cpu_exceeded'
    failure = failure or reaped_cpu_limit_reason(usage_before, usage_after)
    postflight = manifest_postflight(config['files'])
    write_new(out / 'POSTFLIGHT.json', postflight)
    result = None
    result_path = out / 'WORKER_RESULT.json'
    try:
        snapshot = terminal_output_snapshot(out)
        failure = failure or terminal_limit_reason(snapshot, RESOURCES)
        raw = result_path.read_bytes()
        need(len(raw) <= 1048576, 'bounded worker result')
        result = json.loads(raw)
        artifacts = artifact_manifest(out)
    except (OSError, ValueError, TypeError) as exc:
        failure = failure or 'terminal_evidence:' + type(exc).__name__ + ':' + str(exc)
        artifacts = {}
        snapshot = None
    passed = bool(proc and proc.returncode == 0 and not failure and not cleanup['remaining'] and
                  postflight['passed'] and worker_result_passed(result, a.config_sha))
    receipt = dict(schema='qwen2-m128-metadata-cold-receipt-v1',
        status=WORKER_STATUS if passed else 'FAIL_M128_METADATA_COLD_RETAINED', passed=passed,
        action=ACTION, scope=SCOPE, observed_domain_passed=False,
        full29_numeric_pass=False, hardware_acceptance=False,
        config_sha256=a.config_sha, review_sha256=a.review_sha,
        approval_sha256=sha(approval_raw), claim_sha256=claim_id['sha256'],
        run_id=approval['run_id'], limit_reason=failure,
        worker_pid=proc.pid if proc else None, worker_returncode=proc.returncode if proc else None,
        worker_reaped=bool(proc and proc.returncode is not None),
        worker_result_status=result.get('status') if type(result) is dict else None,
        tracked_pid_start_ticks=tracked, tracked_identity_rebindings=tracked.rebindings,
        cleanup=cleanup, resources=RESOURCES, peak_sampled_tree_rss_bytes=peak_rss,
        tree_rss_is_hard_cap=False, sampled_tree_cpu=final_cpu_samples,
        cpu_usage_children=dict(user_seconds=usage_after.ru_utime - usage_before.ru_utime,
            system_seconds=usage_after.ru_stime - usage_before.ru_stime,
            post_exit_reaped_aggregate_budget_checked=True,
            reaped_aggregate_limit_seconds=RESOURCES['cpu_seconds'],
            ru_maxrss_bytes_linux=usage_after.ru_maxrss * 1024,
            ru_maxrss_is_aggregate_tree=False),
        per_process_limits=dict(address_space_bytes=RESOURCES['address_space_bytes'],
            cpu_seconds=RESOURCES['cpu_seconds'], includes_threads=True,
            kernel_aggregate_tree_cpu_hard_cap=False, address_space_is_rss=False),
        worker_wall_seconds=worker_end - worker_started if worker_started is not None else None,
        worker_wall_scope='Immediately before Popen through exit/failure observation; cleanup separate; opaque parent pre/post hashes excluded.',
        preflight=preflight, postflight=postflight,
        parent_elapsed_before_finalization_seconds=time.monotonic() - overall_started,
        output_after_postflight=snapshot, log_limit_scope='stdout.log plus stderr.log combined',
        cold_execution_provenance=config['cold_execution_provenance'],
        cold_provenance_is_native_or_numeric_pass=False, legacy_results_inherited=False,
        artifacts=artifacts, no_retry=True)
    seal = dict(schema='qwen2-m128-metadata-cold-completion-v1', status=WORKER_STATUS,
        action=ACTION, scope=SCOPE, observed_domain_passed=False, full29_numeric_pass=False,
        hardware_acceptance=False, config_sha256=a.config_sha, review_sha256=a.review_sha,
        approval_sha256=sha(approval_raw), claim_sha256=claim_id['sha256'],
        actual_terminal_verified=False, event_protocol_passed=False, metadata_persisted=True, matrix_elf_loaded=False,
        cold_provenance_is_native_or_numeric_pass=False, legacy_results_inherited=False,
        artifacts=artifacts)
    receipt, passed = finalize_terminal_output(out, receipt, RESOURCES,
        seal_template=seal if passed else None,
        completion_path=out / 'COMPLETION_SEAL.json' if passed else None)
    print(json.dumps(dict(status=receipt['status'], receipt=str(out / 'RECEIPT.json'),
                          limit_reason=receipt.get('limit_reason')), sort_keys=True))
    return 0 if passed else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('config', 'config-sha', 'review', 'review-sha', 'approval', 'output'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--go', required=True, choices=['GO'])
    return launch(parser.parse_args())


if __name__ == '__main__':
    raise SystemExit(main())
