"""Cold admission, synthetic control/seals, and tiny original Scalar dispatch.

No full numerical owner transport, native Vector/Matrix arithmetic, checkpoint,
Torch, block/model or RTL execution. Actual-dispatch tests construct real Scalar
and ChunkOwner objects but use explicitly synthetic Matrix/Vector handles and
zero placeholder parameters; only five Scalar exp calls run per selected route.
"""
from collections import Counter
from contextlib import ExitStack, redirect_stdout, redirect_stderr
from copy import deepcopy
from dataclasses import replace
import inspect
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from . import full_driver as f, scalar_identity as s
from . import test_full_driver as control
from .test_scalar_identity import bare, replaced_function_attribute
from ..qwen35_35b_exp.gate_scalar import GateScalar

EXP = f.chunk.ep.EQUAL_HEADS_EXPERIMENTAL_EXP


def vector_gate(policy=f.IEEE_POLICY, mask=28):
    """Exact Vector16 shell for configuration validation ONLY, never native."""
    vector = object.__new__(f.Vector16)
    vector.exception_policy, vector.fatal_mask = policy, mask
    return vector


class FullExpAdmissionColdTests(unittest.TestCase):
    def test_only_exact_selected_scalar_and_literal_flags_admitted(self):
        vector = vector_gate()
        scalar = bare(s.decay.DecayScalar)
        self.assertEqual(f._admit_chunk_scalar(EXP, vector, scalar).report(scalar)['implementation'], 'DecayScalar')
        class Derived(s.decay.DecayScalar):
            pass
        for cls in (s.prep.PrepScalar, GateScalar, Derived):
            with self.subTest(cls=cls.__name__), self.assertRaisesRegex(ValueError, 'exact explicitly enabled DecayScalar'):
                f._admit_chunk_scalar(EXP, vector, bare(cls))
        for flag in ('enable_softplus', 'enable_ieee_exp'):
            for value in (False, 0, 1, None):
                with self.subTest(flag=flag, value=value), patch.object(scalar, flag, value):
                    with self.assertRaises(ValueError):
                        f._admit_chunk_scalar(EXP, vector, scalar)
        with self.assertRaisesRegex(ValueError, 'Softplus-enabled PrepScalar'):
            f._admit_chunk_scalar(f.chunk.ep.LEGACY_EXP, vector, scalar)
        scalar = bare()
        f._admit_chunk_scalar(f.chunk.ep.LEGACY_EXP, vector_gate(f.LEGACY_POLICY, 30), scalar)

    def test_unknown_grouped_policy_and_wrong_vector_never_construct_scalar(self):
        for policy in (f.chunk.ep.IEEE_EXP, 'automatic', None, 1):
            with self.subTest(policy=policy), self.assertRaisesRegex(ValueError, 'explicit legacy or'):
                f._new_chunk_scalar(policy, vector_gate())
        for vector in (vector_gate(f.LEGACY_POLICY, 30), vector_gate(f.IEEE_POLICY, 30),
                       vector_gate(f.IEEE_POLICY, 28.0), None):
            with self.assertRaisesRegex(ValueError, 'IEEE Vector mask 28'):
                f._new_chunk_scalar(EXP, vector)
        with self.assertRaisesRegex(ValueError, 'EQUAL_HEADS'):
            f.chunk.ep.validate_policy(EXP, f.chunk.GROUPED_35B, bare(s.decay.DecayScalar), vector_gate())

    def test_defaults_and_cli_remain_explicit_and_legacy(self):
        for target in (f.FullBlockCoordinator, f.run, f.freeze_identity):
            self.assertEqual(inspect.signature(target).parameters['chunk_exp_policy'].default, f.chunk.ep.LEGACY_EXP)
        for extra, expected in (([], f.chunk.ep.LEGACY_EXP), (['--chunk-exp-policy', EXP], EXP)):
            with patch('sys.argv', ['full_driver', '--fixture', 'unused', '--output', 'unused',
                                    '--vector-library', 'unused', *extra]), \
                 patch.object(f, 'run', return_value={'status': 'ACTUAL_COMPLETE_UNCOMPARED', 'roots': {}}) as run, \
                 redirect_stdout(io.StringIO()):
                self.assertEqual(f.main(), 0)
                self.assertEqual(run.call_args.kwargs['chunk_exp_policy'], expected)
                self.assertEqual(run.call_args.kwargs['vector_exception_policy'], f.LEGACY_POLICY)
                self.assertEqual(run.call_args.kwargs['vector_arithmetic_backend'], f.LEGACY_BACKEND)
                self.assertEqual(run.call_args.kwargs['projection_policy'], f.ProjectionPolicy.Legacy.value)
        with patch('sys.argv', ['full_driver', '--fixture', 'x', '--output', 'x', '--vector-library', 'x',
                                '--chunk-exp-policy', f.chunk.ep.IEEE_EXP]), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                f.main()
            self.assertEqual(error.exception.code, 2)

    def test_routing_callable_code_alias_masks_and_dispatch_are_anchored(self):
        scalar, vector = bare(s.decay.DecayScalar), vector_gate()
        owner = f.chunk.ChunkOwner(scalar, vector, exp_policy=EXP)
        for helper in (f.chunk.ep.operation, f.chunk.ep.validate_policy, f.chunk.ep.identity, f.chunk.ChunkOwner._exp):
            with replaced_function_attribute(helper, '__code__', (lambda *args: None).__code__):
                with self.assertRaisesRegex(ValueError, 'binding changed'):
                    f._admit_chunk_scalar(EXP, vector, scalar)
        for pin in (*s._ROUTE_PINS, *s._CHUNK_ALIAS_PINS, *s._VECTOR_POLICY_PINS):
            with patch.object(pin.owner, pin.name, object()):
                with self.assertRaisesRegex(ValueError, 'binding changed'):
                    s.chunk_exp_routing_identity(f.chunk.ep)
        for value in (30, 28.0):
            with patch.dict(f.chunk.ep.POLICY_MASKS, {f.IEEE_POLICY: value}):
                with self.assertRaisesRegex(ValueError, 'mask contents'):
                    f._admit_chunk_scalar(EXP, vector, scalar)
        with patch.object(owner, '_exp', lambda raw: 0):
            with self.assertRaisesRegex(ValueError, 'resolved ChunkOwner._exp'):
                s.chunk_exp_dispatch_identity(owner)
        s.chunk_exp_dispatch_identity(owner)

    def test_original_owner_job_policy_pair_and_defaults(self):
        scalar, vector = bare(s.decay.DecayScalar), vector_gate()
        owner = f.chunk.ChunkOwner(scalar, vector, exp_policy=EXP)
        job = f.chunk.ChunkJob(1, 0, 1 << 24, 2 << 24, 3 << 24, 4 << 24, 16, exp_policy=EXP)
        job.validate(owner.geometry, owner.layout, owner.cumsum_policy, owner.exp_policy, owner.matmul_policy)
        self.assertIs(owner.scalar, scalar)
        self.assertIs(owner.layout, f.chunk.EQUAL_HEADS)
        self.assertEqual(owner.cumsum_policy, f.chunk.LEGACY_CUMSUM)
        self.assertEqual(owner.matmul_policy, f.chunk.LEGACY_MATMUL)
        with self.assertRaisesRegex(ValueError, 'chunk exp policy identity'):
            replace(job, exp_policy=f.chunk.ep.LEGACY_EXP).validate(
                owner.geometry, owner.layout, owner.cumsum_policy, owner.exp_policy, owner.matmul_policy)

    def test_run_passes_one_selected_scalar_to_snapshot_and_coordinator(self):
        from . import input_fixture
        from ..qwen2_resident_matrix.ffn_attention import matrix_service
        scalar, vector, seen = bare(s.decay.DecayScalar), vector_gate(), []
        identity = dict(arithmetic_seal_schema=f.FULL_ARITHMETIC_SEAL_SCHEMA, scalar_arithmetic_binding=s.ScalarIdentityGuard(scalar).report(scalar),
                        chunk_exp_policy=EXP, chunk_exp_identity=f.chunk.ep.identity(EXP),
                        chunk_cumsum_policy=f.chunk.LEGACY_CUMSUM, chunk_matmul_policy=f.chunk.LEGACY_MATMUL)
        def freeze(*args, **kwargs):
            seen.append(('freeze', kwargs['scalar'], kwargs['chunk_exp_policy']))
            return deepcopy(identity)
        class Coordinator:
            def __init__(self, *args, **kwargs):
                seen.append(('coordinator', kwargs['scalar'], kwargs['chunk_exp_policy']))
                self.roots, self.commands = SimpleNamespace(generation=0), []
            def run_window(self, *args, **kwargs):
                self.roots.generation += 1
                return SimpleNamespace(status=None)
            def report(self):
                return deepcopy(identity)
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            inputs = {name + '.hidden.bf16le': bytes(32768) for name in ('cold128', 'carried128')}
            for module, name, value in (
                    (input_fixture, 'load_fixture', ({'sources': {'layer0_directory': directory}}, inputs)),
                    (input_fixture.gdn, 'load_payload', ({}, {})), (f.d, 'library_from_environment', Path('not-loaded')),
                    (f, '_new_chunk_scalar', scalar), (f, 'final_identity', dict(identity_read_errors={},
                     source_unchanged=True, fixture_unchanged=True, library_unchanged=True, vector_library_unchanged=True)),
                    (f.C, 'CDLL', SimpleNamespace(td_reset=lambda: 0)),
                    (matrix_service, 'configure_library', SimpleNamespace(td_reset=lambda: 0)),
                    (f.d, 'MatrixService', object())):
                stack.enter_context(patch.object(module, name, return_value=value))
            stack.enter_context(patch.object(f, 'freeze_identity', side_effect=freeze))
            stack.enter_context(patch.object(f, 'FullBlockCoordinator', Coordinator))
            result = f.run(directory, Path(directory) / 'result', vector=vector, chunk_exp_policy=EXP)
        self.assertEqual([name for name, _, _ in seen], ['freeze', 'coordinator'])
        self.assertTrue(all(instance is scalar and policy == EXP for _, instance, policy in seen))
        self.assertTrue(result['final_identity']['scalar_arithmetic_binding_unchanged'])
        self.assertTrue(result['final_identity']['chunk_exp_binding_unchanged'])


