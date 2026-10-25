"""Single-use, exact-review-bound launcher for the official fresh M128 single-layer reference worker (preparation, not approval)."""
from __future__ import annotations
import argparse
import ctypes
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_common import (GATE_FILES, LIMITS, encoded, file_id, need, process_stat,
                         read_checked, sha, write_new)


def validate_review(review, config_sha, reviewer_sha, approval, config):
    need(config.get("launch_ready") is True, "M128 draft is not launch-ready; root must select resources and obtain exact independent review")
    need(review.get('schema') == 1 and review.get('status') == 'APPROVED_FOR_SINGLE_M128_OFFICIAL_REFERENCE_PAIR', 'independent review not approved')
    need(review.get('config_sha256') == config_sha, 'review not bound to exact config')
    need(review.get('limits') == LIMITS == config['limits'], 'review must approve exact proposed full-reference limits')
    need(review.get('blockers') == [], 'review has blockers')
    need(review.get('model_import_executed') is False, 'review was not static')
    reviewer = review.get('reviewer')
    need(isinstance(reviewer, str) and reviewer.strip(), 'named independent reviewer required')
    need(approval.get('schema') == 1 and approval.get('action') == 'single_official_m128_full_layer_reference_pair', 'wrong launch approval action')
    need(approval.get('config_sha256') == config_sha and approval.get('review_sha256') == reviewer_sha, 'approval is not bound to config/review')
    need(approval.get('maximum_invocations') == 1 and approval.get('no_retry') is True, 'one-use no-retry approval required')
    issuer = approval.get('issued_by')
    need(isinstance(issuer, str) and issuer.strip() and issuer != reviewer, 'reviewer must differ from launch issuer')
    need(approval.get('exclusive_reference_slot') is True, 'exclusive reference slot required')
    need(approval.get('issued_by') == 'root', 'only explicit root GO authority accepted')
    need(approval.get('go') == 'GO' and approval.get('scope') == config['scope'], 'exact-scope one-time GO required')
    need(review.get('runtime_profile') == config['reviewed_runtime_profile'], 'exact reviewed runtime profile required')
    need(review.get('loopback_probe') == config['loopback_probe'], 'exact dependency probe review required')
    need(review.get('capture_sources') == config['capture_sources'], 'frozen paired capture review required')
    need(review.get('capture_profile') == config['capture_profile'], 'exact two-arm capture profile review required')
    need(isinstance(approval.get('run_id'), str) and approval['run_id'].replace('_', '').replace('-', '').isalnum(), 'canonical run ID required')
    need(0 < len(approval['run_id']) <= 64, 'bounded run ID required')


def runtime_environment(out):
    temp = str(out / 'tmp')
    return {
        'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
        'HOME': str(out / 'home'), 'TMPDIR': temp,
        'OMP_NUM_THREADS': '4', 'MKL_NUM_THREADS': '4', 'OPENBLAS_NUM_THREADS': '4',
        'NUMEXPR_NUM_THREADS': '4', 'VECLIB_MAXIMUM_THREADS': '4', 'BLIS_NUM_THREADS': '4',
        'HF_HOME': str(out / 'hf_home'), 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
        'HF_DATASETS_OFFLINE': '1', 'HF_HUB_DISABLE_TELEMETRY': '1', 'HF_HUB_DISABLE_IMPLICIT_TOKEN': '1',
        'DO_NOT_TRACK': '1', 'USE_TORCH': '1', 'USE_TF': '0', 'USE_FLAX': '0',
    }


class OwnedIdentities(dict):
    """Current verified identities plus an append-only rebind audit trail."""
    def __init__(self):
        super().__init__()
        self.rebindings = []


def discover_tree(worker_pid, tracked):
    table = {}
    for entry in Path('/proc').iterdir():
        if entry.name.isdigit():
            try:
                row = process_stat(int(entry.name))
            except (OSError, ValueError, IndexError):
                continue
            if row:
                table[row['pid']] = row
    return expand_owned_tree(table, worker_pid, tracked, os.getpid())


