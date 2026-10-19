"""Pinned same-buffer cold entry. No compiler, subprocess, model, or network API."""
import hashlib
import json
import os
from pathlib import Path
import stat

MANIFEST_PIN = (4472, '40ebb6c1957941b90906c4dc5c0d561816fa413aa5a4431a1bd2d191f39dc5b1')
TEST_PIN = (15093, '99dd0a09ebb0f39bdd1a1ed7bedb956c1a72296610092294604facbc3a695634')


def checked(path, expected):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('COLD_PATH')
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError('COLD_SYMLINK')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size != expected[0]:
            raise ValueError('COLD_SIZE')
        chunks = []
        remaining = expected[0] + 1
        while remaining:
            block = os.read(fd, min(65536, remaining))
            if not block:
                break
            chunks.append(block)
            remaining -= len(block)
        raw = b''.join(chunks)
        after = os.fstat(fd)
        keys = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        if any(getattr(before, key) != getattr(after, key) for key in keys):
            raise ValueError('COLD_DRIFT')
        if len(raw) != expected[0] or hashlib.sha256(raw).hexdigest() != expected[1]:
            raise ValueError('COLD_HASH')
        return raw
    finally:
        os.close(fd)


def run(root):
    root = Path(root).absolute()
    manifest_raw = checked(root / 'PRODUCTION_MANIFEST.json', MANIFEST_PIN)
    manifest = json.loads(manifest_raw)
    if manifest['scope'] != 'SOURCE_ONLY_NOT_COMPILED_OR_RUN' or len(manifest['files']) != 28:
        raise ValueError('COLD_SCOPE')
    source = {}
    for name, record in manifest['files'].items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or not name.startswith('bridge/'):
            raise ValueError('COLD_MEMBER')
        source[name] = checked(root / relative, (record['bytes'], record['sha256']))
    path = root / 'test_pc01_cold.py'
    raw = checked(path, TEST_PIN)
    scope = {'__name__': 'pc01_cold_checked', '__file__': str(path)}
    exec(compile(raw, str(path), 'exec'), scope)
    return scope['run'](source, manifest)
