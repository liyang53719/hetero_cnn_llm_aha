"""Cold transport controls only: no numerical service or native execution.

DenseHarness drives the actual Dense owner with opaque Matrix control tokens.
The actual OfficialAttentionOwner test stops before delivering its first K reply.
ScriptedTransportConsumer explicitly returns CONTROL_ONLY, never numerical PASS.
"""
import ast
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from candidates.qwen2_resident_matrix.ffn_public import prefix_owners as p
from candidates.qwen2_resident_matrix.official_bf16.owners import OfficialAttentionOwner
from candidates.qwen2_resident_matrix.ffn_attention.attention_owner import AttentionOwner
from candidates.qwen2_resident_matrix.raw_kv_parent.model import ParentLoan, DenseReductionOwner
from candidates.qwen2_resident_matrix.raw_kv_parent.test_model import DenseHarness
from candidates.qwen2_resident_matrix.raw_kv.model import location
from .model import PublicKvTransport


def job():
    return p.Job('Attention', (9 << 16) | 12, 0x100000, 0x200000,
                 0x400000, 1, 1536, 128, 6144, c=0x200400)


class InertScalar:
    """Only ownership controls; invoking an arithmetic primitive fails the test."""
    def __init__(self):
        self.client, self.calls = None, Counter()

    def acquire(self, client):
        if self.client is not None:
            return False
        self.client = client
        return True

    def release(self, client):
        if self.client is not client:
            raise AssertionError('inert scalar release mismatch')
        self.client = None

    def op(self, *args, **kwargs):
        raise AssertionError('cold test reached scalar arithmetic')


class InertMatrix:
    """Legacy client's idle controls only; no CDLL, Matrix packet or arithmetic."""
    def __init__(self):
        self.owner, self.mode = None, None
        self.reset_required = False
        self.epoch = self.ticket = 0
        self.counts = Counter()
        self.result = self.done = None
        self.lib = SimpleNamespace(matrix_normal_fmas=lambda: 0, matrix_state=lambda: 0)

    def acquire(self, owner, mode, tag):
        if self.owner is not None:
            return False
        self.owner, self.mode = owner, mode
        self.counts['owner_acquires'] += 1
        return True

    def _check_owner(self, owner, mode):
        if self.owner is not owner or self.mode != mode:
            raise AssertionError('inert ownership mismatch')

    def _check_event(self, *, epoch):
        if epoch != self.epoch:
            raise AssertionError('inert epoch mismatch')

    def abort(self, owner):
        self._check_owner(owner, 'normal')
        self.reset_required = True
        self.counts['aborts'] += 1

    def retire_owner_response(self, owner):
        self._check_owner(owner, 'normal')
        self.counts['owner_responses'] += 1

    def release(self, owner):
        self._check_owner(owner, 'normal')
        self.owner = self.mode = None
        self.counts['owner_releases'] += 1

    def accept_group(self, *args, **kwargs):
        raise AssertionError('cold test reached Matrix group')

    def accept_step(self, *args, **kwargs):
        raise AssertionError('cold test reached native arithmetic')


class ScriptedTransportConsumer:
    """Small control-channel fixture, not an Attention arithmetic replacement.

    Requests and payloads are fixed transport tokens. Its explicit CONTROL_ONLY
    terminal does not assert Attention success or the original write-byte fence.
    """
    def __init__(self, requests):
        self.requests, self.index = tuple(requests), 0
        self.state, self.poison = 'idle', False
        self.job = self.result = None
        self.received = []
        self.reset_count = self.terminal_fires = self.ack_bytes = 0

    def ports(self):
        return dict(job_ready=self.state == 'idle' and not self.poison,
                    memory=self.requests[self.index] if self.state == 'issue' else None,
                    memory_response_ready=self.state == 'wait',
                    response=self.result if self.state == 'finish' else None,
                    reset_required=self.poison, state=self.state)

    def _finish(self):
        self.state = 'finish'
        self.result = p.OwnerResult(self.job.tag, 'CONTROL_ABORT' if self.poison else 'CONTROL_ONLY',
                                    self.ack_bytes, 0)

    def tick(self, *, job=None, memory_ready=False, memory_response=None,
             response_ready=False, local_reset=False, **controls):
        e = self.ports()
        e.update(job_fire=False, memory_fire=False, memory_response_fire=False, response_fire=False)
        if local_reset:
            self.reset_count += 1
            self.poison = True
            e['job_ready'], e['memory'], e['response'] = False, None, None
            if self.state != 'wait':
                self._finish()
        elif job is not None and e['job_ready']:
            self.job, self.state = job, 'issue'
            e['job_fire'] = True
        if e['memory'] is not None and memory_ready:
            self.state = 'wait'
            e['memory_fire'] = True
        if e['memory_response_ready'] and memory_response is not None:
            q, r = self.requests[self.index], memory_response
            if type(r) is not p.MemoryResponse or r.tag != q.tag:
                raise AssertionError('script received a foreign response')
            e['memory_response_fire'] = True
            self.received.append(r)
            self.poison |= r.error
            if q.write and not r.error:
                self.ack_bytes += r.nbytes
            self.index += 1
            if self.poison or self.index == len(self.requests):
                self._finish()
            else:
                self.state = 'issue'
        if e['response'] is not None and response_ready:
            self.terminal_fires += 1
            self.state, self.result = 'idle', None
            e['response_fire'] = True
        return e


