import hashlib,json,tempfile,unittest
from pathlib import Path
import acquire
class Reuse(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.root=Path(self.t.name);self.prior=self.root/'prior';d=self.prior/'model';d.mkdir(parents=True);self.out=self.root/'out';self.out.mkdir();acquire.OUT=self.out
  self.sha=hashlib.sha256(b'abcd').hexdigest();self.spec={'model':'model','name':'tensor','bytes':4,'verification':'EXACT_NAME_SHA256','expected_sha256':self.sha,'start':10,'end':13,'revision':'pinned','shape':[2],'dtype':'BF16','url':'https://huggingface.co/m/resolve/pinned/f','shard_bytes':20}
  self.r={**self.spec,'actual_sha256':self.sha,'actual_bytes':4,'file':'model/tensor.bin'};self.f=d/'tensor.bin';self.f.write_bytes(b'abcd');self.rp=d/'tensor.receipt.json';self.save()
 def save(self):self.rp.write_text(json.dumps(self.r))
 def tearDown(self):self.t.cleanup()
 def test_good(self):self.assertEqual(acquire.reuse_verified(self.prior,self.spec)['actual_sha256'],self.sha);self.assertEqual((self.out/'model/tensor.bin').read_bytes(),b'abcd')
 def test_absent_receipt(self):self.rp.unlink();self.assertIsNone(acquire.reuse_verified(self.prior,self.spec))
 def test_drift(self):
  self.f.write_bytes(b'abce')
  with self.assertRaises(ValueError):acquire.reuse_verified(self.prior,self.spec)
 def test_semantic_drift(self):
  self.r['revision']='main';self.save()
  with self.assertRaises(ValueError):acquire.reuse_verified(self.prior,self.spec)
 def test_path_escape(self):
  self.r['file']='../private';self.save()
  with self.assertRaises(ValueError):acquire.reuse_verified(self.prior,self.spec)
if __name__=='__main__':unittest.main()
