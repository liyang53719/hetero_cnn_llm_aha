import pathlib,tempfile,unittest,ast,os,io,stat
from unittest.mock import patch,MagicMock
import inventory_runner_jdk as j
class Tests(unittest.TestCase):
 def test_observed_alias_fixture(self):
  root=pathlib.Path('/testjdk');target=MagicMock();target.__str__.return_value='/etc/ssl/certs/adoptium/cacerts';target.is_file.return_value=True;target.is_symlink.return_value=False;target.stat.return_value.st_size=134280;target.stat.return_value.st_mode=stat.S_IFREG|0o644;target.open.return_value=io.BytesIO(b'x'*134280)
  r=j.external_record(root,root/'lib/security/cacerts',target)
  self.assertEqual(r['resolved_target'],'/etc/ssl/certs/adoptium/cacerts');self.assertEqual(r['bytes'],134280);self.assertEqual(len(r['sha256']),64)
 def test_observed_literal_policy(self):
  self.assertEqual(j.PUBLIC_EXTERNALS,{'lib/security/cacerts':'/etc/ssl/certs/adoptium/cacerts'})
 def test_old_java_alias_rejected(self):
  root=pathlib.Path('/testjdk');target=MagicMock();target.__str__.return_value='/etc/ssl/certs/java/cacerts';target.is_file.return_value=True;target.stat.return_value.st_size=134280
  with self.assertRaises(j.InventoryFailure) as c:j.external_record(root,root/'lib/security/cacerts',target)
  self.assertEqual(c.exception.code,'JDK_UNKNOWN_EXTERNAL_ALIAS');target.open.assert_not_called()

 def test_unknown_reject_without_read(self):
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d);p=root/'other';target=MagicMock();target.__str__.return_value='/private/no';target.is_file.return_value=True;target.stat.return_value.st_size=3
   with self.assertRaises(j.InventoryFailure) as c:j.external_record(root,p,target)
   self.assertEqual(c.exception.code,'JDK_UNKNOWN_EXTERNAL_ALIAS');target.open.assert_not_called()
 def test_known_bound_and_hash(self):
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d);target=root/'certs';target.write_bytes(b'public test certs');alias=root/'lib/security/cacerts'
   # Test-only map fixture; production exact target remains hardcoded.
   with patch.dict(j.PUBLIC_EXTERNALS,{'lib/security/cacerts':str(target)},clear=True):
    r=j.external_record(root,alias,target);self.assertEqual(r['bytes'],17);self.assertEqual(len(r['sha256']),64)
 def test_known_repoint_reject(self):
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d);target=root/'other';target.write_bytes(b'x')
   with self.assertRaises(j.InventoryFailure):j.external_record(root,root/'lib/security/cacerts',target)
 def test_large_known_reject(self):
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d);target=root/'cert';target.touch()
   with target.open('wb') as f:f.truncate(4*1024*1024+1)
   with patch.dict(j.PUBLIC_EXTERNALS,{'lib/security/cacerts':str(target)},clear=True),self.assertRaises(j.InventoryFailure) as c:j.external_record(root,root/'lib/security/cacerts',target)
   self.assertEqual(c.exception.code,'JDK_EXTERNAL_TARGET_NOT_BOUNDED_REGULAR')
if __name__=='__main__':unittest.main()
