"""Bounded synthetic prefix checks, independent rational FP32 comparison.

No official checkpoints, heavyweight payloads, Chisel or RTL are executed.
The memory below is a test bus, not a production tensor namespace. It returns
only mapped physical words and keeps produced data poisoned until write ACK.
"""
from dataclasses import replace
from fractions import Fraction
from functools import lru_cache
import json
from pathlib import Path
import random
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from candidates.qwen2_resident_matrix.ffn_public import prefix_arithmetic as arithmetic
from candidates.qwen2_resident_matrix.ffn_public import prefix_owners as p


@lru_cache(maxsize=16384)
def exact(bits):
    exponent, mantissa = (bits >> 23) & 255, bits & 0x7fffff
    if exponent == 255:
        raise ValueError('independent comparison requires finite operands')
    shift = -149 if exponent == 0 else exponent - 150
    mantissa += 0 if exponent == 0 else 1 << 23
    mantissa = -mantissa if bits >> 31 else mantissa
    return Fraction(mantissa << max(shift, 0), 1 << max(-shift, 0))


def rn(number, negative_zero=False):
    """Integer quotient/remainder RNE of an exact rational into IEEE binary32."""
    sign = 0x80000000 if number < 0 or (not number and negative_zero) else 0
    if not number:
        return sign
    number = abs(number)
    numerator, denominator = number.numerator, number.denominator
    exponent = numerator.bit_length() - denominator.bit_length()
    if number < Fraction(1 << max(exponent, 0), 1 << max(-exponent, 0)):
        exponent -= 1
    shift = 149 if exponent < -126 else 23 - exponent
    numerator <<= max(shift, 0)
    denominator <<= max(-shift, 0)
    quotient, remainder = divmod(numerator, denominator)
    quotient += 2 * remainder > denominator or (2 * remainder == denominator and quotient & 1)
    if exponent < -126:
        return sign | quotient
    if quotient >= 1 << 24:
        quotient >>= 1
        exponent += 1
    if exponent > 127:
        return sign | 0x7f800000
    return sign | ((exponent + 127) << 23) | (quotient & 0x7fffff)


def ref_add(a, b):
    return rn(exact(a) + exact(b), a == b == 0x80000000)


def ref_mul(a, b):
    return rn(exact(a) * exact(b), bool((a ^ b) >> 31))


def ref_div(a, b):
    return rn(exact(a) / exact(b), bool((a ^ b) >> 31))


def ref_sqrt(a):
    number = exact(a)
    lo, hi = 0, 0x7f7fffff
    while lo + 1 < hi:
        middle = (lo + hi) // 2
        if exact(middle) ** 2 <= number:
            lo = middle
        else:
            hi = middle
    boundary = ((exact(lo) + exact(hi)) / 2) ** 2
    return hi if number > boundary or (number == boundary and lo & 1) else lo


def ref_bf(a):
    if a & 0x7f800000 == 0x7f800000:
        return a
    high, low = a >> 16, a & 0xffff
    high += low > 0x8000 or (low == 0x8000 and high & 1)
    return (high << 16) & 0xffffffff


def ref_norm(row, gamma):
    total = 0
    for a in row:
        total = ref_add(total, ref_mul(a, a))
    mean = ref_mul(total, rn(Fraction(1, len(row))))
    epsilon = ref_add(mean, rn(Fraction(1, 1000000)))
    root = ref_sqrt(epsilon)
    scale = ref_div(0x3f800000, root)
    return tuple(ref_bf(ref_mul(ref_mul(a, scale), b)) for a, b in zip(row, gamma))


