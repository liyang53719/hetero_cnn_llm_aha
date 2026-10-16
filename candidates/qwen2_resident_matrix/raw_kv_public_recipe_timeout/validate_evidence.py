"""Cold, fail-closed validation of one immutable failed-run evidence archive.

This module imports only the standard library and never executes setup, numerical,
Scala, RTL, native, network, subprocess, or Git work. Valid evidence is a TIMEOUT,
not a numerical acceptance result. Hash identity does not authenticate GitHub.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

HERE = Path(__file__).resolve().parent
CHECKOUT = 'ac3a074cd0e29342447844a7675425af628a39ef'
CONTRACT = '3fb70fe4016b226bca41cf82bd8ca4e34845575f1216fe3c45af2d2108cce271'
ZIP_SHA256 = '85b9554eaedf9904760d1da4363470903dbd04e32c72016c131c55e9c89d4855'
ZIP_BYTES = 15278
ELAPSED = 2587.336054
MEMBERS = {
    'summary.json': (1195, '37dec6d87998010ba7726a6ed17853a8216cb0318f0fdba89364187f414f171d'),
    'progress.json': (80, '513dcd1280fd8380ec7ddcfa7f8f08b24e0f994a76e0284ddc8d461dfa68cdb0'),
    'source_hashes.json': (39391, '0632730cb3a5fbe10cd713f613e23ed41d91cafc24579481ce87ab71ef1aca26'),
}
KEYSETS = {
    'generated_sha256': (12, 'e970a684417c8a0cbcc5b04ec2298b1e1db4041540a549872b883c94b22d308a'),
    'source_sha256': (283, 'e56e1942d457f58a648ac66b5f5ecc3e224e241f91bdf20ae8df5f09e3223a55'),
}
PROGRESS = {'schema': 1, 'status': 'TIMEOUT', 'phase': 'numeric', 'elapsed_seconds': ELAPSED}
SUMMARY = dict(PROGRESS, checkout_commit=CHECKOUT, clone_started=True,
    cpu_eligibility={
        'backend_qualified': False, 'eligibility_only': True,
        'excluded_flags': {'amx_bf16': False, 'amx_int8': False, 'amx_tile': False},
        'flags': {'avx512_bf16': True, 'avx512bw': True, 'avx512dq': True,
                  'avx512f': True, 'avx512vl': True, 'fma': True},
        'processor_records': 4, 'schema': 1, 'status': 'ELIGIBLE_FOR_BACKEND_CHECK'},
    diagnostic={'exception': 'TimeoutExpired', 'frames': [
        {'line': 608, 'source': 'candidates/qwen2_resident_matrix/raw_kv_public_recipe_run/run_ci.py'},
        {'line': 222, 'source': 'candidates/qwen2_resident_matrix/raw_kv_public_recipe_run/run_ci.py'},
        {'line': 198, 'source': 'candidates/qwen2_resident_matrix/raw_kv_public_fresh/setup.py'},
    ], 'phase': 'numeric'},
    enable_raw_kv=True, fresh_profile=True, full_29_node_acceptance=False,
    launch_contract_sha256=CONTRACT, numeric_started=True, numerical_acceptance=False,
    postflight_complete=False, profile='qwen2-public-paired-m128-linked-launch-v1',
    rows=128, rtl_executed=False, scala_executed=False, setup_started=True)
CHECKPOINT = {
    'schema': 1,
    'checkpoint_kind': 'FAILED_RUN_TIMEOUT',
    'original_run': {'run_id': '38952336951', 'job_id': '117146548710',
                     'artifact_id': '12071740663', 'checkout_commit': CHECKOUT},
    'archive': {'filename': 'public-m128-numeric-timeout.zip', 'bytes': ZIP_BYTES,
                'sha256': ZIP_SHA256},
    'members': {name: {'bytes': size, 'sha256': digest}
                for name, (size, digest) in MEMBERS.items()},
    'recorded_facts': {
        'status': 'TIMEOUT', 'phase': 'numeric', 'elapsed_seconds': ELAPSED,
        'numeric_started': True, 'postflight_complete': False,
        'numerical_acceptance': False, 'full_29_node_acceptance': False,
        'scala_executed': False, 'rtl_executed': False,
        'cpu_eligibility_only': True, 'cpu_backend_qualified': False,
        'source_entries': 283, 'generated_entries': 12,
        'launch_contract_sha256': CONTRACT,
    },
    'setup_completion': {
        'classification': 'SOURCE_ORDER_INFERENCE_ONLY',
        'basis': 'The runner enters numeric only after its setup success checks.',
        'native_private_receipt_preserved': False,
        'independent_setup_or_native_verification': False,
    },
    'limits': {
        'numerical_result': 'No numerical acceptance; the numeric phase timed out.',
        'postflight': 'Postflight did not complete; no final acceptance receipt is preserved.',
        'setup': 'Setup completion is a source-order inference, not a preserved native receipt.',
        'source_manifest': 'Source hashes identify the historical run; no claim that the current tree matches.',
        'provenance': 'Run, job, and artifact IDs are supplied provenance; SHA256 anchors supplied ZIP bytes.',
        'data': 'Only the three safe JSON members are preserved; no weights, numerical arrays, or private logs.',
    },
}
LIMITS = {**{name: size for name, (size, _) in MEMBERS.items()}, 'checkpoint.json': 8192}
HEX64 = re.compile(r'[0-9a-f]{64}\Z')
SAFE_PATH = re.compile(r'[A-Za-z0-9_.\-/]+\Z')


class EvidenceError(ValueError):
    """The input is not the exact safe historical TIMEOUT evidence."""


def need(condition, message):
    # Never use assert: fail-closed checks must survive python -O.
    if not condition:
        raise EvidenceError(message)


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw, limit):
    need(type(raw) is bytes, 'input must be bytes')
    need(0 < len(raw) <= limit, 'empty or oversized JSON')

    def pairs(items):
        out = {}
        for key, value in items:
            need(key not in out, 'duplicate JSON field')
            out[key] = value
        return out

    def constant(value):
        raise EvidenceError('non-finite JSON number')

    def check(value, depth=0):
        need(depth <= 16, 'excessive JSON nesting')
        if type(value) is float:
            need(math.isfinite(value), 'non-finite JSON number')
        elif type(value) is dict:
            for nested in value.values():
                check(nested, depth + 1)
        elif type(value) is list:
            for nested in value:
                check(nested, depth + 1)

    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)
        check(value)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise EvidenceError('invalid strict JSON') from exc
    need(type(value) is dict, 'top level must be an object')
    return value


def exact(value, expected, path='root'):
    need(type(value) is type(expected), path + ': wrong type')
    if type(expected) is dict:
        need(value.keys() == expected.keys(), path + ': unknown or missing fields')
        for key in expected:
            exact(value[key], expected[key], path + '.' + key)
    elif type(expected) is list:
        need(len(value) == len(expected), path + ': wrong list length')
        for index, item in enumerate(expected):
            exact(value[index], item, path + '[' + str(index) + ']')
    else:
        need(value == expected, path + ': wrong known-failure value')


def validate_source_schema(value):
    need(type(value) is dict and set(value) == {'schema', 'launch_contract_sha256',
        'generated_sha256', 'source_sha256'}, 'source manifest fields')
    exact(value['schema'], 1, 'schema')
    exact(value['launch_contract_sha256'], CONTRACT, 'launch_contract_sha256')
    for name, (count, keyset_sha) in KEYSETS.items():
        entries = value[name]
        need(type(entries) is dict and len(entries) == count, name + ': wrong count/type')
        for path, digest in entries.items():
            need(type(path) is str and 0 < len(path) <= 256 and SAFE_PATH.fullmatch(path),
                 name + ': unsafe source path')
            posix = PurePosixPath(path)
            need(not posix.is_absolute() and '..' not in posix.parts and
                 str(posix) == path, name + ': non-canonical source path')
            need(type(digest) is str and HEX64.fullmatch(digest), name + ': invalid SHA256')
        keys = json.dumps(sorted(entries), ensure_ascii=True, separators=(',', ':')).encode('ascii')
        need(sha256(keys) == keyset_sha, name + ': unknown or missing source fields')


def validate_schema(name, value):
    if name == 'summary.json':
        exact(value, SUMMARY)
    elif name == 'progress.json':
        exact(value, PROGRESS)
    elif name == 'source_hashes.json':
        validate_source_schema(value)
    elif name == 'checkpoint.json':
        exact(value, CHECKPOINT)
    else:
        raise EvidenceError('unknown evidence filename')
    return value


def validate_member(name, raw):
    need(name in LIMITS, 'unknown evidence filename')
    value = strict_json(raw, LIMITS[name])
    validate_schema(name, value)
    if name in MEMBERS:
        size, digest = MEMBERS[name]
        need(len(raw) == size and sha256(raw) == digest, 'historical member byte identity mismatch')
    return value


def read_bounded(path, limit):
    need(not path.is_symlink() and path.is_file(), 'evidence must be a regular non-symlink file')
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    need(len(raw) <= limit, 'oversized evidence file')
    return raw


def validate_directory(directory=HERE):
    directory = Path(directory)
    # The directory also holds this validator, its cold tests, and README.
    allowed = set(LIMITS) | {'validate_evidence.py', 'test_evidence.py', 'README.md'}
    need({p.name for p in directory.iterdir()} == allowed, 'unexpected or missing archive files')
    for name in LIMITS:
        validate_member(name, read_bounded(directory / name, LIMITS[name]))
    return dict(PROGRESS, numerical_acceptance=False, archive_identity_verified=True)


def validate_zip(path, directory=HERE):
    raw = read_bounded(Path(path), ZIP_BYTES)
    need(len(raw) == ZIP_BYTES and sha256(raw) == ZIP_SHA256, 'original ZIP identity mismatch')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        need(sorted(archive.namelist()) == sorted(MEMBERS), 'ZIP member allowlist mismatch')
        for info in archive.infolist():
            need(not info.is_dir() and not (info.flag_bits & 1) and
                 stat.S_IFMT(info.external_attr >> 16) != stat.S_IFLNK, 'unsafe ZIP member')
            need(info.file_size == MEMBERS[info.filename][0], 'ZIP member size mismatch')
            content = archive.read(info)
            validate_member(info.filename, content)
            need(content == read_bounded(Path(directory) / info.filename, LIMITS[info.filename]),
                 'archived bytes differ from original ZIP member')
    return validate_directory(directory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=HERE)
    parser.add_argument('--zip', dest='zip_path', type=Path)
    args = parser.parse_args()
    result = validate_zip(args.zip_path, args.directory) if args.zip_path else validate_directory(args.directory)
    # A successful cold check must never print a synthetic numerical PASS.
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
