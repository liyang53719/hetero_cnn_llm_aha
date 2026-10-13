"""Bounded admission/lifecycle gates for production-shaped 19-stage plans.

No complete full-shaped block runs in the routine suite. The shared fixture
contains only original zero hidden/weight/trig bytes and unpublished outputs;
it is also usable for an explicitly invoked real M16 integration smoke.
"""
import ctypes as C
from dataclasses import FrozenInstanceError, replace
import os
from pathlib import Path
from types import SimpleNamespace
import unittest

from . import full_driver as f, projection_driver as p
from .norm_rope.coordinator import L3NormRopeCoordinator, L3NormRopePlan
from .norm_rope.owner import QkNorm256Owner, PartialRope64Owner, TORCH_DEFAULT256_POLICY
from .norm_rope.scalar import NormRopeScalar
from .gqa.owner import Bf16CausalGqaOwner, QkOrder
from .kv_cache.owner import KvCacheOwner
from .kv_cache.owner import KvCacheJob
from .kv_cache.driver import TypedKvCacheDriver
from .kv_cache.fence import KvBlockFence
from .kv_cache.test_kv_cache import producer
from ..qwen35_gdn_prefill.projection_owner import PrefixWorkspace
from ..qwen35_gdn_prefill.chunk.vector import IEEE_POLICY
from ..qwen35_gdn_prefill.elementwise.model import (
    ElementwiseOwner, ElementwiseOp, ElementwiseJob, TypedElementwiseDriver)
from ..qwen2_resident_matrix.ffn_attention.matrix_service import configure_library


ROOT = Path(__file__).resolve().parents[2]
LIB = VECTOR_PATH = None


def setUpModule():
    global LIB, VECTOR_PATH
    LIB = configure_library(C.CDLL(str(p.d.library_from_environment(ROOT))))
    VECTOR_PATH = Path(os.environ['GDN_VECTOR16_LIBRARY']).resolve(strict=True)


def make_fixture(library, vector_path, *, tokens=16, phases=2):
    """Allocate every cold/carried span before constructing either prefix."""
    assert library.td_reset() == 0
    memory, scalar = p.d.TypedMemory(), NormRopeScalar()
    matrix, vector = p.d.MatrixService(library), p.Vector16(vector_path, exception_policy=IEEE_POLICY)
    cursor = 0x10000

    def allocate(extent, *, readonly=False):
        nonlocal cursor
        base = cursor
        if readonly:
            memory.add_readonly(base, bytes(extent))
        else:
            memory.allocate_output(base, extent)
        cursor += extent + 64
        return base

    weights = dict(input_weight=allocate(2048, readonly=True))
    for role, (k, n) in p.SHAPES.items():
        weights[role + '_weight'] = allocate(k * n * 2, readonly=True)
    extra = dict(q_norm_weight=allocate(512, readonly=True), k_norm_weight=allocate(512, readonly=True),
                 trig=allocate(256 * 128, readonly=True))
    tail_weights = {role + '_weight': allocate(k * n * 2, readonly=True)
                    for role, (k, n) in f.DENSE_SHAPES.items()}
    tail_weights['post_norm_weight'] = allocate(2048, readonly=True)
    plans, workspaces = [], []
    for index in range(phases):
        projection = p.L3ProjectionPlan(tokens=tokens, hidden=allocate(tokens * 2048, readonly=True),
            **weights, input_norm=allocate(tokens * 2048), packed_q_gate=allocate(tokens * 8192),
            k=allocate(tokens * 1024), v=allocate(tokens * 1024), tag_base=1 + index * 32)
        norm_rope = L3NormRopePlan(projection, **extra, q_norm=allocate(tokens * 4096),
            k_norm=allocate(tokens * 1024), gate=allocate(tokens * 4096), q_rope=allocate(tokens * 4096),
            k_rope=allocate(tokens * 1024), position_base=index * 128, trig_tokens=256,
            norm_policy=TORCH_DEFAULT256_POLICY)
        cache = cursor
        valid = (index + 1) * tokens
        memory.allocate_output(cache, valid * 1024)
        memory.allocate_output(cache + 256 * 1024, valid * 1024)
        cursor += 2 * 256 * 1024 + 64
        plan = f.L3FullBlockPlan(norm_rope, **tail_weights, staging_k=cache,
            context=allocate(tokens * 4096), gated_context=allocate(tokens * 4096),
            o=allocate(tokens * 2048), attention_residual=allocate(tokens * 2048),
            post_norm=allocate(tokens * 2048), gate=allocate(tokens * 7168), up=allocate(tokens * 7168),
            silu_mul=allocate(tokens * 7168), down=allocate(tokens * 2048), output=allocate(tokens * 2048),
            expected_generation=index)
        plans.append(plan)
        workspaces.append(PrefixWorkspace(allocate(f.WORKSPACE_BYTES), f.WORKSPACE_BYTES, index + 1))
    dense = p.GdnProjectionOwner(workspaces[0])
    return SimpleNamespace(memory=memory, scalar=scalar, matrix=matrix, vector=vector, dense=dense,
        rms=p.rms.RmsOwner(scalar), norm=QkNorm256Owner(scalar), rope=PartialRope64Owner(scalar),
        kv=KvCacheOwner(), gqa=Bf16CausalGqaOwner(matrix, scalar),
        elementwise=ElementwiseOwner(scalar, enable_attention_sigmoid_mul=True),
        fence=KvBlockFence(memory), plans=plans, workspaces=workspaces)


