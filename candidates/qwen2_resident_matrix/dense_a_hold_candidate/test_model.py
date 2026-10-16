"""Cold transport/control tests; synthetic finite data, no arithmetic oracle."""
from collections import deque
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import random

import pytest

from candidates.qwen2_resident_matrix.dense_a_hold_candidate.model import (DenseAHoldModel, FfnWindowRequest, Job, MatrixDone,
                    MatrixResult, PrefixWorkspace, ReadBeat, SeedAck, WriteAck,
                    check_sources, down, window)


WORKSPACE = PrefixWorkspace(0x10000000, 8 * 16384, 7, 128)


def make_owner(enabled=False, *, windows=False, cls=DenseAHoldModel):
    args = dict(enable_ffn_window=windows, enable_ffn_tiles=windows)
    if cls is DenseAHoldModel:
        args['enable_a_hold'] = enabled
    return cls(WORKSPACE, **args)


def source_word(kind, index):
    # Bounded finite BF16 patterns with both signs; identities vary by address.
    return ((index * 13 + (29 if kind == 'b' else 7)) & 0x807f) | 0x3f00


class ColdDriver:
    """One real accepted DMA descriptor, two joined result slots, held ACKs.

    Opaque result patterns exercise result/DDR/tile transport only. The Matrix
    observation records every complete operand packet; it never answers an
    input read or computes a saved expected result for the owner.
    """
    def __init__(self, owner, job, *, seed=11):
        self.owner, self.job = owner, job
        self.rng = random.Random(seed)
        self.cycle = 0
        self.read = self.write = self.ack = self.seed_ack = None
        self.results = deque()
        self.result_count = 0
        self.group_steps = 0
        self.group_contexts = 0
        self.packets, self.commands, self.writes, self.events = [], [], [], []
        self.memory = {}
        self.terminal = None

    def beat(self, command):
        if command.kind == 'prefix':
            words = self.memory[command.address]
        else:
            native = self.job.activation_bf16 if command.kind == 'a' else self.job.weight_bf16
            base = self.job.a if command.kind == 'a' else self.job.b
            start = (command.address - base) // (2 if native else 4)
            values = tuple(source_word(command.kind, start + i) for i in range(32 if native else 16))
            words = values if native else tuple(x << 16 for x in values)
        return ReadBeat(command.tag, words, True)

    def step(self, **overrides):
        p = self.owner.ports()
        self.cycle += 1
        terminal = p.get('step') is not None and p['step'].last
        opts = dict(read_command_ready=self.cycle % 7 != 0,
                    step_ready=self.cycle % 5 != 0 and (not terminal or len(self.results) < 2),
                    write_command_ready=self.cycle % 3 != 0,
                    write_data_ready=self.cycle % 4 != 0,
                    tile_accept_ready=self.cycle % 3 != 0,
                    tile_response_ready=self.cycle % 4 != 0)
        if self.read and self.read[1] <= self.cycle:
            opts['read_beat'] = self.beat(self.read[0])
        if self.ack and self.ack[1] <= self.cycle:
            opts['write_ack'] = self.ack[0]
        if self.seed_ack and self.seed_ack[1] <= self.cycle:
            opts['seed_ack'] = self.seed_ack[0]
        if self.results and self.results[0][1] <= self.cycle:
            opts['result'] = self.results[0][0]
        if p.get('abort') and not self.results:
            opts['matrix_done'] = MatrixDone(self.job.tag, True)
        elif (p.get('matrix_done_ready') and self.group_contexts and
              self.result_count == self.group_contexts and not self.results and
              self.owner.pending is None and not self.owner.fifo and
              self.owner.issue_k == self.owner.chunk_end):
            opts['matrix_done'] = MatrixDone(self.job.tag)
        opts.update(overrides)
        event = self.owner.tick(**opts)
        self.events.append(event)
        if event.get('read_fire'):
            if self.read is None:
                raise RuntimeError('unsolicited driver response')
            self.read = None
        if event.get('read_command_fire'):
            if self.read is not None:
                raise RuntimeError('second accepted DMA descriptor')
            self.read = (event['read_command'], self.cycle + 1 + self.rng.randrange(3))
            self.commands.append(event['read_command'])
        if event.get('group_fire'):
            if self.results:
                raise RuntimeError('joined results crossed group boundary')
            self.result_count, self.group_steps = 0, 0
            self.group_contexts = self.owner.contexts
        if event.get('step_fire'):
            packet = event['step']
            self.packets.append((self.owner.n_base, self.owner.chunk_start, packet))
            self.group_steps += 1
            if packet.last:
                if len(self.results) >= 2:
                    raise RuntimeError('more than two joined Matrix result slots')
                value = tuple(tuple(0x3f000000 + packet.context * 512 + r * 16 + c % 16
                                    for c in range(256)) for r in range(16))
                self.results.append((MatrixResult(packet.context, value), self.cycle + 2))
        if event.get('result_fire'):
            self.results.popleft()
            self.result_count += 1
        if event.get('seed_beat_fire') and event['seed_beat'].last:
            self.seed_ack = (SeedAck(event['seed_beat'].request), self.cycle + 2)
        if event.get('seed_ack_fire'):
            self.seed_ack = None
        if event.get('write_command_fire'):
            if self.write is not None or self.ack is not None:
                raise RuntimeError('overlapping write obligations')
            self.write = [event['write_command'], 0]
        if event.get('write_data_fire'):
            command, index = self.write
            data = event['write_data']
            self.memory[command.address + 64 * index] = data.words
            self.writes.append((command.address + 64 * index, data))
            self.write[1] += 1
            if data.last:
                self.ack = (WriteAck(command.tag, nbytes=command.beats * 64), self.cycle + 2)
                self.write = None
        if event.get('write_ack_fire'):
            self.ack = None
        if event.get('response_fire'):
            self.terminal = event['response']
        if event.get('window_result_fire'):
            self.terminal = event['window_result']
        return event

    def run(self, *, window_request=None):
        self.step(**({'window': window_request} if window_request else {'job': self.job}))
        for _ in range(80000):
            self.step()
            if self.terminal is not None:
                if self.read or self.write or self.ack or self.seed_ack or self.results:
                    raise RuntimeError('terminal left an accepted external obligation')
                return self
        raise RuntimeError('cold functional job did not retire')

    def until(self, predicate):
        for _ in range(80000):
            if predicate():
                return
            self.step()
        raise RuntimeError('condition was never reached')


