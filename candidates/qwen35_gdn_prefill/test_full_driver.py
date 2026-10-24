"""Bounded coordinator/control tests with explicitly synthetic semantic owners.

These tests exercise real TypedMemory writes, ACKs, publication, allocation and
coordinator control. They replace ALL numerical owner transports and use no
C++ library/compiler/checkpoint/RTL. Passing is not a full numerical pass.
"""
from collections import Counter
from contextlib import ExitStack
from dataclasses import replace
from types import SimpleNamespace
from pathlib import Path
import gc
import json
import tempfile
import unittest
from unittest.mock import patch

from . import full_driver as f


def write(memory, region, offset, marker, *, acknowledge=True, error=False):
    command = f.d.down.WriteCommand(region.base + offset, 1, 19)
    memory.begin_write(command)
    memory.write_data((marker,) * 32, True)
    if acknowledge:
        memory.acknowledge(f.d.down.WriteAck(19, error, 64))


class SyntheticTransport:
    """Test-only byte writer; does not compute even one numerical layer."""
    def __init__(self, coordinator, memory, job):
        self.coordinator, self.memory, self.job = coordinator, memory, job
        self.role = coordinator.role
        if self.role == 'conv_silu':
            job.validate(current_generation=coordinator.window_roots.generation)
        else:
            job.validate()
        if self.role in f.DENSE:
            coordinator.dense.workspace.validate(job)
        self.output = memory.regions[coordinator.plan[self.role]]
        self.response = self.pending = self.held = None
        self.owner = SimpleNamespace(ports=lambda: {'response': self.held})
        self.begun, self.failed = False, None
        p = coordinator.plan
        source_names = {
            'input_norm': ('hidden',), 'qkv': ('input_norm',), 'z': ('input_norm',),
            'ab': ('input_norm',), 'conv_silu': ('qkv',), 'prep': ('conv_silu', 'ab'),
            'chunk': ('prep',), 'gated_norm': ('chunk', 'z'), 'o': ('gated_norm',),
            'attention_residual': ('hidden', 'o'), 'post_norm': ('attention_residual',),
            'gate': ('post_norm',), 'up': ('post_norm',), 'silu_mul': ('gate', 'up'),
            'down': ('silu_mul',), 'output': ('attention_residual', 'down')}
        self.sources = [memory.exact(p[name], memory.regions[p[name]].extent, readable=True)
                        for name in source_names[self.role]]
        self.spans = [self.output]
        if self.role == 'conv_silu':
            self.history_out = memory.regions[p['history']]
            self.spans.append(self.history_out)
            if not job.cold:
                self.sources.append(memory.exact(job.history_in, self.history_out.extent, readable=True))
        if self.role == 'chunk':
            self.state_out = memory.regions[p['state']]
            self.spans.append(self.state_out)
            if not job.cold:
                self.sources.append(memory.exact(job.state_in, self.state_out.extent, readable=True))
        if self.role == 'down':
            self.spans.insert(0, memory.regions[p['prefix']])
        coordinator.test_launches.append((coordinator.phase, self.role, job,
                                         tuple((r.base, f.sha(r.raw())) for r in self.sources)))

    def receipt(self):
        j, error = self.job, self.failed
        if self.role in f.DENSE:
            return (j.tag, error, j.write_bytes)
        if self.role in ('input_norm', 'post_norm'):
            return f.rms.RmsResult(j.tag, error, j.write_bytes, 0)
        if self.role == 'conv_silu':
            return f.conv.ConvResult(j.tag, error, j.write_bytes, 0, error is None,
                                     j.vector_bytes, j.history_bytes, j.expected_generation)
        if self.role == 'chunk':
            return f.chunk.ChunkResult(j.tag, error, j.write_bytes, j.output, j.state_out,
                j.output_bytes, j.state_bytes, j.expected_generation, 0, error is None)
        result = {'prep': f.prep.InputPrepResult, 'gated_norm': f.norm.GatedNormResult}.get(
            self.role, f.elt.ElementwiseResult)
        return result(j.tag, error, j.write_bytes, 0, error is None)

    def tick(self, *, abort=False, response_ready=True, memory_response_ready=True,
             ack_ready=True, ack_error=False, **ignored):
        if abort:
            self.failed = self.failed or 'Aborted'
        if self.pending is not None:
            if not memory_response_ready or not ack_ready:
                return {}
            self.memory.acknowledge(f.d.down.WriteAck(19, bool(ack_error), 64))
            self.pending = None
            self.failed = self.failed or ('Memory' if ack_error else None)
            self.held = self.receipt()
            return {}
        if self.failed is not None:
            self.held = self.receipt()
        if self.held is not None:
            if response_ready:
                self.response = self.held
                if self.failed is None and self.role != 'chunk':
                    self.memory.publish(self.output.base, (self.job.tag, None, self.output.extent))
                return {'response_fire': True}
            return {}
        if not self.begun:
            self.begun = True
            if self.role == 'conv_silu':
                slot = self.coordinator.conv_nodes[self.job.tag]
                slot['seen'][:] = bytes([1]) * len(slot['seen'])
                slot['data'][:] = b'\x80\x3f' * (len(slot['data']) // 2)
                slot['count'] = len(slot['seen'])
            marker = 0x3000 + self.coordinator.window_roots.generation * 32 + f.ORDER.index(self.role)
            for region in self.spans:
                for offset in range(0, region.extent, 64):
                    last = region is self.spans[-1] and offset + 64 == region.extent
                    write(self.memory, region, offset, marker, acknowledge=not last)
            self.pending = True
        return {}

    def report(self):
        return dict(scope='SYNTHETIC_COORDINATOR_CONTROL_ONLY', numerical_execution=False,
                    output_published=self.output.published)


class FullCoordinatorControlTests(unittest.TestCase):
    PROJECTION_POLICY = f.ProjectionPolicy.Legacy

    @classmethod
    def setUpClass(cls):
        cls.weights = {f.WEIGHTS[role]: bytes(k * n * 2)
                       for role, (k, n) in f.DENSE.items() if role != 'ab'}
        cls.weights.update({
            'linear_attn.in_proj_a.weight': bytes(1024 * 16 * 2),
            'linear_attn.in_proj_b.weight': bytes(1024 * 16 * 2),
            'input_layernorm.weight': bytes(2048), 'post_attention_layernorm.weight': bytes(2048),
            'linear_attn.conv1d.weight': bytes(6144 * 8), 'linear_attn.norm.weight': bytes(512),
            'linear_attn.A_log': bytes(64), 'linear_attn.dt_bias': bytes(32)})

    def setUp(self):
        matrix = object.__new__(f.d.MatrixService)
        matrix.lib = SimpleNamespace(matrix_accumulator_address=lambda: 123,
                                     matrix_state=lambda: 0, td_reset=lambda: 0, matrix_dense_fmas=lambda: 0)
        matrix.resource_address, matrix.owner, matrix.epoch = 123, None, 0
        matrix.counts = Counter()
        vector = object.__new__(f.Vector16)
        vector.resource_address, vector.client = 456, None
        vector.exception_policy, vector.fatal_mask = f.LEGACY_POLICY, 30
        # Explicitly synthetic identity, not a compiled or executed backend.
        from .chunk.vector import BackendIdentity, VECTOR_ABI
        vector.backend_identity = BackendIdentity(f.LEGACY_BACKEND, 'synthetic-control-only',
            'synthetic-control-only', '0' * 64, VECTOR_ABI, '0' * 64)
        vector.library, vector.library_sha256 = Path('synthetic-control-only'), '0' * 64
        vector.lib = SimpleNamespace(**{name: SimpleNamespace(argtypes=(), restype=int)
            for name in ('gdn_vector16', 'gdn_vector16_trace',
                         'gdn_vector16_mul_add_policy_trace', 'gdn_vector16_environment')})
        vector._Vector16__loaded_arithmetic_identity = vector._current_arithmetic_identity()
        vector.calls, vector.lane_ops, vector.flags, vector.host_calls = (Counter() for _ in range(4))
        # The control fixture must not call CDLL(None) or scalar arithmetic
        # merely to initialize SharedScalar's host-environment check.
        scalar = object.__new__(f.prep.PrepScalar)
        scalar.client, scalar.enable_softplus = None, True
        scalar.calls, scalar.internal_calls, scalar.soft_internal_calls = (Counter() for _ in range(3))
        self.events = []
        self.c = f.FullBlockCoordinator(self.weights, {'cold': bytes(32768), 'carry': bytes(32768)},
            matrix=matrix, vector=vector, scalar=scalar, projection_policy=self.PROJECTION_POLICY,
            observe=lambda *args: self.events.append(args))
        self.c.test_launches = []
        def factory(owner, *args, **kwargs):
            return SyntheticTransport(self.c, args[-2], args[-1])
        self.original_drivers = {}
        drivers = [(f.rms, 'TypedRmsDriver'), (f.d, 'TypedDenseDriver'),
                             (f.conv, 'TypedConvDriver'), (f.prep, 'TypedInputPrepDriver'),
                             (f.chunk, 'TypedChunkDriver'), (f.norm, 'TypedGatedNormDriver'),
                             (f.elt, 'TypedElementwiseDriver'), (f, 'TypedSeededDenseDriver')]
        if self.c.projection_module is not None:
            drivers.append((self.c.projection_module, 'TypedProjectionDriver'))
        for module, name in drivers:
            self.original_drivers[module, name] = getattr(module, name)
            p = patch.object(module, name, factory)
            p.start()
            self.addCleanup(p.stop)

    def start(self):
        self.c.start('cold', cold=True, expected_generation=0)

    def test_scalar_modified_before_constructor_is_rejected_before_allocation(self):
        from .test_scalar_identity import bare
        scalar = bare()
        for method in ('op', '_exp_node', '_soft_node', 'acquire', 'release'):
            with self.subTest(method=method), patch.object(scalar, method, lambda *args: 0):
                with self.assertRaisesRegex(ValueError, 'Scalar arithmetic binding changed'):
                    f.FullBlockCoordinator({}, {}, matrix=self.c.matrix, vector=self.c.vector, scalar=scalar)
        for value in (False, 1):
            scalar.enable_softplus = value
            with self.assertRaisesRegex(ValueError, 'explicitly Softplus-enabled'):
                f.FullBlockCoordinator({}, {}, matrix=self.c.matrix, vector=self.c.vector, scalar=scalar)
        # Standalone DecayScalar guards do not widen full-block admission.
        from ..qwen35_35b_exp.scalar import DecayScalar
        with self.assertRaisesRegex(ValueError, 'explicitly Softplus-enabled'):
            f.FullBlockCoordinator({}, {}, matrix=self.c.matrix, vector=self.c.vector, scalar=bare(DecayScalar))

    def test_source_snapshot_rejects_scalar_drift_before_writing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(f, 'verify_library', return_value=(None, None, self.c.vector.backend_identity)):
                with patch.object(self.c.scalar, 'op', lambda *args: 0):
                    with self.assertRaisesRegex(ValueError, 'Scalar arithmetic binding changed'):
                        f.freeze_identity(root, root, {}, {}, root / 'not-loaded', self.c.vector,
                                          root, scalar=self.c.scalar)
                with patch.object(f.prep.PrepScalar, 'op', lambda *args: 0):
                    with self.assertRaisesRegex(ValueError, 'Scalar arithmetic binding changed'):
                        f.freeze_identity(root, root, {}, {}, root / 'not-loaded', self.c.vector,
                                          root, scalar=self.c.scalar)
            self.assertEqual(list(root.iterdir()), [])

    def test_scalar_instance_and_class_binding_are_frozen_before_launch(self):
        with patch.object(self.c.scalar, 'op', lambda *args: 0):
            with self.assertRaisesRegex(ValueError, 'Scalar arithmetic binding changed'):
                self.start()
        with patch.object(f.prep.PrepScalar, 'op', lambda *args: 0):
            with self.assertRaisesRegex(ValueError, 'Scalar arithmetic binding changed'):
                self.start()
        with patch.object(f.chunk, 'ep', SimpleNamespace(operation=lambda policy: 'softplus')):
            with self.assertRaisesRegex(ValueError, 'Scalar arithmetic binding changed'):
                self.start()
        self.assertFalse(self.c.launched)

    def test_scalar_configuration_and_owner_selection_are_frozen(self):
        for target, name, value in ((self.c.scalar, 'enable_softplus', False),
                                    (self.c.scalar, 'enable_softplus', 1),
                                    (self.c.chunk, 'exp_policy', 'different'),
                                    (self.c.prep, 'gate_policy', 'different'),
                                    (self.c.prep, 'reduction_policy', 'different')):
            with self.subTest(field=name, value=value), patch.object(target, name, value):
                with self.assertRaisesRegex(ValueError, 'Scalar arithmetic binding changed|shared owner/bank/service replaced'):
                    self.start()
        self.assertEqual(self.c.report()['scalar_arithmetic_binding']['implementation'], 'PrepScalar')
        self.assertIsNone(self.c.report()['scalar_arithmetic_binding']['enable_ieee_exp'])

    def test_scalar_mutation_inside_nonterminal_tick_is_rejected_immediately(self):
        self.start()
        original = self.c.active.tick
        def mutated_tick(**controls):
            event = original(**controls)
            self.c.scalar.op = lambda *args: 0
            return event
        self.c.active.tick = mutated_tick
        with self.assertRaisesRegex(ValueError, 'Scalar arithmetic binding changed'):
            self.c.tick()
        self.assertIsNone(self.c.response)
        self.assertEqual(self.c.roots.generation, 0)
        self.assertEqual(self.c.commands, [])

    def test_scalar_mutation_after_intermediate_observer_cannot_launch_next_owner(self):
        def mutate(*args):
            self.c.scalar._exp_node = lambda *args: 0
        self.c.observe = mutate
        self.start()
        with self.assertRaisesRegex(ValueError, 'Scalar arithmetic binding changed'):
            self.until(lambda: bool(self.c.commands))
        self.assertEqual(len(self.c.test_launches), 1)
        self.assertEqual(self.c.roots.generation, 0)
        with self.assertRaisesRegex(ValueError, 'Scalar arithmetic binding changed'):
            self.c.report()

    def test_final_scalar_callback_cannot_issue_success_report(self):
        def mutate(phase, role, report, outputs):
            if role == 'output':
                self.c.scalar.op = lambda *args: 0
        self.c.observe = mutate
        self.start()
        with self.assertRaisesRegex(ValueError, 'Scalar arithmetic binding changed'):
            self.until(lambda: self.c.response is not None)
        # Output callback is after the software commit, not a rollback facility.
        self.assertEqual(self.c.roots.generation, 1)
        with self.assertRaisesRegex(ValueError, 'Scalar arithmetic binding changed'):
            self.c.report()

    def test_final_acceptance_guard_cannot_split_joint_publication(self):
        self.start()
        self.final_pending()
        self.c.tick()  # Final ACK: held successful terminal, no publication yet.
        self.assert_uncommitted()
        original = self.c.active.tick
        def mutated_acceptance(**controls):
            event = original(**controls)
            self.c.scalar.op = lambda *args: 0
            return event
        self.c.active.tick = mutated_acceptance
        with self.assertRaisesRegex(ValueError, 'Scalar arithmetic binding changed'):
            self.c.tick()
        # The guard fails only AFTER the no-fallible-check joint fence.
        self.assertEqual(self.c.roots.generation, 1)
        for name in ('history', 'state', 'output'):
            region = self.c.memory.regions[self.c.plan[name]]
            self.assertTrue(region.published)
            self.assertEqual(getattr(self.c.roots, name), region.base)
        with self.assertRaisesRegex(ValueError, 'Scalar arithmetic binding changed'):
            self.c.report()

    def test_vector_backend_identity_is_frozen_before_launch(self):
        self.c.vector.backend_identity = replace(self.c.vector.backend_identity,
                                                 implementation_version='different')
        with self.assertRaisesRegex(ValueError, 'loaded arithmetic binding changed'):
            self.start()

    def test_vector_native_batch_binding_is_frozen_before_launch(self):
        self.c.vector.lib.gdn_vector16_mul_add_policy_trace = SimpleNamespace(argtypes=(), restype=int)
        with self.assertRaisesRegex(ValueError, 'loaded arithmetic binding changed'):
            self.start()

    def test_vector_selected_identity_report_is_explicit(self):
        report = self.c.report()['vector_arithmetic_backend']
        self.assertEqual(report, self.c.vector.backend_report())
        self.assertEqual(report['implementation_version'], 'synthetic-control-only')

    def test_final_callback_cannot_relabel_loaded_backend_or_issue_success_report(self):
        def mutate(phase, role, report, outputs):
            if role == 'output':
                self.c.vector.backend_identity = replace(self.c.vector.backend_identity,
                                                         implementation_version='changed-after-final-ACK')
        self.c.observe = mutate
        self.start()
        with self.assertRaisesRegex(ValueError, 'loaded arithmetic binding changed'):
            self.until(lambda: self.c.response is not None)
        with self.assertRaisesRegex(ValueError, 'loaded arithmetic binding changed'):
            self.c.report()

    def tearDown(self):
        # Large control-only buffers participate in owner/callback cycles.
        # Release them deterministically rather than depend on GC thresholds.
        self.c = None
        gc.collect()

    def until(self, predicate):
        for _ in range(100):
            if predicate():
                return
            self.c.tick()
        self.fail('bounded synthetic transport did not reach expected control state')

    def final_pending(self):
        self.until(lambda: self.c.role == 'output' and self.c.active is not None and self.c.active.pending)

    def assert_uncommitted(self, generation=0):
        p = self.c.plan
        self.assertEqual(self.c.roots.generation, generation)
        for name in ('history', 'state', 'output'):
            self.assertFalse(self.c.memory.regions[p[name]].published)
            with self.assertRaises(ValueError):
                self.c.memory.read64(p[name])

    def test_real_driver_constructor_contracts_with_synthetic_admission_only(self):
        # Each production adapter executes its actual constructor validations.
        # Only admission/service acquisition is mocked; no owner arithmetic runs.
        admitted = []
        def wrapper(original):
            def construct(owner, *args, **kwargs):
                with patch.object(owner, 'tick', return_value={'job_fire': True}), \
                     patch.object(self.c.matrix, 'acquire', return_value=True), \
                     patch.object(self.c.matrix, 'dense_library', return_value=SimpleNamespace()):
                    instance = original(owner, *args, **kwargs)
                    self.assertIs(instance.memory, self.c.memory)
                    self.assertIs(instance.owner, owner)
                    admitted.append(self.c.role)
                return SyntheticTransport(self.c, args[-2], args[-1])
            return construct
        for (module, name), original in self.original_drivers.items():
            p = patch.object(module, name, wrapper(original))
            p.start()
            self.addCleanup(p.stop)
        self.start()
        self.until(lambda: self.c.response is not None)
        self.c.start('carry', cold=False, expected_generation=1)
        self.until(lambda: self.c.response is not None)
        self.assertEqual(admitted, list(f.ORDER) * 2)

    def test_prelaunch_sources_and_strides_are_isolated(self):
        self.assertEqual(sum(r.readonly for r in self.c.memory.regions.values()), 15)
        for p in self.c.plans.values():
            self.assertEqual(self.c.memory.regions[p['prep']].extent, 16 * f.prep.CORE_ROW_BYTES)
            self.assertEqual(self.c.memory.regions[p['state']].extent, 16 * 128 * 128 * 4)
            self.assertEqual(self.c.memory.regions[p['prefix']].extent, 32 * 16384)
            for name, base in p.items():
                if name not in ('rows', 'hidden'):
                    region = self.c.memory.regions[base]
                    self.assertEqual(region.raw(), f.d.GUARD * (region.extent // 64))
                    self.assertFalse(region.published or region.written or region.acknowledged)
        with self.assertRaises(ValueError):
            self.c.memory.allocate_output(self.c.plans['cold']['state'] + 64, 64)

    def test_chain_order_real_byte_dependencies_and_actual_carried_pair(self):
        identity = self.c.resource_identity
        self.start()
        self.until(lambda: self.c.response is not None)
        first = self.c.roots
        first_bytes = {name: self.c.memory.regions[getattr(first, name)].raw()
                       for name in ('history', 'state', 'output')}
        self.assertEqual(first.generation, 1)
        self.assertEqual([e[1] for e in self.events], list(f.ORDER))
        self.assertTrue(self.events[-1][2]['block_committed'])
        self.c.start('carry', cold=False, expected_generation=1)
        self.until(lambda: self.c.response is not None)
        self.assertEqual(self.c.roots.generation, 2)
        warm = {role: (job, sources) for phase, role, job, sources in self.c.test_launches if phase == 'carry'}
        self.assertFalse(warm['conv_silu'][0].cold or warm['chunk'][0].cold)
        self.assertEqual(warm['conv_silu'][0].history_in, first.history)
        self.assertEqual(warm['chunk'][0].state_in, first.state)
        self.assertEqual(warm['conv_silu'][1][-1], (first.history, first.history_sha256))
        self.assertEqual(warm['chunk'][1][-1], (first.state, first.state_sha256))
        self.assertEqual(warm['down'][0].k, 3584)
        self.assertEqual(self.c.dense.workspace.split_k, 2560)
        self.assertEqual(identity, self.c.resource_identity)
        for name, raw in first_bytes.items():
            self.assertEqual(self.c.memory.regions[getattr(first, name)].raw(), raw)
        self.assertFalse(self.c.memory.regions[self.c.plan['prefix']].published)
        self.assertFalse(self.c.report()['public_command128_executed'])
        self.assertFalse(self.c.report()['native_acceptance'])

    def test_final_ack_and_terminal_backpressure_block_all_three_publications(self):
        self.start()
        self.final_pending()
        for _ in range(3):
            self.c.tick(memory_response_ready=False)
            self.assert_uncommitted()
        self.c.tick()
        for _ in range(3):
            self.c.tick(response_ready=False)
            self.assert_uncommitted()
        self.c.tick()
        self.assertEqual(self.c.roots.generation, 1)
        for name in ('history', 'state', 'output'):
            self.assertTrue(self.c.memory.regions[self.c.plan[name]].published)

    def test_last_ack_error_never_partially_commits(self):
        self.start()
        self.final_pending()
        self.c.tick(ack_error=True)
        self.c.tick()
        self.assertEqual(self.c.response.status, 'Memory')
        self.assert_uncommitted()
        self.assertTrue(self.c.locked)
        self.assertFalse(self.events[-1][3])

    def test_abort_drains_accepted_final_write_then_requires_reset(self):
        self.start()
        self.final_pending()
        self.c.tick(abort=True, memory_response_ready=False)
        self.assertIsNotNone(self.c.memory.pending)
        with self.assertRaises(ValueError):
            self.c.reset()
        self.c.tick()
        self.c.tick()
        self.assertEqual(self.c.response.status, 'Aborted')
        self.assert_uncommitted()
        with self.assertRaises(ValueError):
            self.c.start('carry', cold=True, expected_generation=0)
        self.c.reset()
        self.assertEqual(self.c.matrix.epoch, 1)
        self.c.start('carry', cold=True, expected_generation=0)
        self.until(lambda: self.c.response is not None)
        self.assertEqual(self.c.roots.generation, 1)

    def test_reset_at_held_final_success_cancels_without_publication(self):
        self.start()
        self.final_pending()
        self.c.tick()
        self.c.tick(reset=True)
        if self.c.response is None:
            self.c.tick()
        self.assertEqual(self.c.response.status, 'Aborted')
        self.assert_uncommitted()

    def test_stale_generation_cold_reentry_and_changed_committed_root_rejected(self):
        with self.assertRaises(ValueError):
            self.c.start('cold', cold=False, expected_generation=0)
        self.start()
        self.until(lambda: self.c.response is not None)
        for cold, generation in ((True, 1), (False, 0), (False, 2)):
            with self.assertRaises(ValueError):
                self.c.start('carry', cold=cold, expected_generation=generation)
        root = self.c.memory.regions[self.c.roots.state]
        root.storage[64] ^= 1
        with self.assertRaisesRegex(ValueError, 'committed root bytes changed'):
            self.c.start('carry', cold=False, expected_generation=1)
        self.assertEqual(self.c.roots.generation, 1)

    def test_missing_history_ack_and_bad_receipt_fail_before_final_acceptance(self):
        self.start()
        self.final_pending()
        self.c.tick()
        history = self.c.memory.regions[self.c.plan['history']]
        history.acknowledged.remove(0)
        with self.assertRaisesRegex(ValueError, 'ACK coverage'):
            self.c.tick()
        self.assert_uncommitted()
        history.acknowledged.add(0)
        receipt = self.c.receipts['chunk']
        self.c.receipts['chunk'] = replace(receipt, expected_generation=7)
        with self.assertRaisesRegex(ValueError, 'staging receipts'):
            self.c.tick()
        self.assert_uncommitted()

    def test_mutated_rms_policy_rejected_between_normalizations(self):
        self.start()
        self.until(lambda: self.c.role == 'attention_residual' and self.c.active is None)
        self.c.policy = f.rms.ReductionPolicy.LegacyAscending
        with self.assertRaisesRegex(ValueError, 'service replaced'):
            self.c.tick()
        self.assert_uncommitted()
        self.assertNotIn('post_norm', [role for _, role, _, _ in self.c.test_launches])

    def test_mutated_vector_policy_rejected_between_commands(self):
        self.start()
        self.c.vector.exception_policy = f.IEEE_POLICY
        self.c.vector.fatal_mask = 28
        with self.assertRaisesRegex(ValueError, 'service replaced'):
            self.c.tick()
        self.assert_uncommitted()

    def test_conv_trace_rejects_duplicate_and_missing_nodes(self):
        self.start()
        self.until(lambda: self.c.role == 'conv_silu' and self.c.active is not None and self.c.active.pending)
        tag = self.c.active.job.tag
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.c._observe_conv(tag, 0, 0, 0x3f80)
        slot = self.c.conv_nodes[tag]
        slot['seen'][-1] = 0
        slot['count'] -= 1
        self.c.tick()
        with self.assertRaisesRegex(ValueError, 'missing actual Conv'):
            self.c.tick()
        self.assert_uncommitted()
        self.assertFalse(self.c.report()['conv_observations'][tag]['complete'])

    def test_staged_state_mutation_rejected_before_commit(self):
        self.start()
        self.final_pending()
        self.c.tick()
        self.c.memory.regions[self.c.plan['state']].storage[64] ^= 1
        with self.assertRaisesRegex(ValueError, 'producer bytes changed'):
            self.c.tick()
        self.assert_uncommitted()

    def test_failed_carried_attempt_keeps_previous_committed_pair(self):
        self.start()
        self.until(lambda: self.c.response is not None)
        roots = self.c.roots
        self.c.start('carry', cold=False, expected_generation=1)
        self.final_pending()
        self.c.tick(ack_error=True)
        self.c.tick()
        self.assertIs(self.c.roots, roots)
        self.assert_uncommitted(1)
        self.assertEqual(self.c.response.history, roots.history)
        self.assertEqual(self.c.response.state, roots.state)


class ReducedFullCoordinatorControlTests(FullCoordinatorControlTests):
    """Same full staging/fence negatives with the selected projection owner.

    Numerical transports remain explicitly synthetic, as in the base suite.
    Actual partial/sum/ordinary/seeded mode switching has its own numerical gate.
    """
    PROJECTION_POLICY = f.ProjectionPolicy.IndependentK512

    def test_profile_is_in_launch_resource_identity(self):
        old = self.c.projection_profile
        self.c.projection_profile = replace(old, pair_reverse=not old.pair_reverse)
        with self.assertRaisesRegex(ValueError, 'shared owner/bank/service replaced'):
            self.start()

    def test_selected_policy_reports_real_owner_and_shared_resources(self):
        from .projection_owner import GdnProjectionOwner, down as wire
        self.assertIs(type(self.c.dense), GdnProjectionOwner)
        self.assertIs(self.c.dense_wire, wire)
        self.assertIs(self.c.dense.tiles.banks, self.c.dense.a_banks)
        report = self.c.report()
        self.assertEqual(report['projection_policy'], self.PROJECTION_POLICY.value)
        self.assertEqual(report['projection_profile']['ranges'], ((0, 512), (512, 1024)))
        self.assertFalse(report['vector_policy_control_bound_to_current_chisel'])


class IdentityReceiptTests(unittest.TestCase):
    def test_invalid_live_resource_report_still_persists_failed_summary(self):
        from . import input_fixture
        from ..qwen2_resident_matrix.ffn_attention import matrix_service
        def rejected_window(*args, **kwargs):
            raise ValueError('last callback changed loaded arithmetic binding')
        def rejected_report():
            raise ValueError('report cannot verify changed resource')
        coordinator = SimpleNamespace(run_window=rejected_window, report=rejected_report,
                                      roots=SimpleNamespace(generation=0))
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            output = Path(directory) / 'failed-run'
            inputs = {name + '.hidden.bf16le': bytes(32768) for name in ('cold128', 'carried128')}
            replacements = ((input_fixture, 'load_fixture', ({'sources': {'layer0_directory': directory}}, inputs)),
                (input_fixture.gdn, 'load_payload', ({}, {})),
                (f.d, 'library_from_environment', Path(directory) / 'not-loaded.so'),
                (f, 'freeze_identity', {}), (f, 'final_identity', {'source_unchanged': True}),
                (f.prep, 'PrepScalar', object()),
                (f.C, 'CDLL', SimpleNamespace(td_reset=lambda: 0)),
                (matrix_service, 'configure_library', SimpleNamespace(td_reset=lambda: 0)),
                (f.d, 'MatrixService', object()), (f, 'FullBlockCoordinator', coordinator))
            for module, name, value in replacements:
                stack.enter_context(patch.object(module, name, return_value=value))
            with self.assertRaisesRegex(ValueError, 'last callback changed'):
                f.run(directory, output, vector=object())
            report = json.loads((output / 'summary.json').read_text())
            self.assertEqual(report['status'], 'FAILED')
            self.assertFalse(report['full_block_executed'])
            self.assertFalse(report['native_acceptance'])
            self.assertFalse(report['live_resource_identity_valid'])
            self.assertIn('last callback changed', report['error']['message'])
            self.assertIn('cannot verify', report['report_error']['message'])
            self.assertFalse((output / 'actual_terminal.json').exists())

    def test_final_identity_retains_missing_file_and_input_failure_details(self):
        from . import input_fixture
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'source.py').write_text('execution source')
            paths = {}
            for name in ('library', 'compile_receipt', 'matrix_compiler', 'vector_library',
                         'vector_compile_receipt', 'vector_compiler', 'fixture_manifest'):
                path = root / name
                path.write_text(name)
                paths[name] = str(path)
            identity = dict(paths, source_sha256={'source.py': f.sha((root / 'source.py').read_bytes())},
                identity_file_sha256={path: f.sha(Path(path).read_bytes()) for path in paths.values()},
                parameter_sha256={'weight': f.sha(b'raw parameter')},
                authenticated_input_sha256={'input': f.sha(b'raw input')})
            fixture = ({'sources': {'layer0_directory': str(root)}}, {'input': b'raw input'})
            with patch.object(input_fixture, 'load_fixture', return_value=fixture), \
                 patch.object(input_fixture.gdn, 'load_payload', return_value=({}, {'weight': b'raw parameter'})):
                result = f.final_identity(identity, root, root)
                self.assertTrue(all(value for name, value in result.items() if name != 'identity_read_errors'))
                Path(paths['vector_library']).unlink()
                result = f.final_identity(identity, root, root)
                self.assertFalse(result['vector_library_unchanged'])
                self.assertTrue(result['library_unchanged'])
                self.assertIn('vector_library_unchanged', result['identity_read_errors'])
                (root / 'source.py').write_text('mutated source')
                self.assertFalse(f.final_identity(identity, root, root)['source_unchanged'])
                fixture[1]['input'] = b'changed raw input'
                self.assertFalse(f.final_identity(identity, root, root)['fixture_unchanged'])

    def test_setup_error_leaves_failed_summary_without_library_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'evidence'
            with self.assertRaises((OSError, ValueError)):
                f.run(Path(directory) / 'missing_fixture', output, vector=object())
            report = json.loads((output / 'summary.json').read_text())
            self.assertEqual(report['status'], 'FAILED')
            self.assertIsNone(report['identity'])
            self.assertIn('error', report)


if __name__ == '__main__':
    unittest.main()
