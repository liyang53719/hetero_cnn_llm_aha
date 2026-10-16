"""Source/metadata-only runtime-contract negatives; no producer execution."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from . import runtime as r


class RuntimeTests(unittest.TestCase):
    def test_exact_closed_contract(self):
        result=r.contract_snapshot()
        self.assertEqual(len(result['inputs']),210)
        self.assertEqual(len(result['generated']),10)
        self.assertTrue(result['setup_source_ready'])
        self.assertFalse(result['numerical_launch_ready'])
        self.assertFalse(result['m128_executed'])
        self.assertFalse(result['full_29_node_acceptance'])

    def test_contract_canonicality_and_missing_sources(self):
        raw=r.read_source(r.PINS_PATH,131072); original=r.prior.json_bytes(raw)
        cases=[]
        for key,value in [('rows',True),('past_tokens',False),('setup_budget',900.0),
                          ('work_budget',2401),('enable_raw_kv',1),('status','READY')]:
            v=copy.deepcopy(original);v[key]=value;cases.append(v)
        v=copy.deepcopy(original);v['source_sha256'].pop(next(iter(v['source_sha256'])));cases.append(v)
        v=copy.deepcopy(original);v['generated_sha256'][r.prerequisite.ENTRY]='0'*64
        # Another reviewed hash is not enough: changing an unchanged observer is forbidden.
        observer='scripts/observe_qwen2_attention_model.py';v['generated_sha256'][observer]='0'*64;cases.append(v)
        read=r.read_source
        for value in cases:
            with self.subTest(value=list(value)[:1]),patch.object(r,'read_source',side_effect=lambda n,limit=4194304,v=value:
                    r.prerequisite.encoded(v) if n==r.PINS_PATH else read(n,limit)):
                with self.assertRaises(ValueError):r.contract_value()

    def test_setup_verifier_uses_variant_not_old_base(self):
        _,v=r.contract_value();base=r.base_verifier_sources()
        self.assertEqual(len(base),7)
        self.assertEqual(base[r.prerequisite.ASSETS],v['generated_sha256'][r.prerequisite.ASSETS])
        self.assertNotEqual(base[r.prerequisite.ASSETS],v['source_sha256'][r.prerequisite.ASSETS])
        self.assertNotIn(r.SETUP,r.setup_git_sources())
        self.assertIn(r.PINS_PATH,r.setup_git_sources())

    def test_source_modes_and_numeric_admission_closed(self):
        for mode in (False,1,None,'true'):
            with self.subTest(mode=mode),self.assertRaises(ValueError):r.asset_source_snapshot(enable_raw_kv=mode)
        with patch.object(r,'asset_source_snapshot',return_value={}):
            with self.assertRaisesRegex(ValueError,'launch_layer_missing'):
                r.authorize_run({'rows':128},wall_budget=2400,enable_raw_kv=True,fresh_profile=True)
            for rows in (16,True,128.0):
                with self.subTest(rows=rows),self.assertRaises(ValueError):
                    r.authorize_run({'rows':rows},wall_budget=2400,enable_raw_kv=True,fresh_profile=True)

    def test_equal_asset_setup_map_is_explicit(self):
        expected={'a':'0'*64}
        with patch.object(r,'asset_source_snapshot',return_value=expected):
            self.assertEqual(r.asset_sources(expected),expected)
            for value in ({},dict(expected,b='1'*64),{'a':'1'*64}):
                with self.assertRaises(ValueError):r.asset_sources(value)

    def test_loaded_setup_identity_guard(self):
        with patch.object(r,'contract_snapshot',return_value={'generated':{r.SETUP:'a'*64}}):
            r.verify_loaded_setup('a'*64)
            for value in ('b'*64,True,None):
                with self.assertRaises(ValueError):r.verify_loaded_setup(value)

    def test_source_same_bytes_and_no_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'x').write_bytes(b'x');(root/'link').symlink_to(root/'x')
            with patch.object(r,'ROOT',root),patch.object(r.prior,'ROOT',root):
                self.assertEqual(r.read_source('x'),b'x')
                for path in ('link','../x','/x'):
                    with self.assertRaises(ValueError):r.read_source(path)


if __name__=='__main__':unittest.main()
