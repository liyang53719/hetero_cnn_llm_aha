import copy,importlib.util,json,sys,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('exact_elf_closure',HERE/'elf_closure.py');E=importlib.util.module_from_spec(spec);spec.loader.exec_module(E)
class ClosureTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  self.a=self.root/'python';self.z=self.root/'libz.so.1';self.p=self.root/'libpcre2-8.so.0'
  for p in (self.a,self.z,self.p):p.write_bytes(b'fixture '+p.name.encode())
  self.meta={str(self.a):self.meta_for(['libz.so.1','libpcre2-8.so.0']),str(self.z):self.meta_for([],self.z.name),str(self.p):self.meta_for([],self.p.name)}
  self.reader=lambda p:copy.deepcopy(self.meta[str(p)])
 def meta_for(self,needed,soname=None):return dict(needed=needed,soname=soname,rpath=[],runpath=[],interpreter=None)
 def manifest(self):return E.generate([self.a],self.reader,(str(self.root),))
 def test_exact_mock_passes(self):self.assertTrue(E.check(self.manifest(),self.reader))
 def test_missing_libz_record_rejected(self):
  m=self.manifest();del m['files'][str(self.z)]
  with self.assertRaisesRegex(ValueError,'closure drift'):E.check(m,self.reader)
 def test_missing_git_pcre_edge_rejected(self):
  m=self.manifest();m['edges']=[e for e in m['edges'] if e['needed']!='libpcre2-8.so.0']
  with self.assertRaisesRegex(ValueError,'closure drift'):E.check(m,self.reader)
 def test_unresolved_needed_rejected(self):
  self.meta[str(self.a)]['needed'].append('unavailable.so')
  with self.assertRaisesRegex(ValueError,'unresolved NEEDED'):self.manifest()
 def test_soname_mismatch_rejected(self):
  self.meta[str(self.z)]['soname']='other.so'
  with self.assertRaisesRegex(ValueError,'SONAME mismatch'):self.manifest()
 def test_origin_runpath_resolves(self):
  self.meta[str(self.a)]['runpath']=['$ORIGIN']
  m=E.generate([self.a],self.reader,());self.assertEqual(len(m['files']),3)
 def test_unknown_loader_token_rejected(self):
  self.meta[str(self.a)]['runpath']=['$LIB']
  with self.assertRaisesRegex(ValueError,'unresolved or relative'):self.manifest()
if __name__=='__main__':unittest.main()
