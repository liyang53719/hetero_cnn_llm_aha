"""Cold metadata/identity/router tests; no native arithmetic or real prefix run.

The isolated continuation predicates below use explicitly synthetic records.
They never call the successful public authority constructor and cannot stand
in for real ten-command prefix or complete public21 execution evidence.
"""
from collections import Counter
from dataclasses import asdict, replace
import hashlib
import inspect
import struct
import time
from types import SimpleNamespace
import unittest

from candidates.qwen2_attention_resident_candidate.owner import ResidentPV32AttentionOwner
from candidates.qwen2_attention_shared_a_integration.banks import LoanDenseOwner, banked_scratch, LoanFault
from candidates.qwen2_live_attention_model_m128.public_binding import PV32ReductionDriver
from candidates.qwen2_resident_matrix.dense_block_reduce.matrix_binding import ProfiledMatrixService
from candidates.qwen2_resident_matrix.dense_block_reduce.profile import QWEN2_QKV_PROFILE
from candidates.qwen2_resident_matrix.ffn_public import model as public
from candidates.qwen2_resident_matrix.ffn_public.execute_numeric import PublicExecution, numeric
from candidates.qwen2_resident_matrix.ffn_public.fixture import make_qwen2_21_fixture
from candidates.qwen2_resident_matrix.ffn_public.prefix_execution import PhysicalMemory, SENTINEL
from candidates.qwen2_resident_matrix.official_bf16.owners import OfficialPrefixOwner
from .public_binding import DiagnosticPublicExecution, DiagnosticVReductionDriver
from .publication import DiagnosticPublicKvPublication, DiagnosticSharedALoanRouter, expected_kv_identity


class ColdLib:
    """No ABI or arithmetic: only quiescent introspection for constructor tests."""
    def matrix_state(self): return 0
    def matrix_dense_fmas(self): return 0
    def matrix_normal_fmas(self): return 0
    def matrix_accumulator_bytes(self): return 81920


def cold_execution():
    f = make_qwen2_21_fixture(16)
    p = PhysicalMemory(f, {})
    r = f.config.regions[3]
    owner = LoanDenseOwner(numeric.model.PrefixWorkspace(r.base, r.limit - r.base, f.config.epoch + 1, 2560),
        enable_dense_drain=True, enable_k_window=True, enable_ffn_drain=True,
        enable_ffn_window=True, enable_ffn_tiles=True)
    # Deliberately avoid the native service constructor. These objects permit
    # metadata/admission tests only; no Matrix/Scalar operation can execute.
    service = ProfiledMatrixService.__new__(ProfiledMatrixService)
    service.lib, service.owner, service.counts = ColdLib(), None, Counter()
    service.profile, service._bindings = QWEN2_QKV_PROFILE, {}
    scalar = SimpleNamespace(client=None, calls=Counter())
    prefix = OfficialPrefixOwner(scalar)
    attention = ResidentPV32AttentionOwner(service, scalar, scratch=banked_scratch(owner.a_banks),
                                          identity=expected_kv_identity(p))
    x = DiagnosticPublicExecution(public.PublicFrontend(p.metadata_port(), f.config), owner,
        numeric.CappedTrace(), time.monotonic() + 60, fixture=f,
        host=public.group.HostControl(enabled=True, legacy_prefix=True, legacy_attention=True),
        prefix_owner=prefix, attention_owner=attention, matrix_service=service)
    return f, p, x


