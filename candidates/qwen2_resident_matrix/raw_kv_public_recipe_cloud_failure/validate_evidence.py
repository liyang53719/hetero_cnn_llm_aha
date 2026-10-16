"""Cold, evidence-only validation of one failed original Public M128 run.

Standard library only. Never execute/import the numerical runtime, native code,
setup, Git, subprocesses or network. Every successful result retains FAILED.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat

HERE = Path(__file__).resolve().parent
CHECKOUT = 'be00eb8e4bc75e2e41f2a434d05d4c901ed3faa5'
CONTRACT = 'b4ea311e11a64695fba4ccfc1f512240ddccdbada99710d58a1a36dbe5d1d96b'
CONTRACT_PATH = 'candidates/qwen2_resident_matrix/raw_kv_public_recipe_run/launch-contract.json'
TARGET_PREFIX = 'candidates/qwen2_resident_matrix/raw_kv_public_recipe_cloud_failure/'
MEMBER_IDENTITIES = {'progress.json': {'bytes': 79,
                   'sha256': 'd48207e852bdac9e6b946329cee952ea2cf3d2569e60d583589c3467255fc951'},
 'source_hashes.json': {'bytes': 39690,
                        'sha256': '99d4548f9e20edde2f2d42d36848ad25996fa1aae9e44025a403ffd27304ab28'},
 'summary.json': {'bytes': 1960,
                  'sha256': '0a6764b46df7f5c5e798f3e491bda3d8ad594cf8b17294fdf68ce8bc8af99be8'}}
SUMMARY = {'checkout_commit': 'be00eb8e4bc75e2e41f2a434d05d4c901ed3faa5',
 'clone_started': True,
 'cpu_eligibility': {'backend_qualified': False,
                     'eligibility_only': True,
                     'excluded_flags': {'amx_bf16': False, 'amx_int8': False, 'amx_tile': False},
                     'flags': {'avx512_bf16': True,
                               'avx512bw': True,
                               'avx512dq': True,
                               'avx512f': True,
                               'avx512vl': True,
                               'fma': True},
                     'processor_records': 9,
                     'schema': 1,
                     'status': 'ELIGIBLE_FOR_BACKEND_CHECK'},
 'diagnostic': {'exception': 'ValueError',
                'exit_code': 1,
                'frames': [{'line': 427,
                            'source': 'candidates/qwen2_resident_matrix/ffn_public/execute_numeric.py'},
                           {'line': 109,
                            'source': 'candidates/qwen2_resident_matrix/ffn_public/execute_numeric.py'},
                           {'line': 39,
                            'source': 'candidates/qwen2_resident_matrix/ffn_drain/check_numeric.py'}],
                'phase': 'numeric'},
 'elapsed_seconds': 2762.816418,
 'enable_raw_kv': True,
 'fresh_profile': True,
 'full_29_node_acceptance': False,
 'launch_contract_sha256': 'b4ea311e11a64695fba4ccfc1f512240ddccdbada99710d58a1a36dbe5d1d96b',
 'numeric_progress': {'capped': False,
                      'context_sha256': '5864b89dd54542f0b64abb15c44df314a78cc1009ac3785d3b8854433f6cf241',
                      'counts': {'completion_fire': 16,
                                 'host_model_ticks': 18941741,
                                 'owner_result_fire': 14,
                                 'request_fire': 15,
                                 'result_fire': 0},
                      'elapsed_origin': 'NUMERIC_WRITER_START',
                      'elapsed_seconds': 2273.228089879,
                      'event': 'REQUEST',
                      'kind': 'NUMERIC_PROGRESS_DIAGNOSTIC_ONLY',
                      'numerical_acceptance': False,
                      'operator': 'FFN',
                      'ordinal': 16,
                      'phase': 'actual_execute',
                      'phase_elapsed_seconds': 2261.354416201,
                      'phase_state': 'ENTERED',
                      'postflight_complete': False,
                      'schema': 1,
                      'sequence': 61,
                      'source_manifest_sha256': '9d1aa25d2f76aea864c86dbfa7cfc3a724cb2e6bafd2c8f8158d19937f057f33',
                      'stage': 'public_suffix',
                      'writer_sha256': 'd20155dd701203c6043adec7572cb224a5b2dceaff260bee29235ea669611e5e'},
 'numeric_started': True,
 'numerical_acceptance': False,
 'phase': 'numeric',
 'postflight_complete': False,
 'profile': 'qwen2-public-paired-m128-linked-launch-v1',
 'rows': 128,
 'rtl_executed': False,
 'scala_executed': False,
 'schema': 1,
 'setup_started': True,
 'status': 'FAILED'}
PROGRESS = {'elapsed_seconds': 2762.816418, 'phase': 'numeric', 'schema': 1, 'status': 'FAILED'}
CHECKPOINT = {'bounded_timing_projection': {'actual_host_wall_seconds': 2400.2100579410035,
                               'checkout_commit': 'be00eb8e4bc75e2e41f2a434d05d4c901ed3faa5',
                               'completed_pc_count': 16,
                               'completed_pc_first': 0,
                               'completed_pc_last': 15,
                               'completed_pcs_contiguous': True,
                               'context_sha256': '5864b89dd54542f0b64abb15c44df314a78cc1009ac3785d3b8854433f6cf241',
                               'diagnosis': 'INNER_PUBLIC_2400S_WALL_BUDGET_EXCEEDED_AT_FFN_HOST_EDGE',
                               'final_host_counts': {'completion_fire': 16,
                                                     'host_model_ticks': 19929718,
                                                     'owner_result_fire': 14,
                                                     'request_fire': 15,
                                                     'result_fire': 0},
                               'full_29_node_acceptance': False,
                               'hardware_cycles': None,
                               'kind': 'BOUNDED_FAILURE_TIMING_PROJECTION_NO_ACCEPTANCE',
                               'last_numeric_progress_sha256': 'fe5e1bd204a08356f397d9f1b9eed60899c4caff68a56a15977c74cca711a305',
                               'last_operator': 'FFN',
                               'last_ordinal': 16,
                               'last_phase_elapsed_seconds': 2261.354416201,
                               'last_writer_elapsed_seconds': 2273.228089879,
                               'numerical_acceptance': False,
                               'original_budgets_seconds': {'inner_public': 2400,
                                                            'numeric_envelope': 2430,
                                                            'setup': 900,
                                                            'total': 3420},
                               'outer_elapsed_seconds': 2762.816418,
                               'outer_status': 'FAILED',
                               'postflight_complete': False,
                               'prefix_host_wall_seconds': 82.37693366200256,
                               'private_actual_report_included': False,
                               'private_actual_summary_bytes': 309466,
                               'private_actual_summary_sha256': 'a58d7b3133bfc55012a2cccfba8dbd40a3760b3e11b17833a0ee1636ee8b3b13',
                               'rtl_executed': False,
                               'schema': 1,
                               'setup_elapsed_seconds': 335.069335,
                               'setup_receipt_sha256': '79b4ca389df5f19d52e0a0c8a6040f706df5fa9f4d373c27dbbcd813032ec61a',
                               'source_manifest_sha256': '9d1aa25d2f76aea864c86dbfa7cfc3a724cb2e6bafd2c8f8158d19937f057f33',
                               'source_sha256': {'candidates/qwen2_resident_matrix/dense_block_reduce/check_public_numeric.py': 'b3204b92334314c2153a33ea4523d2e55e35ea1f1f632d217d0e3530e3934703',
                                                 'candidates/qwen2_resident_matrix/ffn_drain/check_numeric.py': '7e552390364b985e112a350387623204d76fd17cc6ce146afb42ca2bc8b825be',
                                                 'candidates/qwen2_resident_matrix/ffn_public/execute_numeric.py': 'cdf203f9e7113db7fb29dd290ea6355adf3f7df86e145e5828daf13a5ac51b73'},
                               'timing_limits': ['Writer, actual_execute phase, and inner Public '
                                                 'clock have different origins.',
                                                 'A single last-event snapshot is not a heartbeat '
                                                 'or exact final halt timestamp.',
                                                 'No exact Attention-only wall time or exact FFN '
                                                 'remaining budget is asserted.',
                                                 'Host counters are software-model events, not RTL '
                                                 'cycles or MAC utilization.']},
 'checkout_commit': 'be00eb8e4bc75e2e41f2a434d05d4c901ed3faa5',
 'checkpoint_kind': 'FAILED_ORIGINAL_PUBLIC_M128_INNER_HOST_BUDGET',
 'control_record_identities': {'observed-progress-2143.json': {'bytes': 1445,
                                                               'sha256': '6acff923060e8294ce94aff00ecf82ad7b3c6d0d054b6c11ea0910ae68844623'},
                               'observed-terminal.json': {'bytes': 1447,
                                                          'sha256': '2649973bc3910e3b42c7c01daca8632f680f1415d2b756d890c7beee62f1e6e5'},
                               'session-terminal.json': {'bytes': 674,
                                                         'sha256': '6d1d185463ab2fa88f31dbfda2aeae6fc3c1b53048c11da9a560f3b54b08c019'},
                               'session.json': {'bytes': 567,
                                                'sha256': '60408bc1be8f83698292eedf465ee5e7f7cf3b32458c83917124730451d22a58'},
                               'terminal-record.json': {'bytes': 2101,
                                                        'sha256': '076bebad9c7e413ea737b4bf2cd7efe9b2dfd27b0e5fe7d1dd743ce9922cdf1a'}},
 'diagnosis': {'classification': 'ORIGINAL_INNER_2400_SECOND_PUBLIC_HOST_WALL_CLOCK_GUARD',
               'clean_original_guard_line': 103,
               'clean_original_guard_source_sha256': 'fa550e3b9df4aca6041eb3631f50e520fda762184db5bcaf70e707a7dc72ffb3',
               'exception': 'ValueError',
               'frames': [{'line': 427,
                           'source': 'candidates/qwen2_resident_matrix/ffn_public/execute_numeric.py'},
                          {'line': 109,
                           'source': 'candidates/qwen2_resident_matrix/ffn_public/execute_numeric.py'},
                          {'line': 39,
                           'source': 'candidates/qwen2_resident_matrix/ffn_drain/check_numeric.py'}],
               'guard_message_from_frozen_source': 'public FFN host budget exceeded',
               'inner_wall_budget_seconds': 2400,
               'interpretation': 'The terminal diagnostic frames resolve to the unchanged host '
                                 'deadline check in the pinned composed source. This identifies '
                                 'the observed guard, not a numerical comparison result.',
               'numeric_phase_budget_seconds': 2430,
               'numerical_comparison_completed': False,
               'numerical_mismatch_reported': False,
               'outer_timeout_reported': False,
               'outer_total_budget_seconds': 3420,
               'runtime_guard_line': 109,
               'runtime_guard_source_sha256': 'cdf203f9e7113db7fb29dd290ea6355adf3f7df86e145e5828daf13a5ac51b73'},
 'last_valid_numeric_progress': {'capped': False,
                                 'context_sha256': '5864b89dd54542f0b64abb15c44df314a78cc1009ac3785d3b8854433f6cf241',
                                 'counts': {'completion_fire': 16,
                                            'host_model_ticks': 18941741,
                                            'owner_result_fire': 14,
                                            'request_fire': 15,
                                            'result_fire': 0},
                                 'elapsed_origin': 'NUMERIC_WRITER_START',
                                 'elapsed_seconds': 2273.228089879,
                                 'event': 'REQUEST',
                                 'kind': 'NUMERIC_PROGRESS_DIAGNOSTIC_ONLY',
                                 'numerical_acceptance': False,
                                 'operator': 'FFN',
                                 'ordinal': 16,
                                 'phase': 'actual_execute',
                                 'phase_elapsed_seconds': 2261.354416201,
                                 'phase_state': 'ENTERED',
                                 'postflight_complete': False,
                                 'schema': 1,
                                 'sequence': 61,
                                 'source_manifest_sha256': '9d1aa25d2f76aea864c86dbfa7cfc3a724cb2e6bafd2c8f8158d19937f057f33',
                                 'stage': 'public_suffix',
                                 'writer_sha256': 'd20155dd701203c6043adec7572cb224a5b2dceaff260bee29235ea669611e5e'},
 'limits': {'acceptance': 'All Public numerical, postflight and full-29-node acceptance remain '
                          'false. Source checks, setup progress, historical runs and '
                          'cold-validator success cannot establish PASS.',
            'cpu': 'ELIGIBLE_FOR_BACKEND_CHECK is CPU eligibility only. Its '
                   'backend_qualified=false is preserved unchanged and is not a claim that native '
                   'setup never ran.',
            'data': 'Only three untouched safe JSONs are preserved. Control/context contents, '
                    'private logs, arrays, weights, native libraries and reference outputs are not '
                    'included.',
            'progress': 'Sequence 61 is the last valid emitted diagnostic, not an exact terminal '
                        'program counter or proof of completed FFN arithmetic. Its counters are '
                        'distinct and must not be conflated.',
            'provenance': 'Session and observation identities are local provenance. Hash checks '
                          'verify recorded byte identities; they do not independently authenticate '
                          'a remote CI origin.',
            'scope': 'Evidence-only candidate outside the 285-source closure. No existing '
                     'repository, workflow, runtime, contract or frozen evidence is changed. No '
                     'rerun or push.'},
 'recorded_facts': {'clone_started': True,
                    'elapsed_seconds': 2762.816418,
                    'enable_raw_kv': True,
                    'fresh_profile': True,
                    'full_29_node_acceptance': False,
                    'numeric_started': True,
                    'numerical_acceptance': False,
                    'phase': 'numeric',
                    'postflight_complete': False,
                    'profile': 'qwen2-public-paired-m128-linked-launch-v1',
                    'rows': 128,
                    'rtl_executed': False,
                    'scala_executed': False,
                    'setup_started': True,
                    'status': 'FAILED'},
 'repository': 'liyang53719/hetero_cnn_llm_aha',
 'safe3': {'progress.json': {'bytes': 79,
                             'sha256': 'd48207e852bdac9e6b946329cee952ea2cf3d2569e60d583589c3467255fc951'},
           'source_hashes.json': {'bytes': 39690,
                                  'sha256': '99d4548f9e20edde2f2d42d36848ad25996fa1aae9e44025a403ffd27304ab28'},
           'summary.json': {'bytes': 1960,
                            'sha256': '0a6764b46df7f5c5e798f3e491bda3d8ad594cf8b17294fdf68ce8bc8af99be8'}},
 'schema': 1,
 'session': {'cross_call_proc_identity_available': False,
             'deadline_ns': 66511060765001,
             'launcher_pid': 2,
             'launcher_start_sha256': 'fb3044bbd4b5f3c3b1ee125c60ab401e3a3e111653cb2d4378827f04c2b30bc9',
             'pid_scope': 'EXEC_SESSION_LOCAL_PID_NAMESPACE',
             'process_exit_code': 1,
             'session_id': 99610,
             'started_ns': 63091060765001,
             'started_utc': '2026-10-16T20:58:47Z',
             'total_budget_seconds': 3420},
 'source_binding': {'commit_tree': '07cdd8b1bc7508da7b587fc8465d4e8026f67731',
                    'context_sha256': '5864b89dd54542f0b64abb15c44df314a78cc1009ac3785d3b8854433f6cf241',
                    'generated_entries': 12,
                    'launch_contract_sha256': 'b4ea311e11a64695fba4ccfc1f512240ddccdbada99710d58a1a36dbe5d1d96b',
                    'original_source_manifest_sha256': 'b3f398957ed913b770c0d8686b10923a9cca8479019fe8a58d4e1dced142898f',
                    'runtime_role': 'composed_original_checkout_with_12_pinned_overlays',
                    'runtime_source_manifest_sha256': '9d1aa25d2f76aea864c86dbfa7cfc3a724cb2e6bafd2c8f8158d19937f057f33',
                    'source_entries': 285,
                    'source_manifest_member_sha256': '99d4548f9e20edde2f2d42d36848ad25996fa1aae9e44025a403ffd27304ab28',
                    'source_role': 'clean_original_checkout',
                    'writer_identity_kind': 'RANDOM_PER_RUN_DIAGNOSTIC_WRITER_ID_NOT_SOURCE_HASH',
                    'writer_sha256': 'd20155dd701203c6043adec7572cb224a5b2dceaff260bee29235ea669611e5e'},
 'timing_projection_identity': {'bytes': 2514,
                                'sha256': '3023cfda0e7cc6d01a5d9b6864ad456d0bd2f61184340d5b5e25e493815b6298'}}
KEYSETS = {'generated_sha256': (12, 'e970a684417c8a0cbcc5b04ec2298b1e1db4041540a549872b883c94b22d308a'),
 'source_sha256': (285, '54b0c0157ccdbab2f3a111f9f44f4b237e7bfc1666d50cc139eaac864021b8cb')}
HEX64 = re.compile(r'[0-9a-f]{64}\Z')
SAFE_PATH = re.compile(r'[A-Za-z0-9_.\-/]+\Z')
MEMBERS = {'summary.json', 'progress.json', 'source_hashes.json'}
ROOT_FILES = {'checkpoint.json', 'validate_evidence.py', 'test_evidence.py', 'README.md'}
SOURCE_LIMIT = 2 * 1024 * 1024
SOURCE_TOTAL_LIMIT = 32 * 1024 * 1024


class EvidenceError(ValueError):
    """Not the exact bounded failure evidence."""


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
    need(bool(posix.parts) and not posix.is_absolute() and '..' not in posix.parts and str(posix) == path, 'noncanonical path')
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


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def validate_schema(name, value):
    if name == 'summary.json':
        exact(value, SUMMARY)
    elif name == 'progress.json':
        exact(value, PROGRESS)
    elif name == 'source_hashes.json':
        validate_source_schema(value)
        runtime = dict(value['source_sha256'])
        runtime.update(value['generated_sha256'])
        binding = CHECKPOINT['source_binding']
        need(sha256(encoded(value['source_sha256'])) == binding['original_source_manifest_sha256'],
             'original source manifest mismatch')
        need(sha256(encoded(runtime)) == binding['runtime_source_manifest_sha256'],
             'composed source manifest mismatch')
    else:
        raise EvidenceError('unknown safe3 member')


def validate_member(name, raw):
    need(name in MEMBERS, 'unknown safe3 member')
    identity = MEMBER_IDENTITIES[name]
    value = strict_json(raw, identity['bytes'])
    validate_schema(name, value)
    need(len(raw) == identity['bytes'] and sha256(raw) == identity['sha256'],
         'original safe3 bytes changed')
    return value


def no_link_ancestors(path, *, directory=False):
    path = Path(os.path.abspath(path))
    cursor = Path(path.anchor)
    try:
        for component in path.parts[1:]:
            cursor = cursor / component
            mode = cursor.lstat().st_mode
            need(not stat.S_ISLNK(mode), 'symlink path component')
            if cursor != path or directory:
                need(stat.S_ISDIR(mode), 'non-directory path component')
    except OSError as exc:
        raise EvidenceError('unreadable path component') from exc
    return path


def read_bounded(path, limit):
    path = no_link_ancestors(path)
    try:
        need(stat.S_ISREG(path.lstat().st_mode), 'file must be regular')
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
    directory = no_link_ancestors(directory, directory=True)
    try:
        need({entry.name for entry in directory.iterdir()} == set(expected), 'unexpected/missing entries')
    except OSError as exc:
        raise EvidenceError('unreadable evidence directory') from exc


def validate_directory(directory=HERE):
    directory = Path(directory)
    directory_entries(directory, ROOT_FILES | {'safe3'})
    for name in ROOT_FILES:
        read_bounded(directory / name, 128 * 1024)
    checkpoint = strict_json(read_bounded(directory / 'checkpoint.json', 16384), 16384)
    exact(checkpoint, CHECKPOINT)
    directory_entries(directory / 'safe3', MEMBERS)
    values = {name: validate_member(name, read_bounded(directory / 'safe3' / name,
                MEMBER_IDENTITIES[name]['bytes'])) for name in sorted(MEMBERS)}
    exact(values['progress.json'], {key: values['summary.json'][key] for key in PROGRESS})
    exact(checkpoint['last_valid_numeric_progress'], values['summary.json']['numeric_progress'])
    projection = checkpoint['bounded_timing_projection']
    manifest = values['source_hashes.json']
    runtime = dict(manifest['source_sha256'])
    runtime.update(manifest['generated_sha256'])
    for path, digest in projection['source_sha256'].items():
        exact(runtime[path], digest)
    exact(projection['context_sha256'], values['summary.json']['numeric_progress']['context_sha256'])
    exact(projection['source_manifest_sha256'], sha256(encoded(runtime)))
    exact(projection['last_numeric_progress_sha256'], sha256(encoded(SUMMARY['numeric_progress'])))
    return {'status': 'FAILED', 'phase': 'numeric', 'session_id': 99610,
            'process_exit_code': 1, 'numerical_acceptance': False, 'postflight_complete': False,
            'full_29_node_acceptance': False, 'scala_executed': False, 'rtl_executed': False,
            'archive_identity_verified': True, 'numerical_execution_by_validator': False}


def verify_tree_map(source_tree, entries):
    source_tree = no_link_ancestors(source_tree, directory=True)
    total = 0
    for relative, digest in entries.items():
        parts = safe_relative(relative).parts
        raw = read_bounded(source_tree.joinpath(*parts), SOURCE_LIMIT)
        total += len(raw)
        need(total <= SOURCE_TOTAL_LIMIT, 'source total size limit')
        need(sha256(raw) == digest, 'source byte mismatch: ' + relative)
    return total


def validate_source_tree(source_tree, directory=HERE, *, composed=False):
    """Hash source bytes only. Clean source and pinned composed runtime differ.

    Checks do not authenticate Git commit identity, execute code, qualify native
    backends, validate private receipts, or establish Public numerical acceptance.
    """
    need(type(composed) is bool, 'composed flag must be bool')
    result = validate_directory(directory)
    manifest = validate_member('source_hashes.json',
        read_bounded(Path(directory) / 'safe3/source_hashes.json', 39690))
    entries = dict(manifest['source_sha256'])
    if composed:
        entries.update(manifest['generated_sha256'])
    total = verify_tree_map(source_tree, entries)
    contract = strict_json(read_bounded(Path(source_tree) / CONTRACT_PATH, SOURCE_LIMIT), SOURCE_LIMIT)
    exact(contract['generated_sha256'], manifest['generated_sha256'])
    expected = dict(contract['source_sha256'])
    expected[CONTRACT_PATH] = CONTRACT
    exact(expected, manifest['source_sha256'])
    return dict(result, source_tree_role='composed_runtime' if composed else 'clean_original',
                source_tree_identity_verified=True, source_entries=285,
                generated_contract_identities_verified=12, source_bytes_read=total)


def validate_control_records(control, directory=HERE):
    """Optional local provenance check. Read only the five pinned JSON records."""
    result = validate_directory(directory)
    no_link_ancestors(control, directory=True)
    records = {}
    for name, identity in CHECKPOINT['control_record_identities'].items():
        raw = read_bounded(Path(control) / name, identity['bytes'])
        records[name] = strict_json(raw, identity['bytes'])
        need(len(raw) == identity['bytes'] and sha256(raw) == identity['sha256'], 'control identity mismatch')
    terminal = records['terminal-record.json']
    for key, expected in {'session_id': 99610, 'process_exit_code': 1, 'commit': CHECKOUT,
                          'status': 'FAILED', 'phase': 'numeric', 'elapsed_seconds': 2762.816418,
                          'numerical_acceptance': False, 'postflight_complete': False}.items():
        exact(terminal[key], expected)
    exact(terminal['files'], MEMBER_IDENTITIES)
    exact(terminal['numeric_progress'], SUMMARY['numeric_progress'])
    exact(records['session-terminal.json']['terminal_record_sha256'],
          CHECKPOINT['control_record_identities']['terminal-record.json']['sha256'])
    for name in ('observed-terminal.json', 'observed-progress-2143.json'):
        exact(records[name]['numeric'], SUMMARY['numeric_progress'])
    return dict(result, control_record_identities_verified=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=HERE)
    parser.add_argument('--source-tree', type=Path)
    parser.add_argument('--runtime-tree', type=Path)
    parser.add_argument('--control-records', type=Path)
    args = parser.parse_args()
    result = validate_directory(args.directory)
    if args.source_tree is not None:
        validate_source_tree(args.source_tree, args.directory)
        result['clean_original_source_verified'] = True
    if args.runtime_tree is not None:
        validate_source_tree(args.runtime_tree, args.directory, composed=True)
        result['composed_runtime_source_verified'] = True
    if args.control_records is not None:
        validate_control_records(args.control_records, args.directory)
        result['control_record_identities_verified'] = 5
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
