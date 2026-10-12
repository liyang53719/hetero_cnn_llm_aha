"""Bounded NumPy-only owner/transport tests with rational integer oracle.

Synthetic inputs are physically written/ACKed/published before consumption.
No checkpoint, actual M128, Dense library, Torch, compiler, Chisel, or RTL run.
"""
from dataclasses import replace
from functools import lru_cache
import math
import random
import struct
import time
import unittest
from unittest.mock import patch

from . import model as m
from .. import rms_owner as rms
from ..conv.scalar import ConvScalar
from ..conv.model import ConvOwner
from ..prep.scalar import PrepScalar
from ...qwen2_resident_matrix.ffn_public.test_prefix_owners import (
    exact, ref_add, ref_mul, ref_div, ref_bf)


def bf(values):
    return struct.pack('<' + 'H' * len(values), *(ref_bf(rms.word(v)) >> 16 for v in values))


def produced(memory, base, raw, tag=2):
    region = memory.allocate_output(base, len(raw))
    for offset in range(0, len(raw), 64):
        memory.begin_write(m.WriteCommand(base + offset, 1, tag))
        memory.write_data(struct.unpack('<32H', raw[offset:offset + 64]), True, mask=m.FULL_MASK)
        memory.acknowledge(m.WriteAck(tag, False, 64))
    memory.publish(base, (tag, None, len(raw)))
    return region


@lru_cache(maxsize=1024)
def reference_exp(a):
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


def oracle(a_raw, b_raw, op, *, round_silu=True):
    a, b = struct.iter_unpack('<H', a_raw), struct.iter_unpack('<H', b_raw)
    output = []
    for (x,), (y,) in zip(a, b):
        x, y = x << 16, y << 16
        if op == m.ElementwiseOp.Add:
            result = ref_add(x, y)
        else:
            exponential = reference_exp(x)
            inverse = ref_div(rms.word(1), ref_add(rms.word(1), exponential))
            sigmoid = ref_mul(inverse, exponential if x >> 31 else rms.word(1))
            silu = ref_mul(sigmoid, x)
            result = ref_mul(ref_bf(silu) if round_silu else silu, y)
        output.append(ref_bf(result) >> 16)
    return struct.pack('<' + 'H' * len(output), *output)


