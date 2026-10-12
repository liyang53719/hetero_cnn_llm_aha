#!/usr/bin/env python3
"""Actual decoded-model full FFN: n1 -> 56 resident windows -> DDR act -> Down.

No Host parser, Scala, RTL, native FPU or hardware-cycle execution is claimed.
Predecessor models and C++ arithmetic are imported unchanged. Only accepted
physical transactions populate arithmetic inputs, outputs and workspace data.
Saved producer outputs and independent references are inaccessible until the
final Down ACK and terminal. Native/FP32-final acceptance remains pending.
"""
from array import array
from collections import Counter, deque
import argparse
import ctypes as C
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import resource
import struct
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
TASK = Path(__file__).resolve().parent
EXACT_HEAD = '6510a1d4f4dd6b6bb7ca6ceb3df72655e3d8ab67'
K, WIDTH, WINDOW = 1536, 8960, 160
DOWN_WEIGHT_BASE, DOWN_BASE, PREFIX_BASE = 0x6000000, 0xB000000, 0x10000000
IDENTITY = 0x51464700


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


drain_check = load_module('fullgroup_drain_check', TASK.parent / 'ffn_drain/check_numeric.py')
window_check = drain_check.window_check
tile_check = load_module('fullgroup_tile_check', TASK.parent / 'ffn_tiles/check_numeric.py')
model = load_module('fullgroup_drain_model', TASK.parent / 'ffn_drain/model.py')
group = load_module('fullgroup_coordinator_model', TASK.parent / 'ffn_group/model.py')
require, sha, file_sha = drain_check.require, drain_check.sha, drain_check.file_sha
SOURCE_BASES, DESTINATION_BASES = window_check.SOURCE_BASES, window_check.DESTINATION_BASES


class CappedTrace:
    """Hash every byte, persist only a bounded prefix; no unbounded tick JSON."""
    def __init__(self, path=None, cap=131072):
        self.stream = path.open('wb') if path else None
        self.cap, self.total, self.saved, self.records = cap, 0, 0, 0
        self.digest = hashlib.sha256()
        self.truncated = False

    def write(self, raw):
        self.digest.update(raw)
        self.total += len(raw)
        self.records += 1
        if self.stream and not self.truncated and self.saved + len(raw) <= self.cap:
            self.stream.write(raw)
            self.saved += len(raw)
        elif self.stream:
            self.truncated = True
        return len(raw)

    def event(self, value):
        self.write((json.dumps(value, default=drain_check.jsonable, sort_keys=True,
                               separators=(',', ':')) + '\n').encode())

    def report(self):
        if self.stream:
            self.stream.flush()
        return dict(sha256=self.digest.hexdigest(), records=self.records,
                    total_bytes_hashed=self.total, persisted_prefix_bytes=self.saved,
                    prefix_cap_bytes=self.cap)

    def close(self):
        if self.stream:
            self.stream.close()
            self.stream = None


class FullDestination(drain_check.DestinationMemory):
    def read64(self, address):
        require(self.pending is None and self.ack_bytes == self.extent,
                'act DDR cannot be read before all actual group ACKs')
        require(address in self.write_addresses and address % 64 == 0,
                'act read was not previously physically written')
        offset = drain_check.CANARY_BYTES + address - self.base
        return tuple(struct.unpack('<16I', self.data[offset:offset + 64]))

    def validate_full(self):
        require(self.pending is None and self.acks == self.descriptors and
                self.data_bytes == self.ack_bytes == self.extent,
                'full act DDR final ACK/byte fence')
        require(self.write_addresses == set(range(self.base, self.base + self.extent, 64)),
                'full act DDR exact once-only address coverage')
        require(self.data[:64] == self.initial[:64] and self.data[-64:] == self.initial[-64:],
                'act guard corruption')
        raw = bytes(self.data[64:-64])
        return raw, dict(bytes=self.extent, ack_bytes=self.ack_bytes, descriptors=self.descriptors,
                         acks=self.acks, unique_write_beats=len(self.write_addresses),
                         canaries_exact=True, sha256=sha(raw))


