"""Verify the pinned public source subset without importing or executing it.

Run this snapshot's script from outside the separately checked-out source tree.
This is not model, numerical, native-library, Git-HEAD or runtime qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys

SOURCE_COMMIT = '1ea9b511fc982b2d928472b0dadd9f794c1c20d8'
SOURCE_TREE = 'e6af2af0b35b7c12907a1ff0b66dd416f0e90571'
PINS_SHA256 = '30dd9d7e91a78c25cf9b7bd268f35d57bee450d0f8e2a4e9a9b99dceb3e3fb18'
SOURCE_COUNT = 111
MAX_SOURCE_BYTES = 16 << 20
ALLOWED_SUFFIXES = {'.py', '.scala', '.cpp', '.c', '.h', '.json', '.txt', '.sv'}
# Existing public tensor-header metadata only; never a tensor payload or library.
METADATA_HEADERS = {'config/upstream/weight_headers/qwen3_5_0p8b/model.safetensors-00001-of-00001.safetensors.header.bin'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def validate_manifest(manifest):
    require(type(manifest) is dict, 'manifest must be an object')
    require(set(manifest) == {'schema_version', 'source_commit', 'source_tree',
                             'scope', 'source_count', 'files'}, 'manifest fields changed')
    require(type(manifest['schema_version']) is int and manifest['schema_version'] == 1,
            'manifest schema')
    require(manifest['source_commit'] == SOURCE_COMMIT and manifest['source_tree'] == SOURCE_TREE,
            'source provenance changed')
    require(type(manifest['scope']) is str and bool(manifest['scope']), 'manifest scope')
    count = manifest['source_count']
    files = manifest['files']
    require(type(count) is int and 0 < count <= 2048 and type(files) is dict and len(files) == count,
            'source inventory count')
    for name, pin in files.items():
        require(type(name) is str and bool(name) and '\\' not in name,
                'source path must be repository relative')
        path = PurePosixPath(name)
        require(not path.is_absolute() and str(path) == name and '..' not in path.parts
                and all(part not in ('.', '..', '') for part in path.parts)
                and not any(ord(c) < 32 for c in name), 'noncanonical source path')
        require(path.suffix in ALLOWED_SUFFIXES or name in METADATA_HEADERS,
                'not an allowed source or metadata path')
        require(type(pin) is dict and set(pin) == {'bytes', 'sha256', 'git_blob_sha', 'git_mode'},
                'source pin fields changed')
        require(type(pin['bytes']) is int and 0 <= pin['bytes'] <= MAX_SOURCE_BYTES,
                'source byte count')
        require(type(pin['sha256']) is str and re.fullmatch('[0-9a-f]{64}', pin['sha256']) is not None,
                'source SHA256 format')
        require(type(pin['git_blob_sha']) is str and re.fullmatch('[0-9a-f]{40}', pin['git_blob_sha']) is not None,
                'Git blob SHA format')
        require(pin['git_mode'] in ('100644', '100755'), 'source Git mode')
    return manifest


def load_manifest(path):
    raw = Path(path).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == PINS_SHA256, 'published source-pin manifest changed')
    manifest = validate_manifest(json.loads(raw, object_pairs_hook=unique_object))
    require(manifest['source_count'] == SOURCE_COUNT, 'published source count changed')
    return manifest


def verify_sources(source_root, manifest):
    """Check selected file contents only; never import model modules or run Git."""
    validate_manifest(manifest)
    root = Path(source_root)
    require(not root.is_symlink() and root.is_dir(), 'source root must be a real directory')
    root = root.resolve(strict=True)
    for name, pin in sorted(manifest['files'].items()):
        path = root
        for component in PurePosixPath(name).parts:
            path = path / component
            require(not path.is_symlink(), 'source path alias: ' + name)
        require(path.is_file(), 'missing selected source: ' + name)
        require(path.resolve(strict=True).is_relative_to(root), 'source path escaped root')
        require(path.stat().st_size == pin['bytes'], 'source size changed: ' + name)
        raw = path.read_bytes()
        require(len(raw) == pin['bytes'], 'source changed during read: ' + name)
        require(hashlib.sha256(raw).hexdigest() == pin['sha256'], 'source hash changed: ' + name)
        blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        require(blob == pin['git_blob_sha'], 'Git blob hash changed: ' + name)
    return {'status': 'PASS_SELECTED_PUBLIC_SOURCE_BYTES_ONLY',
            'source_commit_provenance': SOURCE_COMMIT, 'source_tree_provenance': SOURCE_TREE,
            'selected_files_verified': len(manifest['files']), 'git_head_checked': False,
            'full_repository_checked': False, 'runtime_or_native_checked': False,
            'model_executed': False, 'numerical_acceptance': None, 'rtl_executed': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--pins', type=Path, default=Path(__file__).with_name('SOURCE_PINS.json'))
    args = parser.parse_args(argv)
    try:
        result = verify_sources(args.source_root, load_manifest(args.pins))
    except (ValueError, OSError, UnicodeError) as error:
        print(json.dumps({'status': 'FAIL_SOURCE_CHECK', 'error': str(error)}), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