class Bus:
    """One addressed 64B bus with ACK-only writes and explicit publication."""
    POISON = struct.pack('<I', 0x7fc00001) * 16

    def __init__(self):
        self.words = {}
        self.readable = set()
        self.outputs = {}
        self.acked = set()
        self.pending = None
        self.reads, self.writes, self.trace = [], [], []

    def input(self, base, words):
        assert len(words) % 16 == 0
        for offset in range(0, len(words), 16):
            address = base + offset * 4
            assert address not in self.words
            self.words[address] = struct.pack('<16I', *words[offset:offset + 16])
            self.readable.add(address)

    def output(self, base, extent):
        addresses = set(range(base, base + extent, 64))
        assert not addresses.intersection(self.words)
        self.outputs[base] = addresses
        for address in addresses:
            self.words[address] = self.POISON

    def accept(self, request):
        assert self.pending is None
        assert request.address % 64 == 0
        self.pending = request
        self.trace.append(request)
        if request.write:
            assert request.mask == p.FULL_MASK and len(request.data) == 64
            assert any(request.address in addresses for addresses in self.outputs.values())
            assert request.address not in self.acked
            self.writes.append(request.address)
        else:
            assert request.address in self.readable, 'read before source/producer publication'
            self.reads.append(request.address)

    def response(self):
        q = self.pending
        assert q is not None
        return p.MemoryResponse(q.tag, None if q.write else self.words[q.address])

    def retire(self, response):
        q = self.pending
        if q.write and response.tag == q.tag and not response.error and response.nbytes == 64:
            self.words[q.address] = q.data
            self.acked.add(q.address)
        self.pending = None

    def publish(self, owner, job):
        assert owner.state == 'idle' and owner.status is None
        assert owner.ack_bytes == job.write_bytes
        addresses = self.outputs[job.dst]
        assert addresses <= self.acked
        self.readable.update(addresses)

    def raw(self, base):
        return b''.join(self.words[address] for address in sorted(self.outputs[base]))


class Harness:
    def __init__(self, owner=None, bus=None):
        self.owner = owner or p.PrefixOwner()
        self.bus = bus or Bus()

    def tick(self, *, memory_ready=True, respond=True, response=None, **kwargs):
        old = self.bus.pending
        r = response if response is not None else self.bus.response() if old and respond else None
        edge = self.owner.tick(memory_ready=memory_ready, memory_response=r, **kwargs)
        if edge['memory_fire']:
            self.bus.accept(edge['memory'])
        if edge['memory_response_fire']:
            self.bus.retire(r)
        return edge

    def until(self, predicate, limit=200000, **kwargs):
        for _ in range(limit):
            if predicate():
                return
            self.tick(**kwargs)
        raise AssertionError('prefix handshake budget exceeded')

    def run(self, job, *, publish=True):
        assert self.tick(job=job)['job_fire']
        self.until(lambda: self.owner.ports()['response'] is not None)
        result = self.owner.ports()['response']
        for _ in range(3):
            self.tick()
            assert self.owner.ports()['response'] == result
        assert self.tick(response_ready=True)['response_fire']
        if publish and result.status is None:
            self.bus.publish(self.owner, job)
        return result


def bias_job(*, rows=1, width=256, tag=(7 << 16) | 4):
    return p.Job('Bias', tag, 0x100000, 0x200000, 0x300000,
                 rows, width, width, rows * width * 4)


def bias_harness(job=None):
    j = job or bias_job()
    h = Harness()
    h.bus.input(j.a, [arithmetic.word((i % 19 - 9) / 16) for i in range(j.m * j.n)])
    h.bus.input(j.b, [arithmetic.word((i % 7 - 3) / 32) for i in range(j.n)])
    h.bus.output(j.dst, j.write_bytes)
    return h, j


