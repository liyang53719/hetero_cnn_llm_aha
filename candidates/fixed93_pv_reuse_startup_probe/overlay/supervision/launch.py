"""Prepared sole fullblock launcher. Default: real source-only preflight, not actual.

Only explicit new root source/cold+budget+scalar authority permits one child.
The original public WNOWAIT observation/cleanup implementation is reused exactly.
"""
import argparse
import json
import os
from pathlib import Path
import resource
import signal
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate import (HERE, CANDIDATE, OWNED, OUTPUT, CONTRACT, CLEANUP_SECONDS,
                  POST_SECONDS, need, read_budget, preflight, actual_gate,
                  parent_identity, free_space, strict_json, read_checked)


def interrupted(*_):
    raise TimeoutError('shared wholeblock launch deadline')


def terminal(adapter, state, diagnostics, started, deadline):
    """Whole-scope terminal check, also repeated after the final receipt write."""
    files = adapter.owned_inventory(OWNED)
    rss = adapter.rss_high_water()
    need(rss['supervisor_maxrss_bytes'] <= adapter.RSS_BYTES and
         rss['child_cumulative_maxrss_bytes'] <= adapter.RSS_BYTES, 'terminal RSS lower-bound excess')
    cpu = adapter.cpu_usage()
    now = time.monotonic()
    need(cpu <= adapter.WHOLE_SECONDS and now < deadline, 'whole supervisor+child CPU/wall excess')
    need(not state.get('tree', {}).get('ownership_uncertain', False), 'sticky ownership uncertainty')
    need(not state.get('terminal_live_descendant_pids'), 'live descendants at natural leader exit')
    need(diagnostics.get('cleanup_confirmed') is True, 'cleanup not confirmed')
    return dict(whole_owned_files=files, rusage_maxrss=rss, whole_cpu_seconds=cpu,
                wall_seconds=now - started, sampled_tree_rss_bytes=state.get('peak_rss_bytes', 0))


