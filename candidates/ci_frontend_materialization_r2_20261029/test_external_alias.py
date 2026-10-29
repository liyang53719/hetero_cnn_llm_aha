import pathlib,tempfile,unittest,ast,os
from unittest.mock import patch,MagicMock
import inventory_runner_jdk as j
class Tests(unittest.TestCase):
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
class Integration(unittest.TestCase):
 def test_pre_post_alias_mapping(self):
  source=(pathlib.Path(__file__).parent.parent/'ci_frontend_pipeline_r2_20261029'/'supervise_multiroot.py').read_text();tree=ast.parse(source);node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='verify_aliases')
  def need(ok,msg):
   if not ok:raise ValueError(msg)
  ns={'Path':pathlib.Path,'os':os,'need':need};exec(compile(ast.Module(body=[node],type_ignores=[]),'reviewed_alias_function','exec'),ns)
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d);a=root/'a';b=root/'b';a.write_bytes(b'a');b.write_bytes(b'b');link=root/'link';link.symlink_to(a)
   rows=[{'path':str(link),'link':str(a),'target':str(a)}];ns['verify_aliases'](rows)
   link.unlink();link.symlink_to(b)
   with self.assertRaises(ValueError):ns['verify_aliases'](rows)
  self.assertEqual(source.count("verify_aliases(caps.get('jdk_aliases',[]))"),2)
if __name__=='__main__':unittest.main()
