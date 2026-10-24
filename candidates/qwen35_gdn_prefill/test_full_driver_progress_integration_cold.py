"""Actual-module telemetry integration with synthetic nonnumeric transports.

Uses real coordinator/owner metadata and real identity guards, but bare Scalar
and synthetic Matrix/Vector resources. No native-backed constructor or numerical
execution is qualified. The external bounded runner denies native/model math.
"""
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from . import full_driver as f, test_full_driver as control


METADATA_ROWS = []


class _Fixture(unittest.TestCase):
    PROJECTION_POLICY = f.ProjectionPolicy.Legacy
    CHUNK_EXP_POLICY = f.chunk.ep.LEGACY_EXP
    ACTUAL_SCALAR = False
    setUpClass = classmethod(control.FullCoordinatorControlTests.setUpClass.__func__)
    setUp = control.FullCoordinatorControlTests.setUp
    tearDown = control.FullCoordinatorControlTests.tearDown
    until = control.FullCoordinatorControlTests.until

    def test_actual_owner_metadata_for_every_role(self):
        owners = {role: self.c.dense for role in f.DENSE}
        owners.update(input_norm=self.c.rms, post_norm=self.c.rms, conv_silu=self.c.conv,
                      prep=self.c.prep, chunk=self.c.chunk, gated_norm=self.c.norm,
                      attention_residual=self.c.elementwise, silu_mul=self.c.elementwise,
                      output=self.c.elementwise)
        self.assertEqual(set(owners), set(f.ORDER))
        self.c.phase = 'cold'
        for role in f.ORDER:
            owner = owners[role]
            self.c.role, self.c.active = role, SimpleNamespace(owner=owner)
            before = (vars(owner).copy(), self.c.chunk.context.copy())
            snapshot = self.c._progress_snapshot(0.)
            self.assertIs(type(snapshot), f.FullBlockProgress)
            self.assertEqual(snapshot.owner_state, 'idle')
            self.assertIs(type(snapshot.owner_state), str)
            self.assertEqual(snapshot.owner_ticks, None if role in f.DENSE else 0)
            self.assertTrue(all(type(value) in (str, int, float, type(None)) for value in snapshot))
            self.assertEqual(vars(owner), before[0])
            self.assertEqual(self.c.chunk.context, before[1])
            METADATA_ROWS.append(dict(projection=self.PROJECTION_POLICY.value,
                chunk_exp_policy=self.CHUNK_EXP_POLICY, role=role,
                owner_class=type(owner).__module__ + '.' + type(owner).__name__,
                state_type=type(snapshot.owner_state).__name__,
                ticks_type=type(snapshot.owner_ticks).__name__, snapshot=snapshot._asdict()))
        # Use the actual read-only context metadata setter, never a generator or
        # arithmetic tick. Head/subchunk assignments mirror Python range/enumerate.
        self.c.role, self.c.active = 'chunk', SimpleNamespace(owner=self.c.chunk)
        self.c.chunk.context.update(head=15, chunk=1)
        self.c.chunk._phase('state_update_matmul')
        snapshot = self.c._progress_snapshot(1.)
        self.assertEqual((snapshot.chunk_phase, snapshot.chunk_head, snapshot.chunk_subchunk),
                         ('state_update_matmul', 15, 1))
        self.assertIs(type(snapshot.chunk_head), int)
        self.assertIs(type(snapshot.chunk_subchunk), int)
        self.assertEqual(sum(self.c.scalar.calls.values()), 0)
        self.assertEqual(sum(self.c.vector.calls.values()), 0)


class ActualOwnerMetadataTests(_Fixture):
    pass


class ActualProjectionOwnerMetadataTests(_Fixture):
    PROJECTION_POLICY = f.ProjectionPolicy.IndependentK512


class ActualExperimentalOwnerMetadataTests(_Fixture):
    CHUNK_EXP_POLICY = f.chunk.ep.EQUAL_HEADS_EXPERIMENTAL_EXP


class ActualSelectedOwnerMetadataTests(_Fixture):
    PROJECTION_POLICY = f.ProjectionPolicy.IndependentK512
    CHUNK_EXP_POLICY = f.chunk.ep.EQUAL_HEADS_EXPERIMENTAL_EXP


