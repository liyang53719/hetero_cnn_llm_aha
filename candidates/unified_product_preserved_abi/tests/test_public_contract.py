"""Packaging/source tests only. Never reads actual generated FIR/SV or invokes tools."""
from pathlib import Path
import copy,hashlib,importlib.util,json,tempfile,unittest
R=Path(__file__).resolve().parents[1]
def module(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
sv=module('new_declaration_metadata',R/'checks/sv/reconstruct_expectation.py')
c=module('new_annotation_checker',R/'checks/chirrtl/check_chirrtl.py')
f=module('handwritten_annotation_fixture',R/'checks/chirrtl/test_check_chirrtl.py')
NEW_TOP='ce13b35764776c3b136dc17e9aabefa079204ed993aa8d45ad922703045912a9';OLD_TOP='f1bb55d392e2c9fd0c4a4de14c3b44a581b59dc48d80eb8ba754c891514cc09e'
class Contract(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.old=sv.load_baseline().build();cls.new=sv.transform(cls.old);cls.top=(R/'source/UnifiedSharedResourceTop.scala').read_bytes();cls.expected=c.annotation_expectation(f.fixture_modules(),f.E)
 def test_exact_top(self):self.assertEqual(hashlib.sha256(self.top).hexdigest(),NEW_TOP);self.assertEqual(len(self.top),4542)
 def test_exact_source_inverse(self):
  marker=b'  dontTouch(io)\n';self.assertEqual(self.top.count(marker),1);self.assertEqual(hashlib.sha256(self.top.replace(marker,b'',1)).hexdigest(),OLD_TOP)
 def test_top_binding_position(self):self.assertIn(b'  })\n  dontTouch(io)\n  admission.io.launch.bits',self.top)
 def test_no_fullblock_upgrade(self):self.assertIn(b'io.completeBlockImplemented:=false.B',self.top)
 def test_original_expectation(self):self.assertEqual(hashlib.sha256(self.old).hexdigest(),sv.OLD_SHA)
 def test_successor_expectation(self):self.assertEqual(hashlib.sha256(self.new).hexdigest(),sv.NEW_SHA)
 def test_single_key_inverse(self):self.assertEqual(self.new.replace(b'"integer_0":',b'"integer":',1),self.old)
 def test_strict_ports(self):
  e=json.loads(self.new);self.assertEqual(len(e['selected_module_ports']),7);self.assertEqual(len(e['selected_module_ports']['UnifiedSharedResourceTop']),4599);self.assertEqual(sum(map(len,e['selected_module_ports'].values())),9308)
 def test_wrong_input_rejected(self):
  with self.assertRaises(ValueError):sv.transform(self.old+b'\n')
 def test_already_new_rejected(self):
  with self.assertRaises(ValueError):sv.transform(self.new)
 def test_missing_helper_rejected(self):
  with tempfile.TemporaryDirectory()as d:
   with self.assertRaises(ValueError):sv.load_baseline(Path(d))
 def test_mutated_helper_rejected(self):
  with tempfile.TemporaryDirectory()as d:
   p=Path(d)/'checks/sv';p.mkdir(parents=True);(p/'reconstruct_expectation.py').write_text('raise RuntimeError("must not execute")')
   with self.assertRaises(ValueError):sv.load_baseline(Path(d))
 def test_write_never_overwrites(self):
  with tempfile.TemporaryDirectory()as d:
   p=Path(d)/'existing';p.write_text('unchanged')
   with self.assertRaises(ValueError):sv.load_baseline().write_new(p,self.new)
   self.assertEqual(p.read_text(),'unchanged')
 def test_symlink_output_rejected(self):
  with tempfile.TemporaryDirectory()as d:
   p=Path(d);(p/'target').write_text('keep');(p/'link').symlink_to(p/'target')
   with self.assertRaises(ValueError):sv.load_baseline().write_new(p/'link',self.new)
   self.assertEqual((p/'target').read_text(),'keep')
 def test_targets_count_and_uniqueness(self):
  a=self.expected['dont_touch_targets'];self.assertEqual(len(a),9213);self.assertEqual(len(set(a)),9213)
 def test_exact_product_target_count(self):self.assertEqual(sum('|UnifiedSharedResourceTop>'in x for x in self.expected['dont_touch_targets']),4597)
 def test_exact_collection_target_count(self):self.assertEqual(sum('|UnifiedSharedResourceCollection>'in x for x in self.expected['dont_touch_targets']),4616)
 def test_critical_targets_present(self):
  for n in ['io.completeBlockImplemented','io.result.bits.version']:self.assertIn('~UnifiedSharedResourceCollection|UnifiedSharedResourceTop>'+n,self.expected['dont_touch_targets'])
 def test_missing_product_annotation_rejected(self):
  def mutate(rows):rows.pop(next(i for i,x in enumerate(rows)if x.get('target')=='~UnifiedSharedResourceCollection|UnifiedSharedResourceTop>io.completeBlockImplemented'))
  with self.assertRaises(ValueError):c.parse_bytes(f.encode(f.fixture_modules(),mutate),f.E)
 def test_duplicate_product_annotation_rejected(self):
  def mutate(rows):rows.append(copy.deepcopy(next(x for x in rows if x.get('target')=='~UnifiedSharedResourceCollection|UnifiedSharedResourceTop>io.result.bits.version')))
  with self.assertRaises(ValueError):c.parse_bytes(f.encode(f.fixture_modules(),mutate),f.E)
if __name__=='__main__':unittest.main()
