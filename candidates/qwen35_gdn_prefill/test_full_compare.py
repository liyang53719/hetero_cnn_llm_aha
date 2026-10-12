"""Bounded synthetic file/metric tests. No checkpoint, Torch, owner or RTL run."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from . import full_compare as c


def bf16(values):
    a = np.asarray(values, dtype='<f4').view('<u4')
    return ((a + 0x7fff + ((a >> 16) & 1)) >> 16).astype('<u2').tobytes()


class MetricsTest(unittest.TestCase):
    def test_strict_aggregate_cannot_hide_failure_or_missing_node(self):
        checks = {name: {'passed': True} for name in (*c.ORDER, 'history_staging', 'state_staging')}
        checks['prep'] = dict(passed=None, thresholds=None)
        self.assertTrue(c.assigned_pass(checks, prep_unassigned=True))
        checks['state_staging']['passed'] = False
        self.assertFalse(c.assigned_pass(checks, prep_unassigned=True))
        checks['state_staging']['passed'] = None
        self.assertFalse(c.assigned_pass(checks, prep_unassigned=True))
        del checks['state_staging']
        with self.assertRaisesRegex(ValueError, 'inventory incomplete'):
            c.assigned_pass(checks, prep_unassigned=True)

    def test_prep_cannot_be_given_a_new_pass_gate(self):
        checks = {name: {'passed': True} for name in (*c.ORDER, 'history_staging', 'state_staging')}
        with self.assertRaisesRegex(ValueError, 'no packed prep threshold'):
            c.assigned_pass(checks, prep_unassigned=True)

    def test_signed_zero_bit_mismatch_is_numeric_equal(self):
        metric = c.bf16_metric(b'\x00\x80', b'\x00\x00', gate='ulp')
        self.assertTrue(metric['passed'])
        self.assertEqual(metric['max_bf16_ulp'], 0)
        self.assertEqual(metric['bit_mismatches'], 1)
        self.assertEqual(metric['signed_zero_only_mismatches'], 1)

    def test_original_node_max_and_mean_are_both_gates(self):
        reference = bf16(np.zeros(100))
        values = np.zeros(100)
        values[0] = .03125
        self.assertTrue(c.bf16_metric(bf16(values), reference)['passed'])
        values[0] = .0315
        self.assertFalse(c.bf16_metric(bf16(values), reference)['passed'])
        self.assertFalse(c.bf16_metric(bf16(np.full(100, .0078125)), reference)['passed'])
        self.assertTrue(c.bf16_metric(bf16(np.full(100, .00390625)), reference)['passed'])

    def test_final_output_retains_original_wider_gate_only(self):
        values = np.zeros(100)
        values[0] = .04
        self.assertTrue(c.bf16_metric(bf16(values), bf16(np.zeros(100)), gate='output')['passed'])
        self.assertFalse(c.bf16_metric(bf16(values), bf16(np.zeros(100)))['passed'])
        values[0] = .0501
        self.assertFalse(c.bf16_metric(bf16(values), bf16(np.zeros(100)), gate='output')['passed'])
        self.assertFalse(c.bf16_metric(bf16(np.full(100, .015625)), bf16(np.zeros(100)), gate='output')['passed'])

    def test_conv_one_ulp_frozen(self):
        reference = np.array([0x3f80], '<u2').tobytes()
        self.assertTrue(c.bf16_metric(np.array([0x3f81], '<u2').tobytes(), reference, gate='ulp')['passed'])
        self.assertFalse(c.bf16_metric(np.array([0x3f82], '<u2').tobytes(), reference, gate='ulp')['passed'])
        with self.assertRaisesRegex(ValueError, 'unknown frozen gate'):
            c.bf16_metric(reference, reference, gate='relaxed')

    def test_fp32_gate_is_every_element_absolute_plus_relative(self):
        reference = np.array([0, 1, -1], '<f4')
        within = np.array([.00009999, 1.00019, -.99981], '<f4')
        outside = within.copy()
        outside[0] = .00010001
        self.assertTrue(c.state_metric(within.tobytes(), reference.tobytes())['passed'])
        metric = c.state_metric(outside.tobytes(), reference.tobytes())
        self.assertFalse(metric['passed'])
        self.assertEqual(metric['mismatches'], 1)
        self.assertEqual(metric['thresholds'], {'atol': 1e-4, 'rtol': 1e-4})

    def test_metric_shape_nonfinite_and_empty_rejected(self):
        for a, b in ((b'', b''), (b'\0\0', b'\0\0\0\0'), (b'\x80\x7f', b'\0\0')):
            with self.assertRaises(ValueError):
                c.bf16_metric(a, b)
        with self.assertRaises(ValueError):
            c.state_metric(np.array([np.nan], '<f4').tobytes(), bytes(4))

    def test_frozen_source_hashes_match_original(self):
        c.verify_source_hashes(c.GATE_SOURCES, c.ROOT)


class FileFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.records = {}

    def tensor(self, key, value, shape, dtype='BF16'):
        filename = str(len(self.records)) + '.bin'
        raw = value if isinstance(value, bytes) else np.asarray(value, '<u2' if dtype == 'BF16' else '<f4').tobytes()
        (self.root / filename).write_bytes(raw)
        self.records[key] = dict(file=filename, shape=list(shape), dtype=dtype, bytes=len(raw), sha256=c.sha(raw))
        return raw

    def store(self):
        return c.NativeTensors(self.root, self.records)


class NativeFilesTest(FileFixture):
    def test_ab_uses_whole_separate_a_b_projections_in_column_order(self):
        a = np.arange(256, dtype='<u2').reshape(16, 16)
        b = a + 1000
        self.tensor('cold16.module.linear_attn.in_proj_a.result', a, [1, 16, 16])
        self.tensor('cold16.module.linear_attn.in_proj_b.result', b, [1, 16, 16])
        raw = c.native_role(self.store(), 'cold16', 'ab', 16)
        np.testing.assert_array_equal(np.frombuffer(raw, '<u2').reshape(16, 32), np.concatenate((a, b), axis=1))

    def test_conv_channel_major_warm_full_output_selects_last_m(self):
        values = np.arange(6144 * 20, dtype=np.uint32).astype('<u2').reshape(1, 6144, 20)
        self.tensor('carried16.causal_conv1d_fn.output', values, values.shape)
        raw = c.native_role(self.store(), 'carried16', 'conv_silu', 16)
        np.testing.assert_array_equal(np.frombuffer(raw, '<u2').reshape(16, 6144), values[0, :, -16:].T)

    def test_original_chunk_is_one_full_m128_output(self):
        raw = self.tensor('cold128.chunk0.output', bytes(128 * 2048 * 2), [1, 128, 16, 128])
        self.assertEqual(c.native_role(self.store(), 'cold128', 'chunk', 128), raw)
        with self.assertRaisesRegex(ValueError, 'shape/dtype'):
            c.native_role(self.store(), 'cold128', 'chunk', 16)

    def test_residual_and_silu_mul_exact_boundary_mappings(self):
        residual = self.tensor('cold16.module.post_attention_layernorm.args.0', bytes(16 * 1024 * 2), [1, 16, 1024])
        silu = self.tensor('cold16.module.mlp.down_proj.args.0', bytes(16 * 3584 * 2), [1, 16, 3584])
        store = self.store()
        self.assertEqual(c.native_role(store, 'cold16', 'attention_residual', 16), residual)
        self.assertEqual(c.native_role(store, 'cold16', 'silu_mul', 16), silu)

    def test_missing_node_remains_missing(self):
        with self.assertRaises(c.MissingNode):
            c.native_role(self.store(), 'cold16', 'down', 16)
        metric = c.missing_metric(c.MissingNode('down not captured'), b'\0\0')
        self.assertEqual(metric['status'], 'MISSING')
        self.assertFalse(metric['passed'])
        self.assertIsNone(metric['native_sha256'])

    def test_corruption_missing_file_and_path_escape_fail(self):
        self.tensor('x', b'\0\0', [1])
        (self.root / '0.bin').write_bytes(b'\x01\0')
        with self.assertRaisesRegex(ValueError, 'bytes/hash'):
            self.store()
        (self.root / '0.bin').unlink()
        with self.assertRaisesRegex(ValueError, 'missing file'):
            self.store()
        self.records['x']['file'] = '../outside.bin'
        with self.assertRaisesRegex(ValueError, 'path escape'):
            self.store()

    def test_equal_element_count_does_not_allow_shape_shortcut(self):
        self.tensor('cold16.module.linear_attn.norm.result', bytes(16 * 2048 * 2), [1, 16, 2048])
        with self.assertRaisesRegex(ValueError, 'shape/dtype'):
            c.native_role(self.store(), 'cold16', 'gated_norm', 16)

    def test_dtype_and_byte_extent_must_agree(self):
        self.tensor('x', bytes(4), [1], 'F32')
        with self.assertRaisesRegex(ValueError, 'shape/dtype'):
            self.store().get('x', [1], 'BF16')
        self.records['x']['shape'] = [2]
        with self.assertRaisesRegex(ValueError, 'byte count'):
            self.store()

    def test_prep_stays_unassigned_despite_zero_differences(self):
        for name, shape, dtype in (('value', [1, 16, 16, 128], 'BF16'),
                                    ('g', [1, 16, 16], 'F32'), ('beta', [1, 16, 16], 'BF16')):
            self.tensor('cold16.chunk0.' + name, bytes(int(np.prod(shape)) * (4 if dtype == 'F32' else 2)), shape, dtype)
        report = c.prep_diagnostic(bytes(16 * 6400 * 4), self.store(), 'cold16', 16)
        self.assertIsNone(report['passed'])
        self.assertIsNone(report['thresholds'])
        self.assertIsNone(report['native_sha256'])
        self.assertFalse(report['packed_native_boundary_observed'])
        for metric in report['captured_components'].values():
            self.assertIsNone(metric['passed'])
            self.assertEqual(metric['max_abs'], 0)


class NativeContinuityTest(FileFixture):
    def setUp(self):
        super().setUp()
        self.inputs, cases = {}, []
        for index, phase in enumerate(('cold16', 'carried16')):
            input_raw = self.tensor(phase + '.input', bytes(16 * 1024 * 2), [1, 16, 1024])
            self.inputs[c.PHASES[index]] = input_raw
            qkv = np.full((16, 6144), 0x3f80 + index, '<u2')
            self.tensor(phase + '.module.linear_attn.in_proj_qkv.result', qkv, [1, 16, 6144])
            history = qkv[-4:].T.copy().tobytes()
            state = np.full((1, 16, 128, 128), index + 1, '<f4').tobytes()
            final = dict(conv_state=phase + '.final_cache.conv_state',
                         recurrent_state=phase + '.final_cache.recurrent_state', has_previous_state=True)
            prior = dict(conv_state=None, recurrent_state=None, has_previous_state=False)
            if index:
                prior = dict(conv_state=phase + '.prior_cache.conv_state',
                             recurrent_state=phase + '.prior_cache.recurrent_state', has_previous_state=True)
                self.tensor(prior['conv_state'], previous_history, [1, 6144, 4])
                self.tensor(prior['recurrent_state'], previous_state, [1, 16, 128, 128], 'F32')
                self.tensor(phase + '.chunk0.initial_state', previous_state, [1, 16, 128, 128], 'F32')
                conv_input = np.concatenate((np.frombuffer(previous_history, '<u2').reshape(6144, 4), qkv.T), axis=1)
            else:
                conv_input = qkv.T
            self.tensor(phase + '.causal_conv1d_fn.input', conv_input, [1, 6144, 16 + 4 * index])
            self.tensor(final['conv_state'], history, [1, 6144, 4])
            self.tensor(final['recurrent_state'], state, [1, 16, 128, 128], 'F32')
            self.tensor(phase + '.chunk0.final_state', state, [1, 16, 128, 128], 'F32')
            cases.append(dict(name=phase, input=phase + '.input', prior_cache=prior, final_cache=final,
                chunk_calls=[dict(final_state=phase + '.chunk0.final_state',
                                  initial_state=phase + '.chunk0.initial_state' if index else None)],
                conv_calls=[dict(activation='silu', includes_prior_history=bool(index),
                                 input=phase + '.causal_conv1d_fn.input')]))
            previous_history, previous_state = history, state
        self.manifest = {'cases': cases}

    def test_pure_official_cache_and_conv_boundary_continuity(self):
        c.verify_native_continuity(self.manifest, self.store(), self.inputs, 16)

    def test_changed_pure_official_prior_state_rejected(self):
        store = self.store()
        key = 'carried16.prior_cache.recurrent_state'
        store.raw[key] = bytes(len(store.raw[key]))
        with self.assertRaisesRegex(ValueError, 'prior/final cache discontinuity'):
            c.verify_native_continuity(self.manifest, store, self.inputs, 16)

    def test_changed_chunk_initial_state_rejected(self):
        store = self.store()
        key = 'carried16.chunk0.initial_state'
        store.raw[key] = bytes(len(store.raw[key]))
        with self.assertRaisesRegex(ValueError, 'chunk/cache initial differs'):
            c.verify_native_continuity(self.manifest, store, self.inputs, 16)

    def test_same_shape_wrong_raw_inputs_rejected(self):
        inputs = dict(self.inputs, carried128=bytes([1]) * (16 * 1024 * 2))
        with self.assertRaisesRegex(ValueError, 'raw input differ'):
            c.verify_native_continuity(self.manifest, self.store(), inputs, 16)

    def test_warm_conv_must_use_original_four_sample_history(self):
        store = self.store()
        key = 'carried16.causal_conv1d_fn.input'
        store.raw[key] = bytes(len(store.raw[key]))
        with self.assertRaisesRegex(ValueError, 'own QKV/prior history'):
            c.verify_native_continuity(self.manifest, store, self.inputs, 16)


def make_actual(directory):
    """Only writes bounded synthetic zeros and explicit fake transport receipts."""
    source = directory / 'synthetic_source.py'
    source.write_text('# synthetic test input; never an execution\n')
    digest = c.sha(source.read_bytes())
    identity = dict(rows=16, source_sha256={'synthetic_source.py': digest},
                    identity_file_sha256={str(source): digest},
                    rms_policy='synthetic_fixture', projection_policy='legacy_sequential_k',
                    projection_profile=None, vector_exception_policy='legacy_vector_fatal_underflow',
                    vector_fatal_mask=30)
    files, commands = {}, []
    for phase in c.PHASES:
        for role in c.ROLES:
            raw = bytes(c.byte_extent(role, 16))
            name = c.filename(phase, role)
            (directory / name).write_bytes(raw)
            files[name] = dict(bytes=len(raw), sha256=c.sha(raw))
        for role in c.ORDER:
            item = dict(phase=phase, role=role, complete=True, status=None, terminal_accepted=True,
                        owner_tag=len(commands) + 1, output_sha256=files[c.filename(phase, role)]['sha256'])
            if role == 'conv_silu':
                item.update(staging_complete=True, history_staging_sha256=files[c.filename(phase, 'history_staging')]['sha256'],
                    conv_before_silu_observation=dict(complete=True, output_sha256=files[c.filename(phase, 'conv_before_silu')]['sha256']))
            if role == 'chunk':
                item.update(staging_complete=True, state_sha256=files[c.filename(phase, 'state_staging')]['sha256'])
            commands.append(item)
    history = files[c.filename('cold128', 'history_staging')]['sha256']
    state = files[c.filename('cold128', 'state_staging')]['sha256']
    report = dict(status='ACTUAL_COMPLETE_UNCOMPARED', scope='QWEN35_L0_COMPLETE_TYPED_SOFTWARE_COORDINATOR',
        identity=identity, full_block_executed=True, reset_required=False,
        rms_policy=identity['rms_policy'], projection_policy=identity['projection_policy'],
        projection_profile=None, vector_policy=identity['vector_exception_policy'], vector_fatal_mask=30,
        roots=dict(generation=2, history=64, state=128, output=192, history_sha256=history, state_sha256=state),
        response=dict(status=None, generation=2),
        source_initialization='raw_inputs_and_parameters_only_before_launch',
        carried_dependency='preceding_actual_committed_history_and_fp32_state',
        source_unchanged=True, fixture_unchanged=True, library_unchanged=True, vector_library_unchanged=True,
        final_identity=dict(source_unchanged=True, output_files_unchanged=True, identity_read_errors={}),
        commands=commands, terminal_count=32, output_files=files,
        window_inputs=[dict(phase='cold128', cold=True, expected_generation=0, history_sha256=None, state_sha256=None),
                       dict(phase='carried128', cold=False, expected_generation=1, history_sha256=history, state_sha256=state)])
    (directory / 'identity.json').write_text(json.dumps(identity))
    write_seal(directory, report)
    return report


def write_seal(directory, report):
    for name in ('summary.json', 'actual_terminal.json'):
        (directory / name).write_text(json.dumps(report))


class ActualSealTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.report = make_actual(self.root)

    def load(self):
        return c.load_actual(self.root, root=self.root)

    def test_complete_synthetic_file_seal_loads(self):
        report, actual, digest = self.load()
        self.assertEqual(report['terminal_count'], 32)
        self.assertEqual(len(actual['cold128']), 19)
        self.assertEqual(digest, c.sha((self.root / 'summary.json').read_bytes()))

    def test_only_exact_sealed_summary_allowed(self):
        (self.root / 'summary.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'sealed actual terminal'):
            self.load()

    def test_failed_actual_does_not_read_native_or_run_any_reference(self):
        self.report['status'] = 'FAILED'
        write_seal(self.root, self.report)
        with patch.object(c, 'validate_manifest') as native, patch.object(c.conv_reference, 'native_conv') as conv:
            with self.assertRaisesRegex(ValueError, 'completion'):
                c.compare_run(self.root, self.root.parent / 'absent_native/manifest.json', self.root / 'unused',
                              self.root.parent / ('comparison_' + self.root.name + '.json'), root=self.root)
            native.assert_not_called()
            conv.assert_not_called()

    def test_missing_terminal_rejected(self):
        self.report['commands'].pop()
        write_seal(self.root, self.report)
        with self.assertRaisesRegex(ValueError, '32 ordered terminals'):
            self.load()

    def test_failed_or_unaccepted_terminal_rejected(self):
        self.report['commands'][7]['status'] = 'NumericFault'
        write_seal(self.root, self.report)
        with self.assertRaisesRegex(ValueError, 'owner terminal'):
            self.load()

    def test_wrong_actual_prior_root_rejected(self):
        self.report['window_inputs'][1]['state_sha256'] = '0' * 64
        write_seal(self.root, self.report)
        with self.assertRaisesRegex(ValueError, 'preceding actual root pair'):
            self.load()

    def test_missing_observed_preconv_is_not_fabricated(self):
        self.report['commands'][4]['conv_before_silu_observation']['complete'] = False
        write_seal(self.root, self.report)
        with self.assertRaisesRegex(ValueError, 'pre-SiLU actual observation incomplete'):
            self.load()

    def test_missing_and_corrupt_actual_file_rejected(self):
        path = self.root / c.filename('cold128', 'down')
        path.write_bytes(b'\x01' + path.read_bytes()[1:])
        with self.assertRaisesRegex(ValueError, 'bytes/hash'):
            self.load()
        path.unlink()
        with self.assertRaisesRegex(ValueError, 'missing file'):
            self.load()

    def test_self_consistent_wrong_shape_still_rejected(self):
        name = c.filename('cold128', 'gate')
        raw = bytes(64)
        (self.root / name).write_bytes(raw)
        self.report['output_files'][name] = dict(bytes=len(raw), sha256=c.sha(raw))
        write_seal(self.root, self.report)
        with self.assertRaisesRegex(ValueError, 'actual shape mismatch'):
            self.load()

    def test_source_change_after_completion_rejected(self):
        (self.root / 'synthetic_source.py').write_text('# modified\n')
        with self.assertRaisesRegex(ValueError, 'source identity changed'):
            self.load()

    def test_postlaunch_policy_change_is_not_same_sealed_arithmetic(self):
        for key, changed in (('rms_policy', 'changed'), ('projection_policy', 'changed'),
                             ('projection_profile', {'ranges': [[0, 16], [16, 32]]}),
                             ('vector_policy', 'changed'), ('vector_fatal_mask', 28)):
            old = self.report[key]
            self.report[key] = changed
            write_seal(self.root, self.report)
            with self.assertRaisesRegex(ValueError, 'numerical policy differs from prelaunch'):
                self.load()
            self.report[key] = old


if __name__ == '__main__':
    unittest.main()
