import ast,importlib.util,pathlib,tempfile,unittest,json
from unittest.mock import patch
P=pathlib.Path(__file__).resolve().parent/'fresh_host.py'
spec=importlib.util.spec_from_file_location('candidate_fresh_host',P);h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
class Tests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.base=pathlib.Path(self.t.name);self.allowed=self.base/'trusted';(self.allowed/'bin').mkdir(parents=True);(self.allowed/'lib').mkdir();self.lib=self.allowed/'lib/libjli.so';self.lib.write_bytes(b'test library');self.roots=(self.allowed,)
 def tearDown(self):self.t.cleanup()
 def text(self,p):return 'libjli.so => '+str(p)+' (0x123)\n'
 def test_safe_parent_component(self):
  raw=self.allowed/'bin/../lib/libjli.so';self.assertEqual(h.dependency_paths(self.text(raw),self.roots),[str(raw)]);self.assertEqual(h.resolve_dependency(raw,self.roots),self.lib)
 def test_parent_escape(self):
  other=self.base/'outside.so';other.write_bytes(b'x');raw=self.allowed/'bin/../../outside.so'
  with self.assertRaises(h.DependencyRejected) as got:h.dependency_paths(self.text(raw),self.roots)
  self.assertEqual(got.exception.rejection_kind,'CANONICAL_ROOT_REJECTED');self.assertTrue(got.exception.parent_component)
 def test_symlink_escape(self):
  other=self.base/'outside.so';other.write_bytes(b'x');alias=self.allowed/'lib/alias.so';alias.symlink_to(other)
  with self.assertRaises(h.DependencyRejected) as got:h.resolve_dependency(alias,self.roots)
  self.assertEqual(got.exception.rejection_kind,'CANONICAL_ROOT_REJECTED')
 def test_symlink_internal_and_raw_alias_retained(self):
  alias=self.allowed/'lib/alias.so';alias.symlink_to(self.lib);self.assertEqual(h.dependency_paths(self.text(alias),self.roots),[str(alias)]);self.assertEqual(h.resolve_dependency(alias,self.roots),self.lib)
 def test_untrusted_alias_to_trusted_not_admitted(self):
  alias=self.base/'outside-alias.so';alias.symlink_to(self.lib)
  with self.assertRaises(h.DependencyRejected):h.resolve_dependency(alias,self.roots)
 def test_prefix_confusion(self):
  fake=self.base/'trusted-other';fake.mkdir();f=fake/'x.so';f.write_bytes(b'x')
  with self.assertRaises(h.DependencyRejected):h.resolve_dependency(f,self.roots)
 def test_missing_target(self):
  with self.assertRaises(h.DependencyRejected) as got:h.resolve_dependency(self.allowed/'none.so',self.roots)
  self.assertEqual(got.exception.rejection_kind,'MISSING_TARGET')
 def test_directory_rejected(self):
  with self.assertRaises(h.DependencyRejected) as got:h.resolve_dependency(self.allowed/'lib',self.roots)
  self.assertEqual(got.exception.rejection_kind,'NONREGULAR_TARGET')
 def test_missing_library(self):
  with self.assertRaises(h.DependencyRejected) as got:h.dependency_paths('libx.so => not found',self.roots)
  self.assertEqual(got.exception.rejection_kind,'UNRESOLVED_LIBRARY')
 def test_symlink_retarget_rejected_at_pin_time(self):
  alias=self.allowed/'lib/alias.so';alias.symlink_to(self.lib);h.dependency_paths(self.text(alias),self.roots);alias.unlink();other=self.base/'outside.so';other.write_bytes(b'x');alias.symlink_to(other)
  with self.assertRaises(h.DependencyRejected):h.resolve_dependency(alias,self.roots)
 def test_fixed_safe_metadata(self):
  exc=h.DependencyRejected('CANONICAL_ROOT_REJECTED',True);exc.query_role='JDK_EXECUTABLE';r=h.failure_metadata(exc);self.assertEqual(r['query_role'],'JDK_EXECUTABLE');self.assertEqual(r['reason'],'ELF_DEPENDENCY_ROOT_REJECTED');self.assertEqual(r['rejection_kind'],'CANONICAL_ROOT_REJECTED');self.assertTrue(r['had_parent_component']);self.assertNotIn(str(self.base),json.dumps(r))
  exc.query_role='/private/path';self.assertEqual(h.failure_metadata(exc)['query_role'],'UNKNOWN')
 def test_original_lexical_rule_rejects_safe_parent_spelling(self):
  raw=self.allowed/'bin/../lib/libjli.so';text=self.text(raw)
  paths=h.dependency_paths(text,self.roots);self.assertEqual(paths,[str(raw)])
  self.assertTrue(pathlib.Path(paths[0]).is_relative_to(self.allowed))
  self.assertFalse(all(pathlib.Path(p).is_relative_to(self.allowed) and '..' not in pathlib.Path(p).parts for p in paths))
  self.assertTrue(all(h.resolve_dependency(p,self.roots).is_file() for p in paths))
 def test_source_rechecks_canonical_before_hash_and_keeps_alias(self):
  s=P.read_text();ast.parse(s);self.assertIn('for dep in paths:add(dep,dependency=True)',s);self.assertIn("if p!=r:aliases[str(p)]=str(r)",s);self.assertIn('pins[str(r)]=sha(r)',s)
  self.assertIn("VERSION_ID')=='24.04'",s);self.assertIn('total<=3*1024**3',s);self.assertIn('time.monotonic()-start<240',s)
if __name__=='__main__':unittest.main()
