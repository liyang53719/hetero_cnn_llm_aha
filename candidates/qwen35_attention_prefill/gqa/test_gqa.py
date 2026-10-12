"""Small model-only GQA gates using an explicitly supplied existing library.

Never compile, search for a library, fetch weights, or run an official M16/M128
fixture. The synthetic tile-boundary case uses M17/cache33. QK uses independent
libm.fmaf checks and a cancellation witness. The
constant-score end-to-end test has hand-computable softmax/PV results. Test
producer bytes reach the exact TypedMemory through actual data/ACK/terminal.
"""
import ctypes as C
from dataclasses import replace
import os
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.build_shared_matrix_recipe import from_environment
from ...qwen2_resident_matrix.ffn_attention.matrix_service import (
    MatrixService, LegacyMatrixClient, LegacyRequest, configure_library,
)
from ...qwen2_resident_matrix.transposed_down.model import WriteCommand, WriteAck
from ...qwen35_gdn_prefill.typed_dense import TypedMemory
from ..norm_rope.scalar import NormRopeScalar
from . import owner as o
from .driver import TypedBf16CausalGqaDriver


def pack(words):
    return struct.pack('<' + 'H' * len(words), *words)


def producer(memory, base, raw, tag):
    region = memory.allocate_output(base, len(raw))
    for offset in range(0, len(raw), 64):
        sequence = (tag << 32) | (offset // 64)
        memory.begin_write(WriteCommand(base + offset, 1, sequence))
        memory.write_data(struct.unpack('<32H', raw[offset:offset + 64]), True)
        memory.acknowledge(WriteAck(sequence, False, 64))
    memory.publish(base, (tag, None, len(raw)))
    return region


def float32(bits):
    return struct.unpack('<f', struct.pack('<I', bits))[0]


def word32(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


class DescriptorTests(unittest.TestCase):
    def test_capacity_reservation_and_named_policy(self):
        job = o.Bf16CausalGqaJob(7, 0x100000000, 0x200000000, 0x300000000, 2, 1, 3)
        job.validate()
        self.assertEqual(job.cache_v - job.cache_base, 256 * 1024)
        self.assertEqual(job.input_spans[1][1], 3072)
        for bad in (replace(job, output=job.cache_base + 100 * 1024),
                    replace(job, query_start=0), replace(job, qk_policy='pair_high_first'),
                    replace(job, head_dim=128), replace(job, tokens=True)):
            with self.assertRaises(ValueError):
                bad.validate()


class GqaModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Missing environment or changed compile/source identity is a failure,
        # never a skipped green suite and never a request to build a library.
        path = from_environment(o.ROOT)
        cls.lib = configure_library(C.CDLL(str(path)))
        cls.libm = C.CDLL('libm.so.6')
        cls.libm.fmaf.argtypes = (C.c_float, C.c_float, C.c_float)
        cls.libm.fmaf.restype = C.c_float

    def setUp(self):
        self.assertEqual(self.lib.td_reset(), 0)
        self.matrix, self.scalar = MatrixService(self.lib), NormRopeScalar()
        self.memory = TypedMemory()

    def case(self, tokens=2, prefix=0, *, policy=o.QkOrder.PairHighFirst, witness=False,
             observer=None, query_word=0, key_word=0, offset=0, owner=None, constant_values=False):
        job = o.Bf16CausalGqaJob(71 + offset // 0x100000, 0x100000000 + offset,
                                0x200000000 + offset, 0x300000000 + offset,
                                tokens, prefix, prefix + tokens, qk_policy=policy)
        query = [query_word] * (tokens * 8 * 256)
        keys = [key_word] * (job.cache_length * 2 * 256)
        values = []
        # Increasing integer token values keep expected uniform PV simple.
        for token in range(job.cache_length):
            for head in range(2):
                word = word32(float(2 * (1 if constant_values else token + 1) + head)) >> 16
                values.extend([word] * 256)
        if witness:
            query[:4] = [0x3f80, 0, 0x4580, 0xc580]  # 1,0,4096,-4096
            keys[:4] = [0x3f80, 0, 0x4580, 0x4580]
        for index, ((base, _), raw) in enumerate(zip(job.input_spans, (pack(query), pack(keys), pack(values)))):
            producer(self.memory, base, raw, index + 1)
        self.memory.allocate_output(job.output, job.write_bytes)
        owner = o.Bf16CausalGqaOwner(self.matrix, self.scalar, observer) if owner is None else owner
        driver = TypedBf16CausalGqaDriver(owner, self.memory, job)
        return driver, query, keys, values

    def until(self, driver, predicate, control=None, *, max_ticks=20000):
        for tick in range(max_ticks):
            if predicate(driver):
                return
            driver.tick(**({} if control is None else control(driver, tick)))
        self.fail('small GQA transaction exceeded software tick bound')

    def finish(self, driver, control=None):
        self.until(driver, lambda d: d.response is not None, control)
        return driver.response

    def cancel(self, driver):
        driver.tick(abort=True)
        self.finish(driver)
        self.assertFalse(driver.output.published)
        self.assertEqual(driver.response.status, 'Aborted')
        self.assertTrue(driver.owner.poison)
        self.assertIsNone(self.matrix.owner)

    def oracle(self, query, keys, row, key, policy):
        result = 0
        for index in range(256):
            d = index ^ 1 if policy is o.QkOrder.PairHighFirst else index
            result = word32(self.libm.fmaf(float32(query[row * 8 * 256 + d] << 16),
                                          float32(keys[key * 2 * 256 + d] << 16), float32(result)))
        return ((result + 0x7fff + ((result >> 16) & 1)) >> 16) & 0xffff

    def test_minimum_qk_pair_order_actual_result_done_and_abort(self):
        for policy in o.QkOrder:
            with self.subTest(policy=policy):
                self.setUp()
                driver, query, keys, _ = self.case(prefix=1, witness=True, policy=policy)
                with patch.object(self.matrix, 'accept_step', wraps=self.matrix.accept_step) as steps:
                    self.until(driver, lambda d: d.owner.state == 'result')
                    held = self.matrix.result
                    self.assertIsNotNone(held)
                    raw = held.value.raw
                    for _ in range(3):
                        driver.tick(matrix_result_ready=False)
                        self.assertIs(self.matrix.result, held)
                        self.assertEqual(self.matrix.result.value.raw, raw)
                        self.assertEqual(driver.owner.counts['matrix_results'], 0)
                    self.until(driver, lambda d: d.owner.state == 'done',
                               lambda *_: dict(matrix_done_ready=False))
                    self.assertIsNone(self.matrix.result)
                    self.assertEqual(driver.owner.counts['matrix_results'], 1)
                    self.assertEqual(driver.owner.counts['matrix_done'], 0)
                    for _ in range(2):
                        driver.tick(matrix_done_ready=False)
                        self.assertEqual(driver.owner.counts['scalar_requests'], 0)
                    driver.tick()
                    self.assertEqual(driver.owner.counts['matrix_done'], 1)
                    self.assertEqual(self.matrix.counts['legacy_replies'], 0)
                    for row in range(2):
                        for key in range(3):
                            self.assertEqual(driver.owner.qk[row * 32 + key],
                                             self.oracle(query, keys, row, key, policy))
                    self.assertEqual(driver.owner.qk[0], 0x3f80 if policy is o.QkOrder.PairHighFirst else 0)
                    self.assertEqual(len(steps.call_args_list), 256)
                    for index, call in enumerate(steps.call_args_list):
                        step = call.args[1]
                        d = index ^ 1 if policy is o.QkOrder.PairHighFirst else index
                        self.assertEqual((step.index, step.context), (index, 0))
                        self.assertEqual(step.a[0], query[d])
                        self.assertEqual(step.b[0], keys[d])
                        self.assertEqual(step.clear, index == 0)
                        self.assertEqual((step.last, step.finish, step.emit), (index == 255,) * 3)
                        self.assertEqual(step.a[2:], (0,) * 14)
                        self.assertEqual(step.b[3:], (0,) * 253)
                self.cancel(driver)

    def test_constant_scores_causal_softmax_pv_and_final_ack_fence(self):
        observed = []
        driver, _, _, _ = self.case(observer=lambda *event: observed.append(event))
        self.until(driver, lambda d: d.pending is not None and d.owner.request.write and
                   d.counts['write_bytes'] == d.job.write_bytes)
        self.assertFalse(driver.output.published)
        self.assertEqual(driver.counts['ack_bytes'], driver.job.write_bytes - 64)
        for _ in range(3):
            driver.tick(memory_response_ready=False)
            self.assertFalse(driver.output.published)
            self.assertIsNone(driver.response)
        driver.tick(response_ready=False)
        self.assertEqual(driver.owner.state, 'finish')
        held = driver.owner.result
        for _ in range(3):
            driver.tick(response_ready=False)
            self.assertIs(driver.owner.result, held)
            self.assertFalse(driver.output.published)
        self.finish(driver)
        self.assertIsNone(driver.response.status)
        self.assertTrue(driver.output.published)
        words = struct.unpack('<' + 'H' * (driver.job.write_bytes // 2), driver.output.raw())
        for token in range(2):
            for head in range(8):
                expected = word32(float(2 + token + head // 4)) >> 16
                start = token * 2048 + head * 256
                self.assertEqual(words[start:start + 256], (expected,) * 256)
        probabilities = [event for event in observed if event[0] == 'probabilities_bf16']
        self.assertEqual(len(probabilities), 16)
        for _, token, _, _, raw in probabilities:
            self.assertEqual(raw, (0x3f800000, 0) if token == 0 else (0x3f000000, 0x3f000000))
        fp32_probabilities = [event for event in observed if event[0] == 'probability_fp32']
        self.assertEqual(len(fp32_probabilities), 32)
        for _, token, _, key, raw in fp32_probabilities:
            self.assertEqual(raw, ((0x3f800000 if key == 0 else 0),) if token == 0 else (0x3f000000,))
        self.assertEqual(driver.owner.counts['qk_groups'], 8)
        self.assertEqual(driver.owner.counts['pv_groups'], 8)
        self.assertEqual(driver.owner.counts['matrix_results'], 16)
        self.assertEqual(driver.owner.counts['matrix_done'], 16)
        self.assertEqual(self.matrix.counts['legacy_replies'], 0)
        self.assertIsNone(self.scalar.client)
        self.assertIsNone(self.matrix.owner)

    def test_abort_held_matrix_result_and_joint_reset(self):
        driver, *_ = self.case(tokens=1)
        self.until(driver, lambda d: d.owner.state == 'result')
        held = self.matrix.result
        driver.tick(abort=True, matrix_result_ready=False, matrix_done_ready=False)
        for _ in range(3):
            driver.tick(matrix_result_ready=False, matrix_done_ready=False)
            self.assertIs(self.matrix.result, held)
            self.assertIsNone(driver.response)
        driver.tick(matrix_done_ready=False)
        self.assertIsNone(self.matrix.result)
        self.assertIsNotNone(self.matrix.done)
        self.assertIsNone(driver.response)
        self.finish(driver)
        self.assertEqual(driver.response.status, 'Aborted')
        self.assertFalse(driver.output.published)
        with self.assertRaises(ValueError):
            driver.owner.reset()
        self.matrix.reset()
        driver.owner.reset()
        self.assertTrue(driver.owner.ports()['job_ready'])

    def test_same_instances_legacy_dense_gqa_and_back_without_reset(self):
        address, epoch = self.matrix.resource_address, self.matrix.epoch

        def finish_owner(client):
            self.matrix.retire_owner_response(client)
            self.matrix.release(client)

        def legacy(tag):
            client_owner = object()
            self.assertTrue(self.matrix.acquire(client_owner, 'normal', tag))
            client = LegacyMatrixClient(self.matrix, client_owner)
            for index in range(8):
                request = LegacyRequest(0x23, (0x3f80,) * 16, (0x3f80,) * 256,
                                        index == 0, index == 7, 8)
                self.assertTrue(client.tick(request=request)['request_fire'])
                for _ in range(20):
                    if client.ports()['result'] is not None:
                        break
                    client.tick()
                else:
                    self.fail('legacy Matrix client did not return')
                response = client.ports()['result']
                self.assertFalse(response.error)
                self.assertEqual(response.value[0][0], word32(float(index + 1)))
                self.assertTrue(client.tick(result_ready=True)['result_fire'])
            finish_owner(client_owner)

        def dense(tag):
            client_owner = object()
            self.assertTrue(self.matrix.acquire(client_owner, 'dense', tag))
            adapter = self.matrix.dense_library(client_owner)
            self.assertEqual(adapter.td_group(0, 16, 1), 0)
            output = (C.c_uint32 * 4096)()
            for index in range(16):
                last = index == 15
                self.assertEqual(adapter.td_step(index, 0, index == 0, last, last, last,
                    (C.c_uint16 * 16)(), (C.c_uint16 * 256)(), output), int(last))
            self.assertFalse(any(output))
            result = SimpleNamespace(context=0, last=True, error=False,
                                     value=tuple(tuple(output[r * 256:(r + 1) * 256]) for r in range(16)))
            adapter.retire_result(result)
            adapter.retire_done(SimpleNamespace(tag=tag, error=False))
            finish_owner(client_owner)

        legacy(100)
        dense(101)
        first, *_ = self.case(tokens=1)
        self.finish(first)
        self.assertIsNone(first.response.status)
        legacy(102)
        dense(103)
        second, *_ = self.case(tokens=1, offset=0x100000, owner=first.owner)
        self.finish(second)
        self.assertIsNone(second.response.status)
        self.assertIs(first.memory, second.memory)
        self.assertIs(first.owner, second.owner)
        self.assertIs(first.owner.scalar, self.scalar)
        self.assertEqual((self.matrix.resource_address, self.matrix.epoch), (address, epoch))
        self.assertEqual(self.matrix.counts['owner_acquires'], 6)
        self.assertEqual(self.matrix.counts['owner_responses'], 6)
        self.assertEqual(self.matrix.counts['owner_releases'], 6)
        self.assertEqual(self.matrix.counts['legacy_replies'], 16)
        self.assertEqual(first.output.raw(), second.output.raw())

    def test_read_and_final_ack_errors_never_publish(self):
        driver, *_ = self.case(tokens=1)
        self.until(driver, lambda d: d.pending is not None)
        driver.tick(read_error=True)
        self.finish(driver)
        self.assertEqual(driver.response.status, 'Memory')
        self.assertFalse(driver.output.published)
        self.setUp()
        driver, *_ = self.case(tokens=1)
        self.until(driver, lambda d: d.pending is not None and d.owner.request.write and
                   d.counts['write_bytes'] == d.job.write_bytes)
        driver.tick(ack_error=True)
        self.finish(driver)
        self.assertEqual(driver.response.status, 'Memory')
        self.assertEqual(driver.response.write_bytes, driver.job.write_bytes - 64)
        self.assertFalse(driver.output.published)

    def test_early_matrix_done_during_stalled_pv_read_drains(self):
        driver, *_ = self.case(tokens=1)
        self.until(driver, lambda d: d.owner.counts['pv_groups'] == 1 and
                   d.owner.state == 'memory_issue')
        reads = driver.owner.counts['read_requests']
        # External service fault exposes actual error-done without a result.
        self.matrix.abort(driver.owner)
        driver.tick(memory_ready=False, matrix_done_ready=False)
        self.assertEqual(driver.owner.state, 'drain')
        self.assertEqual(driver.owner.counts['read_requests'], reads)
        self.assertIsNone(driver.owner.ports()['memory'])
        self.finish(driver, lambda *_: dict(memory_ready=False))
        self.assertEqual(driver.response.status, 'Protocol')
        self.assertFalse(driver.output.published)

    def test_nonfinite_input_and_unsupported_unmasked_difference(self):
        driver, *_ = self.case(tokens=1, query_word=0x7f80)
        self.finish(driver)
        self.assertEqual((driver.response.status, driver.response.attention_status), ('Numerical', 1))
        self.assertEqual(driver.owner.counts['matrix_steps'], 0)
        self.setUp()
        # Producer bytes are fixed before driver admission, never patched
        # into an admitted source or injected as arithmetic intermediates.
        memory = self.memory
        job = o.Bf16CausalGqaJob(72, 0x100000000, 0x200000000, 0x300000000, 1, 1, 2)
        raw_q = pack([0x3f80] * 2048)
        raw_k = pack([0] * 512 + [0x40a0] * 512)  # scaled scores 0 and 80 exactly
        raw_v = pack([0x3f80] * 1024)
        for tag, ((base, _), raw) in enumerate(zip(job.input_spans, (raw_q, raw_k, raw_v)), 1):
            producer(memory, base, raw, tag)
        memory.allocate_output(job.output, job.write_bytes)
        owner = o.Bf16CausalGqaOwner(self.matrix, self.scalar)
        driver = TypedBf16CausalGqaDriver(owner, memory, job)
        self.finish(driver)
        self.assertEqual((driver.response.status, driver.response.attention_status), ('Unsupported', 3))
        self.assertFalse(driver.output.published)

    def test_descriptor_source_and_producer_coverage_rejections(self):
        driver, *_ = self.case(tokens=1)
        query = driver.inputs[0]
        query.storage[64] ^= 1
        with self.assertRaises(ValueError):
            driver.tick()
        self.cancel(driver)

    def test_source_guard_and_coverage_failure_drain_accepted_read(self):
        for mutation in ('guard', 'coverage'):
            with self.subTest(mutation=mutation):
                self.setUp()
                driver, *_ = self.case(tokens=1)
                self.until(driver, lambda d: d.pending is not None)
                request = driver.owner.request
                self.assertFalse(request.write)
                if mutation == 'guard':
                    driver.inputs[0].storage[0] ^= 1
                else:
                    driver.inputs[0].acknowledged.remove(0)
                with self.assertRaises(ValueError):
                    driver.tick(memory_response_ready=False)
                driver.tick(abort=True, memory_response_ready=False)
                self.assertIs(driver.owner.request, request)
                self.assertIsNotNone(driver.pending)
                self.assertIsNone(driver.response)
                self.finish(driver)
                self.assertEqual(driver.response.status, 'Aborted')
                self.assertIsNone(driver.pending)
                self.assertIsNone(driver.memory.pending)
                self.assertFalse(driver.output.published)

    def test_source_corruption_drain_final_accepted_write(self):
        driver, *_ = self.case(tokens=1)
        self.until(driver, lambda d: d.pending is not None and d.owner.request.write and
                   d.counts['write_bytes'] == d.job.write_bytes)
        driver.inputs[1].storage[64] ^= 1
        with self.assertRaises(ValueError):
            driver.tick(memory_response_ready=False)
        driver.tick(abort=True, memory_response_ready=False)
        self.assertIsNotNone(driver.memory.pending)
        self.assertIsNone(driver.response)
        self.finish(driver)
        self.assertEqual(driver.response.status, 'Aborted')
        self.assertEqual(driver.response.write_bytes, driver.job.write_bytes)
        self.assertFalse(driver.output.published)
        self.assertIsNone(driver.memory.pending)

    def test_mutated_held_matrix_payload_fails_and_drains(self):
        driver, *_ = self.case(tokens=2)
        self.until(driver, lambda d: d.owner.state == 'result')
        driver.tick(matrix_result_ready=False)
        held = self.matrix.result
        raw = held.value.raw
        # Deliberate frozen-dataclass bypass tests the integrity fence. The
        # immutable Matrix snapshot is never legitimately writable by a client.
        object.__setattr__(held.value, 'raw', bytes([raw[0] ^ 1]) + raw[1:])
        self.finish(driver)
        self.assertEqual(driver.response.status, 'Protocol')
        self.assertFalse(driver.output.published)
        self.assertIsNone(self.matrix.result)
        self.assertIsNone(self.matrix.done)

    def test_matrix_fault_revokes_held_success_before_acceptance(self):
        for ready_on_fault in (False, True):
            with self.subTest(ready_on_fault=ready_on_fault):
                self.setUp()
                driver, *_ = self.case(tokens=1)
                self.until(driver, lambda d: d.owner.state == 'finish',
                           lambda *_: dict(response_ready=False))
                driver.tick(response_ready=False)  # Freeze the actual held success.
                old = driver.owner.result
                self.assertIsNone(old.status)
                self.assertFalse(driver.output.published)
                self.matrix.abort(driver.owner)
                event = driver.tick(response_ready=ready_on_fault)
                self.assertFalse(event['response_fire'])
                self.assertIsNone(driver.response)
                self.assertFalse(driver.output.published)
                failed = driver.owner.result
                self.assertIsNot(failed, old)
                self.assertEqual(failed.status, 'Protocol')
                for _ in range(3):
                    driver.tick(response_ready=False)
                    self.assertIs(driver.owner.result, failed)
                self.finish(driver)
                self.assertIs(driver.response, failed)
                self.assertFalse(driver.output.published)
                self.assertEqual(driver.owner.counts['owner_results'], 1)
                self.assertEqual(self.matrix.counts['owner_responses'], 1)
                self.assertEqual(self.matrix.counts['owner_releases'], 1)
                self.assertIsNone(self.matrix.owner)
                self.assertIsNone(self.scalar.client)
                with self.assertRaises(ValueError):
                    driver.owner.reset()
                self.matrix.reset()
                driver.owner.reset()
                self.assertTrue(driver.owner.ports()['job_ready'])

    def test_matrix_fault_with_final_ack_pending_drains_once(self):
        for accept_ack_on_fault in (False, True):
            with self.subTest(accept_ack_on_fault=accept_ack_on_fault):
                self.setUp()
                driver, *_ = self.case(tokens=1)
                self.until(driver, lambda d: d.pending is not None and d.owner.request.write and
                           d.counts['write_bytes'] == d.job.write_bytes)
                request = driver.owner.request
                self.matrix.abort(driver.owner)
                event = driver.tick(memory_response_ready=accept_ack_on_fault, response_ready=True)
                self.assertFalse(event['response_fire'])
                self.assertFalse(driver.output.published)
                if not accept_ack_on_fault:
                    self.assertEqual(driver.owner.state, 'drain')
                    self.assertIs(driver.owner.request, request)
                    self.assertIsNotNone(driver.memory.pending)
                self.finish(driver)
                self.assertEqual(driver.response.status, 'Protocol')
                self.assertEqual(driver.response.write_bytes, driver.job.write_bytes)
                self.assertFalse(driver.output.published)
                self.assertIsNone(driver.pending)
                self.assertIsNone(driver.memory.pending)
                self.assertEqual(driver.owner.counts['owner_results'], 1)
                self.assertEqual(self.matrix.counts['owner_releases'], 1)
                self.matrix.reset()
                driver.owner.reset()
                self.assertTrue(driver.owner.ports()['job_ready'])

    def test_terminal_drift_rejected_and_accepted_success_cannot_be_revoked(self):
        driver, *_ = self.case(tokens=1)
        self.until(driver, lambda d: d.owner.state == 'finish', lambda *_: dict(response_ready=False))
        driver.tick(response_ready=False)
        held = driver.owner.result
        driver.owner.result = replace(held, status='Protocol', output_committed=False)
        with self.assertRaises(ValueError):
            driver.tick(response_ready=False)
        self.assertFalse(driver.output.published)
        driver.owner.result = held
        self.finish(driver)
        self.assertIs(driver.response, held)
        self.assertTrue(driver.output.published)
        another = object()
        self.assertTrue(self.matrix.acquire(another, 'normal', driver.job.tag))
        self.matrix.abort(another)
        with self.assertRaises(ValueError):
            driver.tick(abort=True)
        self.assertIs(driver.response, held)
        self.assertTrue(driver.output.published)
        self.matrix.retire_owner_response(another)
        self.matrix.release(another)

    def test_old_epoch_held_terminal_cannot_alias_reacquired_owner(self):
        driver, *_ = self.case(tokens=1)
        self.until(driver, lambda d: d.owner.state == 'finish', lambda *_: dict(response_ready=False))
        driver.tick(response_ready=False)
        # Deliberately reset outside the required joint protocol, then reuse
        # even the same Python owner/tag. The old driver must reject the epoch.
        self.matrix.reset()
        self.assertTrue(self.matrix.acquire(driver.owner, 'normal', driver.job.tag))
        self.matrix.abort(driver.owner)
        with self.assertRaises(ValueError):
            driver.tick(abort=True)
        self.assertIsNone(driver.response)
        self.assertFalse(driver.output.published)
        self.matrix.retire_owner_response(driver.owner)
        self.matrix.release(driver.owner)

    def test_held_matrix_done_requires_exact_types_and_stability(self):
        for field, replacement in (('error', 0), ('epoch', False), ('tag', 999)):
            with self.subTest(field=field):
                self.setUp()
                driver, *_ = self.case(tokens=1)
                self.until(driver, lambda d: d.owner.state == 'done',
                           lambda *_: dict(matrix_done_ready=False))
                driver.tick(matrix_done_ready=False)
                held = self.matrix.done
                object.__setattr__(held, field, replacement)
                driver.tick(matrix_done_ready=False)
                self.assertEqual(driver.owner.state, 'drain')
                self.assertEqual(driver.owner.counts['scalar_requests'], 0)
                self.assertIsNone(driver.response)
                self.finish(driver)
                self.assertEqual(driver.response.status, 'Protocol')
                self.assertFalse(driver.output.published)
                self.assertEqual(driver.owner.counts['owner_results'], 1)
                self.assertIsNone(self.matrix.owner)

    def test_synthetic_m17_cache33_crosses_both_tile_boundaries(self):
        driver, *_ = self.case(tokens=17, prefix=16, constant_values=True)
        with patch.object(self.memory, 'read64', wraps=self.memory.read64) as reads:
            self.until(driver, lambda d: d.response is not None, max_ticks=100000)
        self.assertIsNone(driver.response.status)
        self.assertTrue(driver.output.published)
        words = struct.unpack('<' + 'H' * (driver.job.write_bytes // 2), driver.output.raw())
        for token in range(17):
            allowed = 17 + token
            fp32_probability = word32(1.0 / allowed)
            probability = ((fp32_probability + 0x7fff + ((fp32_probability >> 16) & 1)) >> 16) & 0xffff
            for head in range(8):
                # Independent source-order FMA over the quantized BF16
                # probability; do not assume rounded probabilities sum to 1.
                value = word32(float(2 + head // 4))
                accumulator = 0
                for key in range(33):
                    operand = probability << 16 if key < allowed else 0
                    accumulator = word32(self.libm.fmaf(float32(operand), float32(value), float32(accumulator)))
                expected = ((accumulator + 0x7fff + ((accumulator >> 16) & 1)) >> 16) & 0xffff
                start = token * 2048 + head * 256
                self.assertEqual(words[start:start + 256], (expected,) * 256)
        self.assertEqual(driver.owner.counts['qk_groups'], 2 * 8 * 2)
        self.assertEqual(driver.owner.counts['pv_groups'], 2 * 8)
        self.assertEqual(driver.owner.counts['matrix_results'], 48)
        self.assertEqual(driver.owner.counts['matrix_done'], 48)
        expected_reads = 17 * 8 * 8 + 2 * 8 * 33 * 8 + 2 * 8 * 33 * 8
        self.assertEqual(reads.call_count, expected_reads)
        # Last Q token and final K tile/V key must be fetched from the actual
        # published physical regions for both KV heads.
        addresses = {call.args[0] for call in reads.call_args_list}
        for head in range(8):
            self.assertIn(driver.job.query_input + 16 * 4096 + head * 512 + 7 * 64, addresses)
        for head in range(2):
            self.assertIn(driver.job.cache_base + 32 * 1024 + head * 512 + 7 * 64, addresses)
            self.assertIn(driver.job.cache_v + 32 * 1024 + head * 512 + 7 * 64, addresses)


if __name__ == '__main__':
    unittest.main()
