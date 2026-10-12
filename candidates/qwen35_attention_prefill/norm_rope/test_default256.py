"""C2 opt-in arithmetic and legacy-mode protocol, small software transactions."""
from collections import Counter
from dataclasses import replace
import struct
import unittest
from unittest.mock import patch

import numpy as np

from . import owner as o
from .scalar import NormRopeScalar, RawScalarResult
from .driver import TypedNormRopeDriver
from .test_owner import Transport, values, opaque, pack
from ...qwen35_gdn_prefill.rms_owner import ArithmeticFault
from ...qwen35_gdn_prefill.typed_dense import TypedMemory


def reference(words, weights):
    # Independent vector-residue implementation, not the serial owner loop.
    x = np.array(words, dtype='<u4').view('<f4')
    w = np.array(weights, dtype='<u4').view('<f4')
    squares = np.multiply(x, x, dtype=np.float32)
    accum = np.zeros((4, 8), dtype=np.float32)
    for tile in squares.reshape(8, 4, 8):
        accum = np.add(accum, tile, dtype=np.float32)
    lanes = accum[0]
    for residue in accum[1:]:
        lanes = np.add(lanes, residue, dtype=np.float32)
    total = np.float32(0)
    for lane in lanes:
        total = np.add(total, lane, dtype=np.float32)
    mean = np.multiply(total, np.float32(1 / 256), dtype=np.float32)
    eps = np.array([o.EPSILON], dtype='<u4').view('<f4')[0]
    mean_eps = np.add(mean, eps, dtype=np.float32)
    inverse = np.divide(np.float32(1), np.sqrt(mean_eps, dtype=np.float32), dtype=np.float32)
    weighted = np.multiply(np.multiply(x, inverse, dtype=np.float32),
                           np.add(np.float32(1), w, dtype=np.float32), dtype=np.float32)
    bits = weighted.view('<u4')
    rounded = ((bits.astype(np.uint64) + 0x7fff + ((bits >> 16) & 1)) >> 16).astype('<u2')
    return rounded.tobytes(), int(mean_eps.view('<u4')), int(inverse.view('<u4'))


def case(owner, policy, role=1, tag=31):
    j = o.QkNorm256Job(tag, 0x10000, 0x20000, 0x30000, 1, role,
                       0x40000 if role == 0 else 0, policy=policy)
    xs = [values(256, 139 * head) for head in range(j.heads)]
    xs[0] = (0, 0x8000) + xs[0][2:]
    weights = values(256, 111)
    raw = b''.join(pack(x) + (pack(opaque(256)) if role == 0 else b'') for x in xs)
    return Transport(owner, j, {j.input: raw, j.weight: pack(weights)}), xs, weights