class _ControlFixture(unittest.TestCase):
    # Reuse setup/helpers, but do NOT inherit or silently repeat the full suite.
    PROJECTION_POLICY = f.ProjectionPolicy.Legacy
    CHUNK_EXP_POLICY = EXP
    ACTUAL_SCALAR = False
    setUpClass = classmethod(control.FullCoordinatorControlTests.setUpClass.__func__)
    setUp = control.FullCoordinatorControlTests.setUp
    tearDown = control.FullCoordinatorControlTests.tearDown
    start = control.FullCoordinatorControlTests.start
    until = control.FullCoordinatorControlTests.until
    final_pending = control.FullCoordinatorControlTests.final_pending
    assert_uncommitted = control.FullCoordinatorControlTests.assert_uncommitted


class ExperimentalFullControlTests(_ControlFixture):
    def test_selected_owner_job_shared_scalar_and_unchanged_other_policies(self):
        self.assertIs(type(self.c.scalar), s.decay.DecayScalar)
        for owner in (self.c.rms, self.c.conv, self.c.prep, self.c.chunk, self.c.norm, self.c.elementwise):
            self.assertIs(owner.scalar, self.c.scalar)
        self.assertEqual(self.c.prep.gate_policy, f.prep.LEGACY_GATE)
        self.assertEqual(self.c.prep.reduction_policy, f.prep.ASCENDING)
        self.assertEqual(self.c.projection_policy, f.ProjectionPolicy.Legacy)
        self.start()
        self.until(lambda: self.c.role == 'chunk' and self.c.active is not None)
        self.assertEqual(self.c.active.job.exp_policy, EXP)
        self.assertEqual(self.c.chunk.exp_policy, EXP)
        self.assertEqual(self.c.active.job.cumsum_policy, f.chunk.LEGACY_CUMSUM)
        self.assertEqual(self.c.active.job.matmul_policy, f.chunk.LEGACY_MATMUL)
        self.assertEqual(sum(self.c.scalar.calls.values()), 0)

    def test_configuration_and_original_dispatch_drift_rejected(self):
        for owner, name, value in ((self.c, 'chunk_exp_policy', f.chunk.ep.LEGACY_EXP),
                (self.c.chunk, 'exp_policy', f.chunk.ep.LEGACY_EXP),
                (self.c.chunk, 'cumsum_policy', f.chunk.GUARDED_CUMSUM),
                (self.c.chunk, 'matmul_policy', f.chunk.ROW4_MATMUL),
                (self.c.chunk, 'layout', f.chunk.GROUPED_35B),
                (self.c.scalar, 'enable_ieee_exp', False), (self.c.scalar, 'enable_ieee_exp', 1),
                (self.c.chunk, '_exp', lambda raw: 0)):
            with self.subTest(name=name), patch.object(owner, name, value):
                with self.assertRaises(ValueError):
                    self.start()
        self.assertFalse(self.c.launched)

    def test_snapshot_rejects_wrong_policy_scalar_and_modified_dispatch_before_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            with patch.object(f, 'verify_library', return_value=(None, None, self.c.vector.backend_identity)):
                for policy, scalar in ((f.chunk.ep.LEGACY_EXP, self.c.scalar), (EXP, bare()),
                                       (f.chunk.ep.IEEE_EXP, self.c.scalar)):
                    with self.assertRaises(ValueError):
                        f.freeze_identity(path, path, {}, {}, path, self.c.vector, path,
                                          scalar=scalar, chunk_exp_policy=policy)
                with patch.object(f.chunk.ChunkOwner, '_exp', lambda *args: 0):
                    with self.assertRaisesRegex(ValueError, 'binding changed'):
                        f.freeze_identity(path, path, {}, {}, path, self.c.vector, path,
                                          scalar=self.c.scalar, chunk_exp_policy=EXP)
            self.assertEqual(list(path.iterdir()), [])

    test_real_driver_admission_only = control.FullCoordinatorControlTests.test_real_driver_constructor_contracts_with_synthetic_admission_only
    test_cold_carried_control_only = control.FullCoordinatorControlTests.test_chain_order_real_byte_dependencies_and_actual_carried_pair
    test_final_joint_commit_not_split = control.FullCoordinatorControlTests.test_final_acceptance_guard_cannot_split_joint_publication
    test_post_commit_mutation_blocks_report = control.FullCoordinatorControlTests.test_final_scalar_callback_cannot_issue_success_report
    test_last_ack_backpressure = control.FullCoordinatorControlTests.test_final_ack_and_terminal_backpressure_block_all_three_publications
    test_last_ack_error = control.FullCoordinatorControlTests.test_last_ack_error_never_partially_commits
    test_abort_and_reset = control.FullCoordinatorControlTests.test_abort_drains_accepted_final_write_then_requires_reset
    test_failed_carried_pair_preserved = control.FullCoordinatorControlTests.test_failed_carried_attempt_keeps_previous_committed_pair


