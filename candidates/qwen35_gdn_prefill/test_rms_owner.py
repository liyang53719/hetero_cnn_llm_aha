"""Small synthetic memory/rounding/protocol gates; no model, C++ build or RTL."""
from dataclasses import replace
from pathlib import Path
import struct
import time
import unittest
from unittest.mock import patch

import numpy as np

from . import rms_owner as r


def bf16(values):
    words = np.asarray(values, dtype='<f4').view('<u4')
    return ((words + 0x7fff + ((words >> 16) & 1)) >> 16).astype('<u2')


def decode(raw, shape):
    return (np.frombuffer(raw, '<u2').astype('<u4') << 16).view('<f4').reshape(shape)


def oracle(hidden, weight, rows, policy):
    """Independent batched NumPy node graph, evaluated after owner completion."""
    x, w = decode(hidden, (rows, 1024)), decode(weight, (1024,))
    squares = np.multiply(x, x, dtype=np.float32)
    total = np.zeros((rows, 1), dtype='<f4')
    add = lambda a, b: np.add(a, b, dtype=np.float32)
    if policy == r.ReductionPolicy.LegacyAscending:
        for i in range(1024):
            total = add(total, squares[:, i:i + 1])
    else:
        for lane in range(8):
            lane_sum = np.zeros_like(total)
            for residue in range(4):
                residue_sum = np.zeros_like(total)
                for block in range(2):
                    partial = np.zeros_like(total)
                    for term in range(16):
                        i = block * 512 + term * 32 + residue * 8 + lane
                        partial = add(partial, squares[:, i:i + 1])
                    residue_sum = add(residue_sum, partial)
                lane_sum = add(lane_sum, residue_sum)
            total = add(total, lane_sum)
    mean = np.multiply(total, np.float32(1 / 1024), dtype=np.float32)
    variance = add(mean, np.float32(1e-6))
    root = np.sqrt(variance, dtype=np.float32)
    inverse = np.divide(np.float32(1), root, dtype=np.float32)
    normalized = np.multiply(x, inverse, dtype=np.float32)
    result = np.multiply(normalized, add(np.float32(1), w), dtype=np.float32)
    return bf16(result).tobytes(), total.view('<u4').reshape(-1).tolist()


def raw_values(rows, salt=0):
    random = np.random.default_rng(812 + salt)
    data = random.uniform(-4, 4, (rows, 1024)).astype('<f4')
    data[:, 0] = np.float32(2**-70)  # square enters gradual FP32 underflow
    data[:, 1] = np.float32(-0.0)
    return bf16(data).tobytes()


