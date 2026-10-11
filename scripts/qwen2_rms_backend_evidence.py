#!/usr/bin/env python3
"""Restore/verify immutable Torch source evidence and inspect this host's backend.

verify is offline and leaves the source directory unchanged. restore downloads
only the 14 published source records into a fresh directory. Both write a fresh
metadata-only report; no pointers, model tensors, or environment values are
printed. This supplementary check was NOT enforced by the historical RMS/RoPE
diagnostic CLI and changes no numerical/hardware acceptance policy.

Example (no network):
  python scripts/qwen2_rms_backend_evidence.py verify \
    --sources work/qwen2_rms_rope_sources_20261011 \
    --report work/qwen2_rms_backend_verify_new.json
"""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import sys
import urllib.request
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = ROOT / 'reports/execution/QWEN2_RMS_ROPE_POLICY_20261011'
COMMIT = '449b1768410104d3ed79d3bcfe4ba1d65c7f22c0'
BASE_URL = 'https://raw.githubusercontent.com/pytorch/pytorch/' + COMMIT + '/aten/src/ATen/'
MANIFEST_SHA = '52555a6d4b7b307e7e87bb2cb6bfcaf4b20d27fa58046ef50ea78427a38dcbf9'
BACKEND_SHA = 'ab362419567a7278b69c50f59b04659a64ed1ce102664c8efd7bd712e64ff06e'
HEADER_PATHS = {
    'vec256_float.h': 'ATen/cpu/vec/vec256/vec256_float.h',
    'vec512_float.h': 'ATen/cpu/vec/vec512/vec512_float.h',
    'vml.h': 'ATen/cpu/vml.h',
    'Loops.h': 'ATen/native/cpu/Loops.h',
    'DispatchStub.h': 'ATen/native/DispatchStub.h',
}
HEADER_PREFIX = b'#if !defined(TORCH_STABLE_ONLY) && !defined(TORCH_TARGET_VERSION)\n'
HEADER_SUFFIX = (b'\n#else\n#error "This file should not be included when either TORCH_STABLE_ONLY '
                 b'or TORCH_TARGET_VERSION is defined."\n#endif  // !defined(TORCH_STABLE_ONLY) '
                 b'&& !defined(TORCH_TARGET_VERSION)\n')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def file_identity(path):
    """Bound current library bytes using bounded reads, without loading a copy."""
    hasher = hashlib.sha256()
    count = 0
    with Path(path).open('rb') as stream:
        before = os.fstat(stream.fileno())
        while chunk := stream.read(1 << 20):
            hasher.update(chunk)
            count += len(chunk)
        after = os.fstat(stream.fileno())
    require((before.st_size, before.st_mtime_ns, before.st_ino) ==
            (after.st_size, after.st_mtime_ns, after.st_ino) and count == after.st_size,
            'library changed while hashing')
    return dict(file=Path(path).name, bytes=count, sha256=hasher.hexdigest())


def safe_path(value):
    """No lexical traversal or symlinks, including in any existing ancestor."""
    path = Path(value)
    require('..' not in path.parts, 'path traversal is forbidden')
    path = path.absolute()
    for part in (path, *path.parents):
        require(not part.is_symlink(), 'symlink paths are forbidden')
    return path


def validate_entries(entries):
    require(isinstance(entries, list) and len(entries) == 14, 'exactly 14 source pins required')
    names = set()
    for entry in entries:
        require(set(entry) == {'source', 'file', 'sha256', 'bytes'}, 'unexpected source record fields')
        filename = PurePosixPath(entry['file'])
        require(not filename.is_absolute() and '..' not in filename.parts
                and '\\' not in entry['file'], 'source record path traversal')
        name = filename.name
        require(re.fullmatch(r'[A-Za-z0-9_]+\.(cpp|h)', name) is not None
                and name not in names, 'invalid or duplicate source basename')
        names.add(name)
        url = entry['source']
        parsed = urlsplit(url)
        tail = url.removeprefix(BASE_URL)
        require(url.startswith(BASE_URL) and not parsed.query and not parsed.fragment
                and parsed.netloc == 'raw.githubusercontent.com'
                and '..' not in PurePosixPath(tail).parts and '%' not in tail
                and '\\' not in tail and '//' not in tail
                and PurePosixPath(tail).name == name, 'source URL is not an immutable allowlisted URL')
        require(type(entry['bytes']) is int and 0 < entry['bytes'] <= 1_000_000, 'invalid source byte length')
        require(isinstance(entry['sha256'], str) and re.fullmatch('[0-9a-f]{64}', entry['sha256']),
                'invalid source digest')
    return entries


