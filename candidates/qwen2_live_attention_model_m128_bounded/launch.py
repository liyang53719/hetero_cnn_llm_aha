#!/usr/bin/env python3
"""One fresh supervised run only after independent parent review and go."""
import argparse
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from candidates.qwen2_live_attention_model_m128_bounded import gates, runner


def save(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')
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
    """Bound TERM and KILL waits; do not report cleanup if the OS cannot reap."""
    try: os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError: pass
    incomplete = False
    try:
        remaining = cleanup_deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired('bounded group cleanup', 0)
        returncode = child.wait(timeout=min(3, remaining))
    except subprocess.TimeoutExpired:
        try: os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError: pass
        try:
            remaining = cleanup_deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired('bounded group cleanup', 0)
            returncode = child.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            returncode = None
            incomplete = True
    # Also terminate remaining descendants after the primary child exits.
    try: os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError: pass
    while group_exists(child.pid):
        remaining = cleanup_deadline - time.monotonic()
        if remaining <= 0:
            incomplete = True
            break
        time.sleep(min(.05, remaining))
    return returncode, incomplete


def supervise(out, data, reference, reviewed_source_manifest):
    started = time.monotonic()
    deadline = started + 930
    execution_cutoff = deadline - 6
    cleanup_deadline = deadline - 1
    gates.require_review(reviewed_source_manifest)
    data_path = gates.data_path(data)
    gates.reference_path(reference)
    out = Path(out).absolute()
    gates.fresh_output(out, data_path)
    paths = {name: out.with_name(out.name + suffix) for name, suffix in (
        ('receipt', '.LAUNCH.json'), ('stdout', '.stdout.log'), ('stderr', '.stderr.log'))}
    gates.require(all(not p.exists() for p in paths.values()), 'launcher output already exists')
    gates.require(out.parent.is_dir(), 'bounded work root must already exist')
    argv = [sys.executable, '-B', str(Path(runner.__file__).resolve()), '--actual',
            '--data', data, '--reference', reference, '--out', str(out),
            '--reviewed-source-manifest', reviewed_source_manifest]
    environment = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
    receipt = dict(schema=1, status='STARTED', argv=argv, reviewed_source_manifest=reviewed_source_manifest,
        inner_wall_seconds=900, outer_wall_seconds=930, supervisor_term_at_seconds=924,
        termination_grace_seconds=3, cleanup_reap_deadline_seconds=929, final_receipt_reserve_seconds=1,
        old_pass_inherited=False, compile_executed=False, fullblock_pass=False)
    save(paths['receipt'], receipt)
    outer_timeout = False
    cleanup_incomplete = False
    with paths['stdout'].open('x') as stdout, paths['stderr'].open('x') as stderr:
        gates.require(time.monotonic() < execution_cutoff, 'outer execution cutoff expired during launch admission')
        child = subprocess.Popen(argv, cwd=ROOT, env=environment, stdout=stdout, stderr=stderr, start_new_session=True)
        receipt['pid'] = child.pid
        save(paths['receipt'], receipt)
        try:
            returncode = child.wait(timeout=max(.001, execution_cutoff - time.monotonic()))
            if time.monotonic() >= execution_cutoff:
                outer_timeout = True
                returncode, cleanup_incomplete = terminate_group(child, cleanup_deadline=cleanup_deadline)
            elif group_exists(child.pid):
                returncode, cleanup_incomplete = terminate_group(child, cleanup_deadline=cleanup_deadline)
        except subprocess.TimeoutExpired:
            outer_timeout = True
            returncode, cleanup_incomplete = terminate_group(child, cleanup_deadline=cleanup_deadline)
    result_path = out / 'RESULT.json'
    result = {}
    try:
        result = json.loads(result_path.read_text())
    except (OSError, ValueError) as error:
        receipt['result_read_error'] = repr(error)
    outer_timeout = outer_timeout or time.monotonic() >= deadline
    if outer_timeout or cleanup_incomplete:
        # A terminal PASS cannot survive the supervisor deadline. Preserve any
        # genuine pre-timeout physical seal as historical evidence, not acceptance.
        result.update(status='FAILED', failure_kind='OUTER_WALL_TIMEOUT' if outer_timeout else 'PROCESS_GROUP_CLEANUP_INCOMPLETE',
            acceptance_sealed=False, official_observed_node_pass=False, fullblock_pass=False,
            outer_wall_timeout=outer_timeout, cleanup_incomplete=cleanup_incomplete, returncode=returncode)
        result.setdefault('actual_outputs_sealed', False)
        if out.is_dir():
            save(result_path, result)
    passed = not outer_timeout and not cleanup_incomplete and returncode == 0 and result.get('acceptance_sealed') is True and \
        result.get('status') == 'PASS_M128_OFFICIAL_OBSERVED_ATTENTION_PC12_HELD'
    receipt.update(status='PASS' if passed else 'FAILED', returncode=returncode,
        outer_timeout=outer_timeout, elapsed_seconds=time.monotonic() - started,
        cleanup_incomplete=cleanup_incomplete, child_status=result.get('status'), acceptance_sealed=passed)
    save(paths['receipt'], receipt)
    print(json.dumps(receipt, sort_keys=True), flush=True)
    return 0 if passed else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--actual', action='store_true')
    parser.add_argument('--data')
    parser.add_argument('--reference')
    parser.add_argument('--out')
    parser.add_argument('--reviewed-source-manifest')
    args = parser.parse_args(argv)
    if not args.actual:
        gates.require(all(v is None for v in (args.data, args.reference, args.out, args.reviewed_source_manifest)),
                      'actual arguments require explicit --actual')
        return runner.main([])
    gates.require(all(v is not None for v in (args.data, args.reference, args.out, args.reviewed_source_manifest)),
                  '--actual requires paths and independently reviewed current source manifest')
    return supervise(args.out, args.data, args.reference, args.reviewed_source_manifest)


if __name__ == '__main__':
    raise SystemExit(main())
