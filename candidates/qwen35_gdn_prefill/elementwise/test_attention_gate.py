"""Bounded software-only coverage of the existing opt-in attention gate owner.

Expected values use exact rational FP32 primitives and literal source recipe
coefficients. They never call the owner's scalar, observer, NumPy or a native
framework. No checkpoint, Dense library, compiler, Chisel or RTL is executed.
"""
from collections import Counter
from dataclasses import replace
from fractions import Fraction
from functools import lru_cache
import random
import struct
import time
import unittest
from unittest.mock import patch

from . import model as m
from .test_model import bf, produced, oracle as legacy_oracle
from .. import rms_owner as rms
from ..conv.scalar import ConvScalar
from ..prep.scalar import PrepScalar
from ...qwen2_resident_matrix.ffn_public.test_prefix_owners import (
    exact, rn, ref_add, ref_mul, ref_div, ref_bf)


@lru_cache(maxsize=2048)
def exact_sigmoid(gate):
    """Separately rounded frozen ExpNegative4 / Add0 / Div2 / MulIeeeRne6."""
    magnitude = gate & 0x7fffffff
    if gate >> 31 and magnitude >= 0x42a00000:
        raise ValueError('unsupported negative source gate')
    if magnitude >= 0x42a00000:
        exponential = 0
    else:
        scaled = ref_mul(magnitude, 0x3fb8aa3b)
        integral = int(exact(scaled))
        fraction = ref_add(scaled, rn(Fraction(integral)) ^ 0x80000000)
        coefficients = (0x3f800000, 0xbf317218, 0x3e75fdf0, 0xbd635847,
                        0x3c1d955b, 0xbaaec3ff, 0x39218489, 0xb77fe5fe)
        exponential = coefficients[-1]
        for coefficient in reversed(coefficients[:-1]):
            exponential = ref_add(ref_mul(exponential, fraction), coefficient)
        exponential = ref_mul(exponential, (127 - integral) << 23)
    denominator = ref_add(0x3f800000, exponential)
    reciprocal = ref_div(0x3f800000, denominator)
    return ref_mul(reciprocal, exponential if gate >> 31 else 0x3f800000)


def reference(gates, contexts, *, round_sigmoid=True):
    outputs, observed = [], []
    for index, ((gate,), (context,)) in enumerate(zip(
            struct.iter_unpack('<H', gates), struct.iter_unpack('<H', contexts))):
        sigmoid = exact_sigmoid(gate << 16)
        rounded = ref_bf(sigmoid)
        observed.append((index, sigmoid, rounded >> 16))
        product = ref_mul(rounded if round_sigmoid else sigmoid, context << 16)
        outputs.append(ref_bf(product) >> 16)
    return struct.pack('<' + 'H' * len(outputs), *outputs), observed


def raw(words):
    return struct.pack('<' + 'H' * len(words), *words)


