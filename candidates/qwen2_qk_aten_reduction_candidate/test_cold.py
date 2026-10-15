from pathlib import Path
import sys
import unittest
from candidates.qwen2_qk_aten_reduction_candidate import model
class ColdTests(unittest.TestCase):
    def test_no_compile(self):
        self.assertIsNone(model.compile_library('/tmp/should-not-exist'))
        self.assertNotIn('numpy',sys.modules);self.assertNotIn('torch',sys.modules)
    def test_source_pins(self):
        self.assertEqual(model.sha(model.OWNER),model.OWNER_SHA)
        self.assertEqual(model.sha(model.EARLIER_KERNEL),model.EARLIER_SHA)
    def test_capacity(self):
        self.assertEqual(model.SCHEDULE['software_partial_words'],64*64)
        self.assertEqual(model.SCHEDULE['software_partial_bytes'],16384)
        self.assertEqual(model.SCHEDULE['hardware_mapping'],'NOT_IMPLEMENTED')
    def test_no_external_oracle_operand(self):
        s=(model.HERE/'kernel.cpp').read_text()
        self.assertNotIn('torch',s);self.assertNotIn('load',s);self.assertNotIn('reference',s)
        self.assertIn('exact_fma(a,',s)
    def test_no_bias_in_projection(self):
        s=(model.HERE/'kernel.cpp').read_text()
        self.assertNotIn('bias[',s);self.assertIn('partial[c][0][0]+0.0f',s)
if __name__=='__main__':unittest.main()