def check_packets(driver):
    job = driver.job
    for ng, chunk, packet in driver.packets:
        expected_a = tuple(source_word('a', m * job.k + packet.k) if m < job.m else 0
                           for m in range(128))
        expected_w = tuple(source_word('b', packet.k * job.n + ng + packet.context * 32 + n)
                           for n in range(32))
        assert packet.a == expected_w[:16]
        assert packet.b == expected_a + expected_w[16:] + (0,) * 112
        assert packet.clear == (packet.k == 0)
        assert packet.last == (packet.k + 1 == min(chunk + WORKSPACE.split_k, job.k))


def test_source_closure_and_typed_default_off():
    assert len(check_sources()) == 10
    owner = make_owner()
    assert not owner.enable_a_hold and owner.FIFO_DEPTH == 4
    for flag in (1, None, 'on'):
        with pytest.raises(ValueError): DenseAHoldModel(WORKSPACE, enable_a_hold=flag)


def test_disabled_is_exact_frozen_control_trace():
    job = Job(m=16, k=32, n=96)
    baseline = ColdDriver(make_owner(cls=window.FfnWindowOwnerModel), job).run()
    disabled = ColdDriver(make_owner(), job).run()
    assert baseline.events == disabled.events
    assert baseline.packets == disabled.packets
    assert baseline.writes == disabled.writes


@pytest.mark.parametrize('m,k,n,native', [(16,32,32,True), (16,32,96,True),
    (16,64,160,True), (16,32,256,True), (128,32,160,True), (16,32,96,False),
    (16,256,256,True)])
