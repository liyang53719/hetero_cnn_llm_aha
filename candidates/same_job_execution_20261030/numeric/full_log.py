"""Full-budget V2 only: lossless, finite, single-member gzip DUT evidence.

No arithmetic or acceptance policy. Every byte read from the pipe is retained.
A cap/pipe/storage failure is explicitly incomplete, never a complete transcript.
The caller still owns and proves absence of the inherited outer process group.
"""
import hashlib
import json
import os
import pathlib
import selectors
import select
import stat
import signal
import struct
import time
import zlib

P = pathlib.Path
SCHEMA = 'FULL_PREFILL_LOSSLESS_GZIP_LOG_V1'
V3_SCHEMA = 'FULL_PREFILL_LOSSLESS_GZIP_LOG_V3'
POLICY = dict(schema=SCHEMA, compressed_bytes=64 << 20, raw_bytes=16 << 30, line_bytes=8192)
CHUNK = 64 << 10
READ_CPU_SECONDS = 300  # Per complete verification pass; independent of wall wait.
CAPTURE_FIELDS = {'schema', 'policy', 'pid', 'consumer_pid', 'native_exit', 'termination_reason',
                  'errors', 'pipe_eof_observed', 'gzip_finalized', 'raw_bytes', 'raw_sha256',
                  'gzip_bytes', 'gzip_sha256', 'raw_crc32', 'retained_read_bytes', 'pipe_read_bytes', 'pipe_read_sha256', 'complete'}
REASONS = {'NATIVE_EXIT', 'WALL_TIMEOUT', 'LOG_LIMIT', 'PIPE_EOF_TIMEOUT', 'CAPTURE_ERROR'}


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def policy(value):
    need(type(value) is dict and set(value) == set(POLICY), 'exact full log policy')
    need(value['schema'] in (SCHEMA,V3_SCHEMA), 'full log schema')
    maximum=dict(POLICY,compressed_bytes=128<<20) if value['schema']==V3_SCHEMA else POLICY
    for key in ('compressed_bytes', 'raw_bytes', 'line_bytes'):
        need(type(value[key]) is int and 0 < value[key] <= maximum[key], 'finite full log '+key)
    need(value['line_bytes'] == POLICY['line_bytes'], 'unchanged bounded full log line')
    return dict(value)


def effective_policy(admission, profile, file_bytes):
    need(admission.get('mode') == 'FULL_BLOCK_ACCEPTANCE' and type(admission.get('budget_version')) is int and admission['budget_version'] in (2, 3),
         'streaming requires separately reviewed full V2')
    need(admission['log_policy'] == POLICY, 'reviewed full log maximum policy')
    value = dict(POLICY)
    value['raw_bytes'] = admission['profile_log_raw_bytes'][str(profile)]
    need(type(file_bytes) is int and file_bytes == POLICY['compressed_bytes'], 'original 64MiB output file cap')
    if admission['budget_version']==3:
        need(type(profile)is int and profile in admission['selected_profiles'],'selected V3 full log profile')
        value.update(compressed_bytes=admission['profile_log_compressed_bytes'][str(profile)])
        if value['compressed_bytes']>POLICY['compressed_bytes']:value['schema']=V3_SCHEMA
    return policy(value)


def paths(log):
    log = P(log)
    return P(str(log)+'.gz'), P(str(log)+'.capture.json')


def fingerprint(s):
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def regular(path, limit):
    path = P(path)
    need(path.is_absolute() and not any(p.is_symlink() for p in (path, *path.parents)), 'regular absolute full log path')
    need(path.is_file() and path.stat().st_size <= limit, 'bounded full log file')
    return path


