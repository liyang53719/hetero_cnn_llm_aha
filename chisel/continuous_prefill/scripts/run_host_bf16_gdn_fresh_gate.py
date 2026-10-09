#!/usr/bin/env python3
"""CI entry for fresh production Host Dense0/Conv0/Dense1/Conv1 and faults.

The build job transfers only its simulator, RTL and identity receipts. Each
case job regenerates the bounded official two-token input and independent
48-head reference in-process. No persisted fixture is an acceptance input.
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


def fresh_output(path):
    path = Path(path)
    require(not path.is_symlink(), 'output root symlink')
    path = path.resolve()
    require(path.is_relative_to(ROOT / 'work') and path != ROOT / 'work'
            and not path.exists(), 'new output under ignored work required')
    path.mkdir(parents=True)
    return path


def source_closure(build=None):
    sources = _sources()
    sources.update({name: sha(ROOT / name) for name in ENTRY_SOURCES})
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


def build_admission(build, commit):
    identity = _build_identity(build)
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
    expected = dict(experimental_bf16_gdn=True, default_enabled=False, scope=SCOPE,
                    policy_version=1, hidden=1024, gdn_channels=6144, conv_kernel=4,
                    scalar_service_shared=True, recurrent_state_supported=False,
                    gated_norm_supported=False, full_block_supported=False, burst_writes=False,
                    logical_matrix_engines=1, physical_matrix_slices=8, pinned_idma_instances=1)
    require(all(type(scope.get(k)) is type(v) and scope[k] == v for k, v in expected.items()),
            'wrong GDN Dense/Conv-only build profile')
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
    sources = source_closure(build)
    verify_checkout(commit, sources)
    verify_all_build_sources(build, source_root=ROOT)
    return ready, sources, identity


def package(build, output, commit):
    ready, sources, _ = build_admission(build, commit)
    files = {name: describe(build / name) for name in sorted(FILES)}
    manifest = dict(schema=1, status=BUILD_STATUS, numerical_pass=False,
                    source_commit=commit, sources=sources, files=files,
                    binary_sha256=ready['binary_sha256'], rtl_sha256=ready['rtl_sha256'])
    validate_manifest(manifest, commit)
    with output.open('xb') as raw, gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as zipped, \
            tarfile.open(fileobj=zipped, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        for name in [MANIFEST] + sorted(FILES):
            data = encoded(manifest) if name == MANIFEST else (build / name).read_bytes()
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            entry.mode = 0o755 if name == 'obj/VHostBlockTop' else 0o644
            archive.addfile(entry, io.BytesIO(data))
    digest = sha(output)
    validate_archive(output, digest, commit)
    return digest, manifest


def validate_manifest(manifest, commit):
    require(re.fullmatch('[0-9a-f]{40}', commit) and manifest.get('schema') == 1
            and manifest.get('source_commit') == commit, 'package commit/schema mismatch')
    require(manifest.get('status') == BUILD_STATUS and manifest.get('numerical_pass') is False,
            'package must carry build-only status')
    files = manifest['files']
    require(type(files) is dict and set(files) == FILES, 'package file allowlist mismatch')
    for name, row in files.items():
        safe_name(name)
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


def validate_archive(path, digest, commit):
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
                files = validate_manifest(manifest, commit)
            else:
                require(name in files and entry.size == files[name]['bytes'], 'extra file or size mismatch')
                value = hashlib.sha256()
                stream = archive.extractfile(entry)
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    value.update(chunk)
                require(value.hexdigest() == files[name]['sha256'], 'archive file digest mismatch')
    require(manifest is not None and seen == FILES | {MANIFEST}, 'incomplete archive')
    return manifest


def unpack(path, digest, commit, output):
    require(not output.exists() and not output.is_symlink(), 'refuse evidence overwrite')
    manifest = validate_archive(path, digest, commit)
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


def run(args):
    out = fresh_output(args.output)
    started = time.monotonic()
    summary = dict(status='PENDING_PRODUCTION_HOST_GDN', stage='preflight',
                   scope=SCOPE, numerical_acceptance=False, actual_dut_identity_verified=False,
                   full_block_supported=False, input_norm_dut=False, recurrent_state_supported=False,
                   gated_norm_supported=False, cross_host_byte_equivalence_claimed=False,
                   mode=getattr(args, 'mode', None), source_commit=None,
                   artifact_upload_allowlist=['compact/' + name for name in sorted(COMPACT_FILES)])
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
        hashes['source_sha256'] = source_closure()
        verify_checkout(commit, hashes['source_sha256'])
        build = out / 'host_build'
        if args.command == 'build':
            env = os.environ.copy()
            env.setdefault('BUILD_JOBS', '1')
            require(env['BUILD_JOBS'] == '1', 'serial production build required')
            checkpoint('production_host_build_only')
            with (out / 'build.log').open('x') as log:
                subprocess.run(['bash', str(ROOT / 'chisel/continuous_prefill/scripts/run_host_bf16_gdn_gate.sh'),
                                str(build), '0'], cwd=ROOT, env=env, stdout=log,
                               stderr=subprocess.STDOUT, check=True, timeout=6300)
            checkpoint('seal_build_only_package')
            digest, manifest = package(build, out / 'host_gdn_build.tar.gz', commit)
            hashes['source_sha256'] = manifest['sources']
            hashes.update(package_sha256=digest, binary_sha256=manifest['binary_sha256'],
                          rtl_sha256=manifest['rtl_sha256'], build_log_sha256=sha(out / 'build.log'))
            summary.update(status=BUILD_STATUS, package_sha256=digest, numerical_acceptance=False)
            if args.github_output:
                with args.github_output.open('a') as stream:
                    stream.write('package_sha256=' + digest + '\nsource_commit=' + commit + '\n')
        else:
            require(type(args.timeout_seconds) is int and 0 < args.timeout_seconds <= 5400,
                    'case budget must be 1..5400 seconds')
            require(os.environ.get('HF_HUB_OFFLINE') == '1', 'case must use reacquired fixed local payloads offline')
            checkpoint('verify_build_transfer')
            manifest = unpack(args.archive, args.expected_sha256, commit, build)
            ready, sources, _ = build_admission(build, commit)
            require(sources == manifest['sources'], 'source closure differs from build job')
            hashes['source_sha256'] = sources
            hashes.update(package_sha256=args.expected_sha256, binary_sha256=ready['binary_sha256'],
                          rtl_sha256=ready['rtl_sha256'], build_ready_sha256=sha(build / 'build_ready.json'))
            summary['runtime'] = runtime_identity(build / 'obj/VHostBlockTop')
            checkpoint('fresh_official_two_token_reference')
            fixture = out / 'fresh_fixture'
            with (out / 'reference.log').open('x') as log, contextlib.redirect_stdout(log):
                session = generate_fixture(fixture)
                fixture_report = session.verify(fixture)
                authority = authenticate_fixture(fixture, session=session)
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
            checkpoint('actual_host_' + args.mode)
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
            build_admission(build, commit)
            hashes['output_sha256'] = {str(row['run']): row['actual_sha256'] for row in result['runs']}
            hashes['actual_log_sha256'] = result['log_sha256']
            summary.update(status=result['status'], actual_dut_identity_verified=True,
                           numerical_acceptance=args.mode in ('pass', 'reset-recovery'),
                           case_verified=True, runs=result['runs'], source_admission=result['source_admission'])
        checkpoint('complete')
        return summary, 0
    except (subprocess.TimeoutExpired, InterruptedError, KeyboardInterrupt) as error:
        summary.update(status='PENDING_INCOMPLETE_PRODUCTION_HOST_GDN', numerical_acceptance=False,
                       error=dict(type=type(error).__name__, message=str(error)))
    except Exception as error:
        summary.update(status='FAIL_PRODUCTION_HOST_GDN_GATE', numerical_acceptance=False,
                       error=dict(type=type(error).__name__, message=str(error)))
    finally:
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)
        if summary['stage'] != 'complete':
            names = ['build.log', 'reference.log']
            if summary['mode'] in CI_MODES:
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
    build.add_argument('--output', type=Path, required=True)
    build.add_argument('--github-output', type=Path)
    case = commands.add_parser('run')
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
