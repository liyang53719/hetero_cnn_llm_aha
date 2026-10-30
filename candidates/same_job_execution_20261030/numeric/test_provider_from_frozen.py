import json,pathlib,tempfile,unittest
import provider_from_frozen as p
class T(unittest.TestCase):
 def fixture(self,root):
  src=root/'source';src.mkdir();(src/'input_only').mkdir();(src/'input_only/h.bin').write_bytes(b'abc')
  r=dict(profile={'profile':0},complete_block_tokens=128,exact_baseline_observer_output_equal=True,hardware_executed=False,router_policy='UNMODIFIED_OFFICIAL_TORCH_TOPK',tensor_records={'x':dict(file='input_only/h.bin',bytes=3,sha256=p.sha(src/'input_only/h.bin'))})
  (src/'RESULT.json').write_text(json.dumps(r));out=root/'out';out.mkdir();return src,out,r
 def test_copy_exact(self):
  with tempfile.TemporaryDirectory() as t:
   src,out,r=self.fixture(pathlib.Path(t));q=p.copy_reference(p.pin(src/'RESULT.json'),out,0)
   self.assertEqual((q/'input_only/h.bin').read_bytes(),b'abc');self.assertEqual(p.sha(q/'RESULT.json'),p.sha(src/'RESULT.json'))
 def test_tamper(self):
  with tempfile.TemporaryDirectory() as t:
   src,out,r=self.fixture(pathlib.Path(t));(src/'input_only/h.bin').write_bytes(b'bad')
   with self.assertRaises(ValueError):p.copy_reference(p.pin(src/'RESULT.json'),out,0)
 def test_escape_or_oracle(self):
  for filename in ('../secret','/absolute','data/h.bin'):
   with tempfile.TemporaryDirectory() as t:
    src,out,r=self.fixture(pathlib.Path(t));r['tensor_records']['x']['file']=filename;(src/'RESULT.json').write_text(json.dumps(r))
    with self.assertRaises(ValueError):p.copy_reference(p.pin(src/'RESULT.json'),out,0)
 def test_profile_and_tokens(self):
  with tempfile.TemporaryDirectory() as t:
   src,out,r=self.fixture(pathlib.Path(t));r['complete_block_tokens']=1;(src/'RESULT.json').write_text(json.dumps(r))
   with self.assertRaises(ValueError):p.copy_reference(p.pin(src/'RESULT.json'),out,0)
if __name__=='__main__':unittest.main()
