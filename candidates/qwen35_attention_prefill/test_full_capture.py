"""Small capture/coverage/failure-retention checks, no model workload or RTL."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import fnmatch
import re
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from . import full_compare as compare, full_fixture as fixture, run_fullblock as runner


def native_events():
    contract = compare.load_contract()
    manifest, case = {'tensors': {}}, {'dispatch_events': []}
    for index, entry in enumerate(contract['producer_sequence']):
        module, op, occurrence = entry['key'].split('|')
        dtype = {'float32': 'F32', 'bfloat16': 'BF16'}[entry['storage_dtype']]
        if op == 'cast_bf16':
            op = 'aten.to.dtype' if module == 'self_attn' else 'aten.type_as.default'
        key = 'native' + str(index)
        manifest['tensors'][key] = dict(dtype=dtype)
        case['dispatch_events'].append(dict(index=index, module=module, op=op, result={'tensor': key}))
    return manifest, case, contract


class FullCaptureTests(unittest.TestCase):
    def test_complete_execution_freeze_and_workflow_paths(self):
        text = (runner.ROOT / '.github/workflows/qwen35-attention-prefill-model.yml').read_text()
        paths = re.findall(r"^      - '([^']+)'$", text, re.M)
        self.assertIn('candidates/qwen35_gdn_prefill/dense_prefix.py', runner.SOURCE_FILES)
        self.assertTrue(all(any(fnmatch.fnmatchcase(name, pattern) for pattern in paths)
                            for name in runner.SOURCE_FILES))
        known = SimpleNamespace(__file__=str(runner.ROOT / 'candidates/qwen35_gdn_prefill/dense_prefix.py'))
        absent = SimpleNamespace(__file__=str(runner.ROOT / 'candidates/unfrozen_execution_dependency.py'))
        with patch.dict(runner.sys.modules, {'known': known}, clear=True):
            runner.require_loaded_source_closure()
            runner.sys.modules['absent'] = absent
            with self.assertRaisesRegex(ValueError, 'unfrozen_execution_dependency'):
                runner.require_loaded_source_closure()

    def test_native_inventory_keeps_all_original_keys_and_rejects_drift(self):
        manifest, case, contract = native_events()
        result = compare.producer_references(manifest, case, contract)
        self.assertEqual(list(result), [p['key'] for p in contract['producer_sequence']])
        for mutation in ('missing', 'duplicate', 'dtype', 'order'):
            m, c = deepcopy(manifest), deepcopy(case)
            if mutation == 'missing': c['dispatch_events'].pop(3)
            elif mutation == 'duplicate': c['dispatch_events'].insert(3, deepcopy(c['dispatch_events'][3]))
            elif mutation == 'dtype': m['tensors']['native0']['dtype'] = 'BF16'
            else: c['dispatch_events'][0], c['dispatch_events'][1] = c['dispatch_events'][1], c['dispatch_events'][0]
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                compare.producer_references(m, c, contract)

    def test_observation_inventory_requires_every_actual_node(self):
        observed = compare.FullObservations(1, 2)
        with self.assertRaisesRegex(ValueError, 'incomplete actual RMS'):
            observed.arrays()
        for role in observed.rms:
            cb = observed.rms_callback(role)
            for stage, width in compare.RMS_WIDTHS.items(): cb(stage, 0, (0,) * width)
        with self.assertRaisesRegex(ValueError, 'incomplete actual activation'):
            observed.arrays()
        for role, width in (('sigmoid', 2048), ('silu', 3584)):
            cb = observed.activation_callback(role)
            for index in range(width): cb(index, 0, 0)
        with self.assertRaisesRegex(ValueError, 'incomplete actual GQA'):
            observed.arrays()
        for stage, array in observed.gqa.items():
            for head in range(8): observed.gqa_callback(stage, 0, head, 0, (0,) * array.shape[-1])
        arrays = observed.arrays()
        self.assertEqual(arrays['input_norm.gamma'].shape, (1024,))
        self.assertEqual(arrays['silu'].shape, (1, 1, 3584))
        self.assertEqual(arrays['qk_bf16'].shape, (1, 8, 1, 2))
        arrays['qk_bf16'][...] = 1
        self.assertTrue((observed.gqa['qk_bf16'] == 0).all())

    def test_duplicate_partial_width_and_out_of_range_are_rejected(self):
        observed = compare.FullObservations(1, 2)
        cb = observed.rms_callback('input_norm'); cb('mean', 0, (1,))
        for args in (('mean', 0, (1,)), ('squares', 0, (1,)), ('mean', True, (1,)), ('mean', 0, (True,))):
            with self.assertRaises(ValueError): cb(*args)
        ab = observed.activation_callback('sigmoid'); ab(0, 0, 0)
        for args in ((0, 0, 0), (2048, 0, 0), (True, 0, 0), (1, 0, 65536)):
            with self.assertRaises(ValueError): ab(*args)
        observed.gqa_callback('qk_bf16', 0, 0, 0, (1,))
        for args in (('qk_bf16', 0, 0, 0, (1,)), ('qk_bf16', 0, 0, 2, (1,)),
                     ('qk_bf16', 0, 0, 1, (True,)), ('qk_bf16', 1, 0, 1, (1,))):
            with self.assertRaises(ValueError): observed.gqa_callback(*args)

    def test_tail_fullshape_dtype_extent_required(self):
        rows = 16
        modules = {module: dict(output={'result': {'tensor': role}}) for role, module in fixture.MODULES.items()}
        modules['post_attention_layernorm']['input'] = {'args': [{'tensor': 'attention_residual'}]}
        modules['self_attn.o_proj']['input'] = {'args': [{'tensor': 'gated_context'}]}
        modules['mlp.down_proj']['input'] = {'args': [{'tensor': 'silu_mul'}]}
        roles = (*fixture.MODULES, 'attention_residual', 'gated_context', 'silu_mul', 'output')
        manifest = dict(query_tokens=rows, tensors={role: dict(dtype='BF16', shape=[1, rows, fixture.WIDTHS[role]],
                        bytes=rows * fixture.WIDTHS[role] * 2) for role in roles})
        case = dict(module_boundaries=modules, output='output')
        self.assertEqual(set(fixture.select_tail_references(manifest, case)), set(roles))
        for change in ({'shape': [1, 1, 1024]}, {'dtype': 'F32'}, {'bytes': rows * 1024}):
            changed = deepcopy(manifest); changed['tensors']['output'].update(change)
            with self.assertRaises(ValueError): fixture.select_tail_references(changed, case)

    def test_partial_capture_never_pads_unobserved_words(self):
        observed = compare.FullObservations(1, 2)
        observed.gqa_callback('qk_bf16', 0, 2, 1, (0x3f800000,))
        observed.rms_callback('input_norm')('mean', 0, (0x80000000,))
        observed.activation_callback('sigmoid')(7, 0x3f000000, 0x3f00)
        norms = {key: {} for key in ('q_norm', 'k_norm', 'q_rope', 'k_rope')}
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            items = runner.save_observations(out, 'partial', norms, observed, partial=True)
            qk = items['qk_bf16']
            self.assertEqual(qk['shape'], [1])
            self.assertEqual(np.frombuffer((out / qk['file']).read_bytes(), '<u4').tolist(), [0x3f800000])
            coords = np.frombuffer((out / qk['coordinates']['file']).read_bytes(), '<u4').reshape(-1, 4)
            self.assertEqual(coords.tolist(), [[0, 2, 0, 1]])
            self.assertEqual(items['input_norm.mean']['tokens'], [0])

    def test_early_failure_preserves_frozen_source_and_is_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'actual'
            with patch.object(runner.fixture, 'load_fixture', side_effect=ValueError('input identity rejected')):
                with self.assertRaisesRegex(ValueError, 'input identity rejected'):
                    runner.run('/unused', '/unused', out, budget_seconds=1)
            report = json.loads((out / 'summary.json').read_text())
            self.assertEqual(report['status'], 'FAILED')
            self.assertFalse(report['full_block_executed'])
            self.assertFalse(report['original_57_producer_contract_accepted'])
            self.assertEqual(report['evidence_preservation_errors'], [])
            self.assertEqual(report['windows'], [])
            for path, digest in report['source_sha256'].items():
                self.assertEqual(runner.sha((out / 'source_snapshot' / path).read_bytes()), digest)
            with self.assertRaisesRegex(ValueError, 'fresh output'):
                runner.run('/unused', '/unused', out, budget_seconds=1)


if __name__ == '__main__': unittest.main()
