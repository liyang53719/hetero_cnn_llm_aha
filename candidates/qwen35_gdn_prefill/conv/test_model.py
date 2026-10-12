"""Small 32-channel gates: addressed producer bytes, rational oracle, faults.

No model payload, compiler, RTL, Java, or real M128 execution is used. Full
6144-channel/M128 support below is admission only, not a numerical pass.
"""
from collections import Counter
from dataclasses import replace
import math
import random
import struct
import time
import unittest

from . import model as m
from . import scalar as s
from .. import rms_owner as rms
from ...qwen2_resident_matrix.ffn_public.test_prefix_owners import (
    exact, ref_add, ref_mul, ref_div, ref_bf)


def bf(values):
    return struct.pack('<' + 'H' * len(values), *(ref_bf(rms.word(v)) >> 16 for v in values))


def produced(memory, base, raw, tag=2):
    """A tiny addressed test producer, including real data, ACK and terminal."""
    region = memory.allocate_output(base, len(raw))
    for off in range(0, len(raw), 64):
        memory.begin_write(m.WriteCommand(base + off, 1, tag))
        memory.write_data(struct.unpack('<32H', raw[off:off + 64]), True, mask=m.FULL_MASK)
        memory.acknowledge(m.WriteAck(tag, False, 64))
    memory.publish(base, (tag, None, len(raw)))
    return region


def reference_exp(a):
    """Integer rational arithmetic and independent source-Double constants."""
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


def oracle(raw, weights, history, tokens, channels=32):
    x = struct.unpack('<' + 'H' * (tokens * channels), raw)
    w = struct.unpack('<' + 'H' * (channels * 4), weights)
    h0 = struct.unpack('<' + 'H' * (channels * 4), history)
    h = [list(h0[i * 4:i * 4 + 4]) for i in range(channels)]
    output = []
    for token in range(tokens):
        for channel in range(channels):
            sample = x[token * channels + channel]
            total = 0
            for tap, v in enumerate(h[channel][1:] + [sample]):
                total = ref_add(total, ref_mul(v << 16, w[channel * 4 + tap] << 16))
            conv = ref_bf(total)
            probability = reference_exp(conv)
            inverse = ref_div(rms.word(1), ref_add(rms.word(1), probability))
            signed = ref_mul(inverse, probability if conv >> 31 else rms.word(1))
            output.append(ref_bf(ref_mul(signed, conv)) >> 16)
            h[channel] = h[channel][1:] + [sample]
    return (struct.pack('<' + 'H' * len(output), *output),
            struct.pack('<' + 'H' * (channels * 4), *(v for row in h for v in row)))


