#!/usr/bin/env python3
"""Fresh production Host GDN CI with a receiver-selected build profile.

The build job transfers only its simulator, RTL and identity receipts. Each
case job regenerates its bounded official two-token input and independent
reference in-process. No persisted fixture is an acceptance input. Dense/Conv
v1 remains the default; core acceptance stops before output projection.
This entrypoint is not evidence of a production numerical PASS.
"""
from pathlib import Path
import argparse
import contextlib
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import time

from real2_ci import (BoundedReader, MAX_BYTES, describe, encoded, git_commit,
                      hash_map, read_json, require, runtime_identity, safe_name,
                      save, sha, tail, unique_object, validate_maps)
from pack_host_bf16_gdn_fixture import ROOT, _sources, generate_fixture
from host_bf16_gdn_execution import (BUILD_STATUS, SCOPE, _build_identity,
                                    authenticate_fixture, run_case,
                                    verify_all_build_sources)

SCRIPT = 'chisel/continuous_prefill/scripts/run_host_bf16_gdn_fresh_gate.py'
WORKFLOW = '.github/workflows/host-bf16-gdn.yml'
CORE_WORKFLOW = '.github/workflows/host-bf16-gdn-core.yml'
CORE_SCOPE = 'GDN_CORE_M1_BEFORE_OUTPUT_PROJECTION'
CORE_BUILD_STATUS = 'BUILT_HOST_GDN_CORE_ONLY_NOT_NUMERICAL_PASS'
CORE_FIXTURE_SCOPE = 'DENSE_QKV_Z_AB_CONV4_INPUT_PREP_FP32_RECURRENT_GATED_NORM_FENCE_ONLY'
CORE_PENDING_GATES = ('fault_injection', 'reset_recovery', 'checkpoint_restore',
                      'native_core_acceptance', 'full_block_acceptance')
PROFILES = ('dense-conv', 'core')
MANIFEST = 'gdn_package_manifest.json'
FILES = frozenset((
    'obj/VHostBlockTop', 'generated/HostBlockTop.sv', 'generated/SCOPE.json',
    'build_ready.json', 'build.exit', 'source_base_commit.txt',
    'sources.sha256.json', 'hardfloat.sha256.json', 'source_scope.json',
    'toolchain.json', 'compiler_jars.sha256.json', 'idma_identity.json',
    'actual_verilator_before.json', 'actual_verilator_after.json',
))
ENTRY_SOURCES = (SCRIPT, WORKFLOW, 'pyproject.toml',
                 'scripts/collect_qwen35_layer0_payload.py',
                 'scripts/collect_qwen35_prefix_payload.py',
                 'scripts/check_git_payloads.py')
COMPACT_FILES = frozenset(('summary.json', 'source_input_hashes.json'))
CI_MODES = ('pass', 'last-history-ack-error', 'output-alias', 'reset-recovery')


def profile_contract(profile):
    require(profile in PROFILES, 'unknown GDN profile')
    core = profile == 'core'
    return dict(scope=CORE_SCOPE if core else SCOPE,
                build_status=CORE_BUILD_STATUS if core else BUILD_STATUS,
                modes=('pass',) if core else CI_MODES,
                timeout_limit=7200 if core else 5400)


def fresh_output(path):
    path = Path(path)
    require(not path.is_symlink(), 'output root symlink')
    path = path.resolve()
    require(path.is_relative_to(ROOT / 'work') and path != ROOT / 'work'
            and not path.exists(), 'new output under ignored work required')
    path.mkdir(parents=True)
    return path