def expand_owned_tree(table, worker_pid, tracked, parent_pid):
    """Never extend ancestry or group ownership through a reused process identity."""
    changed = True
    while changed:
        changed = False
        valid = {pid for pid, start in tracked.items()
                 if pid in table and table[pid]['start_ticks'] == start}
        group_confirmed = any(table[pid]['pgrp'] == worker_pid for pid in valid)
        for pid, row in table.items():
            if pid in valid:
                continue
            # A stale numeric PID is not a permanent tombstone. Rebind only
            # after proving this new identity belongs to the CURRENT owned tree.
            inherited = row['ppid'] in valid
            same_owned_group = group_confirmed and row['pgrp'] == worker_pid
            adopted_direct_child = row['ppid'] == parent_pid
            if inherited or same_owned_group or adopted_direct_child:
                previous = tracked.get(pid)
                if previous is not None and previous != row['start_ticks'] and hasattr(tracked, 'rebindings'):
                    tracked.rebindings.append({
                        'pid': pid, 'old_start_ticks': previous, 'new_start_ticks': row['start_ticks'],
                        'current_ppid': row['ppid'], 'current_pgrp': row['pgrp'],
                        'verified_current_parent': inherited, 'verified_current_group': same_owned_group,
                        'adopted_direct_child': adopted_direct_child})
                tracked[pid] = row['start_ticks']
                changed = True
    return {pid: row for pid, row in table.items()
            if pid in tracked and row['start_ticks'] == tracked[pid] and row['state'] != 'Z'}


