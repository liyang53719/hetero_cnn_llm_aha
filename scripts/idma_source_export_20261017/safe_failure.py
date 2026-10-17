#!/usr/bin/env python3
"""Bounded, fail-closed projection of a private receipt; never print raw errors.
Cleanup flags describe recorded stages only, not proof validation by this tool
and not global process absence after an interrupted/unrecorded stage.
"""
import argparse
import json
import os
import re
import signal
import stat
import time

MAX_BYTES = 4 * 1024 * 1024
MAX_STAGES = 256
MAX_OUTPUT = 128 * 1024
WALL_SECONDS = 5
SCOPE = 'ANCHORED_ORIGINAL_GROUP_AND_OBSERVED_IDENTITIES_ONLY'
CATEGORIES = frozenset(('timeout', 'interrupted', 'resource_limit', 'command_failed',
                        'validation_failed', 'cleanup_failed', 'internal_error'))
HASH_KEYS = ('python_sha256', 'bender_sha256', 'uv_sha256', 'verilator_sha256', 'manifest_sha256')
STATUSES = frozenset(('IN_PROGRESS', 'FAILED', 'PASS_SOURCE_EXPORT_ONLY'))


def fallback(state):
    return {'schema': 1, 'receipt_state': state, 'status': 'UNKNOWN',
            'status_scope': 'private_export_receipt_only_not_workflow_outcome',
            'error_category': 'unknown_error', 'hashes': {}, 'stages': [],
            'cleanup_interpretation': 'recorded_stages_only_not_global_absence',
            'global_cleanup_verified': False}


def category(value, raw_error=None):
    if isinstance(value, str) and value in CATEGORIES:
        return value
    if value is None and raw_error is None:
        return 'none_recorded'
    return 'unknown_error'


def valid_hash(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def project(receipt):
    if type(receipt) is not dict or type(receipt.get('stages')) is not list:
        return fallback('invalid')
    if len(receipt['stages']) > MAX_STAGES or any(type(s) is not dict for s in receipt['stages']):
        return fallback('invalid')
    result = fallback('readable')
    status = receipt.get('status')
    result['status'] = status if isinstance(status, str) and status in STATUSES else 'UNKNOWN'
    result['error_category'] = category(receipt.get('error_category'), receipt.get('error'))
    result['hashes'] = {k: receipt[k] for k in HASH_KEYS if valid_hash(receipt.get(k))}
    for index, stage in enumerate(receipt['stages']):
        code = stage.get('exit')
        scope = stage.get('cleanup_scope')
        exact_scope = isinstance(scope, str) and scope == SCOPE
        row = {'index': index, 'exit': code if type(code) is int and -255 <= code <= 255 else None,
               'error_category': category(stage.get('error_category'), stage.get('error')),
               'cleanup_scope': SCOPE if exact_scope else 'unverified_scope',
               'cleanup_verified': exact_scope and stage.get('cleanup_complete') is True}
        for key in ('stdout_sha256', 'stderr_sha256'):
            if valid_hash(stage.get(key)):
                row[key] = stage[key]
        for key in ('stdout_bytes','stderr_bytes','peak_sampled_tree_bytes','tree_limit_bytes','file_hard_limit_bytes'):
            value=stage.get(key)
            if type(value) is int and 0<=value<=2**40:row[key]=value
        result['stages'].append(row)
    return result


def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('duplicate key')
        obj[key] = value
    return obj


def read_receipt(path):
    # No FIFO/device blocking and no final-component symlink traversal.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            raise ValueError('unsupported receipt')
        chunks = []
        size = 0
        while size <= MAX_BYTES:
            chunk = os.read(fd, min(65536, MAX_BYTES + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
        if size > MAX_BYTES:
            raise ValueError('oversized receipt')
        return json.loads(b''.join(chunks), object_pairs_hook=unique_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))
    finally:
        os.close(fd)


def emit(receipt_path, output_path):
    if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
        return 2  # Never replace another operation's deadline.
    stop = time.monotonic() + WALL_SECONDS
    def expired(signum, frame):
        raise TimeoutError('summary deadline')
    previous = signal.signal(signal.SIGALRM, expired)
    try:
        # Reserve output time within the single five-second summary deadline.
        signal.setitimer(signal.ITIMER_REAL, max(.001, stop - time.monotonic() - 1))
        try:
            result = project(read_receipt(receipt_path))
        except FileNotFoundError:
            result = fallback('missing')
        except TimeoutError:
            result = fallback('read_timeout')
        except (OSError, ValueError, TypeError, RecursionError, OverflowError):
            result = fallback('invalid')
        remaining = stop - time.monotonic()
        if remaining <= 0:
            return 2
        signal.setitimer(signal.ITIMER_REAL, remaining)
        data = (json.dumps(result, sort_keys=True, separators=(',', ':')) + '\n').encode()
        if len(data) > MAX_OUTPUT:
            return 2
        # Fresh exact output file: do not overwrite or follow existing links.
        fd = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        try:
            offset = 0
            while offset < len(data):
                written = os.write(fd, data[offset:])
                if written <= 0:
                    return 2
                offset += written
        finally:
            os.close(fd)
        return 0
    except (OSError, TimeoutError, ValueError):
        return 2
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipt')
    parser.add_argument('output')
    args = parser.parse_args()
    raise SystemExit(emit(args.receipt, args.output))