class ArithmeticTests(unittest.TestCase):
    def test_original_scalar_policy_preserves_underflow_and_inexact_distinction(self):
        service, client = arithmetic.ScalarService(), object()
        self.assertTrue(service.acquire(client))
        legacy = lambda op, a, b=0: service.op(client, op, a, b, policy='legacy_scalar')
        # Original BlockScalarFloatSpec vectors, including official legacy UF.
        for a, b, expected in ((0x83d70000, 0x02200000, 0x80000000),
                               (0x00800000, 0x3f000001, 0x00400000),
                               (0x00810000, 0x34810000, 0x00000002)):
            self.assertEqual(service.op(client, 'mul', a, b), expected)
            with self.assertRaisesRegex(arithmetic.ArithmeticFault, 'underflow'):
                legacy('mul', a, b)
        self.assertEqual(legacy('mul', 0x00800000, 0x3f000000), 0x00400000)
        self.assertEqual(legacy('add', 0x3f800000, 0x33800000), 0x3f800000)
        self.assertEqual(legacy('mul', 0x3f800001, 0x3f800001), 0x3f800002)
        self.assertEqual(legacy('div', 0x00800000, 0x40000000), 0x00400000)
        with self.assertRaisesRegex(arithmetic.ArithmeticFault, 'underflow'):
            legacy('div', 1, 0x40000000)
        for op, a, b in (('mul', 0x7f7fffff, 0x40000000),
                         ('div', 0x3f800000, 0), ('sqrt', 0xbf800000, 0),
                         ('add', 0x7fc00000, 0x3f800000),
                         ('mul', 0x7f800000, 0)):
            with self.assertRaises(arithmetic.ArithmeticFault):
                legacy(op, a, b)
        service.release(client)

    def test_every_primitive_matches_independent_exact_rounding(self):
        service, client = arithmetic.ScalarService(), object()
        self.assertTrue(service.acquire(client))
        randoms = random.Random(218)
        pairs = [(1, 1), (0x80000000, 0x80000000), (0x3f800001, 0x3f7ffffe),
                 (0x00800000, 0x3f000000), (0x3f808000, 0x3f818000)]
        pairs += [(randoms.randrange(0x00800000, 0x7e000000),
                   randoms.randrange(0x00800000, 0x7e000000)) for _ in range(120)]
        for a, b in pairs:
            for operation, reference in [('add', ref_add), ('mul', ref_mul)]:
                self.assertEqual(service.op(client, operation, a, b), reference(a, b))
            if exact(b):
                self.assertEqual(service.op(client, 'div', a, b), ref_div(a, b))
            if exact(a) > 0:
                self.assertEqual(service.op(client, 'sqrt', a), ref_sqrt(a))
            self.assertEqual(service.op(client, 'bf', a), ref_bf(a))
        service.release(client)

    def test_source_identity_and_native_fail_remain_explicit(self):
        identity = arithmetic.source_identity()
        # A source-only successor commit has a new HEAD; the arithmetic source
        # identity must stay exact, including its committed counterpart.
        self.assertRegex(identity['recipe']['git_head'], r'^[0-9a-f]{40}$')
        self.assertEqual(identity['recipe']['committed_cpp_sha256'],
                         'd757e1271210e260ca320cddf4175c306d3cf52835ea45f20ca9dfb56ac34db5')
        self.assertEqual(identity['native_acceptance'], 'UNCHANGED_FAIL_POLICY_PENDING')
        receipt = json.loads((Path(__file__).parent / 'numerical_receipt.json').read_text())
        self.assertEqual(receipt['native_acceptance'], identity['native_acceptance'])
        self.assertFalse(identity['hardware_simulation'])


