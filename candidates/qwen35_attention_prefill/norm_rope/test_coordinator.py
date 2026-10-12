"""Small preflight/fault gates followed by one bounded actual M16 chain.

The sole full-shaped run retains all production geometry and shares one
caller-provided Matrix/Vector/scalar. No checkpoint, RTL capture or new build.
"""
import ctypes as C
from dataclasses import FrozenInstanceError, replace
import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch

import numpy as np

from .. import projection_driver as p
from ..test_projection_driver import sparse_weight, sparse_projection_oracle
from ...qwen35_gdn_prefill.chunk.vector import IEEE_POLICY
from ...qwen35_gdn_prefill.projection_owner import PrefixWorkspace
from ...qwen35_gdn_prefill.test_rms_owner import bf16, oracle as rms_oracle
from ...qwen2_resident_matrix.ffn_attention.matrix_service import configure_library
from . import coordinator as c
from .owner import QkNorm256Owner, PartialRope64Owner
from .scalar import NormRopeScalar
from .test_driver import _norm_expected, _rope_expected, _trig_raw


ROOT = Path(__file__).resolve().parents[3]
LIB = VECTOR_PATH = None


def setUpModule():
    global LIB, VECTOR_PATH
    LIB = configure_library(C.CDLL(str(p.d.library_from_environment(ROOT))))
    VECTOR_PATH = Path(os.environ['GDN_VECTOR16_LIBRARY']).resolve(strict=True)