def source_closure(build=None, *, profile='dense-conv'):
    profile_contract(profile)
    sources = _sources()
    entry_sources = ENTRY_SOURCES
    if profile == 'core':
        from pack_host_bf16_gdn_core_fixture import _sources as core_sources
        for name, digest in core_sources().items():
            require(name not in sources or sources[name] == digest, 'source identity conflict: ' + name)
            sources[name] = digest
        entry_sources = tuple(name for name in ENTRY_SOURCES if name != WORKFLOW) + (
            CORE_WORKFLOW, 'chisel/continuous_prefill/config/host_bf16_gdn_core_descriptor_contract.json',
            'chisel/continuous_prefill/scripts/host_bf16_gdn_execution.py',
            'chisel/continuous_prefill/scripts/host_bf16_qkv_execution.py',
            'chisel/continuous_prefill/scripts/verify_host_bf16_gdn_fixture.py',
            'chisel/continuous_prefill/scripts/real2_ci.py',
            'chisel/continuous_prefill/scripts/verify_real_two_layer.py')
    sources.update({name: sha(ROOT / name) for name in entry_sources})
    if build is not None:
        for name, digest in hash_map(read_json(build / 'sources.sha256.json')).items():
            require(name not in sources or sources[name] == digest, 'source identity conflict: ' + name)
            sources[name] = digest
    return hash_map(sources)


def verify_checkout(commit, sources):
    require(re.fullmatch('[0-9a-f]{40}', commit) and git_commit(ROOT) == commit,
            'checkout differs from trusted source commit')
    require(not os.environ.get('GITHUB_SHA') or os.environ['GITHUB_SHA'] == commit,
            'checkout differs from GITHUB_SHA')
    tracked = set(subprocess.check_output(
        ['git', '-C', str(ROOT), 'ls-tree', '-rz', '--name-only', commit]).decode().split('\0'))
    require(set(sources) <= tracked, 'source closure contains uncommitted files')
    dirty = subprocess.check_output(
        ['git', '-C', str(ROOT), 'status', '--porcelain', '--untracked-files=normal'], text=True)
    require(not dirty.strip(), 'exact-commit gate requires a clean checkout')
    for name, digest in hash_map(sources).items():
        path = ROOT / name
        require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(ROOT)
                and sha(path) == digest, 'source changed: ' + name)


def build_admission(build, commit, *, profile='dense-conv'):
    contract = profile_contract(profile)
    core = profile == 'core'
    identity = _build_identity(build, profile=profile)
    ready = read_json(build / 'build_ready.json')
    require(ready['source_base_commit'] == commit
            and (build / 'source_base_commit.txt').read_text().strip() == commit,
            'build source commit mismatch')
    require((build / 'build.exit').read_text().strip() == '0'
            and ready['initial_verilation_exit'] == 0, 'build did not complete')
    require(ready.get('source_snapshot_manifest_sha256') is None,
            'CI must build the exact clean commit, not an external snapshot')
    require(read_json(build / 'source_scope.json') == {'scope': 'full', 'unrelated_helpers_bound': True},
            'full source scope required')
    scope = read_json(build / 'generated/SCOPE.json')
    expected = dict(experimental_bf16_gdn=True, default_enabled=False, scope=contract['scope'],
                    policy_version=2 if core else 1, hidden=1024, gdn_channels=6144, conv_kernel=4,
                    scalar_service_shared=True, full_block_supported=False, burst_writes=False,
                    logical_matrix_engines=1, physical_matrix_slices=8, pinned_idma_instances=1)
    expected.update(dict(experimental_gdn_core=True, max_tokens=1, heads=16, head_dim=128,
                         managed_state_contexts=1, softplus_enabled=True, recurrent_state_dtype='FP32',
                         output_projection_supported=False, ffn_supported=False, timing_signoff=False)
                    if core else dict(recurrent_state_supported=False, gated_norm_supported=False))
    require(all(type(scope.get(k)) is type(v) and scope[k] == v for k, v in expected.items()),
            'wrong GDN ' + profile + ' build profile')
    hf = Path(os.environ.get('HARDFLOAT_SOURCE', ROOT / 'work/upstream/hardfloat_continuous')).resolve()
    require(Path(ready['hardfloat_source']) == hf, 'HardFloat build path differs; do not rebind receipts')
    validate_maps(ROOT, build, hf)
    toolchain = read_json(build / 'toolchain.json')
    require(toolchain['compiler_jars_verified_after_build'] is True
            and toolchain['compiler_jars_sha256'] == read_json(build / 'compiler_jars.sha256.json')
            and toolchain['hardfloat_source_sha256'] == read_json(build / 'hardfloat.sha256.json')
            and toolchain['idma_identity'] == read_json(build / 'idma_identity.json'),
            'tool/source receipt mismatch')
    tools = toolchain['tools']
    require('Verilator 5.032' in tools['verilator_backend']['version']
            and '1.62.1' in tools['firtool']['version'], 'unpinned Verilator/firtool')
    actual = read_json(build / 'actual_verilator_after.json')
    require(actual == read_json(build / 'actual_verilator_before.json') == ready['actual_verilator']
            and actual['actual_elf']['kind'] == 'ELF'
            and re.fullmatch('[0-9a-f]{64}', actual['actual_elf']['sha256'])
            and actual['entrypoint']['sha256'] == tools['verilator_backend']['sha256']
            and actual['actual_elf']['version'] == tools['verilator_backend']['version'],
            'actual Verilator ELF identity mismatch')
    sources = source_closure(build, profile=profile)
    verify_checkout(commit, sources)
    verify_all_build_sources(build, source_root=ROOT)
    return ready, sources, identity