def _exit_status(p):
    state = os.waitid(os.P_PID, p.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    return None if state is None else state.si_status if state.si_code == os.CLD_EXITED else -state.si_status


class Writer:
    """Bounded deterministic gzip; reserve worst-case expansion BEFORE pipe reads."""
    def __init__(self, path, value):
        self.policy = policy(value)
        self.file = P(path).open('xb')
        self.zip = zlib.compressobj(6, zlib.DEFLATED, 31)
        self.raw_hash = hashlib.sha256()
        self.gzip_hash = hashlib.sha256()
        self.raw_bytes = self.gzip_bytes = self.crc = 0
        self.finalized = False

    def room(self):
        # Each write flushes the compressor. This conservative bound covers
        # stored-block expansion, headers, sync marker and the final trailer.
        room = self.policy['compressed_bytes'] - self.gzip_bytes - 1024
        return max(0, min(CHUNK, self.policy['raw_bytes'] - self.raw_bytes, room * 1000 // 1001))

    def _write(self, data):
        need(self.gzip_bytes + len(data) <= self.policy['compressed_bytes'], 'compressed full log cap')
        written = self.file.write(data)
        need(written == len(data), 'complete gzip disk write')
        self.gzip_hash.update(data)
        self.gzip_bytes += len(data)

    def write(self, data):
        need(type(data) is bytes and len(data) <= self.room(), 'pre-reserved full log read')
        self._write(self.zip.compress(data) + self.zip.flush(zlib.Z_SYNC_FLUSH))
        self.raw_hash.update(data)
        self.raw_bytes += len(data)
        self.crc = zlib.crc32(data, self.crc)

    def finish(self):
        self._write(self.zip.flush(zlib.Z_FINISH))
        self.file.flush()
        os.fsync(self.file.fileno())
        self.finalized = True

    def close(self):
        self.file.close()


def capture(p, log, value, wall_seconds, on_started=None, writer=None):
    """Drain this Popen's merged pipe without creating/killing a nested group.

    Never reap the DUT until its native status has been observed with WNOWAIT.
    Ancestors/descendants are the strict outer supervisor's responsibility.
    A descendant holding the pipe prevents complete evidence.
    """
    value = policy(value)
    need(type(wall_seconds) is int and wall_seconds > 0, 'finite capture wall')
    archive, receipt = paths(log)
    need(not P(log).exists() and not receipt.exists(), 'fresh full log round')
    writer = writer if writer is not None else Writer(archive, value)
    pipe_hash = hashlib.sha256()
    pipe_bytes = 0
    selector = selectors.DefaultSelector()
    errors = []
    reason = 'NATIVE_EXIT'
    native = None
    eof = False
    deadline = time.monotonic() + wall_seconds
    drain_deadline = None
    try:
        need(p.stdout is not None and stat.S_ISFIFO(os.fstat(p.stdout.fileno()).st_mode), 'actual merged output pipe')
        os.set_blocking(p.stdout.fileno(), False)
        selector.register(p.stdout, selectors.EVENT_READ)
        if on_started is not None:
            on_started(p)
        while True:
            now = time.monotonic()
            if native is None:
                native = _exit_status(p)
                if native is not None:
                    drain_deadline = now + 5
            if native is None and reason == 'NATIVE_EXIT' and now >= deadline:
                reason = 'WALL_TIMEOUT'
                try: os.kill(p.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                drain_deadline = now + 5
            if eof and native is not None:
                break
            if drain_deadline is not None and now >= drain_deadline:
                if not eof:
                    errors.append('PIPE_EOF_NOT_OBSERVED')
                    if reason == 'NATIVE_EXIT': reason = 'PIPE_EOF_TIMEOUT'
                break
            room = writer.room()
            if room == 0 and not eof:
                # poll is nonconsuming: HUP without POLLIN means no writers
                # and no buffered data. Only then can read(1) prove EOF without
                # consuming an unretainable byte at an exact budget boundary.
                probe = select.poll()
                probe.register(p.stdout, select.POLLIN | select.POLLHUP)
                events = probe.poll(50)
                mask = events[0][1] if events else 0
                if mask & select.POLLHUP and not mask & select.POLLIN:
                    need(os.read(p.stdout.fileno(), 1) == b'', 'empty closed pipe at log boundary')
                    eof = True
                    selector.unregister(p.stdout)
                    continue
                if mask & select.POLLIN:
                    reason = 'LOG_LIMIT'
                    errors.append('FULL_LOG_BUDGET_EXHAUSTED')
                    break  # No read whose bytes cannot be retained.
                need(not mask & (select.POLLERR | select.POLLNVAL), 'valid full log pipe')
                continue
            ready = selector.select(min(.2, max(0, deadline-now)) if native is None and reason == 'NATIVE_EXIT' else .05)
            if ready:
                try:
                    data = os.read(p.stdout.fileno(), room)
                except BlockingIOError:
                    continue
                if data:
                    pipe_hash.update(data)
                    pipe_bytes += len(data)
                    writer.write(data)
                else:
                    eof = True
                    selector.unregister(p.stdout)
            elif eof:
                time.sleep(.02)
    except BaseException:
        reason = 'CAPTURE_ERROR'
        errors.append('CAPTURE_IO_OR_START_FAILURE')
        raise
    finally:
        # Preserve bytes already consumed even on timeout or another failure.
        # Disk errors may prevent this; the incomplete receipt never claims EOF.
        try:
            if native is None:
                native = _exit_status(p)
            if native is None:
                try: os.kill(p.pid, signal.SIGKILL)
                except ProcessLookupError: pass
            p.wait(timeout=5)
            if native is None:
                native = p.returncode
        finally:
            selector.close()
            if p.stdout is not None: p.stdout.close()
            try:
                writer.finish()
            except (OSError, ValueError, zlib.error):
                errors.append('GZIP_FINALIZATION_FAILED')
                reason = 'CAPTURE_ERROR'
            finally:
                try:
                    writer.close()
                except OSError:
                    if 'GZIP_FINALIZATION_FAILED' not in errors: errors.append('GZIP_FINALIZATION_FAILED')
                    reason = 'CAPTURE_ERROR'
            body = dict(schema=value['schema'], policy=value, pid=p.pid, consumer_pid=os.getpid(), native_exit=native,
                        termination_reason=reason, errors=errors, pipe_eof_observed=eof,
                        gzip_finalized=writer.finalized, raw_bytes=writer.raw_bytes,
                        raw_sha256=writer.raw_hash.hexdigest(), gzip_bytes=writer.gzip_bytes,
                        gzip_sha256=writer.gzip_hash.hexdigest(), raw_crc32=f'{writer.crc:08x}',
                        retained_read_bytes=writer.raw_bytes, pipe_read_bytes=pipe_bytes, pipe_read_sha256=pipe_hash.hexdigest(),
                        complete=eof and writer.finalized and reason == 'NATIVE_EXIT' and not errors and writer.raw_bytes == pipe_bytes)
            with receipt.open('x') as f:
                json.dump(body, f, sort_keys=True, separators=(',', ':'))
                f.write('\n')
    return body


def read_capture(log, expected_policy=None):
    archive, receipt = paths(log)
    regular(receipt, 16384)
    value = json.loads(receipt.read_text())
    need(type(value) is dict and set(value) == CAPTURE_FIELDS, 'exact full capture receipt')
    need(value['schema'] == value['policy']['schema'] and value['termination_reason'] in REASONS, 'full capture schema/status')
    policy(value['policy'])
    if expected_policy is not None:
        need(value['policy'] == policy(expected_policy), 'actual reviewed per-profile log limits')
    for key in ('pid', 'consumer_pid'):
        need(type(value[key]) is int and value[key] > 0, 'capture actual process identity')
    need(type(value['native_exit']) is int and -127 <= value['native_exit'] <= 255, 'actual native exit')
    for key in ('pipe_eof_observed', 'gzip_finalized', 'complete'):
        need(type(value[key]) is bool, 'capture booleans')
    need(type(value['errors']) is list and len(value['errors']) <= 3 and all(x in ('PIPE_EOF_NOT_OBSERVED','FULL_LOG_BUDGET_EXHAUSTED','CAPTURE_IO_OR_START_FAILURE','GZIP_FINALIZATION_FAILED') for x in value['errors']), 'capture fixed errors')
    for key, cap in (('raw_bytes', value['policy']['raw_bytes']), ('retained_read_bytes', value['policy']['raw_bytes']), ('pipe_read_bytes', value['policy']['raw_bytes']), ('gzip_bytes', value['policy']['compressed_bytes'])):
        need(type(value[key]) is int and 0 <= value[key] <= cap, 'capture byte bounds')
    need(value['retained_read_bytes'] == value['raw_bytes'] <= value['pipe_read_bytes'], 'retained/read byte correspondence')
    if value['complete']:
        need(value['raw_bytes'] == value['pipe_read_bytes'] and value['raw_sha256'] == value['pipe_read_sha256'], 'all read bytes retained')
    for key, count in (('raw_sha256',64), ('pipe_read_sha256',64), ('gzip_sha256',64), ('raw_crc32',8)):
        need(type(value[key]) is str and len(value[key]) == count and all(x in '0123456789abcdef' for x in value[key]), 'capture digest format')
    need(value['complete'] is (value['pipe_eof_observed'] and value['gzip_finalized'] and value['termination_reason'] == 'NATIVE_EXIT' and not value['errors'] and value['raw_bytes'] == value['pipe_read_bytes']), 'complete capture correspondence')
    regular(archive, value['policy']['compressed_bytes'])
    return value


def chunks(log, expected, *, require_complete=True):
    """Strict full decode with bounded output chunks, CRC/ISIZE/EOF and hashes.

    zlib's single-member decoder rejects corrupt trailers. Explicit EOF and
    unused-data checks reject truncation, concatenation, zero padding and junk.
    Raw size bounds also bound decompression work, never trust gzip ISIZE alone.
    """
    cpu_start = time.process_time()
    actual = read_capture(log, expected['policy'])
    need(actual == expected, 'capture receipt changed')
    if require_complete:
        need(actual['complete'], 'incomplete full log capture')
    need(actual['gzip_finalized'], 'unfinalized gzip capture')
    archive, _ = paths(log)
    before = archive.stat()
    decoder = zlib.decompressobj(31)
    rh = hashlib.sha256(); gh = hashlib.sha256()
    raw_count = gzip_count = crc = 0
    with archive.open('rb') as f:
        need(fingerprint(os.fstat(f.fileno())) == fingerprint(before), 'full log changed before open')
        while True:
            compressed = f.read(CHUNK)
            if not compressed: break
            gh.update(compressed); gzip_count += len(compressed)
            need(gzip_count <= actual['policy']['compressed_bytes'], 'compressed log growth')
            need(not decoder.eof, 'trailing gzip data or concatenated member')
            pending = compressed
            while pending:
                need(time.process_time() - cpu_start <= READ_CPU_SECONDS, 'full log verification CPU bound')
                try:
                    data = decoder.decompress(pending, CHUNK)
                except zlib.error as error:
                    raise ValueError('invalid gzip stream/CRC') from error
                pending = decoder.unconsumed_tail
                need(not decoder.unused_data, 'trailing gzip data or concatenated member')
                if data:
                    raw_count += len(data)
                    need(raw_count <= actual['policy']['raw_bytes'] and raw_count <= actual['raw_bytes'], 'decompressed full log bound')
                    rh.update(data); crc = zlib.crc32(data, crc)
                    yield data
                need(data or not pending, 'gzip decompressor progress')
        need(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail, 'complete gzip trailer and EOF')
        need(fingerprint(os.fstat(f.fileno())) == fingerprint(before) == fingerprint(archive.stat()), 'full log changed while reading')
    need((raw_count, rh.hexdigest(), f'{crc:08x}', gzip_count, gh.hexdigest()) ==
         (actual['raw_bytes'], actual['raw_sha256'], actual['raw_crc32'], actual['gzip_bytes'], actual['gzip_sha256']), 'full log hash/size/CRC binding')


def lines(log, expected, *, require_complete=True):
    pending = b''
    for data in chunks(log, expected, require_complete=require_complete):
        # Each fragment and the sole retained partial line are strictly bounded.
        pieces = data.split(b'\n')
        for part in pieces[:-1]:
            raw = pending + part + b'\n'
            need(len(raw) <= expected['policy']['line_bytes'], 'full log line cap')
            pending = b''
            yield raw
        pending += pieces[-1]
        need(len(pending) <= expected['policy']['line_bytes'], 'full log line cap')
    if pending:
        yield pending


class LogView:
    """One verified pass may index a finite caller-declared receipt vocabulary.

    Only counters and first matching bounded lines are retained in memory. The
    complete original byte stream stays in gzip. No observation is synthesized
    or filtered from the stored evidence. Legacy-like streaming operations are
    still available for tests and callers without an explicit marker index.
    """
    def __init__(self, log, expected, markers=None, prefixes=None):
        self.log, self.expected = P(log), expected
        self.indexed = markers is not None
        self.markers = tuple(markers or ())
        self.prefixes = tuple(prefixes or ())
        for words, bound in ((self.markers,64),(self.prefixes,16)):
            need(len(words)<=bound and len(set(words))==len(words), 'bounded unique marker vocabulary')
            for word in words: self._marker(word)
        self.verified = False

    @staticmethod
    def _marker(marker):
        need(type(marker) is str and marker and len(marker) <= 8192 and not any(x in marker for x in '\r\n\v\f\x1c\x1d\x1e\x85\u2028\u2029'), 'bounded single-line marker')

    def verify(self):
        self.verified = False
        self.counts = dict.fromkeys(self.markers,0)
        self.prefix_counts = dict.fromkeys(self.prefixes,0)
        self.first_lines = {}
        for raw in lines(self.log, self.expected):
            for line in raw.decode('utf-8').splitlines():
                for marker in self.markers:
                    self.counts[marker] += line.count(marker)
                for prefix in self.prefixes:
                    if line.startswith(prefix):
                        self.prefix_counts[prefix] += 1
                        self.first_lines.setdefault(prefix,line)
        self.verified = True
        return self

    def splitlines(self):
        for raw in lines(self.log, self.expected):
            yield from raw.decode('utf-8').splitlines()

    def count(self, marker):
        self._marker(marker)
        if self.indexed:
            need(self.verified and marker in self.counts, 'verified declared marker index')
            return self.counts[marker]
        return sum(line.count(marker) for line in self.splitlines())

    def count_prefix(self,prefix):
        need(self.indexed and self.verified and prefix in self.prefix_counts, 'verified declared prefix index')
        return self.prefix_counts[prefix]

    def unique_marker_line(self,prefix,message):
        need(self.count_prefix(prefix)==1,message)
        return self.first_lines[prefix]


class PostprocessBudgetExceeded(RuntimeError):
    pass


class PostprocessBudget:
    """Explicit host-only wall/CPU reserve, never an extension of DUT runtime."""
    def __init__(self, limits):
        need(type(limits) is dict and set(limits)=={'wall_seconds','cpu_seconds'}, 'exact postprocess budget')
        need(all(type(v) is int and 0<v<=3600 for v in limits.values()) and limits['cpu_seconds']<=limits['wall_seconds'], 'finite reviewed postprocess budget')
        self.limits=dict(limits)
        self.running=False
        self.expired=False

    def start(self):
        import threading
        need(not self.running and threading.current_thread() is threading.main_thread(), 'unused main-thread postprocess watchdog')
        signals={signal.SIGALRM,signal.SIGPROF}
        entry_mask=signal.pthread_sigmask(signal.SIG_BLOCK,signals)
        try:
            need(not signals.intersection(entry_mask), 'unblocked postprocess watchdog signals')
            need(not signals.intersection(signal.sigpending()), 'no pending external postprocess signal')
            need(signal.getitimer(signal.ITIMER_REAL)==(0.,0.) and signal.getitimer(signal.ITIMER_PROF)==(0.,0.), 'unused host watchdog timers')
            self.entry_mask=entry_mask
            self.owner_thread_id=threading.get_ident()
            self.handlers={s:signal.getsignal(s) for s in signals}
            self.expired=False
            self.started=time.monotonic();self.cpu_started=time.process_time()
            def expired(signum, frame):
                self.expired=True
                raise PostprocessBudgetExceeded('postprocess '+('wall' if signum==signal.SIGALRM else 'CPU')+' budget exhausted')
            self.running=True
            for s in self.handlers:signal.signal(s,expired)
            signal.setitimer(signal.ITIMER_REAL,self.limits['wall_seconds'])
            signal.setitimer(signal.ITIMER_PROF,self.limits['cpu_seconds'])
            # Delivery can raise while unmasking a timer or unrelated signal.
            # Keep that transition inside the owner rollback boundary.
            self._restore_owned_mask(entry_mask)
        except BaseException:
            if self.running:self.stop()
            else:self._restore_owned_mask(entry_mask)
            raise
        return self

    def _restore_owned_mask(self, entry_mask):
        signals={signal.SIGALRM,signal.SIGPROF}
        # Even a reentrant unrelated handler at the first mask operation must
        # not skip restoration of the remaining owned bits.
        try:signal.pthread_sigmask(signal.SIG_BLOCK,signals&entry_mask)
        finally:signal.pthread_sigmask(signal.SIG_UNBLOCK,signals-entry_mask)

    def stop(self):
        if not self.running:return
        import threading
        need(threading.current_thread() is threading.main_thread() and threading.get_ident()==self.owner_thread_id, 'owning main-thread postprocess watchdog')
        signals={signal.SIGALRM,signal.SIGPROF}
        signal.pthread_sigmask(signal.SIG_BLOCK,signals)
        try:
            signal.setitimer(signal.ITIMER_REAL,0);signal.setitimer(signal.ITIMER_PROF,0)
            for s in signals:
                if s in signal.sigpending():
                    self.expired=True
                    signal.sigtimedwait({s},0)
            for s,handler in self.handlers.items():signal.signal(s,handler)
        finally:
            self.running=False
            # Restore only our two signal-mask bits. Other bits may have been
            # deliberately changed by the caller while this watchdog ran.
            self._restore_owned_mask(self.entry_mask)
        wall=time.monotonic()-self.started;cpu=time.process_time()-self.cpu_started
        return dict(wall_seconds=wall,cpu_seconds=cpu,budget_exceeded=self.expired or wall>self.limits['wall_seconds'] or cpu>self.limits['cpu_seconds'])
