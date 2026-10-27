#!/usr/bin/env python3
"""Restore one exact source set only. Never compiles, imports or runs target code."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath

PREFIX = 'candidates/unified_runtime_norm_boundary'

def require(ok, message):
    if not ok:
        raise ValueError(message)

def safe_source(repo, relative):
    p = PurePosixPath(relative)
    require(not p.is_absolute() and '..' not in p.parts and str(p) == relative, 'unsafe source path')
    current = repo
    for part in p.parts:
        current = current / part
        require(not current.is_symlink(), 'symlink source rejected')
    require(current.is_file(), 'source missing')
    return current

def restore(repo, stage, out):
    require(not repo.is_symlink(), 'repository symlink rejected')
    repo = repo.resolve(strict=True)
    require(repo.is_dir(), 'repository must be a directory')
    require(not out.exists() and not out.is_symlink(), 'output already exists')
    require(not any(p.is_symlink() for p in out.absolute().parents), 'output parent symlink rejected')
    destination = out.resolve(strict=False)
    require(not destination.is_relative_to(repo), 'output must be outside the source repository')
    selections = json.loads(safe_source(repo, PREFIX + '/SOURCE_SELECTIONS.json').read_text())
    dependencies = json.loads(safe_source(repo, PREFIX + '/SOURCE_DEPENDENCY_MAP.json').read_text())
    if stage in ('norm14', 'boundary4'):
        pins = {r['path']: r for r in selections['unique_sources']}
        rows = [dict(pins[p], repository_path=PREFIX + '/' + p) for p in selections['ordered_compile_selections'][stage]]
    else:
        key = {'prefix4': 'prefix17', 'gdn12': 'gdn41_minus_identical_state4'}[stage]
        rows = []
        for row in next(g for g in dependencies['additional_dependency_groups'] if g['role'] == key)['input_source_pins']:
            if 'available_public_reference' in row:
                relative = row['available_public_reference']['path']
            else:
                relative = PREFIX + '/' + row['bundled_reproduction_path']
            rows.append(dict(row, repository_path=relative))
    seen = set()
    payloads = []
    for row in rows:
        source = safe_source(repo, row['repository_path'])
        body = source.read_bytes()
        require(len(body) == row['bytes'] and hashlib.sha256(body).hexdigest() == row['sha256'], 'source identity mismatch')
        require(source.name not in seen, 'duplicate source basename in stage')
        seen.add(source.name)
        payloads.append((source.name, body, row['sha256']))
    destination.mkdir(parents=True, exist_ok=False)
    for name, body, _ in payloads:
        (destination / name).write_bytes(body)
    return {'stage': stage, 'sources': [{'name': n, 'bytes': len(b), 'sha256': h} for n, b, h in payloads], 'target_executed': False, 'class_or_runtime_restored': False}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--stage', choices=['norm14', 'boundary4', 'prefix4', 'gdn12'], required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(restore(args.repo, args.stage, args.out), indent=2))

if __name__ == '__main__':
    main()
