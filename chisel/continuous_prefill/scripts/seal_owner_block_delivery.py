#!/usr/bin/env python3
"""Seal completed original-opcode owner proofs, never manufacture DUT outputs.

Requires both tiny16 and real16 successful runs, immutable source identities,
all actual/reference tensors, and complete element-by-element CSV. Publication
is an exact allowlist into a new directory; no prior evidence is overwritten.
"""
from __future__ import annotations
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import struct
import subprocess
import sys


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_safe(base: Path, relative: str) -> bytes:
    rel = PurePosixPath(relative)
    require(not rel.is_absolute() and '..' not in rel.parts, 'unsafe artifact path')
    path = base / str(rel)
    require(path.is_file() and not path.is_symlink(), 'missing or symlink artifact: ' + relative)
    require(path.resolve().is_relative_to(base.resolve()), 'artifact escapes directory')
    return path.read_bytes()


def compare_csv(out: Path) -> int:
    manifest = json.loads(read_safe(out, 'fixture/manifest.json'))
    path = out / 'all_owner_elements.csv.gz'
    require(path.is_file() and not path.is_symlink(), 'missing full comparison CSV')
    count = 0
    with gzip.open(path, 'rt', newline='') as stream:
        reader = csv.reader(stream)
        require(next(reader, None) == ['pc', 'tensor', 'index', 'actual_hex', 'reference_hex'], 'CSV header')
        for op in manifest['schedule']:
            for name in op['outputs']:
                actual = read_safe(out, f'tensors/{name}_actual.f32le')
                reference = read_safe(out, f'tensors/{name}_reference.f32le')
                words = manifest['tensors'][name]['words']
                require(len(actual) == len(reference) == 4 * words, 'CSV source length')
                for index, ((a,), (b,)) in enumerate(zip(struct.iter_unpack('<I', actual), struct.iter_unpack('<I', reference))):
                    expected = [str(op['pc']), name, str(index), f'{a:08x}', f'{b:08x}']
                    require(next(reader, None) == expected, 'CSV missing, reordered or changed row ' + str(count))
                    require(a == b, 'independent binary mismatch')
                    count += 1
        require(next(reader, None) is None, 'extra CSV rows')
    return count


def source_identity(repo: Path, out: Path, commit: str) -> dict[str, str]:
    require(bool(re.fullmatch('[0-9a-f]{40}', commit)), 'invalid source commit')
    require(read_safe(out, 'source_base_commit.txt').decode().strip() == commit, 'test/source commit mismatch')
    recorded = json.loads(read_safe(out, 'sources.sha256.json'))
    required = [
        'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/' + n + '.scala'
        for n in ['HostBlockCommands', 'HostBlockTop', 'QwenOwnerProtocol', 'Qwen2Block', 'RetainedIdma', 'RetainedMatrix']
    ] + ['chisel/continuous_prefill/tests/host_block_commands.cpp']
    require(all(p in recorded for p in required), 'missing critical tested source')
    require(len(recorded) >= len(required), 'empty source manifest')
    identity = {}
    for rel, digest in recorded.items():
        require(isinstance(digest, str) and bool(re.fullmatch('[0-9a-f]{64}', digest)), 'malformed source digest')
        current = read_safe(repo, rel)
        original = subprocess.check_output(['git', '-C', str(repo), 'show', f'{commit}:{rel}'])
        require(sha(original) == digest == sha(current), 'tested source drift: ' + rel)
        identity[rel] = digest
    # These public parsers/configurations are outside the hardware manifest.
    # Bind them too instead of silently interpreting bytes with changed rules.
    for rel in ['src/heteronpu/command.py', 'src/heteronpu/descriptor_chain.py',
                'src/heteronpu/l9_transport_contract.py', 'config/descriptor_public_encoding.json']:
        current = read_safe(repo, rel)
        original = subprocess.check_output(['git', '-C', str(repo), 'show', f'{commit}:{rel}'])
        require(current == original, 'public ABI source drift: ' + rel)
        identity[rel] = sha(current)
    return identity


