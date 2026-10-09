"""Small source-bound GDN core layout/carry tests; no checkpoint or RTL run."""
from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import pack_host_bf16_gdn_core_fixture as fixture
from host_bf16_gdn_core_descriptor import parse_host_gdn_core_commands, validate_host_gdn_core_continuation


class GdnCoreFixtureTests(unittest.TestCase):
    def test_layout_uses_public_eight_command_abi_and_real_continuation(self):
        layout = fixture.build_layout()
        bindings = []
        outputs = []
        for token, launch in enumerate(layout['launches']):
            commands = [int(x, 16) for x in launch['packed_commands']]
            records = {i: int(x, 16) for i, x in enumerate(launch['packed_descriptors'])}
            decoded = parse_host_gdn_core_commands(commands, records)
            bindings.append(decoded)
            self.assertEqual(len(commands), 8)
            self.assertEqual(len(records), 113)
            self.assertEqual([b.cold for b in decoded], [not token] * 8)
            self.assertEqual([b.expected_generation for b in decoded], [token] * 8)
            self.assertEqual(decoded[2].d.logical_bytes, 64)
            self.assertEqual(decoded[4].d.logical_bytes, 25600)
            self.assertEqual(decoded[4].aux1.logical_bytes, 32)
            self.assertEqual(decoded[4].aux1.span_bytes, 64)
            self.assertEqual(decoded[5].b.logical_bytes, 1048576)
            self.assertEqual(decoded[6].aux0.logical_bytes, 512)
            for op in launch['operations']:
                outputs.extend((w['address'], w['bytes']) for w in op['writes'])
        validate_host_gdn_core_continuation(*bindings)
        self.assertEqual(layout['launches'][1]['operations'][3]['reads'][2]['producer'], 3)
        self.assertEqual(layout['launches'][1]['operations'][5]['reads'][1]['producer'], 5)
        for index, (a, n) in enumerate(outputs):
            self.assertGreaterEqual(a, layout['scratch'])
            self.assertTrue(all(a + n <= b or b + m <= a for b, m in outputs[:index]))
        self.assertEqual(layout['actual_write_bytes'], 2320512)

    def test_oracle_padding_is_separate_from_actual_dense_work(self):
        self.assertEqual(fixture.ACTUAL_DENSE_MACS, 16842752)
        self.assertEqual(fixture.REFERENCE_FMA_STEPS, 17301504)
        self.assertEqual(fixture.REFERENCE_FMA_STEPS-fixture.ACTUAL_DENSE_MACS, 2*1024*(256-32))

    def test_initialization_inventory_excludes_all_reference_and_native_outputs(self):
        layout = fixture.build_layout()
        names = {x['file'] for x in layout['inputs']}
        self.assertEqual(len(names), 11)
        self.assertFalse(any(x.startswith(('expected_', 'native_')) for x in names))
        self.assertEqual({x for x in names if 'activation' in x}, {'activation0.bf16le', 'activation1.bf16le'})
        self.assertEqual({x for x in names if x.startswith('initial_')}, {'initial_history.bf16le', 'initial_state.f32le'})

    def test_prep_offsets_state_precision_and_independent_carry(self):
        qkv = fixture.bf16(np.linspace(-.2, .3, 6144, dtype='<f4')).reshape(1, 6144)
        projected = dict(qkv=qkv, z=fixture.bf16(np.full((1, 2048), .25, dtype='<f4')),
                         ab=np.zeros((1, 32), dtype='<u2'))
        conv_weight = np.zeros((6144, 4), dtype='<u2'); conv_weight[:, -1] = 0x3f80
        args = (projected, conv_weight, np.zeros(16, '<f4'), np.zeros(16, '<u2'), np.ones(128, '<f4'))
        cold = fixture.canonical_chain(*args, token=0)
        state_before = cold['state'].copy()
        warm = fixture.canonical_chain(*args, token=1, history=cold['history'], state=cold['state'])
        self.assertEqual(cold['prep'].shape, (6400,))
        self.assertEqual(cold['state'].shape, (16, 128, 128))
        self.assertEqual(cold['state'].dtype, np.dtype('<f4'))
        self.assertEqual(cold['norm'].dtype, np.dtype('<u2'))
        np.testing.assert_array_equal(cold['prep'][4096:6144], fixture.fp(cold['conv'].reshape(-1)[4096:]))
        gates = cold['prep'][6144:].reshape(16, 16)
        self.assertTrue(np.all(gates[:, 2:] == 0))
        self.assertTrue(np.all(gates[:, 0] < 0))
        self.assertTrue(np.all(gates[:, 1] == .5))
        np.testing.assert_array_equal(state_before, cold['state'])
        self.assertGreater(np.max(np.abs(warm['state']-cold['state'])), 0)
        np.testing.assert_array_equal(warm['history'][:, 2], cold['history'][:, 3])
        with self.assertRaisesRegex(ValueError, 'carried'):
            fixture.canonical_chain(*args, token=1)

    def test_diagnostics_do_not_grant_a_stage_or_full_block_gate(self):
        result = fixture.fp32_diagnostics(np.array([0, 1], '<f4'), np.array([0, 2], '<f4'))
        self.assertEqual(result['bit_mismatches'], 1)
        self.assertEqual(result['max_abs'], 1)
        self.assertEqual(result['official_acceptance'], 'UNASSIGNED_DIAGNOSTIC_ONLY_NO_STAGE_THRESHOLD_FROZEN')
        self.assertNotIn('pass', result)

    def test_saved_hashes_or_caller_objects_cannot_issue_source_authority(self):
        with self.assertRaises(TypeError):
            fixture.GdnCoreFixtureSession()
        forged = object.__new__(fixture.GdnCoreFixtureSession)
        with self.assertRaisesRegex(ValueError, 'unissued'):
            forged.verify('/tmp')

    def test_frozen_operator_failures_still_block_a_canonical_core(self):
        names = ('qkv', 'z', 'ab', 'conv', 'conv_before_silu')
        canonical = [{name: np.zeros(32, '<u2') for name in names} for _ in range(2)]
        native = [{name: value.copy() for name, value in row.items()} for row in canonical]
        conditioned = [{name: row[name].copy() for name in ('conv', 'conv_before_silu')} for row in canonical]
        self.assertTrue(all(x['passed'] for x in fixture.frozen_operator_metrics(canonical, native, conditioned)))
        native[1]['qkv'][0] = 0x3f80
        result = fixture.frozen_operator_metrics(canonical, native, conditioned)
        self.assertFalse(result[1]['passed'])
        self.assertEqual(result[1]['comparisons']['qkv']['thresholds'], {'max_abs': .03125, 'mean_abs': .005})
        native[1]['qkv'][0] = 0
        conditioned[1]['conv'][0] = 2
        result = fixture.frozen_operator_metrics(canonical, native, conditioned)
        self.assertFalse(result[1]['passed'])
        self.assertEqual(result[1]['comparisons']['silu_same_canonical_input']['max_bf16_ulp'], 2)


if __name__ == '__main__':
    unittest.main()
