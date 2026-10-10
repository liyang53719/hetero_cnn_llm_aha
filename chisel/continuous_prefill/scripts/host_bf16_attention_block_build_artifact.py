#!/usr/bin/env python3
"""Transfer one frozen Attention full-block build, never numerical evidence.

The receiver supplies the build job's trusted archive digest and exact source
commit independently. Compiler binaries, JARs, iDMA and HardFloat are reacquired
externally and checked by the original live gate at their recorded paths. No
tool is rebuilt, no receipt is rebound, and no model/fixture tensors transfer.
"""
from pathlib import Path
import argparse
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import stat
import tarfile
import tempfile
import time
import urllib.request

import host_bf16_attention_block_live_gate as live
from real2_ci import (BoundedReader, MAX_BYTES, describe, encoded, hash_map,
                      read_json, require, safe_name, sha, unique_object,
                      validate_maps)
from run_host_bf16_qkv_fresh_gate import verify_checkout

ROOT = live.ROOT
MANIFEST = 'attention_block_package_manifest.json'
FILES = frozenset((
    'obj/VHostBlockTop', 'generated/HostBlockTop.sv', 'generated/SCOPE.json',
    'build_ready.json', 'build.exit', 'initial_verilation.exit',
    'source_base_commit.txt', 'sources.sha256.json', 'hardfloat.sha256.json',
    'source_scope.json', 'toolchain.json', 'compiler_jars.sha256.json',
    'idma_identity.json', 'actual_verilator_before.json',
    'actual_verilator_after.json',
))
MANIFEST_KEYS = frozenset(('schema', 'status', 'scope', 'numerical_pass',
                         'source_commit', 'sources', 'files',
                         'binary_sha256', 'rtl_sha256'))
MANIFEST_BYTES = 256 * 1024
MAVEN_PREFIX = 'https/repo1.maven.org/maven2/'
MAX_JARS = 256
MAX_JAR_BYTES = 64 * 1024 * 1024
MAX_JAR_TOTAL_BYTES = 512 * 1024 * 1024
JAR_TIMEOUT_SECONDS = 30
JAR_TOTAL_TIMEOUT_SECONDS = 900


class _ArchiveReader(BoundedReader):
    def __init__(self, stream):
        super().__init__(stream)
        self.tail = b''

    def read(self, size):
        data = super().read(size)
        self.tail = (self.tail + data)[-1024:]
        return data


def _regular(path):
    path = Path(path)
    require(not any(p.is_symlink() for p in (path, *path.parents)),
            'symlink in evidence path')
    require(path.is_file() and stat.S_ISREG(path.stat().st_mode),
            'missing regular evidence file: ' + str(path))
    return path


def _new_path(path):
    path = Path(path).absolute()
    require(not path.exists() and not any(p.is_symlink() for p in (path, *path.parents)),
            'refuse evidence overwrite or symlink')
    return path


def _limit(name):
    return (96 * 1024 * 1024 if name == 'generated/HostBlockTop.sv' else
            16 * 1024 * 1024 if name == 'obj/VHostBlockTop' else 2 * 1024 * 1024)