class PrefixNumericTests(unittest.TestCase):
    def test_kv_copy_checks_entire_tile_before_first_store(self):
        j = p.Job('KvAppend', (7 << 16) | 9, 0x100000, 0x200000, 0x300000,
                  16, 256, 256, 2 * 16 * 256 * 4)
        h = Harness()
        a = [0x3f800000] * 4096
        a[1023] = 0x7fc00000
        h.bus.input(j.a, a)
        h.bus.input(j.b, [0x3f800000] * 4096)
        h.bus.output(j.dst, j.write_bytes)
        result = h.run(j, publish=False)
        self.assertEqual(result.status, 'Numerical')
        self.assertEqual(result.write_bytes, 0)
        self.assertEqual(h.bus.writes, [])
        self.assertEqual(len(h.bus.reads), 1024 // 16)

    def test_rope_keeps_original_vector_underflow_policy(self):
        j = p.Job('Rope', 1 << 16, 0x100000, 0x200000, 0x300000,
                  1, 256, 256, 1024, c=0x200000 + 1024 * 64 * 4)
        h = Harness()
        values = ([0x00800000] * 64 + [0] * 64) * 2
        h.bus.input(j.a, values)
        h.bus.input(j.b, [0x3f000001] * 64)
        h.bus.input(j.c, [0] * 64)
        h.bus.output(j.dst, j.write_bytes)
        self.assertIsNone(h.run(j).status)
        self.assertEqual(h.bus.raw(j.dst), struct.pack('<256I', *(([0x00400000] * 64 + [0] * 64) * 2)))

    def test_norm_scalar_mean_underflow_rejects_before_any_output(self):
        j = p.Job('Norm', 1 << 16, 0x100000, 0x200000, 0x300000,
                  1, 1536, 1536, 6144)
        h = Harness()
        h.bus.input(j.a, [arithmetic.word(2 ** -60)] + [0] * 1535)
        h.bus.input(j.b, [0x3f800000] * 1536)
        h.bus.output(j.dst, j.write_bytes)
        result = h.run(j, publish=False)
        self.assertEqual(result.status, 'Numerical')
        self.assertIn('underflow', h.owner.detail)
        self.assertEqual(h.bus.writes, [])
        self.assertEqual(result.write_bytes, 0)

    def test_norm_m16_exact_fp32_nodes_then_bf16_container(self):
        j = p.Job('Norm', 7 << 16, 0x100000, 0x200000, 0x300000,
                  16, 1536, 1536, 16 * 1536 * 4)
        h = Harness()
        row = tuple(arithmetic.word((i % 37 - 18) / 29) for i in range(j.n))
        gamma = tuple(arithmetic.word(0.9 + (i % 11) / 64) for i in range(j.n))
        expected = ref_norm(row, gamma)
        h.bus.input(j.a, row * j.m)
        h.bus.input(j.b, gamma)
        h.bus.output(j.dst, j.write_bytes)
        result = h.run(j)
        self.assertIsNone(result.status)
        self.assertEqual(h.bus.raw(j.dst), struct.pack('<1536I', *expected) * j.m)
        report = h.owner.report()
        self.assertEqual(report['peak_row_buffer_words'], 1536)
        self.assertEqual(report['accepted']['read_responses'], 16 * 1536 // 8)
        self.assertEqual(report['accepted']['write_acks'] * 64, j.write_bytes)
        self.assertEqual(report['scalar_primitive_calls'],
                         dict(mul=16 * (3 * 1536 + 1), add=16 * (1536 + 1), sqrt=16, div=16, bf=16 * 1536))
        self.assertTrue(all(word & 0xffff == 0 for word in expected))
        self.assertFalse(report['local_array_is_physical_bank_allocation_evidence'])

    def test_bias_then_rope_then_kv_read_actual_acknowledged_ddr(self):
        h, bias = bias_harness(bias_job(rows=16))
        raw_a = b''.join(h.bus.words[a] for a in range(bias.a, bias.a + bias.write_bytes, 64))
        raw_b = b''.join(h.bus.words[a] for a in range(bias.b, bias.b + bias.n * 4, 64))
        a, b = struct.unpack('<4096I', raw_a), struct.unpack('<256I', raw_b)
        expected_bias = tuple(ref_add(x, b[i % 256]) for i, x in enumerate(a))
        self.assertIsNone(h.run(bias).status)
        self.assertEqual(h.bus.raw(bias.dst), struct.pack('<4096I', *expected_bias))
        cosine = tuple(arithmetic.word((i % 13 + 1) / 16) for i in range(16 * 64))
        sine = tuple(arithmetic.word((i % 7 - 3) / 32) for i in range(16 * 64))
        rope = p.Job('Rope', (7 << 16) | 7, bias.dst, 0x400000, 0x500000,
                     16, 256, 256, 16 * 256 * 4, c=0x400000 + 1024 * 64 * 4)
        h.bus.input(rope.b, cosine)
        h.bus.input(rope.c, sine)
        h.bus.output(rope.dst, rope.write_bytes)
        self.assertIsNone(h.run(rope).status)
        expected_rope = list(expected_bias)
        for token in range(16):
            for head in range(2):
                for col in range(64):
                    i, ti = token * 256 + head * 128 + col, token * 64 + col
                    x, y, c, s = expected_bias[i], expected_bias[i + 64], cosine[ti], sine[ti]
                    expected_rope[i] = ref_add(ref_mul(x, c), ref_mul(y, s) ^ 0x80000000)
                    expected_rope[i + 64] = ref_add(ref_mul(x, s), ref_mul(y, c))
        self.assertEqual(h.bus.raw(rope.dst), struct.pack('<4096I', *expected_rope))
        kv = p.Job('KvAppend', (7 << 16) | 9, rope.dst, bias.dst, 0x600000,
                   16, 256, 256, 2 * 16 * 256 * 4)
        h.bus.output(kv.dst, kv.write_bytes)
        self.assertIsNone(h.run(kv).status)
        self.assertEqual(h.bus.raw(kv.dst), h.bus.raw(rope.dst) + h.bus.raw(bias.dst))
        self.assertEqual(h.owner.report()['peak_copy_tile_words'], 1024)
        self.assertEqual(h.owner.report()['scalar_primitive_calls'], {})
        self.assertEqual(h.owner.report()['accepted']['write_acks'] * 64, kv.write_bytes)

    def test_m128_full_width_rope_is_bounded_and_source_trig_capacity_is_explicit(self):
        j = p.Job('Rope', (9 << 16) | 7, 0x100000, 0x300000, 0x400000,
                  128, 1536, 1536, 128 * 1536 * 4, c=0x300000 + 128 * 64 * 4)
        h = Harness(p.PrefixOwner(max_tokens=128))
        values = tuple(arithmetic.word((i % 17 + 1) / 16) for i in range(j.m * j.n))
        h.bus.input(j.a, values)
        h.bus.input(j.b, (0x3f800000,) * (128 * 64))
        h.bus.input(j.c, (0,) * (128 * 64))
        h.bus.output(j.dst, j.write_bytes)
        self.assertIsNone(h.run(j).status)
        self.assertEqual(h.bus.raw(j.dst), struct.pack('<' + str(len(values)) + 'I', *values))
        self.assertEqual(h.owner.report()['peak_row_buffer_words'], 0)


class PrefixProtocolTests(unittest.TestCase):
    def test_reset_on_admission_or_held_terminal_does_not_create_success(self):
        h, j = bias_harness()
        edge = h.tick(job=j, local_reset=True)
        self.assertFalse(edge['job_fire'])
        self.assertIsNone(h.owner.ports()['response'])
        self.assertIsNone(h.owner.ports()['memory'])
        h.tick(reset=True)
        h.tick(job=j)
        h.until(lambda: h.owner.ports()['response'] is not None)
        edge = h.tick(local_reset=True, response_ready=True)
        self.assertFalse(edge['response_fire'])
        self.assertEqual(h.owner.ports()['response'].status, 'Protocol')
        h.tick(response_ready=True)
        self.assertEqual(h.owner.state, 'locked')
        self.assertFalse(h.bus.readable.intersection(h.bus.outputs[j.dst]))

    def test_idle_local_reset_does_not_repeat_last_transaction_result(self):
        h, j = bias_harness()
        self.assertIsNone(h.run(j).status)
        h.tick(local_reset=True)
        self.assertEqual(h.owner.state, 'locked')
        self.assertIsNone(h.owner.ports()['response'])

    def test_short_physical_read_and_write_request_stall(self):
        h, j = bias_harness()
        h.tick(job=j)
        h.until(lambda: h.bus.pending is not None)
        h.tick(response=replace(h.bus.response(), data=bytes(32)))
        self.assertEqual(h.owner.ports()['response'].status, 'Protocol')
        self.assertEqual(h.owner.ack_bytes, 0)
        h, j = bias_harness()
        h.tick(job=j)
        h.until(lambda: h.owner.ports()['memory'] is not None and h.owner.ports()['memory'].write)
        held = h.owner.ports()['memory']
        for _ in range(4):
            h.tick(memory_ready=False)
            self.assertEqual(h.owner.ports()['memory'], held)
            self.assertEqual(h.bus.words[held.address], Bus.POISON)
        h.tick()
        self.assertEqual(h.bus.words[held.address], Bus.POISON)
        h.tick()
        self.assertEqual(h.bus.words[held.address], held.data)

    def test_final_write_error_keeps_partial_acked_output_unpublished(self):
        h, j = bias_harness()
        h.tick(job=j)
        h.until(lambda: h.bus.pending is not None and h.bus.pending.write
                and h.owner.ack_bytes == j.write_bytes - 64)
        self.assertIsNone(h.owner.ports()['response'])
        self.assertEqual(len(h.bus.acked) * 64, j.write_bytes - 64)
        self.assertFalse(h.bus.readable.intersection(h.bus.outputs[j.dst]))
        h.tick(response=replace(h.bus.response(), error=True))
        result = h.owner.ports()['response']
        self.assertEqual(result.status, 'Memory')
        self.assertEqual(result.write_bytes, j.write_bytes - 64)
        h.tick(response_ready=True)
        self.assertEqual(h.owner.state, 'locked')
        self.assertFalse(h.bus.readable.intersection(h.bus.outputs[j.dst]))

    def test_request_and_terminal_stalls_and_ack_fence(self):
        h, j = bias_harness()
        self.assertTrue(h.tick(job=j)['job_fire'])
        held = h.owner.ports()['memory']
        for _ in range(4):
            h.tick(memory_ready=False)
            self.assertEqual(h.owner.ports()['memory'], held)
        h.until(lambda: h.bus.pending is not None and h.bus.pending.write)
        q = h.bus.pending
        before = h.bus.words[q.address]
        for _ in range(4):
            h.tick(respond=False)
            self.assertIsNone(h.owner.ports()['response'])
            self.assertEqual(h.owner.ack_bytes, 0)
            self.assertEqual(h.bus.words[q.address], before)
        h.tick()
        self.assertEqual(h.owner.ack_bytes, 64)
        self.assertEqual(h.bus.words[q.address], q.data)
        self.assertNotIn(q.address, h.bus.readable)
        h.until(lambda: h.owner.ports()['response'] is not None)
        done = h.owner.ports()['response']
        self.assertIsNone(done.status)
        self.assertEqual(done.write_bytes, j.write_bytes)
        for _ in range(4):
            h.tick()
            self.assertEqual(h.owner.ports()['response'], done)
        h.tick(response_ready=True)
        h.bus.publish(h.owner, j)

    def test_read_write_fault_tag_and_length_never_publish(self):
        for write in (False, True):
            for mode in ('error', 'tag', 'length'):
                with self.subTest(write=write, mode=mode):
                    h, j = bias_harness()
                    h.tick(job=j)
                    h.until(lambda: h.bus.pending is not None and h.bus.pending.write == write)
                    original = h.bus.response()
                    bad = replace(original, error=True) if mode == 'error' else replace(original,
                        tag=original.tag + 1) if mode == 'tag' else replace(original, nbytes=32)
                    self.assertTrue(h.tick(response=bad)['memory_response_fire'])
                    done = h.owner.ports()['response']
                    self.assertEqual(done.status, 'Memory' if mode == 'error' else 'Protocol')
                    self.assertEqual(done.write_bytes, 0)
                    self.assertTrue(h.owner.poison)
                    self.assertTrue(all(h.bus.words[a] == Bus.POISON for a in h.bus.outputs[j.dst]))
                    h.tick(response_ready=True)
                    self.assertFalse(h.owner.ports()['job_ready'])
                    self.assertIsNone(h.owner.ports()['memory'])
                    self.assertFalse(h.tick(job=j)['job_fire'])
                    h.tick(reset=True)
                    self.assertTrue(h.owner.ports()['job_ready'])

    def test_local_reset_drains_accepted_transaction_and_counts_successful_ack_only(self):
        for write in (False, True):
            h, j = bias_harness()
            h.tick(job=j)
            h.until(lambda: h.bus.pending is not None and h.bus.pending.write == write)
            q = h.bus.pending
            h.tick(local_reset=True, respond=False)
            self.assertEqual(h.owner.state, 'drain')
            for _ in range(3):
                h.tick(respond=False)
                self.assertIsNone(h.owner.ports()['response'])
                self.assertIsNone(h.owner.ports()['memory'])
            h.tick()
            done = h.owner.ports()['response']
            self.assertEqual(done.status, 'Protocol')
            self.assertEqual(done.write_bytes, 64 if write else 0)
            self.assertNotIn(q.address, h.bus.readable if write else set())
            h.tick(response_ready=True)
            self.assertEqual(h.owner.state, 'locked')

    def test_global_reset_does_not_drop_accepted_write(self):
        h, j = bias_harness()
        h.tick(job=j)
        h.until(lambda: h.bus.pending is not None and h.bus.pending.write)
        q = h.bus.pending
        h.tick(reset=True, respond=False)
        self.assertEqual(h.owner.state, 'drain')
        self.assertIs(h.bus.pending, q)
        h.tick()
        self.assertEqual(h.owner.ports()['response'].status, 'Protocol')
        self.assertEqual(h.owner.ack_bytes, 64)
        h.tick(response_ready=True)
        h.tick(reset=True)
        self.assertTrue(h.owner.ports()['job_ready'])

    def test_shared_service_denies_concurrent_owner_without_replacement(self):
        shared = arithmetic.ScalarService()
        one, two = p.PrefixOwner(shared), p.PrefixOwner(shared)
        j = bias_job()
        self.assertTrue(one.tick(job=j)['job_fire'])
        self.assertIs(shared.client, one)
        self.assertFalse(two.tick(job=j)['job_fire'])
        self.assertIsNone(two.ports()['memory'])
        one.tick(local_reset=True)
        self.assertIsNone(shared.client)
        self.assertTrue(two.tick(job=j)['job_fire'])

    def test_unsupported_shape_flags_c_and_alias_fail_before_memory(self):
        base = bias_job()
        cases = [replace(base, kind='Attention'), replace(base, output_bf16=True),
                 replace(base, k=128), replace(base, m=0), replace(base, write_bytes=64),
                 replace(base, dst=base.a), replace(base, a=base.a + 4),
                 replace(base, kind='Norm'), replace(base, kind='Rope', c=0),
                 replace(base, tag=1 << 32)]
        for job in cases:
            with self.subTest(job=job):
                owner = p.PrefixOwner()
                self.assertTrue(owner.tick(job=job)['job_fire'])
                self.assertIsNotNone(owner.ports()['response'].status)
                self.assertEqual(owner.ports()['response'].write_bytes, 0)
                self.assertIsNone(owner.ports()['memory'])
                self.assertIsNone(owner.scalar.client)

    def test_nonfinite_store_fails_without_write_or_success(self):
        h, j = bias_harness()
        h.bus.words[j.a] = struct.pack('<16I', *([0x7f800000] + [0] * 15))
        result = h.run(j, publish=False)
        self.assertEqual(result.status, 'Numerical')
        self.assertEqual(h.bus.writes, [])
        self.assertEqual(h.owner.state, 'locked')


if __name__ == '__main__':
    unittest.main()