def isolated_publication():
    """Real write_event guards + synthetic predicate context, NOT prefix proof."""
    f, p, x = cold_execution()
    r = p.regions['kv']
    producer = SimpleNamespace(kind='KvAppend', tag=(f.config.epoch << 16) | 9,
        dst=r['base'], m=16, write_bytes=r['extent'])
    for address in range(r['base'], r['base'] + r['extent'], 64):
        p.write_event('command', SimpleNamespace(address=address, beats=1, tag=producer.tag))
        p.write_event('data', SimpleNamespace(words=(0,) * 16, mask=(1 << 64) - 1, last=True))
        p.write_event('ack', SimpleNamespace(tag=producer.tag, error=False, nbytes=64))
    p.terminal(producer, SimpleNamespace(tag=producer.tag, status=None, write_bytes=r['extent']))
    job = public.group.PrefixJob('Attention', (f.config.epoch << 16) | 12,
        f.specs['q'][0], f.specs['cache_k'][0], f.specs['att'][0], 16, 1536, 128,
        f.allocations['att'].storage_bytes, c=f.specs['cache_v'][0])
    # Predicate state is explicit, synthetic, and never admitted by __init__.
    h = x.host
    h.published.append((r['base'], r['base'] + r['extent']))
    h.events.update(range(11))
    h.bound, h.completed, h.jobs, h.pc = job, 10, 10, 12
    x.counts.update(completion_fire=10, owner_result_fire=10, request_fire=10)
    x.completions[:] = [dict(pc=i, status=None) for i in range(10)]
    x.requests[:] = [dict(synthetic_predicate_only=i) for i in range(10)]
    x.prefix_owner.job = producer
    x.prefix_owner.ack_bytes = producer.write_bytes
    x.prefix_owner.counts['owner_results'] = 1
    p.publish(producer, h)
    check = DiagnosticPublicKvPublication.__new__(DiagnosticPublicKvPublication)
    check.x, check.physical, check.job = x, p, job
    check.fixture, check.config, check.host = f, f.config, h
    check.frontend, check.metadata = x.frontend, x.frontend.memory
    check.region, check.regions = r, p.regions
    check.epoch, check.identity = f.config.epoch, expected_kv_identity(p)
    check.digest, check.hashes = p.published_hashes['kv'], p.published_hashes
    check.data, check.acked, check.written, check.records = (r[k] for k in ('data', 'acked', 'written', 'records'))
    check.published, check.events = h.published, h.events
    check.completions, check.requests = x.completions, x.requests
    check.host_counts = x.counts
    check.producer, check.producer_job = x.prefix_owner, producer
    check.job_fields = asdict(job)
    check.layout = (r['base'], r['extent'], r['reserved'], r['dtype'], r['readonly'], r['virtual'])
    check.lengths = (len(check.data), len(check.acked), len(check.written), len(check.records),
                     len(check.published), len(check.events))
    check.published_snapshot, check.events_snapshot = tuple(check.published), frozenset(check.events)
    check.completions_snapshot = tuple(dict(c) for c in check.completions)
    check.counts = Counter()
    return check


class BindingCold(unittest.TestCase):
    def test_real_raw_metadata_launch_without_native_or_fabricated_completion(self):
        f, p, x = cold_execution()
        self.assertIsInstance(x, PublicExecution)
        self.assertEqual((x.host.completed, x.host.jobs, len(x.completions), len(x.requests)), (0, 0, 0, 0))
        job = x.advance_to_request()['ordinary_request']
        self.assertEqual((job.kind, job.tag & 0xffff), ('Norm', 0))
        self.assertEqual(x.host.jobs, 0)
        self.assertIs(x.owner.a_banks, x.attention_owner.scratch.storage.banks)
        self.assertIs(x.owner.a_banks, x.owner.tiles.banks)
        with self.assertRaises(ValueError): x.arm_attention(p, job)
        self.assertIsNone(x.attention_router)
        self.assertIsNone(x.owner.a_banks.lease)

    def test_predicted_identity_does_not_publish_or_grant_reads(self):
        f, p, x = cold_execution()
        identity = expected_kv_identity(p)
        r = p.regions['kv']
        self.assertEqual(identity, x.attention_owner.kv_identity)
        self.assertEqual(identity.allocation_k, id(r))
        self.assertEqual(identity.producer_k, (f.config.epoch << 32) | 9)
        with self.assertRaisesRegex(ValueError, 'read before ACK'): p.read_bytes64(r['base'])
        with self.assertRaisesRegex(ValueError, 'arm_attention'): x.attention_edge()
        self.assertFalse(r['published'])
        self.assertIsNone(x.owner.a_banks.lease)

    def test_projection_poison_is_visible_without_reduction_coordinator(self):
        _, _, x = cold_execution()
        self.assertIsNone(x.exact64_projection)
        x.exact64_projection = SimpleNamespace(backend=SimpleNamespace(poison=False))
        self.assertFalse(x.reset_required())
        x.exact64_projection.backend.poison = True
        self.assertTrue(x.reset_required())

    def test_type_and_producer_gates_reject_synthetic_hosts(self):
        f, p, x = cold_execution()
        job = x.advance_to_request()['ordinary_request']
        with self.assertRaises(LoanFault): DiagnosticPublicKvPublication(SimpleNamespace(), p, job)
        with self.assertRaises(LoanFault): DiagnosticPublicKvPublication(x, p, job)
        with self.assertRaises(LoanFault): DiagnosticSharedALoanRouter(x.owner, x.prefix_owner, x.attention_owner, object())
        self.assertEqual(x.host.completed, 0)

    def test_v_driver_inherits_tick_run_and_rejects_q_k_or_copied_execution(self):
        self.assertIs(DiagnosticVReductionDriver.tick, PV32ReductionDriver.tick)
        self.assertIs(DiagnosticVReductionDriver.run, PV32ReductionDriver.run)
        f, p, x = cold_execution()
        for pc, weight, dst, width in ((1, 'wq', 'qraw', 1536), (4, 'wk', 'kraw', 256)):
            job = public.group.Job('Dense', (f.config.epoch << 16) | pc, f.specs['n0'][0],
                f.specs[weight][0], f.specs[dst][0], 16, width, 1536,
                f.allocations[dst].storage_bytes, weight_bf16=True)
            with self.assertRaisesRegex(ValueError, 'only original pc7'):
                DiagnosticVReductionDriver(x, p, job)
        with self.assertRaisesRegex(ValueError, 'one diagnostic'):
            DiagnosticVReductionDriver(SimpleNamespace(reduction=None), p, object())

    def test_v_controller_uses_same_real_tile_delegate_through_guarded_owner(self):
        # Constructor-only predicate setup: no source arithmetic or public
        # prefix is executed, and no successful receipt is asserted.
        f, p, x = cold_execution()
        source = p.regions['n0']
        source['published'] = True
        job = public.group.Job('Dense', (f.config.epoch << 16) | 7, f.specs['n0'][0],
            f.specs['wv'][0], f.specs['vraw'][0], 16, 256, 1536,
            f.allocations['vraw'].storage_bytes, weight_bf16=True)
        # DenseSource validates exact command/ACK evidence even at construction.
        source['records'] = [(SimpleNamespace(address=address, beats=1, tag=0),
                              SimpleNamespace(tag=0, error=False, nbytes=64))
                             for address in range(source['base'], source['base'] + source['extent'], 64)]
        x.host.bound, x.host.state = job, 'issue'
        d = DiagnosticVReductionDriver(x, p, job)
        self.assertIs(d.sum.banks, x.owner.tiles._delegate)
        self.assertIs(d.sum.banks.banks, x.owner.a_banks)
        before = x.owner.clock
        d.sum.bank_tick(owner_quiescent=True, control=None, read=None, write=None,
                        response_ready=False, abort=False)
        self.assertEqual(x.owner.clock, before + 1)
        self.assertEqual(x.host.jobs, 0)


