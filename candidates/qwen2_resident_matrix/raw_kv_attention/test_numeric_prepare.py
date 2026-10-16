"""Default discovery runs dependency checks only; numeric execution is opt-in."""
import ast
from dataclasses import dataclass
import json
import os
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path
import unittest
from unittest.mock import patch
from . import numeric_prepare as p

class NumericPreparation(unittest.TestCase):
    def test_frozen_dependency_closure_without_arithmetic(self):
        result=p.check()
        self.assertEqual(result['status'],'PASS_PREPARATION_ONLY')
        self.assertEqual(result['inputs'],52)
        self.assertFalse(result['arithmetic_executed'])
        self.assertFalse(result['hardware_simulation'])

    def test_changed_input_fails_closed(self):
        original=Path.read_bytes
        def changed(path):
            data=original(path)
            return data+b'\n' if str(path).endswith('/official_bf16/owners.py') else data
        with patch.object(Path,'read_bytes',changed):
            with self.assertRaisesRegex(ValueError,'numeric source drift'):
                p.check()

    def test_missing_library_is_not_success_and_does_not_import_arithmetic(self):
        from . import numeric_bridge as bridge
        with patch.dict(os.environ, {}, clear=True), patch.object(bridge,'dependencies',side_effect=AssertionError('must not import')):
            code,result=bridge.run_numeric()
        self.assertEqual(code,2)
        self.assertEqual(result['status'],'NOT_RUN')
        self.assertFalse(result['arithmetic_executed'])

    def test_missing_library_cli_returns_nonzero_without_payload(self):
        env=dict(os.environ);env.pop('MATRIX_SERVICE_LIBRARY',None)
        proc=subprocess.run([sys.executable,'-m','candidates.qwen2_resident_matrix.raw_kv_attention.numeric_bridge'],
                            cwd=p.ROOT,env=env,capture_output=True,text=True,timeout=5)
        self.assertEqual(proc.returncode,2)
        self.assertEqual(proc.stderr,'')
        self.assertEqual(json.loads(proc.stdout)['status'],'NOT_RUN')
        self.assertLess(len(proc.stdout.encode()),512)

    def test_no_arithmetic_owner_method_is_replaced_by_bridge(self):
        tree=ast.parse((p.HERE/'numeric_bridge.py').read_text())
        forbidden={'_attention','_matrix_step','_op','_read','_write'}
        for node in ast.walk(tree):
            if isinstance(node,ast.FunctionDef):self.assertNotIn(node.name,forbidden)
        self.assertFalse(any(isinstance(n,ast.Assert) for n in ast.walk(tree)),
                         'bridge checks must survive -O')

    def test_ddr_decoder_preserves_full_tag_and_error_retirement(self):
        from .numeric_bridge import decode_ddr_response
        from .model import Reply
        @dataclass
        class Beat:
            tag:int
            data:object=None
            error:bool=False
            nbytes:int=64
        tag=(1<<63)+7
        for beat in (Beat(tag,error=True),Beat(tag,b'',nbytes=32),Beat(tag,None),
                     *(Beat(tag,bytes(64),error=value) for value in (1,None,0.0)),
                     *(Beat(tag,bytes(64),nbytes=value) for value in (True,None,64.0,-1))):
            self.assertEqual(decode_ddr_response(beat,Beat),Reply(tag,0,True))
        raw=bytes(range(64))
        self.assertEqual(decode_ddr_response(Beat(tag,raw),Beat),Reply(tag,int.from_bytes(raw,'little')))
        self.assertEqual(decode_ddr_response(Beat(tag,(0x7fc00001,)*16),Beat),
                         Reply(tag,sum(0x7fc00001<<(32*i) for i in range(16))))
        for bad in (True,-1,1<<64,1.0):
            self.assertNotIsInstance(decode_ddr_response(Beat(bad,raw),Beat),Reply)

    def test_late_skip_cannot_claim_numerical_not_run(self):
        from . import numeric_bridge as bridge
        # Control-flow fixture only: no owner, numerical service or native call.
        deps=SimpleNamespace(verified_library=lambda: object())
        with patch.dict(os.environ,{'MATRIX_SERVICE_LIBRARY':'/test-only/no-library'}), \
             patch.object(Path,'is_file',return_value=True), \
             patch.object(bridge,'dependencies',return_value=deps), \
             patch.object(bridge,'compare_case',side_effect=unittest.SkipTest('late')):
            code,result=bridge.run_numeric()
        self.assertEqual(code,1)
        self.assertEqual(result['status'],'FAIL')
        self.assertTrue(result['numerical_run_started'])
        self.assertNotIn('arithmetic_executed',result)

    def test_numeric_anchor_is_original_pv16_owner(self):
        pins=json.loads((p.HERE/'numeric_pins.json').read_text())['inputs']
        for name in ('official_bf16/owners.py','official_bf16/test_owners.py',
                     'ffn_attention/attention_owner.py','ffn_attention/matrix_service.py',
                     'ffn_public/prefix_arithmetic.py','ffn_public/test_prefix_owners.py'):
            self.assertIn('candidates/qwen2_resident_matrix/'+name,pins)
        tree=ast.parse((p.ROOT/'candidates/qwen2_resident_matrix/official_bf16/owners.py').read_text())
        owner=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='OfficialAttentionOwner')
        self.assertEqual([n.name for n in owner.body if isinstance(n,ast.FunctionDef)],['_attention'])

if __name__=='__main__':unittest.main()
