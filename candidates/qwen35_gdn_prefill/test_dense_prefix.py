"""Bounded actual-C++ two-chunk transport tests; no build, checkpoint, or RTL.

Requires the same explicit MATRIX_SERVICE_LIBRARY and source-fresh compile
receipt as test_typed_dense. CI supplies its freshly built shared recipe.
These K160/K256, M16 fixtures do not execute full K3584/M128 or claim 80 rows.
"""
from dataclasses import replace
import struct
import time
import unittest

from . import dense_prefix as p
from . import test_typed_dense as numeric
from . import typed_dense as t
from ..qwen2_resident_matrix.ffn_attention.matrix_service import LegacyMatrixClient, LegacyRequest, MatrixProtocolError


def setUpModule():
    numeric.setUpModule()


class TypedSeededDenseTests(numeric.DenseTerminalAbortCases, unittest.TestCase):
    def setUp(self):
        self.assertEqual(numeric.LIB.td_reset(), 0)
        self.matrix = p.MatrixService(numeric.LIB)
        self.owner = p.down.DenseOwnerModel(p.down.PrefixWorkspace(0x900000, 5 * 16384, 7, 128))
        self.memory = p.TypedMemory()

    def prepare(self, *, n=32, k=256, tag=55, base=0x10000, prefix=True, raw_a=None, raw_b=None):
        a, b, dst = base, base + 0x10000, base + 0x40000
        self.memory.add_readonly(a, numeric.values(16 * k) if raw_a is None else raw_a)
        self.memory.add_readonly(b, numeric.values(k * n, 2) if raw_b is None else raw_b)
        self.memory.allocate_output(dst, 16 * n * 2)
        if prefix and self.owner.workspace.base not in self.memory.regions:
            self.memory.allocate_output(self.owner.workspace.base, self.owner.workspace.extent)
        return p.down.Job(m=16, k=k, n=n, tag=tag, a=a, b=b, dst=dst,
                          output_bf16=True, write_bytes=16 * n * 2)

    def driver(self, job):
        return p.TypedSeededDenseDriver(self.owner, self.matrix, self.memory, job)

    def until(self, driver, predicate, **kwargs):
        deadline = time.monotonic() + 15
        for _ in range(100000):
            if predicate():
                return
            self.assertLess(time.monotonic(), deadline, 'small Dense wall budget')
            driver.tick(**kwargs)
        self.fail('small Dense tick budget')

    def finish(self, driver, hook=None):
        deadline = time.monotonic() + 15
        for i in range(100000):
            if driver.response is not None:
                return driver.report()
            self.assertLess(time.monotonic(), deadline, 'small Dense wall budget')
            driver.tick(**({} if hook is None else hook(driver, i)))
        self.fail('small Dense tick budget')

    def assert_blocked(self, driver):
        self.assertFalse(driver.output.published)
        self.assertFalse(driver.prefix.published)
        self.assertIsNone(driver.response)
        with self.assertRaises(ValueError):
            self.memory.read64(driver.job.dst)
        with self.assertRaises(ValueError):
            self.memory.read64(self.owner.workspace.base)
        with self.assertRaises(MatrixProtocolError):
            self.matrix.release(self.owner)
        self.assertFalse(self.matrix.acquire(self.owner, 'normal', 99))

    def test_same_resources_single_dense_seeded_five_contexts_single_dense_then_legacy(self):
        identity = (id(self.owner), id(self.owner.a_banks), id(self.owner.b_banks), self.matrix.resource_address)
        first = self.prepare(k=32, tag=50, prefix=False)
        d = t.TypedDenseDriver(self.owner, self.matrix, self.memory, first)
        self.finish(d)
        first_raw = d.output.raw()
        self.assertEqual(first_raw, numeric.oracle(d.a.raw(), d.b.raw(), 16, 32, 32))

        job = self.prepare(n=160, base=0x100000)
        seeded = self.driver(job)
        report = self.finish(seeded, lambda _, i: dict(read_ready=i % 3 != 0,
            read_response_ready=i % 4 != 0, step_ready=i % 5 != 0, result_ready=i % 7 != 0,
            done_ready=i % 3 != 0, write_ready=i % 4 != 0, data_ready=i % 5 != 0,
            ack_ready=i % 6 != 0, seed_begin_ready=i % 4 != 0, seed_beat_ready=i % 3 != 0,
            seed_ack_ready=i % 5 != 0))
        self.assertEqual(seeded.response, (job.tag, None, 5120))
        self.assertEqual(seeded.output.raw(), numeric.oracle(seeded.a.raw(), seeded.b.raw(), 16, 256, 160))
        self.assertEqual(report['executed_fmas'], 256 * 5 * 4096)
        self.assertEqual(report['counts']['seed_begins'], 5)
        self.assertEqual(report['counts']['seed_acks'], 5)
        self.assertEqual(report['counts']['seed_beats'], 5 * 256)
        self.assertEqual(report['counts']['prefix_ack_bytes'], 5 * 16384)
        self.assertEqual(report['groups'], [(0, 0, 5, 0, 128), (1, 0, 5, 128, 256)])
        self.assertLessEqual(report['counts']['peak_results'], 2)
        self.assertFalse(seeded.prefix.published)
        seeded_raw = seeded.output.raw()
        prefix_raw = seeded.prefix.raw()

        last = self.prepare(k=32, tag=56, base=0x200000, prefix=False)
        old = t.TypedDenseDriver(self.owner, self.matrix, self.memory, last)
        self.finish(old)
        self.assertEqual(old.output.raw(), numeric.oracle(old.a.raw(), old.b.raw(), 16, 32, 32))
        self.assertEqual(old.owner.prefix_bytes, 0)
        self.assertEqual(d.output.raw(), first_raw)
        self.assertEqual(seeded.output.raw(), seeded_raw)
        self.assertEqual(seeded.prefix.raw(), prefix_raw)

        # The original normal/legacy client also reacquires the exact array.
        self.assertTrue(self.matrix.acquire(self.owner, 'normal', 88))
        client = LegacyMatrixClient(self.matrix, self.owner)
        request = LegacyRequest(0x24, (0x3f80,) * 16, (0x3f80,) * 32 + (0,) * 224,
                                True, True, 1)
        self.assertTrue(client.tick(request=request)['request_fire'])
        for _ in range(16):
            if client.ports()['result'] is not None:
                break
            client.tick()
        result = client.ports()['result']
        self.assertIsNotNone(result)
        self.assertFalse(result.error)
        self.assertEqual(tuple(tuple(row) for row in result.value),
                         ((0x3f800000,) * 32 + (0,) * 224,) * 16)
        self.assertTrue(client.tick(result_ready=True)['result_fire'])
        self.matrix.retire_owner_response(self.owner)
        self.matrix.release(self.owner)
        self.assertEqual(numeric.LIB.matrix_normal_fmas(), 16 * 32)
        self.assertEqual(self.matrix.counts['owner_acquires'], 4)
        self.assertEqual(self.matrix.counts['owner_releases'], 4)
        self.assertEqual(self.matrix.counts['dense_seed_acks'], 5)
        self.assertEqual(seeded.report()['executed_fmas'], report['executed_fmas'])
        self.assertEqual(self.matrix.epoch, 0)
        self.assertEqual(identity, (id(self.owner), id(self.owner.a_banks), id(self.owner.b_banks),
                                    self.matrix.resource_address))

    def test_n32_short_second_chunk_preserves_fp32_prefix_and_padding(self):
        # 1 + 127/1024 is not BF16-exact. Rounding the prefix to 1.125
        # before the second chunk's -1.125 would wrongly produce zero.
        k, n = 160, 32
        self.owner.workspace = p.down.PrefixWorkspace(0x900000, 16384 + 64, 7, 128)
        raw_a = struct.pack('<' + 'H' * (16 * k), *([0x3f80] * (16 * k)))
        column = [0x3f80] + [0x3a80] * 127 + [0xbf90] + [0] * 31
        raw_b = struct.pack('<' + 'H' * (k * n), *(v for v in column for _ in range(n)))
        job = self.prepare(k=k, n=n, raw_a=raw_a, raw_b=raw_b)
        padding = self.memory.regions[self.owner.workspace.base].raw()[-64:]
        d = self.driver(job)
        self.finish(d)
        self.assertEqual(d.output.raw(), numeric.oracle(raw_a, raw_b, 16, k, n))
        self.assertEqual(struct.unpack('<512H', d.output.raw()), (0xba80,) * 512)
        self.assertEqual(d.prefix.raw()[-64:], padding)
        physical_prefix = struct.unpack('<4096I', d.prefix.raw()[:16384])
        expected_prefix = struct.unpack('<I', struct.pack('<f', 1 + 127 / 1024))[0]
        for row in range(16):
            for col in range(32):
                r, c = p.down.output_coordinate(row, col)
                self.assertEqual(physical_prefix[r * 256 + c], expected_prefix)
        self.assertTrue(any(word & 0xffff for word in physical_prefix))
        self.assertEqual(d.prefix.acknowledged, set(range(0, 16384, 64)))
        with self.assertRaises(ValueError):
            self.memory.read64(d.prefix.base)
        with self.assertRaises(ValueError):
            self.memory.exact(d.prefix.base, d.prefix.extent, readable=True)

    def test_held_prefix_ack_seed_begin_beat_ack_result_done_and_terminal(self):
        d = self.driver(self.prepare())
        self.until(d, lambda: d.pending_ack is not None and
                   d.counts['prefix_write_data_bytes'] == d.prefix_extent)
        for _ in range(5):
            d.tick(ack_ready=False)
            self.assertEqual(self.owner.chunk_index, 0)
            self.assertEqual(d.counts['prefix_ack_bytes'], d.prefix_extent - 64)
            self.assertEqual(d.counts['seed_begins'], 0)
            self.assertFalse(d.output.written)
            self.assert_blocked(d)
        self.until(d, lambda: self.owner.ports()['seed_begin'] is not None)
        for _ in range(5):
            d.tick(seed_begin_ready=False)
            self.assertEqual(d.counts['steps'], 128)
            self.assert_blocked(d)
        self.until(d, lambda: self.owner.ports()['seed_beat'] is not None)
        held = self.owner.ports()['seed_beat']
        for _ in range(5):
            d.tick(seed_beat_ready=False)
            self.assertEqual(self.owner.ports()['seed_beat'], held)
            self.assertEqual(d.counts['steps'], 128)
            self.assert_blocked(d)
        self.until(d, lambda: d.pending_seed_ack is not None)
        for _ in range(5):
            d.tick(seed_ack_ready=False)
            self.assertEqual(d.counts['steps'], 128)
            self.assertTrue(numeric.LIB.matrix_state() & 64)
            self.assert_blocked(d)
        self.until(d, lambda: bool(d.results), result_ready=False)
        held = d.results[0]
        for _ in range(5):
            d.tick(result_ready=False)
            self.assertEqual(d.results[0], held)
            self.assertTrue(numeric.LIB.matrix_state() & 8)
            self.assertEqual(d.counts['done'], 1)
            self.assert_blocked(d)
        self.until(d, lambda: d.output.acknowledged == set(range(0, d.job.write_bytes, 64)),
                   done_ready=False)
        for _ in range(5):
            d.tick(done_ready=False)
            self.assertEqual(d.counts['done'], 1)
            self.assert_blocked(d)
        self.until(d, lambda: self.owner.ports()['response'] is not None, response_ready=False)
        held = self.owner.ports()['response']
        for _ in range(5):
            d.tick(response_ready=False)
            self.assertEqual(self.owner.ports()['response'], held)
            self.assert_blocked(d)
        d.tick()
        self.assertTrue(d.output.published)
        self.assertFalse(d.prefix.published)
        self.assertIsNone(self.matrix.owner)
        self.assertEqual(self.matrix.counts['owner_responses'], 1)

    def test_final_output_ack_is_a_publication_fence(self):
        d = self.driver(self.prepare())
        self.until(d, lambda: d.pending_ack is not None and
                   d.counts['write_data_bytes'] == d.job.write_bytes)
        for _ in range(7):
            d.tick(ack_ready=False)
            self.assertEqual(d.counts['ack_bytes'], d.job.write_bytes - 64)
            self.assert_blocked(d)
        self.finish(d)
        self.assertEqual(d.response, (d.job.tag, None, d.job.write_bytes))
        self.assertTrue(d.output.published)

    def test_two_n_windows_finish_prior_sweep_before_any_restore(self):
        self.owner.workspace = replace(self.owner.workspace, extent=6 * 16384)
        d = self.driver(self.prepare(n=192, k=160))
        self.finish(d)
        self.assertEqual(d.groups, [(0, 0, 5, 0, 128), (0, 160, 1, 0, 128),
                                    (1, 0, 5, 128, 160), (1, 160, 1, 128, 160)])
        self.assertEqual(d.counts['done'], 4)
        self.assertEqual(d.counts['seed_acks'], 6)
        self.assertEqual(d.output.raw(), numeric.oracle(d.a.raw(), d.b.raw(), 16, 160, 192))
        self.assertEqual(d.prefix.acknowledged, set(range(0, 6 * 16384, 64)))
        self.assertFalse(d.prefix.published)

    def test_actual_second_chunk_overflow_drains_without_fabricated_final_result(self):
        k, n = 256, 32
        row = [0x3f80] * 128 + [0x7f7f] * 128
        raw_a = struct.pack('<4096H', *(row * 16))
        raw_b = struct.pack('<8192H', *(v for v in row for _ in range(n)))
        d = self.driver(self.prepare(k=k, n=n, raw_a=raw_a, raw_b=raw_b))
        self.finish(d)
        self.assertIsNotNone(d.numeric_fault)
        self.assertIsNotNone(d.response[1])
        self.assertEqual(d.counts['seed_acks'], 1)
        self.assertEqual(d.counts['results'], 1)
        self.assertEqual(d.counts['write_data_bytes'], 0)
        self.assertFalse(d.output.published)
        self.assertFalse(d.prefix.published)
        self.assertIsNone(self.matrix.owner)
        self.assertTrue(self.matrix.reset_required)

    def test_prefix_and_final_write_ack_errors_lock_without_publication(self):
        for phase in ('prefix', 'final'):
            with self.subTest(phase=phase):
                self.setUp()
                d = self.driver(self.prepare())
                field = 'prefix_write_data_bytes' if phase == 'prefix' else 'write_data_bytes'
                extent = d.prefix_extent if phase == 'prefix' else d.job.write_bytes
                self.until(d, lambda: d.pending_ack is not None and d.counts[field] == extent)
                d.tick(ack_error=True)
                self.finish(d)
                self.assertIsNotNone(d.response[1])
                self.assertFalse(d.output.published)
                self.assertFalse(d.prefix.published)
                self.assertEqual(self.owner.state, 'locked')
                self.assertTrue(self.matrix.reset_required)
                self.assertIsNone(self.matrix.owner)

    def test_seed_error_ack_retires_real_obligation_and_locks(self):
        d = self.driver(self.prepare())
        self.until(d, lambda: d.pending_seed_ack is not None)
        d.tick(seed_ack_error=True)
        self.finish(d)
        self.assertEqual(d.counts['seed_errors'], 1)
        self.assertEqual(self.matrix.counts['dense_seed_acks'], 1)
        self.assertEqual(d.counts['steps'], 128)
        self.assertEqual(d.counts['write_data_bytes'], 0)
        self.assertFalse(numeric.LIB.matrix_state() & 64)
        self.assertIsNotNone(d.response[1])
        self.assertFalse(d.output.published)
        self.assertEqual(self.owner.state, 'locked')
        self.assertTrue(self.matrix.reset_required)
        self.assertIsNone(self.matrix.owner)
        with self.assertRaises(ValueError):
            self.driver(d.job)

    def test_abort_drains_partial_seed_and_other_owned_obligations_without_reset(self):
        for phase in ('read', 'prefix_write', 'seed_begin', 'prefix_read', 'seed_mid', 'seed_ack', 'result', 'final_write'):
            with self.subTest(phase=phase):
                self.setUp()
                d = self.driver(self.prepare())
                predicate = {
                    'read': lambda: d.pending_read is not None,
                    'prefix_write': lambda: self.memory.pending is not None and self.memory.pending[1] is d.prefix,
                    'seed_begin': lambda: d.active_seed is not None,
                    'prefix_read': lambda: d._pending_prefix_read is not None,
                    'seed_mid': lambda: d.counts['seed_beats'] == 11,
                    'seed_ack': lambda: d.pending_seed_ack is not None,
                    'result': lambda: bool(d.results) and self.owner.chunk_index == 1,
                    'final_write': lambda: self.memory.pending is not None and self.memory.pending[1] is d.output,
                }[phase]
                self.until(d, predicate)
                d.tick(abort=True, read_response_ready=False, result_ready=False,
                       ack_ready=False, seed_ack_ready=False, done_ready=False)
                self.assert_blocked(d)
                self.finish(d)
                self.assertIsNotNone(d.response[1])
                self.assertFalse(d.output.published)
                self.assertFalse(d.prefix.published)
                self.assertIsNone(d.pending_read)
                self.assertIsNone(d.pending_ack)
                self.assertIsNone(d.pending_seed_ack)
                self.assertIsNone(d.active_seed)
                self.assertIsNone(self.memory.pending)
                self.assertFalse(d.results)
                self.assertIsNone(self.matrix.owner)
                self.assertEqual(self.owner.state, 'locked')
                self.assertTrue(self.matrix.reset_required)
                self.assertEqual(self.matrix.counts['aborts'], 1)
                self.assertEqual(self.matrix.epoch, 0)
                self.assertFalse(numeric.LIB.matrix_state() & (4 | 8 | 64 | 128))
                other = self.prepare(k=32, prefix=False, tag=72, base=0x200000)
                with self.assertRaises(ValueError):
                    t.TypedDenseDriver(self.owner, self.matrix, self.memory, other)
                self.assertFalse(self.matrix.acquire(self.owner, 'normal', 73))
                # Reset is an explicit caller action after all transport drains.
                bank_identity = (id(self.owner.a_banks), id(self.owner.b_banks), self.matrix.resource_address)
                self.owner.tick(coordinated_reset=True)
                self.matrix.reset()
                old = t.TypedDenseDriver(self.owner, self.matrix, self.memory, other)
                self.finish(old)
                self.assertEqual(self.matrix.epoch, 1)
                self.assertEqual(bank_identity, (id(self.owner.a_banks), id(self.owner.b_banks), self.matrix.resource_address))

    def test_bounds_exact_workspace_alias_and_private_or_stale_sources_rejected(self):
        job = self.prepare()
        for bad in (replace(job, k=128), replace(job, k=288), replace(job, activation_bf16=False),
                    replace(job, output_bf16=False), replace(job, write_bytes=2048), replace(job, dst=job.a)):
            with self.subTest(job=bad), self.assertRaises(ValueError):
                self.driver(bad)
        workspace = self.owner.workspace
        for bad in (replace(workspace, extent=16320), replace(workspace, extent=workspace.extent + 64),
                    replace(workspace, base=job.a), replace(workspace, generation=0),
                    replace(workspace, split_k=64)):
            self.owner.workspace = bad
            with self.subTest(workspace=bad), self.assertRaises(ValueError):
                self.driver(job)
        self.owner.workspace = workspace
        with self.assertRaises(ValueError):
            self.memory.allocate_output(workspace.base + 64, 64)
        self.assertIsNone(self.matrix.owner)
        self.assertEqual(self.matrix.counts['owner_acquires'], 0)
        d = self.driver(job)
        self.finish(d)
        # Even an otherwise complete prefix is private and cannot become A/W.
        with self.assertRaises(ValueError):
            self.memory.read64(workspace.base)
        with self.assertRaises(ValueError):
            self.memory.exact(workspace.base, workspace.extent, readable=True)
        next_job = self.prepare(base=0x200000, tag=71)
        with self.assertRaisesRegex(ValueError, 'fresh unpublished staging'):
            self.driver(next_job)
        self.assertIsNone(self.matrix.owner)

    def test_stale_prefix_receipt_and_changed_held_read_rejected(self):
        d = self.driver(self.prepare())
        self.until(d, lambda: d._pending_prefix_read is not None)
        command, _ = d._pending_prefix_read
        offset = command.address - d.prefix.base
        saved = d._prefix_receipts[offset]
        d._prefix_receipts[offset] = ((d.job.tag, 6, 0, 1, 128), saved[1])
        with self.assertRaisesRegex(ValueError, 'stale or changed ACKed prefix'):
            d.tick()
        self.assertEqual(d.counts['seed_beats'], 0)
        d._prefix_receipts[offset] = saved
        d.prefix.storage[64 + offset] ^= 1
        with self.assertRaisesRegex(ValueError, 'stale or changed ACKed prefix'):
            d.tick()
        self.assert_blocked(d)
        d.prefix.storage[64 + offset] ^= 1
        # A fresh descriptor cannot be forged from an arbitrary private read.
        with self.assertRaisesRegex(ValueError, 'exact accepted descriptor'):
            d._prefix_bytes(replace(command, address=command.address + 64))
        self.finish(d)
        self.assertTrue(d.output.published)
        with self.assertRaises(ValueError):
            d._prefix_bytes(command)


if __name__ == '__main__':
    unittest.main()
