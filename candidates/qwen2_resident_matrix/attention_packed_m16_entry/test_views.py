"""Cold two-root reference capabilities and late byte-reader boundaries."""
import tempfile,unittest
from pathlib import Path
from . import views as v
class ViewTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);root=Path(self.tmp.name)
  self.roots={k:str(root/k) for k in ('origin','fresh')}
  for p in self.roots.values():Path(p).mkdir()
  for k in self.roots:(Path(self.roots[k])/'value').write_bytes(k.encode())
  self.item=v.record('origin',dict(path='value',bytes=6,sha256=v.R.sha(b'origin')))
 def test_exact_root_read(self):self.assertEqual(v.path(self.roots,self.item).read_bytes(),b'origin')
 def test_root_switch_cannot_alias_hash(self):
  with self.assertRaises(ValueError):v.path(self.roots,dict(self.item,root='fresh'))
 def test_unknown_root(self):
  with self.assertRaises(ValueError):v.path(self.roots,dict(self.item,root='other'))
 def test_traversal(self):
  with self.assertRaises(ValueError):v.path(self.roots,dict(self.item,path='../fresh/value'))
 def test_symlink(self):
  (Path(self.roots['origin'])/'alias').symlink_to(Path(self.roots['origin'])/'value')
  with self.assertRaises(ValueError):v.path(self.roots,dict(self.item,path='alias'))
 def test_exact_late_lookup(self):
  ref=dict(fresh_profile=v.PROFILE,roots=self.roots,fresh_lookup={'known':self.item})
  self.assertEqual(v.read_reference_bytes(ref,'known'),b'origin')
  with self.assertRaises(ValueError):v.read_reference_bytes(ref,'missing')
  ref['fresh_profile']='other'
  with self.assertRaises(ValueError):v.read_reference_bytes(ref,'known')
 def test_hash_drift(self):
  (Path(self.roots['origin'])/'value').write_bytes(b'drift!')
  with self.assertRaises(ValueError):v.path(self.roots,self.item)
 def test_only_m16_decoder_domain(self):
  for rows in (True,16.0,1,128):
   with self.assertRaises(ValueError):v.read_native_reference({},b'',rows=rows,method='official_self_cache',name='y',shape=[16,1536])
if __name__=='__main__':unittest.main()