class PublicationPredicateCold(unittest.TestCase):
    def test_full_entry_and_constant_continuation(self):
        p = isolated_publication()
        identity = p.validate(p.job)
        for _ in range(4): self.assertEqual(p.validate_fast(p.job), identity)
        self.assertEqual(p.counts['full_checks'], 1)
        self.assertEqual(p.counts['fast_checks'], 5)
        source = inspect.getsource(DiagnosticPublicKvPublication.validate_fast)
        self.assertNotIn('sha256', source)
        self.assertNotIn('set(', source)
        self.assertNotIn('range(', source)
        self.assertEqual(p.validate(p.job), identity)
        self.assertEqual(p.counts['full_checks'], 2)

    def test_original_write_guard_rejects_kv_and_allows_attention_debt(self):
        p = isolated_publication()
        p.validate(p.job)
        memory = p.physical
        with self.assertRaisesRegex(ValueError, 'immutable/published'):
            memory.write_event('command', SimpleNamespace(address=p.region['base'], beats=1, tag=1))
        att = memory.regions['att']
        memory.write_event('command', SimpleNamespace(address=att['base'], beats=1, tag=2))
        memory.write_event('data', SimpleNamespace(words=(0,) * 16, mask=(1 << 64) - 1, last=True))
        p.validate_fast(p.job)
        self.assertIsNotNone(p.pending())
        memory.write_event('ack', SimpleNamespace(tag=2, error=False, nbytes=64))
        p.validate(p.job)
        self.assertIsNone(p.pending())

    def test_fast_identity_generation_length_and_write_guard_fail_closed(self):
        for name, value in (('data', bytearray(16 * 2048 + 128)), ('acked', set()),
                            ('written', set()), ('records', []), ('published', False), ('terminal', False)):
            p = isolated_publication()
            p.region[name] = value
            with self.assertRaises(LoanFault, msg=name): p.validate_fast(p.job)
        p = isolated_publication()
        p.physical.fixture.config = replace(p.config, epoch=p.epoch + 1)
        with self.assertRaises(LoanFault): p.validate_fast(p.job)
        p = isolated_publication()
        p.physical.write_event = lambda *args: None
        with self.assertRaisesRegex(LoanFault, 'write guard'): p.validate_fast(p.job)
        p = isolated_publication()
        p.region['acked'].pop()
        with self.assertRaises(LoanFault): p.validate_fast(p.job)

    def test_final_full_audit_catches_same_size_data_ack_and_guard_mutations(self):
        for mutation in ('payload', 'ack', 'canary', 'record', 'publication'):
            p = isolated_publication()
            p.validate(p.job)
            if mutation == 'payload': p.data[64] ^= 1
            elif mutation == 'ack':
                p.acked.remove(p.region['base']); p.acked.add(p.region['base'] + p.region['extent'])
            elif mutation == 'canary': p.data[0] ^= 1
            elif mutation == 'record': p.records[0][1].tag += 1
            else: p.published[0] = (0, 64)
            p.validate_fast(p.job)  # documented fixed-size continuation checks
            with self.assertRaises(LoanFault, msg=mutation): p.validate(p.job)


