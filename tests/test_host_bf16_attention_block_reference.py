"""Small arithmetic/schema/control tests. No compiler, model, or real payload."""
from pathlib import Path
import importlib.util
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

SOURCE = Path(__file__).resolve().parents[1] / 'chisel/continuous_prefill/scripts/host_bf16_attention_block_reference.py'
sys.path.insert(0, str(SOURCE.parent))
import host_bf16_attention_block_reference as ref


class FullBlockCandidateTests(unittest.TestCase):
    def test_source_schema_matches_pinned_57_nodes_and_11_bf16_parameters(self):
        schema = ref.contract_schema()
        self.assertEqual(len(schema['command_order']), 22)
        self.assertEqual(schema['command_order'][1:8],
                         ['q', 'k', 'v', 'norm_q', 'norm_k', 'rope_q', 'rope_k'])
        self.assertEqual(len(schema['producers']), 57)
        self.assertEqual(len(schema['parameters']), 11)
        self.assertEqual(schema['dense_macs_per_token'], 18350080)
        self.assertEqual(schema['native_thresholds'], {'operator': {'max_abs': .03125, 'mean_abs': .005},
                                                      'block': {'max_abs': .05, 'mean_abs': .01}})
        self.assertFalse(schema['production_abi_implemented'])
        self.assertFalse(schema['dut_input_injection'])
        self.assertTrue(schema['expected_only'])
        for k, n in ref.DENSE_SHAPES.values():
            self.assertIn(k, ref.dense.ALLOWED_K)
            self.assertEqual(n % 256, 0)

    def test_model_source_pin_and_dependency_closure(self):
        sources = ref.source_identity()
        self.assertEqual(sources[str(ref.SOURCE_PATH.relative_to(ref.ROOT))], ref.sigmoid.SOURCE_SHA256)
        self.assertIn('chisel/continuous_prefill/scripts/gdn_dense_reference.c', sources)
        self.assertIn('scripts/matrix_norm_rope_reference.c', sources)
        self.assertIn('chisel/continuous_prefill/scripts/attention_sigmoid_reference.py', sources)

    def test_every_node_identifies_actual_canonical_predecessors(self):
        p = ref.predecessor_schema()
        self.assertEqual(set(p), {f'producer_{i:02d}' for i in range(57)})
        self.assertEqual(p['producer_08']['actual_predecessors'], ['producer_07', 'weight_q'])
        self.assertEqual(p['producer_42']['actual_predecessors'], ['raw_hidden', 'producer_41'])
        self.assertEqual(p['producer_56']['actual_predecessors'], ['producer_42', 'producer_55'])
        self.assertIn('canonical_cache_prefix_K', p['producer_33']['actual_predecessors'][1])
        self.assertTrue(all(row['native_intermediate_consumed'] is False for row in p.values()))

    def test_sigmoid_product_must_materialize_bf16_sigmoid_first(self):
        gate = np.array([0x3f00, 0x3f80, 0xbf80], dtype='<u2')
        context = np.array([0x3f81, 0x3f81, 0x3e55], dtype='<u2')
        sig, out = ref.sigmoid_product(gate, context)
        self.assertEqual(sig.tolist(), [0x3f1f, 0x3f3b, 0x3e8a])
        self.assertEqual(out.tolist(), [0x3f20, 0x3f3c, 0x3d66])
        for i in range(3):
            lane = ref.sigmoid.lane(int(gate[i]), int(context[i]))
            single_round = ref.sigmoid.bf16(ref.sigmoid.multiply(lane['steps'][3]['result'], int(context[i]) << 16))
            self.assertNotEqual(single_round, int(out[i]))

    def test_sigmoid_signed_zero_positive_saturation_and_negative_domain(self):
        sig, out = ref.sigmoid_product(np.array([0, 0x8000, 0x42a0], dtype='<u2'),
                                       np.array([0x8000, 0x3f80, 0xbf80], dtype='<u2'))
        self.assertEqual(sig.tolist(), [0x3f00, 0x3f00, 0x3f80])
        self.assertEqual(out.tolist(), [0x8000, 0x3f00, 0xbf80])
        for word in (0xc2a0, 0x7f80, 0x7fc0):
            with self.assertRaises(ValueError):
                ref.sigmoid_product(np.array([word], dtype='<u2'), np.array([0x3f80], dtype='<u2'))

    def test_sigmoid_storage_geometry_fails_closed(self):
        with self.assertRaises(ValueError):
            ref.sigmoid_product(np.ones(2, dtype='<f4'), np.ones(2, dtype='<u2'))
        with self.assertRaises(ValueError):
            ref.sigmoid_product(np.ones(2, dtype='<u2'), np.ones(3, dtype='<u2'))

    def test_rms1024_uses_zero_centered_weight_and_final_bf16(self):
        hidden = ref.rms.bf16(np.linspace(-1.73, 1.29, 1024, dtype='<f4')[None, None])
        weight = ref.rms.bf16(np.linspace(-.73, 1.29, 1024, dtype='<f4'))
        nodes = {}
        result = ref._rms_nodes(hidden, weight, 43, nodes)
        self.assertEqual(set(nodes), set(range(43, 51)))
        np.testing.assert_array_equal(result, ref.rms.bf16(nodes[49]))
        np.testing.assert_array_equal(nodes[48], np.add(np.float32(1), ref.rms.fp(weight), dtype=np.float32))
        early = ref.rms.bf16(np.multiply(ref.rms.fp(ref.rms.bf16(nodes[47])), nodes[48], dtype=np.float32))
        self.assertGreater(np.count_nonzero(early != result), 0)

    def test_native_selection_preserves_weight_axes_and_attention_layout(self):
        q = np.arange(1 * 8 * 128 * 256, dtype='<f4').reshape(1, 8, 128, 256)
        np.testing.assert_array_equal(ref._select_native(q, 38, 1, 1, 2), q[:, :, 1:2])
        scores = np.arange(1 * 8 * 128 * 128, dtype='<f4').reshape(1, 8, 128, 128)
        np.testing.assert_array_equal(ref._select_native(scores, 33, 1, 1, 2), scores[:, :, 1:2, :2])
        gamma = np.ones(256, dtype='<f4')
        np.testing.assert_array_equal(ref._select_native(gamma, 14, 127, 1, 256), gamma)

    def test_authorities_cannot_be_constructed_from_saved_receipts(self):
        for cls in (ref.FullBlockDenseTools, ref.FullBlockReferenceSession):
            with self.assertRaises(TypeError):
                cls()
        with self.assertRaises(ValueError):
            object.__new__(ref.FullBlockDenseTools).verify()
        with self.assertRaises(ValueError):
            object.__new__(ref.FullBlockReferenceSession).select(session=None)
        with self.assertRaises(ValueError):
            ref.prepare_full_block_reference(None, None, None, None)

    def test_new_diagnostics_preserve_native_fail_and_original_operator_limits(self):
        contract = json.loads(ref.CONTRACT_PATH.read_text())
        nodes = {i: np.zeros((1,), dtype='<f4') for i in range(57)}
        report = dict(thresholds=contract['thresholds'], producer_sequence=contract['producer_sequence'],
                      status='BLOCKED_BF16_PRODUCER_GATE', gate_pass=False,
                      comparisons=[dict(case='cold_m128', producer=row['key'], storage_dtype=row['storage_dtype'],
                           max_abs_limit=.03125, mean_abs_limit=.005, pass_=False) for row in contract['producer_sequence']])
        for row in report['comparisons']:
            row['pass'] = row.pop('pass_')
        diagnostics = ref._diagnostics(nodes, nodes, report, 'cold')
        self.assertFalse(report['gate_pass'])
        self.assertTrue(all(row['comparison']['pass'] for row in diagnostics))
        self.assertTrue(all(row['original_native_comparison']['pass'] is False for row in diagnostics))
        self.assertTrue(all(row['diagnostic_only'] for row in diagnostics))
        self.assertIn('UNASSIGNED', diagnostics[38]['acceptance'])
        report['comparisons'][56]['max_abs_limit'] = .05
        with self.assertRaises(ValueError):
            ref._diagnostics(nodes, nodes, report, 'cold')

    def test_all_57_graph_boundaries_and_residual_wiring_with_stubbed_dense(self):
        # This is ONLY graph wiring/schema coverage. Dense and C execution are
        # stubbed explicitly; no independent numerical acceptance is claimed.
        hidden = np.full((1, 1024), 0x4000, dtype='<u2')
        weights = {role: shape for role, shape in ref.DENSE_SHAPES.items()}
        weights.update(input_norm=np.zeros(1024, dtype='<u2'), post_norm=np.zeros(1024, dtype='<u2'),
                       q_gamma=np.zeros(256, dtype='<u2'), k_gamma=np.zeros(256, dtype='<u2'))
        trig = np.concatenate((np.full((1, 32), 0x3f80, dtype='<u2'), np.zeros((1, 32), dtype='<u2')), axis=1)
        calls = []
        def dense_stub(x, shape, executable, scratch):
            self.assertEqual(x.shape, (1, shape[0]))
            calls.append((shape, x.copy()))
            return np.zeros((1, shape[1]), dtype='<u2'), [{'status': 'STUB_CONTROL_ONLY'}]
        with tempfile.TemporaryDirectory() as tmp, patch.object(ref, '_dense_rows', side_effect=dense_stub), \
             patch.object(ref.norm_rope.arithmetic, 'crosscheck_c', return_value={'status': 'STUB_CONTROL_ONLY'}), \
             patch.object(ref, '_crosscheck_gqa', return_value={'status': 'STUB_CONTROL_ONLY'}):
            out, nodes, cache, proof = ref._evaluate_launch(hidden, weights, trig, np.zeros((2, 256, 512), dtype='<f4'),
                0, Path('/unused'), Path('/unused'), {}, Path(tmp))
        self.assertEqual(set(nodes), set(range(57)))
        self.assertEqual(len(calls), 7)
        np.testing.assert_array_equal(calls[0][1], out['input_norm'])
        np.testing.assert_array_equal(calls[3][1], out['sigmoid_mul'])
        np.testing.assert_array_equal(calls[4][1], out['post_norm'])
        np.testing.assert_array_equal(calls[5][1], out['post_norm'])
        np.testing.assert_array_equal(calls[6][1], out['silu_mul'])
        np.testing.assert_array_equal(out['residual1'], hidden)
        np.testing.assert_array_equal(out['residual2'], hidden)
        self.assertTrue(np.all(out['input_norm'] == 0x3f80))
        self.assertTrue(np.all(out['sigmoid'] == 0x3f00))
        self.assertEqual(nodes[33].shape, (1, 8, 1, 1))
        self.assertEqual(nodes[38].shape, (1, 8, 1, 256))
        self.assertEqual(nodes[56].shape, (1, 1, 1024))
        self.assertFalse(np.any(cache))
        self.assertEqual(proof['gqa']['status'], 'STUB_CONTROL_ONLY')


if __name__ == '__main__':
    unittest.main()