def _admit(build, commit):
    """Use the existing build/source authorities; never substitute archive trust."""
    require(type(commit) is str and re.fullmatch('[0-9a-f]{40}', commit),
            'exact trusted source commit required')
    build = Path(build)
    require(build.is_dir() and not build.is_symlink(), 'build evidence path')
    for name in FILES:
        _regular(build / name)
    require((build/'obj/VHostBlockTop').stat().st_mode & 0o111,
            'simulator must be executable')
    sources = hash_map(read_json(build/'sources.sha256.json'))
    required = hash_map(live.fixture.source_identity())
    require(all(sources.get(name) == digest for name, digest in required.items()),
            'incomplete live source closure')
    verify_checkout(commit, sources)
    ready = read_json(build/'build_ready.json')
    require(ready['source_base_commit'] == commit and
            (build/'source_base_commit.txt').read_text().strip() == commit,
            'build source commit mismatch')
    require((build/'build.exit').read_text().strip() == '0' and
            (build/'initial_verilation.exit').read_text().strip() == '0',
            'build did not complete')
    require(ready.get('source_snapshot_manifest_sha256') is None,
            'exact checkout required, not a rebound source snapshot')
    require(read_json(build/'source_scope.json') ==
            {'scope': 'full', 'unrelated_helpers_bound': True},
            'full source scope required')
    hf = Path(os.environ.get('HARDFLOAT_SOURCE', ROOT/'work/upstream/hardfloat_continuous')).resolve()
    require(Path(ready['hardfloat_source']) == hf,
            'HardFloat build path differs; do not rebind receipts')
    # Keep the external pinned checkout and every original source hash live.
    validate_maps(ROOT, build, hf)
    toolchain = read_json(build/'toolchain.json')
    require(toolchain['compiler_jars_verified_after_build'] is True and
            hash_map(toolchain['compiler_jars_sha256']) == read_json(build/'compiler_jars.sha256.json') and
            hash_map(toolchain['hardfloat_source_sha256']) == read_json(build/'hardfloat.sha256.json') and
            toolchain['idma_identity'] == read_json(build/'idma_identity.json'),
            'tool/source receipt mismatch')
    hash_map(toolchain['idma_export_source_sha256'])
    actual = read_json(build/'actual_verilator_after.json')
    require(actual == read_json(build/'actual_verilator_before.json') == ready['actual_verilator'],
            'actual Verilator identity drift')
    tools = toolchain['tools']
    require('Verilator 5.032' in tools['verilator_backend']['version'] and
            '1.62.1' in tools['firtool']['version'], 'unpinned Verilator/firtool')
    backend = actual['actual_elf']
    backend_path = Path(backend['path'])
    require(backend['kind'] == 'ELF' and backend_path.is_absolute() and
            backend_path.is_file() and sha(backend_path) == backend['sha256'] and
            backend['version'] == actual['entrypoint']['version'] == tools['verilator_backend']['version'] and
            actual['entrypoint']['sha256'] == tools['verilator_backend']['sha256'],
            'actual Verilator ELF identity mismatch')
    with backend_path.open('rb') as stream:
        require(stream.read(4) == b'\x7fELF', 'actual Verilator ELF required')
    identity = live.build_identity(build, required)
    live.verify_all_build_sources(build, 'artifact_source_verify.log')
    require(live.build_identity(build, required) == identity, 'build changed during source admission')
    return ready, sources


def _validate_manifest(manifest, commit):
    require(type(manifest) is dict and set(manifest) == MANIFEST_KEYS,
            'unexpected package manifest fields')
    require(type(commit) is str and re.fullmatch('[0-9a-f]{40}', commit) and
            type(manifest['schema']) is int and manifest['schema'] == 1 and
            manifest['source_commit'] == commit, 'package commit/schema mismatch')
    require(manifest['status'] == live.BUILD_STATUS and manifest['scope'] == live.SCOPE and
            manifest['numerical_pass'] is False, 'Attention block build-only package required')
    files = manifest['files']
    require(type(files) is dict and set(files) == FILES, 'package file allowlist mismatch')
    for name, row in files.items():
        safe_name(name)
        require(type(row) is dict and set(row) == {'bytes', 'sha256'} and
                type(row['bytes']) is int and 0 < row['bytes'] <= _limit(name) and
                type(row['sha256']) is str and re.fullmatch('[0-9a-f]{64}', row['sha256']),
                'invalid or oversized package file identity')
    require(sum(row['bytes'] for row in files.values()) <= MAX_BYTES, 'package exceeds size bound')
    require(manifest['binary_sha256'] == files['obj/VHostBlockTop']['sha256'] and
            manifest['rtl_sha256'] == files['generated/HostBlockTop.sv']['sha256'],
            'package binary/RTL digest mismatch')
    hash_map(manifest['sources'])
    require(len(encoded(manifest)) <= MANIFEST_BYTES, 'package manifest exceeds size bound')
    return files