def make_prefix(fixture, index=0):
    x, plan = fixture, fixture.plans[index]
    projection = p.L3ProjectionCoordinator(memory=x.memory, dense=x.dense, matrix=x.matrix,
        vector=x.vector, rms_owner=x.rms, plan=plan.norm_rope.projection)
    return L3NormRopeCoordinator(prefix=projection, norm_owner=x.norm, rope_owner=x.rope,
                                 plan=plan.norm_rope)


def make_coordinator(fixture, *, prefix=None, plan=None):
    x = fixture
    return f.L3FullBlockCoordinator(prefix=make_prefix(x) if prefix is None else prefix,
        kv_owner=x.kv, gqa_owner=x.gqa, elementwise_owner=x.elementwise, fence=x.fence,
        plan=x.plans[0] if plan is None else plan)


class FullBlockAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.x = make_fixture(LIB, VECTOR_PATH)

    def test_full_19_jobs_original_resources_and_no_dma_at_construction(self):
        x = self.x
        chain = make_coordinator(x)
        self.assertEqual(len(chain.jobs), 19)
        self.assertEqual([job.tag for job in chain.jobs], list(range(1, 20)))
        self.assertEqual(chain.commands, [])
        self.assertEqual(chain.receipts, {})
        self.assertFalse(chain.started)
        self.assertIsNone(chain.active)
        self.assertIsNone(chain.response)
        self.assertIs(chain.matrix, x.matrix)
        self.assertIs(chain.dense, x.dense)
        self.assertIs(chain.vector, x.vector)
        self.assertIs(chain.scalar, x.scalar)
        self.assertEqual(x.matrix.counts['owner_acquires'], 0)
        self.assertEqual(sum(x.scalar.calls.values()), 0)
        self.assertEqual(chain.jobs[9].qk_policy, QkOrder.PairHighFirst)
        self.assertEqual((chain.jobs[9].query_start, chain.jobs[9].cache_length), (0, 16))
        self.assertEqual(chain.jobs[10].op, ElementwiseOp.SigmoidMul)
        self.assertEqual((chain.jobs[10].a, chain.jobs[10].b, chain.jobs[10].row_width),
                         (chain.plan.norm_rope.gate, chain.plan.context, 2048))
        for index, role in ((11, 'o'), (14, 'gate'), (15, 'up'), (17, 'down')):
            self.assertIs(type(chain.jobs[index]), p.d.down.Job)
            self.assertEqual((chain.jobs[index].k, chain.jobs[index].n), f.DENSE_SHAPES[role])
        self.assertEqual(chain.jobs[12].a, chain.plan.norm_rope.projection.hidden)
        self.assertEqual(chain.jobs[18].a, chain.plan.attention_residual)
        self.assertIs(chain.prefix.prefix.rms, chain.rms)
        self.assertEqual(x.dense.workspace.extent, 524288)
        self.assertEqual(x.plans[1].norm_rope.position_base, 128)
        self.assertEqual(x.plans[1].expected_generation, 1)

    def test_admission_rejects_plan_generation_policy_alias_and_overflow(self):
        x = self.x
        prefix = make_prefix(x)
        original = x.plans[0]
        for plan in (replace(original, expected_generation=1), replace(original, expected_generation=True),
                replace(original, capacity=128), replace(original, output=original.down),
                replace(original, gate_weight=original.up_weight),
                replace(original, context=x.dense.workspace.base), replace(original, output=(1 << 56) - 64),
                replace(original, norm_rope=replace(original.norm_rope, norm_policy=0)),
                replace(original, norm_rope=replace(original.norm_rope))):
            with self.subTest(plan=plan), self.assertRaises(ValueError):
                make_coordinator(x, prefix=prefix, plan=plan)
        with self.assertRaises(FrozenInstanceError):
            original.output = 0
        with self.assertRaises(ValueError):
            replace(original.norm_rope.projection, tokens=1).validate()
        self.assertFalse(prefix.started)
        self.assertEqual(x.matrix.counts['owner_acquires'], 0)

    def test_cache_reservation_holes_include_unrelated_future_allocations(self):
        x = self.x
        x.memory.allocate_output(x.plans[0].staging_k + 16 * 1024, 64)
        with self.assertRaisesRegex(ValueError, 'reserved KV capacity'):
            make_coordinator(x)
        self.assertEqual(x.matrix.counts['owner_acquires'], 0)

    def test_full_workspace_required_and_must_be_fresh(self):
        x = self.x
        original = x.dense.workspace
        x.dense.workspace = PrefixWorkspace(original.base, 16384, 1)
        with self.assertRaises(ValueError):
            make_coordinator(x)
        x.dense.workspace = original
        r = x.memory.regions[original.base]
        r.storage[64] ^= 1
        with self.assertRaisesRegex(ValueError, 'workspace lost initial sentinels'):
            make_coordinator(x)

    def test_every_output_is_fresh_and_tail_weights_original(self):
        x = self.x
        region = x.memory.regions[x.plans[0].output]
        region.storage[64] ^= 1
        with self.assertRaisesRegex(ValueError, 'sentinels'):
            make_coordinator(x)
        region.storage[64] ^= 1
        weight = x.memory.regions[x.plans[0].down_weight]
        weight.readonly = False
        with self.assertRaises(ValueError):
            make_coordinator(x)

    def test_rejects_replaced_plan_job_resource_history_or_late_allocation(self):
        x = self.x
        chain = make_coordinator(x)
        mutations = ((chain, 'plan', replace(chain.plan)), (chain, 'jobs', tuple(list(chain.jobs))),
            (x.gqa, 'scalar', NormRopeScalar()), (x.elementwise, 'sigmoid_observer', lambda *args: None),
            (x.dense, 'workspace', replace(x.dense.workspace)))
        for target, name, value in mutations:
            original = getattr(target, name)
            setattr(target, name, value)
            with self.assertRaises(ValueError):
                chain.start()
            setattr(target, name, original)
        chain.receipts['kv_append'] = object()
        with self.assertRaisesRegex(ValueError, 'history'):
            chain.start()
        chain.receipts.clear()
        x.memory.allocate_output(0x70000000, 64)
        with self.assertRaisesRegex(ValueError, 'allocation'):
            chain.start()

    def test_abort_drains_original_prefix_and_never_launches_kv_or_tail(self):
        x = self.x
        chain = make_coordinator(x)
        chain.start()
        chain.tick(response_ready=False)
        self.assertIsNotNone(chain.active.pending)
        chain.tick(abort=True, memory_response_ready=False, response_ready=False)
        self.assertIsNone(chain.response)
        for _ in range(20):
            if chain.response is not None:
                break
            chain.tick()
        self.assertIsNotNone(chain.response)
        self.assertEqual(chain.response.status, 'Aborted')
        self.assertEqual(chain.response.failed_role, 'input_norm')
        self.assertEqual(len(chain.commands), 1)
        self.assertEqual(chain.commands[0]['role'], 'input_norm')
        self.assertIsNone(x.fence.pending_receipt)
        self.assertEqual(x.fence.state.generation, 0)
        self.assertFalse(x.memory.regions[chain.plan.output].published)
        self.assertFalse(x.memory.regions[chain.plan.staging_k].written)
        with self.assertRaises(ValueError):
            chain.start()
        with self.assertRaises(ValueError):
            chain.tick()

    def test_carried_admission_uses_actual_fence_roots_with_separate_rope_position(self):
        # This executes KV and a real Add, not a preceding complete block.
        # Its purpose is carried-control admission with authentic fence state.
        x = self.x
        a = producer(x.memory, 0x60000000, bytes(16 * 1024), 200)
        b = producer(x.memory, 0x60100000, bytes(16 * 1024), 201)
        job = KvCacheJob(202, 0, 0, 0, a.base, b.base, x.plans[0].staging_k, 16, 0, 0)
        kv = TypedKvCacheDriver(x.kv, x.memory, job, x.fence)
        for _ in range(3000):
            if kv.response is not None:
                break
            kv.tick()
        self.assertIsNotNone(kv.receipt)
        left = producer(x.memory, 0x60200000, bytes(2048), 203)
        right = producer(x.memory, 0x60300000, bytes(2048), 204)
        x.memory.allocate_output(0x60400000, 2048)
        final_job = ElementwiseJob(205, left.base, right.base, 0x60400000, 1)
        final = TypedElementwiseDriver(x.elementwise, x.memory, final_job)
        for _ in range(300):
            if x.elementwise.ports()['response'] is not None:
                break
            final.tick(response_ready=False)
        prepared = x.fence.prepare_final_owner(kv.receipt, final, expected_job=final_job)
        x.fence.accept_final_owner(prepared)
        x.dense.workspace = x.workspaces[1]
        prefix = make_prefix(x, 1)
        carried = make_coordinator(x, prefix=prefix, plan=x.plans[1])
        self.assertEqual((carried.jobs[8].previous_k, carried.jobs[8].previous_v),
                         (kv.job.staging_k, kv.job.staging_v))
        self.assertEqual((carried.jobs[8].previous_tokens, carried.jobs[8].current_generation), (16, 1))
        self.assertEqual((carried.jobs[9].query_start, carried.jobs[9].cache_length), (16, 32))
        self.assertEqual(carried.plan.norm_rope.position_base, 128)
        self.assertIs(carried.fence, x.fence)
        self.assertFalse(carried.started)


if __name__ == '__main__':
    unittest.main()
