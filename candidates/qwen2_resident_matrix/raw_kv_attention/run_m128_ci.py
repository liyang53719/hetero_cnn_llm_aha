#!/usr/bin/env python3
"""Separate opt-in synthetic M128 numerical wrapper; never builds a library.

One 2400-second total includes five seconds for process-group cleanup and one
for the three safe receipts. No retry, native fallback, RTL or model-cycle claim.
The frozen child atomically emits schema-checked progress during execution;
the wrapper validates it again after process-group cleanup on every outcome.
"""
import argparse
import json
import os
from pathlib import Path
import stat
import time

from . import run_numeric_ci as common
from . import run_calibration_ci as calibration
from .streaming import profile

TOTAL_SECONDS = 2400
CHILD_MODULE = 'candidates.qwen2_resident_matrix.raw_kv_attention.m128_numeric'
PASS_STATUS = 'PASS_M128_SYNTHETIC_ATTENTION'
OUTPUTS = (*common.OUTPUTS, 'progress.json')
MAX_PROGRESS_BYTES = 1024
PHASE_LOAN = dict(preflight=None, reference=None, direct=False, loan=True, complete=True)


def source_snapshot():
    from . import m128_numeric
    sources = m128_numeric.source_snapshot()
    common.need(type(sources) is dict and len(sources) == 71, 'numeric_closure')
    required = ('.github/workflows/raw-kv-attention-m128.yml',
        *(common.PREFIX + name for name in ('m128_numeric.py', 'test_m128_numeric.py',
          'run_m128_ci.py', 'test_m128_ci.py', 'run_calibration_ci.py', 'test_calibration_ci.py')))
    common.need(all(name in sources for name in required), 'numeric_closure')
    return sources


def validate_child(raw, *, expected_sources, expected_native):
    return calibration._validate_profile_child(raw, expected_sources=expected_sources,
        expected_native=expected_native, tokens_expected=(128,), status=PASS_STATUS,
        m128=True, seconds_ceiling=2400)


def validate_progress(raw):
    """Progress is bounded counters only; no progress value can grant PASS."""
    common.need(type(raw) is bytes and len(raw) <= MAX_PROGRESS_BYTES, 'progress_size')
    value = common.read_json(raw.decode('utf-8'))
    common.exact_keys(value, ('schema', 'status', 'phase', 'tokens', 'loan', 'events',
        'scalar_operations', 'matrix_packets', 'elapsed_seconds', 'sequence'))
    calibration._same(value['schema'], 1)
    calibration._same(value['status'], 'PROGRESS')
    calibration._same(value['tokens'], 128)
    common.need(type(value['phase']) is str and value['phase'] in PHASE_LOAN, 'progress_phase')
    calibration._same(value['loan'], PHASE_LOAN[value['phase']])
    work = profile(128)
    common.integer(value['events'], 0, 32 * work['matrix_packets'] + 10000)
    common.integer(value['scalar_operations'], 0, work['scalar_total_no_cutoff'])
    common.integer(value['matrix_packets'], 0, work['matrix_packets'])
    common.integer(value['sequence'], 1, 1024)
    calibration._seconds(value['elapsed_seconds'], 2400)
    if value['phase'] in ('preflight', 'reference'):
        for name in ('events', 'scalar_operations', 'matrix_packets'):
            calibration._same(value[name], 0)
    if value['phase'] == 'complete':
        common.integer(value['events'], 1, 32 * work['matrix_packets'] + 10000)
        calibration._same(value['scalar_operations'], work['scalar_total_no_cutoff'])
        calibration._same(value['matrix_packets'], work['matrix_packets'])
    return value


def read_progress(path):
    """Bounded regular-file read; refuse symlinks, devices and FIFO blocking."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        common.need(stat.S_ISREG(info.st_mode) and info.st_size <= MAX_PROGRESS_BYTES, 'progress_size')
        return validate_progress(os.read(fd, MAX_PROGRESS_BYTES + 1))
    finally:
        os.close(fd)


def _complete(progress, result):
    common.need(progress['phase'] == 'complete', 'progress_incomplete')
    final = result['profiles'][0]['passes'][1]
    for key, field in (('events', 'events'), ('scalar_operations', 'scalar_checkpoints')):
        calibration._same(progress[key], final[field])
    calibration._same(progress['matrix_packets'], final['matrix']['count'])


def write_evidence(out, summary, hashes):
    """Retain latest validated partial progress, even when the child fails."""
    # The child may be killed between writing and renaming this exact staging
    # file. Unlink that entry itself, including a symlink, never its target.
    (out / 'progress.pending').unlink(missing_ok=True)
    path = out / 'progress.json'
    try:
        progress = read_progress(path)
    except (OSError, ValueError, UnicodeError, KeyError, TypeError):
        progress = dict(schema=1, status='NOT_AVAILABLE', reason='missing_or_invalid_progress')
    if summary['status'] == PASS_STATUS:
        try:
            _complete(progress, summary['result'])
        except (ValueError, KeyError, TypeError):
            summary.update(status='FAIL', reason='progress_incomplete')
            summary.pop('result', None)
    # A bad child path is never followed. Replace a symlink itself safely;
    # refuse other unexpected entries through the common three-file allowlist.
    temporary = out / 'progress.json.tmp'
    common.need(not temporary.exists() and not temporary.is_symlink(), 'unsafe_output')
    raw = (json.dumps(progress, sort_keys=True, allow_nan=False) + '\n').encode()
    common.need(len(raw) <= MAX_PROGRESS_BYTES, 'progress_size')
    with temporary.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    directory = os.open(out, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    common.save(out, summary, hashes, extra_outputs=('progress.json',))


def run(out, environ=None):
    deadline_ns = time.monotonic_ns() + int(TOTAL_SECONDS * 1_000_000_000)
    env = dict(os.environ if environ is None else environ)
    progress = Path(out).resolve() / 'progress.json'
    def validator(raw):
        result = validate_child(raw, expected_sources=source_snapshot(),
                                expected_native=common.library_snapshot(env)[2])
        _complete(read_progress(progress), result)
        return result
    return common.run(out, env, child_module=CHILD_MODULE,
        child_args=('--run-m128', '--progress', str(progress)),
        validator=validator, snapshot=source_snapshot, total_seconds=TOTAL_SECONDS,
        deadline_ns=deadline_ns, budget_ceiling=2400, pass_statuses=(PASS_STATUS,),
        evidence_writer=write_evidence)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        code, summary = run(args.out)
    except BaseException:
        code, summary = 1, common.safe_summary('FAIL', 'runner_setup_or_receipt_failed')
        summary['total_budget_seconds'] = TOTAL_SECONDS
    print(json.dumps(summary, sort_keys=True, allow_nan=False))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
