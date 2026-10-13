"""Small, real-service proof of the owner's fused causal-prefix semantics.

Only M1/M2 synthetic transactions run, using the explicitly supplied existing
Matrix library, actual TypedMemory producer data/ACKs, and the injected Scalar.
Observers and packet recordings are host-only evidence; they never feed the
owner. There is no materialized mask-add operation or arbitrary-mask claim.
QK/scale remain rectangular and PV still consumes every staged K/V position.
Finite perturbations are subject to the unchanged arithmetic/overflow guards;
equivalence concerns accepted computations. Full-cache zero FMAs can change a
zero's sign, so numerical equality must not be advertised as raw-bit identity.
These are software resource/transaction checks, never hardware-cycle evidence.
"""
from collections import Counter
import ctypes as C
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.build_shared_matrix_recipe import from_environment
from ...qwen2_resident_matrix.ffn_attention.matrix_service import MatrixService, configure_library
from ...qwen35_gdn_prefill.typed_dense import TypedMemory
from ..norm_rope.scalar import NormRopeScalar
from . import owner as o
from .driver import TypedBf16CausalGqaDriver
from .test_gqa import float32, pack, producer, word32


def bf16(bits):
    """Independent RNE packing; retain the sign when a tiny value rounds to 0."""
    return ((bits + 0x7fff + ((bits >> 16) & 1)) >> 16) & 0xffff


class CausalEquivalenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = configure_library(C.CDLL(str(from_environment(o.ROOT))))
        cls.libm = C.CDLL('libm.so.6')
        cls.libm.fmaf.argtypes = (C.c_float, C.c_float, C.c_float)
        cls.libm.fmaf.restype = C.c_float

    def resources(self):
        self.assertEqual(self.lib.td_reset(), 0)
        return MatrixService(self.lib), NormRopeScalar(), TypedMemory()

    def run_case(self, tokens, prefix, *, perturb=False, invalid=None, zero_witness=False,
                 policy=o.QkOrder.PairHighFirst):
        matrix, scalar, memory = self.resources()
        job = o.Bf16CausalGqaJob(193, 0x100000000, 0x200000000, 0x300000000,
                                tokens, prefix, prefix + tokens, qk_policy=policy)
        query = [0] * (tokens * 8 * 256)
        keys = [0] * (job.cache_length * 2 * 256)
        values = [0] * len(keys)
        for row in range(tokens):
            for head in range(8):
                query[(row * 8 + head) * 256] = 0x3f80
        for key in range(job.cache_length):
            for head in range(2):
                base = (key * 2 + head) * 256
                # All prefix scores are -1. The final key is +1 or +2, so
                # an incorrect future-key max changes exp inputs observably.
                future = tokens == 2 and key == job.cache_length - 1
                keys[base] = (0x4200 if perturb else 0x4180) if future else 0xc180
                values[base:base + 256] = [word32(float(2 + head)) >> 16] * 256
                values[base] = 0x8001 if key == 0 else 0
                values[base + 1] = 0
                values[base + 3] = 0x3f80 if key % 2 == 0 else 0xbf80
                if future:
                    values[base:base + 256] = [0xc0e0 if perturb else 0x4040] * 256
                    # Both signs of zero must remain raw, distinct source words.
                    values[base + 1] = 0x8000 if perturb else 0
                if zero_witness and not future:
                    self.assertEqual((tokens, prefix), (2, 1))
                    keys[base] = 0 if key == 0 else 0xc400  # scores 0, -32
                    values[base:base + 256] = [0] * 256
                    values[base] = 0 if key == 0 else 0x8001
        if invalid is not None:
            target, bits = invalid
            {'query': query, 'key': keys, 'value': values}[target][
                0 if target == 'query' else (job.cache_length - 1) * 512] = bits
        for tag, ((base, extent), words) in enumerate(zip(job.input_spans, (query, keys, values)), 1):
            self.assertEqual(len(words) * 2, extent)
            region = producer(memory, base, pack(words), tag)
            self.assertTrue(region.published)
            self.assertEqual(region.written, region.acknowledged)
        memory.allocate_output(job.output, job.write_bytes)
        observed, scalar_packets, comparisons, groups, reads = [], [], [], [], []
        owner = o.Bf16CausalGqaOwner(matrix, scalar, lambda *event: observed.append(event))
        driver = TypedBf16CausalGqaDriver(owner, memory, job)
        real_op, real_less = scalar.op, o._less
        real_group, real_step, real_read = matrix.accept_group, matrix.accept_step, memory.read64

        def scalar_op(client, operation, a, b=0):
            result = real_op(client, operation, a, b)
            scalar_packets.append((operation, a, b, result))
            return result

        def compare(a, b):
            comparisons.append((a, b))
            return real_less(a, b)

        def group(client, packet):
            accepted = real_group(client, packet)
            if accepted:
                groups.append((packet, []))
            return accepted

        def step(client, packet):
            accepted = real_step(client, packet)
            if accepted:
                groups[-1][1].append(packet)
            return accepted

        def read(address):
            reads.append(address)
            return real_read(address)

        with patch.object(scalar, 'op', side_effect=scalar_op), \
                patch.object(o, '_less', side_effect=compare), \
                patch.object(matrix, 'accept_group', side_effect=group), \
                patch.object(matrix, 'accept_step', side_effect=step), \
                patch.object(memory, 'read64', side_effect=read):
            for _ in range(30000):
                if driver.response is not None:
                    break
                driver.tick()
            else:
                self.fail('bounded M1/M2 causal transaction did not finish')
        return SimpleNamespace(driver=driver, query=query, keys=keys, values=values,
                               observed=observed, scalar=scalar_packets, comparisons=comparisons,
                               groups=groups, reads=reads)

    def assert_causal_trace(self, case):
        driver, job = case.driver, case.driver.job
        self.assertIsNone(driver.response.status)
        self.assertTrue(driver.output.published)
        self.assertEqual(driver.counts['write_bytes'], job.write_bytes)
        self.assertEqual(driver.counts['ack_bytes'], job.write_bytes)
        events = {(stage, row, head, key): words for stage, row, head, key, words in case.observed}
        self.assertEqual(len(events), len(case.observed))
        expected_scalar, expected_comparisons, expected_groups = [], [], []
        causal_nodes = sum(job.query_start + row + 1 for row in range(job.tokens)) * 8
        self.assertEqual(Counter(p[0] for p in case.scalar), Counter(
            mul_ieee_rne=job.tokens * job.cache_length * 8,
            add=causal_nodes * 2, exp_negative=causal_nodes, div=causal_nodes))
        # Reconstruct each request from immutable observer values and the
        # descriptor's causal predicate, never by invoking the owner generator.
        for head in range(8):
            maxima = [None] * job.tokens
            for first in range(0, job.cache_length, 32):
                columns = min(32, job.cache_length - first)
                expected_groups.append((0x23, 256, head, first, columns))
                for row in range(job.tokens):
                    scores = events['scaled_scores_bf16', row, head, 0]
                    qk = events['qk_bf16', row, head, first]
                    self.assertEqual(len(qk), columns)
                    for col, raw in enumerate(qk):
                        key = first + col
                        scaled = word32(float32(raw) / 16.0)
                        self.assertEqual(scores[key], bf16(scaled) << 16)
                        expected_scalar.append(('mul_ieee_rne', raw, 0x3d800000, scaled))
                        if key <= job.query_start + row:
                            if maxima[row] is not None:
                                expected_comparisons.append((maxima[row], scores[key]))
                            if maxima[row] is None or float32(maxima[row]) < float32(scores[key]):
                                maxima[row] = scores[key]
            for row in range(job.tokens):
                self.assertIsNotNone(maxima[row])
                self.assertEqual(events['row_max_fp32', row, head, 0], (maxima[row],))
                scores = events['scaled_scores_bf16', row, head, 0]
                probabilities = events['probabilities_bf16', row, head, 0]
                total = 0
                for key in range(job.cache_length):
                    if key > job.query_start + row:
                        for stage in ('score_difference_fp32', 'exp_fp32', 'sum_exp_fp32'):
                            self.assertNotIn((stage, row, head, key), events)
                        self.assertEqual(events['probability_fp32', row, head, key], (0,))
                        self.assertEqual(probabilities[key], 0)  # BF16 +0, never -0
                        continue
                    difference = word32(float32(scores[key]) + float32(maxima[row] ^ 0x80000000))
                    self.assertEqual(events['score_difference_fp32', row, head, key], (difference,))
                    exponential, = events['exp_fp32', row, head, key]
                    expected_scalar.extend((('add', scores[key], maxima[row] ^ 0x80000000, difference),
                                            ('exp_negative', difference, 0, exponential)))
                    expected_comparisons.append((0x3f800000, exponential))
                    summed = word32(float32(total) + float32(exponential))
                    expected_scalar.append(('add', total, exponential, summed))
                    self.assertEqual(events['sum_exp_fp32', row, head, key], (summed,))
                    total = summed
                for key in range(job.query_start + row + 1):
                    exponential, = events['exp_fp32', row, head, key]
                    probability = word32(float32(exponential) / float32(total))
                    expected_scalar.append(('div', exponential, total, probability))
                    expected_comparisons.append((0x3f800000, probability))
                    self.assertEqual(events['probability_fp32', row, head, key], (probability,))
                    self.assertEqual(probabilities[key], bf16(probability) << 16)
            expected_groups.append((0x24, job.cache_length, head, 0, 256))
        self.assertEqual(case.scalar, expected_scalar)
        self.assertEqual(case.comparisons, expected_comparisons)
        self.assertEqual(len(case.groups), len(expected_groups))
        for (group, steps), (opcode, count, head, first, columns) in zip(case.groups, expected_groups):
            self.assertEqual((group.opcode, group.steps, group.profile), (opcode, count, 1))
            self.assertEqual(len(steps), count)
            for index, step in enumerate(steps):
                self.assertEqual((step.index, step.context, step.clear, step.last, step.finish, step.emit),
                                 (index, 0, index == 0, index + 1 == count, index + 1 == count, index + 1 == count))
                if opcode == 0x23:
                    d = index ^ 1 if job.qk_policy is o.QkOrder.PairHighFirst else index
                    a = tuple(case.query[(row * 8 + head) * 256 + d] for row in range(job.tokens))
                    b = tuple(case.keys[((first + col) * 2 + head // 4) * 256 + d] for col in range(columns))
                    self.assertEqual(step.b, b + (0,) * (256 - columns))
                else:
                    a = tuple(events['probabilities_bf16', row, head, 0][index] >> 16 for row in range(job.tokens))
                    base = (index * 2 + head // 4) * 256
                    self.assertEqual(step.b, tuple(case.values[base:base + 256]))
                    for row in range(job.tokens):
                        if index > job.query_start + row:
                            self.assertEqual(step.a[row], 0)
                self.assertEqual(step.a, a + (0,) * (16 - job.tokens))
        # Independent ordered libm FMA of the real packets. Full-cache and
        # causal-prefix reductions must agree numerically; compare zero signs
        # separately, rather than silently normalizing raw zero bits.
        for row in range(job.tokens):
            for head in range(8):
                probabilities = events['probabilities_bf16', row, head, 0]
                expected = []
                for d in range(256):
                    full = prefix = 0
                    for key, probability in enumerate(probabilities):
                        value = case.values[(key * 2 + head // 4) * 256 + d] << 16
                        full = word32(self.libm.fmaf(float32(probability), float32(value), float32(full)))
                        if key <= job.query_start + row:
                            prefix = word32(self.libm.fmaf(float32(probability), float32(value), float32(prefix)))
                    self.assertEqual(float32(full), float32(prefix))
                    if full != prefix:
                        # A future zero FMA may change -0 to +0. Retain the
                        # actual full-packet result, and admit only this exact
                        # numerical-equality exception in the filtered oracle.
                        self.assertEqual(full & 0x7fffffff, 0)
                        self.assertEqual(prefix & 0x7fffffff, 0)
                    expected.append(bf16(full) << 16)
                self.assertEqual(events['context_bf16', row, head, 0], tuple(expected))
                begin = (row * 8 + head) * 512
                self.assertEqual(driver.output.raw()[begin:begin + 512], pack([w >> 16 for w in expected]))
        expected_reads = job.tokens * 8 * 8 + 2 * 8 * job.cache_length * 8
        self.assertEqual(len(case.reads), expected_reads)
        for kv_head in range(2):
            for base in (job.cache_base, job.cache_v):
                self.assertIn(base + (job.cache_length - 1) * 1024 + kv_head * 512 + 7 * 64, case.reads)
        self.assertEqual(driver.owner.counts['matrix_results'], len(case.groups))
        self.assertEqual(driver.owner.counts['matrix_done'], len(case.groups))
        self.assertIsNone(driver.matrix.owner)
        self.assertIsNone(driver.scalar.client)

    def test_first_last_queries_without_prefix(self):
        self.assert_causal_trace(self.run_case(2, 0))

    def test_prefix_cache33_future_perturbation_and_signed_zero(self):
        before = self.run_case(2, 31)
        self.assert_causal_trace(before)
        after = self.run_case(2, 31, perturb=True)
        self.assert_causal_trace(after)
        # Only row 0 masks key 32; row 1 legitimately attends to the changed K/V.
        self.assertEqual(before.driver.output.raw()[:4096], after.driver.output.raw()[:4096])
        self.assertNotEqual(before.driver.output.raw()[4096:], after.driver.output.raw()[4096:])
        for case in (before, after):
            for head in range(8):
                raw = case.driver.output.raw()[head * 512:head * 512 + 4]
                self.assertEqual(raw, pack([0x8000, 0x0000]))
            row0 = [e for e in case.observed if e[0] == 'row_max_fp32' and e[1] == 0]
            self.assertEqual([e[4] for e in row0], [(0xbf800000,)] * 8)

    def test_single_last_query_cache33_partial_key_tile(self):
        self.assert_causal_trace(self.run_case(1, 32, policy=o.QkOrder.LegacyAscending))

    def test_future_zero_fma_keeps_numerical_equality_and_zero_sign_evidence(self):
        positive = self.run_case(2, 1, zero_witness=True)
        negative = self.run_case(2, 1, zero_witness=True, perturb=True)
        for case in (positive, negative):
            self.assert_causal_trace(case)
        for head in range(8):
            begin = head * 512
            a = positive.driver.output.raw()[begin:begin + 2]
            b = negative.driver.output.raw()[begin:begin + 2]
            self.assertEqual(a, pack([0x0000]))
            self.assertEqual(b, pack([0x8000]))
            self.assertNotEqual(a, b)
        # Every first-row component is numerically zero in both transactions;
        # the raw output retains, rather than erases, the d0 sign difference.
        for case in (positive, negative):
            context = [event for event in case.observed if event[0] == 'context_bf16' and event[1] == 0]
            self.assertEqual(len(context), 8)
            self.assertTrue(all(word & 0x7fffffff == 0 for event in context for word in event[4]))

    def test_future_nonfinite_input_still_fails_closed(self):
        for invalid in (('query', 0x7fc1), ('key', 0x7f80), ('value', 0xff80)):
            with self.subTest(invalid=invalid):
                case = self.run_case(2, 0, invalid=invalid)
                self.assertEqual((case.driver.response.status, case.driver.response.attention_status),
                                 ('Numerical', 1))
                self.assertFalse(case.driver.output.published)
                self.assertIsNone(case.driver.matrix.owner)
                self.assertIsNone(case.driver.scalar.client)

    def test_empty_or_invalid_range_rejected_before_dma(self):
        matrix, scalar, memory = self.resources()
        owner = o.Bf16CausalGqaOwner(matrix, scalar)
        valid = o.Bf16CausalGqaJob(1, 0x100000000, 0x200000000, 0x300000000, 2, 31, 33)
        for changes in (dict(tokens=0), dict(tokens=-1), dict(cache_length=0),
                        dict(query_start=-1), dict(query_start=30), dict(query_start=32),
                        dict(tokens=34), dict(query_start=True)):
            with self.subTest(changes=changes), \
                    patch.object(memory, 'exact', wraps=memory.exact) as resolve, \
                    patch.object(memory, 'read64', wraps=memory.read64) as read:
                with self.assertRaises(ValueError):
                    TypedBf16CausalGqaDriver(owner, memory, replace(valid, **changes))
                resolve.assert_not_called()
                read.assert_not_called()
                self.assertIsNone(owner.job)
                self.assertIsNone(matrix.owner)
                self.assertIsNone(scalar.client)
                self.assertFalse(scalar.calls)
        # The descriptor represents a suffix of a nonempty staged cache.
        # Every admitted row therefore has 1..cache_length causal keys;
        # there is no all-mask/empty-row or arbitrary-mask descriptor.
        for tokens, prefix in ((1, 0), (2, 0), (2, 31), (1, 255), (128, 128)):
            job = replace(valid, tokens=tokens, query_start=prefix, cache_length=prefix + tokens)
            job.validate()
            for row in range(tokens):
                self.assertLessEqual(1, job.query_start + row + 1)
                self.assertLessEqual(job.query_start + row + 1, job.cache_length)


if __name__ == '__main__':
    unittest.main()