def load_pins(directory=PUBLISHED):
    raw = safe_path(directory / 'source_manifest.json').read_bytes()
    require(digest(raw) == MANIFEST_SHA, 'published source manifest drift')
    entries = validate_entries(json.loads(raw))
    backend_raw = safe_path(directory / 'backend_observation.json').read_bytes()
    require(digest(backend_raw) == BACKEND_SHA, 'published backend template drift')
    backend = json.loads(backend_raw)
    # Historical machine identity and absolute paths are deliberately unused.
    symbols = backend['dispatch_pointer_observations']
    require(len(symbols) == 8 and all(set(caps) == {'AVX2', 'AVX512', 'DEFAULT'} for caps in symbols.values()),
            'expected 24 dispatch records')
    require({r['upstream_file'] for r in backend['installed_header_observations']} == set(HEADER_PATHS),
            'expected five installed header records')
    return raw, entries, backend


def checked_bytes(raw, entry):
    require(len(raw) == entry['bytes'] and digest(raw) == entry['sha256'],
            'source bytes/hash drift: ' + PurePosixPath(entry['file']).name)
    return raw


def fetch_pinned(entry):
    """Bounded source-only download; reject redirects and extra response bytes."""
    request = urllib.request.Request(entry['source'], headers={'Accept': 'text/plain'})
    with urllib.request.urlopen(request, timeout=30) as response:
        require(response.status == 200 and response.geturl() == entry['source'], 'source HTTP status/URL changed')
        return checked_bytes(response.read(entry['bytes'] + 1), entry)


def restore_sources(directory, manifest_raw, entries, fetch=fetch_pinned):
    directory = safe_path(directory)
    require(not directory.exists(), 'refuse existing source output directory')
    # Validate every response before creating output. No partial source set on
    # a failed download, and no preexisting file is opened for replacement.
    payloads = [(PurePosixPath(e['file']).name, checked_bytes(fetch(e), e)) for e in entries]
    require(not directory.exists(), 'source output appeared during retrieval')
    directory.mkdir(parents=True, exist_ok=False)
    for name, raw in [('source_manifest.json', manifest_raw), *payloads]:
        with (directory / name).open('xb') as stream:
            stream.write(raw)
    return directory


def verify_sources(directory, manifest_raw, entries):
    directory = safe_path(directory)
    require(directory.is_dir(), 'source directory is absent')
    stored_manifest = safe_path(directory / 'source_manifest.json').read_bytes()
    require(stored_manifest == manifest_raw, 'restored source manifest drift')
    observed = []
    for entry in entries:
        name = PurePosixPath(entry['file']).name
        raw = checked_bytes(safe_path(directory / name).read_bytes(), entry)
        observed.append(dict(file=name, bytes=len(raw), sha256=digest(raw), source=entry['source']))
    return observed


def observe_pointer(library, symbol):
    """Return presence and nullness only; never return a pointer address."""
    try:
        return dict(present=True, non_null=ctypes.c_void_p.in_dll(library, symbol).value is not None)
    except ValueError:
        return dict(present=False, non_null=None)


def cpu_model():
    path = Path('/proc/cpuinfo')
    if path.exists():
        for line in path.read_text().splitlines():
            if line.startswith('model name') and ':' in line:
                return line.split(':', 1)[1].strip()
    return platform.processor() or 'unavailable'


