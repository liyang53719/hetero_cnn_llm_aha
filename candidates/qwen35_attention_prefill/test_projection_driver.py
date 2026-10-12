"""Real shared-resource M16 prefix plus inexpensive admission/RMS fault gates.

No checkpoint, native model, replacement numerical owner, or compiler runs.
Existing MATRIX_SERVICE_LIBRARY/COMPILE_RECEIPT and GDN_VECTOR16_LIBRARY must
be explicit. Synthetic finite DATA retain all production shapes and policies.
The one full chain is bounded to 120 seconds; no full-shape fault repetitions.
"""
import ctypes as C
from dataclasses import FrozenInstanceError, replace
import os
from pathlib import Path
import time
import unittest

import numpy as np

from . import projection_driver as p
from ..qwen35_gdn_prefill.chunk.vector import IEEE_POLICY
from ..qwen35_gdn_prefill.prep.scalar import PrepScalar
from ..qwen35_gdn_prefill.projection_owner import PrefixWorkspace
from ..qwen35_gdn_prefill.projection_driver import GDN_PROJECTION_PROFILE
from ..qwen35_gdn_prefill.test_rms_owner import bf16, decode, oracle as rms_oracle
from ..qwen2_resident_matrix.ffn_attention.matrix_service import configure_library


ROOT = Path(__file__).resolve().parents[2]
LIB = VECTOR_PATH = None


def setUpModule():
    global LIB, VECTOR_PATH
    LIB = configure_library(C.CDLL(str(p.d.library_from_environment(ROOT))))
    VECTOR_PATH = Path(os.environ['GDN_VECTOR16_LIBRARY']).resolve(strict=True)


def sparse_weight(n, salt):
    """Exactly one finite BF16 term per independent K512 partial and column."""
    words = np.zeros((1024, n), dtype='<u2')
    columns = np.arange(n)
    first, second = (columns * 3 + salt) % 128, 512 + (columns * 5 + salt) % 128
    words[first, columns] = np.where(columns % 2, 0x3d80, 0x3d00)  # 1/16 or 1/32
    words[second, columns] = 0x3c80  # 1/64
    return words.tobytes()


def sparse_projection_oracle(normalized, raw_weight, rows, n):
    """Post-terminal independent logical oracle for this sparse DATA only.

    A BF16 product is exact in FP32; each block has one nonzero term, so its
    ordered FMA reduction equals that product. The block Add and BF16 RNE are
    explicit. No Matrix/Vector output is used to construct the expectation.
    """
    a, weight = decode(normalized, (rows, 1024)), decode(raw_weight, (1024, n))
    columns = np.arange(n)
    first, second = np.argmax(weight[:512] != 0, axis=0), 512 + np.argmax(weight[512:] != 0, axis=0)
    assert np.all(np.count_nonzero(weight[:512], axis=0) == 1)
    assert np.all(np.count_nonzero(weight[512:], axis=0) == 1)
    left = np.multiply(a[:, first], weight[first, columns], dtype=np.float32)
    right = np.multiply(a[:, second], weight[second, columns], dtype=np.float32)
    return bf16(np.add(left, right, dtype=np.float32)).tobytes()