def test_cold_traffic_exact_packets_results_and_per_context_order(m,k,n,native):
    job = Job(m=m,k=k,n=n,activation_bf16=native,weight_bf16=native)
    baseline = ColdDriver(make_owner(), job).run()
    reused = ColdDriver(make_owner(True), job).run()
    assert reused.terminal == baseline.terminal == (job.tag, None, m*n*4)
    assert reused.packets == baseline.packets
    assert reused.commands == baseline.commands
    assert reused.writes == baseline.writes
    check_packets(reused)
    contexts = n // 32
    gathers = k * ((contexts + 4) // 5)
    assert reused.owner.hold_counts['a_gathers'] == gathers
    assert reused.owner.hold_counts['b_only_gathers'] == k*contexts - gathers
    assert reused.owner.hold_counts['hold_uses'] == k*contexts - gathers
    assert sum(bool(e.get('operand_read') and e['a_reads']) for e in reused.events) == gathers
    assert reused.owner.max_reserved <= 3
    assert reused.owner.hold_words is None
    for event in reused.events:
        if event.get('operand_read'):
            assert len(event['a_reads']) in (0,8)
            assert len(event['b_reads']) == 2
        assert event.get('reserved_after',0) <= 3
    for ng in range(0,n,160):
        for context in range(min(5,(n-ng)//32)):
            assert [p.k for base,_,p in reused.packets if base == ng and p.context == context] == list(range(k))


def test_reserved_response_and_private_packets_survive_long_stall():
    job = Job(m=16,k=32,n=160)
    driver = ColdDriver(make_owner(True), job)
    driver.step(job=job)
    driver.until(lambda: driver.owner.pending is not None)
    for _ in range(25):
        event = driver.step(step_ready=False)
        assert event['reserved_after'] <= 3
    assert len(driver.owner.fifo) == 3 and driver.owner.pending is None
    held = tuple(driver.owner.fifo)
    for _ in range(10):
        driver.step(step_ready=False)
        assert tuple(driver.owner.fifo) == held
    driver.until(lambda: driver.terminal is not None)
    check_packets(driver)
    assert driver.owner.hold_counts['a_gathers'] == 32


@pytest.mark.parametrize('fault', ['abort','local_reset','invalidate_lease'])
@pytest.mark.parametrize('context', [0,2])
def test_invalidation_drains_pending_debt_without_resurrection(fault,context):
    job = Job(m=16,k=32,n=160)
    driver = ColdDriver(make_owner(True), job)
    driver.step(job=job)
    driver.until(lambda: driver.owner.pending is not None and driver.owner.pending[1] == context)
    accepted_before = len(driver.packets)
    event = driver.step(**{fault:True})
    assert not event.get('step_fire') and not event.get('operand_read')
    assert driver.owner.hold_words is None
    driver.until(lambda: driver.terminal is not None)
    assert len(driver.packets) == accepted_before
    assert driver.owner.state == 'locked'
    assert driver.owner.hold_words is None and driver.owner.pending is None and not driver.owner.fifo
    assert driver.read is None
    driver.step(job=job)
    assert driver.owner.state == 'locked'
    driver.step(coordinated_reset=True)
    assert driver.owner.state == 'idle' and driver.owner.hold_generation == 0


def test_generation_mismatch_fault_is_not_disabled_by_python_optimization():
    job = Job(m=16,k=32,n=160)
    driver = ColdDriver(make_owner(True), job)
    driver.step(job=job)
    driver.until(lambda: driver.owner.pending is not None)
    driver.owner.hold_generation += 1  # Inject stale-response metadata.
    driver.step(step_ready=False)
    assert driver.owner.error is not None and driver.owner.hold_words is None
    assert not driver.owner.ports()['step']
    driver.until(lambda: driver.terminal is not None)
    assert driver.owner.state == 'locked'


def test_same_edge_dma_fault_does_not_issue_new_bank_read_or_revive_hold():
    job = Job(m=16,k=256,n=160)
    owner = make_owner(True)
    owner.workspace = replace(WORKSPACE,split_k=256)
    driver = ColdDriver(owner, job)
    driver.step(job=job)
    driver.until(lambda: driver.owner.pending is not None and driver.read is not None and
                 driver.owner.ports()['read_ready'])
    bad = replace(driver.beat(driver.read[0]), error=True)
    event = driver.step(read_beat=bad, step_ready=False)
    assert event['read_fire'] and not event['operand_read']
    assert not event['a_reads'] and not event['b_reads']
    assert driver.owner.error and driver.owner.hold_words is None
    driver.until(lambda: driver.terminal is not None)
    assert driver.owner.state == 'locked'


def test_window_lease_reuses_sram_but_starts_fresh_hold():
    job = Job(m=16,k=32,n=256)
    owner = make_owner(True, windows=True)
    first = FfnWindowRequest(job,55,0,160,0)
    a = ColdDriver(owner,job).run(window_request=first)
    assert a.terminal.committed and owner.lease is not None
    generation = owner.hold_generation
    assert owner.hold_words is None and owner.hold_counts['a_gathers'] == 32
    next_job = replace(job,tag=2,b=0x600000)
    second = FfnWindowRequest(next_job,55,160,96,1,True)
    b = ColdDriver(owner,next_job).run(window_request=second)
    assert b.terminal.committed and owner.hold_generation > generation
    assert owner.hold_counts['a_gathers'] == 64
    assert not [q for q in b.commands if q.kind == 'a']
    check_packets(a)
    check_packets(b)


def test_window_lease_invalidation_rejects_reuse_before_gather():
    job = Job(m=16,k=32,n=160)
    owner = make_owner(True, windows=True)
    ColdDriver(owner,job).run(window_request=FfnWindowRequest(job,55,0,160,0))
    owner.tick(invalidate_lease=True)
    before = owner.hold_counts['a_gathers']
    second = FfnWindowRequest(replace(job,tag=2),55,0,160,1,True)
    driver = ColdDriver(owner,second.job).run(window_request=second)
    assert not driver.terminal.committed and owner.state == 'locked'
    assert owner.hold_counts['a_gathers'] == before


def test_generation_never_wraps():
    owner = make_owner(True)
    owner.hold_generation = 0xffffffff
    owner.tick(job=Job(m=16,k=32,n=32))
    assert owner.error and owner.hold_generation == 0xffffffff
    assert owner.hold_words is None


def test_abort_waits_for_accepted_dma_response():
    job = Job(m=16,k=32,n=160)
    driver = ColdDriver(make_owner(True),job)
    driver.step(job=job)
    driver.until(lambda: driver.read is not None)
    command = driver.read[0]
    driver.read = (command,driver.cycle+1000)
    driver.step(abort=True)
    for _ in range(12):
        event = driver.step()
        assert not event.get('read_command_fire') and not event.get('response_fire')
        assert driver.owner.read_active is not None and driver.owner.state == 'drain'
    driver.read = (command,driver.cycle)
    driver.until(lambda: driver.terminal is not None)
    assert driver.read is None and driver.owner.state == 'locked'


def test_abort_commits_already_accepted_a_rmw_before_terminal():
    job = Job(m=16,k=32,n=160)
    driver = ColdDriver(make_owner(True),job)
    driver.step(job=job)
    driver.until(lambda: driver.owner.a_rmw_pending is not None)
    commits_before = driver.owner.rmw_commits
    driver.step(local_reset=True)
    driver.until(lambda: driver.terminal is not None)
    assert driver.owner.rmw_commits > commits_before
    assert driver.owner.a_rmw_pending is None and driver.owner.a_hold is None
    assert driver.owner.state == 'locked' and driver.owner.hold_words is None


def test_abort_waits_for_accepted_write_ack_and_joined_results():
    job = Job(m=16,k=32,n=160)
    driver = ColdDriver(make_owner(True),job)
    driver.step(job=job)
    driver.until(lambda: driver.ack is not None)
    ack = driver.ack[0]
    driver.ack = (ack,driver.cycle+1000)
    driver.step(abort=True)
    for _ in range(12):
        event = driver.step()
        assert not event.get('response_fire') and not event.get('write_command_fire')
        assert driver.owner.write_state == 'ack'
    driver.ack = (ack,driver.cycle)
    driver.until(lambda: driver.terminal is not None)
    assert driver.ack is None and driver.write is None and not driver.results
    assert driver.owner.write_state == 'idle' and driver.owner.state == 'locked'


def test_abort_waits_for_accepted_seed_obligation():
    job = Job(m=16,k=256,n=32)
    driver = ColdDriver(make_owner(True),job)
    driver.step(job=job)
    driver.until(lambda: driver.owner.seed_outstanding)
    request = driver.owner._seed_request()
    driver.step(abort=True)
    for _ in range(12):
        event = driver.step()
        assert driver.owner.seed_outstanding and not event.get('response_fire')
    event = driver.step(seed_ack=SeedAck(request,error=True))
    assert event['seed_ack_fire'] and not driver.owner.seed_outstanding
    driver.until(lambda: driver.terminal is not None)
    assert driver.read is None and driver.owner.state == 'locked'


def cold_report():
    job = Job(m=16,k=32,n=256)
    baseline = ColdDriver(make_owner(),job).run()
    candidate = ColdDriver(make_owner(True),job).run()
    def digest(items):
        return hashlib.sha256(repr(items).encode()).hexdigest()
    return dict(kind='synthetic_cold_transport_and_order_only', rtl_execution=False,
                arithmetic_execution=False, timing_or_utilization_claim=False,
                shape=dict(m=16,k=32,n=256),
                accepted_packets=len(candidate.packets),
                accepted_packets_equal=baseline.packets == candidate.packets,
                accepted_packets_sha256=digest(candidate.packets),
                dma_commands_equal=baseline.commands == candidate.commands,
                dma_commands_sha256=digest(candidate.commands),
                writes_equal=baseline.writes == candidate.writes,
                writes_sha256=digest(candidate.writes),
                a_gathers_before=sum(bool(e.get('operand_read')) for e in baseline.events),
                a_gathers_after=candidate.owner.hold_counts['a_gathers'],
                b_only_gathers=candidate.owner.hold_counts['b_only_gathers'],
                max_reserved=candidate.owner.max_reserved,
                default_queue_slots=4,candidate_queue_slots=3,
                active_fifo_payload_before_bytes=4*320,
                active_fifo_plus_hold_payload_after_bytes=3*320+256,
                proposed_explicit_metadata_bits=112,
                unchanged_a_sram_bytes=16*1376*32, unchanged_b_sram_bytes=16*160*32)


def test_saved_cold_report():
    expected = json.loads(Path(__file__).with_name('COLD_RESULT.json').read_text())
    assert expected == cold_report()
