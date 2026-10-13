"""Bounded control boundary before expensive complete QKV; no checkpoint claim."""
import time,unittest
from . import driver as d
from ..qwen35_35b_prefill import test_prefix_driver as original
setUpModule=original.setUpModule
class PrepPrefixTests(unittest.TestCase):
 setUpClass=classmethod(original.PrefixTests.setUpClass.__func__)
 setUp=original.PrefixTests.setUp
 def args(self):
  return dict(tokens=16,windows=(d.ColumnWindow(0,8192),),profile=self.profile,
   matrix=self.matrix,vector=self.vector,deadline=time.monotonic()+30,
   conv_weights=bytes(8192*8),ab_weights={'a':self.nk[:131072],'b':self.nk[:131072]},
   ab_profiles={'a':self.profile,'b':self.profile},a_log=bytes(128),dt_bias=bytes(64))
 def test_rms_error_stops_every_consumer(self):
  seen=[]
  r,m=d.execute_prep_prefix(self.hidden,self.weight,self.nk,**self.args(),observe=lambda *x:seen.append(x),
    controls=lambda stage,i,driver:{'read_error':True})
  self.assertEqual(r['failed_stage'],'input_norm');self.assertEqual(len(r['terminals']),1)
  self.assertEqual(seen,[]);self.assertFalse(any(x.published for x in m.regions.values() if not x.readonly))
 def test_original_full_qkv_extent_required(self):
  a=self.args();a['windows']=(d.ColumnWindow(0,160),)
  with self.assertRaises(ValueError):d.execute_prep_prefix(self.hidden,self.weight,self.nk,**a)
if __name__=='__main__':unittest.main()
