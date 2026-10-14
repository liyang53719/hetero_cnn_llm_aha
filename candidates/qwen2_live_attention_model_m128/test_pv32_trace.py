"""Stdlib-only PV32 trace admission; no model imports or arithmetic."""
import contextlib
import io
import json
import unittest
from unittest.mock import patch
from candidates.qwen2_live_attention_model_m128 import pv32_trace as p
class ColdPV32(unittest.TestCase):
    def test_default(self):
        out=io.StringIO()
        with patch.object(p,'dependencies',side_effect=AssertionError('runtime')),contextlib.redirect_stdout(out):self.assertEqual(p.main([]),0)
        self.assertEqual(json.loads(out.getvalue())['status'],'NOT_EXECUTED')
    def test_optin_paths(self):
        for args in (['--out','anything'],['--trace']):
            with self.assertRaises(ValueError):p.main(args)
    def test_width(self):
        for width in (16,32):self.assertEqual(p.validate_width(width),width)
        for width in (0,8,31,33,128,256,True,16.0,'32'):
            with self.assertRaises(ValueError):p.validate_width(width)
    def test_tail(self):
        for count in (1,3,7):self.assertEqual(p.validate_tail(count,7),count)
        for count,length in ((0,7),(8,7),(1,129),(True,7),(1,7.0)):
            with self.assertRaises(ValueError):p.validate_tail(count,length)
if __name__=='__main__':unittest.main()
