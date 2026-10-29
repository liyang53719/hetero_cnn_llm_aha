import unittest,tempfile,pathlib,json
from native_dependency_guard import admit_native_dependencies,digest
P=pathlib.Path
class T(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=P(self.tmp.name);self.obj=self.root/'obj';self.obj.mkdir();self.out=self.root/'out';self.out.mkdir();self.src=self.root/'input.sv';self.src.write_text('module x; endmodule');self.cpp=self.obj/'VTop.cpp';self.cpp.write_text('// generated');self.dep=self.obj/'VTop__ver.d';self.raw=f'{self.cpp} {self.dep}  : {self.src} \n';self.dep.write_text(self.raw);self.pins={str(self.src):digest(self.src)}
 def tearDown(self):self.tmp.cleanup()
 def run_gate(self):return admit_native_dependencies(self.obj,{'VTop':self.obj},self.pins,self.out)
 def test_valid(self):
  generated,deps,rows=self.run_gate();self.assertEqual(deps[str(self.dep)],digest(self.dep));self.assertIn(str(self.dep),generated);self.assertEqual(rows[0]['targets'],2)
 def test_make_injections(self):
  for extra in ['$(shell touch BAD)','; echo BAD','\n\techo BAD','\ninclude /forbidden/evil',' | /forbidden/other','%','\\\n',' #comment',':', '=x']:
   with self.subTest(extra=extra):
    self.dep.write_text(self.raw.rstrip()+extra+'\n')
    with self.assertRaises(ValueError):self.run_gate()
 def test_unknown_dependency(self):
  other=self.root/'unknown.sv';other.write_text('x');self.dep.write_text(self.raw.replace(str(self.src),str(other)))
  with self.assertRaisesRegex(ValueError,'UNBOUND_PREREQUISITE'):self.run_gate()
 def test_external_target(self):
  self.dep.write_text(self.raw.replace(str(self.cpp),str(self.src)))
  with self.assertRaisesRegex(ValueError,'UNBOUND_TARGET'):self.run_gate()
 def test_escape_and_symlink(self):
  for value in [str(self.obj/'../input.sv'),str(self.root/'alias.sv')]:
   if value.endswith('alias.sv'):P(value).symlink_to(self.src)
   self.dep.write_text(self.raw.replace(str(self.src),value))
   with self.assertRaisesRegex(ValueError,'DEPENDENCY_PATH'):self.run_gate()
 def test_unexpected_d(self):
  self.dep.rename(self.obj/'foreign.d')
  with self.assertRaisesRegex(ValueError,'UNEXPECTED_DEPENDENCY_NAME'):self.run_gate()
 def test_compiled_and_diagnostic(self):
  for suffix in ('.o','.a','.gch'):
   f=self.obj/('VTop'+suffix);f.write_bytes(b'not-admitted')
   with self.assertRaisesRegex(ValueError,'COMPILED_PRODUCT'):self.run_gate()
   r=json.loads((self.out/'generated_tree_failure.json').read_text());self.assertEqual(r['relative_path'],f.name);self.assertEqual(r['sha256'],digest(f));self.assertEqual(r['suffix'],suffix);f.unlink()
 def test_pin_drift(self):
  self.src.write_text('changed')
  with self.assertRaisesRegex(ValueError,'DEPENDENCY_PIN_DRIFT'):self.run_gate()
if __name__=='__main__':unittest.main()