class Default256Tests(unittest.TestCase):
    def test_opt_in_legacy_switch_and_independent_numeric(self):
        scalar = NormRopeScalar()
        owner = o.QkNorm256Owner(scalar)
        for index, policy in enumerate((o.POLICY, o.TORCH_DEFAULT256_POLICY, o.POLICY,
                                         o.TORCH_DEFAULT256_POLICY)):
            d, xs, weights = case(owner, policy, index // 2, tag=31 + index)
            before = scalar.calls.copy()
            result = d.run(memory_ready=True)
            self.assertIsNone(result.status)
            self.assertEqual(result.write_bytes, d.job.write_bytes)
            self.assertIsNone(scalar.client)
            self.assertTrue(owner.ports()['job_ready'])
            if policy == o.TORCH_DEFAULT256_POLICY:
                expected = [reference(tuple(v << 16 for v in x), tuple(v << 16 for v in weights))
                            for x in xs]
                self.assertEqual(d.raw(d.job.output, d.job.vector_bytes), b''.join(e[0] for e in expected))
                self.assertEqual((result.last_mean_eps, result.last_inverse), expected[-1][1:])
                self.assertEqual(scalar.calls - before, Counter(add=545 * d.job.heads,
                    mul=769 * d.job.heads, sqrt=d.job.heads, div=d.job.heads))
            else:
                self.assertEqual(scalar.calls - before,
                                 Counter(add=515 * d.job.heads, mul=775 * d.job.heads))
            if d.job.role == 0:
                self.assertEqual(d.raw(d.job.gate_output, d.job.vector_bytes), pack(opaque(256)) * d.job.heads)

    def test_div_sqrt_error_nonfinite_and_type_protocol(self):
        for operation in ('sqrt', 'div'):
            for value, status in ((None, 'Numerical'), (0x7f800000, 'Numerical'), (True, 'Protocol')):
                scalar = NormRopeScalar()
                original = scalar.op
                def fake(client, op, a, b=0):
                    if op == operation:
                        if value is None:
                            raise ArithmeticFault('existing service error')
                        return value
                    return original(client, op, a, b)
                with patch.object(scalar, 'op', side_effect=fake):
                    d, _, _ = case(o.QkNorm256Owner(scalar), o.TORCH_DEFAULT256_POLICY)
                    result = d.run()
                self.assertEqual(result.status, status)
                self.assertEqual(result.write_bytes, 0)
                self.assertTrue(d.owner.poison)
                self.assertIsNone(scalar.client)
                self.assertFalse(d.writes)

    def test_c2_add_mul_still_require_genuine_raw_flags(self):
        scalar = NormRopeScalar()
        with patch.object(scalar, 'raw_op', return_value=RawScalarResult(0, 0, False, False)):
            d, _, _ = case(o.QkNorm256Owner(scalar), o.TORCH_DEFAULT256_POLICY)
            self.assertEqual(d.run().status, 'Protocol')
            self.assertFalse(d.writes)

    def test_successful_returned_sqrt_and_div_words_drive_following_requests(self):
        scalar = NormRopeScalar()
        original_op, original_raw = scalar.op, scalar.raw_op
        requests, unflagged = [], []
        def altered(client, operation, a, b=0):
            if operation in ('sqrt', 'div'):
                scalar.calls[operation] += 1
                unflagged.append((operation, a, b))
                return 0x40000000 if operation == 'sqrt' else 0x3f000000
            return original_op(client, operation, a, b)
        def recorded(client, operation, a, b=0):
            requests.append((operation, a, b))
            return original_raw(client, operation, a, b)
        with patch.object(scalar, 'op', side_effect=altered), patch.object(scalar, 'raw_op', side_effect=recorded):
            d, xs, _ = case(o.QkNorm256Owner(scalar), o.TORCH_DEFAULT256_POLICY)
            result = d.run()
        self.assertIsNone(result.status)
        self.assertEqual(result.last_inverse, 0x3f000000)
        self.assertEqual([r for r in unflagged if r[0] == 'div'], [('div', 0x3f800000, 0x40000000)] * d.job.heads)
        for x in xs:
            self.assertIn(('mul', x[71] << 16, 0x3f000000), requests)

    def test_c2_typed_q_gate_publication_and_policy_identity(self):
        memory, scalar = TypedMemory(), NormRopeScalar()
        j = o.QkNorm256Job(77, 0x10000, 0x20000, 0x30000, 1, 0, 0x40000,
                           policy=o.TORCH_DEFAULT256_POLICY)
        x, weight, gate = values(256), values(256, 71), opaque(256)
        memory.add_readonly(j.input, (pack(x) + pack(gate)) * j.heads)
        memory.add_readonly(j.weight, pack(weight))
        for base, size in j.output_spans:
            memory.allocate_output(base, size)
        d = TypedNormRopeDriver(o.QkNorm256Owner(scalar), memory, j)
        while d.owner.state != 'finish':
            d.tick(response_ready=False)
        self.assertTrue(all(not r.published for r in d.outputs))
        self.assertEqual(d.identity['norm_policy'], o.TORCH_DEFAULT256_POLICY)
        self.assertFalse(d.identity['production_chisel_policy_implemented'])
        d.tick(response_ready=True)
        self.assertIsNone(d.response.status)
        self.assertTrue(all(r.published for r in d.outputs))
        expected = reference(tuple(v << 16 for v in x), tuple(v << 16 for v in weight))[0]
        self.assertEqual(d.outputs[0].raw(), expected * j.heads)
        self.assertEqual(d.outputs[1].raw(), pack(gate) * j.heads)

    def test_unknown_policy_rejected_before_scalar_memory(self):
        scalar = NormRopeScalar(); owner = o.QkNorm256Owner(scalar)
        j = o.QkNorm256Job(1, 0x10000, 0x20000, 0x30000, 1, 1, policy=0xc3)
        with self.assertRaisesRegex(ValueError, 'descriptor'):
            owner.tick(job=j)
        self.assertFalse(scalar.calls)
        self.assertIsNone(owner.request)
        self.assertTrue(owner.ports()['job_ready'])

    def test_c2_final_ack_backpressure_and_abort(self):
        d, _, _ = case(o.QkNorm256Owner(NormRopeScalar()), o.TORCH_DEFAULT256_POLICY)
        while d.owner.state != 'finish':
            d.tick(response_ready=False)
        held = d.owner.result
        for _ in range(3):
            d.tick(response_ready=False)
            self.assertIs(d.owner.result, held)
        d.tick(abort=True, response_ready=True)
        self.assertIsNone(d.response)
        self.assertEqual(d.run().status, 'Aborted')
        self.assertTrue(d.owner.poison)


if __name__ == '__main__':
    unittest.main()
