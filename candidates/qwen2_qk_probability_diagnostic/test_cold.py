import ast
from pathlib import Path
import sys
import unittest
from candidates.qwen2_qk_probability_diagnostic import model,probe

class ColdTests(unittest.TestCase):
    def test_no_execution(self):
        self.assertNotIn('torch',sys.modules)
        self.assertEqual(probe.run()['status'],'NOT_EXECUTED')
        self.assertNotIn('torch',sys.modules)
    def test_exact_qk_boundaries(self):
        qk,soft,n=model.owner_nodes()
        self.assertEqual(len(qk),4)
        self.assertEqual(ast.unparse(qk[2]),"dot = self._op('bf', total)")
        self.assertIn('1035273459',ast.unparse(qk[3]))
        self.assertIn('exp_negative(self.scalar, self, difference)',ast.unparse(soft[1]))
        self.assertEqual(ast.unparse(n),"probability = self._op('mul', probability, inverse)")
    def test_compile_cold(self):
        self.assertIsNone(model.compile_batch('/tmp/not-created',execute=False))
    def test_not_replacement_matrix(self):
        source=(model.HERE/'native_batch.cpp').read_text()
        self.assertIn('matrix_normal_step(s,0,s==0,last,last,1,a,b,out)',source)
        self.assertNotIn('fmaf(',source)
        self.assertNotIn('std::fma(',source)
    def test_output_scoped(self):
        self.assertEqual(probe.OUT.parent,model.ROOT/'work/qwen2_qk_probability_diagnostic')

if __name__=='__main__':unittest.main()