class ActualLegacyDispatchTests(_ControlFixture):
    CHUNK_EXP_POLICY = f.chunk.ep.LEGACY_EXP
    ACTUAL_SCALAR = True

    def test_five_original_raw_words_through_same_selected_owner_scalar(self):
        self.c._check_resources()
        scalar, owner = self.c.scalar, self.c.chunk
        self.assertTrue(scalar.acquire(owner))
        inputs = (0xc2a00000, 0xc2aeac50, 0xc2b72752, 0xc2cff1b4, 0xc2cff1b5)
        expected = (0, 0, 0, 0, 0) if self.CHUNK_EXP_POLICY == f.chunk.ep.LEGACY_EXP else (
            0x05bfecba, 0x007fffe6, 0x0001d7fd, 1, 0)
        try:
            for raw, output in zip(inputs, expected):
                self.assertEqual(owner._exp(raw), output)
                self.c._check_resources()
        finally:
            scalar.release(owner)
        self.assertEqual(scalar.calls[f.chunk.ep.operation(self.CHUNK_EXP_POLICY)], 5)
        self.assertEqual(sum(scalar.calls.values()), 5)
        self.assertEqual(owner.exp_stats['calls'], 5)
        self.assertEqual(owner.exp_stats['saturated_abs_ge_80'], 5 if self.CHUNK_EXP_POLICY == f.chunk.ep.LEGACY_EXP else 0)
        self.assertEqual(self.c.vector.calls, Counter())
        self.assertEqual(self.c.matrix.counts, Counter())
        self.assertFalse(self.c.launched)
        self.assertEqual(self.c.roots.generation, 0)
        report = self.c.report()
        self.assertFalse(report['full_block_executed'])
        self.assertIsNone(report['scalar_arithmetic_binding']['numerical_acceptance'])
        if self.CHUNK_EXP_POLICY == EXP:
            self.assertEqual(scalar.decay_internal_calls, Counter(mul=63, add=45, integer_rne=5))
            self.assertIsNone(report['chunk_exp_identity']['numerical_acceptance'])
            self.assertFalse(report['chunk_exp_identity']['full_block_validated'])


class ActualExperimentalDispatchTests(ActualLegacyDispatchTests):
    CHUNK_EXP_POLICY = EXP


if __name__ == '__main__':
    unittest.main()