def package(build, output, commit, *, profile='dense-conv'):
    contract = profile_contract(profile)
    ready, sources, _ = build_admission(build, commit, profile=profile)
    files = {name: describe(build / name) for name in sorted(FILES)}
    manifest = dict(schema=1, status=contract['build_status'], numerical_pass=False,
                    build_profile=profile, scope=contract['scope'],
                    source_commit=commit, sources=sources, files=files,
                    binary_sha256=ready['binary_sha256'], rtl_sha256=ready['rtl_sha256'])
    validate_manifest(manifest, commit, profile=profile)
    with output.open('xb') as raw, gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as zipped, \
            tarfile.open(fileobj=zipped, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        for name in [MANIFEST] + sorted(FILES):
            data = encoded(manifest) if name == MANIFEST else (build / name).read_bytes()
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            entry.mode = 0o755 if name == 'obj/VHostBlockTop' else 0o644
            archive.addfile(entry, io.BytesIO(data))
    digest = sha(output)
    validate_archive(output, digest, commit, profile=profile)
    return digest, manifest


def validate_manifest(manifest, commit, *, profile='dense-conv'):
    contract = profile_contract(profile)
    require(type(manifest) is dict, 'package manifest must be an object')
    require(re.fullmatch('[0-9a-f]{40}', commit) and type(manifest.get('schema')) is int
            and manifest['schema'] == 1
            and manifest.get('source_commit') == commit, 'package commit/schema mismatch')
    require(manifest.get('build_profile') == profile and manifest.get('scope') == contract['scope'],
            'package does not match receiver-selected GDN profile')
    require(manifest.get('status') == contract['build_status'] and manifest.get('numerical_pass') is False,
            'package must carry build-only status')
    files = manifest['files']
    require(type(files) is dict and set(files) == FILES, 'package file allowlist mismatch')
    for name, row in files.items():
        safe_name(name)
        require(type(row) is dict, 'invalid package file identity')
        limit = 96 * 1024 * 1024 if name.endswith('.sv') else 16 * 1024 * 1024 if name == 'obj/VHostBlockTop' else 2 * 1024 * 1024
        require(type(row.get('bytes')) is int and 0 < row['bytes'] <= limit
                and type(row.get('sha256')) is str and re.fullmatch('[0-9a-f]{64}', row['sha256']),
                'invalid package file identity')
    require(sum(row['bytes'] for row in files.values()) <= MAX_BYTES, 'package exceeds size bound')
    require(manifest['binary_sha256'] == files['obj/VHostBlockTop']['sha256']
            and manifest['rtl_sha256'] == files['generated/HostBlockTop.sv']['sha256'],
            'package binary/RTL digest mismatch')
    hash_map(manifest['sources'])
    return files


def validate_archive(path, digest, commit, *, profile='dense-conv'):
    profile_contract(profile)
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_BYTES,
            'invalid package archive')
    require(re.fullmatch('[0-9a-f]{64}', digest) and sha(path) == digest,
            'archive digest differs from trusted build-job output')
    seen = set()
    manifest = None
    with gzip.open(path, 'rb') as raw, tarfile.open(fileobj=BoundedReader(raw), mode='r|', ignore_zeros=True) as archive:
        for entry in archive:
            name = safe_name(entry.name)
            require(entry.isreg() and not entry.pax_headers and name not in seen,
                    'nonregular or duplicate archive entry')
            require(entry.mode == (0o755 if name == 'obj/VHostBlockTop' else 0o644),
                    'unexpected archive permissions')
            seen.add(name)
            if manifest is None:
                require(name == MANIFEST and 0 < entry.size <= 128 * 1024, 'manifest must be first and bounded')
                manifest = json.load(archive.extractfile(entry), object_pairs_hook=unique_object)
                files = validate_manifest(manifest, commit, profile=profile)
            else:
                require(name in files and entry.size == files[name]['bytes'], 'extra file or size mismatch')
                value = hashlib.sha256()
                stream = archive.extractfile(entry)
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    value.update(chunk)
                require(value.hexdigest() == files[name]['sha256'], 'archive file digest mismatch')
    require(manifest is not None and seen == FILES | {MANIFEST}, 'incomplete archive')
    return manifest


