"""Actual small C++ Matrix/Vector projection transactions, never checkpoints.

Existing MATRIX_SERVICE_LIBRARY/COMPILE_RECEIPT and GDN_VECTOR16_LIBRARY are
required explicitly. Tests never compile or search for numerical libraries.
"""
import ctypes as C
import ctypes.util
import ast
import inspect
from dataclasses import replace
import os
from pathlib import Path
import struct
import time
import textwrap
import unittest
from unittest.mock import patch

from . import typed_dense as t
from .dense_prefix import TypedSeededDenseDriver
from . import projection_owner as p
from .projection_driver import TypedProjectionDriver, GDN_PROJECTION_PROFILE, SharedVector16Loan
from .chunk.vector import Vector16, IEEE_POLICY
from ..qwen2_resident_matrix.dense_block_reduce.profile import ReductionProfile
from ..qwen2_resident_matrix.ffn_attention.matrix_service import configure_library

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ReductionProfile('synthetic_k32_two16_pair_reverse', ((0, 16), (16, 32)), True, '0' * 64)
LIB = LIBM = VECTOR_PATH = None


def setUpModule():
    global LIB, LIBM, VECTOR_PATH
    LIB = configure_library(C.CDLL(str(t.library_from_environment(ROOT))))
    VECTOR_PATH = Path(os.environ['GDN_VECTOR16_LIBRARY']).resolve(strict=True)
    LIBM = C.CDLL(ctypes.util.find_library('m') or 'libm.so.6')
    LIBM.fmaf.argtypes, LIBM.fmaf.restype = [C.c_float] * 3, C.c_float


