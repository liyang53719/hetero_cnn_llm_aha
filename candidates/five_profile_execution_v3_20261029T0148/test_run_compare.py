import importlib.util, pathlib, unittest, struct, tempfile
spec=importlib.util.spec_from_file_location('runner',pathlib.Path(__file__).with_name('run_compare.py'))
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
class Tests(unittest.TestCase):
 def test_nonsquare_cache_permutation(self):
  # H2,T3,D2: distinct byte values catch a mistaken identity or H/D swap.
  data=bytes(range(12));self.assertEqual(r.token_major(data,2,3,2,1),bytes([0,1,6,7,2,3,8,9,4,5,10,11]))
 def test_widen_bits_not_float(self):
  self.assertEqual(r.token_major(bytes.fromhex('807f0180'),1,1,2,2,True),bytes.fromhex('0000807f00000180'))
 def test_shape_fail_closed(self):
  with self.assertRaises(ValueError):r.token_major(b'abc',1,1,2,2)
 def test_mismatch_and_zero(self):
  d=r.compare(b'abc',b'adc');self.assertEqual(d['byte_mismatches'],1);self.assertEqual(d['first_mismatch_byte'],1)
  self.assertEqual(r.compare(b'ab',b'ab')['byte_mismatches'],0)
 def test_missing_byte(self):
  with self.assertRaises(ValueError):r.compare(b'a',b'aa')
 def test_never_accepts_tolerance(self):
  self.assertEqual(r.compare(bytes.fromhex('00000000'),bytes.fromhex('00000080'))['byte_mismatches'],1)
class RouteTests(unittest.TestCase):
 def fixture(self):
  data=bytearray();ids=bytearray();weights=bytearray()
  for t in range(128):
   for k in range(8):
    data.extend(struct.pack('<Q',(t<<34)|(k<<31)|(k<<23)|(0x3e00<<7)|t))
    ids.extend(struct.pack('<q',k));weights.extend(struct.pack('<H',0x3e00))
  return data,ids,weights
 def test_all_routes(self):
  x=r.router_compare(*self.fixture());self.assertEqual(x['ids']['byte_mismatches'],0)
 def test_wrong_id_not_waived(self):
  d,i,w=self.fixture();i[0]=7;self.assertGreater(r.router_compare(d,i,w)['ids']['byte_mismatches'],0)
 def test_missing_route_rejected(self):
  d,i,w=self.fixture()
  with self.assertRaises(ValueError):r.router_compare(d[:-8],i,w)
 def test_wrong_rank_rejected(self):
  d,i,w=self.fixture();d[4]^=1
  with self.assertRaises(ValueError):r.router_compare(d,i,w)
 def test_process_leader_cleanup(self):
  with tempfile.TemporaryDirectory() as p:
   q=pathlib.Path(p)
   self.assertEqual(r.execute(pathlib.Path('/bin/true'),q/'none',q/'out',q/'log',dict(address_space_bytes=134217728,cpu_seconds=2,file_bytes=1048576,max_active_cycles=1,wall_seconds=3)),0)
if __name__=='__main__':unittest.main()