def _read_archive(path, digest, commit, output=None, *, capture=None):
    """Validate every entry, including trailing/concatenated gzip/tar content."""
    path = _regular(path)
    require(path.stat().st_size <= MAX_BYTES, 'archive exceeds size bound')
    require(type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest) and sha(path) == digest,
            'archive digest differs from trusted build-job output')
    seen, manifest = set(), None
    try:
        with gzip.open(path, 'rb') as raw:
            bounded = _ArchiveReader(raw)
            archive = tarfile.open(fileobj=bounded, mode='r|', ignore_zeros=True)
            with archive:
                manifest = _read_entries(archive, seen, commit, output, capture)
            require(bounded.bytes % 512 == 0 and bounded.tail == b'\0' * 1024,
                    'invalid or truncated tar terminator')
    except (EOFError, OSError, tarfile.TarError) as error:
        raise ValueError('invalid or truncated package archive') from error
    require(manifest is not None and seen == FILES | {MANIFEST}, 'incomplete archive')
    require(sha(path) == digest, 'archive changed during admission')
    return manifest


def _read_entries(archive, seen, commit, output, capture):
    manifest = None
    for entry in archive:
        name = safe_name(entry.name)
        require(entry.type in (tarfile.REGTYPE, tarfile.AREGTYPE) and not entry.linkname and
                not entry.pax_headers and name not in seen and len(seen) < len(FILES) + 1,
                'nonregular, duplicate or excess archive entry')
        require(entry.mode == (0o755 if name == 'obj/VHostBlockTop' else 0o644),
                'unexpected archive permissions')
        seen.add(name)
        if manifest is None:
            require(name == MANIFEST and 0 < entry.size <= MANIFEST_BYTES,
                    'bounded manifest must be first')
            data = archive.extractfile(entry).read()
            manifest = json.loads(data, object_pairs_hook=unique_object)
            files = _validate_manifest(manifest, commit)
        else:
            require(name in files and entry.size == files[name]['bytes'],
                    'unexpected file or size mismatch')
            data = archive.extractfile(entry).read()
            require(len(data) == entry.size and hashlib.sha256(data).hexdigest() == files[name]['sha256'],
                    'archive file digest mismatch')
            if name == 'obj/VHostBlockTop':
                require(data[:4] == b'\x7fELF', 'actual compiled ELF required')
        if capture is not None and name in capture:
            capture[name] = data
        if output is not None:
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(data)
            target.chmod(0o555 if name == 'obj/VHostBlockTop' else 0o444)
    return manifest


def _receipt(manifest, digest):
    files = manifest['files']
    return dict(schema=1, status=live.BUILD_STATUS, scope=live.SCOPE, numerical_pass=False,
                source_commit=manifest['source_commit'], package_sha256=digest,
                binary_sha256=manifest['binary_sha256'], rtl_sha256=manifest['rtl_sha256'],
                build_ready_sha256=files['build_ready.json']['sha256'],
                source_manifest_sha256=files['sources.sha256.json']['sha256'],
                toolchain_sha256=files['toolchain.json']['sha256'])


def seal(build, archive, expected_commit):
    """Seal only a new build's allowlisted files, returning a compact receipt."""
    build, archive = Path(build), _new_path(archive)
    ready, sources = _admit(build, expected_commit)
    files = {name: describe(_regular(build/name)) for name in sorted(FILES)}
    manifest = dict(schema=1, status=live.BUILD_STATUS, scope=live.SCOPE,
                    numerical_pass=False, source_commit=expected_commit, sources=sources,
                    files=files, binary_sha256=ready['binary_sha256'], rtl_sha256=ready['rtl_sha256'])
    _validate_manifest(manifest, expected_commit)
    archive.parent.mkdir(parents=True, exist_ok=True)
    raw = archive.open('xb')
    try:
        with raw, gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as zipped, \
                tarfile.open(fileobj=zipped, mode='w', format=tarfile.USTAR_FORMAT) as output:
            for name in [MANIFEST] + sorted(FILES):
                data = encoded(manifest) if name == MANIFEST else _regular(build/name).read_bytes()
                entry = tarfile.TarInfo(name)
                entry.size = len(data)
                entry.mode = 0o755 if name == 'obj/VHostBlockTop' else 0o644
                output.addfile(entry, io.BytesIO(data))
        digest = sha(archive)
        _read_archive(archive, digest, expected_commit)
        _admit(build, expected_commit)
        require(all(describe(_regular(build/name)) == row for name, row in files.items()),
                'build changed while sealing')
        archive.chmod(0o444)
        return _receipt(manifest, digest)
    except BaseException:
        archive.unlink(missing_ok=True)
        raise


