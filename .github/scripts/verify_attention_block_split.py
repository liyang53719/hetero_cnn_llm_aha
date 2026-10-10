#!/usr/bin/env python3
"""Aggregate trusted CI attestations for two independent Attention block cases.

This is not a live capture, reference, DUT, or numerical authority factory. The
caller MUST obtain each expected digest from the corresponding trusted CI job
output, or from members of its artifact ZIP after independently authenticating
the ZIP digest and exact run/job identity through trusted CI metadata. Hashing
unauthenticated downloaded JSON does not establish trust. The immutable
build job supplies the commit/package/build digests. Each consumer supplies its
two compact-file digests. Each consumer must have run cold0 -> carried1 in one
DUT with its own fresh live reference authorities. No cold/carried splice is
accepted. Cross-host hidden inputs may differ; this is never an identical-input
fault comparison, native-model acceptance, M128 acceptance or performance gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'chisel/continuous_prefill/scripts'
sys.path.insert(0, str(SCRIPTS))
import host_bf16_attention_block_fixture as fixture
from host_bf16_attention_block_execution import completion_plan
from host_bf16_attention_block_live_gate import BUILD_STATUS, CASE_STATUS, SCOPE
from host_bf16_attention_block_prefix import STATUS as PREFIX_STATUS, CYCLES as PREFIX_CYCLES
from host_bf16_attention_block_reference import contract_schema, CONTRACT_PATH, PIN_PATH
from host_block_mac_profile import STATUS as PROFILE_STATUS
from real2_ci import hash_map, require, safe_name, sha, unique_object

# The aggregation checker may be newer than the frozen production checkout.
# Every imported production helper and data file must still have frozen bytes.
IMPORTED_SOURCE_PATHS = frozenset(
    Path(module.__file__).resolve() for module in tuple(sys.modules.values())
    if getattr(module, '__file__', None) and any(
        Path(module.__file__).resolve().is_relative_to(directory)
        for directory in (SCRIPTS, ROOT / 'src/heteronpu'))
) | {CONTRACT_PATH, PIN_PATH}

MODES = ('pass', 'final-residual-ack-error')
PASS = 'PASS_ATTENTION_BLOCK_SPLIT_FROZEN_RECIPE_AND_FAULT_PROTOCOL'
FAIL = 'FAIL_ATTENTION_BLOCK_SPLIT_ACCEPTANCE'
CONSUMER_PASS = 'PASS_FRESH_HOST_ATTENTION_BLOCK_CASE_M1'
AUTHORITY_SCOPE = (
    'Trusted CI-job attestation aggregation: one immutable build, independent '
    'fresh pass and final-residual-ack-error same-DUT cold0->carried1 cases. '
    'No live authority is issued by reading JSON; no native-model, M128, '
    'performance, or paired-identical-stimulus fault-comparison acceptance.'
)
MAX_COMPACT_BYTES = 16 * 1024 * 1024
HIDDEN_INPUTS = frozenset(('cold0_hidden.bf16le', 'cold1_hidden.bf16le'))
CACHE_PRODUCERS = {'cache_k': 'rope_k', 'cache_v': 'v'}
EMPTY_SHA256 = hashlib.sha256(b'').hexdigest()
CACHE_EVIDENCE_SCOPE = (
    'Reference cache records describe the full prefix; actual cache records '
    'describe only the current append. Full-prefix preservation and dependency '
    'reads are attested by the authenticated live job and frozen driver/auditor, '
    'with every full-DDR and command-snapshot digest retained. Compact JSON '
    'does not contain cache bytes: the aggregator cannot independently recompute '
    'the carried full-cache or canonical FP32 prior-prefix hash.'
)
REQUIRED_SOURCES = frozenset((
    '.github/scripts/verify_attention_block_split.py',
    '.github/workflows/host-bf16-attention-block.yml',
    'pyproject.toml',
    'config/upstream/qwen3_5_0p8b/layer3_bf16_contract.json',
    'chisel/continuous_prefill/scripts/run_host_bf16_attention_block_fresh_gate.py',
    'chisel/continuous_prefill/scripts/run_host_bf16_attention_block_gate.sh',
    'chisel/continuous_prefill/scripts/host_bf16_attention_block_build_artifact.py',
    'chisel/continuous_prefill/scripts/host_bf16_attention_block_live_gate.py',
    'chisel/continuous_prefill/scripts/host_bf16_attention_block_fixture.py',
    'chisel/continuous_prefill/scripts/host_bf16_attention_block_execution.py',
    'chisel/continuous_prefill/scripts/host_bf16_attention_block_reference.py',
    'chisel/continuous_prefill/scripts/host_block_mac_profile.py',
    'chisel/continuous_prefill/scripts/real2_ci.py',
    'chisel/continuous_prefill/tests/host_bf16_attention_block.cpp',
))
BUILD_KEYS = ('package_sha256', 'binary_sha256', 'rtl_sha256',
              'build_ready_sha256', 'source_manifest_sha256', 'toolchain_sha256')
FALSE_SUMMARY = (
    'native_context_acceptance', 'native_full_block_acceptance', 'full128_executed',
    'fault_restore_supported', 'overall_pass', 'timing_signoff', 'qor_signoff',
    'upstream_gdn_decode_executed', 'cross_host_byte_equivalence_claimed',
    'reference_injection', 'intermediate_preload', 'prior_cache_preload',
)
TRUE_SUMMARY = (
    'actual_host_root', 'experimental_default_off', 'raw_hidden_input',
    'actual_prior_prefix_cache_required', 'input_norm_dut', 'sigmoid_gate_dut',
    'output_projection_dut', 'ffn_supported', 'full_block_supported',
    'scalar_service_shared', 'git_head_verified_unchanged', 'source_immutability_verified',
)
SUMMARY_VALUES = dict(
    representative_tokens_per_launch=1, source_tokens=[0, 1], source_phase='cold_m128',
    host_phases=['cold0', 'carried1'], commands_per_launch=22, descriptors_per_launch=296,
    owner_jobs_per_successful_launch=19, acknowledged_bytes_per_successful_launch=68608,
    shared_trig_shape=[256, 64], same_dut_launches_per_case=2, resets_between_launches=0,
    logical_matrix_engines=1, physical_matrix_slices=8, pinned_idma_instances=1,
    frozen_norm_recipe='C1', frozen_rope_recipe='B1', gqa_recipe='sequential_fma_shared_exp7_v1',
    native_context_gate='UNASSIGNED_DIAGNOSTIC_ONLY_NOT_NATIVE_ACCEPTANCE',
    max_declared_rows=128, fresh_official_executions=2, reused_official_executions=0,
    planned_actual_invocations=1, planned_actual_launches=2,
)


def _digest(value, label):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value),
            'missing/invalid trusted SHA256: ' + label)
    return value


def _object(value, label):
    require(type(value) is dict, 'missing/invalid object: ' + label)
    return value


def _value(record, key, wanted):
    require(key in record and type(record[key]) is type(wanted) and record[key] == wanted,
            'scope/value mismatch: ' + key)


def _regular(path):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'symlink evidence/source path')
    require(path.is_file() and stat.S_ISREG(path.stat().st_mode), 'missing regular file: ' + str(path))
    return path


def _read_trusted(path, expected):
    _digest(expected, str(path))
    path = _regular(path)
    require(0 < path.stat().st_size <= MAX_COMPACT_BYTES, 'empty/oversized compact JSON')
    raw = path.read_bytes()
    require(len(raw) <= MAX_COMPACT_BYTES and hashlib.sha256(raw).hexdigest() == expected,
            'compact digest differs from trusted job output: ' + str(path))
    def invalid_constant(value):
        raise ValueError('non-finite JSON number: ' + value)
    return _object(json.loads(raw, object_pairs_hook=unique_object,
                              parse_constant=invalid_constant), str(path))


def _git(repo, *args):
    result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, timeout=60)
    require(result.returncode == 0, 'git source verification failed: ' + ' '.join(args))
    return result.stdout


def _verify_sources(repo, commit, sources, *, check_github_sha=True):
    """Check bytes in both the clean worktree and the exact committed Git blobs."""
    hash_map(sources)
    require(REQUIRED_SOURCES <= sources.keys(), 'incomplete acceptance source closure')
    require(_git(repo, 'rev-parse', 'HEAD').decode().strip() == commit, 'trusted commit differs from current HEAD')
    require(not check_github_sha or not os.environ.get('GITHUB_SHA') or os.environ['GITHUB_SHA'] == commit,
            'trusted commit differs from GITHUB_SHA')
    require(not _git(repo, 'status', '--porcelain', '--untracked-files=normal').strip(),
            'exact-commit acceptance requires a clean checkout')
    # These are the broad live fixture/source roots. Every present source must
    # be pinned; checking only a self-selected handful would admit a partial map.
    required = set(REQUIRED_SOURCES)
    for directory, pattern in (
        ('src/heteronpu', '*.py'), ('chisel/continuous_prefill/scripts', '*.py'),
        ('chisel/continuous_prefill/src/main/scala', '**/*.scala'),
        ('chisel/p0_safety/src/main/scala', '**/*.scala'),
    ):
        required.update(str(p.relative_to(repo)) for p in (repo / directory).glob(pattern) if p.is_file())
    for directory in ('rtl/matrix', 'rtl/integration', 'chisel/continuous_prefill/src/test/scala',
                      'chisel/continuous_prefill/scripts', 'chisel/continuous_prefill/tests'):
        required.update(str(p.relative_to(repo)) for p in (repo / directory).rglob('*')
                        if p.is_file() and p.suffix in {'.scala', '.sv', '.cpp', '.py', '.sh', '.vlt', '.h', '.inc'})
    require(required <= sources.keys(), 'incomplete live source closure')
    for name, expected in sources.items():
        path = _regular(repo / safe_name(name))
        require(sha(path) == expected, 'worktree source drift: ' + name)
        committed = _git(repo, 'show', commit + ':' + name)
        require(hashlib.sha256(committed).hexdigest() == expected, 'committed source drift: ' + name)


def _verify_imported_sources(sources):
    for path in sorted(IMPORTED_SOURCE_PATHS):
        name = str(path.relative_to(ROOT))
        require(name in sources, 'unbound imported production helper/data: ' + name)
        require(sha(_regular(path)) == sources[name], 'imported production helper/data drift: ' + name)


def _bound_sources(subset, sources, label):
    hash_map(subset)
    require(all(sources.get(name) == value for name, value in subset.items()),
            'unbound reference source: ' + label)


def _verify_cache_reference(reference):
    """Check full-prefix geometry/provenance without pretending hashes are bytes."""
    for index, phase in enumerate(fixture.SOURCE_PHASES):
        case = reference['cases'][phase]
        _value(case, 'cache_prefix_origin', 'cold_empty' if index == 0 else
               'previous_launch_canonical_append_outputs')
        prefix = _digest(case.get('canonical_cache_prefix_sha256'), phase + ' canonical cache prefix')
        if index == 0:
            require(prefix == EMPTY_SHA256, 'cold cache prefix must be empty')
        else:
            require(prefix != EMPTY_SHA256, 'carried canonical cache prefix cannot be empty')
        expected = reference['expected'][phase]
        for cache, producer in CACHE_PRODUCERS.items():
            # The reference contains [prior prefix | current append]. The
            # fixture packs only its current 1024-byte tail for actual_* files.
            full = expected[cache + '.bf16le']
            tail = expected[producer + '.bf16le']
            _value(full, 'bytes', (index + 1) * 1024)
            _value(tail, 'bytes', 1024)
            if index == 0:
                _value(full, 'sha256', tail['sha256'])
            else:
                require(full['sha256'] not in (tail['sha256'],
                        reference['expected']['cold0'][cache + '.bf16le']['sha256']),
                        'full cache reference cannot be relabelled as a single-token cache: ' + cache)


def _verify_build(summary, hashes, trusted):
    transfer = _object(summary.get('build_transfer'), 'build_transfer')
    for key, wanted in dict(schema=1, status=BUILD_STATUS, scope=SCOPE, numerical_pass=False,
                            source_commit=trusted['commit']).items():
        _value(transfer, key, wanted)
    for key in BUILD_KEYS:
        _value(transfer, key, trusted[key])
    ready = _object(summary.get('build'), 'build')
    for key, wanted in dict(status=BUILD_STATUS, numerical_pass=False, initial_verilation_exit=0,
                            source_base_commit=trusted['commit'], native_full_block_acceptance=False,
                            model_m128_accepted=False, overall_pass=False).items():
        _value(ready, key, wanted)
    require(ready.get('source_snapshot_manifest_sha256') is None, 'rebound build snapshot is not exact-commit evidence')
    for key in ('binary_sha256', 'rtl_sha256', 'source_manifest_sha256', 'toolchain_sha256'):
        _value(ready, key, trusted[key])
    for key in ('binary_sha256', 'rtl_sha256', 'build_ready_sha256'):
        _value(hashes, key, trusted[key])
    identity = hash_map(hashes.get('build_identity_sha256'))  # Historical name: this is a map.
    identity_fields = {
        'obj/VHostBlockTop': 'binary_sha256', 'generated/HostBlockTop.sv': 'rtl_sha256',
        'sources.sha256.json': 'source_manifest_sha256', 'toolchain.json': 'toolchain_sha256',
        'build_ready.json': 'build_ready_sha256', 'generated/SCOPE.json': 'scope_sha256',
        'actual_verilator_after.json': 'actual_verilator_sha256',
        'compiler_jars.sha256.json': 'compiler_jars_sha256',
        'hardfloat.sha256.json': 'hardfloat_manifest_sha256',
    }
    require(set(identity) == set(identity_fields), 'incomplete immutable build identity')
    for name, key in identity_fields.items():
        _value(identity, name, trusted[key] if key in trusted else _digest(ready.get(key), key))
    toolchain = _object(summary.get('toolchain'), 'toolchain')
    _value(toolchain, 'compiler_jars_verified_after_build', True)
    for key in ('compiler_jars_sha256', 'hardfloat_source_sha256', 'idma_export_source_sha256'):
        hash_map(toolchain.get(key))
    actual = _object(ready.get('actual_verilator'), 'actual Verilator')
    backend = _object(actual.get('actual_elf'), 'actual Verilator ELF')
    _value(backend, 'kind', 'ELF')
    _digest(backend.get('sha256'), 'actual Verilator ELF')
    require('Verilator 5.032' in backend.get('version', ''), 'unpinned actual Verilator ELF')


def _verify_reference(summary, hashes):
    reference = _object(summary.get('block_reference'), 'block_reference')
    # This existing checker validates receipt scope and all independent proof
    # inventories. It does not reissue a live reference authority from JSON.
    inventory = fixture.reference_inventory(reference)
    for name, row in inventory.items():
        _object(row, name)
        _digest(row.get('sha256'), name)
        require(type(row.get('bytes')) is int and row['bytes'] > 0, 'invalid reference byte count')
    canonical = (json.dumps(reference, sort_keys=True, separators=(',', ':')) + '\n').encode()
    _value(hashes, 'block_reference_receipt_sha256', hashlib.sha256(canonical).hexdigest())
    _value(reference, 'schema_version', 1)
    _value(reference, 'variant', 'baseline')
    require(type(reference.get('model_revision')) is str and re.fullmatch('[0-9a-f]{40}', reference['model_revision']),
            'missing model revision')
    _value(reference, 'model_revision', json.loads(CONTRACT_PATH.read_text())['revision'])
    _value(reference, 'schema', contract_schema())
    for key in ('original_projection_gate_pass', 'original_norm_rope_gate_pass'):
        _value(reference, key, True)
    _value(reference, 'gqa_native_gate', 'UNASSIGNED_DIAGNOSTIC_ONLY_NOT_NATIVE_ACCEPTANCE')
    for key in ('source_sha256_before', 'source_sha256_after'):
        _bound_sources(reference[key], hashes['source_sha256'], key)
    inputs = hash_map(hashes.get('input_sha256'))
    require(set(inputs) == set(fixture.INPUTS), 'incomplete raw hidden/weight/trig inventory')
    require(inputs == {name: row['sha256'] for name, row in reference['inputs'].items()},
            'reference input identity mismatch')
    for name, size in fixture.INPUTS.items():
        _value(reference['inputs'][name], 'bytes', size)
    manifest = _digest(hashes.get('official_capture_manifest_sha256'), 'official capture manifest')
    _value(reference, 'official_manifest_sha256', manifest)
    _value(summary, 'official_manifest_sha256', manifest)
    capture = _object(reference.get('original_capture_evidence'), 'original capture evidence')
    for key in ('fresh_official_executions', 'reused_official_executions', 'official_manifest_sha256'):
        _value(capture, key, summary[key])
    for index, phase in enumerate(fixture.SOURCE_PHASES):
        _value(reference['cases'][phase], 'raw_hidden_sha256', inputs[phase + '_hidden.bf16le'])
        _value(reference['cases'][phase]['selected_trig'], 'backing_sha256', inputs['trig.bf16le'])
    scope = _object(reference.get('original_component_gate_scope'), 'original component gate scope')
    for key, name in (('projection_receipt_sha256', 'projection_reference_receipt_sha256'),
                      ('norm_rope_receipt_sha256', 'attention_reference_receipt_sha256')):
        _value(scope, key, _digest(hashes.get(name), name))
    _value(summary['projection_reference'], 'native_operator_gate_pass', True)
    _value(summary['attention_reference'], 'original_operator_gate_pass', True)
    _value(summary['attention_reference'], 'official_manifest_sha256', manifest)
    _value(summary['attention_reference'], 'projection_reference_receipt_sha256', hashes['projection_reference_receipt_sha256'])
    failures = _object(summary.get('native_full_block_failures'), 'native failure evidence')
    original = _object(reference.get('original_native_full_block_failures'), 'reference native failures')
    require(set(failures) == set(original) == {'baseline', 'avx2'}, 'missing native failure variants')
    for variant in ('baseline', 'avx2'):
        report_hash = _digest(summary['native_audit_report_sha256'][variant], 'native audit')
        _value(original[variant], 'report_sha256', report_hash)
        for key in ('gate_pass', 'status', 'failed_producers', 'failed_softmax_invariants'):
            _value(original[variant], key, failures[variant][key])
        _value(failures[variant], 'gate_pass', False)
        require(failures[variant]['failed_producers'] or failures[variant]['failed_softmax_invariants'],
                'native failure records were erased')
    _verify_cache_reference(reference)
    return reference


def _verify_case(summary, hashes, mode, trusted):
    cases = summary.get('cases')
    require(type(cases) is list and len(cases) == 1 and cases[0].get('mode') == mode,
            'missing/extra/wrong case mode inventory')
    result = _object(cases[0].get('result'), 'case result')
    for key, wanted in dict(status=CASE_STATUS, mode=mode, actual_dut_identity_verified=True,
            live_authorities_verified=True, source_immutability_verified=True,
            same_dut_launches=2, resets_between_launches=0, full_block_m1_executed=True,
            full_block_supported=True, full_block_artifact_consistency=True,
            numerical_acceptance_eligible=mode == 'pass', frozen_recipe_block_acceptance=mode == 'pass',
            intermediate_preload=False, prior_cache_preload=False, native_context_acceptance=False,
            native_full_block_acceptance=False, native_full_block_accepted=False, model_m128_accepted=False,
            overall_pass=False, reset_restore_executed=False).items():
        _value(result, key, wanted)
    for key in ('binary_sha256', 'rtl_sha256', 'build_ready_sha256'):
        _value(result, key, trusted[key])
    _value(result, 'block_reference_receipt_sha256', hashes['block_reference_receipt_sha256'])
    _value(result, 'input_sha256', hashes['input_sha256'])
    _digest(result.get('fixture_sha256'), 'actual fixture')
    log = _digest(result.get('log_sha256'), 'actual log')
    identity = _object(result.get('execution_identity'), 'actual execution identity')
    _value(identity, 'log_sha256', log)
    files = hash_map(identity.get('files_sha256'))
    actual = _object(result.get('actual_sha256'), 'actual output hashes')
    require(set(actual) == set(fixture.PHASES), 'missing output phase')
    _value(hashes, 'output_sha256', {mode: actual})
    runs = result.get('runs')
    require(type(runs) is list and len(runs) == 2 and [row.get('phase') for row in runs] == list(fixture.PHASES),
            'incomplete/reordered same-DUT pair')
    expected_files = {}
    for index, phase in enumerate(fixture.PHASES):
        row = runs[index]
        failing = mode != 'pass' and index == 1
        for key, wanted in dict(status=3 if failing else 0, checkpoint_accepted=not failing,
                                inferred_committed_length=1 if failing else index + 1,
                                inferred_committed_generation=1 if failing else index + 1).items():
            _value(row, key, wanted)
        require(type(row.get('inferred_final_output')) is int and row['inferred_final_output'] > 0,
                'missing inferred committed output')
        require(set(hash_map(actual[phase])) == set(fixture.NAMES), 'missing actual terminal output')
        expected = summary['block_reference']['expected'][fixture.SOURCE_PHASES[index]]
        for name, width in zip(fixture.NAMES, fixture.WIDTHS):
            _value(expected[name + '.bf16le'], 'bytes', width * 2 *
                   (index + 1 if name in CACHE_PRODUCERS else 1))
            producer = CACHE_PRODUCERS.get(name, name)
            _value(actual[phase], name, expected[producer + '.bf16le']['sha256'])
        expected_files.update({phase + '/actual_' + name + '.bf16le': digest for name, digest in actual[phase].items()})
        snapshots = hash_map(row.get('snapshot_sha256'))
        require(set(snapshots) == {'writable_after_command' + str(pc) + '.bin' for pc in completion_plan(failing)},
                'missing command snapshot outputs')
        expected_files.update({phase + '/' + name: digest for name, digest in snapshots.items()})
        expected_files[phase + '/ddr_after.bin'] = _digest(row.get('ddr_sha256'), 'actual DDR')
    require(files == expected_files, 'actual output/snapshot/DDR identity mismatch')
    if mode != 'pass':
        require(runs[1]['inferred_final_output'] == runs[0]['inferred_final_output'],
                'fault incorrectly committed final output')
    profiles = _object(summary.get('measured_mac_profiles'), 'MAC profiles')
    require(set(profiles) == {mode}, 'missing/extra MAC profile modes')
    profile = profiles[mode]
    for key, wanted in dict(status=PROFILE_STATUS, mode=mode, log_sha256=log,
                            actual_dut_identity_verified=True, numerical_acceptance=False,
                            performance_acceptance=False).items():
        _value(profile, key, wanted)
    for key in ('binary_sha256', 'rtl_sha256', 'build_ready_sha256'):
        _value(profile, key, trusted[key])
    require(profile.get('fixed_resources') == dict(logical_matrix_engines=1, physical_slices=8,
            rows_per_slice=16, columns_per_slice=32, macs_per_cycle=4096), 'MAC physical resource scope')
    measured = profile.get('runs')
    require(type(measured) is list and len(measured) == 2, 'incomplete MAC profile pair')
    for index, row in enumerate(measured):
        failing = mode != 'pass' and index == 1
        for key, wanted in dict(run=index, phase=fixture.PHASES[index], hardware_status=3 if failing else 0).items():
            _value(row, key, wanted)
        require(type(row.get('cycles')) is int and row['cycles'] > 0 and
                row.get('end_cycle', 0) - row.get('begin_cycle', 0) == row['cycles'], 'invalid measured cycles')
        require([entry.get('pc') for entry in row.get('commands', [])] == completion_plan(failing),
                'MAC profile command inventory')
    return result


def _verify_prefixes(summary, hashes, trusted):
    prefixes = _object(summary.get('deterministic_prefixes'), 'deterministic prefixes')
    for key, wanted in dict(status=PREFIX_STATUS, numerical_acceptance=False, full_block_m1_executed=False,
                            actual_dut_identity_verified=True, live_authorities_verified=True,
                            raw_prefix_events_upload_allowed=False, cycles_per_prefix=PREFIX_CYCLES,
                            input_sha256=hashes['input_sha256']).items():
        _value(prefixes, key, wanted)
    for key in ('binary_sha256', 'rtl_sha256', 'build_ready_sha256'):
        _value(prefixes, key, trusted[key])
    rows = prefixes.get('prefixes')
    require(type(rows) is list and len(rows) == 2, 'incomplete deterministic prefixes')
    for row in rows:
        for key in ('report_sha256', 'deterministic_sha256', 'terminal_event_sha256', 'event_sha256', 'log_sha256'):
            _digest(row.get(key), 'prefix ' + key)
        for key, wanted in dict(cycles=PREFIX_CYCLES, reset_cycles=6, active_cycles=PREFIX_CYCLES - 36).items():
            _value(row['counters'], key, wanted)
    for key in ('deterministic_sha256', 'event_sha256', 'event_bytes', 'log_sha256', 'terminal_event_sha256', 'counters'):
        _value(rows[1], key, rows[0][key])


def _verify_consumer(summary, hashes, mode, trusted):
    for key, wanted in dict(status=CONSUMER_PASS, stage='complete', scope=SCOPE,
                            git_head=trusted['commit'], requested_mode=mode,
                            numerical_acceptance=mode == 'pass',
                            frozen_recipe_block_acceptance=mode == 'pass', **SUMMARY_VALUES).items():
        _value(summary, key, wanted)
    for key in TRUE_SUMMARY:
        _value(summary, key, True)
    for key in FALSE_SUMMARY:
        _value(summary, key, False)
    for key in ('performance_acceptance', 'model_m128_accepted', 'full128_accepted'):
        require(summary.get(key, False) is False, 'unsupported acceptance: ' + key)
    require('error' not in summary and 'final_capture_verification_error' not in summary,
            'consumer retained a failure')
    if 'supervisor' in summary:
        for key, wanted in dict(forced_shutdown=False, returncode=0, worker_returncode=0).items():
            _value(summary['supervisor'], key, wanted)
    _verify_build(summary, hashes, trusted)
    reference = _verify_reference(summary, hashes)
    _verify_prefixes(summary, hashes, trusted)
    _verify_case(summary, hashes, mode, trusted)
    return reference


def _base_report():
    return dict(schema=1, status=FAIL, authority_scope=AUTHORITY_SCOPE,
                split_case_acceptance=False, numerical_acceptance=False,
                frozen_recipe_block_acceptance=False, fault_protocol_acceptance=False,
                live_authority_reissued=False, native_context_acceptance=False,
                native_full_block_acceptance=False, model_m128_accepted=False,
                full128_executed=False, overall_pass=False, performance_acceptance=False,
                timing_signoff=False, qor_signoff=False,
                paired_identical_stimulus_fault_comparison=False,
                cross_host_byte_equivalence_claimed=False,
                cache_evidence_scope=CACHE_EVIDENCE_SCOPE,
                cache_reference_contract_verified=False, cache_append_digest_verified=False,
                cache_full_prefix_preservation_live_attested=False,
                cache_full_prefix_bytes_independently_verified=False,
                carried_canonical_prefix_hash_recomputed=False)


def _cache_evidence(summary):
    reference = summary['block_reference']
    result = summary['cases'][0]['result']
    evidence = {}
    for index, phase in enumerate(fixture.PHASES):
        source_phase = fixture.SOURCE_PHASES[index]
        case = reference['cases'][source_phase]
        expected = reference['expected'][source_phase]
        evidence[phase] = dict(
            reference_source_phase=source_phase,
            cache_prefix_origin=case['cache_prefix_origin'],
            canonical_prior_prefix_fp32_sha256=case['canonical_cache_prefix_sha256'],
            prior_prefix_reference_source_phase='cold0' if index else None,
            prior_prefix_reference={cache: reference['expected']['cold0'][cache + '.bf16le']
                                    for cache in CACHE_PRODUCERS} if index else {},
            full_prefix_reference={cache: expected[cache + '.bf16le'] for cache in CACHE_PRODUCERS},
            actual_append={cache: dict(bytes=1024, sha256=result['actual_sha256'][phase][cache],
                                      canonical_producer=producer)
                           for cache, producer in CACHE_PRODUCERS.items()},
            full_ddr_sha256=result['runs'][index]['ddr_sha256'],
            command_snapshot_sha256=result['runs'][index]['snapshot_sha256'])
    return evidence


def verify(pass_compact, fault_compact, *, expected_commit, expected_package_sha256,
           expected_binary_sha256, expected_rtl_sha256, expected_build_ready_sha256,
           expected_source_manifest_sha256, expected_toolchain_sha256,
           expected_pass_summary_sha256, expected_pass_hashes_sha256,
           expected_fault_summary_sha256, expected_fault_hashes_sha256, repo=None):
    """Validate externally pinned CI attestations, never infer their authority."""
    require(type(expected_commit) is str and re.fullmatch('[0-9a-f]{40}', expected_commit),
            'exact trusted Git commit required')
    trusted = dict(commit=expected_commit, package_sha256=expected_package_sha256,
                   binary_sha256=expected_binary_sha256, rtl_sha256=expected_rtl_sha256,
                   build_ready_sha256=expected_build_ready_sha256,
                   source_manifest_sha256=expected_source_manifest_sha256,
                   toolchain_sha256=expected_toolchain_sha256)
    for key in BUILD_KEYS:
        _digest(trusted[key], key)
    pins = {
        MODES[0]: dict(summary_sha256=expected_pass_summary_sha256, hashes_sha256=expected_pass_hashes_sha256),
        MODES[1]: dict(summary_sha256=expected_fault_summary_sha256, hashes_sha256=expected_fault_hashes_sha256),
    }
    for mode, values in pins.items():
        for key, value in values.items():
            _digest(value, mode + ':' + key)
    evidence, references = {}, {}
    for mode, directory in zip(MODES, (pass_compact, fault_compact)):
        directory = Path(directory)
        summary = _read_trusted(directory / 'summary.json', pins[mode]['summary_sha256'])
        hashes = _read_trusted(directory / 'source_input_hashes.json', pins[mode]['hashes_sha256'])
        evidence[mode] = dict(summary=summary, source_input_hashes=hashes)
    first, second = (evidence[mode] for mode in MODES)
    sources = first['source_input_hashes']['source_sha256']
    require(sources == second['source_input_hashes']['source_sha256'], 'cross-job source closure mismatch')
    _verify_sources(ROOT if repo is None else Path(repo).resolve(), expected_commit, sources,
                    check_github_sha=repo is None)
    if repo is not None:
        # Explicit --repo permits a newer aggregation workflow/checker, never a
        # different production commit or drifted imported production helpers.
        checker_commit = _git(ROOT, 'rev-parse', 'HEAD').decode().strip()
        require(not os.environ.get('GITHUB_SHA') or os.environ['GITHUB_SHA'] == checker_commit,
                'checker commit differs from GITHUB_SHA')
        _verify_imported_sources(sources)
    for mode, item in evidence.items():
        references[mode] = _verify_consumer(item['summary'], item['source_input_hashes'], mode, trusted)
    for key in ('build', 'toolchain', 'build_transfer'):
        require(first['summary'][key] == second['summary'][key], 'cross-job immutable build identity mismatch: ' + key)
    require(references[MODES[0]]['model_revision'] == references[MODES[1]]['model_revision'], 'cross-job model revision mismatch')
    inputs = {mode: evidence[mode]['source_input_hashes']['input_sha256'] for mode in MODES}
    shared = {name: digest for name, digest in inputs[MODES[0]].items() if name not in HIDDEN_INPUTS}
    require(shared == {name: digest for name, digest in inputs[MODES[1]].items() if name not in HIDDEN_INPUTS},
            'cross-job weight/trig identity mismatch')
    raw_hidden = {mode: {name: values[name] for name in sorted(HIDDEN_INPUTS)} for mode, values in inputs.items()}
    report = _base_report()
    report.update(status=PASS, split_case_acceptance=True, numerical_acceptance=True,
        frozen_recipe_block_acceptance=True, fault_protocol_acceptance=True,
        git_head=expected_commit, exact_clean_commit_verified=True,
        source_immutability_verified=True, trusted_build=trusted, trusted_compact_digests=pins,
        explicit_production_checkout=repo is not None,
        cache_reference_contract_verified=True, cache_append_digest_verified=True,
        cache_full_prefix_preservation_live_attested=True,
        cache_evidence={mode: _cache_evidence(item['summary']) for mode, item in evidence.items()},
        mode_inventory=list(MODES), same_dut_launches_per_case=2, resets_between_launches=0,
        model_revision=references[MODES[0]]['model_revision'], shared_weight_trig_sha256=shared,
        actual_raw_hidden_sha256=raw_hidden,
        raw_hidden_observed_equal={name: inputs[MODES[0]][name] == inputs[MODES[1]][name] for name in sorted(HIDDEN_INPUTS)},
        all_raw_hidden_observed_equal=raw_hidden[MODES[0]] == raw_hidden[MODES[1]],
        native_full_block_failures={mode: evidence[mode]['summary']['native_full_block_failures'] for mode in MODES},
        # Preserve every native failure, diagnostic, threshold and original
        # reference record from both authenticated jobs without deduplication.
        consumer_evidence=evidence)
    return report


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('--pass-compact', required=True, type=Path)
    result.add_argument('--fault-compact', required=True, type=Path)
    result.add_argument('--expected-commit', required=True)
    result.add_argument('--repo', type=Path,
                        help='explicit clean frozen production checkout; GITHUB_SHA identifies the checker checkout')
    for key in BUILD_KEYS:
        result.add_argument('--expected-' + key.replace('_', '-'), required=True)
    for mode in ('pass', 'fault'):
        for kind in ('summary', 'hashes'):
            result.add_argument('--expected-' + mode + '-' + kind + '-sha256', required=True)
    result.add_argument('--output', required=True, type=Path)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    output = args.output.absolute()
    require(not output.exists() and not any(p.is_symlink() for p in (output, *output.parents)),
            'new regular report output required')
    values = vars(args).copy()
    values.pop('output')
    try:
        report, code = verify(**values), 0
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
        report, code = _base_report(), 1
        report['error'] = dict(type=type(error).__name__, message=str(error))
        # Even on a partial/failed job, retain every individually authenticated
        # compact file. Never retain untrusted bytes under an evidence label.
        evidence = {}
        for mode, label, directory in ((MODES[0], 'pass', args.pass_compact), (MODES[1], 'fault', args.fault_compact)):
            for key, filename in (('summary', 'summary.json'), ('hashes', 'source_input_hashes.json')):
                try:
                    value = _read_trusted(directory / filename, getattr(args, 'expected_' + label + '_' + key + '_sha256'))
                    evidence.setdefault(mode, {})[key] = value
                except (ValueError, OSError):
                    pass
        report['authenticated_partial_evidence'] = evidence
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    print(report['status'] + ': ' + report['authority_scope'])
    if code:
        print(report['error']['message'], file=sys.stderr)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
