import sys,unittest,numpy as np
from pathlib import Path
from run import rms,ROOT
sys.path.insert(0,str(ROOT/'round_20261110T0833/legacy_python'))
import legacy_reference as exact
class Order(unittest.TestCase):
 def test_actual_row_exact_order(self):
  p=ROOT/'round_20261110T0833/profile1_real_host_payload'
  x=np.fromfile(p/'input.bin',dtype='<u2').reshape(128,1024)[:1]
  w=np.fromfile(p/'input_gamma.bin',dtype='<u2')
  budget=exact.Budget(20000);parts=[0]*32
  for base in (0,512):
   acc=[0]*32
   for term in range(16):
    for i in range(32):
     a=int(x[0,base+term*32+(i%4)*8+i//4])<<16
     acc[i]=exact.add(acc[i],exact.mul(a,a,budget),budget)
   parts=[exact.add(a,b,budget) for a,b in zip(parts,acc)]
  lanes=[0]*8
  for r in range(4):
   for l in range(8):lanes[l]=exact.add(lanes[l],parts[l*4+r],budget)
  total=0
  for v in lanes:total=exact.add(total,v,budget)
  # Validate reduction exactly; remainder separately uses IEEE numpy nodes.
  from original_prep_reference import fp,add,mul
  xx=fp(x);pp=np.zeros((1,32),dtype='<f4')
  for base in (0,512):
   aa=np.zeros_like(pp)
   for term in range(16):
    ids=[base+term*32+(i%4)*8+i//4 for i in range(32)]
    aa=add(aa,mul(xx[:,ids],xx[:,ids]))
   pp=add(pp,aa)
  ll=np.zeros((1,8),dtype='<f4')
  for r in range(4):ll=add(ll,pp[:,np.arange(8)*4+r])
  ss=np.zeros((1,1),dtype='<f4')
  for l in range(8):ss=add(ss,ll[:,l:l+1])
  self.assertEqual(int(ss.view('<u4')[0,0]),total)
  self.assertEqual(rms(x,w).shape,(1,1024))
 def test_reject_width(self):
  with self.assertRaises(ValueError):rms(np.zeros((1,512),dtype='<u2'),np.zeros(512,dtype='<u2'))
if __name__=='__main__':unittest.main()