class Memory:
    """Operand selection only by physical address, never role/kind/job/state."""
    def __init__(self, inputs, rows):
        self.source = window_check.SourceMemory({k: v for k, v in inputs.items() if k != 'down_weight'})
        self.down_weight = inputs['down_weight']
        self.act = FullDestination(rows)
        self.virtual = {name: bytearray(struct.pack('<I', drain_check.SENTINEL_WORD) * (rows * WIDTH))
                        for name in ('gate', 'up')}
        self.virtual_hashes = {name: sha(raw) for name, raw in self.virtual.items()}
        self.regions = self.source.regions + [(DOWN_WEIGHT_BASE, DOWN_WEIGHT_BASE + len(self.down_weight) * 2, 'down_weight'),
            (self.act.base, self.act.base + self.act.extent, 'act')]
        spans = self.regions + [(base, base + rows * WIDTH * 4, name)
                                for name, base in DESTINATION_BASES.items()]
        spans += [(DOWN_BASE, DOWN_BASE + rows * K * 4, 'down'),
                  (PREFIX_BASE, PREFIX_BASE + (K // 32) * 16384, 'workspace')]
        require(all(b <= c or d <= a for i, (a, b, _) in enumerate(spans)
                    for c, d, _ in spans[i + 1:]), 'full cross-command memory spans alias')
        self.spans = spans

    def read64(self, address):
        if DOWN_WEIGHT_BASE <= address < DOWN_WEIGHT_BASE + len(self.down_weight) * 2:
            require(address % 64 == 0, 'Down weight alignment')
            k, n = divmod((address - DOWN_WEIGHT_BASE) // 2, K)
            require(k < WIDTH and n + 32 <= K, 'Down full-stride weight address')
            return 'down_weight', tuple(self.down_weight[(n + lane) * WIDTH + k] for lane in range(32))
        if self.act.base <= address < self.act.base + self.act.extent:
            return 'act', self.act.read64(address)
        return self.source.read64(address)

    def check_virtual(self):
        require({name: sha(raw) for name, raw in self.virtual.items()} == self.virtual_hashes,
                'virtual Gate/Up DDR changed')
        return dict(initial_and_final_sha256=self.virtual_hashes, bytes_each=len(self.virtual['gate']),
                    unchanged=True, physical_writes=0)


def request_for(rows, identity=IDENTITY):
    jobs = {}
    for slot, role in enumerate(('gate', 'up')):
        jobs[role] = group.Job('Dense', identity + slot, SOURCE_BASES['n1'],
            SOURCE_BASES[role + '_weight'], DESTINATION_BASES[role], rows, WIDTH, K,
            rows * WIDTH * 4, True, False, False)
    jobs['act'] = group.Job('Activation', identity + 2, DESTINATION_BASES['gate'],
        DESTINATION_BASES['up'], drain_check.ACT_BASE, rows, WIDTH, WIDTH,
        rows * WIDTH * 4, False, False, False)
    return group.GroupRequest(jobs['gate'], jobs['up'], jobs['act'], identity)


def decode_job(job):
    cls = model.ActivationJob if job.kind == 'Activation' else model.Job
    result = cls(**asdict(job))
    result.validate()
    require(all(getattr(result, key) == value for key, value in asdict(job).items()),
            'decoded-model job field mismatch')
    return result


class Coupled:
    """One actual coordinator edge for each owner edge; no fabricated terminals."""
    def __init__(self, owner, request, trace, deadline):
        self.owner, self.call, self.trace, self.deadline = owner, request, trace, deadline
        self.c = group.ResidentCoordinator()
        self.counts = Counter()
        self.active_steps = self.active_useful = self.active_executed = 0
        self.window_reports, self.drain_reports = [], []
        self.silu_busy = False
        self.terminal = None
        self.handoffs = []
        self.bank_ids = (id(owner.a_banks), id(owner.b_banks), id(owner.tiles.banks))

    def services(self):
        p = self.owner.ports()
        return group.Services(window_busy=self.owner.window_request is not None and p['busy'],
            drain_busy=self.owner.drain_request is not None and p['busy'], tiles_drained=self.owner.tiles.idle,
            tiles_leased=self.owner.tiles.leased, silu_drained=not self.silu_busy,
            bridge_busy=self.silu_busy, lease_valid=self.owner.lease is not None,
            window_reset=bool(self.owner.error), drain_reset=bool(self.owner.drain_poison),
            bridge_reset=self.owner.tiles.poison)

    def tick(self, *, start=False, silu_accept=False, silu_complete=False,
             group_result_ready=False, allow_fault=False, **inputs):
        require(time.monotonic() <= self.deadline, 'full group host budget exceeded')
        svc, p = self.services(), self.owner.ports()
        cp = self.c.ports(svc, abort=inputs.get('abort', False) or inputs.get('local_reset', False))
        # The published coordinator owns the sticky abort fence. Retire already
        # accepted responses, but the facade must not issue new tile requests.
        inputs['abort'] = inputs.get('abort', False) or cp['backend_abort']
        if cp['backend_abort']:
            for key in ('tile_control', 'tile_write', 'tile_read'):
                inputs.pop(key, None)
        wr = p.get('window_result')
        dr = p.get('drain_result')
        converted_w = None if wr is None else group.WindowResult(**asdict(wr),
            useful_macs=self.active_useful, executed_macs=self.active_executed)
        converted_d = None if dr is None else group.DrainResult(**{
            k: v for k, v in asdict(dr).items() if k != 'model_ticks'})
        if cp['handoff'] is not None:
            require(self.owner.state == 'idle' and self.owner.tiles.idle,
                    'coordinator handoff before backend quiescence')
            self.handoffs.append(asdict(cp['handoff']))
        inputs.update(window_result_ready=cp['window_result_ready'],
                      drain_result_ready=cp['drain_result_ready'],
                      invalidate_lease=cp['invalidate_lease'])
        if cp['invalidate_lease'] and not cp['backend_abort'] and not allow_fault:
            require(len(self.drain_reports) == WIDTH // WINDOW, 'lease invalidated before all 56 output terminals')
        ce = self.c.tick(request=self.call if start else None, services=svc,
            window_ready=bool(inputs.get('window')) and p.get('window_ready', False),
            drain_ready=bool(inputs.get('drain')) and p.get('drain_ready', False),
            silu_ready=silu_accept, silu_complete=silu_complete,
            window_result=converted_w, drain_result=converted_d,
            result_ready=group_result_ready, abort=inputs.get('abort', False),
            local_reset=inputs.get('local_reset', False))
        e = self.owner.tick(**inputs)
        if cp['backend_abort'] and self.owner.tiles.idle:
            self.silu_busy = False
        for a, b in (('window_fire', 'window_fire'), ('drain_fire', 'drain_fire'),
                     ('window_result_fire', 'window_result_fire'), ('drain_result_fire', 'drain_result_fire')):
            require(bool(ce[a]) == bool(e.get(b)), 'coordinator/backend handshake disagreement: ' + a)
        if ce['window_fire']:
            self.active_steps = self.active_useful = self.active_executed = 0
            self.counts['windows_accepted'] += 1
        if e.get('step_fire'):
            self.active_steps += 1
        if ce['window_result_fire']:
            self.window_reports.append(asdict(converted_w))
        if ce['drain_result_fire']:
            self.drain_reports.append(asdict(converted_d))
        if ce['result_fire']:
            self.terminal = ce['result']
        self.counts['model_ticks'] += 1
        for name in ('request_fire', 'result_fire', 'window_fire', 'drain_fire', 'silu_fire',
                     'window_result_fire', 'drain_result_fire'):
            self.counts[name] += bool(ce[name])
        if ce['state'] != self.c.state or any(ce[name] for name in ('window_fire', 'drain_fire', 'silu_fire',
                'window_result_fire', 'drain_result_fire', 'result_fire')):
            self.trace.event(dict(tick=self.counts['model_ticks'], coordinator=ce,
                                  state_after=self.c.state, services=svc))
        require(self.bank_ids == (id(self.owner.a_banks), id(self.owner.b_banks), id(self.owner.tiles.banks)),
                'physical owner/banks replaced')
        if not allow_fault:
            require(not self.owner.error and not self.c.poison and not self.owner.tiles.poison,
                    'coupled backend fault: ' + str(self.owner.error or self.c.status))
        return e, ce

    def next_request(self, name):
        for _ in range(8):
            p = self.c.ports(self.services())
            if p[name] is not None:
                return p[name]
            self.tick()
        raise ValueError('coordinator failed to produce ' + name)


class CoupledTilePort:
    def __init__(self, coupled):
        self.h, self.banks = coupled, coupled.owner.a_banks

    @property
    def poison(self):
        return self.h.c.poison or self.h.owner.tiles.poison or bool(self.h.owner.error)

    def tick(self, *, control=None, write=None, read=None, response_ready=True):
        require(self.h.owner.state == 'idle', 'SiLU external port while owner busy')
        event, _ = self.h.tick(tile_control=control, tile_write=write, tile_read=read,
                               tile_response_ready=response_ready)
        require(not any(event.get(x) for x in ('read_command_fire', 'step_fire',
                    'window_fire', 'drain_fire', 'write_command_fire', 'write_data_fire')),
                'SiLU owner edge emitted unrelated traffic')
        return event['tile']


def execute_window(h, lib, memory, expected_ng, role):
    """New orchestration of unchanged actual ports; every request comes from c."""
    q = h.next_request('window_request')
    slot = int(role == 'up')
    require(q == group.WindowRequest(getattr(h.call, role), h.call.identity,
            expected_ng, WINDOW, slot, slot == 1 or expected_ng != 0),
            'coordinator window identity/base/dtype/stride/reuse mismatch')
    request = model.FfnWindowRequest(decode_job(q.job), q.identity, q.ng, q.cols, q.slot, q.reuse_a)
    e, ce = h.tick(window=request)
    require(e['window_fire'] and ce['window_fire'], 'window request was not accepted')
    pending, results, counts = None, deque(), Counter()
    descriptor_hash, packet_hash = hashlib.sha256(), hashlib.sha256()
    aa, bb, terminal = (C.c_uint16 * 16)(), (C.c_uint16 * 256)(), (C.c_uint32 * 4096)()
    first_b = last_b = None
    initial_read_sequence = h.owner.read_sequence
    done = False
    while True:
        p = h.owner.ports()
        kwargs = dict(step_ready=not (p['step'] is not None and p['step'].last and len(results) >= 2))
        if pending:
            kwargs['read_beat'] = model.ReadBeat(pending[0].tag, pending[1], True)
        if results:
            kwargs['result'] = results[0]
        o = h.owner
        if o.group_started and not o.group_done and o.group_accepted_steps == K * 5 and o.results_received == 5 and not results:
            kwargs['matrix_done'] = model.MatrixDone(q.job.tag)
        e, ce = h.tick(**kwargs)
        if e.get('group_fire'):
            counts['groups'] += 1
            require(counts['groups'] == 1 and lib.td_group(0, K, 5) == 0, 'window Matrix group')
        if e.get('read_fire'):
            require(pending is not None, 'response without actual descriptor')
            counts[pending[0].kind + '_reads'] += 1
            pending = None
        if e.get('read_command_fire'):
            cmd = e['read_command']
            require(pending is None and cmd.beats == 1 and cmd.address % 64 == 0 and
                    cmd.tag == ((q.job.tag << 32) | (initial_read_sequence + counts['read_descriptors'])),
                    'input descriptor shape/tag/overlap')
            region, words = memory.read64(cmd.address)
            if cmd.kind == 'a':
                require(not q.reuse_a and region == 'n1' and q.job.a <= cmd.address and
                        cmd.address + 64 <= q.job.a + q.job.m * K * 4 and
                        cmd.address == q.job.a + counts['a_descriptors'] * 64, 'A source/reuse range/order')
            else:
                source_k, source_n = divmod((cmd.address - q.job.b) // 2, WIDTH)
                require(cmd.kind == 'b' and region == role + '_weight' and 0 <= source_k < K and
                        q.ng <= source_n and source_n + 32 <= q.ng + q.cols and
                        cmd.address == q.job.b + ((counts['b_descriptors'] // 5) * WIDTH + q.ng +
                                                (counts['b_descriptors'] % 5) * 32) * 2,
                        'B source/full stride/window/order')
                first_b = cmd.address if first_b is None else first_b
                last_b = cmd.address
            pending = (cmd, words)
            counts['read_descriptors'] += 1
            counts[cmd.kind + '_descriptors'] += 1
            descriptor_hash.update(window_check.descriptor_record(cmd))
        if e.get('step_fire'):
            s = e['step']
            aa[:], bb[:] = s.a, s.b
            packet_hash.update(struct.pack('<HBBBBB', s.k, s.context, s.clear, s.last, s.finish, s.emit))
            packet_hash.update(bytes(aa)); packet_hash.update(bytes(bb))
            status = lib.td_step(s.k, s.context, s.clear, s.last, s.finish, s.emit, aa, bb, terminal)
            require(status >= 0 and bool(status) == s.last, 'physical packet arithmetic error')
            require(len(s.a) == 16 and len(s.b) == 256 and all(x == 0 for x in s.b[q.job.m:128]) and
                    all(x == 0 for x in s.b[144:]), 'physical packet invalid-row/padding lanes')
            counts['matrix_steps'] += 1
            counts['observed_valid_logical_cells'] += q.job.m * 32
            counts['completed_host_physical_fmas'] += 4096
            # Harness observations of successful accepted physical arithmetic,
            # absent from frozen Python terminal fields; not RTL counter reads.
            h.active_useful += q.job.m * 32
            h.active_executed += 4096
            if status:
                results.append(model.MatrixResult(s.context, tuple(tuple(terminal[r * 256 + n]
                    for n in range(256)) for r in range(16))))
        if e.get('result_fire'):
            results.popleft(); counts['matrix_results'] += 1
        if 'matrix_done' in kwargs and e['matrix_done_ready']:
            require(not done, 'duplicate MatrixDone'); done = True
        require(not e.get('write_command_fire') and not e.get('write_data_fire'), 'virtual Gate/Up DDR write')
        if ce['window_result_fire']:
            break
    require(done and not pending and not results and counts['matrix_steps'] == K * 5 and counts['matrix_results'] == 5,
            'window terminal before all actual backend obligations')
    require(counts['a_reads'] * 64 == (0 if q.reuse_a else q.job.m * K * 4) and
            counts['b_reads'] * 64 == K * WINDOW * 2 and o.a_fences == 1 and
            o.rmw_commits == (0 if q.reuse_a else q.job.m * K) and o.lease == model.ALease.for_request(request),
            'retained A actual load/reuse/count mismatch')
    require(first_b == q.job.b + q.ng * 2 and last_b == q.job.b + ((K - 1) * WIDTH + q.ng + WINDOW - 32) * 2,
            'B full-stride endpoints mismatch')
    return dict(request=asdict(q), accepted=dict(counts), descriptor_sha256=descriptor_hash.hexdigest(),
                physical_packet_sha256=packet_hash.hexdigest(), actual_a_rmw_commits=o.rmw_commits,
                actual_a_load_fences=o.a_fences, completion=h.window_reports[-1])


def execute_silu(h, lib, ng, outputs, trace):
    q = h.next_request('silu_request')
    require(q == group.SiluRequest(h.call.identity, ng, h.call.gate.m, WINDOW), 'SiLU request mismatch')
    _, ce = h.tick(silu_accept=True)
    require(ce['silu_fire'], 'SiLU request handshake')
    h.silu_busy = True
    case = dict(identity=q.identity, ng=q.ng, rows=q.rows, cols=q.cols)
    driver = tile_check.BankDriver(model.window.tiles, CoupledTilePort(h), case, trace, h.deadline)
    driver.control(0, 2)
    operands = [(C.c_uint32 * 16)() for _ in range(3)]
    values, flags, errors = (C.c_uint32 * 96)(), (C.c_uint32 * 96)(), (C.c_uint32 * 16)()
    phase_hash, phase_flags = hashlib.sha256(), Counter()
    for index in range(q.rows // 16 * WINDOW):
        g, u = driver.read(0, index), driver.read(1, index)
        row_group, n = divmod(index, WINDOW)
        for role, words in (('gate', g), ('up', u)):
            for lane, word in enumerate(words):
                outputs[role][(row_group * 16 + lane) * WIDTH + ng + n] = word
        operands[0][:], operands[1][:] = g, u
        require(lib.sf_vector(*operands, values, flags, errors) == 0, 'unchanged SiLU primitive policy error')
        phase_hash.update(bytes(values)); phase_flags.update(flags)
        driver.write(2, index, tuple(operands[2]))
    driver.control(1, 2)
    for slot in (0, 1):
        driver.control(2, slot)
    driver.check_storage()
    require(h.owner.tiles.tags[2].live and h.owner.tiles.tags[2].sealed, 'act slot not sealed')
    h.silu_busy = False
    h.tick(silu_complete=True)
    return dict(accepted_requests=q.rows // 16 * WINDOW, accepted=dict(driver.counts),
                phase_sha256=phase_hash.hexdigest(), phase_flags=dict(phase_flags))


def execute_drain(h, target, ng, *, final_ack_stall=3, corrupt_ack=False):
    q = h.next_request('drain_request')
    require(q == group.DrainRequest(h.call.act, h.call.identity, ng, WINDOW), 'drain request mismatch')
    request = model.FfnDrainRequest(decode_job(q.job), q.identity, q.ng, q.cols)
    e, ce = h.tick(drain=request)
    require(e['drain_fire'] and ce['drain_fire'], 'drain request handshake')
    before = target.data_bytes
    counts, hashes, held = Counter(), {key: hashlib.sha256() for key in ('descriptor', 'data', 'ack')}, {}
    remaining, final_seen = final_ack_stall, False
    while True:
        inputs = dict(write_command_ready=counts['ticks'] % 5 != 0,
                      write_data_ready=counts['ticks'] % 7 != 0)
        if target.awaiting_ack:
            cmd = target.pending
            final = target.data_bytes - before == q.job.m * WINDOW * 4
            if final and remaining:
                require(h.owner.ports()['drain_result'] is None and h.owner.tiles.tags[2].live and
                        h.owner.lease is not None and h.c.state == 'actWait', 'final ACK fence violated')
                remaining -= 1; counts['held_final_ack_ticks'] += 1
            else:
                inputs['write_ack'] = model.WriteAck(cmd.tag + int(corrupt_ack), False, cmd.beats * 64)
        e, ce = h.tick(allow_fault=corrupt_ack, **inputs)
        counts['ticks'] += 1
        require(not any(e.get(key) for key in ('read_command_fire', 'read_fire', 'step_fire', 'result_fire', 'group_fire')),
                'act drain emitted input DDR or Matrix traffic')
        for signal, ready in (('write_command', inputs['write_command_ready']), ('write_data', inputs['write_data_ready'])):
            if signal in held:
                require(e.get(signal) == held[signal], 'held DDR ' + signal + ' changed')
            if e.get(signal) is not None and not ready:
                held[signal] = e[signal]
            else:
                held.pop(signal, None)
        if e.get('write_command_fire'):
            cmd = e['write_command']
            require(cmd.tag >> 32 == q.job.tag, 'act descriptor job tag')
            target.accept_command(cmd)
            hashes['descriptor'].update(struct.pack('<QIQ', cmd.address, cmd.beats, cmd.tag))
            counts['descriptors'] += 1
        if e.get('write_data_fire'):
            beat = e['write_data']; address = target.accept_data(beat)
            hashes['data'].update(struct.pack('<QQ?16I', address, beat.mask, beat.last, *beat.words))
            counts['data_beats'] += 1
        if e.get('write_ack_fire'):
            if corrupt_ack:
                require(h.owner.error is not None, 'bad ACK did not fault backend')
                return dict(injected_bad_ack_rejected=True, accepted=dict(counts))
            ack = inputs['write_ack']; target.accept_ack(ack)
            hashes['ack'].update(struct.pack('<Q?I', ack.tag, ack.error, ack.nbytes))
            counts['acks'] += 1
            if target.ack_bytes - before == q.job.m * WINDOW * 4:
                final_seen = True; counts['final_ack_tick'] = counts['ticks']
        if ce['drain_result_fire']:
            require(final_seen and counts['ticks'] > counts['final_ack_tick'] and remaining == 0,
                    'terminal before held final ACK retired')
            break
    require(target.data_bytes - before == q.job.m * WINDOW * 4 and not h.owner.tiles.leased,
            'window act drain bytes/leases')
    return dict(request=asdict(q), accepted=dict(counts), completion=h.drain_reports[-1],
                hashes={key: val.hexdigest() for key, val in hashes.items()})


def execute_group(rows, lib, memory, out, deadline, *, window_limit=56):
    workspace = model.PrefixWorkspace(PREFIX_BASE, (K // 32) * 16384, IDENTITY, 2560)
    owner = model.FfnDrainOwnerModel(workspace, enable_ffn_window=True, enable_ffn_tiles=True, enable_ffn_drain=True)
    require(owner.tiles.banks is owner.a_banks and len(owner.a_banks.words) == 16 and
            len(owner.a_banks.words[0]) == 1376 and len(owner.b_banks.words) == 16 and
            len(owner.b_banks.words[0]) == 160, 'fixed physical owner bank geometry')
    trace = CappedTrace(out / 'coordinator_prefix.jsonl')
    h = Coupled(owner, request_for(rows), trace, deadline)
    _, ce = h.tick(start=True)
    require(ce['request_fire'], 'decoded group request was not accepted')
    outputs = {role: array('I', [drain_check.SENTINEL_WORD]) * (rows * WIDTH) for role in ('gate', 'up')}
    reports, retained = [], None
    tile_trace = CappedTrace(out / 'silu_events_prefix.jsonl')
    started = time.monotonic()
    for ng in range(0, window_limit * WINDOW, WINDOW):
        gate = execute_window(h, lib, memory, ng, 'gate')
        current = tile_check.bank_region_hash(owner.a_banks.words, 0, 768)
        if retained is None:
            retained = current
        require(current == retained, 'later Gate changed retained A')
        up = execute_window(h, lib, memory, ng, 'up')
        silu = execute_silu(h, lib, ng, outputs, tile_trace)
        drain = execute_drain(h, memory.act, ng)
        require(tile_check.bank_region_hash(owner.a_banks.words, 0, 768) == retained, 'Up/SiLU/drain changed retained A')
        reports.append(dict(ng=ng, gate=gate, up=up, silu=silu, drain=drain))
        with (out / 'completed_window_receipts.jsonl').open('a') as receipts:
            receipts.write(json.dumps(reports[-1], sort_keys=True, separators=(',', ':')) + '\n')
        (out / 'progress.json').write_text(json.dumps(dict(windows=len(reports), coordinator_state=h.c.state,
            accepted_act_ack_bytes=memory.act.ack_bytes, host_wall_seconds=time.monotonic() - started)) + '\n')
    if window_limit == 56:
        for _ in range(8):
            _, ce = h.tick(group_result_ready=True)
            if ce['result_fire']:
                break
        require(h.terminal is not None and h.terminal.status is None and h.c.state == 'idle' and owner.lease is None,
                'group terminal/lease invalidation incomplete')
        raw, ddr_report = memory.act.validate_full()
        outputs['act'] = array('I'); outputs['act'].frombytes(raw)
        expected_useful = sum(r['useful_macs'] for r in h.window_reports)
        expected_executed = sum(r['executed_macs'] for r in h.window_reports)
        require(h.terminal.write_bytes == memory.act.ack_bytes and h.terminal.useful_macs == expected_useful and
                h.terminal.executed_macs == expected_executed, 'coordinator accepted terminal counters mismatch')
    else:
        ddr_report = dict(partial_synthetic_windows=window_limit, ack_bytes=memory.act.ack_bytes)
    for role, words in outputs.items():
        (out / ('actual_' + role + '.f32le')).write_bytes(words.tobytes())
    report = dict(windows=reports, coordinator=dict(accepted=dict(h.counts), terminal=asdict(h.terminal) if h.terminal else None,
        window_terminals=h.window_reports, drain_terminals=h.drain_reports, handoffs=h.handoffs,
        cycles_unit='Python protocol-model ticks, not hardware cycles',
        counters_source='Harness observation: each successful accepted td_step executes 4096 physical FMAs; m*32 valid logical cells. Frozen Python owner lacks optional counter fields. Values are attached only to real terminals and accumulated on coordinator handshake. Chisel counter is independently (physicalSteps-physicalBase)*512; no RTL counter observation or timing equivalence claimed.'),
        ddr=ddr_report, virtual_outputs=memory.check_virtual(), same_owner_and_banks=True,
        resets_between_windows=0, retained_a_sha256=retained, owner_a_fences=owner.a_fences,
        coordinator_trace=trace.report(), silu_trace=tile_trace.report(),
        host_wall_seconds=time.monotonic() - started)
    trace.close(); tile_trace.close()
    return owner, h, outputs, report


def configure_down_library(lib):
    u16, u32 = C.POINTER(C.c_uint16), C.POINTER(C.c_uint32)
    lib.td_seed_begin.argtypes, lib.td_seed_begin.restype = [C.c_uint], C.c_int
    lib.td_seed_beat.argtypes, lib.td_seed_beat.restype = [C.c_uint, C.c_uint, u32], C.c_int
    lib.td_seed_commit.argtypes, lib.td_seed_commit.restype = [C.c_uint], C.c_int
    lib.td_reference.argtypes, lib.td_reference.restype = [u32, u16, u32, C.c_uint], C.c_int


def compare_after_terminal(pins, inputs, outputs, down_actual, lib, rows, out, deadline):
    """Only called after actual group and Down final ACKs/terminal consumption."""
    count = rows * WIDTH
    direct = {role: array('I', [0]) * count for role in ('gate', 'up', 'act')}
    ca = (C.c_uint32 * len(inputs['n1'])).from_buffer(inputs['n1'])
    for role in ('gate', 'up'):
        weight = inputs[role + '_weight']
        cw = (C.c_uint16 * len(weight)).from_buffer(weight)
        for ng in range(0, WIDTH, WINDOW):
            require(time.monotonic() <= deadline, 'independent reference budget exceeded')
            tile = (C.c_uint32 * (rows * WINDOW))()
            require(lib.fw_reference(ca, cw, tile, rows, WINDOW, ng) == 0, 'independent direct projection failed')
            for m in range(rows):
                direct[role][m * WIDTH + ng:m * WIDTH + ng + WINDOW] = array('I', tile[m * WINDOW:(m + 1) * WINDOW])
    args = [(C.c_uint32 * count).from_buffer(direct[role]) for role in ('gate', 'up', 'act')]
    require(lib.sf_reference(*args, count) == 0, 'independent direct SiLU failed')
    # The unchanged Down reference has a fixed M128 ABI. The M16-only direct
    # check pads the remaining 112 rows with zero AFTER actual completion.
    reference_act = array('I', outputs['act'])
    reference_act.extend([0] * ((128 - rows) * WIDTH))
    cw = (C.c_uint16 * len(inputs['down_weight'])).from_buffer(inputs['down_weight'])
    ca_down = (C.c_uint32 * len(reference_act)).from_buffer(reference_act)
    ref_down = (C.c_uint32 * (128 * K))()
    require(lib.td_reference(ca_down, cw, ref_down, K) == 0, 'independent Down failed')
    direct['down'] = array('I', ref_down[:rows * K])
    outputs['down'] = down_actual
    report = {}
    for role in ('gate', 'up', 'act', 'down'):
        require(time.monotonic() <= deadline, 'post-final-ACK comparison budget exceeded')
        raw = drain_check.checked_file(pins['comparison_only'][role])
        saved = array('I'); saved.frombytes(raw)
        actual, independent = outputs[role], direct[role]
        saved = saved[:len(actual)]
        require(len(actual) == len(independent) == len(saved), 'comparison lengths')
        item = dict(actual_sha256=sha(actual.tobytes()), direct_sha256=sha(independent.tobytes()),
                    saved_sha256=sha(saved.tobytes()))
        for name, expected in (('independent_direct', independent), ('saved_producer', saved)):
            differences = [i for i, (a, b) in enumerate(zip(actual, expected)) if a != b]
            item[name + '_bit_mismatches'] = len(differences)
            first = differences[0] if differences else None
            item[name + '_first_difference'] = None if first is None else dict(flat_index=first,
                actual_fp32_bits=hex(actual[first]), expected_fp32_bits=hex(expected[first]))
        report[role] = item
    return report


def freeze_sources(out, pins):
    """Capture all imported physical models, arithmetic and composition pins."""
    source_paths = set(pins['sources'])
    for dirname in ('ffn_fullgroup', 'ffn_group', 'ffn_drain', 'ffn_window', 'ffn_tiles', 'transposed_down'):
        for path in (TASK.parent / dirname).iterdir():
            if path.is_file() and path.suffix in ('.py', '.cpp', '.json', '.patch', '.scala'):
                source_paths.add(str(path.relative_to(ROOT)))
    composition_path = TASK.parent / 'ffn_group/source_pins.json'
    composition = json.loads(composition_path.read_text())
    for path, digest in composition['patches'].items():
        require(file_sha(ROOT / path) == digest, 'source composition patch drift: ' + path)
        source_paths.add(path)
    hashes = {}
    frozen = out / 'frozen_sources'
    for path in sorted(source_paths):
        raw = (ROOT / path).read_bytes()
        target = frozen / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        hashes[path] = sha(raw)
    return hashes, frozen


def run(out, rows=128, wall_budget=900, expected_head=EXACT_HEAD):
    import subprocess
    require(not out.exists(), 'use a new evidence directory')
    out.mkdir(parents=True)
    start, cpu_start = time.monotonic(), time.process_time()
    deadline = start + wall_budget
    report = dict(status='PREPARING', scope='DECODED_COORDINATOR_FULL_FFN_HOST_PORT_NUMERIC_MODEL_ONLY',
        rows=rows, source_baseline_commit=EXACT_HEAD,
        row_scope=('Rows 0-15 of frozen M128 n1 and saved producer comparisons; same official weights. This is not an independent official 16-token forward.'
                   if rows == 16 else 'All 128 rows of the frozen v0 n1 producer input; same official weights and saved v0 producer comparisons.'),
        hardware_arithmetic_executed=False, rtl_executed=False, actual_idma=False,
        public_host_parser_executed=False, host_production_coordinator_executed=False,
        resident_coordinator_python_model_executed=True, protocol_model_ticks_are_hardware_cycles=False,
        predicted_hardware_cycles=None, physical_resource_qor_established=False,
        full_wall_utilization=None, full_wall_denominator='4096 MACs times hardware wall cycles; unavailable in this host-model capture',
        full_block_executed=False, official_framework_forward=False,
        native_m128_and_fp32_final_acceptance='UNCHANGED_FAIL_POLICY_PENDING',
        fixed_resource_contract=dict(mac_units=4096, sram_bytes=768 * 1024, banks=32,
            bank_ports='1R1W', a_banks=16, a_depth_words=1376, b_banks=16, b_depth_words=160,
            word_bits=256, added_hardware_resources=0),
        budget=dict(wall_seconds=wall_budget, compile_timeout_seconds=30, single_host_process=True,
                    no_rtl_or_eda=True, local_trace_prefix_cap_each=131072))
    def save():
        (out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    try:
        require(sys.byteorder == 'little', 'little-endian host required')
        observed_head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        require(observed_head == expected_head, 'expected execution checkout HEAD mismatch')
        report['execution_checkout_head'] = observed_head
        report['host_resources_before'] = drain_check.host_preflight()
        pins = json.loads((TASK / 'precision_pins.json').read_text())
        baseline = drain_check.load_pins()
        report['origin'] = window_check.verify_provenance(baseline)
        for path, digest in pins['sources'].items():
            require(file_sha(ROOT / path) == digest, 'fullgroup frozen source drift: ' + path)
        manifest = json.loads((ROOT / 'work/qwen2_layer0_payload_20261011/manifest.json').read_text())
        down_tensor = [t for t in manifest['tensors'] if t['local_name'] == 'mlp.down_proj.weight']
        require(len(down_tensor) == 1 and down_tensor[0]['shape'] == [K, WIDTH] and
                down_tensor[0]['dtype'] == 'BF16' and down_tensor[0]['sha256'] == pins['inputs']['down_weight']['sha256'],
                'official Down weight provenance/shape mismatch')
        inputs = {}
        for name, spec in pins['inputs'].items():
            inputs[name] = array('I' if name == 'n1' else 'H')
            inputs[name].frombytes(drain_check.checked_file(spec))
        memory = Memory(inputs, rows)
        report['source_sha256'], frozen = freeze_sources(out, pins)
        report.update(status='PINNED_BEFORE_EXECUTION', pins=pins,
            source_memory=dict(selection='physical address only; lazy official output-major to K-major weight view',
                prelaunch_payloads=list(inputs), intermediate_prelaunch_payloads=[],
                act_initial='sentinel only', gate_up_destinations='sentinel only, no physical write traffic',
                workspace_initial='sentinel only', spans=memory.spans),
            comparison_boundary='Saved phase10/11/12/13 data are decoded only after group completion and actual full Down final ACK/terminal.')
        save()
        (out / 'FROZEN_PINS.json').write_text(json.dumps(report, indent=2) + '\n')
        lib, report['compile'] = drain_check.build_library(out, pins, frozen)
        configure_down_library(lib)
        owner, h, outputs, report['group'] = execute_group(rows, lib, memory, out, deadline)
        report.update(status='GROUP_DONE_DOWN_PENDING', actual_act_ddr_sha256=sha(outputs['act'].tobytes()))
        save()
        down_driver = load_module('fullgroup_down_driver', TASK / 'down_driver.py')
        job = model.Job(m=rows, k=WIDTH, n=K, tag=IDENTITY + 3, a=memory.act.base,
                        b=DOWN_WEIGHT_BASE, dst=DOWN_BASE, weight_bf16=True, activation_bf16=False,
                        output_bf16=False, write_bytes=rows * K * 4)
        trace = CappedTrace(out / 'down_events_prefix.jsonl')
        report['down'], actual_down = down_driver.execute_down(model, owner, lib, memory, job, out, deadline, trace)
        report['down_trace'] = trace.report(); trace.close()
        require(h.bank_ids == (id(owner.a_banks), id(owner.b_banks), id(owner.tiles.banks)), 'Down replaced physical banks')
        require(owner.lease is None and not owner.tiles.leased, 'Down left FFN tile leases')
        report['virtual_outputs_after_down'] = memory.check_virtual()
        report.update(status='DOWN_DONE_COMPARISON_PENDING', all_actual_final_acks_and_terminals_before_comparison=True)
        save()
        (out / 'actual_down.f32le').write_bytes(actual_down.tobytes())
        report['comparison'] = compare_after_terminal(pins, inputs, outputs, actual_down, lib, rows, out, deadline)
        require(all(item['independent_direct_bit_mismatches'] == item['saved_producer_bit_mismatches'] == 0
                    for item in report['comparison'].values()), 'actual full FFN differs from independent/saved outputs')
        require(all(sha(raw.tobytes()) == pins['inputs'][name]['sha256'] for name, raw in inputs.items()),
                'raw arithmetic source changed')
        report['source_sha256_after'] = {path: file_sha(ROOT / path) for path in report['source_sha256']}
        require(report['source_sha256'] == report['source_sha256_after'], 'capture source changed during run')
        report.update(status='PASS_ACTUAL_FULL_FFN_COORDINATOR_TO_DOWN_HOST_MODEL_ONLY',
            full_ffn_host_model_executed=True, same_owner_and_banks_through_down=True,
            host_wall_seconds=time.monotonic() - start, host_cpu_seconds=time.process_time() - cpu_start,
            host_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        save()
        return report
    except Exception as error:
        report.update(status='FAILED', error=str(error), host_wall_seconds=time.monotonic() - start,
                      host_cpu_seconds=time.process_time() - cpu_start)
        if 'memory' in locals():
            (out / 'failed_capture_actual_act_with_guards.bin').write_bytes(memory.act.data)
            report['failed_capture_act'] = dict(accepted_data_bytes=memory.act.data_bytes,
                accepted_ack_bytes=memory.act.ack_bytes, pending_descriptor=asdict(memory.act.pending) if memory.act.pending else None,
                sha256=sha(memory.act.data), comparison_permitted=False)
        if 'source_sha256' in report:
            report['source_sha256_after'] = {path: file_sha(ROOT / path) for path in report['source_sha256']}
        save()
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--rows', type=int, choices=(16, 128), default=128)
    parser.add_argument('--wall-budget', type=int, default=900)
    parser.add_argument('--expected-head', default=EXACT_HEAD)
    args = parser.parse_args()
    result = run(args.out.resolve(), args.rows, args.wall_budget, args.expected_head)
    print(json.dumps({key: result[key] for key in ('status', 'rows', 'host_wall_seconds', 'host_cpu_seconds')}))