def values(count, salt=0):
    basis = (0x3e83, 0xbe47, 0x3f07, 0xbf13, 0x3d8b, 0x0080, 0x0001)
    return struct.pack('<' + 'H' * count, *(basis[(i * 3 + i // 7 + salt) % len(basis)] for i in range(count)))


def fp(word):
    return struct.unpack('<f', struct.pack('<I', word))[0]


def oracle(a_raw, b_raw, m, k, n, ranges=None, pair_reverse=False):
    """Logical row-major oracle, only called after actual accepted terminal."""
    aa = struct.unpack('<' + 'H' * (m * k), a_raw)
    bb = struct.unpack('<' + 'H' * (k * n), b_raw)
    words = []
    for row in range(m):
        for col in range(n):
            partials = []
            for begin, end in ranges or ((0, k),):
                total = 0.0
                for ordinal in range(end - begin):
                    depth = begin + (ordinal ^ int(pair_reverse))
                    total = LIBM.fmaf(fp(aa[row * k + depth] << 16), fp(bb[depth * n + col] << 16), total)
                partials.append(total)
            value = partials[0] if len(partials) == 1 else partials[0] + partials[1]
            bits = struct.unpack('<I', struct.pack('<f', value))[0]
            words.append(p.down.bf16_rne(bits))
    return struct.pack('<' + 'H' * len(words), *words)


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(LIB.td_reset(), 0)
        self.matrix = t.MatrixService(LIB)
        self.vector = Vector16(VECTOR_PATH, exception_policy=IEEE_POLICY)
        self.owner = p.GdnProjectionOwner(p.PrefixWorkspace(0x900000, 16384, 1, 128))
        self.memory = t.TypedMemory()

    def prepare(self, n=32, k=32, m=16, tag=41, a=0x10000, b=0x20000, dst=0x60000):
        if a not in self.memory.regions:
            self.memory.add_readonly(a, values(m * k))
        self.memory.add_readonly(b, values(k * n, 2))
        self.memory.allocate_output(dst, m * n * 2)
        return t.down.Job(m=m, k=k, n=n, tag=tag, a=a, b=b, dst=dst,
            activation_bf16=True, weight_bf16=True, output_bf16=True, write_bytes=m * n * 2)

    def driver(self, job):
        return TypedProjectionDriver(self.owner, self.matrix, self.memory, job,
            vector=self.vector, role='synthetic', profile=PROFILE)

    def finish(self, driver, hook=None):
        deadline = time.monotonic() + 25
        for tick in range(200000):
            self.assertLess(time.monotonic(), deadline, 'bounded actual projection transaction')
            driver.tick(**({} if hook is None else hook(driver, tick)))
            if driver.response is not None:
                return driver.report()
        self.fail('projection did not retire')

    def until(self, driver, predicate, **controls):
        deadline = time.monotonic() + 20
        while not predicate():
            self.assertLess(time.monotonic(), deadline, 'bounded projection edge search')
            driver.tick(**controls)
            self.assertIsNone(driver.response)

    def identity(self):
        return (id(self.owner), id(self.owner.a_banks), id(self.owner.b_banks),
                id(self.owner.tiles.banks), self.matrix.resource_address,
                id(self.vector), self.vector.resource_address, self.matrix.epoch)

    def test_actual_n32_n160_n192_same_physical_resources(self):
        for n in (32, 160, 192):
            with self.subTest(n=n):
                self.setUp()
                d = self.driver(self.prepare(n=n))
                identity = self.identity()
                report = self.finish(d, lambda _, i: dict(read_ready=i % 3 != 0,
                    read_response_ready=i % 4 != 0, step_ready=i % 5 != 0,
                    result_ready=i % 7 != 0, done_ready=i % 3 != 0,
                    write_ready=i % 4 != 0, data_ready=i % 5 != 0, ack_ready=i % 6 != 0))
                self.assertEqual(d.response, (41, None, 16 * n * 2))
                self.assertEqual(d.output.raw(), oracle(d.a.raw(), d.b.raw(), 16, 32, n, PROFILE.ranges, True))
                self.assertEqual(report['executed_fmas'], 32 * (n // 32) * 4096)
                self.assertEqual(report['vector_add_calls'], n)
                self.assertEqual(report['vector_add_lanes'], n * 16)
                self.assertEqual(report['a_load_fences'], 1)
                self.assertEqual(report['counts']['a_read_beats'], 16)
                self.assertEqual(report['counts']['b_read_beats'], n)
                self.assertEqual(report['counts']['ack_bytes'], 16 * n * 2)
                self.assertEqual(len(report['partials']), 2 * ((n + 159) // 160))
                self.assertEqual(self.identity(), identity)
                self.assertTrue(d.output.published)
                self.assertIsNone(self.vector.client)

    def test_full_n6144_bf16_shape_uses_real_destination_extent(self):
        # A legal workspace follows BF16 D immediately; a fake FP32 D fails.
        j = p.Job(m=16, k=1024, n=6144, tag=7, a=0x100000,
            b=0x400000, dst=0x2000000, output_bf16=True, write_bytes=16 * 6144 * 2)
        q = p.GdnReductionRequest(j, 8, GDN_PROJECTION_PROFILE.ranges, True)
        q.validate()
        w = p.PrefixWorkspace(j.dst + j.write_bytes, 16384, 1)
        w.validate(j)
        with self.assertRaises(ValueError):
            w.validate(replace(j, output_bf16=False, write_bytes=j.write_bytes * 2))
        for bad in (replace(j, write_bytes=j.write_bytes * 2), replace(j, output_bf16=False),
                    replace(j, b=j.a), replace(j, materialize_dense_output=True)):
            with self.assertRaises(ValueError):
                replace(q, job=bad).validate()

    def test_actual_projection_then_ordinary_then_seeded_down_without_reset(self):
        self.memory.allocate_output(self.owner.workspace.base, self.owner.workspace.extent)
        identity = self.identity()
        first = self.driver(self.prepare())
        self.finish(first)
        first_report = first.report()
        second_job = self.prepare(n=256, tag=42, a=first.job.dst, b=0x30000, dst=0x70000)
        second = t.TypedDenseDriver(self.owner, self.matrix, self.memory, second_job)
        self.finish(second)
        self.assertEqual(second.output.raw(), oracle(first.output.raw(), second.b.raw(), 16, 32, 256))
        third_job = self.prepare(k=256, tag=43, a=second.job.dst, b=0x40000, dst=0x80000)
        third = TypedSeededDenseDriver(self.owner, self.matrix, self.memory, third_job)
        self.finish(third)
        self.assertEqual(third.output.raw(), oracle(second.output.raw(), third.b.raw(), 16, 256, 32))
        self.assertEqual(self.identity(), identity)
        self.assertEqual(self.matrix.epoch, 0)
        self.assertEqual(self.matrix.counts['owner_acquires'], 4)
        self.assertGreater(third.counts['seed_acks'], 0)
        self.assertEqual(first.report(), first_report)

    def test_final_ack_and_held_success_do_not_publish(self):
        d = self.driver(self.prepare(n=192))
        self.until(d, lambda: d.pending_ack is not None and d.counts['write_data_bytes'] == d.job.write_bytes)
        for _ in range(5):
            d.tick(ack_ready=False)
            self.assertFalse(d.output.published)
            self.assertIsNone(d.response)
        self.until(d, lambda: d.coordinator.ports(d.services())['result'] is not None, response_ready=False)
        held = d.coordinator.result
        for _ in range(5):
            d.tick(response_ready=False)
            self.assertEqual(d.coordinator.result, held)
            self.assertFalse(d.output.published)
        d.tick()
        self.assertTrue(d.output.published)

    def test_abort_held_success_is_failed_once_and_requires_reset(self):
        d = self.driver(self.prepare())
        self.until(d, lambda: d.coordinator.ports(d.services())['result'] is not None, response_ready=False)
        self.assertFalse(d.tick(abort=True)['result_fire'])
        self.finish(d, lambda *_: dict(abort=True))
        self.assertIsNotNone(d.response[1])
        self.assertFalse(d.output.published)
        self.assertIsNone(self.matrix.owner)
        self.assertIsNone(self.vector.client)
        with self.assertRaises(ValueError):
            d.tick()
        identity = self.identity()[:-1]
        self.owner.tick(coordinated_reset=True)
        self.matrix.reset()
        self.assertEqual(self.identity()[:-1], identity)
        self.assertFalse(d.output.published)
        recovered = self.driver(self.prepare(tag=42, b=0x30000, dst=0x70000))
        self.finish(recovered)
        self.assertEqual(recovered.response[1], None)
        self.assertTrue(recovered.output.published)
        self.assertFalse(d.output.published)

    def test_abort_during_read_matrix_result_sum_and_final_ack_drains(self):
        points = ('read', 'result', 'sum', 'data', 'ack')
        for point in points:
            with self.subTest(point=point):
                self.setUp()
                d = self.driver(self.prepare())
                predicate = {'read': lambda: d.pending_read is not None,
                    'result': lambda: bool(d.results),
                    'sum': lambda: d.loan.result is not None,
                    'data': lambda: self.owner.ports()['write_data'] is not None and
                        d.counts['write_data_bytes'] + 64 == d.job.write_bytes,
                    'ack': lambda: d.pending_ack is not None and d.counts['write_data_bytes'] == d.job.write_bytes}[point]
                self.until(d, predicate)
                if point == 'data':
                    for _ in range(3):
                        d.tick(abort=True, data_ready=False)
                        self.assertIsNone(d.response)
                        self.assertIsNotNone(self.memory.pending)
                self.finish(d, lambda *_: dict(abort=True))
                self.assertIsNotNone(d.response[1])
                self.assertFalse(d.output.published)
                self.assertIsNone(d.pending_read)
                self.assertIsNone(d.pending_ack)
                self.assertFalse(d.results)
                self.assertIsNone(self.memory.pending)
                self.assertIsNone(self.matrix.owner)
                self.assertIsNone(self.vector.client)

    def test_failed_real_ack_credits_no_bytes_and_does_not_publish(self):
        d = self.driver(self.prepare())
        self.until(d, lambda: d.pending_ack is not None)
        d.tick(ack_error=True)
        self.finish(d)
        self.assertIsNotNone(d.response[1])
        self.assertEqual(d.response[2], 0)
        self.assertFalse(d.output.published)
        self.assertFalse(d.output.acknowledged)

    def test_unsolicited_late_result_poison_cannot_accept_held_success(self):
        d = self.driver(self.prepare())
        self.until(d, lambda: d.coordinator.ports(d.services())['result'] is not None, response_ready=False)
        # A real owner interface response with no accepted outstanding request.
        self.owner.tick(result=p.down.MatrixResult(0, ((0,) * 256,) * 16))
        self.finish(d)
        self.assertIsNotNone(d.response[1])
        self.assertFalse(d.output.published)

    def test_fp32_partial_may_exceed_bf16_before_cancellation(self):
        owner = self.owner
        job = p.Job(m=16, k=32, n=32, output_bf16=True, write_bytes=1024)
        owner.job = job
        owner.window_request = p.GdnKWindowRequest(job, 1, 0, 32, 0,
            k_begin=0, k_end=16, block_id=1)
        owner.contexts = 1
        owner.results_received = 0
        raw = [[0] * 256 for _ in range(16)]
        for m in range(16):
            for n in range(32):
                row, col = p.down.output_coordinate(m, n)
                raw[row][col] = 0x7f7fffff
        owner._receive_result(p.down.MatrixResult(0, raw), {0})
        self.assertIsNone(owner.error)
        self.assertIs(owner.final_value, raw)

    def test_vector_loan_uses_existing_resource_and_real_overflow_error(self):
        from ..qwen2_resident_matrix.dense_block_reduce.vector_add_model import Request
        loan = SharedVector16Loan(self.vector)
        address = self.vector.resource_address
        self.assertTrue(loan.tick(request=Request((0x7f7fffff,) * 16, (0x7f7fffff,) * 16))['request_fire'])
        self.assertTrue(loan.ports()['result'].error)
        self.assertEqual(loan.fault['operation'], 'add')
        self.assertTrue(loan.tick(result_ready=True)['result_fire'])
        self.assertTrue(loan.poison)
        self.assertTrue(loan.ports()['drained'])
        self.assertIsNone(self.vector.client)
        self.assertEqual(self.vector.resource_address, address)

    def test_actual_sum_and_terminal_bf16_overflow_fail_without_publication(self):
        for name, aword, second_weight in (('vector', 0x7f00, 0x3f80),
                                          ('bf16', 0x7f7f, 0x3b01), ('matrix', 0x7f00, 0)):
            with self.subTest(name=name):
                self.setUp()
                a = struct.pack('<H', aword) * (16 * 32)
                b = [0] * (32 * 32)
                for n in range(32):
                    b[n] = 0x7f00 if name == 'matrix' else 0x3f80
                    b[16 * 32 + n] = second_weight
                self.memory.add_readonly(0x10000, a)
                self.memory.add_readonly(0x20000, struct.pack('<1024H', *b))
                self.memory.allocate_output(0x60000, 1024)
                j = t.down.Job(m=16, k=32, n=32, tag=42, a=0x10000, b=0x20000,
                    dst=0x60000, output_bf16=True, write_bytes=1024)
                d = self.driver(j)
                self.finish(d)
                self.assertIsNotNone(d.response[1])
                self.assertEqual(d.response[2], 0)
                self.assertFalse(d.output.published)
                self.assertFalse(d.output.written)
                self.assertIsNone(self.vector.client)
                if name == 'vector':
                    self.assertIsNotNone(d.loan.fault)
                elif name == 'bf16':
                    self.assertIsNone(d.loan.fault)
                    self.assertEqual(self.owner.error, 'sum outside finite BF16 output domain')
                else:
                    self.assertIsNotNone(d.numeric_fault)
                    self.assertEqual(d.counts['matrix_aborts'], 1)

    def test_bf16_drain_specialization_preserves_frozen_lifecycle(self):
        expected = textwrap.dedent(inspect.getsource(p.drain.FfnDrainOwnerModel.tick))
        expected = expected.replace('def tick(', 'def _bf16_drain_tick(', 1)
        expected = expected.replace('q.job.m * q.cols * 4', 'q.job.m * q.cols * 2')
        expected = expected.replace('self.drain_request.cols // 16', 'self.drain_request.cols // 32')
        expected = expected.replace('self.job.m * self.drain_request.cols * 4',
                                    'self.job.m * self.drain_request.cols * 2')
        start = expected.index('        elif not self.error:\n            for lane, word in enumerate(r.words):')
        end = expected.index('    if te["ctl_fire"]:', start)
        body = expected[start:end].split('        elif not self.error:\n', 1)[1]
        guarded = ('        elif not self.error:\n'
            '            if any(not down.finite32(word) or (word & 0x7fffffff) >= 0x7f7f8000 for word in r.words):\n'
            '                self._fault("sum outside finite BF16 output domain")\n'
            '            else:\n' + ''.join('    ' + line if line.strip() else line for line in body.splitlines(True)))
        expected = expected[:start] + guarded + expected[end:]
        actual = textwrap.dedent(inspect.getsource(p.GdnProjectionOwner._bf16_drain_tick))
        self.assertEqual(ast.dump(ast.parse(actual), include_attributes=False),
                         ast.dump(ast.parse(expected), include_attributes=False))

    def test_production_roles_reject_changed_split_pair_order_and_provenance(self):
        j = t.down.Job(m=16, k=1024, n=6144, tag=7, a=0x100000,
            b=0x400000, dst=0x2000000, output_bf16=True, write_bytes=16 * 6144 * 2)
        for profile in (replace(GDN_PROJECTION_PROFILE, ranges=((0, 256), (256, 1024))),
                        replace(GDN_PROJECTION_PROFILE, pair_reverse=False),
                        replace(GDN_PROJECTION_PROFILE, source_sha256='1' * 64)):
            with self.assertRaisesRegex(ValueError, 'policy/profile mismatch'):
                TypedProjectionDriver(self.owner, self.matrix, self.memory, j,
                    vector=self.vector, role='qkv', profile=profile)
        self.assertIsNone(self.matrix.owner)
        self.assertIsNone(self.vector.client)

    def test_synthetic_m128_k128_n32_actual_two_partials(self):
        profile = replace(PROFILE, identity='synthetic_m128_k128', ranges=((0, 64), (64, 128)))
        j = self.prepare(m=128, k=128)
        d = TypedProjectionDriver(self.owner, self.matrix, self.memory, j,
            vector=self.vector, role='synthetic', profile=profile)
        report = self.finish(d)
        self.assertEqual(d.response, (j.tag, None, 8192))
        self.assertEqual(d.output.raw(), oracle(d.a.raw(), d.b.raw(), 128, 128, 32, profile.ranges, True))
        self.assertEqual(report['vector_add_calls'], 256)
        self.assertEqual(report['counts']['a_read_beats'], 512)
        self.assertEqual(report['executed_fmas'], 128 * 4096)

    def test_partial_checks_selected_nan_and_ignores_inactive_padding(self):
        for selected in (False, True):
            with self.subTest(selected=selected):
                self.setUp()
                owner = self.owner
                owner.job = p.Job(m=16, k=32, n=32, output_bf16=True, write_bytes=1024)
                owner.window_request = p.GdnKWindowRequest(owner.job, 1, 0, 32, 0,
                    k_begin=0, k_end=16, block_id=1)
                owner.contexts, owner.results_received = 1, 0
                raw = [[0] * 256 for _ in range(16)]
                raw[0][0 if selected else 16] = 0x7fc00000
                owner._receive_result(p.down.MatrixResult(0, raw), {0})
                if selected:
                    self.assertEqual(owner.error, 'nonfinite result')
                    self.assertIsNone(owner.final_value)
                else:
                    self.assertIsNone(owner.error)
                    self.assertIs(owner.final_value, raw)

    def test_ordinary_and_seeded_abort_keep_real_ack_obligations_after_projection(self):
        for mode in ('ordinary_final_ack', 'seeded_seed_ack'):
            with self.subTest(mode=mode):
                self.setUp()
                self.memory.allocate_output(self.owner.workspace.base, self.owner.workspace.extent)
                first = self.driver(self.prepare(n=32 if mode.startswith('ordinary') else 160))
                self.finish(first)
                identity = self.identity()
                if mode.startswith('ordinary'):
                    j = self.prepare(tag=42, a=first.job.dst, b=0x30000, dst=0x70000)
                    d = t.TypedDenseDriver(self.owner, self.matrix, self.memory, j)
                    self.until(d, lambda: d.pending_ack is not None and d.counts['write_data_bytes'] == j.write_bytes)
                    hold = dict(ack_ready=False)
                else:
                    j = self.prepare(k=160, tag=42, a=first.job.dst, b=0x30000, dst=0x70000)
                    d = TypedSeededDenseDriver(self.owner, self.matrix, self.memory, j)
                    self.until(d, lambda: d.pending_seed_ack is not None)
                    hold = dict(seed_ack_ready=False)
                for _ in range(4):
                    d.tick(abort=True, **hold)
                    self.assertIsNone(d.response)
                    self.assertIsNone(self.owner.ports()['response'])
                self.finish(d, lambda *_: dict(abort=True))
                self.assertIsNotNone(d.response[1])
                self.assertFalse(d.output.published)
                self.assertIsNone(self.matrix.owner)
                self.assertEqual(self.identity(), identity)

    def test_ordinary_and_seeded_held_success_reject_same_edge_unsolicited_responses(self):
        for mode in ('ordinary', 'seeded'):
            for fault in ('read_beat', 'result'):
                with self.subTest(mode=mode, fault=fault):
                    self.setUp()
                    self.memory.allocate_output(self.owner.workspace.base, self.owner.workspace.extent)
                    first = self.driver(self.prepare(n=32 if mode == 'ordinary' else 160))
                    self.finish(first)
                    j = self.prepare(k=32 if mode == 'ordinary' else 160, tag=42,
                        a=first.job.dst, b=0x30000, dst=0x70000)
                    cls = t.TypedDenseDriver if mode == 'ordinary' else TypedSeededDenseDriver
                    d = cls(self.owner, self.matrix, self.memory, j)
                    self.until(d, lambda: self.owner.ports()['response'] is not None, response_ready=False)
                    held = self.owner.ports()['response']
                    actual_tick = self.owner.tick
                    injected = (p.down.ReadBeat(0xdead, (0,) * 32, True) if fault == 'read_beat'
                                else p.down.MatrixResult(0, ((0,) * 256,) * 16))
                    def injection(**inputs):
                        return actual_tick(**dict(inputs, **{fault: injected}))
                    with patch.object(self.owner, 'tick', side_effect=injection):
                        edge = d.tick()
                    self.assertTrue(edge['response_fire'])
                    self.assertEqual(edge['response'], held)
                    self.assertEqual(d.response[1], 'Protocol')
                    self.assertFalse(d.output.published)
                    self.assertTrue(self.owner.ports()['reset_required'])
                    self.assertEqual(self.owner.state, 'locked')
                    self.assertIsNone(self.matrix.owner)


if __name__ == '__main__':
    unittest.main()
