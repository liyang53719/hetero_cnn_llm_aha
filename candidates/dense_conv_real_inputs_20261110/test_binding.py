import unittest,numpy as np
from bind_training_payload import transpose,ab,program
class BindingTest(unittest.TestCase):
 def test_transpose(self):
  a=np.arange(21,dtype='<u2').reshape(3,7)
  self.assertEqual(transpose(transpose(a.tobytes(),[3,7]),[7,3]),a.tobytes())
 def test_ab_order(self):
  a=np.arange(16*1024,dtype='<u2').reshape(16,1024);b=a+16384
  c=np.frombuffer(ab(a.tobytes(),b.tobytes()),dtype='<u2').reshape(1024,32)
  np.testing.assert_array_equal(c[:,:16],a.T);np.testing.assert_array_equal(c[:,16:],b.T)
 def test_real_producer_edges(self):
  b,_=program.common(1);_,_,m=b.finish();s={x['name']:x for x in m['schedule']}
  self.assertEqual(s['conv']['a'],s['qkv']['d']);self.assertEqual(s['rawprep']['a'],s['conv']['d']);self.assertEqual(s['rawprep']['b'],s['ab']['d'])
  for n in ['input_norm','qkv','z','ab','conv','prepared','chunk']:
   self.assertFalse(m['tensors'][n]['readonly'])
 def test_bad_ab(self):
  with self.assertRaises(ValueError):ab(bytes(4),bytes(4))
if __name__=='__main__':unittest.main()
