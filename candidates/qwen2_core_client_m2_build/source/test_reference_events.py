"""Small closed-form oracle self-checks, no model or hardware execution."""
import importlib.util,unittest
from fractions import Fraction
from pathlib import Path
s=importlib.util.spec_from_file_location('closed_reference',Path(__file__).with_name('reference_events.py'));r=importlib.util.module_from_spec(s);s.loader.exec_module(r)
class Reference(unittest.TestCase):
 def test_fixed_counts(self):
  for m,g,q,p,mem,score,obs,book in ((1,12,96,96,384,12,408,864),(2,24,192,288,960,36,828,1824),(3,36,288,576,1728,72,1260,2880)):
   x=r.counts(m);self.assertEqual((x['groups'],x['qkAcceptedSteps'],x['pvRequests'],x['memoryAccepted'],x['scoreWrites'],x['observations'],x['accounting512Steps']),(g,q,p,mem,score,obs,book))
 def test_event_cardinalities(self):
  for m in (1,2,3):
   x=r.counts(m);a=list(r.vector_events(m));b=list(r.memory_events(m));c=list(r.pv_events(m));self.assertEqual(len(a),x['observations']);self.assertEqual(len(b),x['memoryAccepted']);self.assertEqual(len(c),x['pvRequests']);self.assertEqual(sum(x['scoreWrite'] for x in a),r.counts(m)['scoreWrites'])
 def test_retirement_order(self):
  a=list(r.vector_events(3))
  for t in range(3):
   for h in range(12):self.assertEqual([x['scoreIndex'] for x in a if x['token']==t and x['head']==h and x['scoreWrite']],list(range(t+1)))
 def test_max_preedge(self):
  for x in r.vector_events(3):self.assertEqual(x['maxScore'],0 if x['phase']==4 and x['selected']>0 else 0xff800000)
 def test_unique_output_and_alignment(self):
  for m in (1,2,3):
   a=list(r.memory_events(m));out=[x['address'] for x in a if x['write']];self.assertEqual(len(out),len(set(out)));self.assertEqual(len(out),96*m);self.assertTrue(all(x['address']%64==0 for x in a));self.assertEqual(sorted(out),list(range(r.DST,r.DST+6144*m,64)))
 def test_no_physical_repeat_tensor(self):
  a=list(r.memory_events(3))
  for kind in ('K','V'):self.assertEqual(len(set(x['address'] for x in a if x['kind']==kind)),48)
 def test_rational_bits(self):self.assertEqual([r.rational_f32_rne(Fraction(1,n)) for n in (1,2,3)],[0x3f800000,0x3f000000,0x3eaaaaab])
 def test_uniform_bf16(self):self.assertEqual([r.uniform_bf16(n) for n in (1,2,3)],[0x3f80,0x3f00,0x3eab])
 def test_pv_boundaries(self):
  for n,x in enumerate(r.pv_events(3)):
   self.assertEqual(x['clear'],x['key']==0);self.assertEqual(x['last'],x['key']==x['token']);self.assertEqual(x['a0'],[0x3f80,0x3f00,0x3eab][x['token']])
 def test_wrong_case_rejected(self):
  for m in (0,4,17,128,True,2.0):
   with self.assertRaises(ValueError):r.counts(m)
 def test_wrong_probability_rejected(self):
  for m in (0,4,True,2.0):
   with self.assertRaises(ValueError):r.uniform_bf16(m)
if __name__=='__main__':unittest.main()
