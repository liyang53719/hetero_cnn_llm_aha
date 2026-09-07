#!/usr/bin/env python3
"""Read-only portable audit of a published Host owner regression directory.

Verifies all stored bytes and re-reads actual outputs/CSV, without a simulator,
compiled DUT libraries or original CI absolute paths. This does NOT re-run RTL.
Use with the source checkout whose immutable source manifest matches the proof.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys


def require(ok, message):
    if not ok:
        raise ValueError(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def read_json(path):
    return json.loads(path.read_text(), object_pairs_hook=unique_object)


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def inventory(root):
    require(root.is_dir() and not root.is_symlink(), 'invalid evidence root')
    manifest_path = root / 'PUBLISHED_SHA256.json'
    require(manifest_path.is_file() and not manifest_path.is_symlink(), 'missing manifest')
    manifest = read_json(manifest_path)
    require(isinstance(manifest, dict) and bool(manifest), 'empty/invalid manifest')
    for name, checksum in manifest.items():
        p = PurePosixPath(name)
        require(not p.is_absolute() and '..' not in p.parts and str(p) == name, 'unsafe/noncanonical path')
        require(isinstance(checksum, str) and re.fullmatch('[0-9a-f]{64}', checksum), 'invalid digest')
        target = root / name
        require(target.is_file() and not target.is_symlink(), 'missing/symlink file: ' + name)
        require(target.resolve().is_relative_to(root.resolve()), 'path escapes evidence')
        require(sha(target) == checksum, 'stored byte mismatch: ' + name)
    paths = set()
    for path in root.rglob('*'):
        require(not path.is_symlink(), 'symlink in publication')
        if path.is_file():
            paths.add(str(path.relative_to(root)))
    require(paths == set(manifest) | {'PUBLISHED_SHA256.json'}, 'extra or missing publication files')
    return manifest


def source_compatibility(repo, relative, expected, changes):
    path = repo / relative
    current = sha(path)
    if current == expected:
        return
    # Narrow compatibility for the post-run CLI preservation fix. Reconstruct
    # the entire original byte stream; no function, DUT, recipe or tolerance is
    # exempted. An arbitrary edit anywhere else still fails the exact SHA check.
    allowed = {'chisel/continuous_prefill/scripts/run_owner_lifecycle_gate.py',
               'chisel/continuous_prefill/scripts/run_owner_replay_gate.py'}
    marker = "        # Existing evidence is never changed on rejection; caller records exit status.\n"
    original = "        if a.output.exists():(a.output/'gate.exit').write_text('1\\n')\n"
    raw = path.read_text()
    require(relative in allowed and raw.count(marker) == 1, 'checkout differs from tested source: ' + relative)
    restored = raw.replace(marker, original).encode()
    require(hashlib.sha256(restored).hexdigest() == expected, 'non-CLI source drift: ' + relative)
    changes[relative] = {'tested_sha256': expected, 'current_sha256': current,
                         'change': 'remove only the CLI failure handler write to an unowned output directory'}


def recheck(repo, root, expected_source):
    require(re.fullmatch('[0-9a-f]{40}', expected_source), 'invalid expected source')
    manifest = inventory(root)
    report = read_json(root / 'REGRESSION_RESULT.json')
    require(report['status'] == 'PASS_FIXED_HOST_OWNER_REGRESSION', 'incomplete regression')
    require(report['source_commit'] == expected_source, 'source mismatch')
    require((root / 'source_commit.txt').read_text().strip() == expected_source, 'source file mismatch')
    require((root / 'gate.exit').read_text().strip() == '0', 'failed gate')
    sys.path.insert(0, str(repo / 'chisel/continuous_prefill/scripts'))
    from verify_host_block_gate import verify
    from audit_owner_block_abi import audit
    from seal_owner_regression import compare_csv
    from run_owner_lifecycle_gate import verify as verify_lifecycle

    profile = report['profile']
    plans = {'tiny': [('base17', 17, 1), ('relocated32', 32, 1),
                     ('relocated33', 33, 1), ('high48_33', 33, 1),
                     ('layers2_17', 17, 2), ('layers3_33', 33, 3)],
             'real-cross': [('real17', 17, 1)]}
    require(profile in plans, 'unsupported profile')
    require(set(report['cases']) == {p[0] for p in plans[profile]}, 'incorrect case inventory')
    hidden, ffn = (64, 128) if profile == 'tiny' else (1536, 8960)
    numerical = {}
    source_checks = {}
    cli_changes = {}
    for name, tokens, layers in plans[profile]:
        out = root / name
        require((out / 'gate.exit').read_text().strip() == '0', 'case failed')
        result = verify(out, False)
        public = audit(out)
        count = compare_csv(out)
        require((result['shape']['H'], result['shape']['F'], result['tokens'], result.get('layers', 1))
                == (hidden, ffn, tokens, layers), 'case geometry mismatch')
        require(count == result['checked_fp32'] == public['checked_fp32'], 'comparison count disagreement')
        saved = read_json(out / 'RESULT.json')
        require(all(saved.get(k) == v for k, v in result.items()), 'stored numerical result changed')
        for relative, digest in read_json(out / 'sources.sha256.json').items():
            rel = PurePosixPath(relative)
            require(not rel.is_absolute() and '..' not in rel.parts, 'unsafe source path')
            # Replay records the actual newly linked harness separately while
            # preserving the original hardware identity. Check both on disk.
            source_compatibility(repo, relative, digest, cli_changes)
            source_checks[relative] = digest
        numerical[name] = {'tokens': tokens, 'layers': layers, 'checked_fp32': count,
                           'commands': result['commands'], 'bit_differences': 0,
                           'generated_rtl_sha256': result['generated_rtl_sha256']}

    faults = []
    repeats = []
    if profile == 'tiny':
        fixture = read_json(root / 'base17/fixture/manifest.json')
        expected_groups = {
            'repeat': {('repeat', 0)},
            'fault_metadata': {(m, p) for m in ('command-read-error', 'descriptor-read-error') for p in range(21)},
            'fault_payload': {(m, p) for m in ('read-error', 'write-error', 'last-write-error')
                              for p in range(21) if p not in (10, 11)}}
        for group, expected in expected_groups.items():
            parent = root / group
            require((parent / 'gate.exit').read_text().strip() == '0', 'lifecycle group failed')
            saved = read_json(parent / 'RESULT.json')
            require(saved['status'] == 'PASS_HOST_OWNER_LIFECYCLE_SUITE', 'lifecycle group not complete')
            for path, digest in saved['frozen_dut_sources'].items():
                require(sha(repo / path) == digest, 'lifecycle DUT source drift')
            dirs = sorted(p for p in parent.iterdir() if p.is_dir())
            require(len(dirs) == len(saved['cases']) == len(expected), 'missing lifecycle cases')
            seen = set()
            for directory, original in zip(dirs, saved['cases']):
                mode, pc = original['mode'], original['fault_pc']
                key = mode, 0 if pc is None else pc
                require(key in expected and key not in seen, 'duplicate or unexpected lifecycle case')
                seen.add(key)
                actual = verify_lifecycle(directory, fixture, *key)
                require(actual == original == read_json(directory / 'RESULT.json'), 'lifecycle result mismatch')
                summary = {'mode': mode, 'pc': pc, 'checked_fp32': actual['checked_fp32'],
                           'reset_between_requests': actual['reset_between_requests']}
                (repeats if mode == 'repeat' else faults).append(summary)
            require(seen == expected, 'missing required fault site')
        require(len(faults) == 99 and len(repeats) == 1, 'fixed scope incomplete')
    else:
        require(report['fault_recoveries'] == [] and report['no_reset_repeats'] == [], 'real scope overstated')
    return {'status': 'PASS_READONLY_PUBLISHED_OWNER_REGRESSION_RECHECK',
            'profile': profile, 'tested_source': expected_source, 'published_files': len(manifest) + 1,
            'source_files_verified': len(source_checks), 'numerical_cases': numerical,
            'post_run_cli_preservation_changes': cli_changes,
            'fault_recoveries': faults, 'no_reset_repeats': repeats,
            'rtl_rerun': False, 'compiled_library_bytes_rechecked': False,
            'note': 'Archived library digests retain provenance. Absent CI libraries are not claimed rechecked.',
            'official_weights': False, 'q1024_full_network': False, 'dc': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        require(not args.output.exists(), 'refuse to overwrite earlier audit')
        result = recheck(args.repo.resolve(), args.evidence.resolve(), args.source)
        with args.output.open('x') as stream:
            json.dump(result, stream, indent=2);stream.write('\n')
        print(json.dumps(result, indent=2))
    except (ValueError, OSError, KeyError, TypeError) as error:
        raise SystemExit('PUBLICATION_RECHECK_REJECTED: ' + str(error))