def unpack(path, digest, commit, output, *, profile='dense-conv'):
    require(not output.exists() and not output.is_symlink(), 'refuse evidence overwrite')
    manifest = validate_archive(path, digest, commit, profile=profile)
    verify_checkout(commit, manifest['sources'])
    # Validate the complete archive before writing files or loading its ELF.
    output.mkdir(parents=True)
    with gzip.open(path, 'rb') as raw, tarfile.open(fileobj=BoundedReader(raw), mode='r|', ignore_zeros=True) as archive:
        for entry in archive:
            destination = output / safe_name(entry.name)
            require(entry.name in FILES | {MANIFEST} and entry.isreg(), 'archive changed before extraction')
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open('xb') as stream:
                shutil.copyfileobj(archive.extractfile(entry), stream)
            destination.chmod(0o755 if entry.name == 'obj/VHostBlockTop' else 0o644)
    require(sha(path) == digest and read_json(output / MANIFEST) == manifest, 'archive changed during extraction')
    require(all(describe(output / name) == record for name, record in manifest['files'].items()),
            'extracted file identity mismatch')
    return manifest


def write_compact(out, summary, hashes):
    compact = out / 'compact'
    require(not compact.is_symlink(), 'compact root symlink')
    compact.mkdir(exist_ok=True)
    require(all(p.is_file() and not p.is_symlink() and p.name in COMPACT_FILES for p in compact.iterdir()),
            'non-allowlisted compact content')
    save(compact / 'summary.json', summary)
    save(compact / 'source_input_hashes.json', hashes)


def core_reference_summary(report):
    expected = dict(status='SOURCE_AUTHENTICATED_HOST_GDN_CORE_TWO_TOKEN_FIXTURE',
                    scope=CORE_FIXTURE_SCOPE, token_ids=[19, 92], tokens_per_launch=1,
                    launches=2, commands_per_launch=8, heads=16, head_width=128,
                    reference_head_jobs=66, reference_padded_fma_steps=17301504,
                    actual_useful_dense_macs=16842752,
                    canonical_acceptance='EXACT_BITS_EVERY_STAGE_AND_BOTH_STATES',
                    native_operator_gate_pass=True,
                    native_core_gate_pass=None, native_full_block_gate_pass=None,
                    native_full_block_status='NOT_ESTABLISHED_BY_CORE_FIXTURE',
                    full_block_supported=False, input_norm_dut=False, o_projection_dut=False,
                    residual_dut=False, ffn_dut=False, rtl_executed=False, generations=[0, 1, 2])
    require(all(key in report and type(report[key]) is type(value) and report[key] == value
                for key, value in expected.items()), 'bounded fresh core source contract changed')
    return {key: report[key] for key in (*expected, 'input_boundary', 'official_stage_acceptance',
                                        'frozen_operator_metrics',
                                        'reference_elapsed_seconds', 'max_rss_kib', 'tools')}


