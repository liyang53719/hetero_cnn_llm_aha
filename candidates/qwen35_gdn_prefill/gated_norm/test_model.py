"""Synthetic transport/lifecycle checks with independent integer FP32 oracle.

M1 covers all 16 production heads. M16/M128 use one or two active test heads,
retain production 4096B/token stride and physically zero-write inactive heads.
These checks do not run a Dense arithmetic producer, native model, compiler,
checkpoint, Chisel or RTL. Test input producers perform real data/ACK/publish.
"""
from dataclasses import replace
from functools import lru_cache
import math
import random
import struct
import time
import unittest

from . import model as m
from .. import rms_owner as rms
from ..conv.scalar import ConvScalar
from ..conv.model import ConvOwner
from ..prep.scalar import PrepScalar
from ...qwen2_resident_matrix.ffn_public.test_prefix_owners import (
    exact, ref_add, ref_mul, ref_div, ref_sqrt, ref_bf)


def bf(values):
    return struct.pack('<' + 'H' * len(values), *(ref_bf(rms.word(v)) >> 16 for v in values))


def produced(memory, base, raw, tag=2):
    """Synthetic addressed producer, not a checkpoint/native/Dense fixture."""
    region = memory.allocate_output(base, len(raw))
    for offset in range(0, len(raw), 64):
        memory.begin_write(m.WriteCommand(base + offset, 1, tag))
        memory.write_data(struct.unpack('<32H', raw[offset:offset + 64]), True, mask=m.FULL_MASK)
        memory.acknowledge(m.WriteAck(tag, False, 64))
    memory.publish(base, (tag, None, len(raw)))
    return region


@lru_cache(maxsize=512)
def reference_exp(a):
    """Rational FP32 nodes; independent constants derived from Scala math."""
    magnitude = a & 0x7fffffff
    if exact(magnitude) >= 80:
        return 0
    z = ref_mul(magnitude, rms.word(1 / math.log(2)))
    k = int(exact(z))
    fraction = ref_add(z, rms.word(float(k)) ^ 0x80000000)
    coefficients = [rms.word(math.pow(-math.log(2), i) / math.factorial(i)) for i in range(8)]
    accumulator = coefficients[-1]
    for coefficient in reversed(coefficients[:-1]):
        accumulator = ref_add(ref_mul(accumulator, fraction), coefficient)
    return ref_mul(accumulator, (127 - k) << 23)


def oracle_head(core, gate, weights, *, gate_bf16=False, weight_bf16=False,
                attention_weight=False, normalize_bf16=True):
    core, gate = struct.unpack('<128H', core), struct.unpack('<128H', gate)
    weights = struct.unpack('<128I', weights)
    total = 0
    for raw in core:
        total = ref_add(total, ref_mul(raw << 16, raw << 16))
    mean = ref_mul(total, rms.word(1 / 128))
    inverse = ref_div(rms.word(1), ref_sqrt(ref_add(mean, rms.word(1e-6))))
    output = []
    for x, z, w in zip(core, gate, weights):
        normalized = ref_mul(x << 16, inverse)
        normalized = ref_bf(normalized) if normalize_bf16 else normalized
        w = ref_bf(w) if weight_bf16 else w
        w = ref_add(rms.word(1), w) if attention_weight else w
        weighted = ref_mul(w, normalized)
        z <<= 16
        e = reference_exp(z)
        reciprocal = ref_div(rms.word(1), ref_add(rms.word(1), e))
        sigmoid = ref_mul(reciprocal, e if z >> 31 else rms.word(1))
        activated = ref_mul(sigmoid, z)
        activated = ref_bf(activated) if gate_bf16 else activated
        output.append(ref_bf(ref_mul(weighted, activated)) >> 16)
    return struct.pack('<128H', *output)


def oracle(core, gate, weights, tokens, heads):
    output = bytearray(tokens * m.ROW_BYTES)
    for token in range(tokens):
        for head in range(heads):
            start = token * m.ROW_BYTES + head * m.HEAD_BYTES
            output[start:start + m.HEAD_BYTES] = oracle_head(
                core[start:start + m.HEAD_BYTES], gate[start:start + m.HEAD_BYTES], weights)
    return bytes(output)


