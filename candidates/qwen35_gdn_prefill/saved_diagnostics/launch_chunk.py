"""Single-use bounded actual-only launch; requires an explicitly reviewed plan SHA.

Reuses unchanged repository strict_cleanup for original retained-leader ownership.
No poll/wait occurs before the helper's two complete absence scans. No retry.
RSS/tree/log caps are sampled; address space, CPU and individual files use rlimits.
Audit hooks are accidental-access guards, not a native-code security sandbox.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import stat
import subprocess
import sys
import time
import types

# -I omits the script directory; admit only this pinned helper directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from chunk_case import plan_case

HERE = Path(__file__).resolve().parent


def need(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while block := stream.read(1024 * 1024):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    raw = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
    need(len(raw) <= 4 << 20, 'bounded supervisor record')
    temporary = path.with_suffix(path.suffix + '.tmp')
    need(not path.is_symlink() and not temporary.is_symlink(), 'no output aliases')
    with temporary.open('wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_DIRECTORY | os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def verify(plan):
    for name, pin in plan['inputs'].items():
        path = Path(name)
        need(str(path.resolve(strict=True)) == pin['resolved'], 'input resolution: ' + name)
        before = path.stat()
        need(stat.S_ISREG(before.st_mode) and before.st_size == pin['bytes'] and
             sha(path) == pin['sha256'], 'input bytes: ' + name)
        after = path.stat()
        need((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
             (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
             'input changed while hashing: ' + name)


def helper(plan):
    path = Path(plan['cleanup_helper'])
    raw = path.read_bytes()
    need(hashlib.sha256(raw).hexdigest() == plan['inputs'][str(path)]['sha256'], 'cleanup helper pin')
    module = types.ModuleType('frozen_original_cleanup')
    module.__file__ = str(path)
    module._ADMITTED_SOURCE_SHA256 = hashlib.sha256(raw).hexdigest()
    exec(compile(raw, str(path), 'exec', dont_inherit=True), module.__dict__)
    return module


def readiness(plan):
    mem = int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines()
                   if x.startswith('MemAvailable:'))) * 1024
    fs = os.statvfs(Path(plan['run_directory']).parent)
    disk = fs.f_bavail * fs.f_frsize
    need(mem >= plan['limits']['minimum_host_available_bytes'], 'insufficient current host memory')
    need(disk >= plan['limits']['minimum_disk_available_bytes'], 'insufficient current disk')
    need(plan['cpu'] in os.sched_getaffinity(0), 'selected CPU is no longer allowed')
    duplicates = []
    for path in Path('/proc').glob('[0-9]*/cmdline'):
        if int(path.parent.name) == os.getpid():
            continue
        try:
            args = path.read_bytes().split(b'\0')
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        if plan['child_argv'][-2].encode() in args:
            duplicates.append(int(path.parent.name))
    need(not duplicates, 'existing identical diagnostic child; no duplicate launch: ' + str(duplicates))
    return dict(memavailable_bytes=mem, disk_available_bytes=disk,
                cgroup_path=Path('/proc/self/cgroup').read_text().strip(),
                cgroup_filesystem_available=Path('/sys/fs/cgroup').is_dir(), duplicate_pids=duplicates)


def output_usage(run, plan):
    size = logs = 0
    for n, path in enumerate(run.rglob('*'), 1):
        need(n <= 4096, 'owned output entry cap')
        s = path.lstat()
        need(not stat.S_ISLNK(s.st_mode), 'owned output symlink')
        if stat.S_ISREG(s.st_mode):
            need(s.st_nlink == 1 and s.st_size <= plan['limits']['file_bytes'], 'owned output file cap')
            size += s.st_size
            if path.suffix == '.log':
                logs += s.st_size
    return dict(output_bytes=size, log_bytes=logs)


def observe(run, owner, strict, plan):
    pid = owner['process'].pid
    row = strict._Linux().read(pid)
    need(row is not None and {k: row[k] for k in strict.OWNER_KEYS} == owner['identity'] and
         row['session'] == pid, 'live retained leader identity drift')
    rss = cpu = 0
    hz = os.sysconf('SC_CLK_TCK'); page = os.sysconf('SC_PAGE_SIZE')
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            raw = path.read_text(); fields = raw[raw.rfind(')') + 2:].split()
            if int(fields[2]) == pid:
                need(int(fields[3]) == pid, 'owned process session drift')
                rss += max(0, int(fields[21])) * page
                cpu += sum(int(fields[i]) for i in (11, 12)) / hz
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
    output = output_usage(run, plan)
    progress = None
    p = run / 'actual' / 'progress.json'
    if p.exists():
        try:
            need(p.stat().st_size <= 32 << 20, 'progress file cap')
            value = json.loads(p.read_text())
            commands = value.get('commands', [])
            progress = dict(terminal_count=len(commands), roots_generation=value.get('roots', {}).get('generation'),
                last_phase=commands[-1].get('phase') if commands else None,
                last_role=commands[-1].get('role') if commands else None, mtime_ns=p.stat().st_mtime_ns)
        except (json.JSONDecodeError, FileNotFoundError):
            progress = dict(state='PARTIAL_WRITE_RETRY_NEXT_HEARTBEAT')
    return dict(group_rss_bytes=rss, group_cpu_seconds=cpu, **output, progress=progress)


def execute(plan, plan_sha, start, plan_path):
    stop = start + plan['limits']['outer_wall_seconds']
    selected = plan_case(plan)
    work_stop = stop - selected['cleanup_reserve_seconds']
    run = Path(plan['run_directory'])
    owner = None; observed = None; proof = None; failure = None; strict = None
    created = False
    record = dict(schema=1, status='STARTING', started_utc=datetime.now(timezone.utc).isoformat(),
        plan_sha256=plan_sha, supervisor_pid=os.getpid(), original_stop_monotonic=stop,
        source_commit=plan['source_commit'], limits=plan['limits'],
        automatic_retry=False, rtl_executed=False, numerical_acceptance=False,
        isolated_component_complete_uncompared=False, observed_peak_rss_bytes=0, observed_peak_output_bytes=0)
    signals = (signal.SIGTERM, signal.SIGINT, signal.SIGHUP, signal.SIGALRM)
    old = {sig: signal.getsignal(sig) for sig in signals}
    def interrupted(sig, frame):
        raise InterruptedError('supervisor signal/deadline: ' + str(sig))
    def limits():
        os.sched_setaffinity(0, {plan['cpu']})
        for key, value in ((resource.RLIMIT_AS, plan['limits']['address_space_bytes']),
                           (resource.RLIMIT_CPU, plan['limits']['cpu_seconds']),
                           (resource.RLIMIT_FSIZE, plan['limits']['file_bytes']),
                           (resource.RLIMIT_CORE, 0)):
            resource.setrlimit(key, (value, value))
        signal.pthread_sigmask(signal.SIG_UNBLOCK, set(signals))
    try:
        for sig in signals:
            signal.signal(sig, interrupted)
        signal.setitimer(signal.ITIMER_REAL, max(.001, work_stop - time.monotonic()))
        need(sha(plan_path) == plan_sha, 'launch plan changed')
        verify(plan); record['readiness'] = readiness(plan); strict = helper(plan)
        need(not os.path.lexists(run), 'fresh single-use run directory required')
        run.mkdir(mode=0o700); created = True; (run / 'pycache').mkdir()
        save(run / 'LAUNCH.json', record)
        with (run / 'stdout.log').open('xb') as out, (run / 'stderr.log').open('xb') as err:
            mask = signal.pthread_sigmask(signal.SIG_BLOCK, set(signals))
            try:
                environment = dict(plan['environment'], QWEN35_REVIEWED_PLAN_SHA256=plan_sha)
                child = subprocess.Popen(plan['child_argv'], cwd=plan['repository'], env=environment,
                    stdout=out, stderr=err, start_new_session=True, preexec_fn=limits)
                owner = dict(process=child, identity=None)
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK, mask)
            api = strict._Linux(); boot = api.boot()
            leader, _ = strict._verify_leader(owner, api, None, boot)
            record.update(status='RUNNING', child_identity=dict(leader), boot_id=boot, argv=plan['child_argv'])
            save(run / 'LAUNCH.json', record)
            save(run / 'START.json', dict(leader, boot_id=boot, work_stop_monotonic=work_stop))
            last = -10
            while True:
                now = time.monotonic()
                need(now < work_stop, 'outer work deadline; case-specific reserve for cleanup/receipts')
                observed = os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                sample = observe(run, owner, strict, plan)
                record['observed_peak_rss_bytes'] = max(record['observed_peak_rss_bytes'], sample['group_rss_bytes'])
                record['observed_peak_output_bytes'] = max(record['observed_peak_output_bytes'], sample['output_bytes'])
                record['latest_observation'] = sample
                need(sample['group_rss_bytes'] <= plan['limits']['sampled_rss_bytes'], 'sampled RSS cap')
                need(sample['output_bytes'] < plan['limits']['output_bytes'] - (8 << 20), 'sampled output cap/reserve')
                need(sample['log_bytes'] <= plan['limits']['log_bytes'], 'sampled log cap')
                if now - last >= 5 or observed is not None:
                    record['elapsed_seconds'] = now - start
                    save(run / 'HEARTBEAT.json', record); last = now
                if observed is not None:
                    record['exit_observed_while_unreaped'] = dict(code=observed.si_code, status=observed.si_status)
                    break
                time.sleep(1)
    except BaseException as error:
        failure = type(error).__name__ + ': ' + str(error)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        for sig in signals:
            signal.signal(sig, signal.SIG_IGN)
        if owner is not None:
            try:
                proof = strict.cleanup_owned(owner, stop - 5)
                strict.validate_cleanup_proof(proof, owner=owner, stop=stop - 5)
                save(run / 'CLEANUP.json', owner['strict_cleanup_observation'])
            except BaseException as error:
                proof = None
                failure = (failure or '') + ' cleanup: ' + repr(error)
                if hasattr(error, 'evidence'):
                    save(run / 'CLEANUP_FAILED.json', error.evidence)
        # Cleanup owns its deadline alarm internally. Postflight retains the
        # original outer stop, with two seconds reserved for terminal receipts.
        signal.signal(signal.SIGALRM, interrupted)
        signal.setitimer(signal.ITIMER_REAL, max(.001, stop - 2 - time.monotonic()))
        try:
            need(sha(plan_path) == plan_sha, 'final reviewed plan changed')
            verify(plan)
            record['all_frozen_actual_inputs_unchanged'] = True
        except BaseException as error:
            record['all_frozen_actual_inputs_unchanged'] = False
            failure = (failure or '') + ' final identity: ' + repr(error)
        try:
            need(time.monotonic() < stop - 2, 'postflight deadline')
            summary = json.loads((run / 'actual' / 'summary.json').read_text())
            record['child_status'] = summary.get('status')
            record['terminal_count'] = summary.get('terminal_count')
            record['roots_generation'] = summary.get('roots', {}).get('generation')
            complete = (summary.get('status') == 'ISOLATED_CHUNK_COMPLETE_UNCOMPARED' and
                        record['terminal_count'] == 1 and summary.get('output_elements') == selected['elements'] and
                        (run / 'actual' / 'output.bf16le').is_file())
        except BaseException as error:
            complete = False; record['child_summary_error'] = repr(error)
        natural = bool(observed and observed.si_code == os.CLD_EXITED and observed.si_status == 0)
        try:
            final_usage = output_usage(run, plan) if created else dict(output_bytes=0, log_bytes=0)
            record['final_usage_before_terminal_receipts'] = final_usage
            need(final_usage['output_bytes'] < plan['limits']['output_bytes'] - (8 << 20) and
                 final_usage['log_bytes'] <= plan['limits']['log_bytes'], 'final output/log caps and receipt reserve')
        except BaseException as error:
            failure = (failure or '') + ' final resources: ' + repr(error)
        record.update(status='ISOLATED_CHUNK_COMPLETE_UNCOMPARED' if complete and natural and proof and not failure else 'FAILED',
            isolated_component_complete_uncompared=bool(complete and natural and proof and not failure),
            failure=failure, natural_exit=natural, cleanup_confirmed=proof is not None,
            returncode=None if owner is None else owner['process'].returncode,
            elapsed_seconds=time.monotonic() - start, cleanup_proof=proof)
        if time.monotonic() >= stop:
            record.update(status='FAILED', isolated_component_complete_uncompared=False, failure='ORIGINAL_OUTER_DEADLINE_EXCEEDED')
        signal.setitimer(signal.ITIMER_REAL, max(.001, stop - time.monotonic()))
        if created:
            save(run / 'LAUNCH.json', record); save(run / 'HEARTBEAT.json', record)
        signal.setitimer(signal.ITIMER_REAL, 0)
        for sig, handler in old.items():
            signal.signal(sig, handler)
    print(json.dumps(record, sort_keys=True), flush=True)
    return 0 if record['isolated_component_complete_uncompared'] else 1


def main():
    start = time.monotonic()
    def original_deadline(sig, frame):
        raise TimeoutError('bounded case-specific supervisor deadline')
    signal.signal(signal.SIGALRM, original_deadline)
    signal.setitimer(signal.ITIMER_REAL, 75)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--reviewed-plan-sha256', required=True)
    args = parser.parse_args()
    path = args.plan.resolve(strict=True)
    need(sha(path) == args.reviewed_plan_sha256, 'reviewed plan SHA mismatch')
    plan = json.loads(path.read_text())
    selected = plan_case(plan)
    signal.setitimer(signal.ITIMER_REAL, max(.001, start + selected['outer_seconds'] - time.monotonic()))
    if not args.execute:
        verify(plan)
        print(json.dumps(dict(status='READY_NOT_EXECUTED', readiness=readiness(plan),
            plan_sha256=args.reviewed_plan_sha256, target_exists=Path(plan['run_directory']).exists())))
        signal.setitimer(signal.ITIMER_REAL, 0)
        return 0
    return execute(plan, args.reviewed_plan_sha256, start, path)


if __name__ == '__main__':
    raise SystemExit(main())
