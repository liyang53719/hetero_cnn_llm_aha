#!/usr/bin/env python3
"""Reconstruct the fixed offline verifier input view. Source files are only bytes.

No Git, subprocess, network, numerical imports, extraction, or runtime execution.
The 465-file content proof does not authenticate Git HEAD or the rest of a tree.
Requires POSIX directory-fd and O_NOFOLLOW support; unsupported hosts fail closed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat

HERE = Path(__file__).absolute().parent
COMMIT = '8ba333c76722b47b681be88612b1c6987e34a5f4'
CONTRACT = 'candidates/qwen2_resident_matrix/portable_same_host_m128_launch/input-contract.json'
CONTRACT_SHA = '2ac3f216a7e5566fc7dad84c4050502c8afd99d82d9d33e05625bc6f774f1e6c'
MAP_SHA = 'cded2ae582a6387cddce8c8bbc38c2e1df46a4038c1d3460bf7566f3273e5228'
PINS_SHA = '34cd14b4a42f93266f7f6d516bafc156b8c84d88a5efbd5058434c02d7235c9d'
MAX_FILE = 1024 * 1024
MAX_TOTAL = 16 * 1024 * 1024
COUNT = 465


class SourceViewError(ValueError):
    pass


def need(condition, code):
    if not condition:
        raise SourceViewError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def strict(raw):
    need(type(raw) is bytes and len(raw) <= MAX_FILE, 'JSON_SIZE')
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'JSON_DUPLICATE')
            result[key] = value
        return result
    def nonfinite(_):
        raise SourceViewError('JSON_NONFINITE')
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=nonfinite)
        encoded(value)
        return value
    except (UnicodeError, ValueError, TypeError, RecursionError) as error:
        if isinstance(error, SourceViewError):
            raise
        raise SourceViewError('JSON_INVALID') from None


def relative(name):
    need(type(name) is str and 0 < len(name) <= 4096 and
         all(0 < len(part) <= 255 and part not in ('.', '..') and
             re.fullmatch(r'[A-Za-z0-9_.-]+', part) for part in name.split('/')), 'SOURCE_PATH')
    return name.split('/')


def source_map(value, count):
    need(type(value) is dict and len(value) == count, 'SOURCE_COUNT')
    for name, digest in value.items():
        parts = relative(name)
        need(type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest), 'SOURCE_DIGEST')
        need(not any('/'.join(parts[:i]) in value for i in range(1, len(parts))), 'SOURCE_PATH_COLLISION')


def signature(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def dir_identity(value):
    return (value.st_dev, value.st_ino, value.st_mode)


def directory_flags():
    need(os.name == 'posix' and hasattr(os, 'O_NOFOLLOW') and hasattr(os, 'O_DIRECTORY') and
         os.open in os.supports_dir_fd and os.stat in os.supports_dir_fd, 'UNSUPPORTED_HOST')
    return os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY


def absolute(path):
    # Reject traversal even when abspath could normalize it harmlessly.
    value = os.fspath(path)
    need(value and '\x00' not in value and '\\' not in value and
         all(part not in ('.', '..') for part in value.split('/')), 'ROOT_PATH')
    return Path(os.path.abspath(value))


def open_directory(path):
    """Open each absolute directory component without following aliases."""
    path = absolute(path)
    fd = os.open('/', directory_flags())
    try:
        for part in path.parts[1:]:
            next_fd = os.open(part, directory_flags(), dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def relative_directory(root_fd, parts, create=False):
    fd = os.dup(root_fd)
    trail = []
    try:
        for part in parts:
            if create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(part, directory_flags(), dir_fd=fd)
            trail.append(dir_identity(os.fstat(child)))
            os.close(fd)
            fd = child
        return fd, tuple(trail)
    except BaseException:
        os.close(fd)
        raise


def read_checked(root_fd, name, limit=MAX_FILE):
    """Bounded single-link file read, anchored to a non-symlink directory fd."""
    parts = relative(name)
    parent_fd, trail = relative_directory(root_fd, parts[:-1])
    fd = None
    try:
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent_fd)
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
             0 <= before.st_size <= limit, 'FILE_TYPE_SIZE')
        chunks = []
        left = before.st_size
        while left:
            chunk = os.read(fd, min(left, 65536))
            need(bool(chunk), 'FILE_SHORT_READ')
            chunks.append(chunk)
            left -= len(chunk)
        need(not os.read(fd, 1), 'FILE_GREW')
        after = os.fstat(fd)
        named = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
        need(signature(before) == signature(after) == signature(named), 'FILE_DRIFT')
        # Rewalk from root to detect renamed/replaced ancestors during this read.
        check_fd, check_trail = relative_directory(root_fd, parts[:-1])
        try:
            need(trail == check_trail and signature(os.stat(parts[-1], dir_fd=check_fd,
                 follow_symlinks=False)) == signature(before), 'FILE_PATH_DRIFT')
        finally:
            os.close(check_fd)
        return b''.join(chunks), (trail, signature(before))
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent_fd)


def write_exclusive(root_fd, name, raw):
    parts = relative(name)
    parent_fd, _ = relative_directory(root_fd, parts[:-1], create=True)
    try:
        fd = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=parent_fd)
        try:
            need(stat.S_ISREG(os.fstat(fd).st_mode) and os.fstat(fd).st_nlink == 1, 'OUTPUT_TYPE')
            position = 0
            while position < len(raw):
                count = os.write(fd, raw[position:])
                need(count > 0, 'OUTPUT_SHORT_WRITE')
                position += count
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


def load_pins(package=HERE):
    root_fd = open_directory(package)
    try:
        raw, _ = read_checked(root_fd, 'pins.json')
        need(sha(raw) == PINS_SHA, 'PACKAGE_PINS')
        pins = strict(raw)
        map_raw, _ = read_checked(root_fd, 'FULL_SOURCE_HASHES.json')
        need(sha(map_raw) == MAP_SHA, 'PACKAGE_MAP_PIN')
        full = strict(map_raw)
        source_map(full, COUNT)
        need(encoded(full) == map_raw and full.get(CONTRACT) == CONTRACT_SHA, 'PACKAGE_MAP')
        return pins, full, map_raw
    finally:
        os.close(root_fd)


def derive_map(contract_raw):
    need(sha(contract_raw) == CONTRACT_SHA, 'INPUT_CONTRACT_PIN')
    contract = strict(contract_raw)
    need(type(contract) is dict and set(contract) ==
         {'budgets', 'composed_sources', 'inputs', 'profile', 'schema', 'workflow'}, 'CONTRACT_FIELDS')
    need(type(contract['schema']) is int and contract['schema'] == 1 and
         contract['profile'] == 'qwen2-fresh-same-host-m128-combined-v1', 'CONTRACT_IDENTITY')
    source_map(contract['inputs'], COUNT - 1)
    need(CONTRACT not in contract['inputs'], 'CONTRACT_SELF_REFERENCE')
    full = {**contract['inputs'], CONTRACT: sha(contract_raw)}
    source_map(full, COUNT)
    need(sha(encoded(full)) == MAP_SHA, 'DERIVED_MAP_PIN')
    return full


def build(checkout, output, package=HERE):
    checkout = absolute(checkout)
    output = absolute(output)
    need(checkout != output and checkout not in output.parents and output not in checkout.parents,
         'OUTPUT_CHECKOUT_OVERLAP')
    need(output.name not in ('', '.', '..'), 'OUTPUT_PATH')
    pins, full, map_raw = load_pins(package)
    source_fd = open_directory(checkout)
    parent_fd = None
    out_fd = None
    root_identity = dir_identity(os.fstat(source_fd))
    try:
        parent_fd = open_directory(output.parent)
        # Existing output, including a symlink or dangling alias, is never reused.
        try:
            os.stat(output.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise SourceViewError('OUTPUT_EXISTS')
        contract_raw, _ = read_checked(source_fd, CONTRACT)
        need(derive_map(contract_raw) == full, 'CONTRACT_MAP_MISMATCH')
        # Validate everything before creating output; only the authenticated closure is read.
        snapshots = {}
        total = 0
        for name, digest in sorted(full.items()):
            raw, snapshot = read_checked(source_fd, name)
            need(sha(raw) == digest, 'SOURCE_HASH')
            total += len(raw)
            need(total <= MAX_TOTAL, 'SOURCE_TOTAL_SIZE')
            snapshots[name] = snapshot
        os.mkdir(output.name, mode=0o700, dir_fd=parent_fd)
        out_fd = os.open(output.name, directory_flags(), dir_fd=parent_fd)
        need(stat.S_IMODE(os.fstat(out_fd).st_mode) == 0o700, 'OUTPUT_NOT_PRIVATE')
        for name, digest in sorted(full.items()):
            raw, snapshot = read_checked(source_fd, name)
            need(snapshot == snapshots[name] and sha(raw) == digest, 'SOURCE_DRIFT')
            write_exclusive(out_fd, 'source/' + name, raw)
        # Recheck after the final copy so a changed earlier source cannot pass.
        for name, digest in sorted(full.items()):
            raw, snapshot = read_checked(source_fd, name)
            need(snapshot == snapshots[name] and sha(raw) == digest, 'SOURCE_DRIFT')
            copied, _ = read_checked(out_fd, 'source/' + name)
            need(sha(copied) == digest, 'OUTPUT_HASH')
        current_fd = open_directory(checkout)
        try:
            need(dir_identity(os.fstat(current_fd)) == root_identity, 'CHECKOUT_ROOT_DRIFT')
        finally:
            os.close(current_fd)
        current_parent_fd = open_directory(output.parent)
        try:
            need(dir_identity(os.fstat(current_parent_fd)) == dir_identity(os.fstat(parent_fd)),
                 'OUTPUT_PARENT_DRIFT')
        finally:
            os.close(current_parent_fd)
        need(dir_identity(os.stat(output.name, dir_fd=parent_fd, follow_symlinks=False)) ==
             dir_identity(os.fstat(out_fd)), 'OUTPUT_ROOT_DRIFT')
        # The verifier's required map is the final completion marker.
        write_exclusive(out_fd, 'FULL_SOURCE_HASHES.json', map_raw)
        os.fsync(out_fd)
        return dict(schema=1, status='PINNED_SOURCE_VIEW_BUILT', commit=COMMIT,
                    source_files=COUNT, source_bytes=total, source_map_sha256=MAP_SHA,
                    checkout_content_authenticated=True, git_head_authenticated=False,
                    runtime_executed=False, github_metadata_authenticated=False)
    finally:
        if out_fd is not None:
            os.close(out_fd)
        if parent_fd is not None:
            os.close(parent_fd)
        os.close(source_fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkout', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    try:
        print(encoded(build(args.checkout, args.out)).decode(), end='')
    except (SourceViewError, OSError) as error:
        parser.exit(2, f'source-view rejected: {error}\n')


if __name__ == '__main__':
    main()
