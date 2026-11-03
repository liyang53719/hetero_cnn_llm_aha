"""The only public export boundary: three bounded, explicitly typed JSON files.

No internal receipt is passed through. Callers construct these records explicitly.
This module neither uploads artifacts nor imports a numerical framework.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

TENSOR_ORDER = ('hidden_native', 'hidden_storage', 'positions', 'rope_cos', 'rope_sin', 'causal_mask', 'baseline_output', 'baseline_cache.keys', 'baseline_cache.values', 'stage.input_layernorm.0', 'stage.self_attn.q_proj.0', 'stage.self_attn.k_proj.0', 'stage.self_attn.v_proj.0', 'stage.self_attn.o_proj.0', 'stage.self_attn.0.0', 'stage.self_attn.0.1', 'stage.post_attention_layernorm.0', 'stage.mlp.gate_proj.0', 'stage.mlp.up_proj.0', 'stage.mlp.down_proj.0', 'stage.mlp.0', 'final_cache.keys', 'final_cache.values', 'output_storage')
TENSOR_NAMES = frozenset(TENSOR_ORDER)
CANDIDATE_ID = 'P0_QWEN2_FULL128_DEFAULT_REFERENCE_V1'
REPAIR_CANDIDATE_ID = 'P0_QWEN2_FULL128_DEFAULT_REFERENCE_REPAIR_41720209902_V1'
FILENAMES = ('RESULT.json', 'CHECKS.json', 'HOST_RESOURCES.json')
GIB = 1024 ** 3
MIB = 1024 ** 2
MAX_FILE_BYTES = 65536
MAX_TOTAL_BYTES = 131072
MAX_MEASURED_BYTES = 1024 ** 5
MAX_MEASURED_SECONDS = 86400
STAGE_BUDGETS = {
    'runtime': (1800, 1800, 3 * GIB, 6 * GIB),
    'weights': (600, 120, 512 * MIB, 6 * GIB),
    'reference': (600, 1200, 3 * GIB, 160 * MIB),
    'rope': (120, 120, GIB, 16 * MIB),
    'finalize': (60, 60, 256 * MIB, 6 * GIB),
}
REASONS = frozenset(('PRECHECK_PIN', 'ABI', 'CPU_PROOF', 'RESOURCE_ADMISSION',
    'INSTALL', 'WEIGHT_HASH', 'REFERENCE_HASH', 'REFERENCE_GEOMETRY',
    'REFERENCE_INVENTORY', 'ROPE_HASH', 'LIMIT', 'OWNERSHIP_INCOMPLETE', 'EXPORT_SCHEMA'))
from weight_errors import WEIGHT_FAILURE_REASONS
REASONS = REASONS | WEIGHT_FAILURE_REASONS
RESULT_FIELDS = frozenset(('schema', 'candidate_id', 'status', 'reason',
    'candidate_source_sha256', 'frozen_manifest_sha256', 'runtime_receipt_sha256',
    'weight_expected', 'weight_checked', 'tensor_expected', 'tensor_checked',
    'first_mismatch_name', 'all_visible_exact', 'hardware_executed',
    'dut_numerical_pass', 'raw_payloads_uploaded', 'internal_op_order_proven'))
CHECK_FIELDS = frozenset(('name', 'status', 'expected_bytes', 'observed_bytes',
    'expected_sha256', 'observed_sha256', 'shape_equal', 'dtype_equal'))
HOST_FIELDS = frozenset(('schema', 'architecture', 'python_implementation',
    'python_version', 'python_sha256', 'cpu_affinity_count', 'cpu_evidence_sha256',
    'isa', 'requested_capability', 'observed_capability', 'requested_threads',
    'observed_threads', 'requested_interop', 'observed_interop',
    'initial_free_bytes', 'minimum_free_bytes', 'mem_available_bytes', 'stages',
    'job_wall_seconds', 'job_cpu_seconds', 'job_wall_budget_seconds', 'job_cpu_budget_seconds'))
STAGE_FIELDS = frozenset(('name', 'status', 'wall_seconds', 'cpu_seconds',
    'peak_rss_bytes', 'disk_bytes', 'wall_budget_seconds', 'cpu_budget_seconds',
    'rss_budget_bytes', 'disk_budget_bytes', 'native_exit', 'cleanup',
    'pipe_eof', 'gzip_finalized'))
COMPLETE_CLEANUP = 'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'


class ExportError(ValueError):
    """Only an enum-like message is emitted, never offending content."""


def require(ok):
    if not ok:
        raise ExportError('EXPORT_SCHEMA')


def exact(value, fields):
    require(type(value) is dict and set(value) == set(fields))


def enum(value, values, nullable=False):
    require((nullable and value is None) or (type(value) is str and value in values))


def integer(value, low, high, nullable=False):
    require((nullable and value is None) or (type(value) is int and low <= value <= high))


def number(value, high, nullable=False):
    require((nullable and value is None) or
            (type(value) in (float, int) and 0 <= value <= high and math.isfinite(value)))


def boolean(value, nullable=False):
    require(type(value) is bool or (nullable and value is None))


def digest(value, nullable=False):
    require((nullable and value is None) or
            (type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None))


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=True, allow_nan=False) + '\n').encode('utf-8')


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        require(key not in out)
        out[key] = value
    return out


def _reject_constant(_):
    raise ExportError('EXPORT_SCHEMA')


def _decode(raw):
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                          parse_constant=_reject_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise ExportError('EXPORT_SCHEMA') from None


def _frozen(frozen):
    if type(frozen) is dict:
        raw = canonical(frozen)
        data = frozen
    else:
        path = Path(frozen)
        require(not path.is_symlink() and path.is_file())
        raw = path.read_bytes()
        data = _decode(raw)
    fixture = data['frozen_fixture']
    records = fixture['tensor_records']
    require(type(records) is dict and set(records) == TENSOR_NAMES)
    pins = dict(records)
    pins['rope1024'] = fixture['rope1024']
    for name, pin in pins.items():
        require(type(name) is str and re.fullmatch('[a-z][a-z0-9_.]{0,63}', name))
        integer(pin['bytes'], 0, 128 * MIB)
        digest(pin['sha256'])
    return pins, hashlib.sha256(raw).hexdigest()


def frozen_digest(frozen):
    return _frozen(frozen)[1]


def validate_records(result, checks, host, frozen):
    """Validate complete records and cross-file semantic consistency."""
    pins, frozen_sha = _frozen(frozen)
    exact(result, RESULT_FIELDS)
    enum(result['schema'], ('P0_PORTABLE_REFERENCE_RESULT_V1',))
    enum(result['candidate_id'], (CANDIDATE_ID, REPAIR_CANDIDATE_ID))
    enum(result['status'], ('PASS_EXACT_VISIBLE_FIXTURE', 'FAIL', 'INCOMPLETE', 'NOT_STARTED'))
    enum(result['reason'], REASONS, nullable=True)
    require((result['reason'] is None) == (result['status'] in ('PASS_EXACT_VISIBLE_FIXTURE', 'NOT_STARTED')))
    digest(result['candidate_source_sha256'], nullable=True)
    digest(result['runtime_receipt_sha256'], nullable=True)
    require(result['frozen_manifest_sha256'] == frozen_sha)
    integer(result['weight_expected'], 12, 12)
    integer(result['weight_checked'], 0, 12)
    integer(result['tensor_expected'], 25, 25)
    integer(result['tensor_checked'], 0, 25)
    enum(result['first_mismatch_name'], pins, nullable=True)
    boolean(result['all_visible_exact'])
    for key in ('hardware_executed', 'dut_numerical_pass', 'raw_payloads_uploaded', 'internal_op_order_proven'):
        require(result[key] is False)
    exact(checks, ('schema', 'frozen_manifest_sha256', 'weight_checked', 'weight_mismatch_count', 'checks'))
    enum(checks['schema'], ('P0_PORTABLE_REFERENCE_CHECKS_V1',))
    require(checks['frozen_manifest_sha256'] == frozen_sha)
    integer(checks['weight_checked'], 0, 12)
    integer(checks['weight_mismatch_count'], 0, 1)
    require(checks['weight_mismatch_count'] <= checks['weight_checked'])
    require(checks['weight_checked'] == result['weight_checked'])
    rows = checks['checks']
    require(type(rows) is list and len(rows) == 25)
    mismatches = []
    reached = 0
    # Inventory order is fixed for serialization, but execution order need not be.
    for row, (name, pin) in zip(rows, pins.items()):
        exact(row, CHECK_FIELDS)
        require(row['name'] == name)
        enum(row['status'], ('PASS', 'MISMATCH', 'NOT_REACHED'))
        integer(row['expected_bytes'], 0, 128 * MIB)
        require(row['expected_bytes'] == pin['bytes'])
        require(row['expected_sha256'] == pin['sha256'])
        integer(row['observed_bytes'], 0, 128 * MIB, nullable=True)
        digest(row['observed_sha256'], nullable=True)
        boolean(row['shape_equal'], nullable=True)
        boolean(row['dtype_equal'], nullable=True)
        measured = ('observed_bytes', 'observed_sha256', 'shape_equal', 'dtype_equal')
        if row['status'] == 'NOT_REACHED':
            require(all(row[k] is None for k in measured))
        else:
            reached += 1
            same = (row['observed_bytes'] == pin['bytes'] and
                    row['observed_sha256'] == pin['sha256'] and
                    row['shape_equal'] is True and row['dtype_equal'] is True)
            if row['status'] == 'PASS':
                require(same)
            else:
                require(not same and any(row[k] is not None for k in measured))
                mismatches.append(name)
    # Runtime saves in this original, fixed order, irrespective of JSON key order.
    by_name = {r['name']: r for r in rows}
    halted = False
    for name in (*TENSOR_ORDER, 'rope1024'):
        status = by_name[name]['status']
        if halted:
            require(status == 'NOT_REACHED')
        if status != 'PASS':
            halted = True
    require(len(mismatches) <= 1)
    require(result['tensor_checked'] == reached)
    require(result['first_mismatch_name'] == (mismatches[0] if mismatches else None))
    require(result['all_visible_exact'] == (all(r['status'] == 'PASS' for r in rows)))
    exact(host, HOST_FIELDS)
    enum(host['schema'], ('P0_PORTABLE_REFERENCE_HOST_V1',))
    enum(host['architecture'], ('x86_64', 'aarch64', 'i386', 'i686', 'armv7l', 'ppc64le', 's390x', 'OTHER'), True)
    enum(host['python_implementation'], ('CPython', 'PyPy', 'OTHER'), True)
    require(host['python_version'] is None or
            (type(host['python_version']) is str and re.fullmatch(r'[23]\.[0-9]{1,2}\.[0-9]{1,3}', host['python_version'])))
    digest(host['python_sha256'], True)
    digest(host['cpu_evidence_sha256'], True)
    integer(host['cpu_affinity_count'], 1, 65536, True)
    exact(host['isa'], ('sse2', 'avx', 'avx2', 'avx512f'))
    for value in host['isa'].values():
        boolean(value, True)
    enum(host['requested_capability'], ('default',))
    enum(host['observed_capability'], ('DEFAULT', 'AVX2', 'AVX512', 'OTHER'), True)
    integer(host['requested_threads'], 4, 4)
    integer(host['requested_interop'], 1, 1)
    integer(host['observed_threads'], 1, 65536, True)
    integer(host['observed_interop'], 1, 65536, True)
    for key in ('initial_free_bytes', 'minimum_free_bytes', 'mem_available_bytes'):
        integer(host[key], 0, MAX_MEASURED_BYTES, True)
    if host['initial_free_bytes'] is not None and host['minimum_free_bytes'] is not None:
        require(host['minimum_free_bytes'] <= host['initial_free_bytes'])
    for key in ('job_wall_seconds', 'job_cpu_seconds'):
        number(host[key], MAX_MEASURED_SECONDS, True)
    for key in ('job_wall_budget_seconds', 'job_cpu_budget_seconds'):
        integer(host[key], 3600, 3600)
    stages = host['stages']
    require(type(stages) is list and len(stages) == 5)
    stopped = False
    for row, (name, budgets) in zip(stages, STAGE_BUDGETS.items()):
        exact(row, STAGE_FIELDS)
        require(row['name'] == name)
        enum(row['status'], ('PASS', 'FAIL', 'INCOMPLETE', 'NOT_REACHED'))
        if stopped:
            require(row['status'] == 'NOT_REACHED')
        if row['status'] != 'PASS':
            stopped = True
        for key, bound in zip(('wall_budget_seconds', 'cpu_budget_seconds', 'rss_budget_bytes', 'disk_budget_bytes'), budgets):
            integer(row[key], bound, bound)
        for key in ('wall_seconds', 'cpu_seconds'):
            number(row[key], MAX_MEASURED_SECONDS, True)
        for key in ('peak_rss_bytes', 'disk_bytes'):
            integer(row[key], 0, MAX_MEASURED_BYTES, True)
        integer(row['native_exit'], -255, 255, True)
        enum(row['cleanup'], (COMPLETE_CLEANUP, 'INCOMPLETE', 'NOT_REACHED'))
        for key in ('pipe_eof', 'gzip_finalized'):
            enum(row[key], ('COMPLETE', 'INCOMPLETE', 'NOT_REACHED'))
        if row['status'] == 'NOT_REACHED':
            require(all(row[k] is None for k in ('wall_seconds', 'cpu_seconds', 'peak_rss_bytes', 'disk_bytes', 'native_exit')))
            require(all(row[k] == 'NOT_REACHED' for k in ('cleanup', 'pipe_eof', 'gzip_finalized')))
        if row['status'] == 'PASS':
            require(row['native_exit'] == 0 and row['cleanup'] == COMPLETE_CLEANUP)
            require(row['pipe_eof'] == row['gzip_finalized'] == 'COMPLETE')
            for key, bound in zip(('wall_seconds', 'cpu_seconds', 'peak_rss_bytes', 'disk_bytes'), budgets):
                require(row[key] is not None and row[key] <= bound)
    if result['status'] == 'NOT_STARTED':
        require(reached == 0 and result['weight_checked'] == 0)
        require(all(s['status'] == 'NOT_REACHED' for s in stages))
    if result['status'] == 'PASS_EXACT_VISIBLE_FIXTURE':
        require(result['all_visible_exact'] and result['weight_checked'] == 12 and checks['weight_mismatch_count'] == 0)
        for key in ('job_wall_seconds', 'job_cpu_seconds'):
            require(host[key] is not None and host[key] <= 3600)
        require(result['candidate_source_sha256'] is not None and result['runtime_receipt_sha256'] is not None)
        require(all(s['status'] == 'PASS' for s in stages))
        require(host['architecture'] == 'x86_64' and host['python_implementation'] == 'CPython')
        require(host['python_version'] is not None and host['python_version'].startswith('3.12.'))
        require(host['observed_capability'] == 'DEFAULT' and host['observed_threads'] == 4 and host['observed_interop'] == 1)
        require(all(host[k] is not None for k in ('python_sha256', 'cpu_evidence_sha256', 'cpu_affinity_count', 'initial_free_bytes', 'minimum_free_bytes', 'mem_available_bytes')))
        require(all(type(v) is bool for v in host['isa'].values()))
        require(host['initial_free_bytes'] >= 8 * GIB and host['minimum_free_bytes'] >= 3 * GIB // 2)
    return True


def _open_dir(path):
    path = Path(path).absolute()
    # Reject symlinks in every existing ancestor, including the final directory.
    for node in (path, *path.parents):
        require(not node.is_symlink())
    return os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)


def validate_exports(output, frozen):
    """Read exactly three regular, single-link files without following symlinks."""
    fd = _open_dir(output)
    try:
        require(set(os.listdir(fd)) == set(FILENAMES))
        records = []
        total = 0
        inodes = set()
        for name in FILENAMES:
            file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            try:
                info = os.fstat(file_fd)
                require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1)
                require(0 < info.st_size <= MAX_FILE_BYTES)
                inode = (info.st_dev, info.st_ino)
                require(inode not in inodes)
                inodes.add(inode)
                raw = b''
                while len(raw) <= MAX_FILE_BYTES:
                    chunk = os.read(file_fd, min(8192, MAX_FILE_BYTES + 1 - len(raw)))
                    if not chunk:
                        break
                    raw += chunk
                require(len(raw) <= MAX_FILE_BYTES and len(raw) == info.st_size)
                total += len(raw)
                require(total <= MAX_TOTAL_BYTES)
                records.append(_decode(raw))
            finally:
                os.close(file_fd)
        validate_records(*records, frozen)
        return dict(zip(FILENAMES, records))
    finally:
        os.close(fd)


def write_exports(output, result, checks, host, frozen):
    """Write a fresh directory only; refuse overwrites and partial prior exports."""
    validate_records(result, checks, host, frozen)
    payloads = [canonical(x) for x in (result, checks, host)]
    require(all(len(x) <= MAX_FILE_BYTES for x in payloads))
    require(sum(map(len, payloads)) <= MAX_TOTAL_BYTES)
    path = Path(output).absolute()
    for node in path.parents:
        require(not node.is_symlink())
    path.mkdir(mode=0o700, exist_ok=False)
    fd = _open_dir(path)
    try:
        for name, raw in zip(FILENAMES, payloads):
            out = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
            with os.fdopen(out, 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        os.fsync(fd)
    finally:
        os.close(fd)
    return validate_exports(path, frozen)