class GatedNormTests(unittest.TestCase):
    def setup_driver(self, tokens=1, heads=1, *, core=None, gate=None, weight=None, prep=False):
        self.memory = m.TypedMemory()
        self.scalar = PrepScalar(enable_softplus=True) if prep else ConvScalar()
        self.owner = m.GatedNormOwner(self.scalar, heads=heads)
        rng = random.Random(381)
        core = bf([rng.uniform(-2, 2) for _ in range(2048)]) * tokens if core is None else core
        gate = bf([rng.uniform(-4, 4) for _ in range(2048)]) * tokens if gate is None else gate
        weight = struct.pack('<128I', *(rms.word(rng.uniform(-1.5, 1.5)) for _ in range(128))) if weight is None else weight
        produced(self.memory, 0x100000, core)
        produced(self.memory, 0x200000, gate)
        self.memory.add_readonly(0x300000, weight)
        self.memory.allocate_output(0x400000, tokens * m.ROW_BYTES)
        self.job = m.GatedNormJob(91, 0x100000, 0x200000, 0x300000, 0x400000, tokens, heads)
        return m.TypedGatedNormDriver(self.owner, self.memory, self.job)

    def finish(self, driver, hook=None):
        deadline = time.monotonic() + 60
        for i in range(100000):
            self.assertLess(time.monotonic(), deadline, 'bounded software-only gate')
            driver.tick(**({} if hook is None else hook(driver, i)))
            if driver.response is not None:
                return driver.report()
        self.fail('gated norm handshake budget')

    def test_all16_m1_exact_recipe_and_shared_fp32_weights(self):
        d = self.setup_driver(heads=16)
        source = tuple(r.raw() for r in d.sources)
        expected = oracle(*source, 1, 16)
        report = self.finish(d, lambda _, i: dict(memory_ready=i % 3 != 0,
            memory_response_ready=i % 4 != 0, response_ready=i % 5 != 0))
        self.assertIsNone(d.response.status)
        self.assertEqual(d.output.raw(), expected)
        self.assertTrue(d.output.published)
        self.assertEqual(d.response.write_bytes, 4096)
        self.assertEqual(report['counts']['read_bytes'], 512 + 2 * 4096)
        self.assertEqual(report['counts']['write_bytes'], 4096)
        self.assertEqual(report['owner']['scalar_calls'], dict(mul_ieee_rne=769 * 16,
            add=257 * 16, sqrt=16, div=129 * 16, exp_negative=128 * 16))
        self.assertEqual(report['owner']['exp_internal_calls'], dict(mul=9 * 128 * 16, add=8 * 128 * 16))
        self.assertEqual(report['owner']['accepted']['write_acks'], 64)
        self.assertTrue(report['owner']['production_geometry'])
        self.assertEqual(report['owner']['test_only_zero_filled_heads'], 0)
        self.assertEqual(report['owner']['retained_fp32_head_capacity'], 128)
        self.assertEqual(report['owner']['retained_weight_fp32_elements'], 128)
        self.assertFalse(report['owner']['tensor_buffered'])
        self.assertFalse(any(report[k] for k in ('state_committed', 'history_committed', 'generation_advanced')))
        self.assertFalse(report['owner']['native_acceptance'])
        self.assertFalse(report['owner']['rtl_executed'])
        self.assertEqual(source, tuple(r.raw() for r in d.sources))
        self.assertIsNone(self.scalar.client)

    def test_m16_m128_token_head_offsets_with_explicit_reduced_geometry(self):
        for tokens, heads in ((16, 2), (128, 1)):
            with self.subTest(tokens=tokens, active_test_heads=heads):
                # Each token and active head has distinct data at its physical
                # production offset, so replaying token zero cannot pass.
                core, gate = bytearray(tokens * 4096), bytearray(tokens * 4096)
                for token in range(tokens):
                    for head in range(heads):
                        start = token * 4096 + head * 256
                        core[start:start + 256] = bf([((i + token + head * 5) % 29 - 14) / 8 for i in range(128)])
                        gate[start:start + 256] = bf([((i * 3 + token * 7 + head * 11) % 41 - 20) / 8 for i in range(128)])
                d = self.setup_driver(tokens, heads, core=bytes(core), gate=bytes(gate))
                trace = []
                deadline = time.monotonic() + 60
                for _ in range(65536):
                    self.assertLess(time.monotonic(), deadline, 'bounded M128 transport check')
                    event = d.tick()
                    if event['memory_fire']:
                        trace.append(event['memory'])
                    if d.response is not None:
                        break
                else:
                    self.fail('M128 transport handshake budget')
                self.assertEqual(d.output.raw(), oracle(*(r.raw() for r in d.sources), tokens, heads))
                self.assertEqual([q.address for q in trace if q.write],
                                 list(range(self.job.output, self.job.output + tokens * 4096, 64)))
                for base in (self.job.core, self.job.gate):
                    self.assertEqual([q.address for q in trace if base <= q.address < base + tokens * 4096],
                        [base + token * 4096 + head * 256 + beat * 64
                         for token in range(tokens) for head in range(heads) for beat in range(4)])
                self.assertEqual([q.address for q in trace if self.job.weight <= q.address < self.job.weight + 512],
                                 list(range(self.job.weight, self.job.weight + 512, 64)))
                self.assertEqual(len({q.tag for q in trace}), len(trace))
                self.assertEqual(d.response.write_bytes, tokens * 4096)
                report = d.report()
                self.assertEqual(report['counts']['read_bytes'], 512 + tokens * heads * 512)
                self.assertEqual(report['owner']['test_only_zero_filled_heads'], 16 - heads)
                self.assertFalse(report['owner']['production_geometry'])
                self.assertTrue(report['output_published'])

    def test_bf16_norm_original_fp32_weight_and_fp32_silu_boundaries(self):
        d = self.setup_driver()
        core, gate, weight = (r.raw() for r in d.sources)
        expected = oracle_head(core[:256], gate[:256], weight)
        self.assertTrue(any(w & 0xffff for w in struct.unpack('<128I', weight)))
        for variant in (dict(gate_bf16=True), dict(weight_bf16=True),
                        dict(attention_weight=True), dict(normalize_bf16=False)):
            with self.subTest(incorrect_variant=variant):
                self.assertNotEqual(expected, oracle_head(core[:256], gate[:256], weight, **variant))
        self.finish(d)
        self.assertEqual(d.output.raw()[:256], expected)

    def test_final_ack_and_terminal_acceptance_both_required_for_publication(self):
        d = self.setup_driver()
        while d.pending is None or self.owner.request.address != self.job.output + 4096 - 64:
            d.tick()
        for _ in range(3):
            d.tick(memory_response_ready=False)
            self.assertEqual(self.owner.ack_bytes, 4096 - 64)
            self.assertIsNone(d.response)
            self.assertFalse(d.output.published)
        d.tick(response_ready=False)
        held = self.owner.ports()['response']
        self.assertTrue(held.staging_complete)
        self.assertEqual(held.write_bytes, 4096)
        for _ in range(3):
            d.tick(response_ready=False)
            self.assertEqual(self.owner.ports()['response'], held)
            self.assertFalse(d.output.published)
            with self.assertRaises(ValueError):
                self.memory.read64(self.job.output)
        with self.assertRaisesRegex(ValueError, 'held completion'):
            self.owner.reset()
        d.tick()
        self.assertIs(d.response, held)
        self.assertTrue(d.output.published)

    def test_abort_reset_drain_inflight_reads_and_writes_without_publication(self):
        for reset in (False, True):
            for write in (False, True):
                with self.subTest(reset=reset, write=write):
                    d = self.setup_driver()
                    while d.pending is None or self.owner.request.write != write:
                        d.tick()
                    request = self.owner.request
                    event = d.tick(abort=not reset, reset=reset, memory_response_ready=False)
                    self.assertFalse(event['response_fire'])
                    self.assertEqual(self.owner.state, 'drain')
                    self.assertEqual(self.owner.request, request)
                    self.assertIs(self.scalar.client, self.owner)
                    for _ in range(3):
                        d.tick(memory_response_ready=False)
                        self.assertIsNone(self.owner.ports()['memory'])
                        self.assertFalse(d.output.published)
                    self.finish(d)
                    self.assertEqual(d.response.status, 'Aborted')
                    self.assertFalse(d.response.staging_complete)
                    self.assertFalse(d.output.published)
                    self.assertIsNone(d.pending)
                    self.assertIsNone(self.memory.pending)
                    self.assertEqual(self.owner.state, 'locked')
                    self.assertIsNone(self.scalar.client)
                    self.owner.reset()
                    self.assertTrue(self.owner.ports()['job_ready'])

    def test_abort_reset_suppress_unaccepted_request_or_held_success(self):
        for reset in (False, True):
            for held in (False, True):
                with self.subTest(reset=reset, held=held):
                    d = self.setup_driver()
                    if held:
                        while self.owner.state != 'finish':
                            d.tick(response_ready=False)
                    event = d.tick(abort=not reset, reset=reset, response_ready=True)
                    self.assertFalse(event['memory_fire'])
                    self.assertFalse(event['response_fire'])
                    self.assertIsNone(d.response)
                    self.assertFalse(d.output.published)
                    self.assertEqual(self.owner.result.status, 'Aborted')
                    self.finish(d)
                    self.assertEqual(d.response.status, 'Aborted')
                    self.assertFalse(d.output.published)

    def test_abort_reset_on_final_ack_never_linearizes_success(self):
        for reset in (False, True):
            for ack_error in (False, True):
                with self.subTest(reset=reset, ack_error=ack_error):
                    d = self.setup_driver()
                    while d.pending is None or self.owner.request.address != self.job.output + 4096 - 64:
                        d.tick()
                    event = d.tick(abort=not reset, reset=reset, ack_error=ack_error, response_ready=True)
                    self.assertTrue(event['memory_response_fire'])
                    self.assertFalse(event['response_fire'])
                    self.assertIsNone(d.response)
                    self.assertFalse(d.output.published)
                    self.assertIsNone(self.memory.pending)
                    self.assertEqual(self.owner.result.status, 'Memory' if ack_error else 'Aborted')
                    self.finish(d)
                    self.assertFalse(d.output.published)
                    self.assertEqual(d.response.write_bytes, 4096 - (64 if ack_error else 0))

    def test_late_numerical_fault_leaves_partial_staging_unpublished(self):
        gate = bytearray(bf([1] * 2048))
        gate[127 * 2:128 * 2] = struct.pack('<H', 0x7fc0)
        d = self.setup_driver(gate=bytes(gate))
        self.finish(d)
        self.assertEqual(d.response.status, 'Numerical')
        self.assertEqual(d.response.write_bytes, 192)
        self.assertEqual(d.output.acknowledged, {0, 64, 128})
        self.assertFalse(d.output.published)
        with self.assertRaises(ValueError):
            self.memory.read64(self.job.output)

    def test_one_head_cache_is_reused_across_heads_and_tokens(self):
        d = self.setup_driver(tokens=2, heads=2)
        head_cache_ids, weight_cache_ids, output_offsets = set(), set(), set()
        for _ in range(1000):
            q = self.owner.ports()['memory']
            if q is not None and q.write:
                local = self.owner.program.gi_frame.f_locals
                head_cache_ids.add(id(local['cache']))
                weight_cache_ids.add(id(local['weights']))
                self.assertEqual(len(local['cache']), 128)
                self.assertEqual(len(local['weights']), 128)
                self.assertLessEqual(len(local['packet']), 32)
                self.assertEqual({key for key, value in local.items() if type(value) is list}, {'cache', 'weights'})
                output_offsets.add(q.address - self.job.output)
                if q.address == self.job.output:
                    for _ in range(3):
                        d.tick(memory_ready=False)
                        self.assertIs(self.owner.ports()['memory'], q)
            d.tick()
            if d.response is not None:
                break
        self.assertIsNotNone(d.response)
        self.assertEqual(len(head_cache_ids), 1)
        self.assertEqual(len(weight_cache_ids), 1)
        self.assertEqual(output_offsets, set(range(0, 2 * 4096, 64)))

    def test_abort_reset_preserve_held_memory_numerical_and_protocol_errors(self):
        for status in ('Memory', 'Numerical', 'Protocol'):
            for reset in (False, True):
                with self.subTest(status=status, reset=reset):
                    changes = dict(core=struct.pack('<2048H', *([0x7f80] * 2048))) if status == 'Numerical' else {}
                    d = self.setup_driver(**changes)
                    if status == 'Protocol':
                        # Owner-level malformed read, with no external write
                        # obligation; the original driver has not issued it.
                        q = self.owner.request
                        self.owner.tick(memory_ready=True)
                        self.owner.tick(memory_response=rms.MemoryResponse(q.tag + 1, bytes(64)))
                    else:
                        while self.owner.state != 'finish':
                            d.tick(read_error=status == 'Memory', response_ready=False)
                    detail = self.owner.numerical_detail
                    self.assertEqual(self.owner.result.status, status)
                    event = d.tick(abort=not reset, reset=reset, response_ready=True)
                    self.assertFalse(event['response_fire'])
                    self.assertEqual(self.owner.result.status, status)
                    self.assertEqual(self.owner.numerical_detail, detail)
                    d.tick()
                    self.assertEqual(d.response.status, status)
                    self.assertFalse(d.output.published)

    def test_accepted_success_is_not_revoked_by_late_abort_or_reset(self):
        for reset in (False, True):
            with self.subTest(reset=reset):
                d = self.setup_driver()
                self.finish(d)
                response, output = d.response, d.output.raw()
                event = self.owner.tick(abort=not reset, reset=reset, response_ready=True)
                self.assertFalse(event['response_fire'])
                self.assertIs(d.response, response)
                self.assertTrue(d.output.published)
                self.assertEqual(d.output.raw(), output)
                self.assertIsNone(d.response.status)
                self.assertEqual(self.memory.read64(self.job.output), output[:64])

    def test_read_partial_write_and_last_ack_faults_never_publish(self):
        for phase in ('weight', 'core', 'gate', 'first_write', 'last_ack'):
            with self.subTest(phase=phase):
                d = self.setup_driver()
                target = {'weight': self.job.weight, 'core': self.job.core, 'gate': self.job.gate,
                          'first_write': self.job.output, 'last_ack': self.job.output + 4096 - 64}[phase]
                def hook(driver, _):
                    q = self.owner.request
                    fail = driver.pending is not None and q.address == target
                    return dict(read_error=fail and not q.write, ack_error=fail and q.write)
                self.finish(d, hook)
                self.assertEqual(d.response.status, 'Memory')
                self.assertFalse(d.output.published)
                self.assertFalse(d.response.staging_complete)
                self.assertIsNone(self.memory.pending)

    def test_driver_malformed_write_ack_drains_without_success_credit(self):
        for field in ('tag', 'nbytes', 'error'):
            for last in (False, True):
                for fault in (None, 'abort', 'reset'):
                    with self.subTest(field=field, last=last, fault=fault):
                        d = self.setup_driver()
                        target = d.job.output + (d.job.write_bytes - 64 if last else 0)
                        for _ in range(512):
                            if d.pending is not None and d.owner.request.address == target:
                                break
                            d.tick()
                        else:
                            self.fail('bounded write-response target')
                        acknowledged = d.output.acknowledged.copy()
                        ack_bytes, ack_count = d.owner.ack_bytes, d.owner.counts['write_acks']
                        wire = dict(ack_tag=d.pending.tag + 1) if field == 'tag' else dict(ack_nbytes=32)
                        if field == 'error':
                            d.pending = replace(d.pending, error=0)
                            wire = dict(ack_error=True)
                        with self.assertRaises(ValueError):
                            d.owner.reset()
                        # A stalled response cannot unlock reset or consume the
                        # physical transaction, including during abort drain.
                        physical = d.memory.pending
                        d.tick(memory_response_ready=False, **({fault: True} if fault else {}))
                        self.assertIs(d.memory.pending, physical)
                        self.assertFalse(d.owner.ports()['job_ready'])
                        with self.assertRaises(ValueError):
                            d.owner.reset()
                        event = d.tick(response_ready=False, **wire)
                        self.assertTrue(event['memory_response_fire'])
                        self.assertIsNone(d.pending)
                        self.assertIsNone(d.pending_request)
                        self.assertIsNone(d.pending_write)
                        self.assertIsNone(d.memory.pending)
                        self.assertEqual(d.owner.result.status, 'Protocol')
                        self.assertEqual(d.owner.ack_bytes, ack_bytes)
                        self.assertEqual(d.owner.counts['write_acks'], ack_count)
                        self.assertEqual(d.output.acknowledged, acknowledged)
                        self.assertIn(target - d.output.base, d.output.written)
                        self.assertNotIn(target - d.output.base, d.output.acknowledged)
                        held = d.owner.result
                        d.tick(response_ready=False)
                        self.assertIs(d.owner.result, held)
                        with self.assertRaises(ValueError):
                            d.owner.reset()
                        d.tick()
                        self.assertIs(d.response, held)
                        self.assertEqual(d.response.status, 'Protocol')
                        self.assertFalse(d.response.staging_complete or d.output.published)
                        self.assertEqual(d.owner.counts['owner_results'], 1)
                        self.assertEqual(d.owner.state, 'locked')
                        with self.assertRaisesRegex(ValueError, 'retired'):
                            d.tick()
                        d.owner.reset()
                        self.assertTrue(d.owner.ports()['job_ready'])

    def test_driver_final_ack_fault_priority_and_preserved_wire_memory_error(self):
        for fault in ('abort', 'reset'):
            for malformed in (False, True):
                with self.subTest(fault=fault, malformed=malformed):
                    d = self.setup_driver()
                    for _ in range(512):
                        if d.pending is not None and d.owner.request.address == d.job.output + d.job.write_bytes - 64:
                            break
                        d.tick()
                    else:
                        self.fail('bounded final ACK target')
                    # An already supplied transport error must not be erased by
                    # default fault-injection arguments.
                    d.pending = replace(d.pending, error=True)
                    event = d.tick(**{fault: True}, **(dict(ack_tag=d.pending.tag + 1) if malformed else {}))
                    self.assertTrue(event['memory_response_fire'])
                    self.assertFalse(event['response_fire'])
                    self.assertIsNone(d.memory.pending)
                    self.assertEqual(d.owner.result.status, 'Protocol' if malformed else 'Memory')
                    self.assertEqual(d.owner.ack_bytes, d.job.write_bytes - 64)
                    d.tick(abort=True, response_ready=False)
                    self.assertEqual(d.owner.result.status, 'Protocol' if malformed else 'Memory')
                    d.tick()
                    self.assertFalse(d.output.published)

    def test_driver_read_faults_retire_through_transport_and_drain(self):
        for defect in ('tag', 'nbytes', 'data', 'error_type', 'memory'):
            for fault in (None, 'abort', 'reset'):
                with self.subTest(defect=defect, fault=fault):
                    d = self.setup_driver()
                    d.tick()
                    self.assertFalse(d.pending_request.write)
                    changes = {'tag': dict(read_tag=d.pending.tag + 1), 'nbytes': dict(read_nbytes=32)}.get(defect, {})
                    if defect in ('data', 'error_type', 'memory'):
                        d.pending = replace(d.pending, **{'data': dict(data=bytes(32)),
                            'error_type': dict(error=0), 'memory': dict(error=True)}[defect])
                    d.tick(memory_response_ready=False, **({fault: True} if fault else {}))
                    with self.assertRaises(ValueError):
                        d.owner.reset()
                    d.tick(response_ready=False, read_error=defect == 'error_type', **changes)
                    self.assertIsNone(d.pending)
                    self.assertIsNone(d.memory.pending)
                    self.assertEqual(d.owner.result.status, 'Memory' if defect == 'memory' else 'Protocol')
                    d.tick()
                    self.assertEqual(d.owner.state, 'locked')
                    self.assertFalse(d.output.published)
                    self.assertEqual(d.owner.ack_bytes, 0)

    def test_driver_never_retires_replaced_physical_write(self):
        for replace_record in (False, True):
            d = self.setup_driver()
            for _ in range(64):
                if d.pending is not None and d.pending_request.write:
                    break
                d.tick()
            else:
                self.fail('bounded first write target')
            original = d.memory.pending
            command = original[0]
            if replace_record:
                d.memory.pending = list(original)
            else:
                original[0] = replace(command, tag=command.tag + 1)
            unrelated = d.memory.pending
            with self.assertRaisesRegex(ValueError, 'physical write identity changed'):
                d.tick(ack_tag=d.pending.tag + 1)
            self.assertIs(d.memory.pending, unrelated)
            self.assertEqual(d.owner.state, 'wait')
            self.assertFalse(d.output.acknowledged)
            original[0] = command
            d.memory.pending = original
            d.tick(ack_error=True)
            d.tick()
            self.assertEqual(d.response.status, 'Memory')
            self.assertFalse(d.output.published)

    def test_protocol_bad_tag_size_packet_and_error_type_retire_obligation(self):
        for defect in ('tag', 'size', 'packet', 'error_type'):
            with self.subTest(defect=defect):
                d = self.setup_driver()
                q = self.owner.request
                self.owner.tick(memory_ready=True)
                response = rms.MemoryResponse(q.tag + (defect == 'tag'), bytes(32 if defect == 'packet' else 64),
                    0 if defect == 'error_type' else False, 32 if defect == 'size' else 64)
                self.owner.tick(memory_response=response)
                self.assertEqual(self.owner.result.status, 'Protocol')
                self.assertIsNone(self.owner.request)
                self.assertIsNone(self.scalar.client)
                self.owner.tick(response_ready=True)
                self.assertEqual(self.owner.state, 'locked')
                self.assertFalse(d.output.published)

    def test_numeric_domains_preserve_source_fault_policy(self):
        for field, raw in (('core', 0x7f80), ('core', 0x7f7f), ('gate', 0x7fc0),
                           ('gate', 0x7f80), ('gate', 0xc2a0), ('gate', 0xc2c8)):
            with self.subTest(field=field, raw=hex(raw)):
                d = self.setup_driver(**{field: struct.pack('<2048H', *([raw] * 2048))})
                self.finish(d)
                self.assertEqual(d.response.status, 'Numerical')
                self.assertFalse(d.output.published)
        for bits in (0x7f800000, 0x7fc00000, 0x7f7fffff):
            with self.subTest(weight=hex(bits)):
                d = self.setup_driver(weight=struct.pack('<128I', *([bits] * 128)))
                self.finish(d)
                self.assertEqual(d.response.status, 'Numerical')
                self.assertFalse(d.output.published)

    def test_gate_positive_saturation_negative_boundary_and_signed_zero(self):
        values = [0x8000, 0, 0x3e80, 0xbe80, 0xc29f, 0x42a0, 0x42c8, 1] * 16
        gate = struct.pack('<128H', *values) + bytes(4096 - 256)
        d = self.setup_driver(gate=gate, core=bf([1] * 2048), weight=struct.pack('<128I', *([rms.word(1)] * 128)))
        expected = oracle(*(r.raw() for r in d.sources), 1, 1)
        self.finish(d)
        self.assertIsNone(d.response.status)
        self.assertEqual(d.output.raw(), expected)
        self.assertEqual(struct.unpack('<H', d.output.raw()[:2])[0], 0x8000)
        self.assertEqual(self.owner.scalar_counts.get('mul', 0), 0)
        # Public legacy Div still rejects inexact underflow. This owner has
        # not widened the shared numeric policy to achieve an apparent pass.
        client = object()
        self.scalar.acquire(client)
        with self.assertRaises(rms.ArithmeticFault):
            self.scalar.op(client, 'div', 0x800000, rms.word(3))
        self.scalar.release(client)

    def test_shared_scalar_exclusion_reuse_prep_subclass_and_stall_stability(self):
        d = self.setup_driver(prep=True)
        another = ConvOwner(self.scalar, channels=32)
        self.assertFalse(another.ports()['job_ready'])
        request = self.owner.ports()['memory']
        for _ in range(3):
            d.tick(memory_ready=False)
            self.assertEqual(self.owner.ports()['memory'], request)
        with self.assertRaises(ValueError):
            self.scalar.op(another, 'exp_negative', 0)
        original = self.scalar
        self.owner.scalar = ConvScalar()
        with self.assertRaisesRegex(ValueError, 'resource replaced'):
            d.tick()
        self.owner.scalar = original
        self.finish(d)
        self.assertTrue(another.ports()['job_ready'])
        self.assertEqual(self.scalar.calls.get('softplus', 0), 0)
        self.memory.allocate_output(0x500000, 4096)
        following = m.TypedGatedNormDriver(self.owner, self.memory, replace(self.job, tag=92, output=0x500000))
        self.finish(following)
        self.assertEqual(d.output.raw(), following.output.raw())
        self.assertIs(following.owner.scalar, original)

    def test_admission_exact_geometry_bounds_and_source_identity(self):
        d = self.setup_driver()
        for changes in (dict(tokens=0), dict(tokens=129), dict(tokens=True), dict(heads=2),
                        dict(tag=True), dict(gate=1), dict(output=self.job.core),
                        dict(weight=self.job.gate), dict(output=(1 << 56) - 64)):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(self.job, **changes).validate(1)
        full = replace(self.job, tokens=128, heads=16)
        full.validate()
        self.assertEqual(full.write_bytes, 128 * 4096)
        with self.assertRaisesRegex(ValueError, 'ConvScalar or PrepScalar'):
            m.GatedNormOwner(rms.SharedScalar())
        identity = m.source_identity()
        self.assertEqual(identity['source_default_max_tokens'], 128)
        self.assertFalse(identity['native_acceptance'])
        self.assertFalse(identity['production_host_command'])
        self.assertFalse(identity['historical_pass_inherited'])

    def test_actual_producer_acks_publication_and_original_fp32_weight_required(self):
        for defect in ('readonly_core', 'readonly_gate', 'unacked_core', 'unwritten_gate',
                       'staging_core', 'mutable_weight', 'bf16_weight', 'short_core', 'short_output'):
            with self.subTest(defect=defect):
                memory = m.TypedMemory()
                for label, base in (('core', 0x100000), ('gate', 0x200000)):
                    raw = bytes(256 if defect == 'short_core' and label == 'core' else 4096)
                    if defect == 'readonly_' + label:
                        memory.add_readonly(base, raw)
                    else:
                        region = produced(memory, base, raw)
                        if defect == 'unacked_' + label:
                            region.acknowledged.clear()
                        if defect == 'unwritten_' + label:
                            region.written.clear()
                        if defect == 'staging_' + label:
                            region.published = False
                if defect == 'mutable_weight':
                    produced(memory, 0x300000, bytes(512))
                else:
                    memory.add_readonly(0x300000, bytes(256 if defect == 'bf16_weight' else 512))
                memory.allocate_output(0x400000, 256 if defect == 'short_output' else 4096)
                owner = m.GatedNormOwner(ConvScalar(), heads=1)
                job = m.GatedNormJob(1, 0x100000, 0x200000, 0x300000, 0x400000, 1, 1)
                with self.assertRaises(ValueError):
                    m.TypedGatedNormDriver(owner, memory, job)
                self.assertTrue(owner.ports()['job_ready'])


if __name__ == '__main__':
    unittest.main()