class L3NormRopeTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(LIB.td_reset(), 0)
        self.matrix = p.d.MatrixService(LIB)
        self.vector = p.Vector16(VECTOR_PATH, exception_policy=IEEE_POLICY)
        self.scalar = NormRopeScalar()
        self.rms = p.rms.RmsOwner(self.scalar)
        self.norm, self.rope = QkNorm256Owner(self.scalar), PartialRope64Owner(self.scalar)
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
        self.projection_plan = p.L3ProjectionPlan(**plan)
        self.plan = c.L3NormRopePlan(self.projection_plan,
            q_norm_weight=allocate(bytes(512)), k_norm_weight=allocate(bytes(512)),
            q_norm=allocate(extent=16 * 4096), k_norm=allocate(extent=16 * 1024),
            gate=allocate(extent=16 * 4096), q_rope=allocate(extent=16 * 4096),
            k_rope=allocate(extent=16 * 1024), trig=allocate(_trig_raw(35)),
            position_base=17, trig_tokens=35)
        # The original prefix freezes the entire map, including all later
        # destinations and original norm/trig parameters, before admission.
        self.prefix = p.L3ProjectionCoordinator(memory=self.memory, dense=self.dense,
            matrix=self.matrix, vector=self.vector, rms_owner=self.rms, plan=self.projection_plan)

    def coordinator(self, **changes):
        args = dict(prefix=self.prefix, norm_owner=self.norm, rope_owner=self.rope, plan=self.plan)
        args.update(changes)
        return c.L3NormRopeCoordinator(**args)

    def until(self, coordinator, predicate, *, deadline=None, controls=None):
        deadline = deadline or time.monotonic() + 15
        while not predicate():
            self.assertLess(time.monotonic(), deadline, 'bounded real chain execution')
            self.assertIsNone(coordinator.response)
            coordinator.tick(**({} if controls is None else controls(coordinator)))

    def assert_fresh(self, *names):
        for name in names:
            region = self.memory.regions[getattr(self.plan, name)]
            self.assertFalse(region.published)
            self.assertFalse(region.written)
            self.assertFalse(region.acknowledged)
            self.assertEqual(region.raw(), p.d.GUARD * (region.extent // 64))

    def test_a_preflight_alias_range_sentinels_and_same_original_plan(self):
        for plan in (replace(self.plan, q_norm=self.plan.gate),
                     replace(self.plan, k_rope=self.projection_plan.v),
                     replace(self.plan, q_norm_weight=self.projection_plan.input_weight),
                     replace(self.plan, q_norm=self.dense.workspace.base),
                     replace(self.plan, trig=(1 << 56) - 64),
                     replace(self.plan, position_base=20),
                     replace(self.plan, position_base=True),
                     replace(self.plan, trig_tokens=0),
                     replace(self.plan, projection=replace(self.projection_plan))):
            with self.subTest(plan=plan), self.assertRaises(ValueError):
                self.coordinator(plan=plan)
        r = self.memory.regions[self.plan.gate]
        r.storage[64] ^= 1
        with self.assertRaisesRegex(ValueError, 'sentinels'):
            self.coordinator()
        r.storage[64] ^= 1
        weight = self.memory.regions[self.plan.q_norm_weight]
        weight.readonly = False
        with self.assertRaises(ValueError):
            self.coordinator()
        weight.readonly = True
        self.assertFalse(self.prefix.started)
        self.assertEqual(self.matrix.counts['owner_acquires'], 0)
        self.assert_fresh('q_norm', 'k_norm', 'gate', 'q_rope', 'k_rope')

    def test_b_rejects_replaced_resources_jobs_allocations_and_fake_receipts(self):
        chain = self.coordinator()
        with self.assertRaises(FrozenInstanceError):
            self.plan.position_base = 3
        for target, name, replacement in ((chain, 'plan', replace(self.plan)),
                (self.norm, 'scalar', NormRopeScalar()),
                (chain, 'jobs', tuple(list(chain.jobs)))):
            original = getattr(target, name)
            setattr(target, name, replacement)
            with self.assertRaisesRegex(ValueError, 'binding'):
                chain.start()
            setattr(target, name, original)
        region = self.memory.regions[self.plan.k_norm]
        original = region.storage
        region.storage = bytearray(original)
        with self.assertRaisesRegex(ValueError, 'storage'):
            chain.start()
        region.storage = original
        chain.receipts['v'] = (74, None, 16384)
        with self.assertRaisesRegex(ValueError, 'history'):
            chain.start()
        chain.receipts.clear()
        self.prefix.receipts['v'] = (74, None, 16384)
        with self.assertRaisesRegex(ValueError, 'provenance'):
            chain.start()
        self.prefix.receipts.clear()
        observer = self.norm.observer
        self.norm.observer = lambda *args: None
        with self.assertRaisesRegex(ValueError, 'binding'):
            chain.start()
        self.norm.observer = observer
        self.memory.allocate_output(0x3000000, 64)
        with self.assertRaisesRegex(ValueError, 'allocation'):
            chain.start()
        self.assertFalse(chain.started)

    def test_c_original_mutable_raw_guard_rechecked_before_start(self):
        chain = self.coordinator()
        for base in (self.plan.q_norm_weight, self.plan.trig, self.projection_plan.hidden):
            region = self.memory.regions[base]
            region.storage[64] ^= 1
            with self.assertRaisesRegex(ValueError, 'bytes changed'):
                chain.start()
            region.storage[64] ^= 1
        self.assertFalse(chain.started)

    def test_d_actual_rms_read_failure_has_held_terminal_and_no_norm_launch(self):
        chain = self.coordinator()
        chain.start()
        chain.tick()
        self.assertIsNotNone(chain.active.pending)
        chain.tick(read_error=True, response_ready=False)
        held = self.rms.ports()['response']
        self.assertEqual(held.status, 'Memory')
        for _ in range(3):
            chain.tick(response_ready=False)
            self.assertEqual(self.rms.ports()['response'], held)
            self.assertIsNone(chain.response)
        event = chain.tick()
        self.assertTrue(event['chain_terminal_fire'])
        self.assertEqual(chain.response.status, 'Memory')
        self.assertEqual(chain.response.failed_role, 'input_norm')
        self.assertEqual(chain.role, 'input_norm')
        self.assertEqual(len(chain.commands), 1)
        self.assertEqual(self.matrix.counts['owner_acquires'], 0)
        self.assertIsNone(self.norm.job)
        self.assertTrue(chain.report()['reset_required'])
        self.assertFalse(chain.report()['complete_l3_norm_rope_valid'])
        self.assert_fresh('q_norm', 'k_norm', 'gate', 'q_rope', 'k_rope')

    def test_e_abort_drains_accepted_rms_read_and_retains_poison(self):
        chain = self.coordinator()
        chain.start()
        chain.tick()
        pending = chain.active.pending
        for _ in range(3):
            chain.tick(abort=True, memory_response_ready=False)
            self.assertIs(chain.active.pending, pending)
            self.assertIsNone(chain.response)
            self.assertIs(self.scalar.client, self.rms)
        chain.tick(response_ready=False)
        self.assertIsNone(self.scalar.client)
        chain.tick()
        self.assertEqual(chain.response.status, 'Aborted')
        self.assertTrue(chain.locked)
        self.assertIsNone(self.memory.pending)
        self.assertFalse(self.rms.ports()['job_ready'])
        self.assertIsNone(self.norm.job)
        self.assert_fresh('q_norm', 'k_norm', 'gate', 'q_rope', 'k_rope')
        with self.assertRaises(ValueError):
            chain.start()
        with self.assertRaises(ValueError):
            chain.tick()

    def test_f_abort_at_genuine_stage_boundary_preserves_accepted_rms(self):
        chain = self.coordinator()
        chain.start()
        self.until(chain, lambda: len(chain.commands) == 1)
        region = self.memory.regions[self.projection_plan.input_norm]
        saved = region.raw()
        self.assertTrue(region.published)
        chain.tick(abort=True, response_ready=False)
        self.assertIsNone(chain.response)
        chain.tick()
        self.assertEqual(chain.response.status, 'Aborted')
        self.assertEqual(region.raw(), saved)
        self.assertTrue(region.published)
        self.assertEqual(self.matrix.counts['owner_acquires'], 0)
        self.assert_fresh('q_norm', 'k_norm', 'gate', 'q_rope', 'k_rope')

    def test_z_one_actual_m16_shared_chain_with_every_norm_rope_terminal_fence(self):
        began = time.monotonic()
        deadline = began + 120
        chain = self.coordinator()
        binding = chain._resource_identity()
        chain.start()
        with (patch('heteronpu.qk_norm256_candidate.head_trace', side_effect=AssertionError('oracle')),
             patch('heteronpu.qk_norm256_candidate.rsqrt_trace', side_effect=AssertionError('oracle')),
             patch('heteronpu.rope_bf16_candidate.pair_trace', side_effect=AssertionError('oracle')),
             patch.object(NormRopeScalar, '__init__', side_effect=AssertionError('second scalar'))):
            self.until(chain, lambda: chain._prefix_result is not None, deadline=deadline)
            self.assertEqual([x['role'] for x in chain.commands], list(p.ORDER))
            v_region = self.memory.regions[self.projection_plan.v]
            saved_v = v_region.raw()
            self.assertTrue(v_region.published)
            for index in range(4, 8):
                self.assertIsNone(chain.active)
                self.assertEqual(len(chain.commands), index)
                # Source bytes and genuine receipt provenance are checked at
                # admission, including unrelated previously published V.
                for base in (self.plan.trig, self.projection_plan.v):
                    region = self.memory.regions[base]
                    region.storage[64] ^= 1
                    with self.assertRaisesRegex(ValueError, 'bytes changed'):
                        chain.tick()
                    region.storage[64] ^= 1
                receipt = chain.receipts[c.ORDER[index - 1]]
                chain.receipts[c.ORDER[index - 1]] = (receipt,)
                with self.assertRaisesRegex(ValueError, 'receipt identity'):
                    chain.tick()
                chain.receipts[c.ORDER[index - 1]] = receipt
                chain.tick()
                self.assertIs(chain.active.owner.scalar, self.scalar)
                self.assertIs(chain.active.memory, self.memory)
                self.until(chain, lambda: chain.active.pending is not None and
                    chain.active.owner.request.write and
                    chain.active.counts['write_bytes'] == chain.active.job.write_bytes,
                    deadline=deadline, controls=lambda x: dict(memory_ready=x.ticks % 13 != 0,
                                                               memory_response_ready=x.ticks % 17 != 0))
                outputs = chain.active.outputs
                for _ in range(3):
                    chain.tick(ack_ready=False)
                    self.assertTrue(all(not r.published for r in outputs))
                    self.assertEqual(len(chain.commands), index)
                chain.tick(response_ready=False)
                held = chain.active.owner.ports()['response']
                self.assertIsNotNone(held)
                for _ in range(3):
                    chain.tick(response_ready=False)
                    self.assertEqual(chain.active.owner.ports()['response'], held)
                    self.assertTrue(all(not r.published for r in outputs))
                    self.assertIsNone(chain.response)
                event = chain.tick()
                self.assertTrue(all(r.published for r in outputs))
                self.assertEqual(event['chain_terminal_fire'], index == 7)
                self.assertEqual(v_region.raw(), saved_v)
                self.assertTrue(v_region.published)
        self.assertIsNone(chain.response.status)
        self.assertEqual(chain._resource_identity(), binding)
        self.assertEqual([x['role'] for x in chain.commands], list(c.ORDER))
        self.assertEqual([x['job']['tag'] for x in chain.commands], list(range(71, 79)))
        self.assertIsNone(self.scalar.client)
        self.assertIsNone(self.matrix.owner)
        self.assertIsNone(self.vector.client)
        self.assertIsNone(self.memory.pending)
        report = chain.report()
        self.assertTrue(report['complete_l3_norm_rope_valid'])
        self.assertEqual(report['actual_owner_commands'], 8)
        self.assertEqual(report['acknowledged_write_bytes'], 16 * (1024 + 4096 + 512 + 512 + 4096 + 512 + 2048 + 512) * 2)
        self.assertEqual(report['scalar_request_count'], sum(self.scalar.calls.values()))
        for key in ('public_command128_executed', 'native_acceptance', 'full_block_executed',
                    'actual_kv_cache_executed', 'rtl_executed', 'chisel_executed'):
            self.assertFalse(report[key])
        self.assertIsNone(report['hardware_cycles'])
        normalized, _ = rms_oracle(self.hidden, self.input_weight, 16, self.prefix.rms_policy)
        self.assertEqual(self.memory.regions[self.projection_plan.input_norm].raw(), normalized)
        for role, (_, n) in p.SHAPES.items():
            self.assertEqual(self.memory.regions[getattr(self.projection_plan, role)].raw(),
                sparse_projection_oracle(normalized, self.weights[role], 16, n))
        for role, source, weight, output in ((0, self.projection_plan.packed_q_gate, self.plan.q_norm_weight, self.plan.q_norm),
                                            (1, self.projection_plan.k, self.plan.k_norm_weight, self.plan.k_norm)):
            expected = _norm_expected(self.memory.regions[source].raw(), self.memory.regions[weight].raw(), 16, role)
            self.assertEqual(self.memory.regions[output].raw(), expected[0])
            if role == 0:
                self.assertEqual(self.memory.regions[self.plan.gate].raw(), expected[1])
        trig = self.memory.regions[self.plan.trig].raw()
        for heads, source, output in ((8, self.plan.q_norm, self.plan.q_rope), (2, self.plan.k_norm, self.plan.k_rope)):
            self.assertEqual(self.memory.regions[output].raw(),
                _rope_expected(self.memory.regions[source].raw(), trig, 16, heads, 17))
        self.assertLess(time.monotonic() - began, 120)
        report['commands'].clear()
        self.assertEqual(len(chain.report()['commands']), 8)


if __name__ == '__main__':
    unittest.main()