class AttentionGateTests(unittest.TestCase):
    def setup_driver(self, *, width=32, tokens=1, gates=None, contexts=None,
                     production=False, observer=None, prep=False):
        scalar = PrepScalar(enable_softplus=True) if prep else ConvScalar()
        self.memory = m.TypedMemory()
        self.owner = m.ElementwiseOwner(scalar, enable_attention_sigmoid_mul=True,
            sigmoid_observer=observer, **({} if production else dict(
                hidden_width=width, ffn_width=width, attention_width=width, test_geometry=True)))
        width = m.ATTENTION_WIDTH if production else width
        count = width * tokens
        rng = random.Random(9217)
        gates = bf([rng.uniform(-7, 7) for _ in range(count)]) if gates is None else gates
        contexts = bf([rng.uniform(-4, 4) for _ in range(count)]) if contexts is None else contexts
        produced(self.memory, 0x100000, gates)
        produced(self.memory, 0x200000, contexts)
        self.memory.allocate_output(0x300000, count * 2)
        self.job = m.ElementwiseJob(102, 0x100000, 0x200000, 0x300000,
                                   tokens, m.ElementwiseOp.SigmoidMul, width)
        return m.TypedElementwiseDriver(self.owner, self.memory, self.job)

    def until(self, driver, predicate, **kwargs):
        deadline = time.monotonic() + 30
        for _ in range(3000):
            if predicate():
                return
            self.assertLess(time.monotonic(), deadline, 'bounded software-only attention gate check')
            driver.tick(**kwargs)
        self.fail('bounded attention owner handshake budget')

    def finish(self, driver):
        self.until(driver, lambda: driver.response is not None)
        return driver.report()

    def test_default_sigmoid_rejected_before_dma_and_source_identity_is_pinned(self):
        scalar, memory = ConvScalar(), m.TypedMemory()
        owner = m.ElementwiseOwner(scalar)
        job = m.ElementwiseJob(103, 0x100000, 0x200000, 0x300000, 1,
                              m.ElementwiseOp.SigmoidMul, 2048)
        for operation in (m.ElementwiseOp.SigmoidMul, 2):
            candidate = replace(job, op=operation)
            with self.assertRaisesRegex(ValueError, 'explicit opt-in'):
                m.TypedElementwiseDriver(owner, memory, candidate)
            with self.assertRaisesRegex(ValueError, 'explicit opt-in'):
                owner.tick(job=candidate)
        self.assertIsNone(owner.request)
        self.assertIsNone(scalar.client)
        self.assertFalse(scalar.calls or owner.counts or memory.regions)
        identity = m.source_identity()
        self.assertEqual(identity['source_default_attention_width'], 2048)
        self.assertIs(identity['source_default_enable_attention_sigmoid_mul'], False)
        self.assertEqual(identity['elementwise_opcodes'], dict(Add=0, SiluMul=1, SigmoidMul=2))
        self.assertEqual(identity['source_sha256']['HEAD:' + m.OWNER_SOURCE], m.OWNER_SHA)
        self.assertFalse(any('/test_' in p or '/reference.py' in p for p in identity['implementation_sha256']))
        for field in ('rtl_executed', 'native_acceptance', 'native_numeric_diagnostics_executed',
                      'historical_pass_inherited', 'production_host_command'):
            self.assertFalse(identity[field])
        with patch.object(m, 'OWNER_SHA', '0' * 64), self.assertRaisesRegex(ValueError, 'source drift'):
            m.source_identity()

    def test_exact_width_and_explicit_geometry_enable_types(self):
        job = m.ElementwiseJob(1, 0x100000, 0x200000, 0x300000, 1, 2, 2048)
        job.validate(enable_attention_sigmoid_mul=True)
        replace(job, tokens=128).validate(enable_attention_sigmoid_mul=True)
        for width in (0, 31, 32, 1024, 2047, 2080, True):
            with self.subTest(width=width), self.assertRaises(ValueError):
                replace(job, row_width=width).validate(enable_attention_sigmoid_mul=True)
        replace(job, row_width=64).validate(32, 64, True, attention_width=64,
                                          enable_attention_sigmoid_mul=True)
        for options in (dict(attention_width=32), dict(attention_width=31, test_geometry=True),
                        dict(attention_width=2080, test_geometry=True), dict(attention_width=True),
                        dict(enable_attention_sigmoid_mul=1), dict(enable_attention_sigmoid_mul='true'),
                        dict(sigmoid_observer=[])):
            with self.subTest(options=options), self.assertRaises(ValueError):
                m.ElementwiseOwner(ConvScalar(), **options)
        for op in (-1, 3, True, 2.0):
            with self.subTest(op=op), self.assertRaises(ValueError):
                replace(job, op=op).validate(enable_attention_sigmoid_mul=True)

    def test_m1_production_exact_integer_recipe_and_actual_boundary_observer(self):
        observations = []
        d = self.setup_driver(production=True, observer=lambda *values: observations.append(values))
        sources = tuple(region.raw() for region in d.sources)
        expected, boundaries = reference(*sources)
        report = self.finish(d)
        self.assertIsNone(d.response.status)
        self.assertEqual(d.output.raw(), expected)
        self.assertEqual(observations, boundaries)
        self.assertEqual(d.owner.scalar_counts,
                         dict(exp_negative=2048, add=2048, div=2048, mul_ieee_rne=4096))
        self.assertEqual(d.owner.exp_counts, dict(mul=2048 * 9, add=2048 * 8))
        self.assertEqual(report['counts']['read_bytes'], 8192)
        self.assertEqual(report['counts']['write_bytes'], 4096)
        self.assertEqual(report['owner']['accepted']['write_acks'], 64)
        self.assertTrue(report['owner']['production_geometry'])
        self.assertTrue(report['owner']['enable_attention_sigmoid_mul'])
        self.assertEqual(report['owner']['attention_width'], 2048)
        self.assertEqual(sources, tuple(region.raw() for region in d.sources))
        self.assertIsNone(d.owner.scalar.client)
        self.assertFalse(any(report[k] for k in ('state_committed', 'history_committed', 'generation_advanced')))

    def test_sigmoid_rounding_is_required_skips_silu_and_ignores_observer_return(self):
        d = self.setup_driver(width=64, tokens=2, observer=lambda *values: 0x7fc00000)
        sources = tuple(region.raw() for region in d.sources)
        expected, _ = reference(*sources)
        self.assertNotEqual(expected, reference(*sources, round_sigmoid=False)[0])
        self.assertNotEqual(expected, legacy_oracle(*sources, m.ElementwiseOp.SiluMul))
        seen_buffers = [set(), set(), set()]
        for index in range(3000):
            if d.owner.request is not None and d.owner.request.write:
                local = d.owner.program.gi_frame.f_locals
                self.assertEqual({name for name, value in local.items() if type(value) is list},
                                 {'input_a', 'input_b', 'output'})
                for seen, name in zip(seen_buffers, ('input_a', 'input_b', 'output')):
                    self.assertEqual(len(local[name]), 32)
                    seen.add(id(local[name]))
            d.tick(memory_ready=index % 3 != 0, memory_response_ready=index % 4 != 0,
                   response_ready=index % 5 != 0)
            if d.response is not None:
                break
        self.assertIsNotNone(d.response)
        self.assertEqual(d.output.raw(), expected)
        self.assertEqual([len(seen) for seen in seen_buffers], [1, 1, 1])
        self.assertEqual(d.owner.scalar_counts['mul_ieee_rne'], 256)
        self.assertNotIn('mul', d.owner.scalar_counts)

    def test_add_then_sigmoid_then_silu_share_owner_scalar_and_memory_without_reset(self):
        scalar, memory, observed = PrepScalar(enable_softplus=True), m.TypedMemory(), []
        owner = m.ElementwiseOwner(scalar, hidden_width=32, ffn_width=32,
            attention_width=32, test_geometry=True, enable_attention_sigmoid_mul=True,
            sigmoid_observer=lambda *values: observed.append(values))
        memory.add_readonly(0x100000, bf([-1, 0, 1, 2] * 8))
        produced(memory, 0x200000, bf([0.25] * 32))
        for base in (0x300000, 0x400000, 0x500000):
            memory.allocate_output(base, 64)
        totals = Counter()
        for tag, op, a, out in ((1, m.ElementwiseOp.Add, 0x100000, 0x300000),
                               (2, m.ElementwiseOp.SigmoidMul, 0x300000, 0x400000),
                               (3, m.ElementwiseOp.SiluMul, 0x400000, 0x500000)):
            d = m.TypedElementwiseDriver(owner, memory, m.ElementwiseJob(tag, a, 0x200000, out, 1, op, 32))
            inputs = tuple(region.raw() for region in d.sources)
            expected = reference(*inputs)[0] if op == m.ElementwiseOp.SigmoidMul else legacy_oracle(*inputs, op)
            self.finish(d)
            self.assertIsNone(d.response.status)
            self.assertEqual(d.output.raw(), expected)
            self.assertTrue(d.output.published)
            self.assertIs(d.owner, owner)
            self.assertIs(d.memory, memory)
            self.assertIs(d.owner.scalar, scalar)
            self.assertIsNone(scalar.client)
            totals += owner.scalar_counts
        self.assertEqual(scalar.calls, totals)
        self.assertEqual(totals, dict(add=96, exp_negative=64, div=64, mul_ieee_rne=160))
        self.assertEqual(len(observed), 32)
        self.assertFalse(scalar.soft_internal_calls)
        self.assertTrue(owner.ports()['job_ready'])

    def test_signed_zero_subnormal_positive_saturation_and_op6_underflow(self):
        gates = raw([0, 0x8000, 1, 0x8001, 0xc29f, 0x42a0, 0x7f7f, 0xc120] * 4)
        contexts = raw([0x8000, 0, 1, 0x8001, 0x0080, 1, 0x8001, 1] * 4)
        d = self.setup_driver(gates=gates, contexts=contexts)
        calls = []
        operation = d.owner.scalar.op
        def observe(client, op, a, b=0):
            result = operation(client, op, a, b)
            calls.append((op, a, b, result))
            return result
        with patch.object(d.owner.scalar, 'op', side_effect=observe):
            self.finish(d)
        self.assertIsNone(d.response.status)
        self.assertEqual(d.output.raw(), reference(gates, contexts)[0])
        self.assertEqual(struct.unpack('<4H', d.output.raw()[:8]), (0x8000, 0, 0, 0x8000))
        self.assertEqual(calls[7 * 5 + 4][0], 'mul_ieee_rne')
        op, a, b, result = calls[7 * 5 + 4]
        self.assertLess(result & 0x7fffffff, 0x00800000)
        self.assertNotEqual(exact(a) * exact(b), exact(result))
        self.assertTrue(all(op != 'mul' for op, *_ in calls))
        scalar, client = d.owner.scalar, object()
        self.assertTrue(scalar.acquire(client))
        with self.assertRaisesRegex(rms.ArithmeticFault, 'underflow'):
            scalar.op(client, 'mul', a, b)
        with self.assertRaisesRegex(rms.ArithmeticFault, 'underflow'):
            scalar.op(client, 'div', 0x00800000, 0x40400000)
        scalar.release(client)

    def test_nonfinite_and_out_of_domain_leave_partial_staging_unpublished(self):
        for gate, context, status in ((0xc2a0, 0x3f80, 'Unsupported'),
                (0xc2a1, 0x3f80, 'Unsupported'), (0xff7f, 0x3f80, 'Unsupported'),
                (0x7f80, 0x3f80, 'Numerical'), (0xff80, 0x3f80, 'Numerical'),
                (0x7fc0, 0x3f80, 'Numerical'), (0x3f80, 0x7f80, 'Numerical'),
                (0x3f80, 0x7fc0, 'Numerical')):
            with self.subTest(gate=gate, context=context):
                d = self.setup_driver(width=64, gates=raw([0x3f80] * 63 + [gate]),
                                      contexts=raw([0x3f80] * 63 + [context]))
                self.finish(d)
                self.assertEqual(d.response.status, status)
                self.assertEqual(d.response.write_bytes, 64)
                self.assertFalse(d.output.published or d.response.staging_complete)
                self.assertEqual(d.owner.state, 'locked')
                self.assertIsNone(d.owner.scalar.client)
                with self.assertRaises(ValueError):
                    d.memory.read64(d.job.output)

    def test_held_request_final_ack_and_terminal_acceptance_fence(self):
        d = self.setup_driver(width=64)
        first = d.owner.request
        for _ in range(3):
            d.tick(memory_ready=False)
            self.assertIs(d.owner.request, first)
            self.assertEqual(d.output.raw(), m.GUARD * 2)
        self.until(d, lambda: d.pending is not None and d.pending_request.address == d.job.output + 64)
        for _ in range(3):
            d.tick(memory_response_ready=False)
            self.assertEqual(d.owner.ack_bytes, 64)
            self.assertIsNone(d.owner.result)
            self.assertFalse(d.output.published)
            with self.assertRaises(ValueError):
                d.memory.read64(d.job.output)
        d.tick(response_ready=False)
        held = d.owner.result
        self.assertTrue(held.staging_complete)
        for _ in range(3):
            d.tick(response_ready=False)
            self.assertIs(d.owner.result, held)
            self.assertFalse(d.output.published)
        with self.assertRaisesRegex(ValueError, 'held completion'):
            d.owner.reset()
        d.tick()
        self.assertIs(d.response, held)
        self.assertTrue(d.output.published)
        self.assertEqual(d.owner.counts['owner_results'], 1)

    def test_abort_reset_drain_and_preserve_opt_in_and_observer(self):
        for reset in (False, True):
            for stage in ('issue', 'read', 'write', 'held_success'):
                with self.subTest(reset=reset, stage=stage):
                    observer = lambda *values: None
                    d = self.setup_driver(observer=observer)
                    if stage in ('read', 'write'):
                        self.until(d, lambda: d.pending is not None and d.pending_request.write == (stage == 'write'))
                    elif stage == 'held_success':
                        self.until(d, lambda: d.owner.state == 'finish', response_ready=False)
                    request = d.owner.request
                    event = d.tick(reset=reset, abort=not reset, memory_response_ready=False)
                    self.assertFalse(event['memory_fire'] or event['response_fire'])
                    self.assertFalse(d.output.published)
                    if stage in ('read', 'write'):
                        self.assertEqual(d.owner.state, 'drain')
                        self.assertIs(d.owner.request, request)
                        with self.assertRaises(ValueError):
                            d.owner.reset()
                    self.finish(d)
                    self.assertEqual(d.response.status, 'Aborted')
                    self.assertFalse(d.output.published)
                    self.assertIsNone(d.memory.pending)
                    self.assertIsNone(d.owner.scalar.client)
                    self.assertEqual(d.owner.state, 'locked')
                    d.owner.reset()
                    self.assertTrue(d.owner.ports()['job_ready'])
                    self.assertTrue(d.owner.enable_attention_sigmoid_mul)
                    self.assertEqual(d.owner.attention_width, 32)
                    self.assertIs(d.owner.sigmoid_observer, observer)
                    d.memory.allocate_output(0x400000, 64)
                    following = m.TypedElementwiseDriver(d.owner, d.memory, replace(d.job, tag=104, output=0x400000))
                    self.finish(following)
                    self.assertIsNone(following.response.status)
                    self.assertTrue(following.output.published)

    def test_final_ack_error_priority_and_no_false_publication(self):
        for fault in ('abort', 'reset'):
            for malformed in (False, True):
                d = self.setup_driver(width=64)
                self.until(d, lambda: d.pending is not None and d.pending_request.address == d.job.output + 64)
                options = dict(ack_tag=d.pending.tag + 1) if malformed else dict(ack_error=True)
                event = d.tick(**{fault: True}, **options)
                self.assertTrue(event['memory_response_fire'])
                self.assertFalse(event['response_fire'])
                self.finish(d)
                self.assertEqual(d.response.status, 'Protocol' if malformed else 'Memory')
                self.assertEqual(d.response.write_bytes, 64)
                self.assertFalse(d.output.published)
                self.assertIsNone(d.memory.pending)

    def test_observer_exception_drains_same_read_then_reset_recovers(self):
        observed = []
        def fail_once(*values):
            observed.append(values)
            if len(observed) == 1:
                raise RuntimeError('directed sigmoid observer failure')
        d = self.setup_driver(observer=fail_once)
        self.until(d, lambda: d.pending is not None and d.pending_request.address == d.job.b)
        pending, request = d.pending, d.pending_request
        self.assertFalse(request.write)
        with self.assertRaisesRegex(RuntimeError, 'directed sigmoid observer failure'):
            d.tick()
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0], reference(d.a.raw(), d.b.raw())[1][0])
        self.assertEqual(d.owner.scalar.calls,
                         dict(exp_negative=1, add=1, div=1, mul_ieee_rne=1))
        self.assertIs(d.pending, pending)
        self.assertIs(d.pending_request, request)
        self.assertIs(d.owner.request, request)
        self.assertIs(d.owner.scalar.client, d.owner)
        self.assertIsNone(d.response)
        self.assertFalse(d.output.published or d.output.written or d.output.acknowledged)
        self.assertEqual(d.output.raw(), m.GUARD)
        with self.assertRaises(ValueError):
            d.memory.read64(d.job.output)
        with self.assertRaisesRegex(ValueError, 'drained transport'):
            d.owner.reset()

        event = d.tick(abort=True, memory_response_ready=False)
        self.assertFalse(event['memory_fire'] or event['memory_response_fire'] or event['response_fire'])
        self.assertEqual(d.owner.state, 'drain')
        self.assertIs(d.pending, pending)
        self.assertIs(d.pending_request, request)
        self.assertIs(d.owner.request, request)
        event = d.tick(response_ready=False)
        self.assertTrue(event['memory_response_fire'])
        self.assertFalse(event['memory_fire'] or event['response_fire'])
        self.assertIsNone(d.pending)
        self.assertIsNone(d.pending_request)
        self.assertIsNone(d.owner.request)
        self.assertIsNone(d.memory.pending)
        self.assertIsNone(d.owner.scalar.client)
        self.assertEqual(d.owner.result.status, 'Aborted')
        self.assertEqual(d.owner.result.write_bytes, 0)
        d.tick()
        self.assertEqual(d.response.status, 'Aborted')
        self.assertEqual(d.owner.state, 'locked')
        self.assertFalse(d.output.published)

        d.owner.reset()
        self.assertIs(d.owner.sigmoid_observer, fail_once)
        self.assertTrue(d.owner.enable_attention_sigmoid_mul)
        # The failed invocation wrote nothing, so its unchanged output
        # allocation is still eligible for a fresh, independently tagged job.
        following = m.TypedElementwiseDriver(d.owner, d.memory, replace(d.job, tag=104))
        self.finish(following)
        self.assertIsNone(following.response.status)
        self.assertTrue(following.output.published)
        expected, boundaries = reference(d.a.raw(), d.b.raw())
        self.assertEqual(following.output.raw(), expected)
        self.assertEqual(observed[1:], boundaries)
        self.assertIsNone(d.owner.scalar.client)

    def test_parameter_binding_rejects_mutation_before_dma_and_publication(self):
        fields = dict(attention_width=64, enable_attention_sigmoid_mul=False, hidden_width=64,
                      ffn_width=64, test_geometry=False, sigmoid_observer=lambda *values: None)
        for held in (False, True):
            for name, changed in fields.items():
                with self.subTest(held=held, name=name):
                    d = self.setup_driver()
                    if held:
                        self.until(d, lambda: d.owner.state == 'finish', response_ready=False)
                    original = getattr(d.owner, name)
                    request, counters = d.owner.request, d.counts.copy()
                    setattr(d.owner, name, changed)
                    with self.assertRaisesRegex(ValueError, 'parameters changed'):
                        d.tick()
                    self.assertEqual(d.counts, counters)
                    self.assertIs(d.owner.request, request)
                    self.assertFalse(d.output.published)
                    with self.assertRaisesRegex(ValueError, 'parameters changed'):
                        d.owner.reset()
                    setattr(d.owner, name, original)
                    self.finish(d)
                    self.assertTrue(d.output.published)
        owner = m.ElementwiseOwner(ConvScalar())
        owner.enable_attention_sigmoid_mul = True
        job = m.ElementwiseJob(1, 0x100000, 0x200000, 0x300000, 1, 2, 2048)
        with self.assertRaisesRegex(ValueError, 'parameters changed'):
            m.TypedElementwiseDriver(owner, m.TypedMemory(), job)
        self.assertIsNone(owner.scalar.client)

    def test_execution_source_and_producer_drift_block_publication(self):
        for source in (False, True):
            d = self.setup_driver()
            self.until(d, lambda: d.owner.state == 'finish', response_ready=False)
            if source:
                identity = dict(m.source_identity(), changed=True)
                with patch.object(m, 'source_identity', return_value=identity):
                    with self.assertRaisesRegex(ValueError, 'source changed'):
                        d.tick()
            else:
                d.a.storage[64] ^= 1
                with self.assertRaisesRegex(ValueError, 'producer bytes changed'):
                    d.tick()
            self.assertFalse(d.output.published)

    def test_attention_inputs_require_actual_producer_receipts(self):
        for readonly in ('gate', 'context'):
            scalar, memory = ConvScalar(), m.TypedMemory()
            owner = m.ElementwiseOwner(scalar, hidden_width=32, ffn_width=32,
                attention_width=32, test_geometry=True, enable_attention_sigmoid_mul=True)
            for name, base in (('gate', 0x100000), ('context', 0x200000)):
                if name == readonly:
                    memory.add_readonly(base, bf([1] * 32))
                else:
                    produced(memory, base, bf([1] * 32))
            memory.allocate_output(0x300000, 64)
            job = m.ElementwiseJob(1, 0x100000, 0x200000, 0x300000, 1, 2, 32)
            with self.assertRaisesRegex(ValueError, 'actual producer'):
                m.TypedElementwiseDriver(owner, memory, job)
            self.assertIsNone(owner.request)
            self.assertIsNone(scalar.client)


if __name__ == '__main__':
    unittest.main()
