"""Opt-in full-budget V2 RSS evidence. No sampling or resource-limit changes.

The compressor retains all serialized observations, with bounded internal state.
No raw file, thinning, rotating member or prefix-only success is permitted.
A successful receipt is checked against the entire closed physical file.
"""
import hashlib
import json
import math
import os
import re
from pathlib import Path
import stat
import struct
import time
import zlib

SCHEMA = 'FULL_PREFILL_RSS_GZIP_V1'
V3_SCHEMA = 'FULL_PREFILL_RSS_GZIP_V3'
MAX_RAW_BYTES = 16 << 30
COMPRESSED_BYTES = 64 << 20
LINE_BYTES = 1 << 20
CHUNK = 64 << 10
MAX_VERIFY_SECONDS = 3600
POLICY_FIELDS = {'schema', 'raw_bytes', 'compressed_bytes', 'line_bytes',
                 'verification_wall_seconds', 'verification_cpu_seconds'}
HEADER = b'\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff'

RECEIPT_FIELDS = {'schema', 'policy', 'filename', 'raw_bytes', 'raw_sha256', 'compressed_bytes',
                  'compressed_sha256', 'samples', 'raw_crc32', 'packed_bytes_before_finalization',
                  'sample_bytes_storage_state', 'gzip_finalized', 'writer_closed', 'capture_failed',
                  'all_written_bytes_verified'}
VERIFICATION_FIELDS = {'gzip_crc_eof_verified', 'physical_eof_verified',
                       'verification_wall_seconds', 'verification_cpu_seconds'}


def need(value, reason):
    if not value:
        raise ValueError(reason)


def policy(value):
    need(type(value) is dict and set(value) == POLICY_FIELDS, 'exact RSS telemetry policy')
    need(value['schema'] in (SCHEMA,V3_SCHEMA), 'RSS telemetry V2 opt-in schema')
    need(type(value['raw_bytes']) is int and 0 < value['raw_bytes'] <= MAX_RAW_BYTES,
         'finite per-profile RSS raw cap')
    need(type(value['compressed_bytes']) is int and
         (0 < value['compressed_bytes'] <= 1<<30 if value['schema']==V3_SCHEMA else value['compressed_bytes'] == COMPRESSED_BYTES),
         'unchanged RSS telemetry 64MiB file cap')
    need(type(value['line_bytes']) is int and value['line_bytes'] == LINE_BYTES,
         'bounded RSS observation size')
    for key in ('verification_wall_seconds', 'verification_cpu_seconds'):
        need(type(value[key]) is int and 0 < value[key] <= MAX_VERIFY_SECONDS,
             'finite RSS verification '+key)
    need(value['verification_cpu_seconds'] <= value['verification_wall_seconds'],
         'RSS verification CPU within wall budget')
    return dict(value)


def fingerprint(s):
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns


