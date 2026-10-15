"""Diagnostic public-KV authority and one-edge shared-A router.

Full metadata, producer, ACK, payload hash and canary checks occur at entry
and terminal release. The hot path checks fixed-size identities/generations
and lengths; accepted writes still use the unchanged PhysicalMemory guard.
This is a software-owner diagnostic, not a Chisel or performance claim.
"""
from collections import Counter
from dataclasses import asdict
import hashlib

from candidates.qwen2_attention_resident_candidate.owner import ResidentPV32AttentionOwner
from candidates.qwen2_attention_resident_candidate.scratch import ReadonlyKVIdentity
from candidates.qwen2_attention_shared_a_integration.banks import (
    LoanDenseOwner, BankByteView, need,
)
from candidates.qwen2_attention_shared_a_integration.lease import SharedALoanRouter
from candidates.qwen2_resident_matrix.ffn_public import model as public
from candidates.qwen2_resident_matrix.ffn_public.fixture import (
    Fixture, QWEN2_21_SOURCE_COMMIT, QWEN2_21_SOURCE_PINS,
)
from candidates.qwen2_resident_matrix.ffn_public.prefix_execution import PhysicalMemory, SENTINEL
from candidates.qwen2_resident_matrix.official_bf16.execution import OPCODES, validate_job

_PHYSICAL_WRITE_EVENT = PhysicalMemory.write_event
_PHYSICAL_REGION = PhysicalMemory.region


def validate_public21_fixture(fixture, physical):
    """Check original metadata only; never manufacture producer completion."""
    need(type(fixture) is Fixture and type(physical) is PhysicalMemory and
         physical.fixture is fixture, 'original fixture and exact physical map required')
    f = fixture
    need(f.scope == 'QWEN2_21_METADATA_ONLY' and f.config.command.count == 21 and
         len(f.commands) == 21 and tuple(int(c.opcode) for c in f.commands) == OPCODES and
         all(c.event_wait == i and c.event_signal == i + 1 for i, c in enumerate(f.commands)),
         'diagnostic requires original public21 command schedule')
    need(f.manifest['commands'] == 21 and f.provenance['source_commit'] == QWEN2_21_SOURCE_COMMIT and
         f.provenance['source_sha256'] == QWEN2_21_SOURCE_PINS,
         'original public21 manifest/provenance required')
    f.validate_spans()
    for name, key, table in (('command_table', 'host_commands.bin', f.config.command),
                             ('descriptor_table', 'host_descriptors.bin', f.config.descriptor)):
        raw = bytes(f.memory.mappings[table.base])
        region = physical.regions[name]
        need(region['readonly'] and region['base'] == table.base and region['extent'] == len(raw) and
             physical.raw(table.base, len(raw)) == raw and
             hashlib.sha256(raw).hexdigest() == f.manifest['table_sha256'][key],
             'public metadata does not match original manifest')
    command_raw = bytes(f.memory.mappings[f.config.command.base])
    need(command_raw[:21 * 16] == b''.join(c.to_bytes() for c in f.commands),
         'manifest command objects differ from the fetched bytes')


def expected_kv_identity(physical):
    """Identity prediction only. It grants neither publication nor read access."""
    need(type(physical) is PhysicalMemory, 'expected identity needs actual PhysicalMemory')
    f = physical.fixture
    r = physical.regions['kv']
    a = f.allocations['kv']
    need(r['base'] == a.address and r['extent'] == a.storage_bytes and r['dtype'] == 7 and
         not r['readonly'] and not r['virtual'], 'expected identity needs the actual KV parent')
    generation = (f.config.epoch << 32) | 9
    identity = ReadonlyKVIdentity(id(r), id(r), generation, generation)
    identity.validate()
    return identity