def stop_owned(worker_pid, tracked):
    """Never signal a reused PID; group signal only while group leader identity matches."""
    active = discover_tree(worker_pid, tracked)
    leader = process_stat(worker_pid)
    if leader and leader['start_ticks'] == tracked.get(worker_pid) and leader['pgrp'] == worker_pid:
        try:
            os.killpg(worker_pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    for pid, record in active.items():
        current = process_stat(pid)
        if current and current['start_ticks'] == tracked[pid]:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    return sorted(active)


def total_output(out):
    return sum(p.stat().st_size for p in out.rglob('*') if p.is_file() and not p.is_symlink())


def terminal_output_snapshot(out):
    """Actual full-directory/log sizes, after workers have become terminal."""
    return {'output_bytes': total_output(out),
            'log_bytes': {name: (out / name).stat().st_size if (out / name).exists() else 0
                          for name in ('stdout.log', 'stderr.log')}}


def terminal_limit_reason(snapshot):
    if snapshot['output_bytes'] > LIMITS['output_bytes']:
        return 'terminal_output_limit_exceeded'
    if any(size > LIMITS['log_bytes_each'] for size in snapshot['log_bytes'].values()):
        return 'terminal_log_limit_exceeded'
    return None


def project_terminal_success(out, receipt, seal_template):
    """Exact encoded receipt + seal sizes; no file writes or authority changes."""
    snapshot = terminal_output_snapshot(out)
    candidate = dict(receipt)
    candidate['terminal_output_budget'] = {
        'limit_bytes': LIMITS['output_bytes'], 'before_parent_terminal_files': snapshot,
        'exact_receipt_and_seal_projection_required': True,
        'actual_staged_bytes_checked_before_success_seal': True,
        'exclusive_directory_assumption': 'Launcher-owned directory; worker and tracked descendants are terminal; no external writers during finalization.',
        'success_seal_publication': 'Byte-preserving atomic rename after complete staged-file size/hash/log checks; no later output-directory writes.',
        'failure_diagnostics_may_exceed_success_limit': True,
    }
    receipt_raw = encoded(candidate)
    receipt_identity = {'bytes': len(receipt_raw), 'sha256': sha(receipt_raw)}
    seal = dict(seal_template, receipt=receipt_identity)
    # Only decimal byte-count lengths are self-referential. Reach an exact
    # fixed point before any candidate terminal output is written.
    seal_bytes = projected_total = 0
    for _ in range(16):
        seal['terminal_output_budget'] = {
            'limit_bytes': LIMITS['output_bytes'], 'base_output_bytes': snapshot['output_bytes'],
            'receipt_bytes': len(receipt_raw), 'completion_seal_bytes': seal_bytes,
            'final_output_bytes': projected_total, 'terminal_log_bytes': snapshot['log_bytes'],
            'actual_staged_bytes_checked_before_success_seal': True,
        }
        seal_raw = encoded(seal)
        actual = (len(seal_raw), snapshot['output_bytes'] + len(receipt_raw) + len(seal_raw))
        if actual == (seal_bytes, projected_total):
            return {'receipt': candidate, 'receipt_identity': receipt_identity,
                    'seal': seal, 'seal_identity': {'bytes': len(seal_raw), 'sha256': sha(seal_raw)},
                    'snapshot': snapshot, 'projected_total_bytes': projected_total}
        seal_bytes, projected_total = actual
    raise ValueError('terminal output byte projection did not converge')


def write_failed_terminal(out, receipt, reason):
    """Retain every candidate/worker artifact; FAIL diagnostics may exceed cap."""
    preserved = {}
    for name in ('RECEIPT.json', 'COMPLETION_SEAL.pending.json'):
        path = out / name
        if path.exists():
            rejected = out / (name + '.REJECTED')
            need(not rejected.exists(), 'rejected candidate target already exists')
            path.rename(rejected)
            preserved[rejected.name] = file_id(rejected)
    # This function never creates or removes a successful completion seal.
    need(not (out / 'COMPLETION_SEAL.json').exists(), 'failure cannot follow success publication')
    failed = dict(receipt, status='FAIL_OFFICIAL_M128_REFERENCE_GATE', passed=False)
    failed['limit_reason'] = failed.get('limit_reason') or reason
    failed['terminal_output_budget'] = {
        'passed': False, 'limit_bytes': LIMITS['output_bytes'],
        'before_failure_diagnostics': terminal_output_snapshot(out),
        'failure_reason': reason, 'preserved_rejected_candidates': preserved,
        'failure_diagnostics_may_exceed_success_limit': True,
        'no_artifacts_deleted_to_fit_limit': True,
        'success_seal_created': False,
    }
    write_new(out / 'RECEIPT.json', failed)
    return failed, False


def finalize_terminal_output(out, receipt, seal_template=None, completion_path=None):
    """Close the success output budget before publishing the sole parent seal.

    Precondition: workers/descendants are terminal and this directory has no
    external writers. A pending candidate is not a completion seal. Publishing
    it by rename is the last directory mutation on the successful path.
    """
    if not receipt['passed']:
        return write_failed_terminal(out, receipt, receipt.get('limit_reason') or 'earlier_gate_failed')
    try:
        need(completion_path == out / 'COMPLETION_SEAL.json', 'exact completion seal destination required')
        need(not completion_path.exists(), 'completion seal already exists')
        need(not (out / 'RECEIPT.json').exists() and not (out / 'COMPLETION_SEAL.pending.json').exists(),
             'terminal candidate path already exists')
        projection = project_terminal_success(out, receipt, seal_template)
        reason = terminal_limit_reason(projection['snapshot'])
        need(reason is None, reason or 'terminal limits failed')
        need(projection['projected_total_bytes'] <= LIMITS['output_bytes'],
             'projected_final_output_limit_exceeded')
        receipt_id = write_new(out / 'RECEIPT.json', projection['receipt'])
        pending = out / 'COMPLETION_SEAL.pending.json'
        seal_id = write_new(pending, projection['seal'])
        need(receipt_id == projection['receipt_identity'] and seal_id == projection['seal_identity'],
             'terminal encoded output identity changed')
        actual = terminal_output_snapshot(out)
        reason = terminal_limit_reason(actual)
        need(reason is None, reason or 'terminal limits failed after writes')
        need(actual['output_bytes'] == projection['projected_total_bytes']
             and actual['log_bytes'] == projection['snapshot']['log_bytes'],
             'terminal output changed after exact projection')
        need(file_id(out / 'RECEIPT.json') == projection['receipt_identity']
             and file_id(pending) == projection['seal_identity'], 'staged terminal bytes changed')
        # No process can write here under the stated ownership precondition.
        # The final path publication changes no byte count and adds no output.
        pending.rename(completion_path)
        return projection['receipt'], True
    except (OSError, ValueError, TypeError) as exc:
        return write_failed_terminal(out, receipt, 'terminal_finalization:' + str(exc))


def manifest_postflight(manifest):
    """Independent complete rehash. Keep every difference, not just the first."""
    begin = time.monotonic()
    differences = {}
    checked_bytes = 0
    for path, expected in manifest.items():
        try:
            actual = file_id(path)
            checked_bytes += actual['bytes']
            if actual != expected:
                differences[path] = {'expected': expected, 'actual': actual}
        except (OSError, ValueError) as exc:
            differences[path] = {'expected': expected, 'error': type(exc).__name__ + ': ' + str(exc)}
    return {'passed': not differences, 'files_checked': len(manifest),
            'bytes_checked': checked_bytes, 'differences': differences,
            'wall_seconds': time.monotonic() - begin,
            'scope': 'full sealed file manifest after worker/descendant terminal state; outside worker budget'}


def launch(a):
    need(a.go == 'GO', 'explicit command-line GO is required; no environment override')
    beginning = time.monotonic()
    config_path = Path(a.config).resolve(strict=True)
    config = read_checked(config_path, a.config_sha256)
    review_path = Path(a.review).resolve(strict=True)
    review = read_checked(review_path, a.review_sha256, maximum=1048576)
    approval_path = Path(a.approval).resolve(strict=True)
    approval_raw = approval_path.read_bytes()
    need(len(approval_raw) <= 16384, 'oversized approval')
    approval = json.loads(approval_raw)
    validate_review(review, a.config_sha256, a.review_sha256, approval, config)
    need(config['status'] == 'PREPARED_NOT_EXECUTED_NOT_APPROVED' and config['execution_started'] is False, 'wrong config scope')
    need(Path(sys.executable).resolve() == Path(config['interpreter']), 'exact pinned Python required')
    need(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode and sys.flags.optimize == 0,
         'launcher requires exact python -I -S -B (without -O)')
    # All file-manifest rehashing happens before the worker timer begins.
    manifest_check_start = time.monotonic()
    checked_bytes = 0
    for path, expected in config['file_manifest'].items():
        actual = file_id(path)
        need(actual == expected, 'preflight file manifest drift: ' + path)
        checked_bytes += actual['bytes']
    for name in GATE_FILES:
        need(str(Path(config['gate_directory']) / name) in config['file_manifest'], 'unmanifested gate source')
    preflight = {'files_checked': len(config['file_manifest']), 'bytes_checked': checked_bytes,
                 'wall_seconds': time.monotonic() - manifest_check_start, 'worker_started': False}
    out = Path(a.output).resolve()
    need(out == Path(config['gate_directory']) / approval['run_id'], 'output must be exactly gate_directory/run_id')
    need(not out.exists(), 'output already exists: one fresh run only')
    need(out.name == approval['run_id'], 'output basename must equal approved run_id')
    # A claim remains consumed even if a later startup step fails. No automatic retries.
    claim_path = Path(config['gate_directory']) / 'FULL_REFERENCE_CLAIM.json'
    write_new(claim_path, {'approval_sha256': sha(approval_raw), 'config_sha256': a.config_sha256,
              'review_sha256': a.review_sha256, 'pid': os.getpid(), 'process': process_stat(os.getpid()),
              'run_id': approval['run_id'], 'output': str(out), 'maximum_invocations': 1, 'go': 'GO'})
    out.mkdir(mode=0o700)
    for folder in ('tmp', 'home', 'hf_home'):
        (out / folder).mkdir(mode=0o700)
    write_new(out / 'PREFLIGHT.json', preflight)
    with (out / 'REVIEW.json').open('xb') as stream:
        raw_review = review_path.read_bytes()
        need(sha(raw_review) == a.review_sha256, 'review changed before archive')
        stream.write(raw_review)
    with (out / 'APPROVAL.json').open('xb') as stream:
        stream.write(approval_raw)
    # Subreaper allows any unexpected orphaned import descendants to be reaped.
    libc = ctypes.CDLL(None, use_errno=True)
    need(libc.prctl(36, 1, 0, 0, 0) == 0, 'PR_SET_CHILD_SUBREAPER failed')
    affinity_before = sorted(os.sched_getaffinity(0))
    need(len(affinity_before) >= LIMITS['affinity_count'], 'four available affinity CPUs required')
    cpus = affinity_before[:LIMITS['affinity_count']]
    rlimit_as = resource.getrlimit(resource.RLIMIT_AS)
    parent_argv = [os.fsdecode(x) for x in Path('/proc/self/cmdline').read_bytes().split(b'\0') if x]
    cap = {'parent_pid': os.getpid(), 'parent_start_ticks': process_stat(os.getpid())['start_ticks'],
           'parent_argv': parent_argv, 'config_sha256': a.config_sha256, 'review_sha256': a.review_sha256,
           'approval_sha256': sha(approval_raw), 'run_id': approval['run_id'], 'output': str(out),
           'rlimit_as_unchanged': list(rlimit_as), 'go': 'GO',
           'approval_path': str(out / 'APPROVAL.json'), 'review_path': str(out / 'REVIEW.json'),
           'claim_path': str(claim_path), 'affinity': cpus}
    readfd, writefd = os.pipe()
    env = runtime_environment(out)
    argv = [config['interpreter'], '-I', '-S', '-B', str(Path(config['gate_directory']) / 'worker.py'),
            '--config', str(config_path), '--config-sha256', a.config_sha256,
            '--output', str(out), '--capability-fd', str(readfd)]
    def child_setup():
        os.sched_setaffinity(0, set(cpus))
        resource.setrlimit(resource.RLIMIT_CPU, (LIMITS['cpu_seconds_hard'], LIMITS['cpu_seconds_hard']))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        # No RLIMIT_AS/RLIMIT_DATA/RLIMIT_RSS change: VSZ is not RSS.
    tracked = OwnedIdentities()
    peak_rss = 0
    limit_reason = None
    killed = []
    reaped = []
    result = None
    p = None
    usage_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    worker_start = time.monotonic()
    try:
        with (out / 'stdout.log').open('xb') as stdout, (out / 'stderr.log').open('xb') as stderr:
            p = subprocess.Popen(argv, env=env, cwd=out, stdin=subprocess.DEVNULL,
                  stdout=stdout, stderr=stderr, start_new_session=True,
                  pass_fds=(readfd,), preexec_fn=child_setup)
            os.close(readfd)
            readfd = -1
            os.write(writefd, encoded(cap))
            os.close(writefd)
            writefd = -1
            st = process_stat(p.pid)
            need(st is not None, 'worker vanished before PID identity capture')
            tracked[p.pid] = st['start_ticks']
            write_new(out / 'LAUNCH.json', {'worker_argv': argv, 'worker_identity': st,
                      'parent_identity': process_stat(os.getpid()), 'parent_argv': parent_argv,
                      'affinity_parent': affinity_before, 'affinity_worker': cpus,
                      'environment': env, 'limits': LIMITS,
                      'rlimit_as_before': list(rlimit_as), 'rlimit_as_changed': False,
                      'preflight_excluded_from_worker_budget': True})
            while True:
                active = discover_tree(p.pid, tracked)
                rss = sum(row['rss_bytes'] for row in active.values())
                peak_rss = max(peak_rss, rss)
                elapsed = time.monotonic() - worker_start
                if rss > LIMITS['sampled_tree_rss_bytes']:
                    limit_reason = 'sampled_tree_rss_exceeded'
                elif elapsed > LIMITS['wall_seconds']:
                    limit_reason = 'worker_wall_exceeded'
                elif stdout.tell() > LIMITS['log_bytes_each'] or stderr.tell() > LIMITS['log_bytes_each']:
                    limit_reason = 'log_limit_exceeded'
                elif total_output(out) > LIMITS['output_bytes']:
                    limit_reason = 'output_limit_exceeded'
                returncode = p.poll()
                if limit_reason:
                    killed += stop_owned(p.pid, tracked)
                    break
                if returncode is not None:
                    break
                time.sleep(LIMITS['poll_seconds'])
    except BaseException as exc:
        limit_reason = limit_reason or 'launcher_exception:' + type(exc).__name__ + ':' + str(exc)
    finally:
        for fd in (readfd, writefd):
            if fd >= 0:
                os.close(fd)
        if p is not None:
            killed += stop_owned(p.pid, tracked)
            try:
                p.wait(timeout=LIMITS['cleanup_seconds'])
            except subprocess.TimeoutExpired:
                limit_reason = limit_reason or 'worker_unreaped_after_cleanup'
            cleanup_until = time.monotonic() + LIMITS['cleanup_seconds']
            while time.monotonic() < cleanup_until:
                try:
                    pid, status = os.waitpid(-1, os.WNOHANG)
                except ChildProcessError:
                    break
                if pid:
                    reaped.append({'pid': pid, 'wait_status': status})
                    continue
                if not discover_tree(p.pid, tracked):
                    break
                stop_owned(p.pid, tracked)
                time.sleep(0.02)
        else:
            limit_reason = limit_reason or 'worker_not_started'
    remaining = discover_tree(p.pid, tracked) if p else {}
    after_cleanup_output = terminal_output_snapshot(out)
    limit_reason = limit_reason or terminal_limit_reason(after_cleanup_output)
    usage_after = resource.getrusage(resource.RUSAGE_CHILDREN)
    child_usage = {'user_cpu_seconds': usage_after.ru_utime - usage_before.ru_utime,
                   'system_cpu_seconds': usage_after.ru_stime - usage_before.ru_stime,
                   'ru_maxrss_bytes_linux': usage_after.ru_maxrss * 1024,
                   'ru_maxrss_note': 'RUSAGE_CHILDREN high-water counter; not summed tree RSS'}
    if (out / 'WORKER_RESULT.json').exists():
        result = json.loads((out / 'WORKER_RESULT.json').read_text())
    worker_wall = time.monotonic() - worker_start
    postflight = manifest_postflight(config['file_manifest'])
    write_new(out / 'POSTFLIGHT.json', postflight)
    after_postflight_output = terminal_output_snapshot(out)
    limit_reason = limit_reason or terminal_limit_reason(after_postflight_output)
    passed = bool(p and p.returncode == 0 and not remaining and limit_reason is None and result and result['passed'] and postflight['passed'])
    receipt = {'status': 'REFERENCE_PAIR_CAPTURE_AND_SELF_CHECKS_COMPLETE_NOT_DUT_PASS' if passed else 'FAIL_OFFICIAL_M128_REFERENCE_GATE',
       'passed': passed, 'config_sha256': a.config_sha256, 'review_sha256': a.review_sha256,
       'approval_sha256': sha(approval_raw), 'claim': str(claim_path),
       'worker_pid': p.pid if p else None, 'worker_returncode': p.returncode if p else None,
       'worker_reaped': bool(p and p.returncode is not None), 'tracked_pid_start_ticks': tracked,
       'tracked_identity_rebindings': tracked.rebindings,
       'remaining_tracked_live_processes': remaining, 'cleanup_signaled_pids': sorted(set(killed)),
       'reaped_descendants': reaped, 'limit_reason': limit_reason,
       'peak_sampled_tree_rss_bytes': peak_rss, 'rss_is_hard_cap': False,
       'worker_wall_seconds': worker_wall,
       'worker_wall_scope': 'Popen through worker exit and cleanup, including import and observed-file hashing; excludes parent manifest preflight',
       'overall_wall_seconds': time.monotonic() - beginning, 'preflight': preflight, 'postflight': postflight,
       'cpu_usage_children': child_usage,
       'output_after_cleanup': after_cleanup_output, 'output_after_postflight': after_postflight_output,
       'rlimit_cpu_scope': 'worker process including threads; Python subprocess/fork/spawn/exec/system audit events are denied; not a kernel aggregate tree CPU quota',
       'rlimit_as_before': list(rlimit_as), 'rlimit_as_changed': False,
       'limits': LIMITS, 'worker_result_status': result['status'] if result else None,
       'full_live_code_identity_proven': False, 'model_instance_created': bool(result and result.get('model_instance_created')),
       'layer_instances': 1 if result and result.get('model_instance_created') else 0,
       'forward_call_count': result.get('forward_call_count', 0) if result else 0,
       'capture_profile': config['capture_profile'],
       'forward_executed': bool(result and result.get('forward_executed')), 'numeric_pass': False, 'dut_or_matrix_executed': False,
       'artifacts': {str(path.relative_to(out)): file_id(path) for path in sorted(out.rglob('*')) if path.is_file()},
       'no_retry': True}
    # Only this parent terminal path may issue a reference completion seal.
    # Frozen capture/SEAL.json is an internal capture-completeness receipt only.
    if passed:
        seal_template = {
            'schema': 1, 'status': receipt['status'], 'numeric_acceptance': 'NOT_RUN',
            'capture_profile': config['capture_profile'], 'layer_instances': 1, 'forward_calls': 2,
            'dut_comparison': 'NOT_RUN', 'legacy_results_inherited': False,
            'config_sha256': a.config_sha256, 'review_sha256': a.review_sha256,
            'approval_sha256': sha(approval_raw), 'artifacts': receipt['artifacts']}
        receipt, passed = finalize_terminal_output(out, receipt, seal_template,
                                                   completion_path=out / 'COMPLETION_SEAL.json')
    else:
        receipt, passed = finalize_terminal_output(out, receipt)
    limit_reason = receipt['limit_reason']
    print(json.dumps({'status': receipt['status'], 'receipt': str(out / 'RECEIPT.json'),
                      'worker_returncode': receipt['worker_returncode'], 'limit_reason': limit_reason}, sort_keys=True))
    return 0 if passed else 2


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--go', required=True, choices=['GO'])
    p.add_argument('--config', required=True)
    p.add_argument('--config-sha256', required=True)
    p.add_argument('--review', required=True)
    p.add_argument('--review-sha256', required=True)
    p.add_argument('--approval', required=True)
    p.add_argument('--output', required=True)
    return launch(p.parse_args())

if __name__ == '__main__':
    raise SystemExit(main())