class Writer:
    """One deterministic gzip member, checked writes and fixed bounded memory."""
    def __init__(self, path, value):
        self.policy = policy(value)
        self.path = Path(path)
        self.file = self.path.open('xb', buffering=0)
        self.compressor = zlib.compressobj(6, zlib.DEFLATED, -15)
        self.raw_hash = hashlib.sha256()
        self.compressed_hash = hashlib.sha256()
        self.raw_bytes = self.compressed_bytes = self.samples = self.crc = 0
        self.packed_bytes_before_finalization = 0
        self.finalized = self.failed = self.closed = False
        try:
            self._write(HEADER)
            self.packed_bytes_before_finalization = self.compressed_bytes
        except BaseException:
            self.file.close()
            self.closed = True
            raise

    def _write(self, data):
        if not data:
            return
        need(self.compressed_bytes + len(data) <= self.policy['compressed_bytes'],
             'RSS telemetry 64MiB compressed cap')
        n = self.file.write(data)
        # Account for an explicitly reported partial write, but never accept it.
        if type(n) is int and 0 <= n <= len(data):
            self.compressed_hash.update(data[:n])
            self.compressed_bytes += n
        need(type(n) is int and n == len(data), 'complete RSS telemetry disk write')
        self.file.flush()

    def write(self, line):
        try:
            need(not self.finalized and not self.failed and not self.closed, 'open RSS telemetry writer')
            need(type(line) is str, 'serialized RSS JSONL observation')
            data = line.encode('utf-8')
            need(data.endswith(b'\n') and data.count(b'\n') == 1 and len(data) <= self.policy['line_bytes'],
                 'one bounded RSS observation')
            need(self.raw_bytes + len(data) <= self.policy['raw_bytes'], 'RSS raw telemetry cap')
            self._write(self.compressor.compress(data))
            self.raw_hash.update(data)
            self.raw_bytes += len(data)
            self.crc = zlib.crc32(data, self.crc)
            self.samples += 1
            self.packed_bytes_before_finalization = self.compressed_bytes
        except BaseException:
            self.failed = True
            raise

    def finish(self):
        if self.finalized:
            return
        try:
            need(not self.failed and not self.closed, 'finish healthy RSS telemetry writer')
            self._write(self.compressor.flush(zlib.Z_FINISH))
            self._write(struct.pack('<II', self.crc, self.raw_bytes & 0xffffffff))
            self.file.flush()
            need(os.fstat(self.file.fileno()).st_size == self.compressed_bytes,
                 'RSS written physical byte count')
            self.finalized = True
        except BaseException:
            self.failed = True
            raise

    def close(self):
        if not self.closed:
            try:
                self.file.close()
            except BaseException:
                self.failed = True
                raise
            finally:
                self.closed = True

    def receipt(self):
        return dict(schema=self.policy['schema'], policy=dict(self.policy), filename=self.path.name,
                    raw_bytes=self.raw_bytes, raw_sha256=self.raw_hash.hexdigest(),
                    compressed_bytes=self.compressed_bytes,
                    compressed_sha256=self.compressed_hash.hexdigest(), samples=self.samples,
                    raw_crc32=f'{self.crc:08x}',
                    packed_bytes_before_finalization=self.packed_bytes_before_finalization,
                    sample_bytes_storage_state='BOUNDED_DEFLATE_BUFFER_UNTIL_FINALIZATION',
                    gzip_finalized=self.finalized,
                    writer_closed=self.closed, capture_failed=self.failed,
                    all_written_bytes_verified=False)


def _sample(line):
    value = json.loads(line)
    fields = {'elapsed', 'aggregate_rss_bytes', 'processes', 'MemAvailable_bytes',
              'reserve_below_1GiB_warning'}
    need(type(value) is dict and set(value) == fields, 'exact RSS sample fields')
    need(type(value['elapsed']) in (int, float) and math.isfinite(value['elapsed']) and value['elapsed'] >= 0,
         'finite RSS sample elapsed')
    for key in ('aggregate_rss_bytes', 'MemAvailable_bytes'):
        need(type(value[key]) is int and value[key] >= 0, 'RSS sample nonnegative '+key)
    rows = value['processes']
    need(type(rows) is list and len(rows) <= 4096, 'RSS observed process bound')
    need(all(type(row) is list and len(row) == 7 and all(type(x) is int and x >= 0 for x in row)
             for row in rows), 'RSS process observation fields')
    need(len({row[0] for row in rows}) == len(rows), 'unique RSS observed identities')
    need(sum(row[4] for row in rows) == value['aggregate_rss_bytes'], 'RSS aggregate observation agreement')
    need(type(value['reserve_below_1GiB_warning']) is bool and
         value['reserve_below_1GiB_warning'] == (value['MemAvailable_bytes'] < 1024**3),
         'RSS memory warning evidence')
    return value