class RmsTests(unittest.TestCase):
    def setup_driver(self, tokens=1, policy=r.ReductionPolicy.LegacyAscending):
        self.memory = r.TypedMemory()
        self.memory.add_readonly(0x10000, raw_values(tokens))
        self.memory.add_readonly(0x60000, bf16(np.linspace(-0.2, 0.2, 1024, dtype='<f4')).tobytes())
        self.memory.allocate_output(0x80000, tokens * 2048)
        self.scalar = r.SharedScalar()
        self.owner = r.RmsOwner(self.scalar)
        self.job = r.RmsJob(71, 0x10000, 0x60000, 0x80000, tokens, policy)
        return r.TypedRmsDriver(self.owner, self.memory, self.job)

    def finish(self, driver, hook=None):
        deadline = time.monotonic() + 20
        for i in range(20000):
            self.assertLess(time.monotonic(), deadline, 'small RMS wall budget')
            driver.tick(**({} if hook is None else hook(driver, i)))
            if driver.response is not None:
                return driver.report()
        self.fail('small RMS handshake budget')

    def test_both_policies_m1_and_m16_actual_packed_outputs(self):
        sums = {}
        for tokens in (1, 16):
            for policy in r.ReductionPolicy:
                with self.subTest(tokens=tokens, policy=policy):
                    d = self.setup_driver(tokens, policy)
                    report = self.finish(d, lambda _, i: dict(memory_ready=i % 3 != 0,
                        memory_response_ready=i % 4 != 0, response_ready=i % 5 != 0))
                    expected, expected_sum = oracle(d.input.raw(), d.weight.raw(), tokens, policy)
                    self.assertEqual(d.output.raw(), expected)
                    self.assertEqual([row['sum'] for row in report['owner']['row_scalars']], expected_sum)
                    self.assertEqual(d.response.status, None)
                    self.assertEqual(d.response.write_bytes, tokens * 2048)
                    self.assertEqual(report['counts']['read_bytes'], (tokens + 1) * 2048)
                    self.assertEqual(report['owner']['scalar_calls']['mul_ieee_rne'], tokens * 3073)
                    self.assertEqual(report['owner']['scalar_calls']['add'], tokens * (2049 if policy == r.ReductionPolicy.LegacyAscending else 2153))
                    self.assertEqual(report['owner']['scalar_calls']['div'], tokens)
                    self.assertEqual(report['owner']['scalar_calls']['sqrt'], tokens)
                    self.assertIsNone(self.scalar.client)
                    self.assertFalse(report['owner']['native_acceptance'])
                    sums[tokens, policy] = expected_sum
        self.assertNotEqual(sums[16, r.ReductionPolicy.LegacyAscending], sums[16, r.ReductionPolicy.Torch210CpuDefault1024])

    def test_final_ack_and_held_terminal_require_publication_fence(self):
        d = self.setup_driver()
        while d.pending is None or not self.owner.request.write or d.counts['write_bytes'] != 2048:
            d.tick()
        for _ in range(4):
            d.tick(memory_response_ready=False)
            self.assertFalse(d.output.published)
            self.assertIsNone(d.response)
        d.tick(response_ready=False)
        held = self.owner.ports()['response']
        self.assertIsNotNone(held)
        for _ in range(4):
            d.tick(response_ready=False)
            self.assertEqual(self.owner.ports()['response'], held)
            self.assertFalse(d.output.published)
            with self.assertRaises(ValueError):
                self.memory.read64(self.job.output)
        with self.assertRaisesRegex(ValueError, 'held completion'):
            self.owner.reset()
        d.tick()
        self.assertTrue(d.output.published)
        self.assertEqual(self.owner.counts['owner_results'], 1)

    def test_same_memory_and_scalar_reused_for_next_real_producer(self):
        d = self.setup_driver()
        self.finish(d)
        first = d.output.raw()
        self.memory.allocate_output(0xa0000, 2048)
        j2 = replace(self.job, tag=72, input=self.job.output, output=0xa0000,
                     policy=r.ReductionPolicy.Torch210CpuDefault1024)
        following = r.TypedRmsDriver(self.owner, self.memory, j2)
        self.finish(following)
        self.assertEqual(following.output.raw(), oracle(first, d.weight.raw(), 1, j2.policy)[0])
        self.assertIs(following.owner.scalar, self.scalar)
        self.assertIs(following.memory, d.memory)

    def test_shape_dtype_extent_alias_and_unpublished_source_admission(self):
        for bad in (r.RmsJob(1, 0, 2048, 4096, 0), r.RmsJob(1, 0, 2048, 4096, 129),
                    r.RmsJob(True, 0, 2048, 4096, 1), r.RmsJob(1, 0, 0, 4096, 1),
                    r.RmsJob(1, 0, 2048, 0, 1), r.RmsJob(1, 1, 2048, 4096, 1),
                    r.RmsJob(1, 0, 2048, (1 << 56) - 64, 1), r.RmsJob(1, 0, 2048, 4096, 1, width=1536)):
            with self.subTest(job=bad), self.assertRaises(ValueError):
                bad.validate()
        r.RmsJob(1, 0, 0x60000, 0x80000, 128).validate()
        memory, owner = r.TypedMemory(), r.RmsOwner()
        memory.allocate_output(0x10000, 2048)
        memory.add_readonly(0x60000, bytes(2048))
        memory.allocate_output(0x80000, 4096)  # wrong 4-byte output extent
        with self.assertRaises(ValueError):
            r.TypedRmsDriver(owner, memory, r.RmsJob(1, 0x10000, 0x60000, 0x80000, 1))
        self.assertTrue(owner.ports()['job_ready'])

    def test_abort_drains_accepted_read_and_write_then_reset(self):
        for phase in ('read', 'write'):
            with self.subTest(phase=phase):
                d = self.setup_driver()
                while d.pending is None or bool(self.owner.request.write) != (phase == 'write'):
                    d.tick()
                accepted = self.owner.request
                d.tick(abort=True, memory_response_ready=False)
                self.assertEqual(self.owner.state, 'drain')
                self.assertEqual(self.owner.request, accepted)
                self.assertIs(self.scalar.client, self.owner)
                with self.assertRaises(ValueError):
                    self.owner.reset()
                self.finish(d)
                self.assertEqual(d.response.status, 'Aborted')
                self.assertFalse(d.output.published)
                self.assertIsNone(self.memory.pending)
                self.assertIsNone(d.pending)
                self.assertEqual(self.owner.state, 'locked')
                self.assertFalse(self.owner.ports()['job_ready'])
                self.owner.reset()
                self.assertTrue(self.owner.ports()['job_ready'])

    def test_abort_cancels_unaccepted_request_and_reset_does_not_drop_completion(self):
        d = self.setup_driver()
        self.assertEqual(self.owner.state, 'issue')
        d.tick(abort=True, memory_ready=True, response_ready=False)
        self.assertIsNone(d.pending)
        self.assertEqual(d.counts['read_bytes'], 0)
        with self.assertRaisesRegex(ValueError, 'held completion'):
            self.owner.tick(reset=True)
        self.finish(d)
        self.assertEqual(d.response.status, 'Aborted')

    def test_read_error_and_final_ack_error_never_publish(self):
        for phase in ('read', 'final_ack'):
            with self.subTest(phase=phase):
                d = self.setup_driver()
                self.finish(d, lambda x, _: dict(read_error=phase == 'read',
                    ack_error=phase == 'final_ack' and x.pending is not None and
                    self.owner.request.write and x.counts['write_bytes'] == 2048))
                self.assertEqual(d.response.status, 'Memory')
                self.assertFalse(d.output.published)
                self.assertEqual(d.response.write_bytes, 0 if phase == 'read' else 1984)
                self.assertIsNone(self.memory.pending)

    def test_bad_tag_accepted_response_retires_single_physical_obligation(self):
        for defect in ('tag', 'bytes'):
            with self.subTest(defect=defect):
                owner = r.RmsOwner()
                job = r.RmsJob(9, 0x10000, 0x20000, 0x30000, 1)
                owner.tick(job=job)
                q = owner.ports()['memory']
                owner.tick(memory_ready=True)
                bad = r.MemoryResponse(q.tag + int(defect == 'tag'), bytes(64), nbytes=32 if defect == 'bytes' else 64)
                owner.tick(memory_response=bad)
                self.assertEqual(owner.state, 'finish')
                self.assertIsNone(owner.request)
                self.assertEqual(owner.ports()['response'].status, 'Protocol')
                self.assertEqual(owner.counts['memory_responses'], 1)
                self.assertIsNone(owner.scalar.client)
                owner.tick(response_ready=True)
                self.assertEqual(owner.state, 'locked')
                self.assertEqual(owner.counts['owner_results'], 1)

    def test_reset_active_drains_read_and_keeps_one_rejected_completion(self):
        owner = r.RmsOwner()
        owner.tick(job=r.RmsJob(3, 0x10000, 0x20000, 0x30000, 1))
        q = owner.ports()['memory']
        owner.tick(memory_ready=True)
        owner.tick(reset=True)
        self.assertEqual(owner.state, 'drain')
        self.assertEqual(owner.request, q)
        owner.tick(memory_response=r.MemoryResponse(q.tag, bytes(64)))
        self.assertEqual(owner.ports()['response'].status, 'Aborted')
        with self.assertRaisesRegex(ValueError, 'held completion'):
            owner.tick(reset=True)
        owner.tick(response_ready=True)
        self.assertEqual(owner.counts['owner_results'], 1)
        owner.tick(reset=True)
        self.assertTrue(owner.ports()['job_ready'])

    def test_nonfinite_input_or_overflow_rejects_before_write(self):
        for bits in (0x7f80, 0x7fc1, 0x7f7f):
            with self.subTest(bits=bits):
                memory = r.TypedMemory()
                memory.add_readonly(0x10000, struct.pack('<1024H', *([bits] * 1024)))
                memory.add_readonly(0x20000, bytes(2048))
                memory.allocate_output(0x30000, 2048)
                d = r.TypedRmsDriver(r.RmsOwner(), memory, r.RmsJob(1, 0x10000, 0x20000, 0x30000, 1))
                self.finish(d)
                self.assertEqual(d.response.status, 'Numerical')
                self.assertEqual(d.counts['write_bytes'], 0)
                self.assertFalse(d.output.published)

    def test_explicit_mul_ieee_rne_and_legacy_exception_policies(self):
        s, client = r.SharedScalar(), object()
        self.assertTrue(s.acquire(client))
        self.assertFalse(s.acquire(object()))
        self.assertEqual(s.op(client, 'mul_ieee_rne', 1, r.word(0.5)), 0)
        self.assertEqual(s.op(client, 'mul_ieee_rne', 0x80000001, r.word(0.5)), 0x80000000)
        self.assertEqual(s.op(client, 'div', 0x00800000, r.word(2)), 0x00400000)
        with self.assertRaises(r.ArithmeticFault):
            s.op(client, 'div', 1, r.word(2))
        for operation, a, b in (('mul_ieee_rne', 0x7f7fffff, r.word(2)), ('mul_ieee_rne', 0x7f800000, 0),
                                ('div', r.word(1), 0), ('sqrt', r.word(-1), 0)):
            with self.assertRaises(r.ArithmeticFault):
                s.op(client, operation, a, b)
        with self.assertRaisesRegex(ValueError, 'explicit scalar opcode'):
            s.op(client, 'mul', r.word(1), r.word(2))
        with self.assertRaises(ValueError):
            s.op(object(), 'add', 0, 0)
        s.release(client)

    def test_torch_formula_runs_without_dirty_candidate_files(self):
        original = Path.read_bytes
        forbidden = {r.ROOT / r.OWNER_SOURCE, r.ROOT / r.RECIPE_SOURCE}
        def read(path):
            if path in forbidden:
                raise AssertionError('main owner touched dirty candidate source')
            return original(path)
        with patch.object(Path, 'read_bytes', read):
            identity = r.source_identity(r.ReductionPolicy.Torch210CpuDefault1024)
        self.assertTrue(identity['torch_policy_model_only'])
        self.assertFalse(identity['candidate_mapping_verified'])
        self.assertFalse(identity['historical_m1_pass_inherited'])


if __name__ == '__main__':
    unittest.main()
