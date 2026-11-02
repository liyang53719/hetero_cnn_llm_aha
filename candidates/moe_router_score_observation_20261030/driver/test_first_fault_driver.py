"""Exact whole-byte legacy relation; no simulator invoked."""
import importlib.util,pathlib,unittest
D=pathlib.Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location('readonly_driver_inverse',D/'verify_first_fault_driver.py');v=importlib.util.module_from_spec(sp);sp.loader.exec_module(v)
def candidate():return (D/'host_axi_driver_first_fault.cpp').read_bytes()
def original():
 b=candidate()
 for _,add,_ in v.INSERTIONS:
  if b.count(add)!=1:raise ValueError('exact fixture additions')
  b=b.replace(add,b'',1)
 return b
class Test(unittest.TestCase):
 def test_whole_relation(self):
  r=v.verify_driver(original(),candidate());self.assertTrue(r['exact_inverse']);self.assertEqual(r['legacy_driver_sha256'],v.LEGACY_DRIVER_SHA256)
 def test_changed_reset_gate(self):
  with self.assertRaises(ValueError):v.verify_driver(original(),candidate().replace(b'need(!d.io_resetRequired,',b'need(true,'))
 def test_duplicate_addition(self):
  with self.assertRaises(ValueError):v.verify_driver(original(),candidate()+v.INSERTIONS[-1][1])
 def test_extra_clock(self):
  with self.assertRaises(ValueError):v.verify_driver(original(),candidate().replace(b'firstFault.observe(d,',b'd.eval();firstFault.observe(d,'))
 def test_wrong_old_driver(self):
  with self.assertRaises(ValueError):v.verify_driver(original()+b'\n',candidate())
 def test_wrong_bytes_type(self):
  with self.assertRaises(ValueError):v.verify_driver(bytearray(original()),candidate())
if __name__=='__main__':unittest.main()