def _scan(path, raw_cap, compressed_cap, line_cap, wall_seconds, cpu_seconds):
    """Private bounded stream scanner. Tests also exercise small exact limits.

    At both byte boundaries read/decompress at most one extra byte to establish
    true EOF versus overflow. Never use gzip's concatenated-member convenience.
    """
    path = Path(path)
    need(path.is_absolute() and not any(p.is_symlink() for p in (path, *path.parents)),
         'regular absolute RSS telemetry path')
    wall_start = time.monotonic()
    cpu_start = time.thread_time()
    raw_hash = hashlib.sha256()
    compressed_hash = hashlib.sha256()
    raw_bytes = compressed_bytes = samples = crc = 0
    pending = bytearray()
    previous_elapsed = -1
    decoder = zlib.decompressobj(31)
    header = bytearray()

    def budget():
        need(time.monotonic() - wall_start <= wall_seconds, 'RSS verification wall cap')
        need(time.thread_time() - cpu_start <= cpu_seconds, 'RSS verification CPU cap')

    def consume(data):
        nonlocal raw_bytes, samples, crc, previous_elapsed
        raw_bytes += len(data)
        need(raw_bytes <= raw_cap, 'RSS verification raw cap')
        raw_hash.update(data)
        crc = zlib.crc32(data, crc)
        # At most one bounded sample plus one 64KiB decoder chunk is live.
        pending.extend(data)
        while True:
            end = pending.find(b'\n')
            if end < 0:
                need(len(pending) < line_cap, 'RSS verification line cap')
                break
            need(end + 1 <= line_cap, 'RSS verification line cap')
            value = _sample(pending[:end])
            need(value['elapsed'] >= previous_elapsed, 'RSS sample chronological order')
            previous_elapsed = value['elapsed']
            del pending[:end+1]
            samples += 1
            budget()

    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb', buffering=0) as stream:
        initial = os.fstat(stream.fileno())
        need(stat.S_ISREG(initial.st_mode) and initial.st_size <= compressed_cap,
             'bounded regular RSS compressed file')
        while True:
            budget()
            data = stream.read(min(CHUNK, compressed_cap-compressed_bytes+1))
            if not data:
                break
            need(not decoder.eof, 'RSS gzip trailing bytes or second member')
            compressed_bytes += len(data)
            need(compressed_bytes <= compressed_cap, 'RSS verification compressed cap')
            compressed_hash.update(data)
            if len(header) < len(HEADER):
                header.extend(data[:len(HEADER)-len(header)])
            while data:
                budget()
                output = decoder.decompress(data, min(CHUNK, raw_cap-raw_bytes+1))
                consume(output)
                need(not decoder.unused_data, 'RSS gzip trailing bytes or second member')
                data = decoder.unconsumed_tail
                need(not (decoder.eof and data), 'RSS gzip extra compressed tail')
        need(bytes(header) == HEADER, 'deterministic RSS gzip header')
        need(decoder.eof, 'RSS gzip full CRC/trailer EOF required')
        need(not pending, 'RSS final complete JSONL line required')
        need(fingerprint(initial) == fingerprint(os.fstat(stream.fileno())),
             'RSS telemetry changed during verification')
        need(fingerprint(initial) == fingerprint(path.stat(follow_symlinks=False)),
             'RSS telemetry path replaced during verification')
        need(initial.st_size == compressed_bytes, 'RSS exact physical EOF byte count')
        budget()
    return dict(raw_bytes=raw_bytes, raw_sha256=raw_hash.hexdigest(), compressed_bytes=compressed_bytes,
                compressed_sha256=compressed_hash.hexdigest(), samples=samples, raw_crc32=f'{crc:08x}',
                gzip_crc_eof_verified=True, physical_eof_verified=True,
                verification_wall_seconds=time.monotonic()-wall_start,
                verification_cpu_seconds=time.thread_time()-cpu_start)