class TransportTests(unittest.TestCase):
    def scripted(self, parent=None, *, write=False, repeated_read=False):
        j = job()
        requests = [p.MemoryRequest(j.b, (1 << 63) | 3)]
        if repeated_read:
            requests.append(p.MemoryRequest(j.b, (1 << 63) | 5))
        if write:
            requests.append(p.MemoryRequest(j.dst, (1 << 63) | 4, True,
                                            bytes(range(64)), p.FULL_MASK))
        consumer = ScriptedTransportConsumer(requests)
        transport = PublicKvTransport(owner=consumer, parent=parent or ParentLoan(enabled=True), job=j)
        self.assertTrue(transport.tick(job=j)['job_fire'])
        return transport

    def until(self, transport, predicate, **inputs):
        for _ in range(100):
            edge = transport.tick(**inputs)
            if predicate(edge):
                return edge
        self.fail(('transport did not progress', transport.supply.state, transport.owner.state))

    def miss(self, transport):
        edge = self.until(transport, lambda e: e['memory_fire'])
        self.assertEqual(edge['memory'], transport.pending)
        self.assertEqual(transport.route, 'kv')
        self.assertTrue(transport.supply.ddr_pending)
        return edge['memory']

    def held_raw_read(self, transport):
        request = self.miss(transport)
        response = p.MemoryResponse(request.tag, bytes(range(64)))
        edge = transport.tick(memory_response=response)
        self.assertTrue(edge['memory_response_fire'])
        self.assertIsNone(transport.pending)
        self.until(transport, lambda e: transport.supply.state == 'read_wait' and
                   transport.parent.raw.response is not None)
        return request, transport.parent.raw.response

    def test_actual_official_owner_reads_q_then_first_k_without_arithmetic(self):
        self.assertIs(OfficialAttentionOwner.tick, AttentionOwner.tick)
        scalar, matrix = InertScalar(), InertMatrix()
        owner = OfficialAttentionOwner(matrix, scalar)
        parent, j = ParentLoan(enabled=True), job()
        transport = PublicKvTransport(owner=owner, parent=parent, job=j)
        banks = parent.owner.a_banks
        with patch.object(parent, 'tick', wraps=parent.tick) as tick:
            self.assertTrue(transport.tick(job=j)['job_fire'])
            self.assertEqual(tick.call_count, transport.ticks)
            for index in range(8):
                edge = transport.tick()
                self.assertTrue(edge['memory_fire'])
                q = edge['memory']
                self.assertEqual(q.address, j.a + 64 * index)
                self.assertEqual(transport.route, 'direct')
                self.assertIsNone(parent.raw.owner)
                edge = transport.tick(memory_response=p.MemoryResponse(q.tag, bytes(64)))
                self.assertTrue(edge['memory_response_fire'])
                self.assertEqual(tick.call_count, transport.ticks)
            self.assertEqual(owner.ports()['memory'].address, j.b)
            edge = transport.tick()
            self.assertTrue(edge['core_memory_fire'])
            self.assertFalse(edge['memory_fire'])
            request = self.miss(transport)
            self.assertEqual(request.address, j.b)
            self.assertEqual(tick.call_count, transport.ticks)
            self.assertEqual(parent.owner.clock, transport.ticks)
        self.assertEqual(owner.counts['read_responses'], 8)
        self.assertEqual(scalar.calls, Counter())
        self.assertEqual(matrix.counts['normal_steps'], 0)
        self.assertIs(parent.raw.banks, banks)
        self.assertIs(transport.supply.parent, parent)
        self.assertIs(transport.pending, request)
        self.assertIsInstance(parent.owner, DenseReductionOwner)

    def test_actual_dense_attention_transport_dense_reuses_same_parent_and_banks(self):
        h = DenseHarness()
        h.until(lambda: h.response is not None)
        parent, dense, banks = h.parent, h.owner, h.owner.a_banks
        words = banks.words
        self.assertEqual(h.response, (h.job.tag, None, 2048))
        transport = self.scripted(parent)
        self.held_raw_read(transport)
        self.until(transport, lambda e: e['supply']['released'])
        self.assertEqual(transport.ports()['response'].status, 'CONTROL_ONLY')
        self.assertTrue(transport.tick(response_ready=True)['response_fire'])
        self.assertIs(parent.owner, dense)
        self.assertIs(parent.raw.banks, banks)
        self.assertIs(dense.tiles.banks, banks)
        self.assertIs(banks.words, words)
        self.assertFalse(any(parent.debts().values()))
        h.job = replace(h.job, tag=h.job.tag + 1)
        h.response = None
        edge = parent.tick(job=h.job)
        self.assertTrue(edge['owner']['job_ready'])
        self.assertIs(dense.job, h.job)
        h.until(lambda: h.response is not None)
        self.assertEqual(h.response, (h.job.tag, None, 2048))
        self.assertEqual(h.counts['step_fire'], 64)
        self.assertEqual(h.counts['write_ack_fire'], 32)
        self.assertIs(banks.words, words)

    def test_delayed_raw_ack_and_output_ack_hold_host_terminal(self):
        transport = self.scripted(write=True)
        _, held = self.held_raw_read(transport)
        edge = transport.tick(raw_ack_ready=False, response_ready=True)
        self.assertTrue(edge['core_memory_response_fire'])
        self.assertFalse(edge['memory_response_fire'])
        self.assertEqual(transport.supply.state, 'ack_wait')
        self.assertIs(transport.parent.raw.response, held)
        edge = transport.tick(raw_ack_ready=False, response_ready=True)
        self.assertTrue(edge['memory_fire'])
        write = edge['memory']
        self.assertTrue(write.write)
        for _ in range(3):
            edge = transport.tick(raw_ack_ready=False, response_ready=True)
            self.assertFalse(edge['response_fire'])
            self.assertIsNone(transport.ports()['response'])
            self.assertIs(transport.pending, write)
            self.assertIs(transport.parent.raw.response, held)
        edge = transport.tick(memory_response=p.MemoryResponse(write.tag),
                              raw_ack_ready=False, response_ready=True)
        self.assertTrue(edge['memory_response_fire'])
        self.assertEqual(transport.owner.ack_bytes, 64)
        terminal = transport.owner.ports()['response']
        for _ in range(3):
            edge = transport.tick(raw_ack_ready=False, response_ready=True)
            self.assertFalse(edge['response_fire'])
            self.assertFalse(edge['supply']['released'])
            self.assertIsNone(edge['response'])
            self.assertEqual(transport.owner.ports()['response'], terminal)
        edge = transport.tick(raw_ack_ready=True, response_ready=True)
        self.assertTrue(edge['supply']['parent']['raw']['acked'])
        self.assertFalse(edge['response_fire'])
        edge = self.until(transport, lambda e: e['supply']['released'], response_ready=True)
        self.assertFalse(edge['response_fire'])
        self.assertEqual(transport.ports()['response'], terminal)
        self.assertTrue(transport.tick(response_ready=True)['response_fire'])
        self.assertEqual(transport.owner.terminal_fires, 1)
        self.assertEqual(transport.supply.counts['core_responses'], 1)
        self.assertFalse(transport.parent.raw.blocked)

    def test_foreign_ddr_reply_retains_matching_debt_and_cannot_release(self):
        transport = self.scripted()
        request = self.miss(transport)
        edge = transport.tick(memory_response=p.MemoryResponse(request.tag ^ 1, bytes(64)),
                              response_ready=True)
        self.assertFalse(edge['memory_response_fire'])
        self.assertTrue(transport.supply.ddr_pending)
        self.assertIs(transport.pending, request)
        self.assertEqual(transport.owner.reset_count, 1)
        for _ in range(4):
            edge = transport.tick(response_ready=True)
            self.assertFalse(edge['response_fire'] or edge['supply']['released'])
            self.assertIsNone(transport.ports()['response'])
            self.assertIs(transport.pending, request)
        edge = transport.tick(memory_response=p.MemoryResponse(request.tag, bytes(64)),
                              response_ready=True)
        self.assertTrue(edge['memory_response_fire'])
        self.assertFalse(transport.supply.ddr_pending)
        self.until(transport, lambda e: e['supply']['released'], response_ready=True)
        self.assertEqual(transport.owner.received, [p.MemoryResponse(request.tag, bytes(64), True)])
        self.assertEqual(transport.owner.reset_count, 1)
        self.assertEqual(transport.ports()['response'].status, 'CONTROL_ABORT')
        self.assertTrue(transport.tick(response_ready=True)['response_fire'])
        self.assertFalse(any(transport.supply.valid))

    def test_repeat_read_is_a_shared_bank_hit_without_another_external_request(self):
        transport = self.scripted(repeated_read=True)
        request, held = self.held_raw_read(transport)
        parent, banks = transport.parent, transport.parent.owner.a_banks
        payload = int.from_bytes(bytes(range(64)), 'little')
        lo, hi, row = location(0)
        self.assertEqual(banks.words[lo][row], payload & ((1 << 256) - 1))
        self.assertEqual(banks.words[hi][row], payload >> 256)
        edge = transport.tick()
        self.assertTrue(edge['core_memory_response_fire'])
        for _ in range(30):
            edge = transport.tick(memory_ready=False)
            self.assertFalse(edge['memory_fire'])
            self.assertIsNone(edge['memory'])
            self.assertIs(parent.raw.banks, banks)
            if edge['core_memory_response_fire']:
                break
        else:
            self.fail('raw cache hit required external DDR progress')
        self.assertEqual(transport.supply.counts['ddr_requests'], 1)
        self.assertEqual(transport.supply.counts['fills'], 1)
        self.assertEqual(transport.supply.counts['hits'], 1)
        self.assertEqual(transport.owner.received,
                         [p.MemoryResponse(request.tag, bytes(range(64))),
                          p.MemoryResponse((1 << 63) | 5, bytes(range(64)))])
        self.until(transport, lambda e: e['supply']['released'])
        self.assertFalse(any(transport.supply.valid))

    def test_abort_after_core_reply_keeps_raw_ack_debt_and_never_duplicates_reply(self):
        transport = self.scripted()
        _, held = self.held_raw_read(transport)
        edge = transport.tick(raw_ack_ready=False)
        self.assertTrue(edge['core_memory_response_fire'])
        self.assertEqual(transport.supply.state, 'ack_wait')
        for _ in range(4):
            edge = transport.tick(abort=True, raw_ack_ready=False, response_ready=True)
            self.assertFalse(edge['core_memory_response_fire'])
            self.assertFalse(edge['response_fire'] or edge['supply']['released'])
            self.assertIs(transport.parent.raw.response, held)
            self.assertTrue(transport.parent.raw.blocked)
            self.assertFalse(transport.parent.raw.drained)
        self.assertEqual(transport.owner.reset_count, 1)
        self.assertEqual(len(transport.owner.received), 1)
        edge = transport.tick(raw_ack_ready=True, response_ready=True)
        self.assertTrue(edge['supply']['parent']['raw']['acked'])
        self.assertFalse(edge['response_fire'])
        self.until(transport, lambda e: e['supply']['released'], response_ready=True)
        self.assertEqual(transport.ports()['response'].status, 'CONTROL_ABORT')
        self.assertTrue(transport.tick(response_ready=True)['response_fire'])
        self.assertEqual(transport.owner.terminal_fires, 1)
        self.assertEqual(transport.supply.counts['core_responses'], 1)

    def test_foreign_direct_reply_before_acceptance_faults_without_inventing_debt(self):
        scalar, matrix = InertScalar(), InertMatrix()
        owner, j = OfficialAttentionOwner(matrix, scalar), job()
        transport = PublicKvTransport(owner=owner, parent=ParentLoan(enabled=True), job=j)
        self.assertTrue(transport.tick(job=j)['job_fire'])
        offered = transport.ports()['memory']
        self.assertEqual(offered.address, j.a)
        self.assertFalse(transport.tick(memory_ready=False)['memory_fire'])
        self.assertIs(transport.ports()['memory'], offered)
        edge = transport.tick(memory_ready=True,
                              memory_response=p.MemoryResponse(offered.tag + 1, bytes(64)),
                              response_ready=True)
        self.assertFalse(edge['memory_fire'] or edge['core_memory_fire'])
        self.assertFalse(edge['memory_response_fire'] or edge['core_memory_response_fire'])
        self.assertFalse(edge['response_fire'])
        self.assertTrue(transport.supply.reset_required)
        self.assertIsNone(transport.pending)
        self.assertIsNone(transport.route)
        self.assertIsNone(transport.kv_request)
        self.assertFalse(owner.memory_pending or transport.supply.ddr_pending)
        self.assertEqual(transport.supply.counts['ddr_requests'], 0)
        self.assertEqual(transport.supply.counts['core_requests'], 0)
        edge = self.until(transport, lambda e: e['response_fire'], response_ready=True)
        self.assertEqual(edge['response'].status, 'Protocol')
        self.assertEqual(owner.state, 'locked')
        self.assertEqual(scalar.calls, Counter())
        self.assertEqual(matrix.counts['normal_steps'], 0)
        self.assertEqual(matrix.counts['aborts'], 1)

    def test_fault_edge_cannot_retire_an_advertised_successful_terminal(self):
        j = job()
        consumer = HostControlOnlyConsumer([p.MemoryRequest(j.b, 17)])
        transport = PublicKvTransport(owner=consumer, parent=ParentLoan(enabled=True), job=j)
        self.assertTrue(transport.tick(job=j)['job_fire'])
        self.held_raw_read(transport)
        self.until(transport, lambda e: e['supply']['released'])
        success = transport.ports()['response']
        self.assertIsNone(success.status)  # CONTROL_ONLY protocol success token.
        edge = transport.tick(abort=True, response_ready=True)
        self.assertFalse(edge['response_fire'])
        self.assertEqual(edge['response'], success)
        self.assertEqual(consumer.terminal_fires, 0)
        self.assertTrue(transport.supply.reset_required)
        self.assertFalse(transport.parent.raw.blocked)
        self.assertTrue(transport.parent.raw.drained)
        edge = self.until(transport, lambda e: e['response_fire'], response_ready=True)
        self.assertEqual(edge['response'].status, 'CONTROL_ABORT')
        self.assertEqual(consumer.terminal_fires, 1)
        self.assertEqual(consumer.reset_count, 1)

    def test_external_api_uses_accepted_events_and_never_exposes_core_ready(self):
        transport = self.scripted()
        def tick(**inputs):
            self.assertNotIn('memory_response_ready', transport.ports())
            edge = transport.tick(**inputs)
            self.assertNotIn('memory_response_ready', edge)
            self.assertIn('core_memory_response_ready', edge)
            if edge['memory_response_fire']:
                self.assertIsNotNone(inputs.get('memory_response'))
            return edge
        for _ in range(20):
            edge = tick()
            self.assertFalse(edge['memory_response_fire'])
            if edge['memory_fire']:
                request = edge['memory']
                break
        else:
            self.fail('no external miss request')
        edge = tick(memory_response=p.MemoryResponse(request.tag, bytes(64)))
        self.assertTrue(edge['memory_response_fire'])
        self.assertFalse(edge['core_memory_response_fire'])
        self.assertTrue(edge['core_memory_response_ready'])
        self.assertTrue(edge['supply']['parent']['raw']['accepted'])
        for _ in range(20):
            edge = tick()
            self.assertFalse(edge['memory_response_fire'])
            if edge['core_memory_response_fire']:
                self.assertTrue(edge['core_memory_response_ready'])
                self.assertTrue(edge['supply']['response_fire'])
                break
        else:
            self.fail('no core response after accepted raw fill')

    def test_default_off_parent_rejected_without_hidden_allocation(self):
        parent, j = ParentLoan(), job()
        banks = parent.owner.a_banks
        with self.assertRaisesRegex(ValueError, 'enabled original parent'):
            PublicKvTransport(owner=ScriptedTransportConsumer([]), parent=parent, job=j)
        self.assertIs(parent.owner.a_banks, banks)
        self.assertIsNone(parent.raw.owner)
        self.assertEqual(parent.owner.clock, 0)


