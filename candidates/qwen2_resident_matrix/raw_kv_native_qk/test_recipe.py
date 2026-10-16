"""Source/control checks; never compile or load a native library."""
import ast
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from . import adapter,prepare
from ..raw_kv_native_qkv import prepare as prior


class RecipeTests(unittest.TestCase):
    def composed(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'variant'
            report=prepare.prepare(out)
            return report,(out/prepare.ORIGINAL).read_bytes()

    def test_exact_two_patch_composition(self):
        with patch('ctypes.CDLL',side_effect=AssertionError('native load forbidden')):
            report,generated=self.composed()
        self.assertEqual(report['status'],'PASS_SOURCE_PREPARATION_ONLY')
        self.assertFalse(report['numerical_execution'])
        self.assertEqual(hashlib.sha256(generated).hexdigest(),report['generated_module_sha256'])
        self.assertEqual(len(report['source_sha256']),19)
        self.assertIn(b"round_output(round_output(qk_dot) / math.sqrt(dim))",generated)

    def test_qkv_only_projection_and_enabled_mutation_reject(self):
        _,generated=self.composed()
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'base';prior.prepare(out);base=(out/prior.ORIGINAL).read_bytes()
        prepare.check_scope(base,generated)
        for before,after in ((b'qkv_recipe.qk_dot(q, repeated_k)',b'qkv_recipe.qk_dot(q, repeated_v)'),
                             (b'/ math.sqrt(dim)',b'* math.sqrt(dim)'),
                             (b"qk_dot = qkv_recipe.qk_dot(q, repeated_k)",b"qk_dot = qkv_recipe.qk_dot(q, repeated_k)\n        print(qk_dot)")):
            with self.assertRaises(ValueError):prepare.check_scope(base,generated.replace(before,after))

    def test_exact_recipe_and_canonical_scope(self):
        class Foreign:
            def revalidate(self):raise AssertionError('foreign called')
        for value in (None,Foreign(),object()):
            with self.assertRaises(ValueError):adapter.validate(value,tokens=16,carried=False,threads=4)
        recipe=object.__new__(adapter.Recipe)
        with patch.object(adapter.Recipe,'revalidate') as revalidate,patch.object(adapter.Recipe,'identity',return_value={'fixture':True}):
            self.assertEqual(adapter.validate(recipe,tokens=16,carried=False,threads=4),{'fixture':True})
            for args in ({'tokens':True,'carried':False,'threads':4},
                         {'tokens':16,'carried':0,'threads':4},
                         {'tokens':16,'carried':False,'threads':4.0},
                         {'tokens':128,'carried':True,'threads':4}):
                with self.assertRaises(ValueError):adapter.validate(recipe,**args)
            self.assertEqual(revalidate.call_count,1)

    def test_linear_delegates_original_verified_recipe(self):
        recipe=object.__new__(adapter.Recipe)
        class Old:
            def linear(self,*args):self.args=args;return token
        old=Old();recipe.qkv=old;token=object();args=(object(),object(),object(),'self_attn.q_proj')
        with patch.object(adapter.Recipe,'revalidate') as check:
            self.assertIs(recipe.linear(*args),token)
            self.assertEqual(old.args,args);self.assertEqual(check.call_count,2)

    def test_no_scaled_or_official_qk_input(self):
        tree=ast.parse(Path(adapter.__file__).read_text())
        method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='qk_dot')
        self.assertEqual([x.arg for x in method.args.args],['self','query','repeated_key'])
        names={n.id for n in ast.walk(method) if isinstance(n,ast.Name)}
        self.assertFalse({'torch','native','official','bias','scores','mask'}&names)
        self.assertNotIn('sqrt',ast.unparse(method))

if __name__=='__main__':unittest.main()
