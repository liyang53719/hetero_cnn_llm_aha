import unittest,numpy as np
from .probe import compare,chunk_inputs
class ProbeTests(unittest.TestCase):
 def test_no_tolerance_or_pass_in_diagnostics(self):
  d=compare(np.array([0,1,2],'<u4'),np.array([1,1,3],'<u4'))
  self.assertIsNone(d['passed']);self.assertIsNone(d['thresholds'])
  self.assertEqual(d['ulp_histogram'],{'0':1,'1':2});self.assertEqual(d['zero_when_reference_positive'],1)
 def test_actual_chunk_exp_input_inventory(self):
  for rows,chunks in [(16,1),(128,2)]:
   inputs,counts,prefix=chunk_inputs(np.full((rows,32),-.5,dtype='<f4'))
   self.assertEqual(prefix.shape,(1,32,chunks,64))
   self.assertEqual(counts,{'chunk_decay':32*chunks,'cumulative':32*chunks*64,'remaining':32*chunks*64,'pairwise':32*chunks*2080})
   self.assertEqual(inputs.size,32*chunks*2209)
   self.assertEqual(float(prefix[0,0,0,-1]),-min(rows,64)*.5)
   self.assertTrue((inputs<=0).all())
if __name__=='__main__':unittest.main()
