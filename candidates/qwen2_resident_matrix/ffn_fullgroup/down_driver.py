"""Drive ordinary Dense/Down on the caller's exact owner and physical banks.

This file contains transport orchestration and physical DDR checks only. The
unchanged inherited transposed_down owner generates every transaction and the
unchanged td_* library consumes accepted physical Matrix/seed packets. It does
not decode saved results or invoke reference arithmetic. Those comparisons
belong after this function has observed the final ACK and owner terminal.
"""
from array import array
from collections import Counter, deque
import ctypes as C
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import struct
import sys
import time


SENTINEL_WORD = 0xA5963CC3
FULL_MASK = (1 << 64) - 1
BEAT_BYTES, CONTEXT_BYTES, GUARD_BYTES = 64, 16384, 64
CHUNKS = ((0, 2560), (2560, 5120), (5120, 7680), (7680, 8960))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class PhysicalRegion:
    """One sentinel-backed physical address span, including immutable guards."""
    def __init__(self, base, extent):
        require(type(base) is int and base % 64 == 0 and type(extent) is int and
                extent > 0 and extent % 64 == 0, 'physical DDR span geometry')
        self.base, self.extent = base, extent
        self.guard = struct.pack('<I', SENTINEL_WORD) * (GUARD_BYTES // 4)
        self.data = bytearray(struct.pack('<I', SENTINEL_WORD) *
                              ((extent + 2 * GUARD_BYTES) // 4))
        self.initial_sha256 = sha(self.data[GUARD_BYTES:-GUARD_BYTES])

    def contains(self, address, size=64):
        return self.base <= address and address + size <= self.base + self.extent

    def offset(self, address):
        require(type(address) is int and address % 64 == 0 and self.contains(address),
                'physical DDR access outside aligned address span')
        return GUARD_BYTES + address - self.base

    def read64(self, address):
        offset = self.offset(address)
        return struct.unpack_from('<16I', self.data, offset)

    def write64(self, address, words):
        require(len(words) == 16 and all(type(word) is int and 0 <= word < 1 << 32
                                       for word in words), 'physical DDR data width')
        struct.pack_into('<16I', self.data, self.offset(address), *words)

    def raw(self):
        return bytes(self.data[GUARD_BYTES:-GUARD_BYTES])

    def check_guards(self):
        require(self.data[:GUARD_BYTES] == self.guard and self.data[-GUARD_BYTES:] == self.guard,
                'physical DDR guard corruption')


class CappedRecords:
    """Persist a bounded whole-record prefix while hashing the complete stream."""
    def __init__(self, path, cap=131072):
        self.path, self.cap = Path(path), cap
        self.saved = self.total = self.records = 0
        self.truncated = False
        self.digest = hashlib.sha256()
        self.stream = self.path.open('wb')

    def write(self, raw):
        self.digest.update(raw)
        self.total += len(raw)
        self.records += 1
        if not self.truncated and self.saved + len(raw) <= self.cap:
            self.stream.write(raw)
            self.saved += len(raw)
        else:
            self.truncated = True

    def report(self):
        self.stream.flush()
        return dict(path=self.path.name, sha256=self.digest.hexdigest(), records=self.records,
                    total_bytes_hashed=self.total, persisted_prefix_bytes=self.saved,
                    prefix_cap_bytes=self.cap)

    def close(self):
        self.stream.close()


@dataclass(frozen=True)
class DenseSource:
    """Caller-owned physical A span; callbacks observe the live shared memory.

    ready() must return True only when this span is readable. raw() returns its
    actual bytes for integrity checks, never arithmetic. A published span also
    supplies write_acks(): the actual (WriteCommand, WriteAck) pairs retained
    by shared memory, covering every byte once. Readonly inputs need no ACKs.
    These callbacks are checked again immediately before admission and after
    terminal; accepted A payloads always come from memory.read64(address).
    """
    base: int
    extent: int
    provenance: str
    ready: object
    raw: object
    write_acks: object = None

    def validate(self, job):
        require(type(self.base) is int and type(self.extent) is int and
                self.base == job.a and self.extent == job.m * job.k * 4,
                'Dense A source must match the actual full physical span')
        require(self.provenance in ('readonly', 'published') and callable(self.ready) and
                callable(self.raw), 'Dense A requires explicit readonly/published provenance and readiness')
        require(self.ready() is True, 'Dense A physical span is not ready for admission')
        if self.provenance == 'published':
            require(callable(self.write_acks), 'published Dense A requires actual prior write ACK records')
            covered = set()
            for command, ack in self.write_acks():
                require(type(command.address) is int and command.address % 64 == 0 and
                        type(command.beats) is int and 1 <= command.beats <= 16 and
                        self.base <= command.address and
                        command.address + command.beats * 64 <= self.base + self.extent and
                        command.address // 1024 == (command.address + command.beats * 64 - 1) // 1024 and
                        ack.tag == command.tag and not ack.error and ack.nbytes == command.beats * 64,
                        'published Dense A has malformed prior physical write ACK')
                addresses = set(range(command.address, command.address + command.beats * 64, 64))
                require(not covered.intersection(addresses), 'published Dense A has duplicate prior write ACK')
                covered.update(addresses)
            require(covered == set(range(self.base, self.base + self.extent, 64)),
                    'published Dense A lacks full prior physical write ACK coverage')
        raw = self.raw()
        require(isinstance(raw, (bytes, bytearray, memoryview)) and len(raw) == self.extent,
                'Dense A source snapshot byte extent')
        return sha(raw)


def execute_down(model, owner, lib, memory, job, out, deadline, trace, *, synthetic_geometry=False,
                 owner_tick=None, matrix_bridge=None, workspace_transport=None, output_event=None):
    """Strict historical Down entry point, returning report and actual FP32 words."""
    report, destination = _execute_dense(model, owner, lib, memory, job, out, deadline, trace,
        synthetic_geometry=synthetic_geometry, owner_tick=owner_tick, a_source=None,
        output_event=output_event, matrix_bridge=matrix_bridge, workspace_transport=workspace_transport)
    actual = array('I'); actual.frombytes(destination.raw())
    return report, actual


def execute_dense(model, owner, lib, memory, job, out, deadline, trace, *, a_source,
                  output_event, owner_tick=None, matrix_bridge=None, workspace_transport=None):
    """Return (report, actual acknowledged PhysicalRegion) after final terminal.

    output_event(kind, value) is mandatory shared-memory transport: command,
    data, and ack receive the unchanged accepted port objects, in that order.
    The sink must keep the destination unreadable until terminal receives the
    successful owner response, after the final ACK and all driver checks. An
    exception/fault never emits terminal; accepted writes remain in the sink.
    No end-of-job bulk injection substitutes for these actual write events.
    """
    require(isinstance(a_source, DenseSource), 'explicit DenseSource required')
    require(callable(output_event), 'Dense requires actual shared-memory output event routing')
    return _execute_dense(model, owner, lib, memory, job, out, deadline, trace,
        synthetic_geometry=False, owner_tick=owner_tick, a_source=a_source,
        output_event=output_event, matrix_bridge=matrix_bridge, workspace_transport=workspace_transport)


def _execute_dense(model, owner, lib, memory, job, out, deadline, trace, *,
                   synthetic_geometry, owner_tick, a_source, output_event, matrix_bridge, workspace_transport):
    """One accepted-port orchestration for both ordinary Dense and strict Down.

    memory.read64(address) selects act/weight solely by physical address. The
    local physical prefix span is selected by that same address rule before
    delegating other addresses. Command kinds are checked only after dispatch.
    No owner, SRAM bank, tile adapter, arithmetic model or reference is created.
    """
    legacy_down = a_source is None
    require(matrix_bridge is None or (lib is matrix_bridge and matrix_bridge.owner is owner),
            'shared Matrix bridge must be this driver arithmetic resource and actual owner')
    tick_owner = owner.tick if owner_tick is None else owner_tick
    started, start_tick = time.monotonic(), owner.clock
    out, down, workspace = Path(out), model.down, owner.workspace
    require(sys.byteorder == 'little', 'explicit little-endian host required')
    job.validate()
    require(type(synthetic_geometry) is bool, 'explicit typed synthetic geometry flag')
    require(job.kind == 'Dense' and not job.activation_bf16 and job.weight_bf16 and not job.output_bf16 and
            job.write_bytes == job.m * job.n * 4, 'full Down decoded job/dtype/byte contract')
    require(workspace is not None, 'same-owner explicit Down workspace required')
    workspace.validate(job)
    if not legacy_down:
        chunks = tuple((start, min(start + workspace.split_k, job.k))
                       for start in range(0, job.k, workspace.split_k))
    elif synthetic_geometry:
        require(job.m == 16 and job.k in (256, 512) and job.n == 32 and workspace.split_k == 128,
                'synthetic Down restricted to M16/K256-or512/N32/split128')
        chunks = tuple((start, min(start + workspace.split_k, job.k))
                       for start in range(0, job.k, workspace.split_k))
    else:
        require(job.m in (16, 128) and job.k == 8960 and job.n == 1536 and workspace.split_k == 2560,
                'full Down requires M16/M128 K8960 N1536 split2560')
        chunks = CHUNKS
    final_chunk = len(chunks) - 1
    prefix_versions = tuple(range(1, len(chunks)))
    active_prefix_extent = (job.n // 32) * CONTEXT_BYTES if final_chunk else 0
    if legacy_down and workspace_transport is None:
        require(workspace.extent == active_prefix_extent,
                'full physical Down prefix workspace required')
    require(owner.state == 'idle' and owner.lease is None and owner.window_request is None and
            owner.drain_request is None and owner.tiles.idle and not owner.tiles.leased and
            not owner.error and not owner.tiles.poison and not owner.drain_poison and
            all(not tag.live for tag in owner.tiles.tags),
            'Down admission before group terminal, lease invalidation, or tile drain')
    if legacy_down:
        require(job.a == memory.act.base and memory.act.pending is None and
                memory.act.extent == job.m * job.k * 4 and memory.act.ack_bytes == memory.act.extent and
                memory.act.data_bytes == memory.act.extent and
                len(memory.act.write_addresses) == memory.act.extent // 64,
                'Down A is not the fully ACK-written actual act address span')
    require(not any((owner.read_active, owner.a_hold, owner.a_rmw_pending, owner.pending,
                     owner.fifo, owner.final_value, owner.seed_outstanding)) and
            owner.write_state == 'idle', 'Down admission with unfinished physical obligation')
    bank_ids = (id(owner), id(owner.a_banks), id(owner.b_banks), id(owner.tiles), id(owner.tiles.banks))
    require(owner.tiles.banks is owner.a_banks and
            (len(owner.a_banks.words), len(owner.a_banks.words[0]), len(owner.b_banks.words),
             len(owner.b_banks.words[0])) == (16, 1376, 16, 160), 'same fixed physical owner banks')
    initial_act_hash = (sha(memory.act.data[GUARD_BYTES:-GUARD_BYTES]) if legacy_down else
                        a_source.validate(job))
    initial_read_sequence, initial_write_sequence = owner.read_sequence, owner.write_sequence
    initial_group_sequence, initial_responses = owner.group_sequence, owner.responses
    # The owner's full reservation remains untouched. Only used prefix bytes
    # need backing; single-chunk jobs neither allocate nor access a prefix.
    if workspace_transport is not None:
        physical = getattr(memory, 'physical_memory', memory)
        require(workspace_transport.physical_memory is physical,
                'Dense workspace transport must share the operand physical address index')
        prefix = workspace_transport.begin(job, workspace)
        require((prefix is None) == (active_prefix_extent == 0) and
                (prefix is None or prefix.extent == active_prefix_extent),
                'shared workspace active extent differs from accepted Dense geometry')
    else:
        prefix = PhysicalRegion(workspace.base, active_prefix_extent) if active_prefix_extent else None
    destination = PhysicalRegion(job.dst, job.write_bytes)
    prefix_beats, contexts_total = active_prefix_extent // 64, job.n // 32
    versions = bytearray(prefix_beats)
    data_versions = bytearray(prefix_beats)
    read_versions, seeded_versions = Counter(), Counter()
    prefix_writes, prefix_reads, seed_counts = Counter(), Counter(), Counter()
    seed_commits, matrix_done_groups, written, acknowledged = set(), set(), set(), set()
    act_reads, weight_reads = set(), set()
    physical_result_hashes, prefix_sweeps, groups = {}, [], []
    counts, region_counts, held = Counter(), Counter(), {}
    hashes = {key: hashlib.sha256() for key in
              ('read_descriptors', 'read_payloads', 'steps', 'results', 'write_descriptors',
               'write_data', 'write_acks', 'seed_requests', 'seed_acks', 'matrix_done')}
    seed_records = CappedRecords(out / 'down_seed_records_prefix.bin')
    prefix_records = CappedRecords(out / 'down_prefix_transactions_prefix.jsonl')
    operand_a, operand_b = (C.c_uint16 * 16)(), (C.c_uint16 * 256)()
    physical, seed_words = (C.c_uint32 * 4096)(), (C.c_uint32 * 16)()
    pending_read = pending_write = pending_ack = seed_ack = None
    results, staged = deque(), []
    result_peak, operand_peak, finished, final_ack_tick = 0, 0, None, None
    final_ack_stall_remaining, final_ack_stall_ticks = 5, 0
    saw_explicit_mask, saw_implicit_mask = False, False
    expected_groups = [dict(chunk_index=chunk, start=start, end=end, n_base=n,
                            contexts=min(5, (job.n - n) // 32))
                       for chunk, (start, end) in enumerate(chunks)
                       for n in range(0, job.n, 160)]

    def check_budget():
        require(time.monotonic() <= deadline, 'full Down host budget exceeded')

    def check_identity():
        require(bank_ids == (id(owner), id(owner.a_banks), id(owner.b_banks),
                             id(owner.tiles), id(owner.tiles.banks)), 'physical owner/banks replaced')
        require(owner.workspace is workspace, 'physical owner workspace reservation replaced')
        require(owner.lease is None and not owner.error and not owner.tiles.poison and
                not owner.drain_poison, 'same-owner Down fault/lease: ' + str(owner.error))

    def prefix_record(kind, address, version, words, old_version=None):
        value = dict(tick=owner.clock, kind=kind, address=address, version=version,
                     payload_sha256=sha(struct.pack('<16I', *words)))
        if old_version is not None:
            value['overwritten_version'] = old_version
        raw = (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()
        prefix_records.write(raw)

    def read64(command):
        address = command.address
        if prefix is not None and prefix.contains(address):
            # Shared transport resolves the original address index and records
            # this accepted descriptor; audit reads never authorize operands.
            words = (workspace_transport.accept_read(command) if workspace_transport is not None
                     else prefix.read64(address))
            return 'workspace', words
        region, words = memory.read64(address)
        if legacy_down:
            return region, words
        # Dispatch the actual physical memory first. Its labels do not select
        # arithmetic operands; the accepted address and live tensor spans do.
        if job.a <= address and address + 64 <= job.a + a_source.extent:
            return 'act', words
        if job.b <= address and address + 64 <= job.b + job.k * job.n * 2:
            return 'down_weight', words
        raise ValueError('Dense read escaped physical A/weight/workspace spans')

    try:
        check_budget()
        if not legacy_down:
            require(a_source.validate(job) == initial_act_hash, 'Dense A changed before actual admission')
        port = owner.ports()
        require(port['job_ready'] and port['response'] is None, 'ordinary Down job port not ready')
        admission = tick_owner(job=job)
        require(admission['job_ready'] and owner.job is job and owner.state == 'clear' and
                not admission.get('response_fire'), 'ordinary Down job handshake not accepted')
        counts['job_handshakes'] = 1
        counts['model_ticks'] = 1
        check_identity()
        trace.event(dict(kind='down_admission', tick=owner.clock, job=asdict(job),
                         inherited_owner=True, lease_invalid=True,
                         act_ack_bytes=(memory.act.ack_bytes if legacy_down else
                                        a_source.extent if a_source.provenance == 'published' else 0),
                         initial_read_sequence=initial_read_sequence,
                         initial_write_sequence=initial_write_sequence))
        while finished is None:
            check_budget()
            ports = owner.ports()
            chunk_index, chunk_start, chunk_end = owner.chunk_index, owner.chunk_start, owner.chunk_end
            n_base, group_sequence = owner.n_base, owner.group_sequence
            contexts = getattr(owner, 'contexts', 0)
            tick = counts['model_ticks']
            operand_peak = max(operand_peak, len(owner.fifo) + int(owner.pending is not None))
            inputs = dict(step_ready=not (ports['step'] is not None and ports['step'].last and len(results) >= 2),
                          write_command_ready=tick % 5 != 0, write_data_ready=tick % 7 != 0)
            if pending_read is not None:
                command, region, version, words = pending_read
                if region == 'workspace':
                    index = (command.address - workspace.base) // 64
                    require(owner.prefix_valid and owner.committed_prefix_end == chunk_start and
                            owner.completed_prefix_sweeps == chunk_index and
                            versions[index] == data_versions[index] == version == chunk_index and
                            prefix.read64(command.address) == words,
                            'prefix version changed between accepted read and response')
                inputs['read_beat'] = down.ReadBeat(command.tag, words, True)
            if results:
                inputs['result'] = results[0]
            if (owner.group_started and not owner.group_done and
                    owner.group_accepted_steps == (chunk_end - chunk_start) * contexts and
                    owner.results_received == contexts and not results):
                inputs['matrix_done'] = down.MatrixDone(job.tag)
            if pending_ack is not None:
                command, index, write_chunk, region = pending_write
                last_output = region == 'down' and len(written) == job.write_bytes // 64
                if last_output and final_ack_stall_remaining:
                    require(ports['response'] is None and owner.state != 'finish' and
                            owner.write_bytes < job.write_bytes, 'Down terminal before final ACK')
                    final_ack_stall_remaining -= 1
                    final_ack_stall_ticks += 1
                    trace.event(dict(kind='down_final_ack_held', tick=owner.clock,
                                     ack_bytes=owner.write_bytes, accepted_data_bytes=len(written) * 64))
                else:
                    inputs['write_ack'] = pending_ack
            if seed_ack is not None:
                inputs['seed_ack'] = seed_ack
            edge = tick_owner(**inputs)
            counts['model_ticks'] += 1
            check_identity()
            for signal, ready in (('write_command', inputs['write_command_ready']),
                                  ('write_data', inputs['write_data_ready'])):
                if signal in held:
                    require(edge.get(signal) == held[signal], 'held Down ' + signal + ' changed')
                if edge.get(signal) is not None and not ready:
                    held[signal] = edge[signal]
                    counts[signal + '_stall_ticks'] += 1
                else:
                    held.pop(signal, None)
            require(not any(edge.get(key) for key in ('window_fire', 'window_result_fire', 'drain_fire',
                        'drain_result_fire')), 'ordinary Down emitted FFN window/drain transaction')

            if edge.get('group_fire'):
                observed = dict(chunk_index=chunk_index, start=chunk_start, end=chunk_end,
                                n_base=n_base, contexts=contexts)
                require(len(groups) < len(expected_groups) and observed == expected_groups[len(groups)] and
                        group_sequence == initial_group_sequence + len(groups) + 1,
                        'unexpected chunk-major Down group sequence/context count')
                require(matrix_done_groups == {entry['sequence'] for entry in groups},
                        'Down group started before all prior MatrixDone handshakes')
                if chunk_index < final_chunk:
                    require(prefix_writes[chunk_index + 1] == n_base // 32 * 256,
                            'Down group before previous group prefix ACKs')
                else:
                    require(len(acknowledged) * 64 == job.m * n_base * 4,
                            'Down group before previous group output ACKs')
                if chunk_index and n_base == 0:
                    require(prefix_writes[chunk_index] == prefix_beats and
                            all(v == chunk_index for v in versions) and versions == data_versions,
                            'Down chunk before complete physical prefix sweep ACKs')
                    prefix.check_guards()
                    raw = prefix.raw()
                    path = out / ('down_acknowledged_prefix_%d_physical.f32le' % chunk_index)
                    path.write_bytes(raw)
                    prefix_sweeps.append(dict(version=chunk_index, bytes=len(raw), sha256=sha(raw),
                                             path=path.name, physical_cells=contexts_total * 4096,
                                             all_128_rows_per_context=True, canaries_exact=True))
                require(edge['group'] == (job.tag, 0x20, 0xff, True), 'Down Matrix group identity/profile')
                if workspace_transport is not None:
                    workspace_transport.accept_group(chunk_index, n_base, contexts, group_sequence)
                require(lib.td_group(chunk_start, chunk_end, contexts) == 0, 'unchanged Down host group setup')
                groups.append(dict(observed, sequence=group_sequence, start_tick=owner.clock))
                counts['groups'] += 1
                trace.event(dict(kind='down_group', tick=owner.clock, group=groups[-1]))
            if edge.get('seed_begin_fire'):
                request = edge['seed_begin']
                require(chunk_index > 0 and request.tag == job.tag and request.sequence == group_sequence and
                        request.generation == workspace.generation and 0 <= request.context < contexts and
                        request.slice_mask == 255, 'Down seed request identity/profile')
                if workspace_transport is not None:
                    workspace_transport.seed_begin(request)
                require(lib.td_seed_begin(request.context) == 0, 'unchanged Down seed reserve')
                hashes['seed_requests'].update(struct.pack('<IIIBB', request.tag, request.sequence,
                    request.generation, request.context, request.slice_mask))
                counts['seed_begins'] += 1
            if edge.get('seed_beat_fire'):
                beat = edge['seed_beat']
                address = workspace.base + (n_base // 32 + beat.request.context) * CONTEXT_BYTES + down.prefix_ddr_beat(beat.index) * 64
                index = (address - workspace.base) // 64
                words, version = prefix.read64(address), versions[index]
                require(version == data_versions[index] == chunk_index and tuple(beat.words) == words and
                        read_versions[index, version] == 1 and seeded_versions[index, version] == 0,
                        'Down seed not exact once-only reread of ACK-written physical prefix version')
                require(beat.request.tag == job.tag and beat.request.sequence == group_sequence and
                        beat.request.generation == workspace.generation and not beat.error and
                        beat.last == (beat.index == 255), 'Down seed beat identity/status/LAST')
                if workspace_transport is not None:
                    workspace_transport.seed_beat(address, beat.request, beat.words)
                seeded_versions[index, version] += 1
                seed_counts[version] += 1
                seed_words[:] = beat.words
                seed_records.write(struct.pack('<IIIBBBB16I', beat.request.tag, beat.request.sequence,
                    beat.request.generation, beat.request.context, beat.index, beat.last, 0, *beat.words))
                require(lib.td_seed_beat(beat.request.context, beat.index, seed_words) == 0,
                        'unchanged Down seed physical beat')
                counts['seed_beats'] += 1
                if beat.last:
                    require(seed_ack is None and lib.td_seed_commit(beat.request.context) == 0,
                            'unchanged Down complete physical seed commit')
                    seed_ack = down.SeedAck(beat.request)
            if edge.get('seed_ack_fire'):
                ack = inputs['seed_ack']
                key = (chunk_index, n_base // 32 + ack.request.context)
                require(seed_ack == ack and key not in seed_commits, 'duplicate or unsolicited seed ACK')
                if workspace_transport is not None:
                    workspace_transport.seed_ack(ack)
                if matrix_bridge is not None:
                    matrix_bridge.retire_seed_ack(ack)
                seed_commits.add(key)
                hashes['seed_acks'].update(struct.pack('<IIIB?', ack.request.tag, ack.request.sequence,
                                                      ack.request.generation, ack.request.context, ack.error))
                seed_ack = None
                counts['seed_acks'] += 1
            if edge.get('read_fire'):
                require(pending_read is not None, 'Down read response without accepted descriptor')
                command, region, version, words = pending_read
                hashes['read_payloads'].update(struct.pack('<QQI', command.address, command.tag, len(words)))
                hashes['read_payloads'].update(struct.pack('<' + ('16I' if len(words) == 16 else '32H'), *words))
                if region == 'workspace':
                    index = (command.address - workspace.base) // 64
                    require(read_versions[index, version] == 0, 'duplicate physical prefix version reread')
                    if workspace_transport is not None:
                        workspace_transport.retire_read(command, words)
                    read_versions[index, version] += 1
                    prefix_reads[version] += 1
                    prefix_record('read', command.address, version, words)
                counts['read_responses'] += 1
                region_counts[region + '_read_beats'] += 1
                pending_read = None
            if edge.get('read_command_fire'):
                command = edge['read_command']
                require(pending_read is None and command.beats == 1 and command.address % 64 == 0 and
                        command.tag == (job.tag << 32) | (initial_read_sequence + counts['read_descriptors']),
                        'Down read descriptor overlap/shape/tag sequence')
                region, words = read64(command)
                version = None
                if region == 'workspace':
                    index = (command.address - workspace.base) // 64
                    version = versions[index]
                    require(command.kind == 'prefix' and version == data_versions[index] == chunk_index and
                            version in prefix_versions and prefix_writes[version] == prefix_beats,
                            'Down prefix read before complete ACK-written sweep')
                elif region == 'act':
                    require(command.kind == 'a' and job.a <= command.address and
                            command.address + 64 <= job.a + job.m * job.k * 4 and len(words) == 16 and
                            command.address not in act_reads, 'Down actual act physical address/coverage')
                    row, k = divmod((command.address - job.a) // 4, job.k)
                    require(0 <= row < job.m and chunk_start <= k and k + 16 <= chunk_end,
                            'Down A read outside actual global-K chunk stride')
                    act_reads.add(command.address)
                elif region == 'down_weight':
                    require(command.kind == 'b' and job.b <= command.address and
                            command.address + 64 <= job.b + job.k * job.n * 2 and len(words) == 32 and
                            command.address not in weight_reads, 'Down weight physical address/coverage')
                    k, n = divmod((command.address - job.b) // 2, job.n)
                    require(chunk_start <= k < chunk_end and n_base <= n and n + 32 <= n_base + contexts * 32,
                            'Down B read outside full-N physical stride/current group')
                    weight_reads.add(command.address)
                else:
                    raise ValueError('Down operand physical address selected unexpected region: ' + str(region))
                pending_read = (command, region, version, tuple(words))
                hashes['read_descriptors'].update(struct.pack('<BQQI', {'a': 0, 'b': 1, 'prefix': 2}[command.kind],
                                                              command.address, command.tag, command.beats))
                counts['read_descriptors'] += 1
                counts[command.kind + '_read_descriptors'] += 1
            if edge.get('step_fire'):
                step = edge['step']
                require(chunk_start <= step.k < chunk_end and 0 <= step.context < contexts and
                        step.clear == (step.k == 0) and step.last == (step.k + 1 == chunk_end) and
                        step.finish == (step.last and step.context + 1 == contexts) and step.emit == step.last,
                        'Down accepted Matrix global-K/clear/terminal semantics')
                require(len(step.a) == 16 and len(step.b) == 256 and
                        all(word == 0 for word in step.b[job.m:128]) and
                        all(word == 0 for word in step.b[144:256]),
                        'Down inactive physical rows or packet padding are not zero')
                operand_a[:], operand_b[:] = step.a, step.b
                hashes['steps'].update(struct.pack('<IIHBBBBBB', group_sequence, n_base, step.k,
                    step.context, step.clear, step.last, step.finish, step.emit, 0))
                hashes['steps'].update(bytes(operand_a)); hashes['steps'].update(bytes(operand_b))
                returned = lib.td_step(step.k, step.context, step.clear, step.last, step.finish, step.emit,
                                       operand_a, operand_b, physical)
                require(returned >= 0 and bool(returned) == step.last, 'unchanged Down accepted-step arithmetic')
                counts['accepted_steps'] += 1
                counts['observed_valid_logical_cells'] += job.m * 32
                counts['completed_host_physical_fmas'] += 4096
                if returned:
                    tile = tuple(tuple(physical[r * 256 + c] for c in range(256)) for r in range(16))
                    results.append(down.MatrixResult(step.context, tile))
                    result_peak = max(result_peak, len(results))
            if edge.get('result_fire'):
                result = results.popleft()
                require(result == inputs['result'], 'Down Matrix result queue handshake mismatch')
                if matrix_bridge is not None:
                    matrix_bridge.retire_result(result)
                raw = b''.join(struct.pack('<256I', *row) for row in result.value)
                hashes['results'].update(struct.pack('<II', group_sequence, result.context)); hashes['results'].update(raw)
                if chunk_index < final_chunk:
                    key = (chunk_index + 1, n_base // 32 + result.context)
                    require(key not in physical_result_hashes, 'duplicate physical prefix Matrix result')
                    physical_result_hashes[key] = sha(raw)
                counts['accepted_results'] += 1
            if edge.get('write_command_fire'):
                command = edge['write_command']
                require(pending_write is None and pending_ack is None and not staged and
                        command.address % 64 == 0 and 1 <= command.beats <= 16 and
                        command.address // 1024 == (command.address + command.beats * 64 - 1) // 1024 and
                        command.tag == (job.tag << 32) | (initial_write_sequence + counts['write_descriptors']),
                        'Down write descriptor overlap/alignment/1KiB/tag sequence')
                if prefix is not None and prefix.contains(command.address, command.beats * 64):
                    region = 'workspace'
                    require(chunk_index < final_chunk and command.beats == 1, 'Down final chunk prefix write/physical beat')
                elif destination.contains(command.address, command.beats * 64):
                    region = 'down'
                    require(chunk_index == final_chunk, 'Down final output published before final chunk')
                else:
                    raise ValueError('Down write escaped physical prefix/output spans')
                pending_write = (command, 0, chunk_index, region)
                hashes['write_descriptors'].update(struct.pack('<QQI', command.address, command.tag, command.beats))
                counts['write_descriptors'] += 1
                region_counts[region + '_write_descriptors'] += 1
                if region == 'workspace' and workspace_transport is not None:
                    workspace_transport.write_event('command', command)
                if region == 'down' and output_event is not None:
                    output_event('command', command)
            if edge.get('write_data_fire'):
                require(pending_write is not None, 'Down write data without accepted descriptor')
                command, index, write_chunk, region = pending_write
                beat = edge['write_data']
                explicit_mask = hasattr(beat, 'mask')
                mask = beat.mask if explicit_mask else FULL_MASK
                saw_explicit_mask |= explicit_mask
                saw_implicit_mask |= not explicit_mask
                require(mask == FULL_MASK and len(beat.words) == 16 and
                        beat.last == (index + 1 == command.beats) and index < command.beats,
                        'Down write data full 64-byte mask/width/LAST')
                address, words = command.address + index * 64, tuple(beat.words)
                if region == 'workspace':
                    beat_index, version = (address - workspace.base) // 64, write_chunk + 1
                    old = versions[beat_index]
                    require(data_versions[beat_index] == old == version - 1,
                            'duplicate or skipped physical prefix version write')
                    if version == 1:
                        require(prefix.read64(address) == (SENTINEL_WORD,) * 16,
                                'initial physical prefix was not sentinel-backed')
                    else:
                        require(read_versions[beat_index, old] == 1 and seeded_versions[beat_index, old] == 1 and
                                (write_chunk, (address - workspace.base) // CONTEXT_BYTES) in seed_commits,
                                'physical prefix overwrite before exact old version reread and seed ACK')
                    if workspace_transport is not None:
                        workspace_transport.write_event('data', beat)
                    else:
                        prefix.write64(address, words)
                    data_versions[beat_index] = version
                else:
                    require(address not in written and destination.read64(address) == (SENTINEL_WORD,) * 16,
                            'duplicate or non-sentinel Down output store')
                    destination.write64(address, words)
                    written.add(address)
                staged.append((address, words))
                hashes['write_data'].update(struct.pack('<QQ?16I', address, mask, beat.last, *words))
                counts['write_data_beats'] += 1
                region_counts[region + '_write_data_beats'] += 1
                pending_write = (command, index + 1, write_chunk, region)
                if beat.last:
                    require(pending_ack is None, 'duplicate Down pending write ACK')
                    pending_ack = down.WriteAck(command.tag, nbytes=command.beats * 64)
                if region == 'down' and output_event is not None:
                    output_event('data', beat)
            if edge.get('write_ack_fire'):
                require(pending_write is not None and pending_ack is not None, 'Down ACK without accepted write')
                command, index, write_chunk, region = pending_write
                ack = inputs['write_ack']
                require(ack == pending_ack and not ack.error and ack.tag == command.tag and
                        ack.nbytes == command.beats * 64 and index == command.beats and len(staged) == command.beats,
                        'Down ACK tag/error/byte count or premature ACK')
                for address, words in staged:
                    if region == 'workspace':
                        beat_index, version = (address - workspace.base) // 64, write_chunk + 1
                        old = versions[beat_index]
                        require(data_versions[beat_index] == version and old == version - 1 and
                                prefix.read64(address) == words, 'physical prefix differs at real ACK')
                        versions[beat_index] = version
                        prefix_writes[version] += 1
                        prefix_record('ack_write', address, version, words, old)
                        context, local_beat = divmod(beat_index, 256)
                        if local_beat == 255:
                            first = GUARD_BYTES + context * CONTEXT_BYTES
                            require(sha(prefix.data[first:first + CONTEXT_BYTES]) == physical_result_hashes[version, context],
                                    'full 4096-cell physical prefix differs from accepted Matrix result')
                            counts['full_physical_prefix_context_checks'] += 1
                    else:
                        require(address not in acknowledged and destination.read64(address) == words,
                                'duplicate or mutated acknowledged Down output')
                        acknowledged.add(address)
                hashes['write_acks'].update(struct.pack('<Q?I', ack.tag, ack.error, ack.nbytes))
                counts['write_acks'] += 1
                region_counts[region + '_write_acks'] += 1
                region_counts[region + '_ack_bytes'] += ack.nbytes
                if region == 'workspace' and workspace_transport is not None:
                    workspace_transport.write_event('ack', ack)
                if region == 'down' and output_event is not None:
                    output_event('ack', ack)
                if region == 'down' and len(acknowledged) * 64 == job.write_bytes:
                    require(final_ack_stall_remaining == 0, 'final Down ACK was not deliberately held')
                    final_ack_tick = owner.clock
                    trace.event(dict(kind='down_final_ack', tick=owner.clock, ack_bytes=owner.write_bytes,
                                     tag=ack.tag, nbytes=ack.nbytes))
                pending_write = pending_ack = None
                staged = []
            if 'matrix_done' in inputs and edge['matrix_done_ready']:
                require(group_sequence not in matrix_done_groups, 'duplicate Down MatrixDone')
                if matrix_bridge is not None:
                    matrix_bridge.retire_done(inputs['matrix_done'])
                matrix_done_groups.add(group_sequence)
                hashes['matrix_done'].update(struct.pack('<II', group_sequence, job.tag))
                counts['matrix_done_handshakes'] += 1
                trace.event(dict(kind='down_matrix_done', tick=owner.clock, sequence=group_sequence))
            if edge.get('response_fire'):
                require(final_ack_tick is not None and owner.clock > final_ack_tick and
                        len(acknowledged) * 64 == job.write_bytes and not pending_ack,
                        'Down response before accepted final ACK fence')
                finished = edge['response']
                counts['response_handshakes'] += 1
                trace.event(dict(kind='down_terminal', tick=owner.clock, response=finished))

        require(finished == (job.tag, None, job.write_bytes) and owner.state == 'idle' and
                owner.responses == initial_responses + 1 and counts['response_handshakes'] == 1,
                'full Down owner terminal status/tag/byte count')
        require(not any((pending_read, pending_write, pending_ack, results, staged, seed_ack, held)) and
                not any((owner.read_active, owner.a_hold, owner.a_rmw_pending, owner.pending, owner.fifo,
                         owner.final_value, owner.seed_outstanding)) and owner.write_state == 'idle',
                'Down terminal with outstanding external/owner obligation')
        require(len(groups) == len(expected_groups) and matrix_done_groups == {g['sequence'] for g in groups} and
                owner.completed_prefix_sweeps == final_chunk and owner.committed_prefix_end == chunks[-1][0] and
                owner.prefix_bytes == final_chunk * active_prefix_extent and counts['seed_acks'] == final_chunk * contexts_total and
                counts['full_physical_prefix_context_checks'] == final_chunk * contexts_total,
                'Down chunk/sweep/full physical prefix completion')
        for version in prefix_versions:
            require(prefix_writes[version] == prefix_reads[version] == seed_counts[version] == prefix_beats and
                    all(read_versions[index, version] == seeded_versions[index, version] == 1
                        for index in range(prefix_beats)), 'Down incomplete exact-version read/seed sweep')
        require(counts['accepted_steps'] == job.k * contexts_total == owner.accepted_steps and
                counts['accepted_results'] == len(chunks) * contexts_total and
                counts['a_read_descriptors'] == job.m * job.k // 16 and
                counts['b_read_descriptors'] == job.k * contexts_total and
                owner.rmw_commits == job.m * job.k and
                counts['read_descriptors'] == counts['read_responses'], 'Down accepted arithmetic/input completeness')
        require(act_reads == set(range(job.a, job.a + job.m * job.k * 4, 64)) and
                weight_reads == set(range(job.b, job.b + job.k * job.n * 2, 64)),
                'Down actual act/weight full physical once-only read coverage')
        require(written == acknowledged == set(range(job.dst, job.dst + job.write_bytes, 64)) and
                region_counts['down_ack_bytes'] == owner.write_bytes == job.write_bytes and
                region_counts['workspace_ack_bytes'] == owner.prefix_bytes and
                counts['write_descriptors'] == counts['write_acks'], 'Down full physical output/ACK coverage')
        owner_deltas = dict(read_descriptors=owner.read_sequence - initial_read_sequence,
                            write_descriptors=owner.write_sequence - initial_write_sequence,
                            groups=owner.group_sequence - initial_group_sequence,
                            responses=owner.responses - initial_responses)
        require(owner_deltas == dict(read_descriptors=counts['read_descriptors'],
                                    write_descriptors=counts['write_descriptors'],
                                    groups=counts['groups'], responses=counts['response_handshakes']),
                'Dense per-job owner sequence/counter deltas differ from accepted traffic')
        require(all(version == final_chunk for version in versions) and versions == data_versions and
                (sha(memory.act.data[GUARD_BYTES:-GUARD_BYTES]) if legacy_down else
                 a_source.validate(job)) == initial_act_hash,
                'Down prefix final version or source act mutation')
        if prefix is not None:
            prefix.check_guards()
        destination.check_guards()
        check_identity(); check_budget()
        if workspace_transport is not None:
            workspace_transport.finish()
        raw = destination.raw()
        output_path = 'actual_down.f32le' if legacy_down else 'actual_dense.f32le'
        (out / output_path).write_bytes(raw)
        report = dict(scope=('ACTUAL_SAME_OWNER_DENSE_HOST_MODEL_ONLY' if not legacy_down else
                             'SYNTHETIC_TINY_DOWN_HOST_MODEL_ONLY' if synthetic_geometry else
                             'ACTUAL_SAME_OWNER_FULL_DOWN_HOST_MODEL_ONLY'),
            synthetic_geometry=synthetic_geometry, job=asdict(job),
            completed=True, completion=list(finished), owner_completed_before_comparison=True,
            same_owner_and_banks=True, owner_resets=0, decoded_job_handshake=True,
            accepted=dict(counts), physical_traffic=dict(region_counts), groups=groups,
            useful_macs=counts['observed_valid_logical_cells'],
            executed_macs=counts['completed_host_physical_fmas'],
            counter_provenance='Harness observations incremented after each successful accepted td_step: m*32 valid logical cells and 4096 host physical FMAs; inactive rows and packet padding checked. These are not RTL measurements or hardware cycles, and do not substitute for the Chisel (physicalSteps - physicalBase)*512 accounting.',
            actual_act_source=dict(base=job.a, bytes=job.m * job.k * 4, sha256=initial_act_hash,
                actual_prior_ack_written=legacy_down or a_source.provenance == 'published',
                unchanged=True, read_beats=len(act_reads),
                full_once_only_read_coverage=True),
            prefix=dict(base=workspace.base, extent=workspace.extent, generation=workspace.generation,
                initial_sha256=prefix.initial_sha256 if prefix is not None else sha(b''),
                sentinel_word_hex=hex(SENTINEL_WORD),
                final_sha256=sha(prefix.raw()) if prefix is not None else sha(b''),
                completed_sweeps=owner.completed_prefix_sweeps,
                committed_prefix_end=owner.committed_prefix_end, ack_bytes=owner.prefix_bytes,
                versions={str(v): dict(ack_beats=prefix_writes[v], read_beats=prefix_reads[v],
                                      seed_beats=seed_counts[v]) for v in prefix_versions},
                physical_sweeps=prefix_sweeps, exact_version_read_before_overwrite=True,
                seed_ack_before_overwrite=True, all_4096_cells_checked_each_context=True,
                canaries_exact=True, guard_bytes=2 * GUARD_BYTES if prefix is not None else 0,
                transaction_records=prefix_records.report(), seed_records=seed_records.report(),
                seed_record_format='<IIIBBBB16I', seed_record_bytes=80),
            ddr=dict(base=job.dst, bytes=job.write_bytes, data_bytes=len(written) * 64,
                ack_bytes=len(acknowledged) * 64, unique_write_beats=len(written),
                full_once_only_coverage=True, initial_sha256=destination.initial_sha256,
                sentinel_word_hex=hex(SENTINEL_WORD), canaries_exact=True, guard_bytes=2 * GUARD_BYTES,
                burst_max_beats=16, all_bursts_within_1kib=True, all_full_64byte_writes=True,
                explicit_mask_observed=saw_explicit_mask, implicit_mask_observed=saw_implicit_mask,
                mask_contract='Inherited ordinary Down WriteBeat has no mask field; all sixteen FP32 words form an implicit full 64-byte write. Any explicit mask is checked against 0xffffffffffffffff.',
                sha256=sha(raw), path=output_path),
            final_ack_fence=dict(held_ticks=final_ack_stall_ticks, final_ack_tick=final_ack_tick,
                terminal_tick=owner.clock, terminal_strictly_after_final_ack=True),
            hashes={name: value.hexdigest() for name, value in hashes.items()},
            same_five_host_banks_erased_at_every_group=True, physical_result_fifo_peak=result_peak,
            operand_reservation_peak=owner.max_reserved if legacy_down else operand_peak,
            actual_a_rmw_commits=owner.rmw_commits,
            owner_start_tick=start_tick, owner_completion_tick=owner.clock,
            protocol_model_ticks=owner.clock - start_tick, protocol_model_ticks_are_hardware_cycles=False,
            arithmetic='Unchanged td_group/td_step/td_seed_* called only for accepted physical packets',
            reference_arithmetic_executed=False, saved_phase13_decoded=False,
            rtl_generated=False, actual_idma=False, hardware_arithmetic_executed=False,
            native_m128_and_fp32_final_acceptance='UNCHANGED_FAIL_POLICY_PENDING',
            trace=trace.report(), host_wall_seconds=time.monotonic() - started)
        if not legacy_down:
            report['actual_a_source'] = report.pop('actual_act_source')
            report['actual_a_source']['provenance'] = a_source.provenance
            report['prefix']['active_extent'] = active_prefix_extent
            report['owner_counter_deltas'] = owner_deltas
            report['output_transport'] = 'Actual accepted command/data/ACK events; terminal publishes only after final ACK'
        if workspace_transport is not None:
            report['prefix'].update(shared_public_allocation=True,
                active_extent=active_prefix_extent, reserved_extent=workspace_transport.extent,
                inactive_tail_pristine=True, public_epoch=workspace_transport.epoch,
                transport_accepted=dict(workspace_transport.counts))
        if output_event is not None:
            output_event('terminal', finished)
        return report, destination
    except Exception as error:
        if workspace_transport is not None:
            workspace_transport.invalidate(type(error).__name__ + ': ' + str(error))
        raise
    finally:
        seed_records.close()
        prefix_records.close()