class ConvTests(unittest.TestCase):
    def test_abort_at_terminal_acceptance_prevents_success_preserves_prior_fault(self):
        for prior_fault in (False,True):
            d=self.setup_driver()
            while d.pending is None or self.owner.request.address != self.job.history_out+192:
                d.tick()
            d.tick(response_ready=False,ack_error=prior_fault)
            self.assertEqual(self.owner.state,'finish')
            self.assertEqual(self.owner.result.status,'Memory' if prior_fault else None)
            d.tick(abort=True,response_ready=True)
            self.assertIsNone(d.response)
            self.assertFalse(d.output.published)
            d.tick()
            self.assertEqual(d.response.status,'Memory' if prior_fault else 'Aborted')
            self.assertFalse(d.output.published)
            self.assertFalse(d.history_out.published)
        d=self.setup_driver()
        self.finish(d)
        published=d.output.raw()
        self.owner.tick(abort=True)
        self.assertTrue(d.output.published)
        self.assertEqual(d.output.raw(),published)
        self.assertEqual(self.owner.state,'locked')

    def test_readonly_node_observer_cannot_inject_computed_value_or_change_schedule(self):
        first=self.setup_driver(tokens=16)
        self.finish(first)
        expected=(first.output.raw(),first.history_out.raw(),first.report()['counts'],self.scalar.calls.copy())
        second=self.setup_driver(tokens=16)
        captured={}
        def observe(tag,token,channel,bits):
            self.assertEqual(tag,second.job.tag)
            self.assertNotIn((token,channel),captured)
            captured[token,channel]=bits
            return 0x7fc0  # Deliberately ignored; never replaces the actual node.
        self.owner.observe=observe
        self.finish(second)
        self.assertEqual(expected,(second.output.raw(),second.history_out.raw(),second.report()['counts'],self.scalar.calls.copy()))
        self.assertEqual(set(captured),{(token,channel) for token in range(16) for channel in range(32)})

    def setup_driver(self, tokens=1, *, cold=True, raw=None, weights=None, history=None, history_published=True):
        self.memory = m.TypedMemory()
        self.scalar = s.ConvScalar()
        self.owner = m.ConvOwner(self.scalar, channels=32)
        rng = random.Random(529 + tokens)
        raw = bf([rng.uniform(-3, 3) for _ in range(tokens * 32)]) if raw is None else raw
        weights = bf([rng.uniform(-0.3, 0.3) for _ in range(128)]) if weights is None else weights
        history = (bytes(256) if cold else bf([rng.uniform(-1, 1) for _ in range(128)])) if history is None else history
        produced(self.memory, 0x10000, raw)
        self.memory.add_readonly(0x20000, weights)
        if cold:
            self.memory.add_readonly(0x30000, history)
        else:
            produced(self.memory, 0x30000, history)
        self.memory.regions[0x30000].published = history_published
        self.memory.allocate_output(0x40000, len(raw))
        self.memory.allocate_output(0x50000, 256)
        self.job = m.ConvJob(71, 0x10000, 0x20000, 0x40000, 0x30000, 0x50000,
                             tokens, cold, 0 if cold else 7, 32)
        return m.TypedConvDriver(self.owner, self.memory, self.job, current_generation=self.job.expected_generation)

    def finish(self, driver, hook=None):
        deadline = time.monotonic() + 15
        for i in range(10000):
            self.assertLess(time.monotonic(), deadline, 'small Conv wall budget')
            driver.tick(**({} if hook is None else hook(driver, i)))
            if driver.response is not None:
                return driver.report()
        self.fail('small Conv handshake budget')

    def test_m1_m16_cold_warm_outputs_and_raw_history_match_rational_oracle(self):
        for tokens in (1, 16):
            for cold in (True, False):
                with self.subTest(tokens=tokens, cold=cold):
                    d = self.setup_driver(tokens, cold=cold)
                    source = tuple(r.raw() for r in (d.input, d.weight, d.history_in))
                    report = self.finish(d, lambda _, i: dict(memory_ready=i % 3 != 0,
                        memory_response_ready=i % 4 != 0, response_ready=i % 5 != 0))
                    expected, history = oracle(*source, tokens)
                    self.assertEqual(d.output.raw(), expected)
                    self.assertEqual(d.history_out.raw(), history)
                    self.assertIsNone(d.response.status)
                    self.assertTrue(d.response.staging_complete)
                    self.assertEqual(d.response.write_bytes, tokens * 64 + 256)
                    self.assertEqual(d.response.generation, self.job.expected_generation)
                    self.assertFalse(d.response.history_committed)
                    self.assertFalse(d.history_out.published)
                    self.assertTrue(d.output.published)
                    self.assertEqual(report['counts']['read_bytes'], tokens * 64 + 256 + (0 if cold else 256))
                    self.assertEqual(report['owner']['scalar_calls'],
                        dict(mul_ieee_rne=tokens * 128, add=tokens * 160,
                             exp_negative=tokens * 32, div=tokens * 32, mul=tokens * 64))
                    self.assertEqual(report['owner']['exp_internal_calls'],
                                     dict(mul=tokens * 32 * 9, add=tokens * 32 * 8))
                    self.assertEqual(report['owner']['accepted']['owner_results'], 1)
                    self.assertIsNone(self.scalar.client)
                    self.assertEqual(source, tuple(r.raw() for r in (d.input, d.weight, d.history_in)))

    def test_final_history_ack_then_held_terminal_guards_both_spans(self):
        d = self.setup_driver()
        while d.pending is None or self.owner.request.address != self.job.history_out + 192:
            d.tick()
        for _ in range(3):
            d.tick(memory_response_ready=False)
            self.assertIsNone(d.response)
            self.assertFalse(d.output.published)
            self.assertFalse(d.history_out.published)
            self.assertEqual(self.owner.history_ack_bytes, 192)
        d.tick(response_ready=False)
        held = self.owner.ports()['response']
        self.assertTrue(held.staging_complete)
        for _ in range(3):
            d.tick(response_ready=False)
            self.assertEqual(self.owner.ports()['response'], held)
            self.assertFalse(d.output.published)
        with self.assertRaisesRegex(ValueError, 'held completion'):
            self.owner.reset()
        d.tick()
        self.assertTrue(d.output.published)
        self.assertFalse(d.history_out.published)
        with self.assertRaises(ValueError):
            self.memory.read64(self.job.history_out)

    def test_warm_cannot_consume_staging_until_caller_fence_selects_root(self):
        d = self.setup_driver()
        self.finish(d)
        produced(self.memory, 0x60000, bf([i / 16 - 1 for i in range(32)]))
        self.memory.allocate_output(0x70000, 64)
        self.memory.allocate_output(0x80000, 256)
        next_job = replace(self.job, tag=72, input=0x60000, output=0x70000,
                           history_in=0x50000, history_out=0x80000, cold=False, expected_generation=1)
        with self.assertRaises(ValueError):
            m.TypedConvDriver(self.owner, self.memory, next_job, current_generation=1)
        # This explicit test-caller publication represents an external fence;
        # Conv supplies no global-generation mutator or implicit commit.
        self.memory.publish(0x50000, (71, None, 256))
        following = m.TypedConvDriver(self.owner, self.memory, next_job, current_generation=1)
        self.finish(following)
        expected, history = oracle(following.input.raw(), following.weight.raw(), d.history_out.raw(), 1)
        self.assertEqual(following.output.raw(), expected)
        self.assertEqual(following.history_out.raw(), history)
        self.assertIs(following.owner.scalar, self.scalar)
        self.assertIs(following.memory, d.memory)
        self.assertFalse(following.history_out.published)

    def test_abort_reset_drain_accepted_read_output_and_history(self):
        for phase in ('read', 'output', 'history'):
            for reset in (False, True):
                with self.subTest(phase=phase, reset=reset):
                    d = self.setup_driver()
                    while (d.pending is None or
                           (phase == 'read' and self.owner.request.write) or
                           (phase == 'output' and self.owner.request.address != self.job.output) or
                           (phase == 'history' and self.owner.request.address != self.job.history_out)):
                        d.tick()
                    accepted = self.owner.request
                    d.tick(abort=not reset, reset=reset, memory_response_ready=False)
                    self.assertEqual(self.owner.state, 'drain')
                    self.assertEqual(self.owner.request, accepted)
                    self.assertIs(self.scalar.client, self.owner)
                    with self.assertRaises(ValueError):
                        self.owner.reset()
                    self.finish(d)
                    self.assertEqual(d.response.status, 'Aborted')
                    self.assertFalse(d.output.published)
                    self.assertFalse(d.history_out.published)
                    self.assertIsNone(self.memory.pending)
                    self.assertEqual(self.owner.state, 'locked')
                    self.owner.reset()
                    self.assertTrue(self.owner.ports()['job_ready'])

    def test_abort_unaccepted_request_and_reset_preserves_held_completion(self):
        d = self.setup_driver()
        d.tick(abort=True, response_ready=False)
        self.assertEqual(d.counts['read_bytes'], 0)
        self.assertIsNone(d.pending)
        with self.assertRaisesRegex(ValueError, 'held completion'):
            self.owner.tick(reset=True)
        self.finish(d)
        self.assertEqual(d.response.status, 'Aborted')

    def test_read_output_and_last_history_faults_never_publish(self):
        for phase in ('read', 'output', 'last_history'):
            with self.subTest(phase=phase):
                d = self.setup_driver()
                def hook(d, _):
                    q = self.owner.request
                    bad_ack = d.pending is not None and q.write and (
                        q.address == self.job.output if phase == 'output' else
                        q.address == self.job.history_out + 192 if phase == 'last_history' else False)
                    return dict(read_error=phase == 'read', ack_error=bad_ack)
                self.finish(d, hook)
                self.assertEqual(d.response.status, 'Memory')
                self.assertFalse(d.output.published)
                self.assertFalse(d.history_out.published)
                self.assertFalse(d.response.staging_complete)
                self.assertIsNone(self.memory.pending)

    def test_bad_tag_size_and_read_packet_retire_one_physical_response(self):
        for defect in ('tag', 'size', 'packet', 'error_type'):
            with self.subTest(defect=defect):
                owner = m.ConvOwner(s.ConvScalar(), channels=32)
                job = m.ConvJob(7, 0x10000, 0x20000, 0x40000, 0x30000, 0x50000, 1, True, 0, 32)
                owner.tick(job=job)
                q = owner.ports()['memory']
                owner.tick(memory_ready=True)
                reply = rms.MemoryResponse(q.tag + (defect == 'tag'),
                    bytes(32 if defect == 'packet' else 64),
                    0 if defect == 'error_type' else False, 32 if defect == 'size' else 64)
                owner.tick(memory_response=reply)
                self.assertEqual(owner.state, 'finish')
                self.assertIsNone(owner.request)
                self.assertEqual(owner.ports()['response'].status, 'Protocol')
                self.assertIsNone(owner.scalar.client)
                owner.tick(response_ready=True)
                self.assertEqual(owner.state, 'locked')

    def test_source_finite_and_negative80_policy_with_discarded_history0(self):
        ones = bf([0, 0, 0, 1] * 32)
        for x in (-80, -81, float('inf'), float('nan')):
            with self.subTest(x=x):
                raw = struct.pack('<32H', *([rms.word(x) >> 16] * 32))
                d = self.setup_driver(raw=raw, weights=ones)
                self.finish(d)
                self.assertEqual(d.response.status, 'Numerical')
                self.assertEqual(d.response.write_bytes, 0)
                self.assertFalse(d.output.published)
        d = self.setup_driver(raw=bf([80] * 32), weights=ones)
        self.finish(d)
        self.assertEqual(d.output.raw(), bf([80] * 32))
        history = struct.pack('<128H', *([0x7fc0, 0, 0, 0] * 32))
        d = self.setup_driver(cold=False, history=history, weights=ones)
        self.finish(d)
        self.assertIsNone(d.response.status)  # source never consumes old history[0]

    def test_admission_alias_domains_and_actual_producer_requirements(self):
        d = self.setup_driver()
        for changes in (dict(tokens=0), dict(tokens=129), dict(channels=64), dict(cold=1),
                        dict(tag=True), dict(input=1), dict(output=self.job.input),
                        dict(history_out=self.job.history_in), dict(expected_generation=1),
                        dict(history_out=(1 << 56) - 64)):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(self.job, **changes).validate(32, 0)
        full = m.ConvJob(1, 0x100000, 0x300000, 0x400000, 0x600000, 0x700000, 128, True, 0)
        full.validate()  # admission only; no full-size allocation/execution
        with self.assertRaisesRegex(ValueError, 'shared ConvScalar'):
            m.ConvOwner(rms.SharedScalar(), channels=32)
        self.assertEqual(self.owner.channels, 32)
        self.assertFalse(m.source_identity()['native_acceptance'])

    def test_cold_history_initializes_zero_without_reading_unused_old_root(self):
        d = self.setup_driver(history=struct.pack('<128H', *([0x7fc0] * 128)), history_published=False)
        self.finish(d)
        expected, history = oracle(d.input.raw(), d.weight.raw(), bytes(256), 1)
        self.assertEqual(d.output.raw(), expected)
        self.assertEqual(d.history_out.raw(), history)
        self.assertEqual(d.report()['cold_history_initialization'], 'internal_bf16_positive_zero')
        self.assertFalse(d.report()['history_input_consumed'])
        self.assertEqual(d.counts['read_bytes'], 320)

    def test_exclusive_single_scalar_and_stable_backpressured_request(self):
        d = self.setup_driver()
        another = m.ConvOwner(self.scalar, channels=32)
        self.assertFalse(another.ports()['job_ready'])
        request = self.owner.ports()['memory']
        for _ in range(3):
            d.tick(memory_ready=False)
            self.assertEqual(self.owner.ports()['memory'], request)
        with self.assertRaises(ValueError):
            self.scalar.op(another, 'mul', rms.word(1), rms.word(1))
        self.finish(d)
        self.assertTrue(another.ports()['job_ready'])

    def test_rejects_readonly_qkv_or_warm_history_and_unacked_producer(self):
        for defect in ('readonly_qkv', 'readonly_history', 'unacked_qkv', 'staging_qkv'):
            with self.subTest(defect=defect):
                memory, owner = m.TypedMemory(), m.ConvOwner(s.ConvScalar(), channels=32)
                if defect == 'readonly_qkv':
                    memory.add_readonly(0x10000, bytes(64))
                else:
                    source = produced(memory, 0x10000, bytes(64))
                    if defect == 'unacked_qkv':
                        source.acknowledged.clear()
                    if defect == 'staging_qkv':
                        source.published = False
                memory.add_readonly(0x20000, bytes(256))
                if defect == 'readonly_history':
                    memory.add_readonly(0x30000, bytes(256))
                else:
                    produced(memory, 0x30000, bytes(256))
                memory.allocate_output(0x40000, 64)
                memory.allocate_output(0x50000, 256)
                job = m.ConvJob(1, 0x10000, 0x20000, 0x40000, 0x30000, 0x50000, 1, False, 7, 32)
                with self.assertRaises(ValueError):
                    m.TypedConvDriver(owner, memory, job, current_generation=7)
                self.assertTrue(owner.ports()['job_ready'])

    def test_mid_invocation_scalar_replacement_is_rejected(self):
        d = self.setup_driver()
        original = self.owner.scalar
        self.owner.scalar = s.ConvScalar()
        with self.assertRaisesRegex(ValueError, 'resource replaced'):
            d.tick()
        self.owner.scalar = original
        self.finish(d)
        self.assertIsNone(d.response.status)


