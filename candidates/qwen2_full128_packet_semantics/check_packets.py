"""Offline accepted Matrix operand-content audit; never imports/runs the DUT.

Uses archived actual q/KV/probability words and an independent integer cursor.
No numerical kernel, reference tensor, reconstructed tensor, DDR replay, or RTL.
The CLI is opt-in; this source package itself grants no execution permission.
"""
import argparse
from array import array
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import stat
import struct
import sys
import time

SCHEMA = 'qwen2-offline-packet-semantics-v1'
MAGIC = b'Q2EVT1\r\n'
END = 0xffffffff
MAX_RECORD = 1024
RESOURCES = dict(cpus=1, cpu_seconds=180, wall_seconds=240,
    address_space_bytes=536870912, sampled_rss_bytes=268435456,
    input_stream_bytes=237446391, input_events=2478339,
    report_bytes=65536)


def need(ok, message):
    if not ok:
        raise ValueError(message)


def uint(value, bits=64):
    return type(value) is int and 0 <= value < 1 << bits


def digest(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def open_regular(path):
    """No final-component symlink; one FD supplies both identity and bytes."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        need(stat.S_ISREG(os.fstat(fd).st_mode), 'input is not a regular file')
        return os.fdopen(fd, 'rb')
    except BaseException:
        os.close(fd)
        raise


def read_pinned(item, limit):
    need(type(item) is dict and set(item) == {'path', 'bytes', 'sha256'}, 'exact input pin')
    need(uint(item['bytes']) and item['bytes'] <= limit and digest(item['sha256']), 'input pin bounds')
    with open_regular(item['path']) as f:
        need(os.fstat(f.fileno()).st_size == item['bytes'], 'input extent changed')
        raw = f.read(item['bytes'] + 1)
    need(len(raw) == item['bytes'] and hashlib.sha256(raw).hexdigest() == item['sha256'], 'input hash changed')
    return raw


def little_words(raw, code):
    value = array(code)
    value.frombytes(raw)
    need(value.itemsize == (4 if code == 'I' else 2), 'array word size')
    if sys.byteorder != 'little':
        value.byteswap()
    return value


class ActualWords:
    """Read-only views of actual archive payloads; no expanded semantic tensor."""
    def __init__(self, rows, q, kv, probability, presence, frequency):
        need(type(rows) is int and 1 <= rows <= 128, 'finite row domain')
        self.rows = rows
        need(len(q) == rows * 1536 * 4 and len(kv) == 2 * rows * 256 * 4, 'actual q/KV extent')
        need(len(probability) == 12 * rows * rows * 4 and len(presence) == 12 * rows * rows
             and len(frequency) == 12 * rows * rows * 2, 'actual probability extent')
        self.q = little_words(q, 'I')
        self.kv = little_words(kv, 'I')
        self.probability = little_words(probability, 'I')
        self.presence = presence
        frequencies = little_words(frequency, 'H')
        for words in (self.q, self.kv):
            need(all((word & 0xffff) == 0 and (word & 0x7f800000) != 0x7f800000 for word in words),
                 'q/KV must be finite BF16 FP32 containers')
        for i, word in enumerate(self.probability):
            key = i % rows
            query = (i // rows) % rows
            causal = key <= query
            need(presence[i] == int(causal) and frequencies[i] == (8 if causal else 0),
                 'probability actual presence/frequency domain')
            if causal:
                need((word & 0xffff) == 0 and (word & 0x7f800000) != 0x7f800000,
                     'causal probability not finite BF16')
                need(word <= 0x3f800000, 'probability not nonnegative <=1')
            else:
                need(word == 0xa5963cc3, 'unobserved future was filled')

    def qk_packet(self, query, head, first_key, active, depth):
        # Token-major q: [M,12,128]. KV parent = K[M,2,128], then V[M,2,128].
        # These integer formulas are independent of the DUT generator/helpers.
        q_base = query * 1536 + head * 128 + depth
        a = [self.q[q_base + lane] >> 16 for lane in range(16)]
        b = [0] * 256
        kv_head = 0 if head < 6 else 1
        for key_lane in range(active):
            k_base = (first_key + key_lane) * 256 + kv_head * 128 + depth
            for lane in range(16):
                b[key_lane * 16 + lane] = self.kv[k_base + lane] >> 16
        return struct.pack('<272H', *(a + b))

    def pv_packet(self, query, head, column, key):
        p_index = (head * self.rows + query) * self.rows + key
        need(self.presence[p_index] == 1, 'read of unobserved future probability')
        a = [self.probability[p_index] >> 16] + [0] * 15
        kv_head = 0 if head < 6 else 1
        v_base = self.rows * 256 + key * 256 + kv_head * 128 + column
        b = [self.kv[v_base + lane] >> 16 for lane in range(16)] + [0] * 240
        return struct.pack('<272H', *(a + b))


def group_cursor(rows):
    """Independent lexicographic expected work, not a DUT scheduling function."""
    for query in range(rows):
        for head in range(12):
            block = 0
            while block * 16 <= query:
                first = block * 16
                count = min(16, query - first + 1)
                yield (0x23, 2, 255, 8, query, head, first, count)
                block += 1
            for column_block in range(8):
                yield (0x24, 0, 1, query + 1, query, head, column_block * 16, None)


def expected_counts(rows):
    qk_groups = 12 * sum(1 + query // 16 for query in range(rows))
    pv_groups = 96 * rows
    qk_steps = 8 * qk_groups
    pv_steps = 96 * rows * (rows + 1) // 2
    return dict(groups=qk_groups + pv_groups, qk_groups=qk_groups, pv_groups=pv_groups,
                qk_packets=qk_steps, pv_packets=pv_steps, packets=qk_steps + pv_steps,
                events=3 + 11 * qk_groups + 2 * pv_groups + 3 * pv_steps)


class FramedEvents:
    """Independent streaming decoder. Success requires footer, same-FD hash, EOF."""
    def __init__(self, stream, *, expected_bytes, expected_sha256, expected_events, budget_check=None):
        need(uint(expected_bytes) and expected_bytes >= 52 and digest(expected_sha256), 'stream pin')
        need(uint(expected_events) and expected_events > 0, 'stream event pin')
        self.stream = stream
        self.expected_bytes, self.expected_sha256 = expected_bytes, expected_sha256
        self.expected_events = expected_events
        self.budget_check = budget_check
        self.file_hash, self.frame_hash = hashlib.sha256(), hashlib.sha256()
        self.count = self.total = 0
        self.finished = False
        need(self._read(8) == MAGIC, 'stream magic')

    def _read(self, count):
        need(self.total + count <= self.expected_bytes, 'stream byte bound')
        data = self.stream.read(count)
        need(len(data) == count, 'truncated stream')
        self.total += count
        self.file_hash.update(data)
        return data

    def next(self):
        need(not self.finished, 'event after footer')
        prefix = self._read(4)
        length = struct.unpack('<I', prefix)[0]
        if length == END:
            tail = self._read(40)
            need(struct.unpack('<Q', tail[:8])[0] == self.count == self.expected_events,
                 'footer event count')
            need(tail[8:] == self.frame_hash.digest(), 'footer frame hash')
            need(self.total == self.expected_bytes and self.stream.read(1) == b'', 'trailing bytes or extent')
            need(self.file_hash.hexdigest() == self.expected_sha256, 'full same-FD stream hash')
            self.finished = True
            return None
        need(0 < length <= MAX_RECORD and self.total + length + 44 <= self.expected_bytes,
             'frame size bound')
        raw = self._read(length)
        self.frame_hash.update(prefix + raw)
        self.count += 1
        need(self.count <= self.expected_events, 'event capacity')
        if self.budget_check is not None and self.count % 1024 == 0:
            self.budget_check()
        event = json.loads(raw)
        need(type(event) is list and len(event) == 3 and type(event[0]) is str and
             uint(event[1]) and type(event[2]) is list, 'event envelope')
        need(json.dumps(event, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii') == raw,
             'noncanonical event encoding')
        return event


def audit(events, actual, owner_tag):
    """Exact expected success language; no event is accepted by counts alone."""
    need(uint(owner_tag, 32), 'owner tag width')
    counts = expected_counts(actual.rows)
    last_edge = -1
    observed = dict(groups=0, qk_packets=0, pv_packets=0)
    last_ticket = 0
    fixed_epoch = None

    def take(name, length):
        nonlocal last_edge
        event = events.next()
        need(event is not None and event[0] == name, 'expected event ' + name)
        need(event[1] >= last_edge and len(event[2]) == length, 'event edge/payload extent')
        last_edge = event[1]
        return event[2]

    acquire = take('acquire', 2)
    need(type(acquire[0]) is str and uint(acquire[1], 32) and
         acquire == ['normal', owner_tag], 'exact owner acquisition')
    for opcode, profile, mask, steps, query, head, coordinate, active in group_cursor(actual.rows):
        group = take('accept_group', 5)
        need(all(uint(v, 32) for v in group), 'group widths')
        need(group[0] == opcode and group[1] == steps and group[3:] == [mask, profile],
             'group order/profile/steps/mask')
        group_tag = group[2]
        ticket = epoch = None
        for index in range(steps):
            final = index + 1 == steps
            emit = profile == 0 or final
            step = take('accept_step', 7)
            need(all(uint(v, 32) for v in step[:2]) and all(type(v) is bool for v in step[2:6])
                 and digest(step[6]), 'step field types')
            need(step[:6] == [index, 0, index == 0, final, final, emit], 'step control metadata')
            if profile == 2:
                packet = actual.qk_packet(query, head, coordinate, active, index * 16)
                observed['qk_packets'] += 1
            else:
                packet = actual.pv_packet(query, head, coordinate, index)
                observed['pv_packets'] += 1
            need(hashlib.sha256(packet).hexdigest() == step[6],
                 'accepted operand digest mismatch at q=%d h=%d op=%d coordinate=%d step=%d' %
                 (query, head, opcode, coordinate, index))
            if emit:
                result = take('retire_result', 6)
                need(uint(result[0], 32) and type(result[1]) is bool and type(result[2]) is bool
                     and uint(result[3]) and uint(result[4]) and digest(result[5]), 'result field types')
                need(result[:3] == [0, final, False], 'result context/last/error')
                if ticket is None:
                    ticket, epoch = result[3:5]
                    need(last_ticket < ticket, 'monotone positive ticket')
                    if last_ticket == 0:
                        need(ticket <= (1 << 64) - counts['groups'], 'nonwrapping first-ticket domain')
                    if fixed_epoch is None:
                        fixed_epoch = epoch
                    need(epoch == fixed_epoch, 'epoch changed')
                need(result[3:5] == [ticket, epoch], 'result ticket/epoch mismatch')
                if final:
                    done = take('retire_done', 4)
                    need(uint(done[0], 32) and type(done[1]) is bool and uint(done[2]) and uint(done[3]),
                         'done types')
                    need(done == [group_tag, False, ticket, epoch], 'done identity/error')
                if profile == 0:
                    reply = take('retire_legacy_reply', 2)
                    need(all(uint(v) for v in reply) and reply == [ticket, epoch], 'legacy reply identity')
        need(ticket is not None, 'group without result')
        last_ticket = ticket
        observed['groups'] += 1
    need(take('retire_owner_response', 0) == [] and take('release', 0) == [], 'owner terminal')
    need(events.next() is None and events.finished, 'extra event/incomplete footer')
    need(events.count == counts['events'] and all(observed[n] == counts[n] for n in observed),
         'exact work count mismatch')
    return dict(schema=SCHEMA, status='PASS_ACCEPTED_MATRIX_OPERAND_CONTENT_AND_INDEX_SEMANTICS',
        rows=actual.rows, observed=observed, expected=counts,
        accepted_pv_packets_per_causal_probability_cell=8,
        byte_order='little-endian <272H: A16 then B256',
        scope=dict(accepted_operand_hashes_verified=True, source_bound_gqa6_expected_content=True,
            expected_causal_work_sequence=True, expected_padding_verified=True,
            ddr_address_handshake_trace_verified=False, complete_result_tile_verified=False,
            logits_tensor_observed=False, mask_tensor_created=False, repeated_tensor_created=False,
            numerical_kernel_executed=False, official_reference_executed=False,
            hardware_cycles=None, rtl_pass=False, full29_numeric_pass=False))


def execute_plan(plan):
    need(type(plan) is dict and plan['schema'] == SCHEMA and plan['rows'] == 128, 'separate exact M128 plan')
    need(plan['resources'] == RESOURCES, 'frozen resource profile')
    need(set(plan['inputs']) == {'q', 'kv', 'probability', 'presence', 'frequency'}, 'exact archive roles')
    inputs = {name: read_pinned(pin, 2 ** 20) for name, pin in plan['inputs'].items()}
    actual = ActualWords(plan['rows'], **inputs)
    expected = expected_counts(plan['rows'])
    need(plan['stream']['bytes'] == RESOURCES['input_stream_bytes'] and
         plan['stream']['events'] == expected['events'] == RESOURCES['input_events'], 'exact stream count/extent')
    started = time.monotonic()
    def budget():
        need(time.monotonic() - started <= RESOURCES['wall_seconds'], 'wall budget')
        need(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024 <= RESOURCES['sampled_rss_bytes'],
             'sampled peak RSS budget')
    with open_regular(plan['stream']['path']) as stream:
        before = os.fstat(stream.fileno())
        need(before.st_size == plan['stream']['bytes'], 'stream size differs')
        events = FramedEvents(stream, expected_bytes=before.st_size,
            expected_sha256=plan['stream']['sha256'], expected_events=plan['stream']['events'],
            budget_check=budget)
        result = audit(events, actual, plan['owner_tag'])
        after = os.fstat(stream.fileno())
        need((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
             (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'stream changed during audit')
    budget()
    result['stream_sha256'] = events.file_hash.hexdigest()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', required=True)
    parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--execute-offline', action='store_true')
    args = parser.parse_args(argv)
    need(args.execute_offline, 'explicit offline execution switch required; no default run')
    need(digest(args.plan_sha256), 'plan digest')
    allowed = os.sched_getaffinity(0)
    need(bool(allowed), 'no allowed CPU')
    os.sched_setaffinity(0, {min(allowed)})
    resource.setrlimit(resource.RLIMIT_CPU, (RESOURCES['cpu_seconds'], RESOURCES['cpu_seconds']))
    resource.setrlimit(resource.RLIMIT_AS, (RESOURCES['address_space_bytes'], RESOURCES['address_space_bytes']))
    signal.signal(signal.SIGALRM, signal.SIG_DFL)
    signal.setitimer(signal.ITIMER_REAL, RESOURCES['wall_seconds'])
    with open_regular(args.plan) as f:
        raw = f.read(65537)
    need(len(raw) <= 65536 and hashlib.sha256(raw).hexdigest() == args.plan_sha256, 'plan identity/size')
    plan = json.loads(raw)
    started_cpu, started_wall = time.process_time(), time.monotonic()
    exit_code = 0
    try:
        result = execute_plan(plan)
    except Exception as error:
        exit_code = 1
        result = dict(schema=SCHEMA, status='FAIL_OFFLINE_ARCHIVE_AUDIT',
                      error_type=type(error).__name__, error=str(error),
                      partial_prefix_is_acceptance=False)
    result.update(plan_sha256=args.plan_sha256, process_cpu_seconds=time.process_time()-started_cpu,
                  wall_seconds=time.monotonic()-started_wall, execution_kind='OFFLINE_ARCHIVE_CHECK_ONLY')
    encoded = (json.dumps(result, indent=2, sort_keys=True) + '\n').encode()
    need(len(encoded) <= RESOURCES['report_bytes'], 'report cap')
    with open(args.output, 'xb') as f:
        f.write(encoded)
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