class RouterPredicateCold(unittest.TestCase):
    def isolated_route(self, *, terminal=False):
        """Test clock/lease mechanics only; never authority constructor proof."""
        f, physical, x = cold_execution()
        route = DiagnosticSharedALoanRouter.__new__(DiagnosticSharedALoanRouter)
        route.dense, route.prefix = x.owner, x.prefix_owner
        route.guard, route.bank_identity = x.owner.a_banks, x.owner.a_banks.payload_identity
        route.active, route.job, route.counts, route.fault = True, object(), Counter(), None
        route.guard.lease = route
        route.scratch, route.storage = x.attention_owner.scratch, x.attention_owner.scratch.storage
        route.b_banks = x.owner.b_banks
        check = SimpleNamespace(full=0, fast=0, pending=lambda: None, identity=x.attention_owner.kv_identity)
        def fast(job): check.fast += 1
        def full(job): check.full += 1
        check.validate_fast, check.validate = fast, full
        route.publication = check
        scratch = x.attention_owner.scratch
        result = SimpleNamespace(status=None) if terminal else None
        a = SimpleNamespace(state='idle', matrix=SimpleNamespace(owner=None), scalar=x.prefix_owner.scalar,
            kv_identity=check.identity,
            matrix_client=None, matrix_request=None, memory_pending=False, abort_pending=False,
            local_pending=False, scratch=scratch, poison=False)
        a.ports = lambda: {'response': result}
        def tick(**inputs):
            self.assertEqual(route.guard.begins, 1)
            self.assertEqual(route.guard.actor, 'cache')
            return dict(response_fire=bool(result is not None and inputs.get('response_ready')), response=result)
        a.tick = tick
        a._fault = lambda *args: setattr(a, 'poison', True)
        route.attention = a
        return route, check

    def test_one_clock_before_cache_no_release_before_terminal(self):
        r, check = self.isolated_route()
        before = r.dense.clock
        for _ in range(3): r.tick()
        self.assertEqual(r.dense.clock, before + 3)
        self.assertEqual(r.guard.counts['bank_edges'], 3)
        self.assertEqual(check.fast, 3)
        self.assertEqual(check.full, 0)
        self.assertIs(r.guard.lease, r)
        self.assertTrue(r.active)

    def test_terminal_requires_full_audit_and_releases_only_after_drain(self):
        r, check = self.isolated_route(terminal=True)
        r.tick(response_ready=False)
        self.assertIs(r.guard.lease, r)
        self.assertEqual(check.full, 0)
        self.assertTrue(r.tick(response_ready=True)['response_fire'])
        self.assertEqual(check.full, 2)
        self.assertIsNone(r.guard.lease)
        self.assertFalse(r.active)
        self.assertEqual(r.counts['releases'], 1)

    def test_failed_full_audit_holds_terminal_and_a_lease(self):
        r, check = self.isolated_route(terminal=True)
        def invalid(job): raise LoanFault('synthetic final hash corruption')
        check.validate = invalid
        before = r.dense.clock
        with self.assertRaises(LoanFault): r.tick(response_ready=True)
        self.assertEqual(r.dense.clock, before)
        self.assertIs(r.guard.lease, r)
        self.assertTrue(r.active)
        self.assertTrue(r.attention.scratch.revoked)
        self.assertEqual(r.counts['releases'], 0)

    def test_detached_bank_or_changed_kv_identity_keeps_lease(self):
        r, _ = self.isolated_route()
        r.attention.kv_identity = replace(r.attention.kv_identity, producer_k=999)
        with self.assertRaisesRegex(LoanFault, 'identity changed'): r.tick()
        self.assertIs(r.guard.lease, r)
        self.assertEqual(r.counts['releases'], 0)

    def test_pending_reply_debt_prevents_release(self):
        r, check = self.isolated_route(terminal=True)
        check.pending = lambda: object()
        with self.assertRaisesRegex(LoanFault, 'before local/DDR'): r.tick(response_ready=True)
        self.assertIs(r.guard.lease, r)
        self.assertTrue(r.active)


if __name__ == '__main__':
    unittest.main()