def inspect_backend(directory, backend_template, torch_module, pointer_reader=observe_pointer,
                    library_loader=ctypes.CDLL):
    package = Path(torch_module.__file__).absolute().parent
    library_path = package / 'lib/libtorch_cpu.so'
    library = library_loader(str(library_path))
    library_identity = file_identity(library_path)
    checks = []
    for stub, caps in backend_template['dispatch_pointer_observations'].items():
        for capability, expected in caps.items():
            symbol = expected['symbol']
            require(re.fullmatch(r'_ZN[A-Za-z0-9_]+', symbol) is not None, 'invalid dispatch symbol')
            actual = pointer_reader(library, symbol)
            require(set(actual) == {'present', 'non_null'} and type(actual['present']) is bool
                    and (actual['non_null'] is None or type(actual['non_null']) is bool), 'invalid pointer observation')
            checks.append(dict(stub=stub, capability=capability, symbol=symbol, **actual,
                               expected_non_null=expected['non_null'],
                               matches=actual['present'] == expected['present'] and actual['non_null'] == expected['non_null']))
    headers = []
    for name, relative in HEADER_PATHS.items():
        upstream = safe_path(directory / name).read_bytes()
        installed_path = package / 'include' / relative
        installed = safe_path(installed_path).read_bytes() if installed_path.exists() else None
        match = installed in (upstream, HEADER_PREFIX + upstream + HEADER_SUFFIX)
        headers.append(dict(upstream_file=name, installed_relative_path='include/' + relative,
                            present=installed is not None, installed_bytes=(len(installed) if installed is not None else None),
                            installed_sha256=(digest(installed) if installed is not None else None),
                            upstream_sha256=digest(upstream), upstream_bytes_match_installed_body=match,
                            upstream_body_byte_offset=(0 if installed == upstream else len(HEADER_PREFIX)) if match else None))
    current = dict(torch_version=torch_module.__version__, torch_git_version=torch_module.version.git_version,
                   reported_cpu_capability=torch_module.backends.cpu.get_cpu_capability(),
                   num_threads=torch_module.get_num_threads(), num_interop_threads=torch_module.get_num_interop_threads(),
                   deterministic_algorithms=torch_module.are_deterministic_algorithms_enabled(),
                   aten_cpu_capability_override_present='ATEN_CPU_CAPABILITY' in os.environ,
                   machine=platform.machine(), cpu_model=cpu_model())
    expected_runtime_match = (current['torch_version'] == '2.10.0+cpu' and current['torch_git_version'] == COMMIT
                              and current['reported_cpu_capability'] == 'AVX512'
                              and not current['aten_cpu_capability_override_present'])
    matches = expected_runtime_match and all(c['matches'] for c in checks) and all(h['upstream_bytes_match_installed_body'] for h in headers)
    return dict(current_runtime=current, current_torch_cpu_library=library_identity,
                runtime_matches_frozen_version_and_capability=expected_runtime_match,
                dispatch_pointer_observations=checks, installed_header_observations=headers,
                all_backend_checks_match=matches, dispatch_functions_invoked=False,
                historical_machine_identity_reused=False)


def write_report(path, report):
    path = safe_path(path)
    require(not path.exists(), 'refuse existing metadata report')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        stream.write(json.dumps(report, indent=2) + '\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('restore', 'verify'))
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args(argv)
    source_dir, report_path = safe_path(args.sources), safe_path(args.report)
    require(not report_path.exists(), 'refuse existing metadata report')
    require(not report_path.is_relative_to(source_dir), 'metadata report must be outside the source directory')
    manifest_raw, entries, backend = load_pins()
    if args.mode == 'restore':
        restore_sources(source_dir, manifest_raw, entries)
    source_checks = verify_sources(source_dir, manifest_raw, entries)
    import torch
    observations = inspect_backend(source_dir, backend, torch)
    # Check source files again before sealing the report. No model is loaded.
    require(source_checks == verify_sources(source_dir, manifest_raw, entries), 'source changed during backend inspection')
    report = dict(schema=1, status='BACKEND_EVIDENCE_MATCH' if observations['all_backend_checks_match'] else 'BACKEND_EVIDENCE_MISMATCH',
                  numerical_status='DIAGNOSTIC_NOT_ACCEPTED', observed_at_utc=datetime.now(timezone.utc).isoformat(),
                  mode=args.mode, generator_sha256=digest(Path(__file__).read_bytes()),
                  published_manifest_sha256=MANIFEST_SHA, published_backend_template_sha256=BACKEND_SHA,
                  source_files=source_checks, source_file_count=len(source_checks), **observations,
                  network_downloads=14 if args.mode == 'restore' else 0,
                  output_contains='metadata_only', model_loaded=False, model_forward_executed=False, rtl_executed=False,
                  historical_main_cli_enforced_this_backend_check=False, numerical_or_hardware_acceptance_changed=False,
                  capture_path_mapping_restored=False)
    write_report(report_path, report)
    print(json.dumps({k: report[k] for k in ('status', 'source_file_count', 'all_backend_checks_match', 'network_downloads', 'numerical_status')}))
    return 0 if observations['all_backend_checks_match'] else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as error:
        print('backend evidence failed: ' + str(error), file=sys.stderr)
        raise SystemExit(2)