class HostControlOnlyConsumer(ScriptedTransportConsumer):
    """Opaque protocol writes/ACKs, exclusively for real Host FSM testing.

    A zero status is required by the Host's success branch. It means only that
    this scripted control transaction completed; it is not numerical evidence.
    The byte count comes from accepted scripted ACKs, and both FMA counts stay 0.
    """
    evidence_scope = 'CONTROL_ONLY'

    def _finish(self):
        super()._finish()
        if not self.poison:
            self.result = replace(self.result, status=None)


def prepared_classes():
    """Execute exact class declarations, using copied original module globals.

    No service constructor, native library, numerical entrypoint or arithmetic
    owner method is replaced. Official/Reduced constructors remain unexecuted.
    """
    from . import prepare
    from candidates.qwen2_resident_matrix.ffn_public import execute_numeric as original
    from candidates.qwen2_resident_matrix.official_bf16 import execution as official
    from candidates.qwen2_resident_matrix.dense_block_reduce import public_execution as reduced
    def declaration(source, name, namespace):
        node = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == name)
        module = ast.Module(body=[node], type_ignores=[])
        exec(compile(module, '<pinned-cold-class>', 'exec'), namespace)
        return namespace[name]
    with tempfile.TemporaryDirectory(prefix='public-kv-cold-') as directory:
        out = Path(directory) / 'source'
        result = prepare.prepare(out)
        Public = declaration((out / prepare.TARGETS[0]).read_text(), 'PublicExecution', dict(vars(original)))
    Official = declaration(Path(official.__file__).read_text(), 'OfficialPublicExecution',
                           dict(vars(official), PublicExecution=Public))
    Reduced = declaration(Path(reduced.__file__).read_text(), 'ReducedPublicExecution',
                          dict(vars(reduced), PublicExecution=Public, OfficialPublicExecution=Official))
    return Public, Official, Reduced, result


class PublicSourceAndHostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.Public, cls.Official, cls.Reduced, cls.preparation = prepared_classes()

    def public_control_fixture(self):
        from candidates.qwen2_resident_matrix.ffn_public import fixture, model
        from candidates.qwen2_resident_matrix.official_bf16.owners import OfficialPrefixOwner
        from candidates.qwen2_resident_matrix.raw_kv_parent import model as parent_model
        f = fixture.make_qwen2_21_fixture(16)
        scalar, matrix = InertScalar(), InertMatrix()
        region = f.config.regions[3]
        dense = DenseReductionOwner(parent_model.down.PrefixWorkspace(
            region.base, 16384, f.config.epoch + 1, 128), enable_ffn_tiles=True,
            enable_ffn_window=True, enable_ffn_drain=True, enable_dense_drain=True,
            enable_k_window=True)
        host = model.group.HostControl(enabled=True, legacy_prefix=True, legacy_attention=True)
        x = self.Public(model.PublicFrontend(f.memory, f.config), dense,
                        SimpleNamespace(event=lambda event: None), time.monotonic() + 10,
                        host=host, prefix_owner=OfficialPrefixOwner(scalar),
                        attention_owner=OfficialAttentionOwner(matrix, scalar), matrix_service=matrix)
        # Existing raw-public control fixture pattern: ten opaque completion
        # tokens advance only the actual Host FSM, not any numerical backend.
        for pc in range(10):
            j = x.advance_to_request()['ordinary_request']
            self.assertEqual(j.tag & 0xffff, pc)
            self.assertTrue(x._host_edge(request_ready=True)['request_fire'])
            token = SimpleNamespace(tag=j.tag, status=None, write_bytes=j.write_bytes,
                                    useful_macs=0, executed_macs=0, evidence_scope='CONTROL_ONLY')
            self.assertTrue(x._host_edge(owner_result=token)['owner_result_fire'])
            x.completion_ready = True
            self.assertTrue(x._host_edge()['completion_fire'])
            x.completion_ready = False
        j = x.advance_to_request()['ordinary_request']
        self.assertEqual((x.host.pc, x.host.completed, x.host.jobs), (12, 10, 10))
        self.assertEqual(j.kind, 'Attention')
        self.assertEqual(len(x.host.scanner.trace), 62)
        return x, j

    def test_pinned_inheritance_default_off_and_original_host_first_k_path(self):
        self.assertEqual(self.preparation['status'], 'PASS_PREPARATION_ONLY')
        self.assertFalse(self.preparation['arithmetic_executed'])
        self.assertIs(self.Reduced.attention_edge, self.Public.attention_edge)
        self.assertIs(self.Official.attention_edge, self.Public.attention_edge)
        self.assertIs(self.Reduced.bind_attention_transport, self.Public.bind_attention_transport)
        x, j = self.public_control_fixture()
        self.assertIsNone(x.attention_transport)
        parent = ParentLoan(owner=x.owner, enabled=True)
        transport = PublicKvTransport(owner=x.attention_owner, parent=parent, job=j)
        x.bind_attention_transport(transport)
        clock = x.owner.clock
        edges = 0
        with patch.object(parent, 'tick', wraps=parent.tick) as tick:
            self.assertTrue(x.attention_edge(job=j)['job_fire']); edges += 1
            for index in range(8):
                edge = x.attention_edge(); edges += 1
                self.assertTrue(edge['memory_fire'])
                self.assertEqual(edge['memory'].address, j.a + 64 * index)
                self.assertTrue(x.attention_edge(memory_response=p.MemoryResponse(
                    edge['memory'].tag, bytes(64)))['memory_response_fire']); edges += 1
            for _ in range(20):
                edge = x.attention_edge(); edges += 1
                if edge['memory_fire']:
                    self.assertEqual(edge['memory'].address, j.b)
                    break
            else:
                self.fail('first public K request did not appear')
            self.assertEqual(tick.call_count, edges)
        self.assertEqual(x.owner.clock - clock, edges)
        self.assertEqual(x.counts['raw_kv_parent_edges'], edges)
        self.assertEqual(x.attention_jobs, 1)
        self.assertEqual((x.host.state, x.host.completed, x.host.jobs), ('waitDone', 10, 11))
        self.assertIsNone(x.ports()['completion'])
        self.assertEqual(x.attention_results, 0)
        self.assertEqual(x.prefix_owner.scalar.calls, Counter())
        self.assertEqual(x.matrix_service.counts['normal_steps'], 0)
        self.assertIs(parent.raw.banks, x.owner.a_banks)
        self.assertNotIn((j.dst, j.dst + j.write_bytes), x.host.published)

    def test_rejected_public_binding_is_atomic_and_default_off_ticks_once(self):
        x, j = self.public_control_fixture()
        parent = ParentLoan(owner=x.owner, enabled=True)
        bad = PublicKvTransport(owner=ScriptedTransportConsumer([]), parent=parent, job=j)
        with self.assertRaises(ValueError):
            x.bind_attention_transport(bad)
        self.assertIsNone(x.attention_transport)
        self.assertIsNone(x.attention_transport_binding)
        clock = x.owner.clock
        self.assertTrue(x.attention_edge(job=j)['job_fire'])
        self.assertEqual(x.owner.clock, clock + 1)
        self.assertEqual(x.counts['raw_kv_parent_edges'], 0)
        self.assertIsNone(parent.raw.owner)

    def test_actual_host_holds_three_control_only_completions_until_raw_release(self):
        x, j = self.public_control_fixture()
        # This is separate from the concrete-owner PublicExecution bind test.
        # The actual Host sees a scripted channel solely to test its FSM fences.
        requests = [p.MemoryRequest(j.b, 0x8000000000000001)]
        requests.extend(p.MemoryRequest(address, 0x8000000000000002 + index,
                         True, bytes(64), p.FULL_MASK)
                        for index, address in enumerate(range(j.dst, j.dst + j.write_bytes, 64)))
        consumer = HostControlOnlyConsumer(requests)
        transport = PublicKvTransport(owner=consumer, parent=ParentLoan(owner=x.owner, enabled=True), job=j)
        before = list(x.host.published)
        def cycle(**inputs):
            hp = x.host.ports()
            edge = transport.tick(response_ready=hp['owner_result_ready'], **inputs)
            he = x.host.tick(request_ready=edge['job_fire'],
                             owner_result=edge['response'] if edge['response_fire'] else None,
                             reset_required=transport.supply.reset_required)
            self.assertEqual(he['request_fire'], edge['job_fire'])
            self.assertEqual(he['owner_result_fire'], edge['response_fire'])
            self.assertEqual(x.host.published, before)
            return edge
        self.assertTrue(cycle(job=j)['job_fire'])
        pending = None
        for _ in range(30):
            edge = cycle(memory_response=p.MemoryResponse(pending.tag, bytes(64)) if pending else None)
            if edge['memory_response_fire']:
                pending = None
            if edge['memory_fire']:
                pending = edge['memory']
            if transport.supply.state == 'read_wait' and transport.parent.raw.response is not None:
                break
        else:
            self.fail('Host control raw reply did not arrive')
        held = transport.parent.raw.response
        self.assertTrue(cycle(raw_ack_ready=False)['core_memory_response_fire'])
        for _ in range(2 * len(requests) + 10):
            edge = cycle(raw_ack_ready=False,
                         memory_response=p.MemoryResponse(pending.tag) if pending else None)
            if edge['memory_response_fire']:
                pending = None
            if edge['memory_fire']:
                self.assertTrue(edge['memory'].write)
                pending = edge['memory']
            self.assertIs(transport.parent.raw.response, held)
            self.assertEqual(x.host.state, 'waitDone')
            self.assertIsNone(x.host.ports()['completion'])
            if consumer.ports()['response'] is not None:
                break
        else:
            self.fail('bounded scripted output ACK sequence did not finish')
        self.assertEqual(consumer.ack_bytes, j.write_bytes)
        self.assertEqual(consumer.result.useful_macs, 0)
        self.assertEqual(consumer.result.executed_macs, 0)
        for _ in range(3):
            self.assertFalse(cycle(raw_ack_ready=False)['response_fire'])
            self.assertEqual(x.host.state, 'waitDone')
        for _ in range(5):
            edge = cycle()
            if edge['response_fire']:
                break
        else:
            self.fail('Host did not receive the retired control terminal')
        self.assertFalse(transport.parent.raw.blocked)
        self.assertEqual(x.host.state, 'complete')
        for pc in (10, 11, 12):
            completion = x.host.ports()['completion']
            self.assertEqual(completion.pc, pc)
            for _ in range(3):
                self.assertFalse(x.host.tick()['completion_fire'])
                self.assertEqual(x.host.ports()['completion'], completion)
                self.assertEqual(x.host.published, before)
            self.assertTrue(x.host.tick(completion_ready=True)['completion_fire'])
            if pc < 12:
                self.assertEqual(x.host.published, before)
        self.assertEqual(x.host.published[-1], (j.dst, j.dst + j.write_bytes))
        self.assertEqual((x.host.pc, x.host.completed, x.host.jobs), (13, 13, 11))
        self.assertEqual(consumer.evidence_scope, 'CONTROL_ONLY')


