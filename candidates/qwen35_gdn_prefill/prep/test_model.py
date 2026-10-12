"""Small synthetic integer-FP32 oracle and real transport/lifecycle checks.

No Torch, checkpoint, native numerical acceptance, Chisel or RTL execution.
Reduced-head cases keep the complete production strides and explicitly write
zeros for inactive heads; a separate default 16-head case computes all heads.
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
from ..conv.model import ConvOwner
from ...qwen2_resident_matrix.ffn_public.test_prefix_owners import (
    exact, ref_add, ref_mul, ref_div, ref_sqrt, ref_bf)


def bf(values):
    return struct.pack('<' + 'H' * len(values), *(ref_bf(rms.word(v)) >> 16 for v in values))


def produced(memory, base, raw, tag=2):
    """An addressed producer writes every actual packet and accepts its ACK."""
    region = memory.allocate_output(base, len(raw))
    for offset in range(0, len(raw), 64):
        memory.begin_write(m.WriteCommand(base + offset, 1, tag))
        memory.write_data(struct.unpack('<32H', raw[offset:offset + 64]), True, mask=m.FULL_MASK)
        memory.acknowledge(m.WriteAck(tag, False, 64))
    memory.publish(base, (tag, None, len(raw)))
    return region


def reference_exp(a):
    """Integer rational operations; constants independently from Scala math."""
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


def reference_softplus(a):
    if exact(a) <= -80:
        raise ValueError('source Softplus domain')
    if exact(a) > 20:
        return a
    e = reference_exp(a)
    y = ref_div(e, ref_add(rms.word(2), e))
    z = ref_mul(y, y)
    coefficients = [rms.word(1 / (2 * i + 1)) for i in range(8)]
    accumulator = coefficients[-1]
    for coefficient in reversed(coefficients[:-1]):
        accumulator = ref_add(ref_mul(accumulator, z), coefficient)
    logarithm = ref_mul(ref_mul(rms.word(2), y), accumulator)
    return ref_add(0 if a >> 31 else a, logarithm)


def oracle_row(conv, ab, a_log, dt_bias, heads):
    """Independent full core6400 byte image; never fed into the real owner."""
    inputs, ab = struct.unpack('<6144H', conv), struct.unpack('<32H', ab)
    a_log, bias = struct.unpack('<16I', a_log), struct.unpack('<32H', dt_bias)
    output = [0] * 6400
    for head in range(heads):
        for role in range(3):
            start = role * 2048 + head * 128
            row = [x << 16 for x in inputs[start:start + 128]]
            if role != 2:
                total = 0
                for x in row:
                    total = ref_add(total, ref_mul(x, x))
                inverse = ref_div(rms.word(1), ref_sqrt(ref_add(total, rms.word(1e-6))))
                row = [ref_mul(x, inverse) for x in row]
                if role == 0:
                    row = [ref_mul(x, rms.word(1 / math.sqrt(128))) for x in row]
            output[start:start + 128] = row
        log = a_log[head]
        positive = reference_softplus(ref_add(ab[head] << 16, bias[head] << 16))
        e = reference_exp(log)
        if not log >> 31:
            e = ref_div(rms.word(1), e)
        g = ref_mul(e ^ 0x80000000, positive)
        b = ab[16 + head] << 16
        e = reference_exp(b)
        inverse = ref_div(rms.word(1), ref_add(rms.word(1), e))
        beta = ref_bf(ref_mul(inverse, e if b >> 31 else rms.word(1)))
        output[6144 + head * 16:6144 + head * 16 + 2] = g, beta
    return struct.pack('<6400I', *output)


class InputPrepTests(unittest.TestCase):
    def setup_driver(self, tokens=1, heads=2, *, conv=None, ab=None, a_log=None,
                     dt_bias=None, enabled=True):
        self.memory = m.TypedMemory()
        self.scalar = s.PrepScalar(enable_softplus=enabled)
        self.owner = m.InputPrepOwner(self.scalar, heads=heads)
        rng = random.Random(617)
        row = bf([rng.uniform(-2, 2) for _ in range(6144)])
        conv = row * tokens if conv is None else conv
        ab = bf([i / 16 - .5 for i in range(16)] + [i / 8 - 1 for i in range(16)]) * tokens if ab is None else ab
        a_log = struct.pack('<16I', *(rms.word((i - 7) / 16) for i in range(16))) if a_log is None else a_log
        dt_bias = bf([i / 64 - .2 for i in range(16)]) + bytes(32) if dt_bias is None else dt_bias
        produced(self.memory, 0x100000, conv)
        produced(self.memory, 0x300000, ab)
        self.memory.add_readonly(0x310000, a_log)
        self.memory.add_readonly(0x320000, dt_bias)
        self.memory.allocate_output(0x400000, tokens * m.CORE_ROW_BYTES)
        self.job = m.InputPrepJob(81, 0x100000, 0x300000, 0x310000, 0x320000, 0x400000, tokens, heads)
        return m.TypedInputPrepDriver(self.owner, self.memory, self.job)

    def finish(self, driver, hook=None):
        deadline = time.monotonic() + 45
        for i in range(200000):
            self.assertLess(time.monotonic(), deadline, 'bounded small software check')
            driver.tick(**({} if hook is None else hook(driver, i)))
            if driver.response is not None:
                return driver.report()
        self.fail('small InputPrep handshake budget')

    def test_m1_m4_exact_source_recipe_all_fields_and_offsets(self):
        for tokens, heads in ((1, 1), (4, 2)):
            with self.subTest(tokens=tokens, heads=heads):
                d = self.setup_driver(tokens, heads)
                source = tuple(r.raw() for r in d.sources)
                expected = oracle_row(source[0][:12288], source[1][:64], source[2], source[3], heads)
                report = self.finish(d, lambda _, i: dict(memory_ready=i % 3 != 0,
                    memory_response_ready=i % 4 != 0, response_ready=i % 5 != 0))
                self.assertEqual(d.output.raw(), expected * tokens)
                self.assertIsNone(d.response.status)
                self.assertEqual(d.response.write_bytes, tokens * 25600)
                self.assertTrue(d.output.published)
                self.assertEqual(report['counts']['read_bytes'], 128 + tokens * (64 + heads * 768))
                self.assertEqual(report['counts']['write_bytes'], tokens * 25600)
                self.assertEqual(report['owner']['scalar_calls'], dict(mul_ieee_rne=642 * heads * tokens,
                    add=260 * heads * tokens, sqrt=2 * heads * tokens, div=3 * heads * tokens,
                    exp_negative=2 * heads * tokens, softplus=heads * tokens))
                self.assertEqual(report['owner']['softplus_internal_calls'],
                    dict(mul=19 * heads * tokens, add=17 * heads * tokens, div=heads * tokens))
                self.assertEqual(report['owner']['test_only_zero_filled_heads'], 16 - heads)
                self.assertFalse(report['owner']['production_geometry'])
                self.assertEqual(report['owner']['retained_fp32_head_capacity'], 128)
                self.assertEqual(source, tuple(r.raw() for r in d.sources))
                self.assertFalse(any(report[k] for k in ('history_committed', 'state_committed', 'generation_advanced')))
                self.assertIsNone(self.scalar.client)

    def test_default_full16_has_no_inactive_fill_and_matches_integer_reference(self):
        d = self.setup_driver(heads=16)
        expected = oracle_row(*(r.raw() for r in d.sources), 16)
        report = self.finish(d)
        self.assertEqual(d.output.raw(), expected)
        self.assertTrue(report['owner']['production_geometry'])
        self.assertEqual(report['owner']['test_only_zero_filled_heads'], 0)
        self.assertEqual(report['owner']['scalar_calls']['softplus'], 16)
        self.assertEqual(report['owner']['scalar_calls']['div'], 16 * 3 + 9)
        self.assertEqual(report['counts']['read_bytes'], 12288 + 192)
        self.assertEqual(report['owner']['accepted']['write_acks'], 400)

    def test_m128_reads_each_token_and_publishes_entire_single_core_span(self):
        row = bf([((i % 29) - 14) / 8 for i in range(6144)])
        changed = bytearray(row)
        changed[:2] = bf([3.25])
        conv = row * 63 + bytes(changed) + row * 64
        ab_row = bf([-.5] * 16 + [.25] * 16)
        ab_changed = bf([.5] * 16 + [-.75] * 16)
        ab = ab_row * 64 + ab_changed + ab_row * 63
        d = self.setup_driver(128, 1, conv=conv, ab=ab)
        ordinary = oracle_row(row, ab_row, d.a_log.raw(), d.dt_bias.raw(), 1)
        expected = (ordinary * 63 + oracle_row(bytes(changed), ab_row, d.a_log.raw(), d.dt_bias.raw(), 1)
                    + oracle_row(row, ab_changed, d.a_log.raw(), d.dt_bias.raw(), 1) + ordinary * 63)
        report = self.finish(d)
        self.assertEqual(d.output.raw(), expected)
        self.assertTrue(d.output.published)
        self.assertEqual(d.response.write_bytes, 128 * 25600)
        self.assertEqual(d.output.written, set(range(0, 128 * 25600, 64)))
        self.assertEqual(d.output.acknowledged, d.output.written)
        self.assertEqual(report['counts']['read_bytes'], 128 + 128 * (64 + 768))
        self.assertEqual(report['owner']['scalar_calls']['softplus'], 128)
        self.assertFalse(report['owner']['native_acceptance'])
        self.assertFalse(report['owner']['identity']['recurrence_implemented'])

    def test_final_ack_and_held_terminal_both_required_for_publication(self):
        d = self.setup_driver()
        final_address = self.job.output + self.job.write_bytes - 64
        while d.pending is None or self.owner.request.address != final_address:
            d.tick()
        for _ in range(3):
            d.tick(memory_response_ready=False)
            self.assertIsNone(d.response)
            self.assertFalse(d.output.published)
            self.assertEqual(self.owner.ack_bytes, self.job.write_bytes - 64)
        d.tick(response_ready=False)
        held = self.owner.ports()['response']
        self.assertTrue(held.staging_complete)
        for _ in range(3):
            d.tick(response_ready=False)
            self.assertEqual(self.owner.ports()['response'], held)
            self.assertFalse(d.output.published)
        with self.assertRaisesRegex(ValueError, 'held completion'):
            self.owner.reset()
        with self.assertRaises(ValueError):
            self.memory.read64(self.job.output)
        d.tick()
        self.assertTrue(d.output.published)

    def test_abort_reset_drain_param_vector_and_gate_requests(self):
        for phase in ('parameter', 'vector', 'gate'):
            for reset in (False, True):
                with self.subTest(phase=phase, reset=reset):
                    d = self.setup_driver()
                    address = {'parameter': self.job.a_log, 'vector': self.job.conv,
                               'gate': self.job.output + 6144 * 4}[phase]
                    while d.pending is None or self.owner.request.address != address:
                        d.tick()
                    request = self.owner.request
                    d.tick(abort=not reset, reset=reset, memory_response_ready=False)
                    self.assertEqual(self.owner.state, 'drain')
                    self.assertEqual(self.owner.request, request)
                    self.assertIs(self.scalar.client, self.owner)
                    with self.assertRaises(ValueError):
                        self.owner.reset()
                    self.finish(d)
                    self.assertEqual(d.response.status, 'Aborted')
                    self.assertFalse(d.output.published)
                    self.assertFalse(d.response.staging_complete)
                    self.assertIsNone(self.memory.pending)
                    self.assertEqual(self.owner.state, 'locked')
                    self.owner.reset()
                    self.assertTrue(self.owner.ports()['job_ready'])

    def test_abort_unaccepted_or_held_terminal_never_publishes(self):
        for held in (False, True):
            with self.subTest(held=held):
                d = self.setup_driver()
                if held:
                    while self.owner.state != 'finish':
                        d.tick(response_ready=False)
                d.tick(abort=True, response_ready=False)
                self.assertFalse(d.output.published)
                self.assertIsNone(d.pending)
                with self.assertRaisesRegex(ValueError, 'held completion'):
                    self.owner.tick(reset=True)
                self.finish(d)
                self.assertEqual(d.response.status, 'Aborted')

    def test_abort_preserves_held_memory_and_numerical_failures(self):
        for status in ('Memory', 'Numerical'):
            with self.subTest(status=status):
                changes = (dict(conv=struct.pack('<6144H', *([0x7f80] * 6144)))
                           if status == 'Numerical' else {})
                d = self.setup_driver(**changes)
                while self.owner.state != 'finish':
                    d.tick(read_error=status == 'Memory', response_ready=False)
                held = self.owner.ports()['response']
                detail = self.owner.numerical_detail
                self.assertEqual(held.status, status)
                event = d.tick(abort=True, response_ready=True)
                self.assertFalse(event['response_fire'])
                self.assertEqual(self.owner.ports()['response'].status, status)
                self.assertEqual(self.owner.numerical_detail, detail)
                self.assertFalse(d.output.published)
                d.tick()
                self.assertEqual(d.response.status, status)
                self.assertEqual(self.owner.state, 'locked')

    def test_abort_wins_same_tick_as_acceptance_of_held_success(self):
        d = self.setup_driver()
        while self.owner.state != 'finish':
            d.tick(response_ready=False)
        self.assertIsNone(self.owner.ports()['response'].status)
        event = d.tick(abort=True, response_ready=True)
        self.assertFalse(event['response_fire'])
        self.assertIsNone(d.response)
        self.assertFalse(d.output.published)
        self.assertEqual(self.owner.ports()['response'].status, 'Aborted')
        self.assertFalse(self.owner.ports()['response'].staging_complete)
        d.tick()
        self.assertEqual(d.response.status, 'Aborted')
        self.assertFalse(d.output.published)

    def test_late_abort_or_reset_cannot_revoke_accepted_success(self):
        for reset in (False, True):
            with self.subTest(reset=reset):
                d = self.setup_driver()
                self.finish(d)
                accepted, output = d.response, d.output.raw()
                event = self.owner.tick(abort=not reset, reset=reset, response_ready=True)
                self.assertFalse(event['response_fire'])
                self.assertIsNone(self.owner.ports()['response'])
                self.assertIs(d.response, accepted)
                self.assertIsNone(accepted.status)
                self.assertTrue(accepted.staging_complete)
                self.assertTrue(d.output.published)
                self.assertEqual(d.output.raw(), output)
                self.assertEqual(self.memory.read64(self.job.output), output[:64])

    def test_read_vector_gate_and_final_ack_errors_poison_without_publication(self):
        for phase in ('read', 'vector', 'gate', 'final'):
            with self.subTest(phase=phase):
                d = self.setup_driver()
                address = {'vector': self.job.output, 'gate': self.job.output + 6144 * 4,
                           'final': self.job.output + self.job.write_bytes - 64}.get(phase)
                def hook(driver, _):
                    q = self.owner.request
                    return dict(read_error=phase == 'read',
                                ack_error=driver.pending is not None and q.write and q.address == address)
                self.finish(d, hook)
                self.assertEqual(d.response.status, 'Memory')
                self.assertFalse(d.output.published)
                self.assertFalse(d.response.staging_complete)
                self.assertIsNone(self.memory.pending)

    def test_protocol_bad_tag_length_and_read_packet_retire_single_obligation(self):
        for defect in ('tag', 'size', 'packet', 'error_type'):
            with self.subTest(defect=defect):
                d = self.setup_driver()
                owner = self.owner
                q = owner.ports()['memory']
                owner.tick(memory_ready=True)
                owner.tick(memory_response=rms.MemoryResponse(q.tag + (defect == 'tag'),
                    bytes(32 if defect == 'packet' else 64),
                    0 if defect == 'error_type' else False, 32 if defect == 'size' else 64))
                self.assertEqual(owner.state, 'finish')
                self.assertIsNone(owner.request)
                self.assertEqual(owner.ports()['response'].status, 'Protocol')
                self.assertIsNone(owner.scalar.client)
                owner.tick(response_ready=True)
                self.assertEqual(owner.state, 'locked')
                self.assertFalse(d.output.published)

    def test_source_domains_nonfinite_and_disabled_softplus_fail_closed(self):
        bad_cases = (
            dict(conv=struct.pack('<6144H', *([0x7f80] * 6144))),
            dict(ab=bf([-80] * 16 + [0] * 16), dt_bias=bytes(64)),
            dict(ab=bf([0] * 16 + [-80] * 16)),
            dict(ab=bf([float('nan')] * 16 + [0] * 16)),
            dict(a_log=struct.pack('<16I', *([rms.word(80)] * 16))),
            dict(a_log=struct.pack('<16I', *([rms.word(-80)] * 16))),
            dict(a_log=struct.pack('<16I', *([rms.word(float('nan'))] * 16))),
            dict(a_log=struct.pack('<16I', *([rms.word(6)] * 16))),
            dict(dt_bias=struct.pack('<32H', *([0x7f80] * 32))),
            dict(enabled=False),
        )
        for changes in bad_cases:
            with self.subTest(changes=list(changes)):
                d = self.setup_driver(**changes)
                self.finish(d)
                self.assertEqual(d.response.status, 'Numerical')
                self.assertFalse(d.output.published)
                self.assertIsNone(self.scalar.client)
        # dtBias's second 32 bytes are physical padding, not BF16 parameters.
        d = self.setup_driver(dt_bias=bytes(32) + struct.pack('<16H', *([0x7fc0] * 16)))
        self.finish(d)
        self.assertIsNone(d.response.status)

    def test_beta_really_rounds_to_bf16_and_v_only_widens(self):
        row = bytearray(bf([0] * 6144))
        row[4096 * 2:4096 * 2 + 256] = struct.pack('<128H', *([1, 0x8000, 0x3f81, 0xbf82] * 32))
        d = self.setup_driver(heads=1, conv=bytes(row), ab=bf([0] * 16 + [.25] * 16))
        self.finish(d)
        output = struct.unpack('<6400I', d.output.raw())
        self.assertEqual(output[4096:4224], tuple(x << 16 for x in [1, 0x8000, 0x3f81, 0xbf82] * 32))
        e = reference_exp(rms.word(.25))
        unrounded = ref_div(rms.word(1), ref_add(rms.word(1), e))
        self.assertNotEqual(unrounded & 0xffff, 0)
        self.assertEqual(output[6145], ref_bf(unrounded))
        self.assertEqual(output[6146:6160], (0,) * 14)

    def test_a_log_retains_original_fp32_low_bits(self):
        bits = rms.word(-.371234)
        self.assertNotEqual(bits & 0xffff, 0)
        log = struct.pack('<16I', *([bits] * 16))
        d = self.setup_driver(heads=1, a_log=log)
        expected = oracle_row(*(r.raw() for r in d.sources), 1)
        rounded_log = struct.pack('<16I', *([ref_bf(bits)] * 16))
        quantized = oracle_row(d.conv.raw(), d.ab.raw(), rounded_log, d.dt_bias.raw(), 1)
        self.finish(d)
        self.assertEqual(d.output.raw(), expected)
        self.assertNotEqual(d.output.raw()[6144 * 4:6144 * 4 + 4], quantized[6144 * 4:6144 * 4 + 4])

    def test_admission_rejects_alias_and_wrong_strides_or_domains(self):
        d = self.setup_driver()
        for changes in (dict(tokens=0), dict(tokens=129), dict(tokens=True), dict(heads=16),
                        dict(tag=True), dict(conv=1), dict(output=self.job.conv),
                        dict(a_log=self.job.ab), dict(output=(1 << 56) - 64)):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(self.job, **changes).validate(2)
        full = m.InputPrepJob(1, 0x100000, 0x300000, 0x310000, 0x320000, 0x400000, 128)
        full.validate()
        self.assertEqual(full.write_bytes, 128 * 25600)
        with self.assertRaisesRegex(ValueError, 'PrepScalar'):
            m.InputPrepOwner(rms.SharedScalar())
        self.assertFalse(m.source_identity()['native_acceptance'])
        self.assertEqual(m.source_identity()['source_tokens'], 1)
        self.assertEqual(d.owner.heads, 2)

    def test_actual_producer_and_readonly_parameters_are_mandatory(self):
        for defect in ('readonly_conv', 'readonly_ab', 'unacked_conv', 'staging_ab', 'mutable_alog',
                       'mutable_bias', 'short_conv', 'short_output'):
            with self.subTest(defect=defect):
                memory = m.TypedMemory()
                conv = bytes(12288 if defect != 'short_conv' else 768)
                if defect == 'readonly_conv':
                    memory.add_readonly(0x100000, conv)
                else:
                    region = produced(memory, 0x100000, conv)
                    if defect == 'unacked_conv':
                        region.acknowledged.clear()
                if defect == 'readonly_ab':
                    memory.add_readonly(0x300000, bytes(64))
                else:
                    region = produced(memory, 0x300000, bytes(64))
                    if defect == 'staging_ab':
                        region.published = False
                for base, kind in ((0x310000, 'mutable_alog'), (0x320000, 'mutable_bias')):
                    if defect == kind:
                        produced(memory, base, bytes(64))
                    else:
                        memory.add_readonly(base, bytes(64))
                memory.allocate_output(0x400000, 1600 if defect == 'short_output' else 25600)
                owner = m.InputPrepOwner(s.PrepScalar(enable_softplus=True), heads=1)
                job = m.InputPrepJob(1, 0x100000, 0x300000, 0x310000, 0x320000, 0x400000, 1, 1)
                with self.assertRaises(ValueError):
                    m.TypedInputPrepDriver(owner, memory, job)
                self.assertTrue(owner.ports()['job_ready'])

    def test_stalls_single_shared_scalar_reuse_and_resource_identity(self):
        d = self.setup_driver()
        another = ConvOwner(self.scalar, channels=32)
        self.assertFalse(another.ports()['job_ready'])
        request = self.owner.ports()['memory']
        for _ in range(3):
            d.tick(memory_ready=False)
            self.assertEqual(self.owner.ports()['memory'], request)
        with self.assertRaises(ValueError):
            self.scalar.op(another, 'softplus', 0)
        original = self.owner.scalar
        self.owner.scalar = s.PrepScalar(enable_softplus=True)
        with self.assertRaisesRegex(ValueError, 'resource replaced'):
            d.tick()
        self.owner.scalar = original
        self.finish(d)
        self.assertTrue(another.ports()['job_ready'])
        self.memory.allocate_output(0x500000, 25600)
        following = m.TypedInputPrepDriver(self.owner, self.memory, replace(self.job, tag=82, output=0x500000))
        self.finish(following)
        self.assertEqual(d.output.raw(), following.output.raw())
        self.assertIs(following.owner.scalar, original)


class SoftplusTests(unittest.TestCase):
    def test_every_fp32_node_matches_independent_integer_reference(self):
        scalar, client = s.PrepScalar(enable_softplus=True), object()
        scalar.acquire(client)
        self.assertEqual(s.SOFT_COEFFICIENTS, tuple(rms.word(1 / (2 * i + 1)) for i in range(8)))
        rng = random.Random(59)
        vectors = [0, 0x80000000, 1, 0x80000001, 0x7fffff, 0x800000,
                   rms.word(-79.5), rms.word(-20), rms.word(20), rms.word(20) + 1, 0x7f7fffff]
        vectors += [rms.word(rng.uniform(-79.9, 21)) for _ in range(60)]
        for a in vectors:
            with self.subTest(a=hex(a)):
                self.assertEqual(scalar.op(client, 'softplus', a), reference_softplus(a))
        active = sum(not (a >> 31 == 0 and a > rms.word(20)) for a in vectors)
        self.assertEqual(scalar.calls, Counter(softplus=len(vectors)))
        self.assertEqual(scalar.soft_internal_calls, Counter(mul=19 * active, add=17 * active, div=active))
        self.assertFalse(scalar.internal_calls)  # internal exp is not a public op4 request
        scalar.release(client)

    def test_disabled_and_domain_rejection_and_existing_opcode_policy(self):
        scalar, client = s.PrepScalar(), object()
        scalar.acquire(client)
        with self.assertRaises(rms.ArithmeticFault):
            scalar.op(client, 'softplus', 0)
        scalar.release(client)
        scalar = s.PrepScalar(enable_softplus=True)
        scalar.acquire(client)
        for a, b in ((rms.word(-80), 0), (rms.word(-100), 0), (0x7f800000, 0),
                     (0x7fc00000, 0), (0, 0x7fc00000)):
            with self.subTest(a=hex(a), b=hex(b)), self.assertRaises(rms.ArithmeticFault):
                scalar.op(client, 'softplus', a, b)
        self.assertEqual(scalar.op(client, 'softplus', rms.word(80)), rms.word(80))
        self.assertEqual(scalar.op(client, 'softplus', rms.word(-79.5)), reference_softplus(rms.word(-79.5)))
        with self.assertRaises(rms.ArithmeticFault):
            scalar.op(client, 'mul', 1, rms.word(1 / math.log(2)))
        self.assertEqual(scalar.op(client, 'mul_ieee_rne', 1, rms.word(1 / math.log(2))), 1)
        with self.assertRaises(rms.ArithmeticFault):
            scalar.op(client, 'div', 0x800000, rms.word(3))
        with self.assertRaises(ValueError):
            scalar.op(client, 'opcode5', 0)
        scalar.release(client)


if __name__ == '__main__':
    unittest.main()