class L3ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(LIB.td_reset(), 0)
        self.matrix = p.d.MatrixService(LIB)
        self.vector = p.Vector16(VECTOR_PATH, exception_policy=IEEE_POLICY)
        self.scalar = PrepScalar(enable_softplus=True)
        self.rms = p.rms.RmsOwner(self.scalar)
        self.dense = p.GdnProjectionOwner(PrefixWorkspace(0x2000000, 16384, 1))
        self.memory = p.d.TypedMemory()
        hidden = ((np.arange(16 * 1024).reshape(16, 1024) % 13 + 1) / 128).astype('<f4')
        self.hidden = bf16(hidden).tobytes()
        self.input_weight = bf16((np.arange(1024) % 5 / 256).astype('<f4')).tobytes()
        self.weights = {role: sparse_weight(n, index + 1)
                        for index, (role, (_, n)) in enumerate(p.SHAPES.items())}
        next_address = 0x10000

        def allocate(raw=None, extent=None):
            nonlocal next_address
            base = next_address
            region = (self.memory.add_readonly(base, raw) if raw is not None
                      else self.memory.allocate_output(base, extent))
            next_address += region.extent + 64
            return base

        plan = dict(tokens=16, hidden=allocate(self.hidden), input_weight=allocate(self.input_weight), tag_base=71)
        for role, raw in self.weights.items():
            plan[role + '_weight'] = allocate(raw)
        plan['input_norm'] = allocate(extent=16 * 2048)
        for role, (_, n) in p.SHAPES.items():
            plan[role] = allocate(extent=16 * n * 2)
        self.plan = p.L3ProjectionPlan(**plan)

    def coordinator(self, **changes):
        args = dict(memory=self.memory, dense=self.dense, matrix=self.matrix, vector=self.vector,
                    rms_owner=self.rms, plan=self.plan, profile=p.ATTENTION_PROJECTION_PROFILE)
        args.update(changes)
        return p.L3ProjectionCoordinator(**args)

    def until(self, c, predicate, *, deadline, hook=None):
        while not predicate():
            self.assertLess(time.monotonic(), deadline, 'bounded real prefix execution')
            self.assertIsNone(c.response)
            c.tick(**({} if hook is None else hook(c.ticks)))

    def assert_untouched(self, *roles):
        for role in roles:
            region = self.memory.regions[getattr(self.plan, role)]
            self.assertFalse(region.published)
            self.assertFalse(region.written)
            self.assertFalse(region.acknowledged)
            self.assertEqual(region.raw(), p.d.GUARD * (region.extent // 64))

    def test_actual_m16_full_shapes_shared_chain_and_final_fences(self):
        began = time.monotonic()
        deadline = began + 120
        c = self.coordinator()
        identity = c._resource_identity()
        self.assert_untouched(*p.ORDER)
        c.start()
        self.until(c, lambda: c.active.pending is not None and self.rms.request.write and
            c.active.counts['write_bytes'] == c.jobs[0].write_bytes, deadline=deadline)
        for _ in range(3):
            c.tick(ack_ready=False)
            self.assertFalse(c.active.output.published)
            self.assertEqual(c.role, 'input_norm')
            self.assertEqual(self.matrix.counts['owner_acquires'], 0)
            self.assert_untouched(*p.ORDER[1:])
        c.tick(response_ready=False)
        held = self.rms.ports()['response']
        self.assertIsNotNone(held)
        for _ in range(3):
            c.tick(response_ready=False)
            self.assertEqual(self.rms.ports()['response'], held)
            self.assertFalse(c.active.output.published)
            with self.assertRaises(ValueError):
                self.memory.read64(self.plan.input_norm)
        c.tick()
        self.assertIsNone(c.active)
        self.assertEqual(len(c.commands), 1)
        self.assertTrue(self.memory.regions[self.plan.input_norm].published)
        self.assertEqual(self.matrix.counts['owner_acquires'], 0)
        self.until(c, lambda: c.role == 'v' and c.active is not None and c.active.pending_ack is not None and
            c.active.counts['write_data_bytes'] == c.active.job.write_bytes, deadline=deadline,
            hook=lambda tick: dict(read_ready=tick % 13 != 0, read_response_ready=tick % 17 != 0,
                step_ready=tick % 19 != 0, result_ready=tick % 23 != 0,
                write_ready=tick % 29 != 0, data_ready=tick % 31 != 0))
        for _ in range(3):
            c.tick(ack_ready=False)
            self.assertFalse(c.active.output.published)
            self.assertIsNone(c.response)
            self.assertEqual(len(c.commands), 3)
        self.until(c, lambda: c.active.coordinator.ports(c.active.services())['result'] is not None,
                   deadline=deadline, hook=lambda _: dict(response_ready=False))
        held = c.active.coordinator.result
        for _ in range(3):
            c.tick(response_ready=False)
            self.assertEqual(c.active.coordinator.result, held)
            self.assertFalse(c.active.output.published)
            self.assertIsNone(c.response)
        event = c.tick()
        self.assertTrue(event['prefix_terminal_fire'])
        self.assertIsNone(c.response.status)
        self.assertEqual(c._resource_identity(), identity)
        self.assertEqual([command['role'] for command in c.commands], list(p.ORDER))
        self.assertEqual([command['job']['tag'] for command in c.commands], list(range(71, 75)))
        self.assertIsNone(self.memory.pending)
        self.assertIsNone(self.matrix.owner)
        self.assertIsNone(self.vector.client)
        self.assertIsNone(self.scalar.client)
        self.assertEqual(self.matrix.epoch, 0)
        report = c.report()
        self.assertTrue(report['fullprefix_success'])
        self.assertEqual(report['software_ticks'], sum(command['software_ticks'] for command in report['commands']))
        self.assertEqual(report['executed_fmas'], 1024 * (4096 + 512 + 512) // 32 * 4096)
        self.assertEqual(report['vector_add_calls'], 4096 + 512 + 512)
        self.assertEqual(report['vector_add_lanes'], 16 * (4096 + 512 + 512))
        self.assertEqual(report['acknowledged_write_bytes'], 16 * (1024 + 4096 + 512 + 512) * 2)
        for role, command in zip(p.ORDER, report['commands']):
            region = self.memory.regions[getattr(self.plan, role)]
            self.assertEqual(command['acknowledged_write_bytes'], region.extent)
            self.assertTrue(region.published)
        self.assertFalse(report['public_command128_executed'])
        self.assertFalse(report['chisel_executed'])
        self.assertFalse(report['rtl_executed'])
        self.assertFalse(report['native_acceptance'])
        self.assertIsNone(report['hardware_cycles'])
        normalized, _ = rms_oracle(self.hidden, self.input_weight, 16, c.rms_policy)
        self.assertEqual(self.memory.regions[self.plan.input_norm].raw(), normalized)
        for role, (_, n) in p.SHAPES.items():
            self.assertEqual(self.memory.regions[getattr(self.plan, role)].raw(),
                             sparse_projection_oracle(normalized, self.weights[role], 16, n))
        self.assertLess(time.monotonic() - began, 120)
        with self.assertRaises(ValueError):
            c.tick()
        with self.assertRaises(ValueError):
            c.start()
        report['commands'].clear()
        self.assertEqual(len(c.report()['commands']), 4)

    def test_preflight_requires_full_shape_profile_raw_inputs_and_sentinels(self):
        for plan in (replace(self.plan, tokens=8), replace(self.plan, tag_base=0),
                     replace(self.plan, tag_base=(1 << 32) - 3), replace(self.plan, v=self.plan.k)):
            with self.subTest(plan=plan), self.assertRaises(ValueError):
                self.coordinator(plan=plan)
        for profile in (GDN_PROJECTION_PROFILE, replace(p.ATTENTION_PROJECTION_PROFILE, identity='synthetic')):
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                self.coordinator(profile=profile)
        output = self.memory.regions[self.plan.input_norm]
        output.storage[64] ^= 1
        with self.assertRaisesRegex(ValueError, 'sentinels'):
            self.coordinator()
        output.storage[64] ^= 1
        weight = self.memory.regions[self.plan.k_weight]
        extent = weight.extent
        weight.extent = 1024 * 32 * 2
        with self.assertRaises(ValueError):
            self.coordinator()
        weight.extent = extent
        source = self.memory.regions[self.plan.hidden]
        source.readonly = False
        source.acknowledged = set(range(0, source.extent, 64))
        with self.assertRaisesRegex(ValueError, 'readonly'):
            self.coordinator()
        self.assertTrue(self.rms.ports()['job_ready'])
        self.assertEqual(self.matrix.counts['owner_acquires'], 0)

    def test_immutable_plan_epoch_resource_storage_and_job_bindings(self):
        c = self.coordinator()
        with self.assertRaises(FrozenInstanceError):
            self.plan.tag_base = 19
        c.plan = replace(self.plan)
        with self.assertRaisesRegex(ValueError, 'binding'):
            c.start()
        c.plan = self.plan
        self.matrix.epoch += 1
        with self.assertRaisesRegex(ValueError, 'epoch'):
            c.start()
        self.matrix.epoch -= 1
        region = self.memory.regions[self.plan.v]
        storage = region.storage
        region.storage = bytearray(storage)
        with self.assertRaisesRegex(ValueError, 'storage'):
            c.start()
        region.storage = storage
        words = self.dense.a_banks.words[0]
        self.dense.a_banks.words[0] = list(words)
        with self.assertRaisesRegex(ValueError, 'binding'):
            c.start()
        self.dense.a_banks.words[0] = words
        c.start()
        job = c.active.job
        c.active.job = replace(job)
        with self.assertRaisesRegex(ValueError, 'transport/job'):
            c.tick()
        c.active.job = job
        self.rms.job = replace(job)
        with self.assertRaisesRegex(ValueError, 'transport/job'):
            c.tick()
        self.rms.job = job
        c.tick(abort=True, response_ready=False)
        self.assertIsNone(c.response)
        c.tick()
        self.assertEqual(c.response.status, 'Aborted')
        self.assertTrue(c.locked)
        self.assert_untouched(*p.ORDER)

    def test_actual_rms_read_error_holds_failed_terminal_and_prevents_dense(self):
        c = self.coordinator()
        c.start()
        c.tick()
        self.assertIsNotNone(c.active.pending)
        c.tick(read_error=True, response_ready=False)
        held = self.rms.ports()['response']
        self.assertEqual(held.status, 'Memory')
        for _ in range(3):
            c.tick(response_ready=False)
            self.assertIsNone(c.response)
            self.assertEqual(self.rms.ports()['response'], held)
        c.tick()
        self.assertEqual(c.response.status, 'Memory')
        self.assertEqual(c.response.failed_role, 'input_norm')
        self.assertEqual(len(c.commands), 1)
        self.assertEqual(self.matrix.counts['owner_acquires'], 0)
        self.assertIsNone(self.scalar.client)
        self.assertIsNone(self.memory.pending)
        self.assert_untouched(*p.ORDER)

    def test_abort_waits_for_accepted_rms_read_before_failed_terminal(self):
        c = self.coordinator()
        c.start()
        c.tick()
        pending = c.active.pending
        for _ in range(3):
            c.tick(abort=True, memory_response_ready=False)
            self.assertIs(c.active.pending, pending)
            self.assertIsNone(c.response)
            self.assertIs(self.scalar.client, self.rms)
        c.tick(response_ready=False)
        self.assertIsNone(c.active.pending)
        self.assertIsNone(c.response)
        c.tick()
        self.assertEqual(c.response.status, 'Aborted')
        self.assertEqual(self.matrix.counts['owner_acquires'], 0)
        self.assertIsNone(self.scalar.client)
        self.assert_untouched(*p.ORDER)

    def test_projection_abort_quarantines_live_tile_until_coordinated_reset(self):
        c = self.coordinator()
        c.start()
        deadline = time.monotonic() + 20
        self.until(c, lambda: c.role == 'packed_q_gate' and self.dense.tiles.leased,
                   deadline=deadline)
        driver = c.active
        self.assertIs(self.matrix.owner, self.dense)
        self.assertTrue(self.memory.regions[self.plan.input_norm].published)
        self.assertEqual(len(c.commands), 1)
        c.tick(abort=True, response_ready=False)
        self.until(c, lambda: driver.coordinator.ports(driver.services())['result'] is not None,
                   deadline=deadline, hook=lambda _: dict(response_ready=False))
        held = driver.coordinator.result
        self.assertIsNotNone(held.status)
        self.assertTrue(self.dense.tiles.idle)
        self.assertTrue(self.dense.tiles.leased)
        self.assertTrue(self.dense.tiles.poison)
        for _ in range(3):
            c.tick(response_ready=False)
            self.assertEqual(driver.coordinator.result, held)
            self.assertIsNone(driver.response)
            self.assertIsNone(c.response)
            self.assertIs(c.active, driver)
            self.assertEqual(len(c.commands), 1)
            self.assert_untouched(*p.ORDER[1:])
        event = c.tick()
        self.assertTrue(event['prefix_terminal_fire'])
        self.assertIsNotNone(c.response.status)
        self.assertEqual(c.response.failed_role, 'packed_q_gate')
        self.assertIsNone(c.active)
        self.assertTrue(c.locked)
        self.assertTrue(c.report()['reset_required'])
        self.assertFalse(c.report()['fullprefix_success'])
        self.assertEqual([command['role'] for command in c.commands], list(p.ORDER[:2]))
        self.assert_untouched(*p.ORDER[1:])
        self.assertIsNone(driver.pending_read)
        self.assertIsNone(driver.pending_ack)
        self.assertFalse(driver.results)
        self.assertIsNone(driver.bridge)
        self.assertIsNone(self.memory.pending)
        self.assertIsNone(self.matrix.owner)
        self.assertIsNone(self.vector.client)
        self.assertIsNone(self.scalar.client)
        self.assertTrue(self.dense.tiles.idle)
        self.assertTrue(self.dense.tiles.leased)
        self.assertTrue(self.dense.tiles.poison)
        self.assertTrue(self.matrix.reset_required)
        self.assertEqual(self.matrix.epoch, 0)
        acquired = self.matrix.counts['owner_acquires']
        self.assertFalse(self.matrix.acquire(self.dense, 'dense', self.plan.tag_base + 10))
        self.assertEqual(self.matrix.counts['owner_acquires'], acquired)
        with self.assertRaises(ValueError):
            p.TypedProjectionDriver(self.dense, self.matrix, self.memory, c.jobs[1], vector=self.vector,
                role='packed_q_gate', family=p.FAMILY, profile=p.ATTENTION_PROJECTION_PROFILE)
        with self.assertRaises(ValueError):
            c.start()


if __name__ == '__main__':
    unittest.main()