def restore(archive, destination, expected_sha256, expected_commit):
    """Re-admit read-only build files before publishing a fresh destination.

    OFFLINE_TOOLS/jars must contain the original compiler receipt's relative
    paths. Build-local caches are deliberately not part of this artifact.
    The destination root stays writable for the original case runner's logs.
    """
    destination = _new_path(destination)
    manifest = _read_archive(archive, expected_sha256, expected_commit)
    verify_checkout(expected_commit, manifest['sources'])
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.attention-build-', dir=destination.parent))
    try:
        require(_read_archive(archive, expected_sha256, expected_commit, temporary) == manifest,
                'archive changed before extraction')
        _admit(temporary, expected_commit)
        require(all(describe(_regular(temporary/name)) == row for name, row in manifest['files'].items()),
                'restored build identity drift')
        require(read_json(temporary/'sources.sha256.json') == manifest['sources'],
                'manifest source closure mismatch')
        # Verification logs are local execution evidence, never transfer inputs.
        (temporary/'artifact_source_verify.log').unlink(missing_ok=True)
        require(not destination.exists() and not destination.is_symlink(), 'refuse evidence overwrite')
        temporary.rename(destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return _receipt(manifest, expected_sha256)


def _jar_url(name):
    safe_name(name)
    require(name.startswith(MAVEN_PREFIX) and name.endswith('.jar') and
            all(re.fullmatch('[A-Za-z0-9_.+-]+', part) and part not in ('.', '..')
                for part in name[len(MAVEN_PREFIX):].split('/')),
            'compiler JAR origin/path must be official repo1.maven.org/maven2')
    return 'https://' + name[len('https/'):]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, new_url):
        raise ValueError('compiler JAR redirect is not permitted')


def _open_maven(url, timeout):
    request = urllib.request.Request(url, headers={'User-Agent': 'Attention-build-artifact/1'})
    return urllib.request.build_opener(_NoRedirect()).open(request, timeout=timeout)


def _download_jar(url, output, expected_sha256, deadline, remaining_bytes):
    require(time.monotonic() < deadline, 'compiler JAR preparation timeout')
    require(remaining_bytes > 0, 'compiler JAR total bytes exceed bound')
    digest, size = hashlib.sha256(), 0
    timeout = min(JAR_TIMEOUT_SECONDS, deadline-time.monotonic())
    require(timeout > 0, 'compiler JAR preparation timeout')
    with _open_maven(url, timeout) as response:
        require(response.geturl() == url and response.status == 200, 'unexpected compiler JAR response')
        length = response.headers.get('Content-Length')
        limit = min(MAX_JAR_BYTES, remaining_bytes)
        if length is not None:
            require(re.fullmatch('[0-9]+', length) and 0 < int(length) <= limit,
                    'compiler JAR exceeds byte bound')
        with output.open('xb') as stream:
            while True:
                require(time.monotonic() < deadline, 'compiler JAR preparation timeout')
                data = response.read(min(1024*1024, limit-size+1))
                if not data:
                    break
                size += len(data)
                require(size <= limit, 'compiler JAR exceeds byte bound')
                digest.update(data)
                stream.write(data)
    require(size > 0 and (length is None or size == int(length)), 'empty or truncated compiler JAR')
    require(digest.hexdigest() == expected_sha256, 'compiler JAR digest mismatch')
    output.chmod(0o444)
    return size


def _jar_cache_file(path, digest):
    _regular(path)
    require(path.stat().st_nlink == 1 and 0 < path.stat().st_size <= MAX_JAR_BYTES,
            'compiler JAR cache link or byte bound')
    require(sha(path) == digest, 'existing compiler JAR cache digest mismatch')
    return path.stat().st_size


