#!/usr/bin/env python3
"""One source-reviewed, supervised isolated O cost attempt; no automatic retry."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from candidates.qwen2_dense_o_cost_m128 import gates


def save(path, value):
    raw = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n'
    gates.require(len(raw.encode()) <= gates.LIMITS['file_bytes'], 'launcher metadata per-file cap')
    temporary = path.with_suffix(path.suffix + '.tmp')
    gates.require(not temporary.is_symlink(), 'aliased launcher temporary file')
    temporary.write_text(raw)
    temporary.replace(path)


def group_exists(pid):
    try:
        os.killpg(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def terminate_group(child, *, cleanup_deadline):
    """Pinned-v2 TERM/KILL/reap protocol, with the isolated 70-second budget."""
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    incomplete = False
    try:
        remaining = cleanup_deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired('bounded group cleanup', 0)
        returncode = child.wait(timeout=min(3, remaining))
    except subprocess.TimeoutExpired:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            remaining = cleanup_deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired('bounded group cleanup', 0)
            returncode = child.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            returncode, incomplete = None, True
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    while group_exists(child.pid):
        remaining = cleanup_deadline - time.monotonic()
        if remaining <= 0:
            incomplete = True
            break
        time.sleep(min(.05, remaining))
    return returncode, incomplete


def directory_bytes(path):
    if not path.exists():
        return 0
    gates.require(not path.is_symlink(), 'aliased output directory')
    total = 0
    for item in path.rglob('*'):
        if item.is_symlink():
            gates.require(item == path / 'actual_dense.f32le' and os.readlink(item) == '/dev/null'
                          and item.resolve() == Path('/dev/null'), 'unexpected output symlink')
            continue
        if item.is_file():
            size = item.stat().st_size
            gates.require(size <= gates.LIMITS['file_bytes'], 'output per-file cap')
            total += size
    return total


def process_group_rss(pid):
    total = 0
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            stat = (path / 'stat').read_text().rsplit(')', 1)[1].split()
            if int(stat[2]) == pid:
                total += int((path / 'statm').read_text().split()[1]) * os.sysconf('SC_PAGE_SIZE')
        except (OSError, ValueError, IndexError):
            continue
    return total


def _child_limits():
    # Hard address-space/per-file limits complement sampled group RSS/disk/logs.
    for kind, amount in ((resource.RLIMIT_AS, gates.LIMITS['rss_bytes']),
                         (resource.RLIMIT_FSIZE, gates.LIMITS['file_bytes'])):
        resource.setrlimit(kind, (amount, amount))


def supervise(out, reviewed_source_manifest):
    started = time.monotonic()
    gates.require_review(reviewed_source_manifest)
    limits = dict(gates.LIMITS)
    out = gates.fresh_output(out)
    gates.require(out.parent.is_dir(), 'isolated O cost work root must already exist')
    paths = {name: out.with_name(out.name + suffix) for name, suffix in (
        ('receipt', '.LAUNCH.json'), ('stdout', '.stdout.log'), ('stderr', '.stderr.log'))}
    gates.require(all(not p.exists() and not p.is_symlink() and
                      not p.with_suffix(p.suffix + '.tmp').exists() and
                      not p.with_suffix(p.suffix + '.tmp').is_symlink() for p in paths.values()),
                  'single-use fresh launcher outputs required')
    deadline = started + limits['outer_wall_seconds']
    cutoff, cleanup_deadline = deadline - 6, deadline - 1
    runner_path = gates.HERE / 'runner.py'
    argv = [sys.executable, '-B', str(runner_path), '--actual', '--out', str(out),
            '--reviewed-source-manifest', reviewed_source_manifest]
    receipt = dict(schema=1, status='STARTED_COST_ONLY', scope=gates.SCOPE,
        argv=argv, reviewed_source_manifest=reviewed_source_manifest,
        resource_limits=limits, automatic_retry=False, compile_executed=False,
        numerical_acceptance=False, cost_complete=False, fullblock_pass=False,
        old_pass_inherited=False, same_chain_acceptance=False,
        peak_sampled_process_group_rss_bytes=0, sampled_disk_bytes=0,
        rss_is_os_hard_cap=False, address_space_has_rlimit=True,
        total_disk_and_log_caps_are_sampled=True, per_file_bytes_has_rlimit=True)
    save(paths['receipt'], receipt)
    failure, returncode, child = None, None, None
    cleanup_incomplete = False
    environment = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
        MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1', VECLIB_MAXIMUM_THREADS='1')
    try:
        with paths['stdout'].open('x') as stdout, paths['stderr'].open('x') as stderr:
            gates.require(time.monotonic() < cutoff, 'outer admission budget expired')
            child = subprocess.Popen(argv, cwd=ROOT, env=environment, stdout=stdout, stderr=stderr,
                                     start_new_session=True, preexec_fn=_child_limits)
            receipt['pid'] = child.pid
            save(paths['receipt'], receipt)
            try:
                while child.poll() is None:
                    rss = process_group_rss(child.pid)
                    disk = directory_bytes(out)
                    logs = sum(paths[n].stat().st_size for n in ('stdout', 'stderr'))
                    receipt['peak_sampled_process_group_rss_bytes'] = max(
                        receipt['peak_sampled_process_group_rss_bytes'], rss)
                    receipt['sampled_disk_bytes'] = max(receipt['sampled_disk_bytes'], disk)
                    if time.monotonic() >= cutoff:
                        failure = 'OUTER_WALL_TIMEOUT'
                    elif rss > limits['rss_bytes']:
                        failure = 'SAMPLED_RSS_CAP'
                    elif disk > limits['output_bytes']:
                        failure = 'SAMPLED_OUTPUT_CAP'
                    elif logs > limits['log_bytes']:
                        failure = 'SAMPLED_LOG_CAP'
                    if failure:
                        break
                    time.sleep(min(limits['poll_seconds'], max(0, cutoff - time.monotonic())))
                if failure or group_exists(child.pid):
                    returncode, cleanup_incomplete = terminate_group(child, cleanup_deadline=cleanup_deadline)
                else:
                    returncode = child.wait(timeout=max(.001, cleanup_deadline - time.monotonic()))
            except BaseException as error:
                failure = failure or 'SUPERVISOR_EXCEPTION'
                receipt['supervisor_error'] = repr(error)
                returncode, cleanup_incomplete = terminate_group(child, cleanup_deadline=cleanup_deadline)
    except BaseException as error:
        failure = failure or 'LAUNCH_EXCEPTION'
        receipt['launch_error'] = repr(error)
        if child is not None and (child.poll() is None or group_exists(child.pid)):
            returncode, cleanup_incomplete = terminate_group(child, cleanup_deadline=cleanup_deadline)
    result = {}
    try:
        result_path = gates._canonical(out / 'RESULT.json')
        gates.require(result_path.stat().st_size <= limits['file_bytes'], 'result per-file cap')
        result = gates._parse(result_path.read_bytes())
        gates.require(type(result) is dict, 'result object required')
    except (OSError, ValueError) as error:
        receipt['result_read_error'] = repr(error)
        result = {}
    try:
        disk = directory_bytes(out)
    except (OSError, ValueError) as error:
        disk = None
        failure = failure or 'OUTPUT_INVENTORY_OR_FILE_CAP'
        receipt['output_error'] = repr(error)
    logs = sum(paths[n].stat().st_size for n in ('stdout', 'stderr') if paths[n].exists())
    if time.monotonic() >= deadline:
        failure = failure or 'OUTER_WALL_TIMEOUT'
    if disk is not None and disk > limits['output_bytes']:
        failure = failure or 'SAMPLED_OUTPUT_CAP'
    if logs > limits['log_bytes']:
        failure = failure or 'SAMPLED_LOG_CAP'
    if cleanup_incomplete:
        failure = failure or 'PROCESS_GROUP_CLEANUP_INCOMPLETE'
    complete = (not failure and returncode == 0 and result.get('status') == 'COST_ONLY_O_COMPLETE'
        and result.get('scope') == gates.SCOPE and result.get('cost_complete') is True
        and result.get('numerical_acceptance') is False
        and result.get('fullblock_pass', False) is False
        and result.get('acceptance_sealed', False) is False
        and result.get('same_chain_acceptance', False) is False
        and result.get('official_observed_node_pass', False) is False
        and result.get('numerical_acceptance_claimed', False) is False
        and result.get('fullblock_executed', False) is False
        and result.get('public21_executed', False) is False)
    if not complete:
        failure = failure or 'CHILD_FAILED_OR_INVALID_COST_RECEIPT'
        result.update(status='FAILED', scope=gates.SCOPE, failure_kind=failure,
                      cost_complete=False, numerical_acceptance=False, fullblock_pass=False,
                      same_chain_acceptance=False, acceptance_sealed=False,
                      official_observed_node_pass=False, numerical_acceptance_claimed=False,
                      cleanup_incomplete=cleanup_incomplete)
        if out.is_dir() and not out.is_symlink() and not (out / 'RESULT.json').is_symlink():
            save(out / 'RESULT.json', result)
    receipt.update(status='COST_ONLY_O_COMPLETE' if complete else 'FAILED',
        returncode=returncode, failure_kind=failure, elapsed_seconds=time.monotonic() - started,
        cleanup_incomplete=cleanup_incomplete, child_status=result.get('status'),
        cost_complete=complete, numerical_acceptance=False,
        final_output_bytes=disk, final_log_bytes=logs)
    save(paths['receipt'], receipt)
    print(json.dumps(receipt, sort_keys=True), flush=True)
    return 0 if complete else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--actual', action='store_true')
    parser.add_argument('--out')
    parser.add_argument('--reviewed-source-manifest')
    args = parser.parse_args(argv)
    if not args.actual:
        gates.require(args.out is None and args.reviewed_source_manifest is None,
                      'actual arguments require explicit --actual')
        from candidates.qwen2_dense_o_cost_m128 import runner
        return runner.main([])
    gates.require(args.out is not None and args.reviewed_source_manifest is not None,
                  '--actual requires fresh out and independently reviewed exact source manifest')
    return supervise(args.out, args.reviewed_source_manifest)


if __name__ == '__main__':
    raise SystemExit(main())
