import copy
import hashlib
import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import patch
from candidates.qwen2_fullblock_ci_prepare import initialize_platform as p

class PlatformInitializationTests(unittest.TestCase):
    def test_fixed_original_pin_source(self):
        pins=p.load_pins();self.assertEqual(pins['runtime_requirements']['threads'],4)
        self.assertEqual(set(pins['runtime_native_files']),set(p.inventory.NAMES))
    def test_summary_never_admits_numerics(self):
        native={n:{'bytes':1,'sha256':'a'*64} for n in p.inventory.NAMES}
        runtime=p.load_pins()['runtime_requirements']
        r=p.sanitized_summary(native,runtime,runtime,True)
        self.assertEqual(set(r),p.SUMMARY_KEYS);self.assertFalse(r['numeric_execution_allowed'])
        self.assertFalse(r['model_executed']);self.assertTrue(r['new_python_identity'])
    def test_incompatible_runtime_is_not_pass(self):
        native={n:{'bytes':1,'sha256':'a'*64} for n in p.inventory.NAMES}
        expected=p.load_pins()['runtime_requirements'];actual={**expected,'capability':'AVX2'}
        r=p.sanitized_summary(native,actual,expected,True)
        self.assertEqual(r['status'],'RUNTIME_INITIALIZED_INCOMPATIBLE')
        self.assertFalse(r['expected_runtime_matches']);self.assertFalse(r['numeric_execution_allowed'])
    def test_no_paths_or_metadata_in_native_summary(self):
        native={n:{'bytes':1,'sha256':'a'*64} for n in p.inventory.NAMES}
        native['python']['path']='/forbidden/path'
        with self.assertRaises(ValueError):p.sanitized_summary(native,{}, {},True)
    def test_missing_native_rejected(self):
        with self.assertRaises(ValueError):p.sanitized_summary({}, {},{},True)
    def test_runtime_unknown_nested_and_digest_fields_rejected(self):
        native={n:{'bytes':1,'sha256':'a'*64} for n in p.inventory.NAMES}
        expected=p.load_pins()['runtime_requirements']
        for change in ({'path':'/private'},{'source_pins':{'x':'secret'}},{'torch':{'nested':'bad'}},
                {'torch_commit':'bad'},{'torch_build_sha256':'/private'},{'threads':True},
                {'deterministic_algorithms':1},{'capability':'../private'}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                p.sanitized_summary(native,{**expected,**change},expected,True)
        for value in ('/private',{'nested':'bad'},'a'*63):
            wrong=copy.deepcopy(native);wrong['python']['sha256']=value
            with self.subTest(value=value),self.assertRaises(ValueError):p.sanitized_summary(wrong,expected,expected,True)
        with self.assertRaises(ValueError):p.sanitized_summary(native,expected,expected,1)

    def test_workflow_exact_single_path_and_artifact(self):
        s=(p.ROOT/'.github/workflows/qwen2-fullblock-platform-initialize.yml').read_text()
        self.assertIn('  workflow_dispatch:',s);self.assertIn('  push:',s);self.assertNotIn('  schedule:',s)
        self.assertEqual(s.count('      - .github/workflows/qwen2-fullblock-platform-initialize.yml'),1)
        self.assertIn('    branches: [main]',s)
        self.assertIn('path: work/ci_platform/runtime_summary.json',s)
        self.assertNotIn('**',s);self.assertNotIn('launch.py',s);self.assertNotIn('capture.py',s)
        self.assertIn('--require-hashes',s);self.assertIn('timeout-minutes: 12',s)
if __name__=='__main__':unittest.main()