class ActualProgressIntegrationTests(_Fixture):
    def test_actual_scalar_guard_rejects_callback_mutation_before_driver_tick(self):
        def mutate(snapshot):
            self.c.scalar.op = lambda *args: 0
        with self.assertRaisesRegex(ValueError, 'Scalar arithmetic binding changed'):
            self.c.run_window('cold', cold=True, expected_generation=0, progress=mutate)
        self.assertEqual(self.c.ticks, 0)
        self.assertEqual(self.c.commands, [])
        self.assertEqual(self.c.roots.generation, 0)
        self.assertIsNone(self.c.response)

    def test_actual_vector_guard_rejects_callback_mutation_before_driver_tick(self):
        def mutate(snapshot):
            self.c.vector.resource_address += 1
        with self.assertRaisesRegex(ValueError, 'binding changed|service replaced'):
            self.c.run_window('cold', cold=True, expected_generation=0, progress=mutate)
        self.assertEqual(self.c.ticks, 0)
        self.assertEqual(self.c.commands, [])
        self.assertEqual(self.c.roots.generation, 0)
        self.assertIsNone(self.c.response)

    def test_progress_outside_actual_preflight_and_joint_commit(self):
        events, snapshots = [], []
        preflight, commit = self.c._preflight_commit, self.c._commit
        def checked_preflight(held):
            events.append('preflight')
            preflight(held)
        def checked_commit():
            events.append('commit')
            commit()
        def progress(snapshot):
            events.append('progress')
            snapshots.append(snapshot)
        # Test instrumentation only; production code does not patch methods.
        times = iter(float(i) for i in range(150))
        with patch.object(self.c, '_preflight_commit', side_effect=checked_preflight), \
             patch.object(self.c, '_commit', side_effect=checked_commit), \
             patch.object(f.time, 'monotonic', side_effect=lambda: next(times)):
            result = self.c.run_window('cold', cold=True, expected_generation=0,
                progress=progress, progress_interval_seconds=1)
        self.assertIsNone(result.status)
        self.assertEqual(self.c.roots.generation, 1)
        self.assertEqual(len(self.c.commands), 16)
        index = events.index('preflight')
        self.assertEqual(events[index:index + 2], ['preflight', 'commit'])
        self.assertTrue(snapshots)
        self.assertEqual([r['role'] for r in self.c.commands], list(f.ORDER))

    def test_real_run_writes_failed_summary_when_progress_raises_without_commit(self):
        from . import input_fixture
        from ..qwen2_resident_matrix.ffn_attention import matrix_service
        self.c.plans = {'cold128': self.c.plans['cold'], 'carried128': self.c.plans['carry']}
        def broken(snapshot):
            self.assertIs(type(snapshot), f.FullBlockProgress)
            raise RuntimeError('explicit progress exception')
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            output = Path(directory) / 'failed-run'
            inputs = {name + '.hidden.bf16le': bytes(32768) for name in ('cold128', 'carried128')}
            replacements = ((input_fixture, 'load_fixture', ({'sources': {'layer0_directory': directory}}, inputs)),
                (input_fixture.gdn, 'load_payload', ({}, {})),
                (f.d, 'library_from_environment', Path(directory) / 'not-loaded.so'),
                (f, 'freeze_identity', {}), (f, 'final_identity', {'source_unchanged': True}),
                (f, '_new_chunk_scalar', self.c.scalar),
                (f.C, 'CDLL', SimpleNamespace(td_reset=lambda: 0)),
                (matrix_service, 'configure_library', SimpleNamespace(td_reset=lambda: 0)),
                (f.d, 'MatrixService', self.c.matrix), (f, 'FullBlockCoordinator', self.c))
            for module, name, value in replacements:
                stack.enter_context(patch.object(module, name, return_value=value))
            with self.assertRaisesRegex(RuntimeError, 'explicit progress exception'):
                f.run(directory, output, vector=self.c.vector, progress=broken,
                      budget_seconds=10800, window_budget_seconds=7200)
            report = json.loads((output / 'summary.json').read_text())
            self.assertEqual(report['status'], 'FAILED')
            self.assertEqual(report['roots']['generation'], 0)
            self.assertEqual(report['commands'], [])
            self.assertIsNone(report['response'])
            self.assertEqual(self.c.ticks, 0)
            self.assertFalse((output / 'actual_terminal.json').exists())