class DiagnosticPublicKvPublication:
    """Only accepted original pc9 plus the offered original pc12 grants a loan."""
    def __init__(self, x, physical, job):
        # Local import avoids a type-admission loophole and an import cycle.
        from .public_binding import DiagnosticPublicExecution
        need(type(x) is DiagnosticPublicExecution and type(physical) is PhysicalMemory,
             'exact diagnostic execution and actual physical memory required')
        self.x, self.physical, self.job = x, physical, job
        self.fixture, self.config, self.host = physical.fixture, physical.fixture.config, x.host
        self.frontend, self.metadata = x.frontend, x.frontend.memory
        need(type(self.frontend) is public.PublicFrontend and type(self.host) is public.group.HostControl and
             self.host.frontend is self.frontend and self.frontend.port.memory is self.metadata and
             getattr(self.metadata, 'physical_memory', None) is physical and
             physical.fixture is x.policy_fixture and self.frontend.config == self.config,
             'same actual public Host/frontend/fixture/physical identity')
        validate_public21_fixture(self.fixture, physical)
        need(physical.pending is None, 'public prefix DDR must drain before producer seal')
        need(x.ports()['ordinary_request'] is job and x.ports()['group_request'] is None and
             validate_job(self.fixture, job) == 12 and self.host.bound is job,
             'actual fused pc12 owner request required')
        need(len(self.host.program) == 21 and self.host.completed == self.host.jobs == 10 and
             self.host.pc == 12 and [c['pc'] for c in x.completions] == list(range(10)) and
             all(c['status'] is None for c in x.completions) and
             x.counts['completion_fire'] == x.counts['owner_result_fire'] == x.counts['request_fire'] == 10 and
             len(x.requests) == 10 and self.host.status is None and x.launch_result is None,
             'ten real public prefix request/terminal/completion handshakes required')
        producer = x.prefix_owner
        need(producer.job is not None and validate_job(self.fixture, producer.job) == 9 and
             producer.job.kind == 'KvAppend' and producer.state == 'idle' and not producer.poison and
             producer.counts['owner_results'] == 1 and producer.ack_bytes == producer.job.write_bytes and
             x.completions[-1]['pc'] == 9,
             'accepted real pc9 KvAppend producer and exact ACK fence required')
        _, r = physical.region(job.b, job.m * 1024)
        _, v = physical.region(job.c, job.m * 1024)
        need(r is v and r is physical.regions['kv'] and r['base'] == job.b and
             job.c == job.b + job.m * 1024 and r['extent'] == job.m * 2048 and r['dtype'] == 7,
             'same FP32 KV parent and exact K/V views required')
        self.region, self.regions = r, physical.regions
        self.epoch, self.identity = self.config.epoch, expected_kv_identity(physical)
        self.digest = physical.published_hashes.get('kv')
        self.hashes = physical.published_hashes
        self.data, self.acked, self.written, self.records = (r[k] for k in ('data', 'acked', 'written', 'records'))
        self.published, self.events = self.host.published, self.host.events
        self.completions, self.requests = x.completions, x.requests
        self.host_counts = x.counts
        self.producer, self.producer_job = producer, producer.job
        self.job_fields = asdict(job)
        self.layout = (r['base'], r['extent'], r['reserved'], r['dtype'], r['readonly'], r['virtual'])
        self.lengths = (len(self.data), len(self.acked), len(self.written), len(self.records),
                        len(self.published), len(self.events))
        self.published_snapshot, self.events_snapshot = tuple(self.published), frozenset(self.events)
        self.completions_snapshot = tuple(dict(c) for c in self.completions)
        self.counts = Counter()
        self.validate(job)

    def validate_fast(self, job):
        """Constant-size checks; no full-KV digest or extent-sized set creation."""
        x, p, r, h = self.x, self.physical, self.region, self.host
        need(job is self.job and x.policy_fixture is self.fixture and p.fixture is self.fixture and
             self.fixture.config is self.config and self.config.epoch == self.epoch and
             x.host is h and h.epoch == self.epoch and x.frontend is self.frontend and
             self.frontend.memory is self.metadata and self.frontend.port.memory is self.metadata and
             self.metadata.physical_memory is p and self.frontend.config == self.config and
             h.frontend is self.frontend and h.bound is job,
             'publication fixture/frontend/Host/job generation or identity changed')
        need(p.regions is self.regions and p.regions.get('kv') is r and
             (r['base'], r['extent'], r['reserved'], r['dtype'], r['readonly'], r['virtual']) == self.layout and
             not r['readonly'] and not r['virtual'] and r['terminal'] is True and r['published'] is True and
             r.get('workspace_transport') is None and p.published_hashes is self.hashes and
             self.digest is not None and self.hashes.get('kv') == self.digest,
             'KV publication/allocation/generation changed')
        need(r['data'] is self.data and r['acked'] is self.acked and r['written'] is self.written and
             r['records'] is self.records and h.published is self.published and h.events is self.events and
             (len(self.data), len(self.acked), len(self.written), len(self.records),
              len(self.published), len(self.events)) == self.lengths,
             'KV data/ACK/publication object or length changed')
        need(x.completions is self.completions and len(self.completions) == 10 and
             x.requests is self.requests and len(self.requests) in (10, 11) and
             h.completed == 10 and h.jobs in (10, 11) and h.pc == 12 and x.launch_result is None and
             x.counts is self.host_counts and x.counts['completion_fire'] == 10 and
             x.counts['owner_result_fire'] == 10 and x.counts['request_fire'] == h.jobs == len(self.requests) and
             x.prefix_owner is self.producer and self.producer.job is self.producer_job and
             self.producer.counts['owner_results'] == 1 and
             self.producer.ack_bytes == self.producer_job.write_bytes,
             'producer generation/public completion changed during KV loan')
        need(PhysicalMemory.write_event is _PHYSICAL_WRITE_EVENT and
             getattr(p.write_event, '__func__', None) is _PHYSICAL_WRITE_EVENT and
             getattr(p.write_event, '__self__', None) is p and
             PhysicalMemory.region is _PHYSICAL_REGION and
             getattr(p.region, '__func__', None) is _PHYSICAL_REGION and
             getattr(p.region, '__self__', None) is p and
             (p.pending is None or p.pending[0] != 'kv'),
             'original immutable published-write guard must remain active')
        self.counts['fast_checks'] += 1
        return self.identity

    def validate(self, job):
        """Complete entry/release audit, including same-size out-of-band edits."""
        self.validate_fast(job)
        p, r = self.physical, self.region
        need(asdict(job) == self.job_fields and validate_job(self.fixture, job) == 12,
             'original fused job fields changed')
        validate_public21_fixture(self.fixture, p)
        expected = set(range(r['base'], r['base'] + r['extent'], 64))
        need(type(self.data) is bytearray and type(self.acked) is set and type(self.written) is set and
             self.acked == self.written == expected and len(self.data) == r['extent'] + 128 and
             tuple(self.published) == self.published_snapshot and frozenset(self.events) == self.events_snapshot and
             tuple(self.completions) == self.completions_snapshot and
             (r['base'], r['base'] + r['extent']) in self.published and
             self.data[:64] == self.data[-64:] == SENTINEL * 16 and
             hashlib.sha256(memoryview(self.data)[64:-64]).hexdigest() == self.digest,
             'exact live KV ACK/publication/hash/canary audit failed')
        # Audit the actual accepted command/ACK records rather than trusting a
        # cardinality or a caller-provided success flag.
        covered = set()
        for command, ack in self.records:
            addresses = set(range(command.address, command.address + command.beats * 64, 64))
            need(1 <= command.beats <= 16 and addresses <= expected and not covered.intersection(addresses) and
                 ack.tag == command.tag and not ack.error and ack.nbytes == command.beats * 64,
                 'KV accepted command/ACK record identity or coverage changed')
            covered.update(addresses)
        need(covered == expected, 'KV accepted ACK records do not cover the full parent')
        self.counts['full_checks'] += 1
        return self.identity

    def pending(self):
        return self.physical.pending

    def report(self):
        return dict(authority='ACTUAL_PUBLIC_PC9_HANDSHAKES', counts=dict(self.counts),
                    validation='FULL_ENTRY_AND_RELEASE_CONSTANT_SIZE_CONTINUATION',
                    original_physical_write_guard=True)