class ScalarTests(unittest.TestCase):
    def test_exp_matches_independent_rational_nodes_and_source_constants(self):
        scalar, client = s.ConvScalar(), object()
        scalar.acquire(client)
        self.assertEqual(s.EXP_COEFFICIENTS, tuple(rms.word(math.pow(-math.log(2), i) / math.factorial(i)) for i in range(8)))
        rng = random.Random(83)
        vectors = [0, 0x80000000, 1, 0x80000001, 0x7fffff, 0x800000,
                   rms.word(-79.5), rms.word(80), 0x7f7fffff]
        vectors += [rms.word(rng.uniform(-80, 80)) for _ in range(40)]
        for a in vectors:
            self.assertEqual(scalar.op(client, 'exp_negative', a), reference_exp(a))
        self.assertEqual(scalar.calls, Counter(exp_negative=len(vectors)))
        scalar.release(client)

    def test_op1_op6_and_exp_internal_flags_have_distinct_policies(self):
        scalar, client = s.ConvScalar(), object()
        scalar.acquire(client)
        with self.assertRaises(rms.ArithmeticFault):
            scalar.op(client, 'mul', 1, s.LOG2_RECIPROCAL)
        self.assertEqual(scalar.op(client, 'mul_ieee_rne', 1, s.LOG2_RECIPROCAL), 1)
        self.assertEqual(scalar.op(client, 'exp_negative', 1), rms.word(1))
        self.assertEqual(scalar.op(client, 'exp_negative', 0x7f7fffff), 0)
        self.assertEqual(scalar.op(client, 'mul', 0x800000, rms.word(.5)), 0x400000)
        for op, a, b in (('mul', 0x7f7fffff, rms.word(2)),
                         ('mul_ieee_rne', 0x7f7fffff, rms.word(2)),
                         ('div', 0x800000, rms.word(3)),
                         ('exp_negative', 0x7f800000, 0),
                         ('exp_negative', 0, 0x7fc00000)):
            with self.subTest(op=op, a=a, b=b), self.assertRaises(rms.ArithmeticFault):
                scalar.op(client, op, a, b)
        with self.assertRaises(ValueError):
            scalar.op(client, 'opcode5', 0)
        scalar.release(client)


if __name__ == '__main__':
    unittest.main()