def prepare_compiler_jars(archive, runtime_root, expected_sha256, expected_commit):
    """Reacquire only hash-bound public compiler JARs, without running them.

    Every download is staged and verified before any cache file is published.
    The exact original relative cache keys survive for live-gate readmission.
    """
    captured = {'compiler_jars.sha256.json': None}
    manifest = _read_archive(archive, expected_sha256, expected_commit, capture=captured)
    verify_checkout(expected_commit, manifest['sources'])
    jars = hash_map(json.loads(captured['compiler_jars.sha256.json'], object_pairs_hook=unique_object))
    require(len(jars) <= MAX_JARS, 'compiler JAR count exceeds bound')
    urls = {name: _jar_url(name) for name in jars}
    runtime_root = Path(runtime_root).absolute()
    jar_root = runtime_root/'jars'
    require(not any(p.is_symlink() for p in (jar_root, *jar_root.parents)) and
            all(not p.exists() or p.is_dir() for p in (jar_root, *jar_root.parents)),
            'compiler JAR runtime must be a directory without symlinks')
    cached, total = {}, 0
    for name, digest in jars.items():
        path = jar_root/name
        if path.exists() or path.is_symlink():
            cached[name] = _jar_cache_file(path, digest)
            total += cached[name]
    require(total <= MAX_JAR_TOTAL_BYTES, 'compiler JAR total bytes exceed bound')
    # Stage on the destination filesystem; no runtime files appear on download
    # failure, hash mismatch, expired budget or changed archive/source identity.
    parent = runtime_root.parent
    while not parent.exists():
        parent = parent.parent
    deadline = time.monotonic() + JAR_TOTAL_TIMEOUT_SECONDS
    with tempfile.TemporaryDirectory(prefix='.attention-jars-', dir=parent) as temporary:
        staging = Path(temporary)
        for index, (name, digest) in enumerate(jars.items()):
            if name not in cached:
                size = _download_jar(urls[name], staging/str(index), digest, deadline,
                                     MAX_JAR_TOTAL_BYTES-total)
                total += size
        require(time.monotonic() < deadline, 'compiler JAR preparation timeout')
        require(sha(_regular(archive)) == expected_sha256, 'archive changed during compiler JAR preparation')
        verify_checkout(expected_commit, manifest['sources'])
        # Recheck existing files immediately before publication. A different
        # byte sequence is an error, never a reason to replace a cache entry.
        for name, digest in jars.items():
            path = jar_root/name
            if path.exists() or path.is_symlink():
                _jar_cache_file(path, digest)
        published = []
        try:
            for index, (name, digest) in enumerate(jars.items()):
                path = jar_root/name
                if name in cached:
                    _jar_cache_file(path, digest)
                    continue
                require(not any(p.is_symlink() for p in (path, *path.parents)), 'compiler JAR cache symlink')
                path.parent.mkdir(parents=True, exist_ok=True)
                # An atomic no-replace link publishes only completed bytes.
                # Remove the private staging name immediately; final cache
                # entries are ordinary single-link files, never symlinks.
                os.link(staging/str(index), path)
                published.append(path)
                (staging/str(index)).unlink()
            for name, digest in jars.items():
                _jar_cache_file(jar_root/name, digest)
        except BaseException:
            for path in reversed(published):
                path.unlink()
            raise
    return dict(status='PREPARED_ATTENTION_BLOCK_COMPILER_JARS',
                source_commit=expected_commit, package_sha256=expected_sha256,
                compiler_jars_manifest_sha256=manifest['files']['compiler_jars.sha256.json']['sha256'],
                jar_count=len(jars), total_bytes=total,
                downloaded_files=len(jars)-len(cached), reused_files=len(cached))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-jars', action='store_true', required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--expected-sha256', required=True)
    parser.add_argument('--expected-commit', required=True)
    args = parser.parse_args(argv)
    print(json.dumps(prepare_compiler_jars(args.archive, args.runtime,
                                        args.expected_sha256, args.expected_commit), sort_keys=True))


if __name__ == '__main__':
    main()