class PreparationNegativeTests(unittest.TestCase):
    def sources(self, directory):
        from . import prepare
        out = Path(directory) / 'source'
        report = prepare.prepare(out)
        original = {name: (prepare.ROOT / name).read_text() for name in prepare.TARGETS}
        generated = {name: (out / name).read_text() for name in prepare.TARGETS}
        return prepare, out, report, original, generated

    def test_preparation_is_reproducible_and_rejects_existing_output(self):
        from . import prepare
        with tempfile.TemporaryDirectory(prefix='public-kv-repeat-') as directory:
            module, first, report, _, generated = self.sources(directory)
            second = Path(directory) / 'second'
            again = module.prepare(second)
            self.assertEqual(report['generated'], again['generated'])
            self.assertEqual(generated, {name: (second / name).read_text() for name in module.TARGETS})
            self.assertFalse(report['arithmetic_executed'] or report['public_fullgraph_executed'])
            with self.assertRaisesRegex(ValueError, 'fresh source directory'):
                prepare.prepare(first)

    def test_changed_source_or_patch_is_rejected_before_composition(self):
        from . import prepare
        original = Path.read_bytes
        for target, message in ((prepare.ROOT / prepare.TARGETS[0], 'public source drift'),
                                (prepare.HERE / 'public_execution.patch', 'public hook patch drift')):
            with self.subTest(target=target.name), tempfile.TemporaryDirectory(prefix='public-kv-drift-') as directory:
                def changed(path):
                    raw = original(path)
                    return raw + b'\n# controlled drift\n' if path == target else raw
                out = Path(directory) / 'source'
                with patch.object(Path, 'read_bytes', changed):
                    with self.assertRaisesRegex(ValueError, message):
                        prepare.prepare(out)
                self.assertFalse(out.exists())

    def test_scope_rejects_physical_loop_ordinary_edge_and_default_on_mutations(self):
        with tempfile.TemporaryDirectory(prefix='public-kv-scope-') as directory:
            module, _, _, original, generated = self.sources(directory)
            for mutation, message in (('physical', 'physical memory loop'),
                                      ('ordinary', 'unrelated public execution'),
                                      ('default', 'default-off public flag')):
                with self.subTest(mutation=mutation):
                    name = module.TARGETS[0 if mutation == 'ordinary' else 1]
                    tree = ast.parse(generated[name])
                    if mutation == 'ordinary':
                        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'PublicExecution')
                        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'ordinary_edge')
                        method.body.append(ast.Pass())
                    else:
                        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'execute_attention_owner')
                        if mutation == 'physical':
                            next(n for n in function.body if isinstance(n, ast.While)).body.append(ast.Pass())
                        else:
                            function.args.kw_defaults[-1] = ast.Constant(value=True)
                    changed = dict(generated, **{name: ast.unparse(ast.fix_missing_locations(tree))})
                    with self.assertRaisesRegex(ValueError, message):
                        module.check_scope(original, changed)


if __name__ == '__main__':
    unittest.main()
