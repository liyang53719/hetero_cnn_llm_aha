#!/usr/bin/env python3
"""Transfer a build, then run the original continuous real16 two-layer gate.

Packages contain a standalone simulator, generated RTL, synthetic fixture and
identity receipts only. They never contain a numerical pass, a checkpoint,
model weights, compiler objects/libraries, or actual/reference tensor dumps.
Historical packaging inspections are explicitly ineligible for execution.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timezone

from verify_real_two_layer import fixed_contract

SCHEMA = 1
BUILT = 'BUILT_NOT_NUMERICAL_PASS'
PASS = 'PASS_REAL16_TWO_LAYER_HOST_NUMERICAL'
IDMA_PIN = '2e0b0fe53b6f8823319e2428e2e9abc2db149b7d'
HF_PIN = 'c1105e6ac6a0dd90fc80893efc4830ab609005d3'
SCRIPT = 'chisel/continuous_prefill/scripts/real2_ci.py'
MANIFEST = 'package_manifest.json'
BASE_FILES = {
    'obj/VHostBlockTop', 'generated/HostBlockTop.sv',
    'generated/owner_shape.h', 'generated/SCOPE.json',
    'sources.sha256.json', 'hardfloat.sha256.json', 'source_scope.json',
    'source_base_commit.txt', 'idma_identity.json',
}
FIXTURE_FILES = {'host_commands.bin', 'host_descriptors.bin', 'manifest.json', 'owner_fixture.h'}
BASE_FILES |= {'fixture/' + n for n in FIXTURE_FILES}
BASE_FILES |= {'fixture/single_layer_template/' + n for n in FIXTURE_FILES}
RECEIPT_FILES = {'build_receipt.json', 'idma_sources.sha256.json', 'idma_commits.json'}
OPTIONAL_FILES = {'compiler_jars.sha256.json'}
ALLOWED_FILES = BASE_FILES | RECEIPT_FILES | OPTIONAL_FILES
MAX_BYTES = 120 * 1024 * 1024


class BoundedReader:
    """Bound decompressed bytes including tar padding and concatenated members."""
    def __init__(self, stream):
        self.stream = stream
        self.bytes = 0

    def read(self, size):
        data = self.stream.read(min(size, MAX_BYTES + 1024 * 1024 + 1 - self.bytes))
        self.bytes += len(data)
        require(self.bytes <= MAX_BYTES + 1024 * 1024, 'decompressed archive exceeds size bound')
        return data


def require(ok, message):
    if not ok:
        raise ValueError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(data)
    return h.hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


def save(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_bytes(encoded(value))
    temporary.replace(path)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def read_json(path):
    return json.loads(Path(path).read_text(), object_pairs_hook=unique_object)


def safe_name(name):
    require(isinstance(name, str) and name and '\\' not in name, 'unsafe path')
    p = PurePosixPath(name)
    require(not p.is_absolute() and '..' not in p.parts and str(p) == name, 'unsafe path: ' + name)
    return name


def hash_map(value):
    require(isinstance(value, dict) and value, 'empty source map')
    for name, digest in value.items():
        safe_name(name)
        require(isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest), 'invalid source digest')
    return value


def run_text(command):
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
    require(result.returncode == 0, 'command failed: ' + ' '.join(map(str, command)) + ': ' + result.stdout[-2000:])
    return result.stdout.strip()


def git_commit(repo):
    commit = run_text(['git', '-C', str(repo), 'rev-parse', 'HEAD'])
    require(re.fullmatch('[0-9a-f]{40}', commit), 'invalid commit')
    return commit


def clean_commit(repo, expected):
    require(git_commit(repo) == expected, 'checkout commit does not match trusted build commit')
    run_text(['git', '-C', str(repo), 'diff', '--exit-code', 'HEAD', '--'])
    # An untracked helper must not masquerade as part of the pinned commit.
    original = subprocess.check_output(['git', '-C', str(repo), 'show', expected + ':' + SCRIPT])
    require(hashlib.sha256(original).hexdigest() == sha(repo / SCRIPT), 'packaging helper is not committed')


def validate_maps(repo, build, hf):
    for base, name in [(repo, 'sources.sha256.json'), (hf, 'hardfloat.sha256.json')]:
        hashes = hash_map(read_json(build / name))
        for relative, digest in hashes.items():
            path = (base / relative).resolve()
            require(path.is_relative_to(base.resolve()) and path.is_file(), 'missing source: ' + relative)
            require(sha(path) == digest, 'source changed: ' + relative)
    require(git_commit(hf) == HF_PIN, 'HardFloat pin drift')
    run_text(['git', '-C', str(hf), 'diff', '--exit-code', 'HEAD', '--'])


def runtime_identity(binary):
    # This binary was produced by this workflow; never call ldd before the
    # archive and its trusted build-job digest have been checked.
    linked = run_text(['ldd', str(binary)])
    require('not found' not in linked, 'missing simulator runtime library')
    libraries = {}
    for line in linked.splitlines():
        match = re.search(r'(?:=>\s*)?(/[^\s]+)', line)
        if match:
            path = Path(match[1]).resolve()
            libraries[path.name] = {'sha256': sha(path), 'path': str(path)}
    release = Path('/etc/os-release')
    return {'machine': platform.machine(), 'platform': platform.platform(),
            'python': sys.version, 'libc': list(platform.libc_ver()),
            'os_release': release.read_text() if release.is_file() else None,
            'dynamic_libraries': libraries, 'ldd': linked}


def verilator_backend_identity(launcher, root):
    entry = next((p for p in [root / 'verilator_bin', root / 'bin/verilator_bin'] if p.is_file()), None)
    require(entry is not None, 'missing Verilator backend entrypoint')
    entry = entry.resolve()
    with entry.open('rb') as stream:
        header = stream.read(4)
    backend = entry
    kind = 'ELF'
    if header != b'\x7fELF':
        # The pinned Debian package puts a Perl forwarding script below
        # usr/share/verilator/bin. Hashing it alone omits the actual compiler.
        wrapper = entry.read_text()
        require('my $relpath = "../../../bin";' in wrapper
                and 'exec { "$RealBin/$relpath/$RealScript" } @ARGV;' in wrapper,
                'unrecognized Verilator backend wrapper')
        backend = (entry.parent / '../../../bin' / entry.name).resolve()
        require(backend == (Path(launcher).resolve().parent / 'verilator_bin').resolve(),
                'Verilator wrapper does not resolve to launcher-adjacent backend')
        kind = 'DEBIAN_PERL_FORWARDER'
    require(backend.is_file(), 'missing actual Verilator ELF backend')
    with backend.open('rb') as stream:
        require(stream.read(4) == b'\x7fELF', 'Verilator backend is not an ELF executable')
    def identity(path):
        return {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size,
                'version': run_text([str(path), '--version'])}
    entry_identity = identity(entry)
    entry_identity['kind'] = kind
    actual_identity = identity(backend)
    actual_identity['kind'] = 'ELF'
    require(entry_identity['version'] == actual_identity['version'], 'Verilator wrapper/backend version mismatch')
    return entry_identity, actual_identity


def tool_identity():
    result = {}
    for name, args in [('java', ['-version']), ('g++', ['--version']),
                       ('verilator', ['--version']), ('python3', ['--version']), ('make', ['--version'])]:
        executable = shutil.which(name)
        require(executable, 'missing build tool: ' + name)
        result[name] = {'path': str(Path(executable).resolve()), 'sha256': sha(executable),
                        'version': run_text([executable] + args)}
    firtool = Path(os.environ.get('CHISEL_FIRTOOL_PATH', '')) / 'firtool'
    if firtool.is_file():
        result['firtool'] = {'path': str(firtool.resolve()), 'sha256': sha(firtool),
                             'version': run_text([str(firtool), '--version'])}
    root = Path(os.environ.get('VERILATOR_ROOT', ''))
    entry, backend = verilator_backend_identity(result['verilator']['path'], root)
    require(backend['version'] == result['verilator']['version'], 'Verilator launcher/backend version mismatch')
    result['verilator_backend_entrypoint'] = entry
    result['verilator_backend'] = backend
    if shutil.which('sbt'):
        launcher = Path(shutil.which('sbt')).resolve()
        result['sbt_launcher'] = {'path': str(launcher), 'sha256': sha(launcher)}
    return result


def describe(path):
    require(path.is_file() and not path.is_symlink(), 'missing or symlink payload: ' + str(path))
    return {'sha256': sha(path), 'bytes': path.stat().st_size}


def original_payload(build):
    # Single-layer build-only callers have no multilayer template. The package
    # command separately requires the complete fixed two-layer file set.
    files = {n for n in BASE_FILES if not n.startswith('fixture/single_layer_template/') or (build / n).exists()}
    files |= {n for n in OPTIONAL_FILES if (build / n).exists()}
    return {n: describe(build / n) for n in sorted(files)}


def verify_idma_receipts(identity, sources_bytes, commits_bytes):
    sources = hash_map(json.loads(sources_bytes, object_pairs_hook=unique_object))
    commits = json.loads(commits_bytes, object_pairs_hook=unique_object)
    require(commits.get('idma') == IDMA_PIN and identity['commits'] == commits, 'iDMA pin/commit map drift')
    require(identity['files_verified'] == len(sources), 'iDMA source count drift')
    require(identity['export_manifest_sha256'] == hashlib.sha256(sources_bytes).hexdigest(), 'iDMA source map digest drift')


def seal_build(repo, build, hf, idma):
    require(not (build / 'build_receipt.json').exists(), 'refuse build receipt overwrite')
    require(not (build / 'simulation.exit').exists() and not (build / 'gate.exit').exists(), 'build-only output contains run evidence')
    validate_maps(repo, build, hf)
    # Recheck the same pinned export before sealing; retain its relative map,
    # not the export or absolute-path compilation filelist.
    from prepare_idma_export import verify as verify_idma
    verify_idma(idma, build)
    for source, destination in [('SHA256SUMS.json', 'idma_sources.sha256.json'), ('COMMITS.json', 'idma_commits.json')]:
        (build / destination).write_bytes((idma / source).read_bytes())
    verify_idma_receipts(read_json(build / 'idma_identity.json'),
                         (build / 'idma_sources.sha256.json').read_bytes(), (build / 'idma_commits.json').read_bytes())
    if not (build / 'compiler_jars.sha256.json').exists():
        # run_host_block_gate isolates Coursier for the build-only SBT path.
        # Record all resolved cache jars, without including any in the package.
        cache = build / 'maven'
        jars = sorted(cache.rglob('*.jar'))
        require(jars, 'missing resolved compiler dependency identity')
        save(build / 'compiler_jars.sha256.json', {str(p.relative_to(cache)): sha(p) for p in jars})
    hash_map(read_json(build / 'compiler_jars.sha256.json'))
    payload = original_payload(build)
    receipt = {'schema': SCHEMA, 'status': BUILT, 'created_at': now(),
               'source_commit': (build / 'source_base_commit.txt').read_text().strip(),
               'payload': payload, 'helper_sha256': sha(repo / SCRIPT),
               'hardfloat_commit': git_commit(hf), 'tools': tool_identity(),
               'build_definition_sha256': {n: sha(repo / n) for n in ['chisel/continuous_prefill/build.sbt', 'chisel/continuous_prefill/project/build.properties']},
               'runtime': runtime_identity(build / 'obj/VHostBlockTop'),
               'idma_sources_verified_at_build': True,
               'idma_sources_sha256': sha(build / 'idma_sources.sha256.json')}
    save(build / 'build_receipt.json', receipt)
    return receipt


def real2_contract(build):
    m = read_json(build / 'fixture/manifest.json')
    fixed_contract(m)
    require(m['base'] == 0x100000000 + 9467985920, 'wrong relocation')
    require(m.get('weight_storage') == 'bf16', 'native BF16 weights required')
    for name in ('host_commands.bin', 'host_descriptors.bin'):
        require(sha(build / 'fixture' / name) == m['table_sha256'][name], 'fixture table digest mismatch')
    scope = read_json(build / 'generated/SCOPE.json')
    expected = dict(matrix_macs=4096, weight_read_burst_beats=16, pipelined=True,
                    burst_writes=False, commit_tail_read=False, overlap_silu=False,
                    host_commands=True, block_launch=False, retained_matrix=True,
                    pinned_idma=True, physical_matrix_slices=8, hidden=1536, ffn=8960)
    require(all(type(scope.get(k)) is type(v) and scope[k] == v for k, v in expected.items()), 'wrong real2 elaboration conditions')


def package(repo, build, output, hf, idma, inspection=False):
    require(not output.exists(), 'refuse package overwrite')
    real2_contract(build)
    commit = (build / 'source_base_commit.txt').read_text().strip()
    require(re.fullmatch('[0-9a-f]{40}', commit), 'invalid original build commit')
    payload = original_payload(build)
    blobs = {}
    if inspection:
        # Preserve the old source map verbatim. Current helper hashes are
        # separate metadata and never rebind an old build or numerical pass.
        require(idma is not None, 'inspection needs original pinned iDMA export')
        blobs['idma_sources.sha256.json'] = (idma / 'SHA256SUMS.json').read_bytes()
        blobs['idma_commits.json'] = (idma / 'COMMITS.json').read_bytes()
        receipt = {'schema': SCHEMA, 'status': 'HISTORICAL_BUILD_PACKAGE_INSPECTION_ONLY',
                   'source_commit': commit, 'original_source_receipt_sha256': sha(build / 'sources.sha256.json'),
                   'current_helper_sha256': sha(repo / SCRIPT), 'payload': payload,
                   'original_build_sealed': False, 'numerical_validation_performed': False}
        blobs['build_receipt.json'] = encoded(receipt)
    else:
        require(hf is not None, 'packaging requires pinned HardFloat source')
        require((build / 'build.exit').read_text().strip() == '0', 'build did not exit successfully')
        require(not (build / 'simulation.exit').exists() and not (build / 'gate.exit').exists(), 'package input must be build-only')
        clean_commit(repo, commit)
        validate_maps(repo, build, hf)
        receipt = read_json(build / 'build_receipt.json')
        require(receipt['status'] == BUILT and receipt['source_commit'] == commit, 'unsealed build')
        require(receipt['payload'] == payload and receipt['helper_sha256'] == sha(repo / SCRIPT), 'build payload/helper changed after sealing')
        require(receipt['idma_sources_verified_at_build'] is True, 'iDMA sources were not checked')
        require(receipt['idma_sources_sha256'] == sha(build / 'idma_sources.sha256.json'), 'iDMA map changed')
        blobs = {n: (build / n).read_bytes() for n in RECEIPT_FILES}
    verify_idma_receipts(read_json(build / 'idma_identity.json'), blobs['idma_sources.sha256.json'], blobs['idma_commits.json'])
    for name, data in blobs.items():
        payload[name] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
    require(sum(row['bytes'] for row in payload.values()) <= MAX_BYTES, 'package exceeds size bound')
    manifest = {'schema': SCHEMA, 'status': BUILT if not inspection else 'INSPECTION_ONLY_NOT_NUMERICAL_PASS',
                'source_commit': commit, 'execution_eligible': not inspection, 'files': payload,
                'packager_source_sha256': sha(repo / SCRIPT), 'continuous_processes': 1,
                'expected_commands': 42, 'expected_descriptors': 430, 'expected_fp32': 1409024}
    output.parent.mkdir(parents=True, exist_ok=True)
    # Explicit files only: no symlinks, directory entries, timestamps or compiler
    # trees. Generated RTL is necessary for the unchanged topology oracle.
    with output.open('xb') as stream, gzip.GzipFile(filename='', mode='wb', fileobj=stream, mtime=0) as zipped, tarfile.open(fileobj=zipped, mode='w', format=tarfile.USTAR_FORMAT) as tar:
        entries = {MANIFEST: encoded(manifest), **blobs}
        for name in [MANIFEST] + sorted(payload):
            if name in entries:
                data = entries[name]
                info = tarfile.TarInfo(name); info.size = len(data)
                info.mode = 0o755 if name == 'obj/VHostBlockTop' else 0o644
                tar.addfile(info, io.BytesIO(data))
            else:
                path = build / name
                info = tarfile.TarInfo(name); info.size = path.stat().st_size
                info.mode = 0o755 if name == 'obj/VHostBlockTop' else 0o644
                with path.open('rb') as data:
                    tar.addfile(info, data)
    result = {'status': manifest['status'], 'package_sha256': sha(output), 'source_commit': commit,
              'compressed_bytes': output.stat().st_size, 'payload_bytes': sum(row['bytes'] for row in payload.values())}
    # Validate our archive completely, catching mutation during packaging too.
    validate_archive(output, result['package_sha256'], commit, inspection)
    return result


def validate_manifest(manifest, expected_commit, inspection):
    require(manifest.get('schema') == SCHEMA and manifest.get('source_commit') == expected_commit, 'package commit/schema mismatch')
    require(re.fullmatch('[0-9a-f]{40}', expected_commit), 'invalid expected commit')
    require(manifest.get('execution_eligible') is True or inspection, 'inspection packages cannot execute')
    require(manifest['status'] == (BUILT if manifest.get('execution_eligible') is True else 'INSPECTION_ONLY_NOT_NUMERICAL_PASS'), 'invalid package status')
    files = manifest['files']
    require(isinstance(files, dict) and BASE_FILES | RECEIPT_FILES <= set(files) <= ALLOWED_FILES, 'unexpected or missing package files')
    require(sum(row['bytes'] for row in files.values()) <= MAX_BYTES, 'oversized package')
    for name, row in files.items():
        safe_name(name)
        limit = 96 * 1024 * 1024 if name == 'generated/HostBlockTop.sv' else 16 * 1024 * 1024 if name == 'obj/VHostBlockTop' else 2 * 1024 * 1024
        require(type(row['bytes']) is int and 0 < row['bytes'] <= limit, 'invalid payload size')
        require(re.fullmatch('[0-9a-f]{64}', row['sha256']), 'invalid payload digest')
    return files


def validate_archive(archive, expected_sha, expected_commit, inspection=False):
    require(archive.is_file() and not archive.is_symlink() and archive.stat().st_size <= MAX_BYTES, 'invalid archive')
    require(re.fullmatch('[0-9a-f]{64}', expected_sha) and sha(archive) == expected_sha, 'archive digest differs from trusted build output')
    seen = set(); manifest = None
    with gzip.open(archive, 'rb') as inflated, tarfile.open(fileobj=BoundedReader(inflated), mode='r|', ignore_zeros=True) as tar:
        for entry in tar:
            name = safe_name(entry.name)
            require(entry.isreg() and not entry.pax_headers and name not in seen, 'nonregular or duplicate archive entry')
            require(not (entry.mode & ~0o777) and entry.mode == (0o755 if name == 'obj/VHostBlockTop' else 0o644), 'unexpected archive permissions')
            seen.add(name)
            if manifest is None:
                require(name == MANIFEST and 0 < entry.size <= 128 * 1024, 'manifest must be first and bounded')
                manifest = json.load(tar.extractfile(entry), object_pairs_hook=unique_object)
                files = validate_manifest(manifest, expected_commit, inspection)
            else:
                require(name in files and entry.size == files[name]['bytes'], 'extra file or size mismatch: ' + name)
                h = hashlib.sha256()
                stream = tar.extractfile(entry)
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    h.update(chunk)
                require(h.hexdigest() == files[name]['sha256'], 'payload digest mismatch: ' + name)
    require(manifest is not None and seen == set(files) | {MANIFEST}, 'incomplete archive')
    return manifest


def validate_unpacked(build, expected_commit, inspection=False):
    manifest = read_json(build / MANIFEST)
    files = validate_manifest(manifest, expected_commit, inspection)
    for name, expected in files.items():
        require(describe(build / name) == expected, 'unpacked payload changed: ' + name)
    verify_idma_receipts(read_json(build / 'idma_identity.json'),
                         (build / 'idma_sources.sha256.json').read_bytes(), (build / 'idma_commits.json').read_bytes())
    real2_contract(build)
    return manifest


def unpack(repo, archive, expected_sha, expected_commit, output, inspection=False):
    require(not output.exists() and not output.is_symlink(), 'unpack output must be new')
    manifest = validate_archive(archive, expected_sha, expected_commit, inspection)
    if not inspection:
        clean_commit(repo, expected_commit)
        require(manifest['packager_source_sha256'] == sha(repo / SCRIPT), 'checkout helper differs from packaged helper')
    # Do not extract anything until every entry has passed the preceding scan.
    output.mkdir(parents=True)
    with gzip.open(archive, 'rb') as inflated, tarfile.open(fileobj=BoundedReader(inflated), mode='r|', ignore_zeros=True) as tar:
        for entry in tar:
            destination = output / entry.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open('xb') as stream:
                shutil.copyfileobj(tar.extractfile(entry), stream)
            destination.chmod(0o755 if entry.name == 'obj/VHostBlockTop' else 0o644)
    validate_unpacked(output, expected_commit, inspection)
    save(output / 'transfer_receipt.json', {'schema': SCHEMA, 'package_sha256': expected_sha,
         'source_commit': expected_commit, 'inspection_only': inspection, 'archive_verified_before_extraction': True,
         'package_manifest_sha256': sha(output / MANIFEST)})
    return {'status': 'PACKAGE_VERIFIED_NOT_NUMERICAL_PASS', 'source_commit': expected_commit,
            'package_sha256': expected_sha, 'execution_eligible': manifest['execution_eligible']}


def tail(path, limit=4096):
    if not path.is_file():
        return None
    with path.open('rb') as stream:
        stream.seek(max(0, path.stat().st_size - limit))
        return stream.read(limit).decode(errors='replace')


def execute(repo, evidence, hf, expected_commit, expected_sha, timeout_seconds):
    require(timeout_seconds > 0, 'timeout must be positive')
    require(not any((evidence / name).exists() for name in ['run_state.json', 'simulation.exit', 'gate.exit', 'run.log', 'tensors']), 'refuse numerical rerun or evidence overwrite')
    state = {'schema': SCHEMA, 'status': 'PREFLIGHT', 'started_at': now(), 'source_commit': expected_commit,
             'simulator_exit': None, 'timed_out': False, 'signal': None, 'process_launches': 0}
    state_path = evidence / 'run_state.json'
    save(state_path, state)
    child = None
    old_handlers = {}
    def interrupted(signum, _frame):
        state['signal'] = signum
        raise InterruptedError('runner received signal ' + str(signum))
    try:
        clean_commit(repo, expected_commit)
        transfer = read_json(evidence / 'transfer_receipt.json')
        require(transfer['package_sha256'] == expected_sha and transfer['source_commit'] == expected_commit,
                'transfer does not match trusted build outputs')
        require(transfer['inspection_only'] is False and transfer['archive_verified_before_extraction'] is True,
                'unverified or inspection-only transfer')
        require(transfer['package_manifest_sha256'] == sha(evidence / MANIFEST), 'manifest changed after transfer')
        manifest = validate_unpacked(evidence, expected_commit)
        require(manifest['packager_source_sha256'] == sha(repo / SCRIPT), 'replay helper drift')
        validate_maps(repo, evidence, hf)
        state['runtime'] = runtime_identity(evidence / 'obj/VHostBlockTop')
        state['idma_validation'] = 'BUILD_VERIFIED_SOURCE_MAP_PACKAGE_HASH_RECHECKED_NO_RUNTIME_SOURCE_REREAD'
        for sig in (signal.SIGTERM, signal.SIGINT):
            old_handlers[sig] = signal.signal(sig, interrupted)
        with (evidence / 'run.log').open('x') as log:
            # Exactly one launch from reset. The original fixture aliases l1_x
            # to DUT l0_y; there is no layer split or reference-input injection.
            child = subprocess.Popen([str(evidence / 'obj/VHostBlockTop'), str(evidence / 'fixture'), str(evidence / 'tensors')], stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            state.update(status='RUNNING_CONTINUOUS_42_COMMANDS', process_launches=1, simulator_pid=child.pid)
            save(state_path, state)
            try:
                code = child.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                state['timed_out'] = True
                raise TimeoutError('continuous simulator exceeded allotted runtime')
        state['simulator_exit'] = code
        (evidence / 'simulation.exit').write_text(str(code) + '\n')
        state['status'] = 'SIMULATOR_EXITED'
        save(state_path, state)
        require(code == 0, 'simulator nonzero exit: ' + str(code))
        scripts = repo / 'chisel/continuous_prefill/scripts'
        checks = [
            ('source_verification.log', ['production_source_identity.py', 'verify', str(repo), str(evidence), str(hf)]),
            ('verification.log', ['verify_host_block_gate.py', str(evidence)]),
        ]
        for logfile, args in checks:
            with (evidence / logfile).open('x') as log:
                result = subprocess.run([sys.executable, str(scripts / args[0])] + args[1:], stdout=log, stderr=subprocess.STDOUT)
            state.setdefault('verifier_exits', {})[args[0]] = result.returncode
            require(result.returncode == 0, 'original verifier failed: ' + args[0])
        # The original real2 oracle requires the original host gate to finish.
        # Only write this after true simulator success and both original checks.
        (evidence / 'gate.exit').write_text('0\n')
        with (evidence / 'real2_verification.log').open('x') as log:
            result = subprocess.run([sys.executable, str(scripts / 'verify_real_two_layer.py'), '--repo', str(repo), '--evidence', str(evidence), '--output', str(evidence / 'REAL2_ACCEPTANCE.json')], stdout=log, stderr=subprocess.STDOUT)
        state.setdefault('verifier_exits', {})['verify_real_two_layer.py'] = result.returncode
        require(result.returncode == 0, 'original real2 numerical verifier failed')
        require(read_json(evidence / 'REAL2_ACCEPTANCE.json')['status'] == PASS, 'missing original real2 acceptance')
        state['acceptance_sha256'] = sha(evidence / 'REAL2_ACCEPTANCE.json')
        state['status'] = PASS
        return 0
    except (Exception, KeyboardInterrupt) as error:
        state['status'] = 'TIMEOUT_NOT_NUMERICAL_PASS' if state['timed_out'] else 'INTERRUPTED_NOT_NUMERICAL_PASS' if state['signal'] else 'FAILED_NOT_NUMERICAL_PASS'
        state['error'] = str(error)
        return 1
    finally:
        # Preserve a real return code when obtainable; null remains null if the
        # supervisor is killed before it can observe termination.
        for sig in old_handlers:
            signal.signal(sig, signal.SIG_IGN)
        if child is not None:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
            state['simulator_exit'] = child.returncode
            (evidence / 'simulation.exit').write_text(str(child.returncode) + '\n')
        state.update(finished_at=now(), last_progress=tail(evidence / 'run.log'))
        save(state_path, state)
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)


def summarize(evidence, output):
    require(not output.exists(), 'summary output must be new')
    output.mkdir(parents=True)
    state = read_json(evidence / 'run_state.json') if (evidence / 'run_state.json').is_file() else {'status': 'NO_RUN_RECEIPT_NOT_NUMERICAL_PASS', 'simulator_exit': None}
    if not (evidence / 'run_state.json').is_file() and (evidence / 'build.exit').is_file():
        state['build_exit'] = int((evidence / 'build.exit').read_text().strip())
        sealed = (evidence / 'build_receipt.json').is_file() and read_json(evidence / 'build_receipt.json').get('status') == BUILT
        state['status'] = BUILT if state['build_exit'] == 0 and sealed else 'BUILD_FAILED_OR_UNSEALED_NOT_NUMERICAL_PASS'
    elif not (evidence / 'run_state.json').is_file() and evidence.is_dir():
        state['status'] = 'BUILD_OR_TRANSFER_INCOMPLETE_NOT_NUMERICAL_PASS'
    success = (state.get('status') == PASS and state.get('simulator_exit') == 0
               and state.get('timed_out') is False and state.get('signal') is None
               and state.get('process_launches') == 1)
    acceptance = evidence / 'REAL2_ACCEPTANCE.json'
    success = success and all((evidence / n).is_file() and (evidence / n).read_text().strip() == '0'
                              for n in ['gate.exit', 'simulation.exit'])
    if success:
        try:
            accepted = read_json(acceptance)
            success = (accepted.get('status') == PASS and accepted.get('source_commit') == state.get('source_commit')
                       and re.fullmatch('[0-9a-f]{40}', accepted['source_commit']) is not None
                       and accepted.get('commands') == 42 and accepted.get('descriptor_records') == 430
                       and accepted.get('checked_fp32') == 1409024 and accepted.get('bit_differences') == 0
                       and state.get('acceptance_sha256') == sha(acceptance)
                       and state.get('verifier_exits') == {'production_source_identity.py': 0,
                            'verify_host_block_gate.py': 0, 'verify_real_two_layer.py': 0})
        except (ValueError, KeyError, TypeError, OSError):
            success = False
    if state.get('status') in ('PREFLIGHT', 'RUNNING_CONTINUOUS_42_COMMANDS', 'SIMULATOR_EXITED'):
        state['status'] = 'INTERRUPTED_OR_INCOMPLETE_NOT_NUMERICAL_PASS'
    if not success and state.get('status') == PASS:
        state['status'] = 'INCOMPLETE_ACCEPTANCE_NOT_NUMERICAL_PASS'
    state['last_progress'] = next((tail(evidence / n) for n in ['run.log', 'hierarchical_build.log', 'build.log'] if (evidence / n).is_file()), None)
    logs = [p for p in sorted(evidence.glob('*.log')) if p.is_file() and not p.is_symlink()]
    state['log_hashes'] = {p.name: describe(p) for p in logs}
    state['log_tails'] = {p.name: tail(p) for p in logs[:32]}
    state['omitted_log_tails'] = max(0, len(logs) - 32)
    state['artifacts_exclude_tensor_and_csv_payloads'] = True
    for name in ['package_manifest.json', 'transfer_receipt.json', 'build_receipt.json']:
        if (evidence / name).is_file():
            state[name + '_sha256'] = sha(evidence / name)
    save(output / 'SUMMARY.json', state)
    if success:
        shutil.copyfile(acceptance, output / 'REAL2_ACCEPTANCE.json')
    return {'status': state['status'], 'numerical_pass': success, 'summary': str(output / 'SUMMARY.json')}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action', required=True)
    for name in ['seal-build', 'package', 'unpack', 'run', 'summarize']:
        s = sub.add_parser(name)
        if name != 'summarize':
            s.add_argument('--repo', type=Path, required=True)
        if name in ('seal-build', 'package'):
            s.add_argument('--build', type=Path, required=True)
            s.add_argument('--idma-export', type=Path, required=name == 'seal-build')
        if name in ('seal-build', 'package', 'run'):
            s.add_argument('--hardfloat', type=Path, required=name != 'package')
        if name in ('package', 'unpack', 'summarize'):
            s.add_argument('--output', type=Path, required=True)
        if name in ('package', 'unpack'):
            s.add_argument('--inspection-only', action='store_true')
        if name in ('unpack', 'run'):
            s.add_argument('--expected-commit', required=True)
            s.add_argument('--expected-sha256', required=True)
        if name == 'unpack':
            s.add_argument('--archive', type=Path, required=True)
        if name in ('run', 'summarize'):
            s.add_argument('--evidence', type=Path, required=True)
        if name == 'run':
            s.add_argument('--timeout-seconds', type=int, default=19500)
        if name == 'package':
            s.add_argument('--github-output', type=Path)
    a = p.parse_args()
    for key, value in vars(a).items():
        if isinstance(value, Path):
            setattr(a, key, value.absolute())
    try:
        if a.action == 'seal-build':
            result = seal_build(a.repo, a.build, a.hardfloat, a.idma_export)
            result = {'status': result['status'], 'source_commit': result['source_commit']}
        elif a.action == 'package':
            result = package(a.repo, a.build, a.output, a.hardfloat, a.idma_export, a.inspection_only)
            if a.github_output:
                require(not a.inspection_only, 'inspection package cannot produce trusted workflow outputs')
                with a.github_output.open('a') as stream:
                    stream.write('package_sha256=' + result['package_sha256'] + '\nsource_commit=' + result['source_commit'] + '\n')
        elif a.action == 'unpack':
            result = unpack(a.repo, a.archive, a.expected_sha256, a.expected_commit, a.output, a.inspection_only)
        elif a.action == 'run':
            return execute(a.repo, a.evidence, a.hardfloat, a.expected_commit, a.expected_sha256, a.timeout_seconds)
        else:
            result = summarize(a.evidence, a.output)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError, tarfile.TarError) as error:
        print('REAL2_CI_REJECTED: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
