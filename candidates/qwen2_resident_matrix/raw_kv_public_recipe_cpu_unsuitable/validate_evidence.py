"""Cold validation of two immutable CPU_UNSUITABLE placements, never acceptance.

Standard library only. No setup, numerical/native imports, subprocesses, network,
Git, Scala, or RTL. Optional source-tree checks read/hash bytes without imports.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

HERE = Path(__file__).resolve().parent
CHECKOUT = 'be00eb8e4bc75e2e41f2a434d05d4c901ed3faa5'
CONTRACT = 'b4ea311e11a64695fba4ccfc1f512240ddccdbada99710d58a1a36dbe5d1d96b'
CONTRACT_PATH = 'candidates/qwen2_resident_matrix/raw_kv_public_recipe_run/launch-contract.json'
TARGET_PREFIX = 'candidates/qwen2_resident_matrix/raw_kv_public_recipe_cpu_unsuitable/'
PLACEMENTS = {'placement_1': {'archive': {'bytes': 15365,
                             'filename': 'public-m128-job117185037810.zip',
                             'sha256': '3b4c54aa75890bb2679df92dc53c8dd3875e993b250a8737c514f5375b34736a'},
                 'artifact_id': '12074126444',
                 'job_id': '117185037810',
                 'members': {'progress.json': {'bytes': 94,
                                               'sha256': '3fd0fdf48293b75e260be007319c2a5f90446d59f82156f23c7f376b67eaac63'},
                             'source_hashes.json': {'bytes': 39690,
                                                    'sha256': '99d4548f9e20edde2f2d42d36848ad25996fa1aae9e44025a403ffd27304ab28'},
                             'summary.json': {'bytes': 1213,
                                              'sha256': '0d53a58255e68c41f8bcb5675dd1c04dd459162302d3dade1ee9de3308a65f3c'}}},
 'placement_2': {'archive': {'bytes': 15364,
                             'filename': 'public-m128-job117185359078.zip',
                             'sha256': 'ab1e1cbe2c58a58438185d53c34afbe79aafe42fcfeff94b81360abcb373a698'},
                 'artifact_id': '12073288607',
                 'job_id': '117185359078',
                 'members': {'progress.json': {'bytes': 94,
                                               'sha256': 'e53dd159437c57744c4884b0c36324e0f6dc91b799ea7bc4aad1709b2ea8f68e'},
                             'source_hashes.json': {'bytes': 39690,
                                                    'sha256': '99d4548f9e20edde2f2d42d36848ad25996fa1aae9e44025a403ffd27304ab28'},
                             'summary.json': {'bytes': 1217,
                                              'sha256': '06dc15a9203139fcec6ac28430c35cddb1d2563170f32a7bf99ec3f3c7ce95cb'}}}}
SUMMARIES = {'placement_1': {'checkout_commit': 'be00eb8e4bc75e2e41f2a434d05d4c901ed3faa5',
                 'clone_started': False,
                 'cpu_eligibility': {'backend_qualified': False,
                                     'eligibility_only': True,
                                     'excluded_flags': {'amx_bf16': False,
                                                        'amx_int8': False,
                                                        'amx_tile': False},
                                     'flags': {'avx512_bf16': False,
                                               'avx512bw': True,
                                               'avx512dq': True,
                                               'avx512f': True,
                                               'avx512vl': True,
                                               'fma': True},
                                     'processor_records': 4,
                                     'schema': 1,
                                     'status': 'CPU_UNSUITABLE'},
                 'diagnostic': {'exception': 'OtherError',
                                'frames': [{'line': 497,
                                            'source': 'candidates/qwen2_resident_matrix/raw_kv_public_recipe_run/run_ci.py'},
                                           {'line': 116,
                                            'source': 'candidates/qwen2_resident_matrix/raw_kv_public_recipe_run/run_ci.py'},
                                           {'line': 108,
                                            'source': 'candidates/qwen2_resident_matrix/raw_kv_public_recipe_run/run_ci.py'}],
                                'phase': 'cpu_qualification'},
                 'elapsed_seconds': 0.124065,
                 'enable_raw_kv': True,
                 'fresh_profile': True,
                 'full_29_node_acceptance': False,
                 'launch_contract_sha256': 'b4ea311e11a64695fba4ccfc1f512240ddccdbada99710d58a1a36dbe5d1d96b',
                 'numeric_started': False,
                 'numerical_acceptance': False,
                 'phase': 'cpu_qualification',
                 'postflight_complete': False,
                 'profile': 'qwen2-public-paired-m128-linked-launch-v1',
                 'rows': 128,
                 'rtl_executed': False,
                 'scala_executed': False,
                 'schema': 1,
                 'setup_started': False,
                 'status': 'CPU_UNSUITABLE'},
 'placement_2': {'checkout_commit': 'be00eb8e4bc75e2e41f2a434d05d4c901ed3faa5',
                 'clone_started': False,
                 'cpu_eligibility': {'backend_qualified': False,
                                     'eligibility_only': True,
                                     'excluded_flags': {'amx_bf16': False,
                                                        'amx_int8': False,
                                                        'amx_tile': False},
                                     'flags': {'avx512_bf16': False,
                                               'avx512bw': False,
                                               'avx512dq': False,
                                               'avx512f': False,
                                               'avx512vl': False,
                                               'fma': True},
                                     'processor_records': 4,
                                     'schema': 1,
                                     'status': 'CPU_UNSUITABLE'},
                 'diagnostic': {'exception': 'OtherError',
                                'frames': [{'line': 497,
                                            'source': 'candidates/qwen2_resident_matrix/raw_kv_public_recipe_run/run_ci.py'},
                                           {'line': 116,
                                            'source': 'candidates/qwen2_resident_matrix/raw_kv_public_recipe_run/run_ci.py'},
                                           {'line': 108,
                                            'source': 'candidates/qwen2_resident_matrix/raw_kv_public_recipe_run/run_ci.py'}],
                                'phase': 'cpu_qualification'},
                 'elapsed_seconds': 0.099335,
                 'enable_raw_kv': True,
                 'fresh_profile': True,
                 'full_29_node_acceptance': False,
                 'launch_contract_sha256': 'b4ea311e11a64695fba4ccfc1f512240ddccdbada99710d58a1a36dbe5d1d96b',
                 'numeric_started': False,
                 'numerical_acceptance': False,
                 'phase': 'cpu_qualification',
                 'postflight_complete': False,
                 'profile': 'qwen2-public-paired-m128-linked-launch-v1',
                 'rows': 128,
                 'rtl_executed': False,
                 'scala_executed': False,
                 'schema': 1,
                 'setup_started': False,
                 'status': 'CPU_UNSUITABLE'}}
PROGRESSES = {'placement_1': {'elapsed_seconds': 0.124065,
                 'phase': 'cpu_qualification',
                 'schema': 1,
                 'status': 'CPU_UNSUITABLE'},
 'placement_2': {'elapsed_seconds': 0.099335,
                 'phase': 'cpu_qualification',
                 'schema': 1,
                 'status': 'CPU_UNSUITABLE'}}
CHECKPOINT = {'checkout_commit': 'be00eb8e4bc75e2e41f2a434d05d4c901ed3faa5',
 'checkpoint_kind': 'FAILED_CPU_PLACEMENTS_BEFORE_CLONE',
 'limits': {'data': 'Only the original three safe JSON members per placement are preserved. No '
                    'weights, numerical arrays, private logs, or ZIP archives are included.',
            'execution': 'Neither placement started setup, native backend checks, Public numerical '
                         'work, or new numeric-progress diagnostics. No numerical acceptance is '
                         'established.',
            'provenance': 'IDs are supplied provenance. ZIP hashes anchor the connected-GitHub '
                          'download bytes against supplied SHA256; cold verification is not '
                          'independent GitHub-origin authentication.',
            'scope': 'This archive is outside the 285-source closure and does not alter workflows, '
                     'runtime, frozen evidence, or source contracts.',
            'source_binding': 'All 285 source hashes were checked against immutable be00 Git '
                              'blobs. The 12 generated hashes match contract expectations; the '
                              'failed placements did not clone or compose.'},
 'placements': {'placement_1': {'archive': {'bytes': 15365,
                                            'filename': 'public-m128-job117185037810.zip',
                                            'sha256': '3b4c54aa75890bb2679df92dc53c8dd3875e993b250a8737c514f5375b34736a'},
                                'artifact_id': '12074126444',
                                'job_id': '117185037810',
                                'members': {'progress.json': {'bytes': 94,
                                                              'sha256': '3fd0fdf48293b75e260be007319c2a5f90446d59f82156f23c7f376b67eaac63'},
                                            'source_hashes.json': {'bytes': 39690,
                                                                   'sha256': '99d4548f9e20edde2f2d42d36848ad25996fa1aae9e44025a403ffd27304ab28'},
                                            'summary.json': {'bytes': 1213,
                                                             'sha256': '0d53a58255e68c41f8bcb5675dd1c04dd459162302d3dade1ee9de3308a65f3c'}}},
                'placement_2': {'archive': {'bytes': 15364,
                                            'filename': 'public-m128-job117185359078.zip',
                                            'sha256': 'ab1e1cbe2c58a58438185d53c34afbe79aafe42fcfeff94b81360abcb373a698'},
                                'artifact_id': '12073288607',
                                'job_id': '117185359078',
                                'members': {'progress.json': {'bytes': 94,
                                                              'sha256': 'e53dd159437c57744c4884b0c36324e0f6dc91b799ea7bc4aad1709b2ea8f68e'},
                                            'source_hashes.json': {'bytes': 39690,
                                                                   'sha256': '99d4548f9e20edde2f2d42d36848ad25996fa1aae9e44025a403ffd27304ab28'},
                                            'summary.json': {'bytes': 1217,
                                                             'sha256': '06dc15a9203139fcec6ac28430c35cddb1d2563170f32a7bf99ec3f3c7ce95cb'}}}},
 'recorded_facts': {'clone_started': False,
                    'cpu_backend_qualified': False,
                    'cpu_eligibility_only': True,
                    'elapsed_seconds': {'placement_1': 0.124065, 'placement_2': 0.099335},
                    'full_29_node_acceptance': False,
                    'missing_required_cpu_flags': {'placement_1': ['avx512_bf16'],
                                                   'placement_2': ['avx512_bf16',
                                                                   'avx512bw',
                                                                   'avx512dq',
                                                                   'avx512f',
                                                                   'avx512vl']},
                    'numeric_started': False,
                    'numerical_acceptance': False,
                    'phase': 'cpu_qualification',
                    'placements': 2,
                    'postflight_complete': False,
                    'processor_records_per_placement': 4,
                    'rtl_executed': False,
                    'scala_executed': False,
                    'setup_started': False,
                    'status': 'CPU_UNSUITABLE'},
 'repository': 'liyang53719/hetero_cnn_llm_aha',
 'run_id': '38963767257',
 'schema': 1,
 'source_binding': {'commit_tree': '07cdd8b1bc7508da7b587fc8465d4e8026f67731',
                    'generated_entries': 12,
                    'generated_identities_match_pinned_contract': True,
                    'generated_sources_executed': False,
                    'launch_contract_sha256': 'b4ea311e11a64695fba4ccfc1f512240ddccdbada99710d58a1a36dbe5d1d96b',
                    'manifest_member_sha256': '99d4548f9e20edde2f2d42d36848ad25996fa1aae9e44025a403ffd27304ab28',
                    'source_entries': 285,
                    'source_sha256_verified_against_commit_blobs': True}}
KEYSETS = {'generated_sha256': (12, 'e970a684417c8a0cbcc5b04ec2298b1e1db4041540a549872b883c94b22d308a'),
 'source_sha256': (285, '54b0c0157ccdbab2f3a111f9f44f4b237e7bfc1666d50cc139eaac864021b8cb')}
HEX64 = re.compile(r'[0-9a-f]{64}\Z')
SAFE_PATH = re.compile(r'[A-Za-z0-9_.\-/]+\Z')
MEMBERS = {'summary.json', 'progress.json', 'source_hashes.json'}
ROOT_FILES = {'checkpoint.json', 'validate_evidence.py', 'test_evidence.py', 'README.md'}
SOURCE_LIMIT = 2 * 1024 * 1024
SOURCE_TOTAL_LIMIT = 32 * 1024 * 1024


class EvidenceError(ValueError):
    """The input is not the exact bounded CPU placement failure evidence."""


def need(condition, message):
    # All enforcement survives python -O.
    if not condition:
        raise EvidenceError(message)


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw, limit):
    need(type(raw) is bytes and 0 < len(raw) <= limit, 'empty/oversized/non-byte JSON')

    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'duplicate JSON key')
            result[key] = value
        return result

    def constant(value):
        raise EvidenceError('non-finite number')

    def bounded(value, depth=0):
        need(depth <= 16, 'excessive nesting')
        if type(value) is float:
            need(math.isfinite(value), 'non-finite number')
        elif type(value) is dict:
            for item in value.values():
                bounded(item, depth + 1)
        elif type(value) is list:
            for item in value:
                bounded(item, depth + 1)

    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)
        bounded(value)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise EvidenceError('invalid strict JSON') from exc
    need(type(value) is dict, 'top level must be an object')
    return value


def exact(value, expected, label='root'):
    need(type(value) is type(expected), label + ': wrong type')
    if type(expected) is dict:
        need(value.keys() == expected.keys(), label + ': unknown/missing fields')
        for key in expected:
            exact(value[key], expected[key], label + '.' + key)
    elif type(expected) is list:
        need(len(value) == len(expected), label + ': wrong length')
        for index, item in enumerate(expected):
            exact(value[index], item, label + '[' + str(index) + ']')
    else:
        need(value == expected, label + ': unexpected historical value')


def safe_relative(path):
    need(type(path) is str and 0 < len(path) <= 256 and SAFE_PATH.fullmatch(path), 'unsafe path')
    posix = PurePosixPath(path)
    need(not posix.is_absolute() and '..' not in posix.parts and str(posix) == path, 'noncanonical path')
    return posix


def validate_source_schema(value):
    need(type(value) is dict and set(value) == {'schema', 'launch_contract_sha256',
        'generated_sha256', 'source_sha256'}, 'source manifest fields')
    exact(value['schema'], 1)
    exact(value['launch_contract_sha256'], CONTRACT)
    for name, (count, keys_digest) in KEYSETS.items():
        entries = value[name]
        need(type(entries) is dict and len(entries) == count, 'source count/type')
        for path, digest in entries.items():
            safe_relative(path)
            need(not path.startswith(TARGET_PREFIX), 'archive entered runtime closure')
            need(type(digest) is str and HEX64.fullmatch(digest), 'invalid source SHA256')
        keys = json.dumps(sorted(entries), ensure_ascii=True, separators=(',', ':')).encode('ascii')
        need(sha256(keys) == keys_digest, 'unknown/missing source identities')
    exact(value['source_sha256'][CONTRACT_PATH], CONTRACT)
    need(set(value['generated_sha256']) <= set(value['source_sha256']), 'generated paths absent from sources')


def validate_schema(placement, name, value):
    need(placement in PLACEMENTS, 'unknown placement')
    if name == 'summary.json':
        exact(value, SUMMARIES[placement])
    elif name == 'progress.json':
        exact(value, PROGRESSES[placement])
    elif name == 'source_hashes.json':
        validate_source_schema(value)
    else:
        raise EvidenceError('unknown member')


def validate_member(placement, name, raw):
    need(placement in PLACEMENTS and name in MEMBERS, 'unknown placement/member')
    identity = PLACEMENTS[placement]['members'][name]
    value = strict_json(raw, identity['bytes'])
    validate_schema(placement, name, value)
    need(len(raw) == identity['bytes'] and sha256(raw) == identity['sha256'], 'historical byte identity mismatch')
    return value


def read_bounded(path, limit):
    path = Path(path)
    # O_NOFOLLOW closes the final-component symlink race; O_NONBLOCK avoids FIFO blocking.
    try:
        need(stat.S_ISREG(path.lstat().st_mode), 'file must be regular and non-symlink')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            metadata = os.fstat(stream.fileno())
            need(stat.S_ISREG(metadata.st_mode) and 0 < metadata.st_size <= limit, 'file type/size')
            raw = stream.read(limit + 1)
        need(0 < len(raw) <= limit, 'empty/oversized file')
        return raw
    except OSError as exc:
        raise EvidenceError('unreadable evidence file') from exc


def directory_entries(directory, expected):
    directory = Path(directory)
    try:
        need(stat.S_ISDIR(directory.lstat().st_mode), 'directory must be non-symlink')
        need({entry.name for entry in directory.iterdir()} == set(expected), 'unexpected/missing entries')
    except OSError as exc:
        raise EvidenceError('unreadable evidence directory') from exc


def validate_directory(directory=HERE):
    directory = Path(directory)
    directory_entries(directory, ROOT_FILES | set(PLACEMENTS))
    for name in ROOT_FILES:
        read_bounded(directory / name, 128 * 1024)
    checkpoint = strict_json(read_bounded(directory / 'checkpoint.json', 16384), 16384)
    exact(checkpoint, CHECKPOINT)
    manifests = []
    for placement in PLACEMENTS:
        directory_entries(directory / placement, MEMBERS)
        for name in sorted(MEMBERS):
            limit = PLACEMENTS[placement]['members'][name]['bytes']
            raw = read_bounded(directory / placement / name, limit)
            validate_member(placement, name, raw)
            if name == 'source_hashes.json':
                manifests.append(raw)
    need(manifests[0] == manifests[1], 'placement source manifests differ')
    return {'status': 'CPU_UNSUITABLE', 'phase': 'cpu_qualification', 'placements': 2,
            'clone_started': False, 'setup_started': False, 'numeric_started': False,
            'numerical_acceptance': False, 'archive_identity_verified': True}


def validate_zip(placement, path, directory=HERE):
    need(placement in PLACEMENTS, 'unknown placement')
    record = PLACEMENTS[placement]
    raw = read_bounded(path, record['archive']['bytes'])
    need(len(raw) == record['archive']['bytes'] and sha256(raw) == record['archive']['sha256'], 'ZIP identity mismatch')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            need(sorted(archive.namelist()) == sorted(MEMBERS), 'ZIP member allowlist')
            for info in archive.infolist():
                identity = record['members'][info.filename]
                need(not info.is_dir() and not (info.flag_bits & 1) and
                     stat.S_IFMT(info.external_attr >> 16) in (0, stat.S_IFREG), 'unsafe ZIP member')
                need(info.file_size == identity['bytes'] and
                     0 < info.compress_size <= len(raw) and
                     info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED), 'ZIP size/compression')
                with archive.open(info) as stream:
                    content = stream.read(identity['bytes'] + 1)
                validate_member(placement, info.filename, content)
                need(content == read_bounded(Path(directory) / placement / info.filename, identity['bytes']),
                     'archive differs from ZIP')
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError) as exc:
        raise EvidenceError('invalid ZIP') from exc
    return validate_directory(directory)


def validate_source_tree(source_tree, directory=HERE):
    """Hash the clean historical tree, without importing or executing its code.

    This confirms historical byte identities, not Git commit provenance or runtime
    execution. Dirty generated-overlay trees correctly fail their original hashes.
    """
    result = validate_directory(directory)
    source_tree = Path(source_tree)
    need(source_tree.is_dir() and not source_tree.is_symlink(), 'unsafe source root')
    manifest = validate_member('placement_1', 'source_hashes.json',
        read_bounded(Path(directory) / 'placement_1/source_hashes.json', 39690))
    total = 0
    contract_raw = None
    for relative, digest in manifest['source_sha256'].items():
        parts = safe_relative(relative).parts
        cursor = source_tree
        for component in parts[:-1]:
            cursor = cursor / component
            need(cursor.is_dir() and not cursor.is_symlink(), 'unsafe source ancestor')
        raw = read_bounded(cursor / parts[-1], SOURCE_LIMIT)
        total += len(raw)
        need(total <= SOURCE_TOTAL_LIMIT, 'source total size limit')
        need(sha256(raw) == digest, 'source byte mismatch: ' + relative)
        if relative == CONTRACT_PATH:
            contract_raw = raw
    contract = strict_json(contract_raw, SOURCE_LIMIT)
    exact(contract['generated_sha256'], manifest['generated_sha256'])
    expected_sources = dict(contract['source_sha256'])
    expected_sources[CONTRACT_PATH] = CONTRACT
    exact(expected_sources, manifest['source_sha256'])
    return dict(result, source_tree_identity_verified=True, source_entries=285,
                generated_contract_identities_verified=12, numerical_execution=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=HERE)
    parser.add_argument('--zip-1', type=Path)
    parser.add_argument('--zip-2', type=Path)
    parser.add_argument('--source-tree', type=Path)
    args = parser.parse_args()
    result = validate_directory(args.directory)
    for placement, path in (('placement_1', args.zip_1), ('placement_2', args.zip_2)):
        if path is not None:
            result = validate_zip(placement, path, args.directory)
    if args.source_tree is not None:
        result = validate_source_tree(args.source_tree, args.directory)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
