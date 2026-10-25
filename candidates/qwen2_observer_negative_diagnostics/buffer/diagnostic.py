"""Bounded stdlib-only cases. Each worker is a fresh -I -B Python process."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import resource
import struct
import sys
import time

ROOT = Path(__file__).resolve().parent
SOURCE = Path(os.environ['QWEN2_TRACE_SOURCE'])
PREFIX_EVENTS = 120000
MAGIC = b'Q2EVT1\r\n'
END = 0xffffffff


def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(65536), b''):
            digest.update(block)
    return digest.hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def frames(path):
    with path.open('rb') as stream:
        assert stream.read(8) == MAGIC
        while prefix := stream.read(4):
            assert len(prefix) == 4
            size, = struct.unpack('<I', prefix)
            assert 0 < size <= 1024
            raw = stream.read(size)
            assert len(raw) == size
            value = json.loads(raw)
            yield prefix + raw, (value[0], value[1], tuple(value[2]))


def inspect(path):
    result = {'bytes': path.stat().st_size, 'sha256': file_hash(path), 'whole_frames': 0,
              'has_end': False, 'truncated_tail_bytes': 0}
    raw_digest = hashlib.sha256()
    with path.open('rb') as stream:
        head = stream.read(8)
        result['header_complete'] = head == MAGIC
        if head != MAGIC:
            result['truncated_tail_bytes'] = len(head)
            return result
        while prefix := stream.read(4):
            if len(prefix) < 4:
                result['truncated_tail_bytes'] = len(prefix)
                break
            size, = struct.unpack('<I', prefix)
            if size == END:
                tail = stream.read(40)
                assert len(tail) == 40 and stream.read(1) == b''
                count, = struct.unpack('<Q', tail[:8])
                assert count == result['whole_frames'] and tail[8:] == raw_digest.digest()
                result['has_end'] = True
                break
            assert 0 < size <= 1024
            raw = stream.read(size)
            if len(raw) != size:
                result['truncated_tail_bytes'] = 4 + len(raw)
                break
            raw_digest.update(prefix + raw)
            result['whole_frames'] += 1
    result['whole_frame_sha256'] = raw_digest.hexdigest()
    return result


class CountJSON:
    def __init__(self):
        self.encodes = 0

    def dumps(self, *args, **kwargs):
        self.encodes += 1
        return json.dumps(*args, **kwargs)


def load_writer(candidate):
    path = ROOT / ('candidate_writer_closure.py' if candidate else 'original_writer_closure.py')
    source = path.read_text()
    for node in ast.parse(source).body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [item.name for item in node.names] if isinstance(node, ast.Import) else [node.module]
            assert set(names) <= {'hashlib', 'json', 'os', 'pathlib', 'struct'}
    ns = {'__name__': 'isolated_stdlib_writer_closure'}
    exec(compile(source, str(path), 'exec'), ns)
    counter = CountJSON()
    ns['json'] = counter
    return ns, counter


def event_sequence():
    yield ('acquire', 0, ('normal', 99))
    yield ('accept_group', 1, (0x23, 8, 99, 255, 2))
    for index in range(8):
        last = index == 7
        yield ('accept_step', 2 + index, (index, 0, index == 0, last, last, last, 'a' * 64))
    yield ('retire_result', 10, (0, True, False, 17, 1, 'b' * 64))
    yield ('retire_done', 11, (99, False, 17, 1))
    yield ('retire_owner_response', 12, ())
    yield ('release', 13, ())


def raw_frame(event):
    value = json.dumps(event, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')
    return struct.pack('<I', len(value)) + value


class FaultRaw:
    def __init__(self, raw, kind):
        self.raw, self.kind, self.calls = raw, kind, 0

    def write(self, data):
        self.calls += 1
        if self.calls != 1:
            raise AssertionError('storage failure was retried')
        if self.kind == 'short_write':
            self.raw.write(data[:7])
            return 7
        if self.kind == 'partial_ioerror':
            self.raw.write(data[:7])
        raise OSError('injected storage failure')

    def flush(self):
        return self.raw.flush()

    def fileno(self):
        return self.raw.fileno()

    def close(self):
        return self.raw.close()


def prepare():
    before = SOURCE.stat()
    assert before.st_size == 133834196
    source_hash = file_hash(SOURCE)
    target = ROOT / 'preserved_prefix_120000.q2evt'
    raw_digest = hashlib.sha256()
    with target.open('xb') as output:
        output.write(MAGIC)
        for index, (frame, _) in enumerate(frames(SOURCE), 1):
            output.write(frame)
            raw_digest.update(frame)
            if index == PREFIX_EVENTS:
                break
    assert index == PREFIX_EVENTS
    after = SOURCE.stat()
    assert (before.st_size, before.st_mtime_ns, before.st_ino) == (after.st_size, after.st_mtime_ns, after.st_ino)
    return {'source_path': str(SOURCE), 'source_bytes': before.st_size, 'source_sha256': source_hash,
            'source_mtime_ns': before.st_mtime_ns, 'source_inode': before.st_ino,
            'prefix': inspect(target), 'prefix_events': index, 'prefix_frame_sha256': raw_digest.hexdigest(),
            'source_read_only': True, 'end_not_added': True}


def benchmark(buffer_bytes, default_off):
    ns, counter = load_writer(buffer_bytes != 0 or default_off)
    target = ROOT / ('benchmark_default_off.q2evt' if default_off else 'benchmark_' + str(buffer_bytes) + '.q2evt')
    options = dict(expected_groups=19200, expected_events=3000000, max_events=3000000, max_bytes=64 * 1024**2)
    if buffer_bytes:
        options['buffer_bytes'] = buffer_bytes
    start_wall, start_cpu = time.perf_counter(), time.process_time()
    writer = ns['EventWriter'](target, **options)
    checkpoints = []
    for index, (frame, event) in enumerate(frames(ROOT / 'preserved_prefix_120000.q2evt'), 1):
        writer.append(event)
        if index in (1, 1024, 16384, 65536, PREFIX_EVENTS):
            snapshot = writer.snapshot()
            checkpoints.append({'count': snapshot['count'], 'event_attempts': snapshot['event_attempts'],
                                'raw_frame_sha256': snapshot['raw_frame_sha256'],
                                'accepted_sha256': snapshot.get('accepted_sha256', snapshot['fully_written_sha256']),
                                'accepted_bytes': snapshot.get('accepted_bytes', snapshot['fully_written_bytes']),
                                'persisted_bytes': snapshot['fully_written_bytes'],
                                'pending_bytes': snapshot.get('pending_buffer_bytes', 0),
                                'audit_error': snapshot['audit_error']})
    before_close = writer.snapshot()
    writer.close_incomplete()
    timed = {'wall_seconds': time.perf_counter() - start_wall, 'cpu_seconds': time.process_time() - start_cpu}
    receipt = writer.snapshot()
    actual = inspect(target)
    fixture = inspect(ROOT / 'preserved_prefix_120000.q2evt')
    assert actual == fixture and actual['whole_frames'] == PREFIX_EVENTS and not actual['has_end']
    assert receipt['fully_written_bytes'] == actual['bytes'] and receipt['fully_written_sha256'] == actual['sha256']
    assert receipt['raw_frame_sha256'] == actual['whole_frame_sha256']
    assert counter.encodes == PREFIX_EVENTS and writer.audit_error is None
    assert not receipt['complete'] and not receipt['raw_complete']
    assert not buffer_bytes or receipt['pending_buffer_bytes'] == 0
    return {'kind': 'benchmark', 'buffer_bytes': buffer_bytes, 'default_off': default_off, 'timed_writer_plus_input_decode': timed,
            'json_encode_calls': counter.encodes, 'actual_file': actual, 'before_close': before_close,
            'receipt': receipt, 'checkpoints': checkpoints,
            'storage_write_calls': receipt.get('storage_write_calls', PREFIX_EVENTS + 1)}


def negative(buffer_bytes, case):
    ns, counter = load_writer(buffer_bytes != 0)
    target = ROOT / ('negative_' + case + '_' + str(buffer_bytes) + '.q2evt')
    options = dict(expected_groups=1, expected_events=14, max_events=16, max_bytes=100000)
    if buffer_bytes:
        options['buffer_bytes'] = buffer_bytes
    if case == 'byte_capacity':
        options['max_bytes'] = 160
    writer = ns['EventWriter'](target, **options)
    events = list(event_sequence())
    expected = bytearray(MAGIC)
    error = None
    fault = None
    if case in ('short_write', 'ioerror', 'partial_ioerror'):
        fault = FaultRaw(writer.file.raw if buffer_bytes else writer.file, case)
        if buffer_bytes:
            writer.file.raw = fault
        else:
            writer.file = fault
    if case in ('abort_close', 'audit_invalid_seal'):
        events.insert(3, ('abort', 3, ()))
    if case == 'encode_failure':
        events.insert(3, ('unknown', 3, ()))
    if case == 'event_capacity':
        events += [('abort', 14, ())] * 4
    try:
        for event in events:
            writer.append(event)
            expected.extend(raw_frame(event))
        if fault is not None:
            writer.file.flush()
        elif case == 'unexpected_exit':
            save(ROOT / ('exit_receipt_' + str(buffer_bytes) + '.json'), writer.snapshot())
            os._exit(73)
        elif case in ('clean_seal', 'audit_invalid_seal'):
            writer.seal()
    except (OSError, ValueError) as caught:
        error = type(caught).__name__ + ': ' + str(caught)
    finally:
        writer.close_incomplete()
    receipt = writer.snapshot()
    actual = inspect(target)
    actual_data = target.read_bytes()
    if actual['has_end']:
        frame_bytes = bytes(expected[8:])
        expected.extend(struct.pack('<IQ', END, len(events)) + hashlib.sha256(frame_bytes).digest())
    if fault:
        # The first attempted raw frame is not accepted in the unbuffered case.
        all_attempted = MAGIC + b''.join(raw_frame(event) for event in events)
        assert all_attempted.startswith(actual_data)
        assert fault.calls == 1 and not actual['has_end'] and not receipt['raw_complete']
        assert actual['bytes'] == (8 if case == 'ioerror' else 15)
        if buffer_bytes:
            assert receipt['persisted_prefix_exact'] == (case == 'short_write')
            assert receipt['fully_written_bytes'] <= actual['bytes']
            assert hashlib.sha256(actual_data[:receipt['fully_written_bytes']]).hexdigest() == receipt['fully_written_sha256']
    else:
        assert actual_data == bytes(expected)
        assert receipt['fully_written_bytes'] == actual['bytes'] and receipt['fully_written_sha256'] == actual['sha256']
        if buffer_bytes:
            assert receipt['pending_buffer_bytes'] == 0
    if case == 'clean_seal':
        assert receipt['complete'] and receipt['raw_complete'] and actual['has_end'] and error is None
    elif case == 'audit_invalid_seal':
        assert not receipt['complete'] and receipt['raw_complete'] and actual['has_end']
        assert receipt['audit_error'] is not None and actual['whole_frames'] == 15
    else:
        assert not receipt['complete'] and not receipt['raw_complete'] and not actual['has_end']
    if case in ('byte_capacity', 'event_capacity', 'encode_failure'):
        assert receipt['writer_error'] is not None and error is not None
    if case == 'abort_close':
        assert receipt['audit_error'] is not None and actual['whole_frames'] == 15
    return {'kind': 'negative', 'case': case, 'buffer_bytes': buffer_bytes, 'caught_error': error,
            'json_encode_calls': counter.encodes, 'fault_write_calls': fault.calls if fault else None,
            'actual_file': actual, 'receipt': receipt, 'raw_record_bytes_exact': True}


def main():
    allowed = os.sched_getaffinity(0)
    os.sched_setaffinity(0, {min(allowed)})
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2, 256 * 1024**2))
    parser = argparse.ArgumentParser()
    parser.add_argument('kind', choices=('prepare', 'benchmark', 'negative'))
    parser.add_argument('--buffer', type=int, default=0, choices=(0, 65536, 1048576))
    parser.add_argument('--default-off', action='store_true')
    parser.add_argument('--case')
    parser.add_argument('--result', required=True)
    args = parser.parse_args()
    start_wall = time.perf_counter()
    if args.kind == 'prepare':
        result = prepare()
    elif args.kind == 'benchmark':
        result = benchmark(args.buffer, args.default_off)
    else:
        result = negative(args.buffer, args.case)
    usage = resource.getrusage(resource.RUSAGE_SELF)
    result.update(process_cpu_seconds=usage.ru_utime + usage.ru_stime,
                  process_wall_seconds=time.perf_counter() - start_wall,
                  max_rss_kib=usage.ru_maxrss, cpu_affinity=sorted(os.sched_getaffinity(0)),
                  python_no_bytecode=sys.dont_write_bytecode,
                  imported_task_modules=[key for key in sys.modules if key.startswith(('candidates.', 'qwen2_', 'numpy', 'torch', 'ctypes'))])
    assert not result['imported_task_modules'] and result['python_no_bytecode']
    save(ROOT / args.result, result)
    print(json.dumps({'result': args.result, 'status': 'PASS', 'cpu_seconds': result['process_cpu_seconds'],
                      'wall_seconds': result['process_wall_seconds'], 'rss_kib': result['max_rss_kib']}), flush=True)


if __name__ == '__main__':
    main()