def _receipt(receipt, expected_policy, expected_samples, complete):
    value = policy(expected_policy)
    need(type(receipt) is dict, 'RSS receipt object')
    allowed = (RECEIPT_FIELDS | VERIFICATION_FIELDS, ) if complete else (RECEIPT_FIELDS, RECEIPT_FIELDS | VERIFICATION_FIELDS)
    need(set(receipt) in allowed, 'exact RSS receipt fields')
    receipt_policy = policy(receipt['policy'])
    need(receipt['schema'] == value['schema'] and receipt_policy == value, 'RSS receipt exact approved policy')
    need(type(receipt['filename']) is str and receipt['filename'] == 'rss_samples.jsonl.gz', 'RSS receipt filename')
    need(receipt['gzip_finalized'] is True and receipt['writer_closed'] is True and
         receipt['capture_failed'] is False, 'RSS writer complete before verification')
    need(type(expected_samples) is int and expected_samples >= 0, 'RSS expected sample count')
    for key, maximum in (('raw_bytes', value['raw_bytes']), ('compressed_bytes', value['compressed_bytes']),
                         ('samples', value['raw_bytes'])):
        need(type(receipt[key]) is int and 0 <= receipt[key] <= maximum, 'RSS receipt finite '+key)
    need(receipt['samples'] == expected_samples, 'every supervisor observation retained')
    for key, digits in (('raw_sha256', 64), ('compressed_sha256', 64), ('raw_crc32', 8)):
        need(type(receipt[key]) is str and re.fullmatch('[0-9a-f]{'+str(digits)+'}', receipt[key]) is not None,
             'RSS receipt hexadecimal '+key)
    need(receipt['sample_bytes_storage_state'] == 'BOUNDED_DEFLATE_BUFFER_UNTIL_FINALIZATION' and
         type(receipt['packed_bytes_before_finalization']) is int and
         0 <= receipt['packed_bytes_before_finalization'] <= receipt['compressed_bytes'],
         'RSS packed bytes and finalization distinction')
    need(type(receipt['all_written_bytes_verified']) is bool, 'RSS verification boolean')
    if set(receipt) == RECEIPT_FIELDS | VERIFICATION_FIELDS:
        need(receipt['all_written_bytes_verified'] is True and receipt['gzip_crc_eof_verified'] is True and
             receipt['physical_eof_verified'] is True, 'RSS complete verification proof')
        for key in ('verification_wall_seconds', 'verification_cpu_seconds'):
            need(type(receipt[key]) in (int, float) and math.isfinite(receipt[key]) and
                 0 <= receipt[key] <= value[key], 'RSS verification used finite '+key)
    return value


def verify(path, receipt, expected_policy, expected_samples):
    """Fully recompute a closed writer receipt; no trust in claimed completion."""
    value = _receipt(receipt, expected_policy, expected_samples, False)
    need(receipt['filename'] == Path(path).name, 'RSS receipt actual filename')
    actual = _scan(path, value['raw_bytes'], value['compressed_bytes'], value['line_bytes'],
                   value['verification_wall_seconds'], value['verification_cpu_seconds'])
    for key in ('raw_bytes', 'compressed_bytes', 'samples', 'raw_sha256', 'compressed_sha256', 'raw_crc32'):
        need(receipt[key] == actual[key], 'RSS receipt '+key)
    result = {**receipt, **actual, 'all_written_bytes_verified': True}
    _receipt(result, value, expected_samples, True)
    return result


def check_receipt(path, receipt, expected_policy, expected_samples):
    """Recheck trusted pinned supervisor proof and physical compressed identity.

    Does NOT redo the supervisor's raw CRC/JSONL pass. Caller must derive expected
    policy and count independently from its admitted profile and supervisor
    report, pin this helper, and account for this read in its own finite phase.
    The compressed physical SHA/count binds every byte to the full prior proof.
    """
    value = _receipt(receipt, expected_policy, expected_samples, True)
    path = Path(path)
    need(path.name == receipt['filename'] and path.is_absolute() and
         not any(p.is_symlink() for p in (path, *path.parents)), 'regular absolute RSS receipt path')
    wall_start = time.monotonic()
    cpu_start = time.thread_time()
    digest = hashlib.sha256()
    count = 0
    def budget():
        need(time.monotonic()-wall_start <= value['verification_wall_seconds'], 'RSS receipt read wall cap')
        need(time.thread_time()-cpu_start <= value['verification_cpu_seconds'], 'RSS receipt read CPU cap')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb', buffering=0) as stream:
        initial = os.fstat(stream.fileno())
        need(stat.S_ISREG(initial.st_mode) and initial.st_size == receipt['compressed_bytes'],
             'RSS receipt physical compressed byte count')
        while True:
            budget()
            data = stream.read(min(CHUNK, value['compressed_bytes']-count+1))
            if not data:
                break
            count += len(data)
            need(count <= value['compressed_bytes'], 'RSS receipt compressed cap')
            digest.update(data)
        need(count == receipt['compressed_bytes'] and digest.hexdigest() == receipt['compressed_sha256'],
             'RSS receipt complete compressed identity')
        need(fingerprint(initial) == fingerprint(os.fstat(stream.fileno())) ==
             fingerprint(path.stat(follow_symlinks=False)), 'RSS receipt file changed during read')
        budget()
    return dict(receipt)
