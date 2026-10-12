"""Small actual-transaction and returned-word tests; no RTL/model download."""
from dataclasses import FrozenInstanceError, replace
import struct
import time
import unittest
from unittest.mock import patch

from heteronpu import qk_norm256_candidate as norm_reference
from heteronpu import rope_bf16_candidate as rope_reference
from ...qwen35_gdn_prefill.rms_owner import ArithmeticFault, RmsOwner
from . import owner as o
from .scalar import NormRopeScalar, RawScalarResult


def pack(words):
    return struct.pack('<' + 'H' * len(words), *words)


def unpack(raw):
    return struct.unpack('<' + 'H' * (len(raw) // 2), raw)


def values(size, salt=0):
    return tuple((0x8000 if i % 3 == 1 else 0) | (0x3E00 + (i * 37 + salt) % 512)
                 for i in range(size))


def opaque(size):
    special = (0x7F80, 0xFF80, 0x7FC1, 0x7F81, 0x0001, 0x8000, 0xFFFF, 0)
    return (special * ((size + 7) // 8))[:size]


class RecordingScalar(NormRopeScalar):
    def __init__(self):
        super().__init__()
        self.trace = []

    def raw_op(self, client, operation, a, b=0):
        result = super().raw_op(client, operation, a, b)
        self.trace.append((operation, a, b, result.bits, result.flags))
        return result


class Transport:
    """Test-only byte transport; no publication or arithmetic reference hook."""
    def __init__(self, owner, job, inputs):
        self.owner, self.job = owner, job
        self.reads = {base + offset: raw[offset:offset + 64]
                      for base, raw in inputs.items() for offset in range(0, len(raw), 64)}
        self.writes, self.requests = {}, []
        self.pending, self.response = None, None
        assert owner.tick(job=job)['job_fire']

    def tick(self, *, memory_ready=True, memory_response_ready=True, response_ready=True,
             mutate=None, **control):
        p = self.owner.ports()
        pending = self.pending if memory_response_ready else None
        if pending is not None and mutate:
            pending = mutate(pending)
        e = self.owner.tick(memory_ready=memory_ready, memory_response=pending,
                            response_ready=response_ready, **control)
        if e['memory_response_fire']:
            self.pending = None
        if e['memory_fire']:
            q = e['memory']
            assert self.pending is None
            assert q.address % 64 == 0 and q.nbytes == 64
            assert q.mask == (o.FULL_MASK if q.write else 0)
            assert q.tag == (self.job.tag << 32) | len(self.requests)
            self.requests.append(q)
            if q.write:
                assert len(q.data) == 64 and q.address not in self.writes
                assert any(base <= q.address < base + size for base, size in self.job.output_spans)
                self.writes[q.address] = q.data
                self.pending = o.MemoryResponse(q.tag)
            else:
                self.pending = o.MemoryResponse(q.tag, self.reads[q.address])
        if e['response_fire']:
            self.response = p['response']
        return e

    def run(self, **kwargs):
        deadline = time.monotonic() + 15
        for _ in range(10000):
            assert time.monotonic() < deadline, 'small owner wall budget'
            self.tick(**kwargs)
            if self.response is not None:
                return self.response
        raise AssertionError('small owner handshake budget')

    def raw(self, base, size):
        return b''.join(self.writes[base + offset] for offset in range(0, size, 64))


def norm_case(role=0, scalar=None, *, tokens=1, observer=None):
    j = o.QkNorm256Job(71, 0x10000, 0x20000, 0x30000, tokens,
                       role=role, gate_output=0x40000 if role == 0 else 0)
    xs = [values(256, 7 * head) for head in range(j.tokens * j.heads)]
    xs[0] = (0, 0x8000) + xs[0][2:]
    weight = tuple(0xBC00 | (i % 128) for i in range(256))
    gates = [opaque(256) for _ in xs]
    raw = b''.join(pack(x) + (pack(g) if role == 0 else b'') for x, g in zip(xs, gates))
    scalar = RecordingScalar() if scalar is None else scalar
    driver = Transport(o.QkNorm256Owner(scalar, observer), j, {j.input: raw, j.weight: pack(weight)})
    return driver, xs, weight, gates


def rope_case(position=0, tokens=1, heads=1, scalar=None, observer=None):
    j = o.PartialRope64Job(72, 0x10000, 0x30000, 0x50000, tokens, heads, position, position + tokens)
    xs = [values(64, 7 * head) + opaque(192) for head in range(tokens * heads)]
    trig = [(0x3F70 + t % 8,) * 32 + (0x3C10 + t % 16,) * 32 for t in range(tokens)]
    raw_trig = pack(opaque(position * 64)) + b''.join(pack(row) for row in trig)
    scalar = RecordingScalar() if scalar is None else scalar
    driver = Transport(o.PartialRope64Owner(scalar, observer), j,
                       {j.input: b''.join(pack(row) for row in xs), j.trig: raw_trig})
    return driver, xs, trig


def norm_expected_requests(trace, x, weights):
    """Map the independently completed reference into the Chisel issue order."""
    expected = []
    append = lambda op, a, b, bits, flags: expected.append((op, a, b, bits, flags))
    for chunk in range(16):
        for lane in range(chunk * 16, (chunk + 1) * 16):
            append('mul', x[lane], x[lane], trace['squares'][lane], trace['square_flags'][lane])
        level = trace['squares'][chunk * 16:(chunk + 1) * 16]
        index = chunk * 15
        while len(level) > 1:
            size = len(level) // 2
            for i in range(size):
                append('add', level[2 * i], level[2 * i + 1], trace['tree'][index + i],
                       trace['tree_flags'][index + i])
            level = trace['tree'][index:index + size]
            index += size
        append('add', trace['running'][chunk - 1] if chunk else 0, trace['partials'][chunk],
               trace['running'][chunk], trace['running_flags'][chunk])
    append('mul', trace['running'][-1], 0x3B800000, trace['mean'], trace['mean_flags'])
    append('add', trace['mean'], o.EPSILON, trace['mean_eps'], trace['mean_eps_flags'])
    r, flags, normalized = trace['rsqrt_values'], trace['rsqrt_flags'], trace['rsqrt_norm']
    coefficient = o.RSQRT_COEFFICIENTS[trace['rsqrt_index']]
    nodes = (('mul', coefficient >> 32, normalized), ('add', r[0], coefficient & 0xFFFFFFFF),
             ('mul', r[1], r[1]), ('mul', normalized, r[2]), ('mul', 0x3F000000, r[3]),
             ('add', 0x3FC00000, r[4] ^ 0x80000000), ('mul', r[1], r[5]),
             ('mul', r[6], trace['rsqrt_scale']))
    for node, bits, flag in zip(nodes, r, flags):
        append(*node, bits, flag)
    for i in range(256):
        append('add', 0x3F800000, weights[i], trace['gamma'][i], trace['gamma_flags'][i])
        append('mul', x[i], trace['inverse'], trace['scaled'][i], trace['scaled_flags'][i])
        append('mul', trace['scaled'][i], trace['gamma'][i], trace['output_fp32'][i], trace['output_fp32_flags'][i])
    return expected


class OwnerTests(unittest.TestCase):
    def test_norm_actual_requests_bits_flags_gate_and_source_pins(self):
        self.assertFalse(o.source_identity()['rtl_executed'])
        for role in (0, 1):
            d, xs, weight, gates = norm_case(role)
            # The owner must finish while all composite reference helpers are forbidden.
            with (patch.object(norm_reference, 'head_trace', side_effect=AssertionError('oracle execution')),
                  patch.object(norm_reference, 'rsqrt_trace', side_effect=AssertionError('oracle execution')),
                  patch.object(rope_reference, 'pair_trace', side_effect=AssertionError('oracle execution'))):
                while d.response is None:
                    tick = d.owner.ticks
                    d.tick(memory_ready=tick % 3 != 0, memory_response_ready=tick % 4 != 0,
                           response_ready=tick % 5 != 0)
            expected, requests, flags = [], [], 0
            for x in xs:
                xw, ww = tuple(v << 16 for v in x), tuple(v << 16 for v in weight)
                trace = norm_reference.head_trace(xw, ww)
                expected.extend(v >> 16 for v in trace['output_bf16'])
                requests.extend(norm_expected_requests(trace, xw, ww))
                flags |= trace['aggregate_flags']
            self.assertEqual(d.raw(d.job.output, d.job.vector_bytes), pack(expected))
            self.assertEqual(d.owner.scalar.trace, requests)
            self.assertEqual(d.response.exception_flags, flags)
            self.assertEqual(d.response.norm_status, 0)
            self.assertEqual(d.response.last_mean_eps, trace['mean_eps'])
            self.assertEqual(d.response.last_inverse, trace['inverse'])
            self.assertEqual(d.owner.scalar_counts, {'add': d.job.heads * 515, 'mul': d.job.heads * 775})
            self.assertEqual(d.response.write_bytes, d.job.write_bytes)
            self.assertIsNone(d.response.status)
            self.assertIsNone(d.owner.scalar.client)
            if role == 0:
                self.assertEqual(d.raw(d.job.gate_output, d.job.vector_bytes), pack(sum(gates, ())))

    def test_rope_actual_requests_bits_flags_tail_and_absolute_position(self):
        for position in (0, 128):
            d, xs, trig = rope_case(position, tokens=2, heads=2)
            with patch.object(rope_reference, 'pair_trace', side_effect=AssertionError('oracle execution')):
                d.run()
            expected, requests, flags = [], [], 0
            for head, x in enumerate(xs):
                output = list(x)
                coeff = trig[head // d.job.heads]
                for i in range(32):
                    e, odd, c, s = (v << 16 for v in (x[i], x[i + 32], coeff[i], coeff[i + 32]))
                    trace = dict(zip(rope_reference.COLUMNS, rope_reference.pair_trace(e, odd, c, s)))
                    for name, a, b in (('ec', e, c), ('os', odd, s), ('es', e, s), ('oc', odd, c)):
                        requests.append(('mul', a, b, trace[name + '_fp32'], trace[name + '_flags']))
                    requests.extend((
                        ('add', trace['ec_bf16'], trace['os_bf16'] ^ 0x80000000,
                         trace['even_sum_fp32'], trace['even_sum_flags']),
                        ('add', trace['es_bf16'], trace['oc_bf16'], trace['odd_sum_fp32'], trace['odd_sum_flags'])))
                    output[i], output[i + 32] = trace['even_bf16'] >> 16, trace['odd_bf16'] >> 16
                    flags |= trace['aggregate_flags']
                expected.extend(output)
            self.assertEqual(d.raw(d.job.output, d.job.write_bytes), pack(expected))
            self.assertEqual(d.owner.scalar.trace, requests)
            self.assertEqual(d.response.exception_flags, flags)
            self.assertEqual(d.owner.scalar_counts, {'add': len(xs) * 64, 'mul': len(xs) * 128})
            self.assertIsNone(d.response.status)
            trig_reads = [q.address for q in d.requests if d.job.trig <= q.address < d.job.trig + d.job.trig_bytes]
            self.assertEqual(trig_reads, [d.job.trig + (position + t) * 128 + b * 64 for t in range(2) for b in range(2)])

    def test_norm_nonfinite_priority_over_range_in_later_input_or_weight_beat(self):
        for mutate_weight in (False, True):
            for nonfinite in (False, True):
                d, _, _, _ = norm_case(1)
                # The earlier range fault cannot mask a later nonfinite operand.
                d.reads[d.job.weight] = pack((1,) + (0,) * 31)
                if nonfinite:
                    base = d.job.weight if mutate_weight else d.job.input
                    d.reads[base + 7 * 64] = pack((0x7FC1,) + (0,) * 31)
                result = d.run()
                self.assertEqual(result.status, 'Numerical')
                self.assertEqual(result.norm_status, 2 if nonfinite else 3)
                self.assertEqual(result.exception_flags, 0)
                self.assertEqual(d.writes, {})
                self.assertEqual(d.owner.scalar.calls, {})
                self.assertEqual(len(d.requests), 16)

    def test_norm_boundary_exponents_signed_zero_and_gate_opacity(self):
        d, _, _, _ = norm_case()
        boundary = (0, 0x8000, 95 << 7, 0x8000 | (158 << 7)) * 64
        for head in range(8):
            for beat in range(8):
                d.reads[d.job.input + head * 1024 + beat * 64] = pack(boundary[beat * 32:(beat + 1) * 32])
        self.assertIsNone(d.run().status)
        self.assertEqual(d.raw(d.job.gate_output, d.job.vector_bytes), pack(opaque(256) * 8))

    def test_norm_two_tokens_distinct_gate_rows_and_late_head_failure(self):
        d, xs, weights, _ = norm_case(tokens=2)
        gates = [(row,) + opaque(255) for row in range(16)]
        for row, gate in enumerate(gates):
            for beat in range(8):
                d.reads[d.job.input + row * 1024 + 512 + beat * 64] = pack(gate[beat * 32:(beat + 1) * 32])
        self.assertIsNone(d.run().status)
        expected = []
        for x in xs:
            trace = norm_reference.head_trace(tuple(v << 16 for v in x), tuple(v << 16 for v in weights))
            expected.extend(v >> 16 for v in trace['output_bf16'])
        self.assertEqual(d.raw(d.job.output, d.job.vector_bytes), pack(expected))
        self.assertEqual(d.raw(d.job.gate_output, d.job.vector_bytes), pack(sum(gates, ())))
        d, xs, weights, _ = norm_case(1)
        d.reads[d.job.input + 512] = pack((0x7FC1,) + (0,) * 31)
        result = d.run()
        first = norm_reference.head_trace(tuple(v << 16 for v in xs[0]), tuple(v << 16 for v in weights))
        self.assertEqual((result.status, result.norm_status, result.write_bytes), ('Numerical', 2, 512))
        self.assertEqual(result.exception_flags, first['aggregate_flags'])
        self.assertEqual((result.last_mean_eps, result.last_inverse), (first['mean_eps'], first['inverse']))
        self.assertEqual(d.owner.scalar_counts, {'add': 515, 'mul': 775})

    def test_rope_nonfinite_arithmetic_inputs_and_fatal_conversion_flags(self):
        for source in ('input', 'trig'):
            d, _, _ = rope_case()
            base = getattr(d.job, source)
            d.reads[base] = pack((0x7F80,) + (0,) * 31)
            self.assertEqual(d.run().status, 'Numerical')
            self.assertEqual(d.owner.scalar.calls, {})
            self.assertFalse(d.writes)
        # Finite BF16 operands can produce fatal BF16 underflow after an exact FP32 product.
        d, _, _ = rope_case()
        d.reads[d.job.input] = pack((0x0001,) + (0x3F80,) * 31)
        d.reads[d.job.trig] = pack((0x3F00,) * 32)
        result = d.run()
        self.assertEqual(result.status, 'Numerical')
        self.assertEqual(result.exception_flags, 3)
        self.assertEqual(len(d.owner.scalar.trace), 1)
        self.assertFalse(d.writes)

    def test_scalar_raw_flags_exclusivity_and_existing_rms_service(self):
        s, client = NormRopeScalar(), object()
        self.assertIs(RmsOwner(s).scalar, s)
        self.assertTrue(s.acquire(client))
        self.assertFalse(s.acquire(object()))
        for operation, a, b, bits, flags in (
            ('mul', 0x00800000, 0x3F7FFFFF, 0x00800000, 3),
            ('mul', 0x7F7FFFFF, 0x40000000, 0x7F800000, 5),
            ('mul', 0x7F800000, 0, 0x7FC00000, 16),
            ('mul', 1, 0x3F000000, 0, 3),
            ('add', 0x3F800000, 1, 0x3F800000, 1),
            ('add', 0x80000000, 0x80000000, 0x80000000, 0)):
            result = s.raw_op(client, operation, a, b)
            self.assertEqual((result.bits, result.flags), (bits, flags))
            self.assertEqual(result.error, bool(flags & 0x1E))
        with self.assertRaises(ArithmeticFault):
            s.op(client, 'mul', 1, 0x3F000000)
        self.assertEqual(s.op(client, 'mul_ieee_rne', 1, 0x3F000000), 0)
        self.assertEqual(s.op(client, 'div', 0x40000000, 0x40000000), 0x3F800000)
        self.assertEqual(s.op(client, 'sqrt', 0x40800000), 0x40000000)
        with self.assertRaises(ValueError):
            s.raw_op(object(), 'add', 0, 0)
        s.release(client)
        with self.assertRaises(TypeError):
            o.QkNorm256Owner()

    def test_returned_scalar_words_drive_later_requests(self):
        class ChangedScalar(RecordingScalar):
            def raw_op(self, client, operation, a, b=0):
                result = super().raw_op(client, operation, a, b)
                return replace(result, bits=0x3F800000) if len(self.trace) == 1 else result
        for factory, tree_index in ((lambda s: norm_case(1, s)[0], 16),
                                    (lambda s: rope_case(scalar=s)[0], 4)):
            s = ChangedScalar()
            d = factory(s)
            d.run()
            self.assertEqual(s.trace[tree_index][1], 0x3F800000)
            self.assertIsNone(d.response.status)

    def test_norm_observer_actual_snapshots_and_switch_do_not_change_execution(self):
        baseline, _, _, _ = norm_case(1)
        baseline.run()
        events = []
        def observe(stage, token, head, words):
            events.append((stage, token, head, words))
            return (0,)  # Deliberately wrong replacement; the owner ignores it.
        d, xs, weights, _ = norm_case(1, observer=observe)
        d.run()
        self.assertEqual(d.response, baseline.response)
        self.assertEqual(d.requests, baseline.requests)
        self.assertEqual(d.writes, baseline.writes)
        self.assertEqual(d.owner.scalar.trace, baseline.owner.scalar.trace)
        self.assertEqual(d.owner.counts, baseline.owner.counts)
        self.assertEqual(d.owner.scalar_counts, baseline.owner.scalar_counts)
        expected = []
        for head, x in enumerate(xs):
            trace = norm_reference.head_trace(tuple(v << 16 for v in x), tuple(v << 16 for v in weights))
            stages = (('squares', trace['squares']), ('sum', (trace['running'][-1],)),
                      ('mean', (trace['mean'],)), ('mean_eps', (trace['mean_eps'],)),
                      ('inverse', (trace['inverse'],)), ('gamma', trace['gamma']),
                      ('scaled', trace['scaled']), ('weighted', trace['output_fp32']),
                      ('output', trace['output_bf16']))
            expected.extend((stage, 0, head, words) for stage, words in stages)
        self.assertEqual(events, expected)
        self.assertTrue(all(type(event[3]) is tuple for event in events))
        self.assertFalse(d.owner.report()['observer_buffers_are_hardware_resources'])
        self.assertTrue(d.owner.report()['software_observer_enabled'])
        self.assertFalse(baseline.owner.report()['software_observer_enabled'])
        d.owner.reset()
        self.assertIs(d.owner.observer, observe)

    def test_rope_observer_actual_products_rotated_output_and_switch(self):
        baseline, _, _ = rope_case(position=128, tokens=2, heads=2)
        baseline.run()
        events = []
        d, xs, trig = rope_case(position=128, tokens=2, heads=2,
                               observer=lambda *event: events.append(event))
        d.run()
        self.assertEqual(d.response, baseline.response)
        self.assertEqual(d.requests, baseline.requests)
        self.assertEqual(d.writes, baseline.writes)
        self.assertEqual(d.owner.scalar.trace, baseline.owner.scalar.trace)
        self.assertEqual(d.owner.counts, baseline.owner.counts)
        self.assertEqual(d.owner.scalar_counts, baseline.owner.scalar_counts)
        expected = []
        for row, x in enumerate(xs):
            token, head = divmod(row, d.job.heads)
            cos, sin, rotated = [0] * 64, [0] * 64, [0] * 64
            for pair in range(32):
                args = tuple(v << 16 for v in (x[pair], x[pair + 32], trig[token][pair], trig[token][pair + 32]))
                trace = dict(zip(rope_reference.COLUMNS, rope_reference.pair_trace(*args)))
                cos[pair], cos[pair + 32] = trace['ec_bf16'], trace['oc_bf16']
                sin[pair], sin[pair + 32] = trace['os_bf16'] ^ 0x80000000, trace['es_bf16']
                rotated[pair], rotated[pair + 32] = trace['even_bf16'], trace['odd_bf16']
            output = tuple(rotated) + tuple(v << 16 for v in x[64:])
            for stage, words in (('cos_product', tuple(cos)), ('sin_product', tuple(sin)),
                                 ('rotated', tuple(rotated)), ('output', output)):
                expected.append((stage, token, head, words))
        self.assertEqual(events, expected)
        for stage, token, head, words in events:
            if stage == 'output':
                address = d.job.output + (token * d.job.heads + head) * 512
                self.assertEqual(pack(tuple(v >> 16 for v in words)), d.raw(address, 512))

    def test_observer_exception_fails_closed_after_prior_staging(self):
        def observe(stage, token, head, words):
            if head == 1 and stage == 'output':
                raise RuntimeError('observer failure')
        for factory in (lambda: norm_case(1, observer=observe)[0],
                        lambda: rope_case(heads=2, observer=observe)[0]):
            d = factory()
            result = d.run()
            self.assertEqual(result.status, 'Observer')
            self.assertEqual(result.write_bytes, 512)
            self.assertEqual(len(d.writes), 8)
            self.assertEqual(d.owner.state, 'locked')
            self.assertIsNone(d.owner.scalar.client)
            self.assertIsNone(d.pending)
        with self.assertRaises(ValueError):
            o.QkNorm256Owner(NormRopeScalar(), observer=1)

    def test_missing_or_fatal_raw_flags_reject_without_write(self):
        for valid, flags, expected in ((False, 0, 'Protocol'), (True, 2, 'Numerical')):
            class FaultScalar(RecordingScalar):
                def raw_op(self, client, operation, a, b=0):
                    result = super().raw_op(client, operation, a, b)
                    return replace(result, flags=flags, flags_valid=valid)
            for factory in (lambda: norm_case(1, FaultScalar())[0], lambda: rope_case(scalar=FaultScalar())[0]):
                d = factory()
                self.assertEqual(d.run().status, expected)
                self.assertFalse(d.writes)
                self.assertEqual(d.response.exception_flags, flags if valid else 0)
                self.assertIsNone(d.owner.scalar.client)

    def test_typed_shape_dtype_span_and_alias_preflight(self):
        nj = norm_case(1)[0].job
        rj = rope_case()[0].job
        for j, changes in ((nj, dict(tag=True)), (nj, dict(tokens=0)), (nj, dict(tokens=129)),
                           (nj, dict(role=True)), (nj, dict(role=2)), (nj, dict(policy=0)),
                           (nj, dict(epsilon=0)), (nj, dict(head_dim=64)), (nj, dict(dtype='fp32')),
                           (nj, dict(gate_output=64)), (nj, dict(input=1)), (nj, dict(output=nj.weight)),
                           (nj, dict(output=(1 << 56) - 64)), (rj, dict(heads=9)),
                           (rj, dict(rotary_dim=32)), (rj, dict(policy=0)), (rj, dict(dtype='fp32')),
                           (rj, dict(position_base=1)), (rj, dict(trig_tokens=True)),
                           (rj, dict(output=rj.trig)), (rj, dict(input=-64))):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(j, **changes).validate()
        qj = replace(nj, role=0, gate_output=nj.output)
        with self.assertRaises(ValueError):
            qj.validate()
        with self.assertRaises(FrozenInstanceError):
            nj.tokens = 2

    def test_read_bad_tag_byte_count_and_final_ack_errors(self):
        for factory in (lambda: norm_case()[0], lambda: norm_case(1)[0], lambda: rope_case()[0]):
            for fault in ('read', 'tag', 'bytes', 'final_ack'):
                d = factory()
                while d.response is None:
                    q = d.owner.request
                    final = q is not None and q.write and len(d.writes) * 64 == d.job.write_bytes
                    mutate = None
                    if fault == 'read' and q is not None and not q.write:
                        mutate = lambda r: replace(r, error=True)
                    elif fault == 'tag':
                        mutate = lambda r: replace(r, tag=r.tag + 1)
                    elif fault == 'bytes':
                        mutate = lambda r: replace(r, nbytes=32)
                    elif fault == 'final_ack' and final:
                        mutate = lambda r: replace(r, error=True)
                    d.tick(mutate=mutate)
                self.assertEqual(d.response.status, 'Protocol' if fault in ('tag', 'bytes') else 'Memory')
                self.assertEqual(d.response.write_bytes, d.job.write_bytes - 64 if fault == 'final_ack' else 0)
                self.assertIsNone(d.pending)
                self.assertIsNone(d.owner.scalar.client)
                self.assertEqual(d.owner.state, 'locked')

    def test_malformed_read_response_is_protocol_failure(self):
        for mutation in (lambda r: replace(r, data=bytes(32)),
                         lambda r: replace(r, data=bytearray(64)),
                         lambda r: replace(r, error=0),
                         lambda r: replace(r, tag=True)):
            d = rope_case()[0]
            result = d.run(mutate=mutation)
            self.assertEqual(result.status, 'Protocol')
            self.assertEqual(result.write_bytes, 0)
            self.assertEqual(d.owner.counts['memory_responses'], 1)
            self.assertIsNone(d.owner.scalar.client)
            self.assertIsNone(d.pending)

    def test_final_ack_and_held_completion(self):
        for factory in (lambda: norm_case()[0], lambda: rope_case()[0]):
            d = factory()
            while d.pending is None or not d.owner.request.write or len(d.writes) * 64 != d.job.write_bytes:
                d.tick()
            for _ in range(3):
                d.tick(memory_response_ready=False)
                self.assertIsNone(d.owner.ports()['response'])
                self.assertEqual(d.owner.ack_bytes, d.job.write_bytes - 64)
            d.tick(response_ready=False)
            result = d.owner.ports()['response']
            self.assertEqual(result.write_bytes, d.job.write_bytes)
            for _ in range(3):
                d.tick(response_ready=False)
                self.assertIs(d.owner.ports()['response'], result)
                self.assertFalse(d.owner.ports()['job_ready'])
                self.assertFalse(d.owner.ports()['reset_required'])
            with self.assertRaisesRegex(ValueError, 'held completion'):
                d.owner.tick(reset=True)
            d.tick()
            self.assertEqual(d.owner.counts['owner_results'], 1)
            self.assertEqual(d.owner.state, 'idle')

    def test_abort_cancels_held_success_before_acceptance_only(self):
        for factory in (lambda: norm_case(1)[0], lambda: rope_case()[0]):
            for ready in (False, True):
                d = factory()
                while d.owner.state != 'finish':
                    d.tick(response_ready=False)
                success = d.owner.ports()['response']
                self.assertIsNone(success.status)
                event = d.tick(abort=True, response_ready=ready)
                self.assertFalse(event['response_fire'])
                self.assertIsNone(d.response)
                cancelled = d.owner.ports()['response']
                self.assertEqual(cancelled.status, 'Aborted')
                self.assertEqual(cancelled.write_bytes, success.write_bytes)
                d.tick(abort=True, response_ready=False)
                self.assertIs(d.owner.ports()['response'], cancelled)
                d.tick(response_ready=True)
                self.assertEqual(d.response.status, 'Aborted')
                self.assertEqual(d.owner.counts['owner_results'], 1)
            d = factory()
            success = d.run()
            event = d.owner.tick(abort=True, response_ready=True)
            self.assertFalse(event['response_fire'])
            self.assertIs(d.response, success)
            self.assertIsNone(success.status)
            self.assertIsNone(d.owner.result)
            self.assertEqual(d.owner.counts['owner_results'], 1)

    def test_abort_and_reset_drain_accepted_reads_and_writes(self):
        for factory in (lambda: norm_case(1)[0], lambda: rope_case()[0]):
            for phase in ('read', 'write'):
                for control in ('abort', 'reset'):
                    d = factory()
                    while d.pending is None or d.owner.request.write != (phase == 'write'):
                        d.tick()
                    accepted = d.owner.request
                    d.tick(memory_response_ready=False, **{control: True})
                    self.assertEqual(d.owner.state, 'drain')
                    self.assertIs(d.owner.request, accepted)
                    self.assertIs(d.owner.scalar.client, d.owner)
                    with self.assertRaises(ValueError):
                        d.owner.reset()
                    result = d.run()
                    self.assertEqual(result.status, 'Aborted')
                    self.assertIsNone(d.pending)
                    self.assertEqual(d.owner.counts['owner_results'], 1)
                    d.owner.tick(reset=True)
                    self.assertTrue(d.owner.ports()['job_ready'])

    def test_abort_cancels_unaccepted_request_and_scalar_is_shared(self):
        s = NormRopeScalar()
        q = norm_case(1, s)[0]
        other = o.PartialRope64Owner(s)
        self.assertFalse(other.ports()['job_ready'])
        q.tick(abort=True, response_ready=False)
        self.assertFalse(q.requests)
        self.assertEqual(q.owner.ports()['response'].status, 'Aborted')
        q.tick()
        self.assertTrue(other.ports()['job_ready'])
        r = rope_case(scalar=s)[0]
        self.assertIsNone(r.run().status)
        self.assertIs(r.owner.scalar, q.owner.scalar)


if __name__ == '__main__':
    unittest.main()
