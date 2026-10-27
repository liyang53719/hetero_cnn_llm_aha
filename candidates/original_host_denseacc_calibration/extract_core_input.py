#!/usr/bin/env python3
"""Extract only the exact, pinned Core from a separately rebuilt public Host high.

No JVM, native target, network, cleanup, or overwrite. --check-only writes nothing.
"""
from pathlib import Path
import argparse, hashlib, json, re
HERE = Path(__file__).resolve().parent
HEADER = re.compile(rb'^  (?:module|extmodule) ([A-Za-z_][A-Za-z0-9_$]*) :')
LIMIT = 8 * 1024 * 1024

def require(value, message):
    if not value:
        raise ValueError(message)

def identity(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

def read_verified_core(parent, pins):
    parent = Path(parent)
    require(parent.is_file() and not parent.is_symlink(), 'regular non-symlink parent required')
    before = parent.stat()
    require(before.st_size == pins['parent']['bytes'], 'parent byte count')
    full = hashlib.sha256()
    core = bytearray()
    active = False
    count = total = 0
    with parent.open('rb') as stream:
        while True:
            line = stream.readline(2 * 1024 * 1024 + 1)
            if not line:
                break
            require(len(line) <= 2 * 1024 * 1024, 'bounded line')
            total += len(line)
            require(total <= pins['parent']['bytes'], 'bounded parent')
            full.update(line)
            match = HEADER.match(line)
            if match:
                active = match[1] == b'Qwen2ContinuousBlock'
                count += int(active)
            if active:
                core.extend(line)
                require(len(core) <= LIMIT, 'bounded Core')
    after = parent.stat()
    fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    require(all(getattr(before, f) == getattr(after, f) for f in fields), 'parent changed')
    require(total == pins['parent']['bytes'] and full.hexdigest() == pins['parent']['sha256'], 'full parent SHA')
    require(count == 1, 'exactly one Core module')
    require(identity(core) == {k: pins['core'][k] for k in ('bytes', 'sha256')}, 'Core bytes/SHA')
    return bytes(core)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('parent_high')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check-only', action='store_true')
    group.add_argument('--output', type=Path)
    args = parser.parse_args()
    pins = json.loads((HERE / 'INPUT_PINS.json').read_text())
    body = read_verified_core(args.parent_high, pins)
    if args.output is not None:
        require(not args.output.exists() and not args.output.is_symlink(), 'fresh output required')
        require(args.output.name == pins['core']['filename'], 'fixed Core filename')
        with args.output.open('xb') as stream:
            stream.write(body)
    print(json.dumps({'status': 'VERIFIED_EXACT_PUBLIC_RECIPE_CORE_INPUT', **identity(body), 'written': args.output is not None}))

if __name__ == '__main__':
    main()