def main(argv=None):
    started = time.monotonic()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest-sha', required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--preflight', action='store_true')
    mode.add_argument('--actual', action='store_true')
    parser.add_argument('--admission-sha')
    parser.add_argument('--budget-sha')
    args = parser.parse_args(argv)
    if not args.actual:
        need(args.admission_sha is None and args.budget_sha is None,
             'preflight does not accept or consume actual authority')
        print(json.dumps(preflight(args.manifest_sha)[0], sort_keys=True))
        return 0
    # These exact reviewed bytes are read before any mkdir, child or DUT import.
    # started and absolute process CPU cover this bootstrap and all preflight too.
    budget = read_budget(args.budget_sha)
    deadline = started + budget['outer_wall_seconds']
    work_stop = min(started + budget['inner_wall_seconds'], deadline - CLEANUP_SECONDS - POST_SECONDS)
    resource.setrlimit(resource.RLIMIT_CPU, (budget['outer_wall_seconds'],) * 2)
    resource.setrlimit(resource.RLIMIT_AS, (budget['rss_bytes'],) * 2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (budget['file_bytes'],) * 2)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    allowed = os.sched_getaffinity(0)
    need(bool(allowed), 'nonempty inherited CPU affinity required')
    os.sched_setaffinity(0, {min(allowed)})
    need(signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK, []) and
         signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'unblocked unowned deadline required')
    previous_alarm = signal.signal(signal.SIGALRM, interrupted)
    previous_term = signal.signal(signal.SIGTERM, interrupted)
    adapter = None
    receipt = None
    state, diagnostics = {}, {}
    try:
        signal.setitimer(signal.ITIMER_REAL, max(.001, deadline - time.monotonic()))
        declaration, manifest, runtime, checked_budget, report = actual_gate(
            args.manifest_sha, args.admission_sha, args.budget_sha)
        need(checked_budget == budget and time.monotonic() < work_stop,
             'admission changed/exhausted the whole-entry budget')
        initial_free_bytes = free_space(budget)
        import supervisor_adapter as adapter
        adapter.configure(budget)
        state['reviewed_projection_hashes'] = report['supervision_projection_hashes']
        # A fresh owned root is itself an irrevocable once marker. The child
        # creates CONSUMED.json through admission.py; no parent manufactures it.
        OWNED.parent.mkdir(mode=0o700, exist_ok=True)
        OWNED.mkdir(mode=0o700, exist_ok=False)
        (OWNED / 'tmp').mkdir(mode=0o700)
        receipt = OWNED / 'LAUNCH.json'
        lease = dict(parent=parent_identity(os.getpid()), contract=CONTRACT,
                     source_manifest_sha256=args.manifest_sha, admission_sha256=args.admission_sha,
                     budget_sha256=args.budget_sha, out=str(OUTPUT),
                     whole_deadline=deadline, work_stop=work_stop, consumed_by_child=False)
        adapter.checked_save(OWNED / 'LEASE.json', lease, OWNED)
        adapter.checked_save(receipt, dict(status='STARTED_ONE_STARTUP_PROBE_PROCESS',
            source_manifest_sha256=args.manifest_sha, admission_sha256=args.admission_sha,
            budget_sha256=args.budget_sha, actual_arithmetic_accepted=False,
            limits=adapter.fixed_limits()), OWNED)
        environment = dict(PATH='/usr/bin:/bin', HOME=str(OWNED / 'tmp'),
            TMPDIR=str(OWNED / 'tmp'), LANG='C', LC_ALL='C', TZ='UTC',
            OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1',
            PYTHONDONTWRITEBYTECODE='1', FIXED93_FULLBLOCK_PARENT_PID=str(os.getpid()),
            QWEN2_FIXED93_ADMISSION_SHA256=args.admission_sha,
            FIXED93_FULLBLOCK_SOURCE_SHA256=args.manifest_sha,
            FIXED93_FULLBLOCK_BUDGET_SHA256=args.budget_sha)
        command = [sys.executable, '-I', '-S', '-B', str(HERE / 'worker.py'),
                   '--manifest-sha', args.manifest_sha, '--admission-sha', args.admission_sha,
                   '--budget-sha', args.budget_sha, '--deadline', str(work_stop)]
        with (OWNED / 'stdout.log').open('xb') as stdout, (OWNED / 'stderr.log').open('xb') as stderr:
            record, raw_log, usage = adapter.run_admitted(
                command, CANDIDATE, OWNED / 'supervisor', environment, OWNED, stdout, stderr,
                deadline, dict(handler=interrupted, deadline=deadline), 0.0, state, diagnostics,
                work_stop=work_stop)
        need(record.get('status') == 'PASS' and record.get('exit_code') == 0 and
             record.get('anchor_confirmed') is True and record.get('reaped') is True and
             record.get('group_state') == 'absent' and record.get('cleanup_confirmed') is True,
             'terminal process/group cleanup not confirmed')
        consumed = strict_json(read_checked(OWNED / 'CONSUMED.json', cap=32768))
        leader = state.get('tree', {}).get('leader')
        need(type(leader) is tuple and len(leader) == 2, 'sampled child identity missing')
        need(consumed.get('parent') == lease['parent'] and
             consumed.get('source_manifest_sha256') == args.manifest_sha and
             consumed.get('admission_sha256') == args.admission_sha and
             consumed.get('child') == dict(pid=leader[0], start_ticks=leader[1]) and
             leader[0] == record.get('pid'),
             'terminal receipt missing exact child consumption')
        final = terminal(adapter, state, diagnostics, started, deadline)
        # Process supervision does not certify numerical/model correspondence.
        adapter.checked_save(receipt, dict(status='PASS_STARTUP_PROBE_PROCESS_SUPERVISION_ONLY',
            source_manifest_sha256=args.manifest_sha, admission_sha256=args.admission_sha,
            budget_sha256=args.budget_sha, returncode=0, cleanup_confirmed=True,
            limits=adapter.fixed_limits(), projection_hashes=state['projection_hashes'],
            initial_free_bytes=initial_free_bytes, diagnostics=diagnostics,
            actual_output=str(OUTPUT), actual_arithmetic_accepted=False,
            independent_actual_review_required=True, M128_acceptance=False, RTL=False,
            **final), OWNED)
        terminal(adapter, state, diagnostics, started, deadline)
        return 0
    except BaseException as error:
        if receipt is not None and adapter is not None:
            try:
                adapter.checked_save(receipt, dict(status='FAIL_STARTUP_PROBE_PROCESS_SUPERVISION',
                    failure_type=type(error).__name__, failure=str(error)[:2048],
                    cleanup_confirmed=diagnostics.get('cleanup_confirmed') is True and
                        not state.get('tree', {}).get('ownership_uncertain', False),
                    ownership_uncertain=state.get('tree', {}).get('ownership_uncertain', False),
                    diagnostics=diagnostics, source_manifest_sha256=args.manifest_sha,
                    budget_sha256=args.budget_sha, actual_arithmetic_accepted=False,
                    M128_acceptance=False, automatic_retry=False), OWNED)
            except BaseException:
                # Preserve every original receipt even if no fail receipt fits.
                pass
        if receipt is None:
            # A rejected pre-spawn admission has no owned invocation yet.
            # Once owned execution begins, all diagnostics stay inside OWNED.
            print(json.dumps(dict(status='FAIL_STARTUP_PROBE_PROCESS_SUPERVISION',
                error_type=type(error).__name__, error=str(error)[:2048],
                actual_arithmetic_accepted=False, automatic_retry=False)), file=sys.stderr)
        return 1
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_alarm)
        signal.signal(signal.SIGTERM, previous_term)


if __name__ == '__main__':
    raise SystemExit(main())
