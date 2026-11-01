"""Real pack helper regression only. No compiler/ELF/native run or mock gates."""
import ast,hashlib,importlib.util,pathlib,tempfile,unittest
D=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('actual_source_pin_pack',D/'pack_model_candidate.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class SourcePinTests(unittest.TestCase):
 def setUp(self):
  t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=pathlib.Path(t.name).resolve();self.p=self.root/'input';self.p.write_bytes(b'')
 def reject(self,pins,reason):
  with self.assertRaises(m.ModelPackFailure)as caught:m.check_pins(pins)
  d=caught.exception.model_pack_diagnostic;self.assertEqual(d['phase'],'SOURCE_PINS');self.assertEqual(d['reason'],reason)
  self.assertNotIn(str(self.root),str(d))
 def test_empty_source_and_make_inputs(self):
  other=self.root/'make';other.write_bytes(b'')
  m.check_pins({str(self.p):hashlib.sha256(b'').hexdigest()});m.check_pins({str(other):m.sha(other)})
 def test_nonempty_input_unchanged(self):
  self.p.write_bytes(b'actual bytes\n');m.check_pins({str(self.p):m.sha(self.p)})
 def test_empty_wrong_sha(self):self.reject({str(self.p):'f'*64},'SOURCE_PIN_HASH_MISMATCH')
 def test_missing(self):self.reject({str(self.root/'absent'):'0'*64},'SOURCE_PIN_PATH')
 def test_direct_symlink(self):
  link=self.root/'link';link.symlink_to(self.p);self.reject({str(link):m.sha(self.p)},'SOURCE_PIN_PATH')
 def test_parent_symlink(self):
  sub=self.root/'real';sub.mkdir();(sub/'empty').write_bytes(b'');link=self.root/'alias';link.symlink_to(sub,target_is_directory=True)
  self.reject({str(link/'empty'):m.sha(sub/'empty')},'SOURCE_PIN_PATH')
 def test_directory(self):self.reject({str(self.root):'0'*64},'SOURCE_PIN_PATH')
 def test_oversize_sparse_before_read(self):
  with self.p.open('wb')as f:f.truncate((4<<30)+1)
  self.reject({str(self.p):'0'*64},'SOURCE_PIN_SIZE')
 def test_malformed_sets_and_keys(self):
  for v in (None,{},[],True):
   with self.subTest(v=v):self.reject(v,'SOURCE_PIN_SET')
  for v in (None,1,True,pathlib.Path('x')):
   with self.subTest(v=v):self.reject({v:'0'*64},'SOURCE_PIN_PATH')
 def test_malformed_hashes(self):
  for v in (None,True,1,{},'0'*63,'A'*64,'../secret'):
   with self.subTest(v=v):self.reject({str(self.p):v},'SOURCE_PIN_HASH_FORMAT')
 def test_all_seven_artifact_roles_remain_nonempty(self):
  for name in (*m.NAMES.values(),'frozen_artifact.json'):
   p=self.root/name;p.write_bytes(b'')
   for gate in (m.regular,m.pin):
    with self.subTest(name=name,gate=gate.__name__),self.assertRaises(ValueError):gate(p)
  with self.assertRaises(ValueError):m.validate_export(self.root)
 def test_empty_json_invalid_json_duplicate_and_nonfinite_refused(self):
  for data in (b'',b'{',b'{"x":1,"x":2}',b'{"x":NaN}'):
   self.p.write_bytes(data)
   with self.subTest(data=data),self.assertRaises(ValueError):m.json_file(self.p,1024)
 def test_original_artifact_gate_whole_ast_unchanged(self):
  expected={'regular':'d91d49208697e5efb7d37996414a0c193ff15b16c2ef31f7905311617c6768a2','pin':'9c56ba9699939c94861063a4d55c4cc71f9a16e68e19e7ed7c0c04e2fce672e4','json_file':'58422d25b8282ffc030203e29977c8abdd1583059b150ccaee3fabd3df082f15'}
  found={n.name:n for n in ast.parse((D/'pack_model_candidate.py').read_text()).body if isinstance(n,ast.FunctionDef)}
  for name,want in expected.items():self.assertEqual(hashlib.sha256(ast.dump(found[name],include_attributes=False).encode()).hexdigest(),want,name)
if __name__=='__main__':unittest.main()
