"""35B exact source audit and unchanged fixed arithmetic; no Torch import."""
import ast
import unittest
from . import reference as r

class SourceTests(unittest.TestCase):
    def test_same_fallback_ast_distinct_authority(self):
        node,identity=r.source_function()
        old=ast.parse((r.ROOT/r.fixed.SOURCE).read_bytes())
        fn=next(n for n in old.body if isinstance(n,ast.FunctionDef) and n.name=='causal_conv1d_fn')
        self.assertEqual(ast.dump(node,include_attributes=False),ast.dump(fn,include_attributes=False))
        self.assertEqual(identity['source_sha256'],r.rms.SOURCE_SHA)
        self.assertNotEqual(identity['source_sha256'],r.fixed.SOURCE_SHA)
        self.assertFalse(identity['full_block']);self.assertFalse(identity['rtl_executed'])
    def test_8192_channel_admission_and_tiny_zero_reference(self):
        from candidates.qwen35_gdn_prefill.conv.model import ConvJob
        j=ConvJob(1,0x100000,0x400000,0x500000,0x800000,0x900000,128,True,0,channels=8192)
        j.validate(channels=8192)
        self.assertEqual(j.vector_bytes,2097152);self.assertEqual(j.history_bytes,65536)
        raw,identity=r.fixed_conv(bytes(8192*2),bytes(8192*8),1)
        self.assertEqual(raw['conv'],bytes(8192*2));self.assertEqual(raw['history'],bytes(8192*8))
        self.assertFalse(identity['scalar_or_owner_called'])

if __name__=='__main__':unittest.main()
