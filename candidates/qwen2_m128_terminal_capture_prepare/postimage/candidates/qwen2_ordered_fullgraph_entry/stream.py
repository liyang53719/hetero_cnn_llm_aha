"""Bounded raw Matrix lifecycle frames, never a client or arithmetic service.

Only one successful pc12 QK2/PV0 owner in the pinned finite non-wrap ticket
profile is accepted. Raw native tickets are preserved; canonical ordinals are
returned transiently by the auditor. No historical ticket/object cache exists.
"""
import hashlib
import json
import os
from pathlib import Path
import struct

MAGIC = b'Q2EVT1\r\n'
END = 0xffffffff
MAX_RECORD = 1024
MAX_EVENTS = 3_000_000
U64 = (1 << 64) - 1
NAMES = ('acquire', 'accept_group', 'accept_step', 'retire_result', 'retire_done',
         'retire_legacy_reply', 'retire_owner_response', 'release', 'abort')
LENGTHS = (2, 5, 7, 6, 4, 2, 0, 0, 0)


def need(ok, message):
    if not ok:
        raise ValueError(message)


def uint(value, bits=64):
    return type(value) is int and 0 <= value < 1 << bits


def digest_word(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def profile_counts(rows):
    need(type(rows) is int and rows in (1, 2, 16, 17, 32, 128), 'finite row profile')
    groups = 12 * sum((k + 15) // 16 for k in range(1, rows + 1))
    total_groups = groups + 96 * rows
    return total_groups, 3 + 11 * groups + 192 * rows + 288 * (rows * (rows + 1) // 2)


def validate_shape(event):
    need(type(event) is tuple and len(event) == 3, 'event tuple')
    name, edge, values = event
    need(type(name) is str and name in NAMES and uint(edge), 'event method/edge')
    need(type(values) is tuple and len(values) == LENGTHS[NAMES.index(name)], 'event payload')
    if name == 'acquire':
        need(values[0] == 'normal' and uint(values[1], 32), 'normal owner tag')
    elif name == 'accept_group':
        need(all(uint(v, 32) for v in values), 'group integer widths')
    elif name == 'accept_step':
        need(all(uint(v, 32) for v in values[:2]) and
             all(type(v) is bool for v in values[2:6]) and digest_word(values[6]), 'step fields')
    elif name == 'retire_result':
        need(uint(values[0], 32) and all(type(v) is bool for v in values[1:3]) and
             uint(values[3]) and uint(values[4]) and digest_word(values[5]), 'result fields')
    elif name == 'retire_done':
        need(uint(values[0], 32) and type(values[1]) is bool and
             uint(values[2]) and uint(values[3]), 'done fields')
    elif name == 'retire_legacy_reply':
        need(all(uint(v) for v in values), 'legacy fields')
    return event


class Lifecycle:
    """O(1) state for one owner and at most one active original Matrix group.

    Native beginGroup uses ticket=nextTicket++, td_reset deliberately does not
    reset nextTicket, and release/abort do not assign it. This candidate rejects
    abort, reset-epoch changes, multiple owners and any uint64 wrap. It is NOT a
    generic lifecycle auditor for other services or reusable ticket domains.
    """
    def __init__(self, expected_groups):
        need(type(expected_groups) is int and 1 <= expected_groups <= 19200, 'group budget')
        self.expected_groups = expected_groups
        self.active = None
        self.owned = self.terminal = self.released = False
        self.last_edge = -1
        self.last_ticket = None
        self.epoch = None
        self.ordinal = self.groups = self.events = 0

    def accept(self, event):
        name, edge, raw = validate_shape(event)
        need(edge >= self.last_edge and not self.released, 'edge order/event after release')
        self.last_edge = edge
        values = list(raw)
        if name == 'acquire':
            need(not self.owned and not self.terminal and self.events == 0, 'duplicate/noninitial acquire')
            self.owned = True
        else:
            need(self.owned, 'event without owner')
        a = self.active
        if name == 'accept_group':
            need(a is None and not self.terminal, 'overlapping group')
            op, steps, tag, mask, profile = values
            need((op, profile, mask) in ((0x23, 2, 255), (0x24, 0, 1)) and
                 ((profile == 2 and steps == 8) or (profile == 0 and 1 <= steps <= 128)),
                 'QK2/PV0 finite group profile')
            self.groups += 1
            need(self.groups <= self.expected_groups, 'too many groups')
            self.active = dict(steps=steps, tag=tag, profile=profile, index=0,
                               pending=None, reply=False, done=False, ticket=None, epoch=None)
        elif name == 'accept_step':
            need(a is not None and not a['done'] and a['pending'] is None and not a['reply'], 'step overlaps debt')
            index, context, clear, last, finish, emit, packet_hash = values
            need(context == 0 and index == a['index'] < a['steps'] and clear == (index == 0) and
                 last == (index + 1 == a['steps']) and finish == last and
                 emit == (last if a['profile'] == 2 else True), 'step order/boundary')
            a['index'] += 1
            if emit:
                a['pending'] = (context, last)
        elif name == 'retire_result':
            need(a is not None and a['pending'] is not None and not a['done'], 'duplicate/foreign result')
            context, last, error, ticket, epoch, result_hash = values
            need((context, last) == a['pending'] and error is False and ticket > 0, 'result metadata/error')
            if a['ticket'] is None:
                need(self.last_ticket is None or ticket > self.last_ticket, 'ticket collision/reuse/order')
                if self.last_ticket is None:
                    need(ticket <= U64 - self.expected_groups + 1, 'ticket domain may wrap')
                need(self.epoch is None or epoch == self.epoch, 'reset epoch changed inside owner')
                self.epoch = epoch
                self.ordinal += 1
                self.last_ticket = a['ticket'] = ticket
                a['epoch'] = epoch
            need(ticket == a['ticket'] and epoch == a['epoch'], 'foreign result ticket/epoch')
            values[3] = self.ordinal
            a['pending'] = None
            a['reply'] = a['profile'] == 0
        elif name == 'retire_done':
            need(a is not None and not a['done'] and a['index'] == a['steps'] and a['pending'] is None, 'early/duplicate done')
            tag, error, ticket, epoch = values
            need(ticket == a['ticket'] and epoch == a['epoch'] and tag == a['tag'] and error is False, 'foreign done')
            values[2] = self.ordinal
            a['done'] = True
            if a['profile'] == 2:
                self.active = None
        elif name == 'retire_legacy_reply':
            need(a is not None and a['profile'] == 0 and a['reply'] and a['pending'] is None, 'duplicate/foreign legacy reply')
            ticket, epoch = values
            need(ticket == a['ticket'] and epoch == a['epoch'], 'foreign legacy ticket/epoch')
            need(a['index'] < a['steps'] or a['done'], 'final reply before done')
            values[0] = self.ordinal
            a['reply'] = False
            if a['done']:
                self.active = None
        elif name == 'retire_owner_response':
            need(a is None and not self.terminal, 'terminal before debt/duplicate')
            self.terminal = True
        elif name == 'release':
            need(a is None and self.terminal, 'release before terminal')
            self.released, self.owned = True, False
        elif name == 'abort':
            raise ValueError('aborted stream is not accepted')
        self.events += 1
        return name, edge, tuple(values)

    def finish(self):
        need(self.released and self.terminal and not self.owned and self.active is None and
             self.groups == self.ordinal == self.expected_groups, 'incomplete lifecycle/groups')


def _encode(event):
    # Structural encoding is deliberately separate from lifecycle validation.
    # An invalid integer width/order/ticket must remain in raw evidence.
    need(type(event) is tuple and len(event) == 3 and type(event[0]) is str and
         event[0] in NAMES and (type(event[1]) is int or event[1] is None) and
         type(event[2]) is tuple and all(type(v) in (int, bool, str, type(None))
                                      for v in event[2]), 'raw record structure')
    raw = json.dumps(event, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')
    need(0 < len(raw) <= MAX_RECORD, 'record extent')
    return struct.pack('<I', len(raw)) + raw


def _decode(raw):
    value = json.loads(raw)
    need(type(value) is list and len(value) == 3 and type(value[2]) is list, 'record structure')
    event = value[0], value[1], tuple(value[2])
    need(_encode(event)[4:] == raw, 'noncanonical/corrupt record encoding')
    return event


class EventWriter:
    """Append-only evidence sink, with separate raw capture and acceptance state.

    Lifecycle errors are sticky but do not raise into the old callback. Thus the
    remaining abort/ACK/cleanup events are still recorded. Only storage/encoding
    exhaustion stops capture. No method returns a service response or ACK.
    """
    def __init__(self, path, *, expected_groups, expected_events, max_events, max_bytes):
        need(type(expected_events) is int and 1 <= expected_events <= MAX_EVENTS, 'event budget')
        need(type(max_events) is int and expected_events <= max_events <= MAX_EVENTS, 'raw event capacity')
        need(type(max_bytes) is int and 52 <= max_bytes <= 1024**3, 'byte budget')
        self.path = Path(path).absolute()
        self.audit = Lifecycle(expected_groups)
        self.expected_groups, self.expected_events = expected_groups, expected_events
        self.max_events, self.max_bytes = max_events, max_bytes
        self.count = self.bytes = self.event_attempts = 0
        self.first_event_sha256 = self.last_event_sha256 = self.failed_event_sha256 = None
        self.raw_hash = hashlib.sha256()
        self.file_hash = hashlib.sha256()
        self.error = self.audit_error = None
        self.closed = self.sealed = self.raw_complete = self.created = False
        self.file = None
        try:
            self.file = self.path.open('xb', buffering=0)
            self.created = True
            self._write(MAGIC)
        except BaseException as error:
            # Disk setup failure is evidence failure, not a driver exception.
            self.error = type(error).__name__ + ': ' + str(error)
            self.close_incomplete()
            if isinstance(error, KeyboardInterrupt):
                raise

    def __iter__(self):
        raise TypeError('EventWriter cannot be materialized; replay its framed file explicitly')

    def _write(self, raw):
        need(self.bytes + len(raw) <= self.max_bytes, 'event stream byte budget')
        written = self.file.write(raw)
        if written != len(raw):
            raise OSError('short event stream write; partial bytes preserved')
        self.bytes += written
        self.file_hash.update(raw)

    def append(self, event):
        self.event_attempts += 1
        frame = None
        try:
            frame = _encode(event)
            need(not self.closed and not self.sealed and self.error is None, 'closed/failed event stream: ' + str(self.error))
            need(self.count < self.max_events, 'raw event capacity exhausted')
            need(self.bytes + len(frame) + 44 <= self.max_bytes, 'event stream footer reserve')
            self._write(frame)
            self.raw_hash.update(frame)
            self.count += 1
            self.last_event_sha256 = hashlib.sha256(frame).hexdigest()
            if self.first_event_sha256 is None:
                self.first_event_sha256 = self.last_event_sha256
        except BaseException as error:
            if frame is not None:
                self.failed_event_sha256 = hashlib.sha256(frame).hexdigest()
            if self.error is None:
                self.error = type(error).__name__ + ': ' + str(error)
            if isinstance(error, KeyboardInterrupt):
                raise
            if isinstance(error, Exception):
                raise
            raise OSError('capture storage failure: ' + self.error) from error
        if self.audit_error is None:
            try:
                self.audit.accept(event)
                need(self.count <= self.expected_events, 'successful event count exceeded')
            except BaseException as error:
                self.audit_error = type(error).__name__ + ': ' + str(error)
                if isinstance(error, KeyboardInterrupt):
                    raise

    def close_incomplete(self):
        if not self.closed:
            try:
                if self.file is not None:
                    self.file.close()
            except BaseException as error:
                if self.error is None:
                    self.error = type(error).__name__ + ': ' + str(error)
                if isinstance(error, KeyboardInterrupt):
                    raise
            finally:
                self.closed = True

    def seal(self):
        need(not self.closed and not self.sealed and self.error is None, 'failed/closed event stream')
        if self.audit_error is None:
            try:
                self.audit.finish()
                need(self.count == self.expected_events, 'incomplete successful event count')
            except BaseException as error:
                self.audit_error = type(error).__name__ + ': ' + str(error)
                if isinstance(error, KeyboardInterrupt):
                    raise
        try:
            # Footer means raw recording completed, NOT lifecycle acceptance.
            self._write(struct.pack('<IQ', END, self.count) + self.raw_hash.digest())
            self.file.flush()
            os.fsync(self.file.fileno())
            self.file.close()
            self.closed = self.raw_complete = True
        except BaseException as error:
            self.error = type(error).__name__ + ': ' + str(error)
            self.close_incomplete()
            raise
        need(self.audit_error is None, 'raw recording complete but lifecycle rejected: ' + str(self.audit_error))
        self.sealed = True
        return self.snapshot()

    def snapshot(self):
        return dict(format='qwen2-raw-event-frames-v1', path=str(self.path),
                    count=self.count, event_attempts=self.event_attempts,
                    first_event_sha256=self.first_event_sha256, last_event_sha256=self.last_event_sha256,
                    failed_event_sha256=self.failed_event_sha256,
                    expected_events=self.expected_events,
                    expected_groups=self.expected_groups, max_events=self.max_events,
                    max_bytes=self.max_bytes, complete=self.sealed,
                    raw_complete=self.raw_complete, created=self.created,
                    writer_error=self.error, audit_error=self.audit_error,
                    fully_written_bytes=self.bytes, fully_written_sha256=self.file_hash.hexdigest(),
                    raw_frame_sha256=self.raw_hash.hexdigest())


def replay_raw(path, *, max_bytes, max_events):
    """Replay raw tuples including invalid lifecycle values; NOT an acceptance gate.

    Consume through EOF to prove the complete recording footer/count/hash. The
    generator return value contains the SHA of these same bytes and same FD.
    """
    need(type(max_events) is int and 1 <= max_events <= MAX_EVENTS, 'raw event capacity')
    need(type(max_bytes) is int and 52 <= max_bytes <= 1024**3, 'byte budget')
    digest, file_digest = hashlib.sha256(), hashlib.sha256()
    count = total = 0
    with Path(path).open('rb') as f:
        need(os.fstat(f.fileno()).st_size <= max_bytes, 'file byte budget')
        header = f.read(len(MAGIC))
        need(header == MAGIC, 'stream header')
        file_digest.update(header)
        total += len(header)
        while True:
            prefix = f.read(4)
            need(len(prefix) == 4, 'truncated stream/no terminal footer')
            file_digest.update(prefix)
            size, = struct.unpack('<I', prefix)
            total += 4
            if size == END:
                tail = f.read(40)
                need(len(tail) == 40, 'truncated footer')
                stored_count, = struct.unpack('<Q', tail[:8])
                need(stored_count == count and tail[8:] == digest.digest(), 'footer count/hash')
                total += 40
                need(total <= max_bytes and f.read(1) == b'', 'trailing bytes/budget')
                file_digest.update(tail)
                return dict(format='qwen2-raw-event-frames-v1', raw_complete=True,
                            count=count, bytes=total, sha256=file_digest.hexdigest())
            need(0 < size <= MAX_RECORD and total + size + 44 <= max_bytes, 'record size/budget')
            raw = f.read(size)
            need(len(raw) == size, 'truncated event')
            total += size
            count += 1
            need(count <= max_events, 'raw event capacity exhausted')
            digest.update(prefix + raw)
            file_digest.update(raw)
            yield _decode(raw)


def replay(path, *, expected_groups, expected_events, max_events, max_bytes, canonical=False):
    """Acceptance replay. Consume through EOF before accepting any yielded prefix."""
    need(type(canonical) is bool, 'canonical flag')
    need(type(expected_events) is int and 1 <= expected_events <= max_events, 'event budget')
    audit = Lifecycle(expected_groups)
    raw = replay_raw(path, max_events=max_events, max_bytes=max_bytes)
    try:
        while True:
            try:
                event = next(raw)
            except StopIteration as stop:
                result = stop.value
                need(result['count'] == expected_events, 'incomplete event count')
                audit.finish()
                result['complete'] = True
                return result
            normalized = audit.accept(event)
            yield normalized if canonical else event
    finally:
        raw.close()


def _consume(iterator):
    while True:
        try:
            next(iterator)
        except StopIteration as stop:
            return stop.value


def verify(path, **limits):
    return _consume(replay(path, **limits))


def equal(left, right, *, limits, canonical=False):
    """Bounded comparison, consuming both verified trailers even on mismatch."""
    from itertools import zip_longest
    sentinel = object()
    same = True
    for a, b in zip_longest(replay(left, canonical=canonical, **limits),
                          replay(right, canonical=canonical, **limits), fillvalue=sentinel):
        same = (a == b) and same
    return same


def artifact_evidence(receipt, expected_path, *, evidence_directory=None):
    """Hash partial/complete evidence without materializing events or claiming PASS."""
    need(type(receipt) is dict and receipt.get('format') == 'qwen2-raw-event-frames-v1', 'stream receipt')
    path = Path(expected_path).absolute()
    need(Path(receipt['path']).absolute() == path, 'exact local stream file')
    limits = {key: receipt[key] for key in ('expected_groups', 'expected_events', 'max_events', 'max_bytes')}
    if not receipt['created']:
        return dict(format=receipt['format'], complete=False, raw_complete=False,
                    file=None, created=False, writer_error=receipt['writer_error'], limits=limits)
    need(path.is_file() and not path.is_symlink(), 'exact local regular stream file')
    need(path.stat().st_size <= receipt['max_bytes'], 'artifact byte bound')
    if receipt['raw_complete']:
        if receipt['complete']:
            result = verify(path, **limits)
        else:
            result = _consume(replay_raw(path, max_events=limits['max_events'], max_bytes=limits['max_bytes']))
            result['complete'] = False
        need(result['sha256'] == receipt['fully_written_sha256'] and
             result['bytes'] == receipt['fully_written_bytes'] and result['count'] == receipt['count'],
             'recorded stream changed')
    else:
        digest, total = hashlib.sha256(), 0
        with path.open('rb') as f:
            for block in iter(lambda: f.read(65536), b''):
                total += len(block)
                need(total <= limits['max_bytes'], 'artifact grew beyond budget')
                digest.update(block)
        result = dict(complete=False, raw_complete=False, count=receipt['count'],
                      bytes=total, sha256=digest.hexdigest())
    result.update(file=os.path.relpath(path, evidence_directory or path.parent),
                  path_base='evidence_directory', format=receipt['format'], created=True,
                  writer_error=receipt['writer_error'], audit_error=receipt['audit_error'],
                  monitor_error=receipt.get('monitor_error'), monitor_residual_tool=receipt.get('monitor_residual_tool'),
                  event_attempts=receipt['event_attempts'], first_event_sha256=receipt['first_event_sha256'],
                  last_event_sha256=receipt['last_event_sha256'], failed_event_sha256=receipt['failed_event_sha256'],
                  raw_values_preserved=True, policy='all recorded raw values; no sampling or ticket rewriting', limits=limits)
    return result