class DiagnosticSharedALoanRouter(SharedALoanRouter):
    """Explicit authority type admission; no patch to the published router."""
    def __init__(self, dense, prefix, attention, publication):
        need(type(dense) is LoanDenseOwner and dense.tiles.banks is dense.a_banks,
             'one actual Dense/Tile A bank allocation required')
        need(type(attention) is ResidentPV32AttentionOwner and
             type(attention.scratch.storage) is BankByteView and
             attention.scratch.storage.banks is dense.a_banks,
             'resident Attention must view those exact existing A banks')
        need(prefix.scalar is attention.scalar and type(publication) is DiagnosticPublicKvPublication and
             publication.x.owner is dense and publication.x.prefix_owner is prefix and
             publication.x.attention_owner is attention,
             'same actual public owners/scalar and diagnostic publication authority required')
        self.dense, self.prefix, self.attention, self.publication = dense, prefix, attention, publication
        self.guard = dense.a_banks
        self.active, self.job, self.counts = False, None, Counter()
        self.bank_identity = self.guard.payload_identity
        self.scratch, self.storage = attention.scratch, attention.scratch.storage
        self.b_banks = dense.b_banks
        self.fault = None

    def _assert_exclusive(self):
        super()._assert_exclusive()
        a = self.attention
        need(self.dense.bank_guard is self.guard and self.dense.a_banks is self.guard and
             self.dense.b_banks is self.b_banks and a.scratch is self.scratch and
             self.scratch.storage is self.storage and self.storage.banks is self.guard and
             self.prefix.scalar is a.scalar and self.prefix.state == 'idle' and not self.prefix.poison and
             a.kv_identity == self.publication.identity and
             (self.scratch.owner is None or
              self.scratch.owner is a and self.scratch.identity == self.publication.identity),
             'shared bank/cache/producer identity changed during A loan')

    def _retain_fault(self, detail):
        if self.fault is None:
            self.fault = str(detail)
            self.counts['faults'] += 1
        self.attention.scratch.revoke()

    def tick(self, **inputs):
        if 'job' in inputs:
            need(not self.active and self.fault is None, 'duplicate/faulted Attention launch')
            self.arm(inputs['job'])
        need(self.active, 'Attention edge without checked public A loan')
        self._assert_exclusive()
        try:
            self.publication.validate_fast(self.job)
            # Audit before a success terminal can be consumed by the Host.
            if self.attention.ports()['response'] is not None and inputs.get('response_ready'):
                self.publication.validate(self.job)
        except ValueError as error:
            self._retain_fault(error)
            # An already-held successful terminal must never escape after a
            # failed full audit. Keep the bank lease and terminal debt intact.
            if self.attention.ports()['response'] is not None:
                raise
        with self.guard.edge():
            self.guard.clock_only = True
            self.dense.tick()
            self.guard.clock_only = False
            try:
                with self.guard.scope('cache'):
                    edge = self.attention.tick(**inputs)
            except (ValueError, AssertionError) as error:
                self._retain_fault(error)
                self.attention._fault('Protocol', 'diagnostic shared A route fault requires drain')
                self.counts['route_faults'] += 1
                raise
            need(self.guard.begins == 1, 'exactly one Dense/Tile bank clock per shared edge')
            self.counts['edges'] += 1
        self._assert_exclusive()
        if edge['response_fire']:
            a = self.attention
            need(a.state in ('idle', 'locked') and a.matrix.owner is None and a.scalar.client is None and
                 a.matrix_client is None and a.matrix_request is None and not a.memory_pending and
                 not a.abort_pending and a.scratch.owner is None and a.scratch.pending is None and
                 a.scratch.held is None and not a.local_pending and self.publication.pending() is None,
                 'A release before local/DDR/Matrix/Scalar drain and accepted terminal')
            if self.fault is None and edge['response'].status is None and not a.poison:
                self.publication.validate(self.job)
                self.guard.lease = None
                self.active = False
                self.counts['releases'] += 1
            else:
                self._retain_fault('faulted Attention terminal; shared A remains quarantined')
                self.counts['faulted_terminal_lease_retained'] += 1
        return edge

    def report(self):
        result = super().report()
        result.update(authority='ACTUAL_PUBLIC_PC9_HANDSHAKES',
                      production_public_checkpoint_executed=True,
                      publication=self.publication.report(), fault=self.fault,
                      scope='DIAGNOSTIC_SOFTWARE_OWNER', performance='NO_GO',
                      hardware='NOT_IMPLEMENTED')
        return result
