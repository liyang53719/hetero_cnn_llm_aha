"""Single new-arm M2 frame-cache calibration with postseal historical comparison.

No sampling. The frozen successful historical arm is never a child input.
New root authority is mandatory; this source cannot grant execution.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import stat
import sys
import time
import types

HERE = Path(__file__).resolve().parent


def need(ok, message):
    if not ok:
        raise ValueError(message)


def bootstrap(manifest_sha):
    """Minimal same-buffer bootstrap; all further reads use the pinned authority."""
    need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode and
         not sys.flags.optimize, 'require Python -I -S -B without optimization')
    def read(path):
        need(path.resolve() == path and not any(p.is_symlink() for p in (path, *path.parents)),
             'unaliased source bootstrap')
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as f:
            before = os.fstat(f.fileno())
            need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= 2 << 20,
                 'bounded regular bootstrap source')
            raw = f.read((2 << 20) + 1)
            after = os.fstat(f.fileno())
        stamp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_nlink)
        need(stamp(before) == stamp(after) == stamp(path.lstat()), 'bootstrap source changed')
        return raw
    raw = read(HERE / 'SOURCE_MANIFEST.json')
    need(hashlib.sha256(raw).hexdigest() == manifest_sha, 'explicit new manifest SHA required')
    own = json.loads(raw)
    source = read(HERE / 'm2_authority.py')
    need(own['files']['m2_authority.py'] == dict(bytes=len(source), sha256=hashlib.sha256(source).hexdigest()),
         'authority bootstrap pin differs')
    need('m2_authority' not in sys.modules, 'fresh parent authority namespace')
    authority = types.ModuleType('m2_authority')
    authority.__file__ = str(HERE / 'm2_authority.py')
    sys.modules['m2_authority'] = authority
    exec(compile(source, authority.__file__, 'exec', dont_inherit=True, optimize=0), vars(authority))
    own = authority.parse(raw)
    gate = authority.load_source(HERE / 'm2_supervision_gate.py', '_m2_supervision_gate',
                                 own['files']['m2_supervision_gate.py'])
    return authority, gate, own


def interrupted(*_):
    raise TimeoutError('shared two-arm M2 launch deadline')


def terminal(adapter, rootout, started, whole_stop, cpu_baseline, states, diagnostics):
    files, rss = adapter.owned_inventory(rootout), adapter.rss_high_water()
    cpu, now = adapter.cpu_usage() - cpu_baseline, time.monotonic()
    need(cpu <= adapter.WHOLE_SECONDS and now < whole_stop and
         rss['supervisor_maxrss_bytes'] <= adapter.RSS_BYTES and
         rss['child_cumulative_maxrss_bytes'] <= adapter.RSS_BYTES, 'whole pair CPU/RSS/wall excess')
    need(all(not s.get('tree', {}).get('ownership_uncertain', False) and
             not s.get('terminal_live_descendant_pids') for s in states), 'sticky ownership uncertainty')
    need(all(d.get('cleanup_confirmed') is True for d in diagnostics), 'cleanup unconfirmed')
    return dict(whole_owned_files=files, rusage_maxrss=rss, whole_cpu_seconds=cpu,
                wall_seconds=now - started)


def main(argv=None):
    started = time.monotonic()
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preflight', action='store_true')
    mode.add_argument('--actual', action='store_true')
    p.add_argument('--manifest-sha', required=True)
    p.add_argument('--base', required=True)
    p.add_argument('--out')
    p.add_argument('--admission')
    p.add_argument('--admission-sha')
    args = p.parse_args(argv)
    authority, gate, own = bootstrap(args.manifest_sha)
    if args.preflight:
        need(args.out is None and args.admission is None and args.admission_sha is None,
             'preflight cannot receive actual authority/output')
        baseline, budget = gate.sources(own, args.base)
        adapter = gate.load_adapter(args.base, baseline)
        print(json.dumps(gate.projection(adapter, budget), sort_keys=True))
        return 0
    need(args.out is not None and args.admission is not None and args.admission_sha is not None,
         'explicit root output/admission/SHA required')
    budget = gate.validate_budget(authority.parse(authority.checked(
        HERE / 'BUDGET.json', own['files']['BUDGET.json'])))
    rootout = Path(args.out)
    whole_stop, work_stop = started + 120, started + 105
    cpu_baseline = 0.0  # Includes parent bootstrap CPU and one reaped child.
    resource.setrlimit(resource.RLIMIT_CPU, (120, 120))
    resource.setrlimit(resource.RLIMIT_AS, (budget['rss_bytes'],) * 2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (budget['file_bytes'],) * 2)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    allowed = os.sched_getaffinity(0)
    need(bool(allowed), 'nonempty inherited affinity')
    os.sched_setaffinity(0, {min(allowed)})
    need(signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK, []) and
         signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'unblocked unowned timer required')
    old_alarm, old_term = signal.signal(signal.SIGALRM, interrupted), signal.signal(signal.SIGTERM, interrupted)
    receipt, states, diagnostics, arm_results = None, [], [], []
    try:
        signal.setitimer(signal.ITIMER_REAL, max(.001, whole_stop - time.monotonic()))
        baseline, checked_budget = gate.sources(own, args.base)
        need(checked_budget == budget, 'source budget changed before admission')
        adapter = gate.load_adapter(args.base, baseline)
        report = gate.projection(adapter, budget)
        gate.admission(own, rootout, args.admission, args.admission_sha,
                       args.manifest_sha, report['projection_hashes'])
        need(time.monotonic() < work_stop, 'admission exhausted shared work budget')
        space = os.statvfs(rootout)
        need(space.f_bavail * space.f_frsize >= budget['output_bytes'] + budget['free_space_margin_bytes'],
             'whole owned output plus free-space margin unavailable')
        adapter.configure(budget)
        lease = dict(parent=authority.process(os.getpid()), admission_sha256=args.admission_sha,
                     source_manifest_sha256=args.manifest_sha, output_root=str(rootout),
                     start=started, work_stop=work_stop, whole_stop=whole_stop,
                     cpu_baseline=cpu_baseline, automatic_retry=False, arms=['new'])
        # Exclusive retained lease is the irreversible once marker. Root, not this
        # launcher, created ADMISSION. Each child creates its own CONSUMED marker.
        with (rootout / 'LEASE.json').open('x') as f:
            json.dump(lease, f, sort_keys=True, allow_nan=False)
        receipt = rootout / 'CACHE_LAUNCH.json'
        adapter.checked_save(receipt, dict(status='STARTED_SINGLE_SUCCESS_M2_FRAME_CACHE_CHILD',
            source_manifest_sha256=args.manifest_sha, admission_sha256=args.admission_sha,
            limits=adapter.fixed_limits(), automatic_retry=False), rootout)
        (rootout / 'tmp').mkdir(mode=0o700)
        environment = dict(PATH='/usr/bin:/bin', HOME=str(rootout / 'tmp'), TMPDIR=str(rootout / 'tmp'),
            LANG='C', LC_ALL='C', TZ='UTC', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
            MKL_NUM_THREADS='1', PYTHONDONTWRITEBYTECODE='1')
        for arm in ('new',):
            need(time.monotonic() < work_stop, 'shared work budget exhausted before arm')
            state, diagnostic = dict(reviewed_projection_hashes=report['projection_hashes']), {}
            states.append(state); diagnostics.append(diagnostic)
            command = [sys.executable, '-I', '-S', '-B', str(HERE / 'm2_entry.py'), '--actual',
                       '--arm', arm, '--base', str(Path(args.base)), '--out', str(rootout / arm),
                       '--admission', args.admission, '--admission-sha', args.admission_sha,
                       '--manifest-sha', args.manifest_sha]
            with (rootout / (arm + '_stdout.log')).open('xb') as stdout, (rootout / (arm + '_stderr.log')).open('xb') as stderr:
                record, _, usage = adapter.run_admitted(command, HERE, rootout / (arm + '_supervisor'),
                    environment, rootout, stdout, stderr, whole_stop,
                    dict(handler=interrupted, deadline=whole_stop), cpu_baseline, state, diagnostic,
                    work_stop=work_stop)
            need(record.get('status') == 'PASS' and record.get('exit_code') == 0 and
                 record.get('anchor_confirmed') is True and record.get('reaped') is True and
                 record.get('group_state') == 'absent' and record.get('cleanup_confirmed') is True,
                 'exact child/group cleanup required before another arm or diff')
            consumed = authority.parse(authority.checked(rootout / ('CONSUMED_' + arm + '.json'), cap=32768))
            leader = state.get('tree', {}).get('leader')
            need(type(leader) is tuple and len(leader) == 2 and consumed.get('arm') == arm and
                 consumed.get('parent') == lease['parent'] and
                 consumed.get('source_manifest_sha256') == args.manifest_sha and
                 consumed.get('admission_sha256') == args.admission_sha and
                 consumed.get('child') == dict(pid=leader[0], start_ticks=leader[1]) and
                 leader[0] == record.get('pid'), 'exact fresh child consumption required')
            summary = authority.parse(authority.checked(rootout / arm / 'M2_CASE.json', cap=262144))
            need(summary.get('status') == 'ACTUAL_SUCCESS_M2_CAPTURED_PENDING_PAIR_COMPARISON' and
                 summary.get('variant') == arm and summary.get('m') == 2 and
                 summary.get('scope') == 'INCOMPLETE_WHOLEBLOCK' and
                 summary.get('wholeblock', {}).get('status') == 'SEALED_ACTUAL_M2_SUBCHAIN_ONLY',
                 'successful finite M2 arm seal required')
            arm_result = authority.parse(authority.checked(rootout / arm / 'ARM_RESULT.json', cap=4 << 20))
            need(arm_result.get('status') == 'PASS_LIMITED_SUCCESS_M2_FRAME_CACHE_ARM' and
                 arm_result.get('arm') == arm and arm_result.get('scope') == 'INCOMPLETE_WHOLEBLOCK' and
                 type(arm_result.get('actual_owner_M')) is int and arm_result['actual_owner_M'] == 2 and
                 arm_result.get('fullblock_pass') is False and arm_result.get('M128_execution') is False and
                 arm_result.get('numerical_acceptance') is False and
                 arm_result.get('source_manifest_sha256') == args.manifest_sha and
                 arm_result.get('base_source_manifest_sha256') == authority.BASE_MANIFEST_SHA and
                 arm_result.get('admission_sha256') == args.admission_sha and
                 arm_result.get('budget_sha256') == own['files']['BUDGET.json']['sha256'] and
                 arm_result.get('policy_sha256') == own['files']['POLICY.json']['sha256'] and
                 arm_result.get('cache_policy_sha256') == own['files']['CACHE_POLICY.json']['sha256'] and
                 arm_result.get('sampling_enabled') is False and arm_result.get('historical_comparison_only') is True and
                 arm_result.get('observer_policy') == ('original-full-identity-every-watched-callback'
                    if arm == 'old' else 'op-evidence-boundary-v1') and
                 arm_result.get('process') == consumed['child'] and
                 arm_result.get('parent') == lease['parent'] and arm_result.get('case') == summary and
                 arm_result.get('official_input_payload_read') is False and
                 arm_result.get('reference_payload_read') is False and
                 arm_result.get('compilation_performed') is False and
                 'postseal_context_verification' in arm_result.get('timings', {}),
                 'postseal exact-source/process/policy ARM_RESULT required before continuing')
            arm_results.append(dict(arm=arm, pid=leader[0], cleanup_confirmed=True, usage=usage))
            terminal(adapter, rootout, started, whole_stop, cpu_baseline, states, diagnostics)
        need(time.monotonic() < work_stop, 'no shared work remaining for pair diff')
        # Diff is parent work, never a third child; the new child group is absent.
        signal.setitimer(signal.ITIMER_REAL, max(.001, work_stop - time.monotonic()))
        diff = authority.load_source(HERE / 'parent/decode_diff.py', '_m2_pair_decode_diff', own['parent_files']['parent/decode_diff.py'])
        adapter.owned_inventory(rootout, reserve=8 << 20)
        diffout = rootout / 'diff'
        diffout.mkdir(mode=0o700)
        # Two bounded diff files can each reach at most 4 MiB; reserve them before
        # writing, with RLIMIT_FSIZE active during comparison, not just post hoc.
        resource.setrlimit(resource.RLIMIT_FSIZE, (4 << 20, budget['file_bytes']))
        history = authority.load_source(HERE / 'parent/history_compare.py', '_m2_history_compare', own['parent_files']['parent/history_compare.py'])
        historical_root = history.verify_history(own)
        comparison = diff.compare_pair(historical_root, rootout / 'new', diffout, expected_variants=('new','new'),
            **gate.decoder_arguments(Path(args.base), baseline, budget))
        need(history.verify_history(own) == historical_root, 'historical sealed source drift during diff')
        need(time.monotonic() < work_stop, 'diff exceeded shared work budget')
        resource.setrlimit(resource.RLIMIT_FSIZE, (budget['file_bytes'],) * 2)
        signal.setitimer(signal.ITIMER_REAL, max(.001, whole_stop - time.monotonic()))
        need(comparison.get('status') == 'MATCHED_SUCCESS_M2_OBSERVER_EQUIVALENCE_ONLY',
             'M2 pair semantic mismatch; no automatic retry')
        final = terminal(adapter, rootout, started, whole_stop, cpu_baseline, states, diagnostics)
        adapter.checked_save(receipt, dict(status='MATCHED_SINGLE_M2_FRAME_CACHE_HISTORICAL_EQUIVALENCE_ONLY',
            historical_comparison_only=True, historical_root=str(historical_root),
            historical_pin=own['parent_files']['parent/HISTORY.json'], sampling_enabled=False,
            cache_policy_sha256=own['files']['CACHE_POLICY.json']['sha256'],
            source_manifest_sha256=args.manifest_sha, admission_sha256=args.admission_sha,
            projection_hashes=report['projection_hashes'], arms=arm_results, diagnostics=diagnostics,
            cleanup_confirmed=True, scope='INCOMPLETE_WHOLEBLOCK', actual_arithmetic_accepted=False,
            M128_acceptance=False, fullblock_pass=False, automatic_retry=False, **final), rootout)
        terminal(adapter, rootout, started, whole_stop, cpu_baseline, states, diagnostics)
        return 0
    except BaseException as error:
        if receipt is not None:
            try:
                adapter.checked_save(receipt, dict(status='FAIL_SINGLE_SUCCESS_M2_FRAME_CACHE',
                    failure_type=type(error).__name__, failure=str(error)[:2048], arms=arm_results,
                    diagnostics=diagnostics, cleanup_confirmed=bool(diagnostics) and all(
                        d.get('cleanup_confirmed') is True for d in diagnostics) and all(
                        not s.get('tree', {}).get('ownership_uncertain', False) for s in states),
                    actual_arithmetic_accepted=False, M128_acceptance=False, fullblock_pass=False,
                    automatic_retry=False), rootout)
            except BaseException:
                pass  # Retain original receipts even if no failure receipt fits.
        else:
            print(json.dumps(dict(status='BLOCKED_BEFORE_M2_LEASE', failure=str(error)[:2048],
                                  automatic_retry=False)), file=sys.stderr)
        return 1
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_alarm)
        signal.signal(signal.SIGTERM, old_term)


if __name__ == '__main__':
    raise SystemExit(main())