class ElementwiseTests(unittest.TestCase):
    def setup_driver(self, op=m.ElementwiseOp.SiluMul, *, tokens=1, width=32,
                     a=None, b=None, production=False, prep=False, readonly_a=False):
        self.memory = m.TypedMemory()
        self.scalar = PrepScalar(enable_softplus=True) if prep else ConvScalar()
        self.owner = (m.ElementwiseOwner(self.scalar) if production else
                      m.ElementwiseOwner(self.scalar, hidden_width=width, ffn_width=width, test_geometry=True))
        width = (1024 if op == m.ElementwiseOp.Add else 3584) if production else width
        rng = random.Random(972)
        a = bf([rng.uniform(-4, 4) for _ in range(width * tokens)]) if a is None else a
        b = bf([rng.uniform(-2, 2) for _ in range(width * tokens)]) if b is None else b
        if readonly_a:
            self.memory.add_readonly(0x100000, a)
        else:
            produced(self.memory, 0x100000, a)
        produced(self.memory, 0x200000, b)
        self.memory.allocate_output(0x300000, width * tokens * 2)
        self.job = m.ElementwiseJob(93, 0x100000, 0x200000, 0x300000, tokens, op, width)
        return m.TypedElementwiseDriver(self.owner, self.memory, self.job)

    def finish(self, driver, hook=None):
        deadline = time.monotonic() + 30
        for i in range(30000):
            self.assertLess(time.monotonic(), deadline, 'bounded software-only check')
            driver.tick(**({} if hook is None else hook(driver, i)))
            if driver.response is not None:
                return driver.report()
        self.fail('pointwise handshake budget')

    def test_m1_production_widths_match_integer_oracle_and_existing_opcodes(self):
        for op, width in ((m.ElementwiseOp.Add, 1024), (m.ElementwiseOp.SiluMul, 3584)):
            with self.subTest(op=op):
                d = self.setup_driver(op, production=True)
                source = tuple(r.raw() for r in d.sources)
                expected = oracle(*source, op)
                report = self.finish(d, lambda _, i: dict(memory_ready=i % 3 != 0,
                    memory_response_ready=i % 4 != 0, response_ready=i % 5 != 0))
                self.assertEqual(d.output.raw(), expected)
                self.assertTrue(d.output.published)
                self.assertEqual(d.response.write_bytes, width * 2)
                self.assertEqual(report['counts']['read_bytes'], width * 4)
                self.assertEqual(report['counts']['write_bytes'], width * 2)
                counts = dict(add=width) if op == m.ElementwiseOp.Add else dict(
                    add=width, div=width, exp_negative=width, mul_ieee_rne=width * 3)
                self.assertEqual(report['owner']['scalar_calls'], counts)
                self.assertEqual(report['owner']['accepted']['write_acks'], width // 32)
                self.assertTrue(report['owner']['production_geometry'])
                self.assertFalse(report['owner']['arbitrary_tail_supported'])
                self.assertFalse(any(report[k] for k in ('state_committed', 'history_committed', 'generation_advanced')))
                self.assertEqual(source, tuple(r.raw() for r in d.sources))
                self.assertIsNone(self.scalar.client)

    def test_silu_rounds_before_product_and_never_uses_legacy_mul(self):
        d = self.setup_driver(width=64)
        source = tuple(r.raw() for r in d.sources)
        correct = oracle(*source, m.ElementwiseOp.SiluMul)
        self.assertNotEqual(correct, oracle(*source, m.ElementwiseOp.SiluMul, round_silu=False))
        self.finish(d)
        self.assertEqual(d.output.raw(), correct)
        self.assertNotIn('mul', self.owner.scalar_counts)
        self.assertEqual(self.owner.exp_counts, dict(mul=64 * 9, add=64 * 8))

    def test_reduced_multitoken_offsets_full_masks_and_one_beat_buffers(self):
        d = self.setup_driver(tokens=16, width=64)
        source = tuple(r.raw() for r in d.sources)
        trace, buffers = [], [set(), set(), set()]
        for _ in range(1000):
            q = self.owner.ports()['memory']
            if q is not None and q.write:
                locals_ = self.owner.program.gi_frame.f_locals
                self.assertEqual({k for k, v in locals_.items() if type(v) is list},
                                 {'input_a', 'input_b', 'output'})
                for seen, name in zip(buffers, ('input_a', 'input_b', 'output')):
                    self.assertEqual(len(locals_[name]), 32)
                    seen.add(id(locals_[name]))
            event = d.tick()
            if event['memory_fire']:
                trace.append(event['memory'])
            if d.response is not None:
                break
        self.assertIsNotNone(d.response)
        self.assertEqual(d.output.raw(), oracle(*source, m.ElementwiseOp.SiluMul))
        self.assertEqual([len(ids) for ids in buffers], [1, 1, 1])
        for base in (self.job.a, self.job.b, self.job.output):
            self.assertEqual([q.address for q in trace if base <= q.address < base + self.job.write_bytes],
                             list(range(base, base + self.job.write_bytes, 64)))
        self.assertEqual(len({q.tag for q in trace}), len(trace))
        self.assertEqual(d.output.written, set(range(0, self.job.write_bytes, 64)))
        self.assertFalse(d.report()['owner']['production_geometry'])

    def test_held_requests_final_ack_then_held_completion_publish_once(self):
        d = self.setup_driver(width=64)
        q = self.owner.request
        for _ in range(3):
            d.tick(memory_ready=False)
            self.assertIs(self.owner.request, q)
            self.assertEqual(d.output.raw(), m.GUARD * 2)
        while d.pending is None or self.owner.request.address != self.job.output + 64:
            d.tick()
        for _ in range(3):
            d.tick(memory_response_ready=False)
            self.assertEqual(self.owner.ack_bytes, 64)
            self.assertFalse(d.output.published)
        d.tick(response_ready=False)
        held = self.owner.result
        self.assertTrue(held.staging_complete)
        for _ in range(3):
            d.tick(response_ready=False)
            self.assertIs(self.owner.result, held)
            self.assertFalse(d.output.published)
            with self.assertRaises(ValueError):
                self.memory.read64(self.job.output)
        with self.assertRaisesRegex(ValueError, 'held completion'):
            self.owner.reset()
        d.tick()
        self.assertIs(d.response, held)
        self.assertTrue(d.output.published)
        self.assertEqual(self.owner.counts['owner_results'], 1)
        with self.assertRaisesRegex(ValueError, 'retired'):
            d.tick()

    def test_abort_reset_drain_inflight_read_write_and_poison_until_reset(self):
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
                    self.assertIs(self.owner.request, request)
                    self.assertIs(self.scalar.client, self.owner)
                    for _ in range(3):
                        d.tick(memory_response_ready=False)
                        self.assertIsNone(self.owner.ports()['memory'])
                    self.finish(d)
                    self.assertEqual(d.response.status, 'Aborted')
                    self.assertFalse(d.output.published)
                    self.assertIsNone(self.memory.pending)
                    self.assertEqual(self.owner.state, 'locked')
                    self.assertIsNone(self.scalar.client)
                    self.owner.reset()
                    self.assertTrue(self.owner.ports()['job_ready'])

    def test_abort_reset_suppress_unaccepted_request_and_held_success(self):
        for reset in (False, True):
            for held in (False, True):
                with self.subTest(reset=reset, held=held):
                    d = self.setup_driver()
                    if held:
                        while self.owner.state != 'finish':
                            d.tick(response_ready=False)
                    event = d.tick(abort=not reset, reset=reset)
                    self.assertFalse(event['memory_fire'])
                    self.assertFalse(event['response_fire'])
                    self.assertFalse(d.output.published)
                    self.assertEqual(self.owner.result.status, 'Aborted')
                    self.finish(d)
                    self.assertEqual(d.response.status, 'Aborted')

    def test_final_ack_abort_reset_and_transport_error_priority(self):
        for reset in (False, True):
            for error in (False, True):
                with self.subTest(reset=reset, error=error):
                    d = self.setup_driver(width=64)
                    while d.pending is None or self.owner.request.address != self.job.output + 64:
                        d.tick()
                    event = d.tick(abort=not reset, reset=reset, ack_error=error)
                    self.assertTrue(event['memory_response_fire'])
                    self.assertFalse(event['response_fire'])
                    self.assertFalse(d.output.published)
                    self.finish(d)
                    self.assertEqual(d.response.status, 'Memory' if error else 'Aborted')
                    self.assertEqual(d.response.write_bytes, 64 if error else 128)

    def test_prior_errors_survive_abort_reset_before_terminal_accept(self):
        for status in ('Memory', 'Numerical', 'Unsupported', 'Protocol'):
            for reset in (False, True):
                with self.subTest(status=status, reset=reset):
                    raw = 0x7fc0 if status == 'Numerical' else 0xc2a0
                    d = self.setup_driver(a=struct.pack('<32H', *([raw] * 32))
                                          if status in ('Numerical', 'Unsupported') else None)
                    if status == 'Protocol':
                        q = self.owner.request
                        self.owner.tick(memory_ready=True)
                        self.owner.tick(memory_response=m.MemoryResponse(q.tag + 1, bytes(64)))
                    else:
                        while self.owner.state != 'finish':
                            d.tick(read_error=status == 'Memory', response_ready=False)
                    self.assertEqual(self.owner.result.status, status)
                    detail = self.owner.numerical_detail
                    event = d.tick(abort=not reset, reset=reset)
                    self.assertFalse(event['response_fire'])
                    self.assertEqual(self.owner.result.status, status)
                    self.assertEqual(self.owner.numerical_detail, detail)
                    d.tick()
                    self.assertEqual(d.response.status, status)
                    self.assertFalse(d.output.published)

    def test_accepted_completion_not_retracted_by_late_abort_reset(self):
        for reset in (False, True):
            d = self.setup_driver()
            self.finish(d)
            result, raw = d.response, d.output.raw()
            self.owner.tick(abort=not reset, reset=reset, response_ready=True)
            self.assertIs(d.response, result)
            self.assertIsNone(result.status)
            self.assertTrue(d.output.published)
            self.assertEqual(self.memory.read64(self.job.output), raw)

    def test_read_first_write_last_ack_and_late_numeric_fault_leave_unpublished(self):
        for target in ('a', 'b', 'first_write', 'last_ack', 'late_numeric'):
            with self.subTest(target=target):
                raw = bf([1] * 63) + struct.pack('<H', 0x7f80) if target == 'late_numeric' else None
                d = self.setup_driver(width=64, a=raw)
                address = dict(a=self.job.a, b=self.job.b, first_write=self.job.output,
                               last_ack=self.job.output + 64, late_numeric=-1)[target]
                def hook(driver, _):
                    q = self.owner.request
                    fail = driver.pending is not None and q.address == address
                    return dict(read_error=fail and not q.write, ack_error=fail and q.write)
                self.finish(d, hook)
                self.assertEqual(d.response.status, 'Numerical' if target == 'late_numeric' else 'Memory')
                self.assertEqual(d.response.write_bytes, 64 if target in ('late_numeric', 'last_ack') else 0)
                self.assertFalse(d.output.published)
                self.assertFalse(d.response.staging_complete)
                self.assertIsNone(self.memory.pending)

    def test_driver_malformed_write_ack_drains_without_success_credit(self):
        for field in ('tag', 'nbytes', 'error'):
            for last in (False, True):
                for fault in (None, 'abort', 'reset'):
                    with self.subTest(field=field, last=last, fault=fault):
                        d = self.setup_driver(width=64)
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
                    d = self.setup_driver(width=64)
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
                    d = self.setup_driver(width=64)
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
            d = self.setup_driver(width=64)
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

    def test_protocol_wrong_tag_size_payload_error_type(self):
        for defect in ('tag', 'size', 'payload', 'error_type'):
            d = self.setup_driver()
            q = self.owner.request
            self.owner.tick(memory_ready=True)
            response = m.MemoryResponse(q.tag + (defect == 'tag'), bytes(32 if defect == 'payload' else 64),
                                       0 if defect == 'error_type' else False, 32 if defect == 'size' else 64)
            self.owner.tick(memory_response=response)
            self.assertEqual(self.owner.result.status, 'Protocol')
            self.assertIsNone(self.owner.request)
            self.assertIsNone(self.scalar.client)
            self.owner.tick(response_ready=True)
            self.assertEqual(self.owner.state, 'locked')
            self.assertFalse(d.output.published)

    def test_finite_flags_negative80_and_bf16_overflow(self):
        cases = ((m.ElementwiseOp.SiluMul, 0xc2a0, 0x3f80, 'Unsupported'),
                 (m.ElementwiseOp.SiluMul, 0xc2a1, 0x3f80, 'Unsupported'),
                 (m.ElementwiseOp.SiluMul, 0x7fc0, 0x3f80, 'Numerical'),
                 (m.ElementwiseOp.SiluMul, 0x3f80, 0x7f80, 'Numerical'),
                 (m.ElementwiseOp.SiluMul, 0x7f7f, 0x4000, 'Numerical'),
                 (m.ElementwiseOp.Add, 0x7f7f, 0x7f7f, 'Numerical'),
                 (m.ElementwiseOp.Add, 0x7f7f, 0x7b00, 'Numerical'))
        for op, a, b, status in cases:
            with self.subTest(op=op, a=a, b=b):
                d = self.setup_driver(op, a=struct.pack('<32H', *([a] * 32)),
                                      b=struct.pack('<32H', *([b] * 32)))
                self.finish(d)
                self.assertEqual(d.response.status, status)
                self.assertFalse(d.output.published)

    def test_subnormal_gradual_underflow_signed_zero_positive_saturation(self):
        values = [0x8000, 0, 1, 0x8001, 2, 0x8002, 0xc29f, 0x42a0] * 4
        a = struct.pack('<32H', *values)
        d = self.setup_driver(a=a, b=bf([1] * 32))
        self.finish(d)
        self.assertIsNone(d.response.status)
        self.assertEqual(d.output.raw(), oracle(a, bf([1] * 32), m.ElementwiseOp.SiluMul))
        self.assertEqual(struct.unpack('<6H', d.output.raw()[:12]), (0x8000, 0, 0, 0x8000, 1, 0x8001))
        client = object()
        self.assertTrue(self.scalar.acquire(client))
        with self.assertRaises(rms.ArithmeticFault):
            self.scalar.op(client, 'div', 0x800000, rms.word(3))
        self.assertEqual(self.scalar.op(client, 'mul_ieee_rne', 1, rms.word(1.44)), 1)
        with self.assertRaises(rms.ArithmeticFault):
            self.scalar.op(client, 'mul', 1, rms.word(1.44))
        self.scalar.release(client)
        d = self.setup_driver(m.ElementwiseOp.Add, a=struct.pack('<32H', *([0x8000, 0] * 16)),
                              b=struct.pack('<32H', *([0x8000] * 32)))
        self.finish(d)
        self.assertEqual(struct.unpack('<2H', d.output.raw()[:4]), (0x8000, 0))

    def test_shared_scalar_exclusion_prep_reuse_and_resource_substitution(self):
        d = self.setup_driver(prep=True)
        other = ConvOwner(self.scalar, channels=32)
        self.assertFalse(other.ports()['job_ready'])
        with self.assertRaises(ValueError):
            self.scalar.op(other, 'exp_negative', 0)
        original = self.scalar
        self.owner.scalar = ConvScalar()
        with self.assertRaisesRegex(ValueError, 'resource replaced'):
            d.tick()
        self.owner.scalar = original
        self.finish(d)
        self.assertTrue(other.ports()['job_ready'])
        self.assertNotIn('softplus', self.scalar.calls)
        self.memory.allocate_output(0x400000, 64)
        following = m.TypedElementwiseDriver(self.owner, self.memory, replace(self.job, tag=94, output=0x400000))
        self.finish(following)
        self.assertEqual(d.output.raw(), following.output.raw())
        self.assertIs(following.owner.scalar, original)

    def test_admission_geometry_bounds_and_pinned_execution_only_identity(self):
        d = self.setup_driver()
        for changes in (dict(tokens=0), dict(tokens=129), dict(tokens=True), dict(row_width=31),
                        dict(tag=True), dict(a=1), dict(output=self.job.a), dict(b=self.job.a),
                        dict(output=(1 << 56) - 64, tokens=2), dict(op=2), dict(op=True)):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(self.job, **changes).validate(32, 32, True)
        for options in (dict(hidden_width=32), dict(hidden_width=33, test_geometry=True),
                        dict(ffn_width=3616, test_geometry=True)):
            with self.assertRaises(ValueError):
                m.ElementwiseOwner(ConvScalar(), **options)
        with self.assertRaisesRegex(ValueError, 'ConvScalar or PrepScalar'):
            m.ElementwiseOwner(rms.SharedScalar())
        replace(self.job, tokens=128, row_width=3584).validate()
        identity = m.source_identity()
        self.assertEqual(identity['source_sha256']['HEAD:' + m.OWNER_SOURCE], m.OWNER_SHA)
        self.assertFalse(any('/test_' in p or '/reference.py' in p for p in identity['implementation_sha256']))
        self.assertFalse(identity['production_host_command'])
        self.assertFalse(identity['native_acceptance'])
        self.assertFalse(identity['historical_pass_inherited'])
        with patch.object(m, 'OWNER_SHA', '0' * 64), self.assertRaisesRegex(ValueError, 'source drift'):
            m.source_identity()

    def test_add_accepts_readonly_initial_hidden_without_fabricated_producer_acks(self):
        d = self.setup_driver(m.ElementwiseOp.Add, width=64, readonly_a=True)
        raw = d.a.raw()
        self.assertTrue(d.a.readonly and d.a.published)
        self.assertFalse(d.a.written or d.a.acknowledged)
        self.finish(d)
        self.assertEqual(d.output.raw(), oracle(raw, d.b.raw(), m.ElementwiseOp.Add))
        self.assertTrue(d.output.published)
        self.assertFalse(d.a.written or d.a.acknowledged)
        self.assertEqual(d.a.raw(), raw)

    def test_readonly_residual_stays_hashed_and_cannot_supply_silumul(self):
        with self.assertRaisesRegex(ValueError, 'actual producer'):
            self.setup_driver(m.ElementwiseOp.SiluMul, readonly_a=True)
        d = self.setup_driver(m.ElementwiseOp.Add, readonly_a=True)
        while d.owner.state != 'finish':
            d.tick(response_ready=False)
        d.a.storage[64] ^= 1
        with self.assertRaisesRegex(ValueError, 'producer bytes changed'):
            d.tick()
        self.assertFalse(d.output.published)

    def test_actual_producer_data_acks_publication_and_fresh_sentinels_required(self):
        for defect in ('readonly_b', 'unwritten', 'unacked', 'unpublished',
                       'wrong_extent', 'written_output', 'changed_sentinel'):
            with self.subTest(defect=defect):
                memory = m.TypedMemory()
                a = (memory.add_readonly(0x100000, bytes(64)) if defect == 'readonly_a' else
                     produced(memory, 0x100000, bytes(128 if defect == 'wrong_extent' else 64)))
                if defect == 'readonly_b':
                    memory.add_readonly(0x200000, bytes(64))
                else:
                    produced(memory, 0x200000, bytes(64))
                if defect == 'unwritten':
                    a.written.clear()
                if defect == 'unacked':
                    a.acknowledged.clear()
                if defect == 'unpublished':
                    a.published = False
                output = memory.allocate_output(0x300000, 64)
                if defect == 'written_output':
                    output.written.add(0)
                if defect == 'changed_sentinel':
                    output.storage[64] ^= 1
                owner = m.ElementwiseOwner(ConvScalar(), hidden_width=32, ffn_width=32, test_geometry=True)
                job = m.ElementwiseJob(1, 0x100000, 0x200000, 0x300000, 1, row_width=32)
                with self.assertRaises(ValueError):
                    m.TypedElementwiseDriver(owner, memory, job)
                self.assertIsNone(owner.scalar.client)
                self.assertEqual(owner.state, 'idle')


if __name__ == '__main__':
    unittest.main()
