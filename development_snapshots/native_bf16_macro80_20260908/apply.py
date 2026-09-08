#!/usr/bin/env python3
"""Install the exact locally tested source delta. No cleanup, no force push.

The chunk files are transport only. The decoded patch becomes normal readable
Scala/Python/C++ source in the existing main branch. part00.b64 is an obsolete,
unreferenced transfer attempt and is deliberately not read by this program.
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zlib

EXPECTED = '570764ca53151411edfc7b0c004d531087bda09c2bdfa1be6ddcc9b56df9f45f'
ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def git(*args, data=None):
    return subprocess.check_output(['git', *args], cwd=ROOT, input=data)


def require(ok, text):
    if not ok:
        raise RuntimeError(text)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    encoded = ''.join((HERE / f'chunk{i:02d}.b64').read_text().strip() for i in range(14))
    payload = zlib.decompress(base64.b64decode(encoded, validate=True))
    require(sha(payload) == EXPECTED, 'TRANSPORT_HASH_MISMATCH')
    bundle = json.loads(payload)
    require(bundle['schema'] == 1 and len(bundle['files']) == 16, 'WRONG_PAYLOAD_SCHEMA')
    git('merge-base', '--is-ancestor', bundle['upstream'], 'HEAD')
    require(not git('status', '--porcelain', '--untracked-files=no').strip(), 'TRACKED_CHECKOUT_NOT_CLEAN')
    skipped = []
    for name, identity in bundle['files'].items():
        p = Path(name)
        require(name.startswith('chisel/continuous_prefill/') and '..' not in p.parts and p.suffix in {'.scala', '.cpp', '.py', '.sh'}, 'PATH_NOT_SOURCE:' + name)
        file = ROOT / p
        require(not file.is_symlink(), 'SYMLINK:' + name)
        actual = sha(file.read_bytes()) if file.exists() else None
        if actual == identity['after']:
            skipped.append(name)
        else:
            require(actual == identity['before'], 'CONCURRENT_SOURCE_CHANGE:' + name)
    args = ['apply'] + ['--exclude=' + n for n in skipped]
    raw_patch = bundle['patch'].encode()
    git(*args, '--check', '-', data=raw_patch)
    git(*args, '-', data=raw_patch)
    for name, identity in bundle['files'].items():
        require(sha((ROOT / name).read_bytes()) == identity['after'], 'POST_APPLY_HASH:' + name)
    changed = set(git('diff', '--name-only').decode().splitlines())
    require(changed <= set(bundle['files']), 'UNEXPECTED_CHANGE')
    git('add', '--', *bundle['files'])
    git('diff', '--cached', '--check')
    git('config', 'user.name', 'heteronpu-source-verified')
    git('config', 'user.email', 'heteronpu-verified@users.noreply.github.com')
    if git('diff', '--cached', '--name-only').strip():
        git('commit', '-m', 'feat(chisel): native BF16 Dense weights and five-microtile token reuse; component verified [skip ci]')
        git('push', 'origin', 'HEAD:main')
    commit = git('rev-parse', 'HEAD').decode().strip()
    git('fetch', '--no-tags', 'origin', 'main')
    git('merge-base', '--is-ancestor', commit, 'origin/main')
    for name, identity in bundle['files'].items():
        require(sha(git('show', 'origin/main:' + name)) == identity['after'], 'REMOTE_BYTE_MISMATCH:' + name)
    report = dict(status='SOURCE_APPLIED_AND_REMOTE_VERIFIED', commit=commit, files=bundle['files'], payload_sha256=EXPECTED,
                  scope='Source publication, NOT a whole-request performance or numerical completion certificate.')
    print(json.dumps(report, indent=2))
    if 'GITHUB_OUTPUT' in os.environ:
        with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
            output.write('commit=' + commit + '\n')


if __name__ == '__main__':
    main()