def validate_core_result(result, ready):
    expected = dict(status='PASS_PRODUCTION_HOST_GDN_CORE_CANONICAL', scope=CORE_SCOPE,
                    actual_dut_identity_verified=True, source_immutability_verified=True,
                    canonical_core_pass=True, actual_useful_dense_macs=16842752,
                    actual_ack_history_state_carry=True, native_operator_gate_pass=True, native_core_gate_pass=None,
                    native_full_block_gate_pass=None, full_block_supported=False,
                    fault_restore_supported=False, input_norm_dut=False, o_projection_dut=False,
                    residual_dut=False, ffn_dut=False,
                    binary_sha256=ready['binary_sha256'], rtl_sha256=ready['rtl_sha256'])
    require(all(key in result and type(result[key]) is type(value) and result[key] == value
                for key, value in expected.items()), 'incomplete/mismatched production core execution result')
    require(type(result.get('runs')) is list and len(result['runs']) == 2,
            'both cold and carried core launches required')
    for token, row in enumerate(result['runs']):
        require(row['token'] == token and row['committed_generation'] == token + 1
                and row['canonical_bit_mismatches'] == 0 and len(row['commands']) == 8,
                'incomplete core launch or persistent generation')


def run(args):
    profile = getattr(args, 'profile', 'dense-conv')
    contract = profile_contract(profile)
    core = profile == 'core'
    out = fresh_output(args.output)
    started = time.monotonic()
    summary = dict(status='PENDING_PRODUCTION_HOST_GDN_CORE' if core else 'PENDING_PRODUCTION_HOST_GDN',
                   stage='preflight', build_profile=profile,
                   scope=contract['scope'], numerical_acceptance=False, actual_dut_identity_verified=False,
                   full_block_supported=False, input_norm_dut=False, recurrent_state_supported=core,
                   gated_norm_supported=core, cross_host_byte_equivalence_claimed=False,
                   mode=getattr(args, 'mode', None), source_commit=None,
                   artifact_upload_allowlist=['compact/' + name for name in sorted(COMPACT_FILES)])
    if core:
        summary.update(numerical_acceptance_scope='canonical_gdn_core_only', canonical_core_pass=False,
                       native_operator_gate_pass=None,
                       native_core_gate_pass=None, native_full_block_gate_pass=None,
                       o_projection_dut=False, residual_dut=False, ffn_dut=False,
                       fault_restore_supported=False, pending_gates=list(CORE_PENDING_GATES))
    hashes = dict(source_sha256={}, input_sha256={}, output_sha256={})

    def checkpoint(stage):
        summary.update(stage=stage, elapsed_seconds=time.monotonic() - started)
        write_compact(out, summary, hashes)

    def interrupted(signum, _frame):
        raise InterruptedError('runner received signal ' + str(signum))

    old_handlers = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        checkpoint('preflight')
        commit = git_commit(ROOT) if args.command == 'build' else args.expected_commit
        summary['source_commit'] = commit
        hashes['source_sha256'] = source_closure(profile=profile)
        verify_checkout(commit, hashes['source_sha256'])
        build = out / 'host_build'
        if args.command == 'build':
            env = os.environ.copy()
            env.setdefault('BUILD_JOBS', '1')
            require(env['BUILD_JOBS'] == '1', 'serial production build required')
            checkpoint('production_host_build_only')
            with (out / 'build.log').open('x') as log:
                subprocess.run(['bash', str(ROOT / 'chisel/continuous_prefill/scripts/run_host_bf16_gdn_gate.sh'),
                                str(build), '0', profile], cwd=ROOT, env=env, stdout=log,
                               stderr=subprocess.STDOUT, check=True, timeout=6300)
            checkpoint('seal_build_only_package')
            digest, manifest = package(build, out / 'host_gdn_build.tar.gz', commit, profile=profile)
            hashes['source_sha256'] = manifest['sources']
            hashes.update(package_sha256=digest, binary_sha256=manifest['binary_sha256'],
                          rtl_sha256=manifest['rtl_sha256'], build_log_sha256=sha(out / 'build.log'))
            summary.update(status=contract['build_status'], package_sha256=digest, numerical_acceptance=False)
            if args.github_output:
                with args.github_output.open('a') as stream:
                    stream.write('package_sha256=' + digest + '\nsource_commit=' + commit + '\n')
        else:
            require(args.mode in contract['modes'], 'unsupported case for selected GDN profile')
            require(type(args.timeout_seconds) is int and 0 < args.timeout_seconds <= contract['timeout_limit'],
                    'case budget must be 1..' + str(contract['timeout_limit']) + ' seconds')
            require(os.environ.get('HF_HUB_OFFLINE') == '1', 'case must use reacquired fixed local payloads offline')
            checkpoint('verify_build_transfer')
            manifest = unpack(args.archive, args.expected_sha256, commit, build, profile=profile)
            ready, sources, _ = build_admission(build, commit, profile=profile)
            require(sources == manifest['sources'], 'source closure differs from build job')
            hashes['source_sha256'] = sources
            hashes.update(package_sha256=args.expected_sha256, binary_sha256=ready['binary_sha256'],
                          rtl_sha256=ready['rtl_sha256'], build_ready_sha256=sha(build / 'build_ready.json'))
            summary['runtime'] = runtime_identity(build / 'obj/VHostBlockTop')
            checkpoint('fresh_official_two_token_reference')
            fixture = out / 'fresh_fixture'
            with (out / 'reference.log').open('x') as log, contextlib.redirect_stdout(log):
                if core:
                    from pack_host_bf16_gdn_core_fixture import generate_fixture as generate_core_fixture
                    session = generate_core_fixture(fixture)
                else:
                    session = generate_fixture(fixture)
                fixture_report = session.verify(fixture)
                if not core:
                    authority = authenticate_fixture(fixture, session=session)
            if core:
                summary['fresh_reference'] = core_reference_summary(fixture_report)
            else:
                require(fixture_report['token_ids'] == [19, 92] and fixture_report['head_jobs'] == 48
                        and fixture_report['matrix_accumulator_steps'] == 12582912
                        and fixture_report['native_gate_pass'] is True, 'bounded fresh source contract changed')
                summary['fresh_reference'] = {key: fixture_report[key] for key in (
                    'token_ids', 'head_jobs', 'matrix_accumulator_steps', 'input_boundary', 'native_gate_pass',
                    'native_full_block_status', 'reference_elapsed_seconds', 'max_rss_kib', 'tools')}
            hashes['input_sha256'] = {name: row['sha256'] for name, row in fixture_report['files'].items()}
            hashes['source_payload_manifest_sha256'] = fixture_report['source_payload_manifest_sha256']
            hashes['fixture_manifest_sha256'] = sha(fixture / 'manifest.json')
            verify_checkout(commit, sources)
            checkpoint('actual_host_core_cold_carried' if core else 'actual_host_' + args.mode)
            if core:
                from host_bf16_gdn_core_execution import run_case as run_core_case
                result = run_core_case(build, fixture, session=session, source_root=ROOT,
                                       timeout_seconds=args.timeout_seconds)
                validate_core_result(result, ready)
                require(result['frozen_operator_metrics'] == fixture_report['frozen_operator_metrics'],
                        'fixed Dense/Conv operator acceptance differs from live reference')
                session.verify(fixture)
                hashes['output_sha256'] = {str(row['token']): row['ddr_after_sha256'] for row in result['runs']}
            else:
                result = run_case(build, fixture, args.mode, authority=authority, source_root=ROOT,
                                  timeout_seconds=args.timeout_seconds)
                require(result['status'] == 'PASS_PRODUCTION_HOST_GDN_CASE'
                        and result['actual_dut_identity_verified'] is True
                        and result['numerical_acceptance_eligible'] is True
                        and result['source_immutability_verified'] is True
                        and result['binary_sha256'] == ready['binary_sha256']
                        and result['rtl_sha256'] == ready['rtl_sha256']
                        and result['mode'] == args.mode, 'incomplete/mismatched production execution result')
                authority.verify(fixture)
                hashes['output_sha256'] = {str(row['run']): row['actual_sha256'] for row in result['runs']}
                summary['source_admission'] = result['source_admission']
            build_admission(build, commit, profile=profile)
            hashes['actual_log_sha256'] = result['log_sha256']
            summary.update(status=result['status'], actual_dut_identity_verified=True,
                           numerical_acceptance=args.mode in ('pass', 'reset-recovery'),
                           case_verified=True, runs=result['runs'])
            if core:
                summary.update(canonical_core_pass=True, native_operator_gate_pass=True,
                               frozen_operator_metrics=result['frozen_operator_metrics'],
                               actual_useful_dense_macs=result['actual_useful_dense_macs'],
                               actual_ack_history_state_carry=True)
        checkpoint('complete')
        return summary, 0
    except (subprocess.TimeoutExpired, InterruptedError, KeyboardInterrupt) as error:
        summary.update(status='PENDING_INCOMPLETE_PRODUCTION_HOST_GDN_CORE' if core else 'PENDING_INCOMPLETE_PRODUCTION_HOST_GDN',
                       numerical_acceptance=False,
                       error=dict(type=type(error).__name__, message=str(error)))
    except Exception as error:
        summary.update(status='FAIL_PRODUCTION_HOST_GDN_CORE_GATE' if core else 'FAIL_PRODUCTION_HOST_GDN_GATE',
                       numerical_acceptance=False,
                       error=dict(type=type(error).__name__, message=str(error)))
    finally:
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)
        if summary['stage'] != 'complete':
            if core:
                summary['canonical_core_pass'] = False
                summary['native_operator_gate_pass'] = None
            names = ['build.log', 'reference.log']
            if core:
                names.append('host_build/core_cold_carried.log')
            elif summary['mode'] in CI_MODES:
                names.append('host_build/' + summary['mode'] + '.log')
            # Bounded compiler/driver text only. Never inspect or upload tensors.
            summary['diagnostic_log_tail'] = {name: tail(out / name) for name in names
                                              if (out / name).is_file()}
            hashes['diagnostic_log_sha256'] = {name: sha(out / name) for name in names
                                               if (out / name).is_file()}
        summary['elapsed_seconds'] = time.monotonic() - started
        write_compact(out, summary, hashes)
    return summary, 1


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest='command', required=True)
    build = commands.add_parser('build')
    build.add_argument('--profile', choices=PROFILES, default='dense-conv')
    build.add_argument('--output', type=Path, required=True)
    build.add_argument('--github-output', type=Path)
    case = commands.add_parser('run')
    case.add_argument('--profile', choices=PROFILES, default='dense-conv')
    case.add_argument('--output', type=Path, required=True)
    case.add_argument('--archive', type=Path, required=True)
    case.add_argument('--expected-sha256', required=True)
    case.add_argument('--expected-commit', required=True)
    case.add_argument('--mode', choices=CI_MODES, required=True)
    case.add_argument('--timeout-seconds', type=int, default=5400)
    return p


if __name__ == '__main__':
    report, code = run(parser().parse_args())
    print(json.dumps(report, indent=2))
    sys.exit(code)
