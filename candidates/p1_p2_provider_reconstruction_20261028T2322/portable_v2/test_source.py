import importlib.util,tempfile,pathlib,unittest
HERE=pathlib.Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('rebuild',HERE/'rebuild.py');r=importlib.util.module_from_spec(s);s.loader.exec_module(r)
class Guards(unittest.TestCase):
 def setUp(self):
  self.root=pathlib.Path('/tmp');self.e={k:1 for k in ('model','name','revision','dtype','shape','bytes','start','end','url','shard_bytes','verification','expected_sha256')};self.v={**self.e,'file':'safe.bin'}
 def test_safe(self):self.assertEqual(r.verified_receipt_path(self.root,self.v,self.e),self.root/'safe.bin')
 def test_joint_receipt_hash(self):
  self.v['expected_sha256']='0'*64;self.v['actual_sha256']='0'*64
  with self.assertRaises(ValueError):r.verified_receipt_path(self.root,self.v,self.e)
 def test_geometry(self):
  self.v['shape']=[1]
  with self.assertRaises(ValueError):r.verified_receipt_path(self.root,self.v,self.e)
 def test_escape(self):
  for p in ('../outside','/outside'):
   with self.subTest(p=p):
    self.v['file']=p
    with self.assertRaises(ValueError):r.verified_receipt_path(self.root,self.v,self.e)
 def test_no_old_workspace_paths(self):
  text=(HERE/'rebuild.py').read_text()
  for old in ('T2258','T2307/reference','environment_recovery_20261028T2032','hetero_verified_recovery_20261028T2035'):self.assertNotIn(old,text)
if __name__=='__main__':unittest.main()
