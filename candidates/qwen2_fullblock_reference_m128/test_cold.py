#!/usr/bin/env python3
"""CPython3.12 stdlib-only source, metadata and refusal tests; no numeric execution."""
from __future__ import annotations
import ast
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

def module(name,path):
    spec = importlib.util.spec_from_file_location(name,path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

R = module('fullblock_source_recipe',HERE/'recipe.py')
C = module('fullblock_disabled_capture',HERE/'capture.py')


class ColdTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pins = R.load_pins()

    def mutation(self,change,method=R.check_contract):
        pins = copy.deepcopy(self.pins)
        change(pins)
        with self.assertRaises(R.Rejected):
            method(pins)

    def test_01_cold_source_metadata(self):
        value = R.source_check(ROOT,self.pins)
        self.assertEqual((value['model_ast_nodes'],value['activation_ast_nodes'],value['reference_nodes']),(38,14,29))
        self.assertEqual((value['preserved_m128_sources'],value['preserved_m16_sources']),(169,188))
        self.assertFalse(value['raw_payload_read'])
        self.assertFalse(value['producer_payload_read'])

    def test_02_no_numerical_import(self):
        self.assertFalse(set(('torch','numpy','transformers')) & set(sys.modules))

    def test_03_all_outputs_uncaptured(self):
        for value in self.pins['references'].values():
            for key in ('sha256','native_sha256','token_major_sha256','native_stride','storage_offset','is_contiguous'):
                self.assertIsNone(value[key])
        self.assertEqual(len(self.pins['prior18_expectations']),18)

    def test_04_no_fake_freeze(self):
        if R.FROZEN_CONTRACT_SHA256 is None:
            with self.assertRaises(R.Rejected):
                R.require_frozen_references(self.pins)
        else:
            self.assertEqual(R.require_frozen_references(self.pins)['status'],'FROZEN_FROM_INDEPENDENT_REVIEW')
        self.mutation(lambda p:p['reference_freeze'].update(status='FROZEN_FROM_INDEPENDENT_REVIEW'))

    def test_05_wrong_hidden_activation(self):
        self.mutation(lambda p:p['contract'].update(hidden_act='gelu'))

    def test_06_missing_raw13(self):
        self.mutation(lambda p:p['raw_tensors'].pop())

    def test_07_duplicate_raw13(self):
        self.mutation(lambda p:p['raw_tensors'].__setitem__(12,p['raw_tensors'][11]))

    def test_08_missing_role14(self):
        self.mutation(lambda p:p['producer_roles'].pop('wg'))

    def test_09_swapped_tail_role(self):
        p = copy.deepcopy(self.pins)
        p['producer_roles']['wg'],p['producer_roles']['wu'] = p['producer_roles']['wu'],p['producer_roles']['wg']
        with self.assertRaises(R.Rejected):
            R.metadata_check(ROOT,p)

    def test_10_output_inventory_missing(self):
        self.mutation(lambda p:p['references'].pop('cache_v'))

    def test_11_output_hash_placeholder(self):
        self.mutation(lambda p:p['references']['y'].update(sha256='0'*64))

    def test_12_output_geometry(self):
        self.mutation(lambda p:p['references']['gate'].update(shape=[1,16,8960]))

    def test_13_output_dtype(self):
        self.mutation(lambda p:p['references']['silu'].update(native_dtype='torch.float32'))

    def test_14_premature_stride(self):
        self.mutation(lambda p:p['references']['y'].update(native_stride=[196608,1536,1]))

    def test_15_model_delta(self):
        self.mutation(lambda p:p['model_ast_nodes'][-1].update(line_start=781))

    def test_16_model_source_drift(self):
        p = copy.deepcopy(self.pins)
        p['model_ast_nodes'][0]['source_sha256'] = '0'*64
        with self.assertRaises(R.Rejected):
            R.official_nodes(ROOT,p['model_ast_nodes'],R.MODEL_SOURCE,p['sources'])

    def test_17_activation_ast_drift(self):
        p = copy.deepcopy(self.pins)
        p['activation_ast_nodes'][-1]['ast_sha256'] = '0'*64
        with self.assertRaises(R.Rejected):
            R.official_nodes(ROOT,p['activation_ast_nodes'],R.ACTIVATION_SOURCE,p['sources'])

    def test_18_runtime_version_boundary(self):
        with mock.patch.object(R.sys,'version_info',(3,13,0)):
            with self.assertRaises(R.Rejected):
                R.require_supported_python()

    def test_19_strict_json(self):
        for raw in (b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":Infinity}'):
            with self.assertRaises(R.Rejected):
                R.parse(raw)

    def test_20_path_refusal(self):
        for value in ('/tmp/x','../x','work/../x','work//x','work/./x','work\\x'):
            with self.assertRaises(R.Rejected):
                R.safe_path(ROOT,value)

    def test_21_budget_cap(self):
        self.mutation(lambda p:p['budget'].update(total_cap_bytes=70*(1<<20)))
        self.assertEqual(2*self.pins['budget']['payload_bytes_per_capture'],65208320)

    def test_22_no_new_acceptance(self):
        self.mutation(lambda p:p['acceptance'].update(full_29_node_acceptance=True))
        self.mutation(lambda p:p['acceptance'].update(softmax_fp32_passed=True))

    def test_23_direct_capture_hard_refusal_before_arguments(self):
        with self.assertRaises(C.CaptureDisabled):
            C.capture(None,None,None,recipe=None)
        self.assertFalse(set(('torch','numpy','transformers')) & set(sys.modules))

    def test_24_all_cli_execution_refused(self):
        options = [['--action',name] for name in ('bootstrap-capture','capture','audit','actual','rtl','download','compile','ci')]
        options += [['--execute'],['--out','/tmp/forbidden'],['--authorization','approved'],['--reference','anything']]
        for option in options:
            with self.subTest(option=option):
                result = subprocess.run([sys.executable,'-B',str(HERE/'recipe.py'),*option],
                    cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
                self.assertEqual(result.returncode,2)
                self.assertEqual(json.loads(result.stderr)['status'],'REJECTED')
                self.assertIn('SOURCE_ONLY',result.stderr)

    def test_25_default_cold_cli(self):
        result = subprocess.run([sys.executable,'-B',str(HERE/'recipe.py')],cwd=ROOT,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
        self.assertEqual(result.returncode,0,result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value['status'],'NOT_EXECUTED_SOURCE_ONLY')
        self.assertFalse(value['torch_imported'])
        self.assertFalse(value['output_files_written'])

    def test_26_capture_imports_are_below_capability_gate(self):
        tree = ast.parse((HERE/'capture.py').read_text())
        capture = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name == 'capture')
        self.assertIsInstance(capture.body[0],ast.If)
        self.assertIsInstance(capture.body[0].body[0],ast.Raise)
        top_imports = [n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom))]
        names = [a.name for n in top_imports for a in n.names]
        self.assertFalse(set(('torch','numpy','transformers')) & set(names))

    def test_27_official_expressions_remain_whole(self):
        nodes = R.official_nodes(ROOT,self.pins['model_ast_nodes'],R.MODEL_SOURCE,self.pins['sources'])
        mlp = nodes[27]
        forward = next(n for n in mlp.body if isinstance(n,ast.FunctionDef) and n.name == 'forward')
        self.assertEqual(len(forward.body),1)
        self.assertIsInstance(forward.body[0],ast.Return)
        self.assertEqual((nodes[21].lineno,nodes[21].end_lineno),(300,300))

    def test_28_metadata_reads_do_not_open_payloads(self):
        original = Path.open
        header = (ROOT/self.pins['shard']['header']['path']).resolve()
        def guarded(path,*args,**kwargs):
            if path.suffix in ('.bin','.f32le','.bf16le','.npz','.npy') and path.resolve() != header:
                raise AssertionError('payload open forbidden in cold check: '+str(path))
            return original(path,*args,**kwargs)
        with mock.patch.object(Path,'open',guarded):
            R.source_check(ROOT,self.pins)

    def test_29_shape_layout_mask_negative_gates(self):
        self.mutation(lambda p:p['references']['cache_v'].update(shape=[1,128,2,128]))
        self.mutation(lambda p:p.update(layout_rule='choose lowest error'))
        self.mutation(lambda p:p['mask_contract'].update(future_word_u16=0))


if __name__ == '__main__':
    unittest.main(verbosity=2)
