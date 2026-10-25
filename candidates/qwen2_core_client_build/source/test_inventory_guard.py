"""Tiny Python filesystem controls only. No inventoried tool/target invocation."""
import hashlib,os,sys,tempfile,unittest
from unittest import mock
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import inventory_guard as g

class Controls(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'root';self.root.mkdir();(self.root/'a').write_bytes(b'ab');(self.root/'sub').mkdir();self.spec={'root':str(self.root),'entries':g.entries(self.root)}
 def tearDown(self):self.tmp.cleanup()
 def pin(self,p):return dict(path=str(p),resolved_path=str(p.resolve()),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
 def test_normal(self):g.verify_inventory(self.spec);g.verify_pin(self.pin(self.root/'a'))
 def test_added_entry(self):
  (self.root/'new').write_text('x')
  with self.assertRaises(ValueError):g.verify_inventory(self.spec)
 def test_deleted_entry(self):
  (self.root/'a').unlink()
  with self.assertRaises(ValueError):g.verify_inventory(self.spec)
 def test_same_size_byte_change(self):
  p=self.pin(self.root/'a');(self.root/'a').write_bytes(b'cd')
  with self.assertRaises(ValueError):g.verify_pin(p)
 def test_directory_link_not_walked_but_identity_bound(self):
  target=Path(self.tmp.name)/'target';target.mkdir();(target/'hidden').write_text('x');(self.root/'link').symlink_to(target,target_is_directory=True)
  e=g.entries(self.root);self.assertEqual([x['relative'] for x in e],['a','link','sub']);g.verify_inventory({'root':str(self.root),'entries':e})
  (self.root/'link').unlink();(self.root/'link').symlink_to(self.root/'sub',target_is_directory=True)
  with self.assertRaises(ValueError):g.verify_inventory({'root':str(self.root),'entries':e})
 def test_file_link_target_bound(self):
  (self.root/'link').symlink_to('a');p=self.pin(self.root/'link');p['symlink_target']='a';g.verify_pin(p);(self.root/'link').unlink();(self.root/'link').symlink_to('sub/missing')
  with self.assertRaises(ValueError):g.verify_pin(p)
 def test_link_root_rejected(self):
  alias=Path(self.tmp.name)/'alias';alias.symlink_to(self.root,target_is_directory=True)
  with self.assertRaises(ValueError):g.entries(alias)
 def test_absent_broken_symlink_rejected(self):
  p=self.root/'missing';g.verify_absent([str(p)]);p.symlink_to('absent-target')
  with self.assertRaises(ValueError):g.verify_absent([str(p)])
 def test_special_entry_rejected(self):
  os.mkfifo(self.root/'fifo')
  with self.assertRaises(ValueError):g.entries(self.root)
 def test_mode_drift(self):
  (self.root/'a').chmod(0o700)
  with self.assertRaises(ValueError):g.verify_inventory(self.spec)

 def test_root_scandir_failure_propagates(self):
  empty=Path(self.tmp.name)/'empty';empty.mkdir();spec={'root':str(empty),'entries':[]}
  with mock.patch('os.scandir',side_effect=PermissionError('synthetic root unreadable')):
   with self.assertRaises(PermissionError):g.verify_inventory(spec)
 def test_empty_subdir_scandir_failure_propagates(self):
  original=os.scandir
  def deny_sub(path):
   if Path(path)==self.root/'sub':raise PermissionError('synthetic child unreadable')
   return original(path)
  with mock.patch('os.scandir',side_effect=deny_sub):
   with self.assertRaises(PermissionError):g.verify_inventory(self.spec)

if __name__=='__main__':unittest.main(verbosity=2)
