#!/usr/bin/env python3
"""M4/M8-only calibration inside the remaining shared numerical-step deadline.

Never allocates a new 120-second window, builds a library, or enables M128.
The verified common wrapper owns all process cleanup, hashes and two-file I/O.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time

from . import run_numeric_ci as common
from . import profile_numeric
from .streaming import profile

CHILD_MODULE = 'candidates.qwen2_resident_matrix.raw_kv_attention.profile_numeric'
WRAPPER_INPUTS = tuple(common.PREFIX + name for name in ('run_calibration_ci.py', 'test_calibration_ci.py'))


def manifest_sha256(sources):
    return hashlib.sha256(json.dumps(sources, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def source_snapshot():
    sources = profile_numeric.source_snapshot()
    common.need(len(sources) == 64, 'numeric_closure')
    for name in WRAPPER_INPUTS:
        sources[name] = common.digest(common.repository_path(name))
    return dict(sorted(sources.items()))


def _same(actual, expected):
    """Exact keys, values and canonical types; bool is never an integer count."""
    common.need(type(actual) is type(expected), 'child_schema')
    if type(expected) is dict:
        common.exact_keys(actual, expected)
        for name, value in expected.items():
            _same(actual[name], value)
    else:
        common.need(actual == expected, 'child_counter')


def _sha(value):
    common.need(type(value) is str and re.fullmatch(r'[0-9a-f]{64}', value) is not None, 'child_schema')


def _seconds(value, ceiling=120):
    common.need(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= ceiling, 'child_counter')


def _digest(value, kind, count, byte_count, *, writes=False):
    common.exact_keys(value, ('version', 'kind', 'count', 'bytes', 'sha256',
                              *(('reads', 'writes', 'metadata') if writes else ())))
    _same(value['version'], 'raw-kv-stream-v1')
    _same(value['kind'], kind)
    _same(value['count'], count); _same(value['bytes'], byte_count)
    _sha(value['sha256'])
    if writes:
        _same(value['reads'], 0); _same(value['writes'], count)
        _digest(value['metadata'], 'core-metadata', count, count * 17)


def validate_child(raw, *, expected_sources, expected_native):
    """Allow only complete M4 then M8 direct/loan equality with safe telemetry."""
    return _validate_profile_child(raw, expected_sources=expected_sources,
        expected_native=expected_native, tokens_expected=(4, 8),
        status='PASS_CALIBRATION_ONLY', m128=False, seconds_ceiling=120)


def _validate_profile_child(raw, *, expected_sources, expected_native,
                            tokens_expected, status, m128, seconds_ceiling):
    """Shared strict schema; public entrypoints select fixed, separate scopes."""
    common.need(type(raw) is bytes and len(raw) <= common.MAX_CHILD_BYTES, 'child_size')
    value = common.read_json(raw.decode('utf-8'))
    common.exact_keys(value, ('status', 'profiles', 'm128_executed', 'hardware_simulation',
        'model_ticks_are_hardware_cycles', 'process_peak_rss_kib', 'source_manifest_sha256',
        'native_hashes', 'inputs_unchanged'))
    _same(value['status'], status)
    _same(value['m128_executed'], m128)
    for name in ('hardware_simulation', 'model_ticks_are_hardware_cycles'):
        _same(value[name], False)
    _same(value['inputs_unchanged'], True)
    common.integer(value['process_peak_rss_kib'], 1, 1 << 31)
    _sha(value['source_manifest_sha256'])
    _same(value['source_manifest_sha256'], manifest_sha256(expected_sources))
    common.exact_keys(value['native_hashes'], ('library_sha256', 'receipt_sha256'))
    for name in ('library_sha256', 'receipt_sha256'):
        _sha(value['native_hashes'][name]); _same(value['native_hashes'][name], expected_native[name])
    common.need(type(value['profiles']) is list and len(value['profiles']) == len(tokens_expected), 'child_cases')
    for tokens, case in zip(tokens_expected, value['profiles']):
        common.exact_keys(case, ('tokens', 'status', 'reference_seconds', 'reference_bytes', 'work', 'passes'))
        _same(case['tokens'], tokens); _same(case['status'], 'PASS')
        _seconds(case['reference_seconds'], seconds_ceiling)
        expected_bytes = 7 * 12 * (tokens * (tokens + 1) // 2) * 4 + 3 * tokens * 12 * 4 + 2 * tokens * 1536 * 4
        _same(case['reference_bytes'], expected_bytes)
        work = profile(tokens)
        _same(case['work'], work)
        common.need(type(case['passes']) is list and len(case['passes']) == 2, 'child_cases')
        for loan, run in zip((False, True), case['passes']):
            common.exact_keys(run, ('loan', 'seconds', 'events', 'scalar', 'matrix', 'core', 'writes',
                'accepted_matrix', 'useful_macs', 'executed_macs', 'scalar_checkpoints',
                'ddr_read_count', 'ddr_write_count', *(('kv',) if loan else ())))
            _same(run['loan'], loan); _seconds(run['seconds'], seconds_ceiling)
            common.integer(run['events'], 1, 32 * work['matrix_packets'] + 10000)
            _digest(run['scalar'], 'scalar', work['scalar_total_no_cutoff'], 14 * work['scalar_total_no_cutoff'])
            _digest(run['matrix'], 'matrix-results', work['matrix_packets'], 16398 * work['matrix_packets'])
            _digest(run['core'], 'core-metadata', work['core_memory_requests'], 17 * work['core_memory_requests'])
            _digest(run['writes'], 'memory-requests', work['output_writes'], 90 * work['output_writes'], writes=True)
            counts = {name: 1 if name.startswith('owner_') else
                work['matrix_groups'] if name in ('normal_groups', 'normal_done') else work['matrix_packets']
                for name in common.MATRIX_COUNTERS}
            _same(run['accepted_matrix'], counts)
            for name, expected in (('useful_macs', work['useful_fmas']), ('executed_macs', work['native_fmas']),
                    ('scalar_checkpoints', work['scalar_total_no_cutoff']), ('ddr_write_count', work['output_writes']),
                    ('ddr_read_count', work['loan_ddr_reads'] if loan else work['q_reads'] + work['kv_reads'])):
                _same(run[name], expected)
            if loan:
                _same(run['kv'], dict(core_requests=work['kv_reads'], ddr_requests=work['unique_kv_lines'],
                    hits=work['kv_hits'], fills=work['unique_kv_lines'], releases=1))
        for name in ('scalar', 'matrix', 'core', 'writes', 'accepted_matrix', 'useful_macs',
                     'executed_macs', 'scalar_checkpoints', 'ddr_write_count'):
            _same(case['passes'][0][name], case['passes'][1][name])
    return value


def run(out, *, deadline_ns, environ=None):
    common.need(type(deadline_ns) is int and 0 < deadline_ns < 1 << 63, 'total_budget')
    remaining = min(120., (deadline_ns - time.monotonic_ns()) / 1_000_000_000)
    if remaining <= common.CLEANUP_SECONDS + common.RECEIPT_SECONDS:
        # No process or unbounded preparation is started when cleanup would
        # consume the remaining window. Do not extend an exhausted deadline
        # with filesystem I/O; the CLI still returns this fixed safe receipt.
        summary = common.safe_summary('NOT_RUN', 'shared_budget_exhausted')
        summary.update(total_budget_seconds=max(0., remaining), wall_seconds=0.)
        return 2, summary
    env = dict(os.environ if environ is None else environ)
    def validator(raw):
        return validate_child(raw, expected_sources=profile_numeric.source_snapshot(),
                              expected_native=common.library_snapshot(env)[2])
    return common.run(out, env, child_module=CHILD_MODULE, child_args=('--calibrate',),
                      validator=validator, snapshot=source_snapshot,
                      total_seconds=remaining, deadline_ns=deadline_ns)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--deadline-ns', type=int, required=True)
    args = parser.parse_args(argv)
    try:
        code, summary = run(args.out, deadline_ns=args.deadline_ns)
    except BaseException:
        code, summary = 1, common.safe_summary('FAIL', 'runner_setup_or_receipt_failed')
    print(json.dumps(summary, sort_keys=True, allow_nan=False))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