def validate_case(repo: Path, out: Path, commit: str, hidden: int, ffn: int) -> dict:
    require(read_safe(out, 'gate.exit').strip() == b'0', 'nonzero gate exit')
    sys.path.insert(0, str(repo / 'chisel/continuous_prefill/scripts'))
    from audit_owner_block_abi import audit
    from verify_host_block_gate import verify
    result = verify(out, False)
    require((result['shape']['H'], result['shape']['F'], result['tokens']) == (hidden, ffn, 16), 'wrong required case geometry')
    abi = audit(out)
    rows = compare_csv(out)
    require(rows == result['checked_fp32'] == abi['checked_fp32'], 'comparison count mismatch')
    saved = json.loads(read_safe(out, 'RESULT.json'))
    require(all(saved.get(k) == v for k, v in result.items()), 'saved result disagrees with independent recheck')
    require(saved.get('full_comparison_sha256') == sha(read_safe(out, 'all_owner_elements.csv.gz')), 'CSV hash mismatch')
    identity = source_identity(repo, out, commit)
    return {'status': result['status'], 'tokens': 16, 'hidden': hidden, 'ffn': ffn,
            'checked_fp32': rows, 'bit_differences': 0, 'commands': 21, 'owner_jobs': 19,
            'source_files_verified': len(identity), 'log_sha256': sha(read_safe(out, 'run.log')),
            'source_identity_sha256': sha(json.dumps(identity, sort_keys=True).encode()),
            'generated_rtl_sha256': result['generated_rtl_sha256'], 'counters': result['counters']}


def publish(repo: Path, artifact: Path, target: Path, commit: str, run: int) -> dict:
    require(run > 0, 'invalid workflow run')
    require(not target.exists(), 'refuse to overwrite prior evidence')
    require(target.resolve().is_relative_to((repo / 'reports/execution').resolve()), 'publication outside reports/execution')
    results = {name: validate_case(repo, artifact / name, commit, h, f)
               for name, h, f in [('tiny16', 64, 128), ('real16', 1536, 8960)]}
    selected: dict[str, bytes] = {}
    essentials = ['run.log', 'gate.exit', 'simulation.exit', 'RESULT.json',
                  'all_owner_elements.csv.gz', 'sources.sha256.json', 'hardfloat.sha256.json',
                  'idma_identity.json', 'source_base_commit.txt', 'build.log',
                  'generated/HostBlockTop.sv', 'generated/SCOPE.json', 'generated/owner_shape.h',
                  'fixture/manifest.json', 'fixture/owner_fixture.h', 'fixture/host_commands.bin', 'fixture/host_descriptors.bin']
    for name in results:
        out = artifact / name
        paths = essentials + [str(p.relative_to(out)) for p in sorted((out / 'tensors').iterdir()) if p.is_file()]
        for extra in ['compile_emit.log', 'compile.log', 'emit.log', 'verification.log', 'idma_verify.log']:
            if (out / extra).is_file():
                paths.append(extra)
        for rel in paths:
            selected[f'{name}/{rel}'] = read_safe(out, rel)
    report = {'schema': 1, 'status': 'PASS_DURABLE_HOST_DRIVEN_OWNER_BLOCK_PROOF',
              'tested_source_commit': commit, 'workflow_run': run, 'cases': results,
              'scope': {'host_driven_21_opcodes': True, 'legacy_block_launch': False,
                        'pinned_idma': True, 'original_matrix': True, 'synthetic_weights': True,
                        'original_gguf_binary_image': False, 'multilayer': False,
                        'q1024_full_network': False, 'dc': False}}
    selected['PUBLICATION_RECHECK.json'] = (json.dumps(report, indent=2) + '\n').encode()
    # Complete validation precedes any destination creation.
    target.mkdir(parents=True)
    for relative, data in selected.items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(data)
    manifest = {relative: sha(data) for relative, data in sorted(selected.items())}
    with (target / 'PUBLISHED_SHA256.json').open('x') as stream:
        json.dump(manifest, stream, indent=2); stream.write('\n')
    for relative, digest in manifest.items():
        require(sha(read_safe(target, relative)) == digest, 'publication byte mismatch')
    report['published_files_including_manifest'] = len(manifest) + 1
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--artifact', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--run', type=int, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(publish(args.repo.resolve(), args.artifact.resolve(), args.output.resolve(), args.source, args.run), indent=2))
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        raise SystemExit('OWNER_PUBLICATION_REJECTED: ' + str(error))
