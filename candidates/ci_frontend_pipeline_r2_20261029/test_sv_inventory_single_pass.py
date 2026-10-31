"""Differential tests against unchanged original whole + per-module scanner."""
import hashlib,importlib.util,io,pathlib,random,sys,tempfile,unittest
D=pathlib.Path(__file__).resolve().parent;M=D.parent/'ci_frontend_materialization_r2_20261029';sys.path.insert(0,str(M));sys.path.insert(0,str(D))
import sv_comment_only_identity as scanner
from module_fingerprints import fingerprints
from sv_inventory_single_pass import inventory
class Tests(unittest.TestCase):
 def check(self,data):
  with tempfile.TemporaryDirectory()as td:
   p=pathlib.Path(td)/'fixture.sv';p.write_bytes(data);counts={};expected=dict(raw_sha256=hashlib.sha256(data).hexdigest(),normalized_sha256=scanner.digest(io.BytesIO(data),counts),bytes=len(data),counts=counts,modules=fingerprints(p));self.assertEqual(inventory(p,scanner),expected)
 def reject(self,data):
  with tempfile.TemporaryDirectory()as td:
   p=pathlib.Path(td)/'fixture.sv';p.write_bytes(data)
   with self.assertRaises(ValueError):inventory(p,scanner)
 def test_original_scanner_pin(self):self.assertEqual(hashlib.sha256((M/'sv_comment_only_identity.py').read_bytes()).hexdigest(),'b49c75780d2bfb295d3e90df6d478475f42c3129dba73c850b4d564e4114965b')
 def test_multimodule_full_counts(self):self.check(b'module A(\n);\n wire x; // @[/root/a.scala 1:2]\nendmodule\nmodule B(\n);\n// @[unrecognized]\nendmodule\n')
 def test_pragma_and_strings(self):self.check(b'module A(\n);\n/* verilator lint_off WIDTH */\nstring s="// @[/not/a.scala 1:2] \\\"";\n\\id/*fake \nendmodule\n')
 def test_block_inside_one_module(self):self.check(b'module A(\n);\n/*\n// @[/not/a.scala 1:2]\n*/\nendmodule\n')
 def test_lf_after_comment_and_identifier(self):
  for end in [b'endmodule // @[/a.scala 2:3]\n',b'endmodule \\escaped\n',b'endmodule\r\n']:
   self.check(b'module A(\n);\n'+end+b'module B(\n);\nendmodule\n')
 def test_cross_boundary_block_rejected(self):self.reject(b'module A(\n);\n/*\nendmodule\nmodule B(\n);\n*/\nendmodule\n')
 def test_cross_boundary_string_rejected(self):self.reject(b'module A(\n);\n"\nendmodule\nmodule B(\n);\n"\nendmodule\n')
 def test_fake_nested_module_rejected(self):self.reject(b'module A(\n);\n/*\nmodule fake(\n*/\nendmodule\n')
 def test_gaps_rejected(self):
  base=b'module A(\n);\nendmodule\n'
  for x in [b'\n'+base,base+b'\n',base+b'// trailer\n',base+b'\nmodule B(\n);\nendmodule\n']:self.reject(x)
 def test_final_lf_required(self):
  for x in [b'endmodule',b'endmodule // comment',b'endmodule\r']:
   self.reject(b'module A(\n);\n'+x)
 def test_duplicate_or_missing_end(self):
  self.reject(b'module A(\n);\nendmodule\nmodule A(\n);\nendmodule\n');self.reject(b'module A(\n);\n')
 def test_buffer_boundary(self):
  for n in [65520,65530,65536,65540,131070]:
   line=b'wire x; // @[/prefix/A.scala 12:{1,2,3}]\n';body=(line*(n//len(line)))+b'/*'+b'x'*(n%len(line))+b'*/\n';self.check(b'module A(\n);\n'+body+b'endmodule\nmodule B(\n);\nendmodule\n')
 def test_deterministic_differential_100(self):
  rng=random.Random(20261031);lines=[b'wire a;\n',b'// @[/prefix/B.scala 1:2]\n',b'// @[invalid]\n',b'/* translate_off */\n',b'string a="//notcomment";\n',b'\\quoted//notcomment \n',b'`ifdef FOO\n',b'`endif\n',b'/* multi\nline */\n',b'// trailing comment\r\n']
  for _ in range(100):
   data=b''.join(b'module M'+str(i).encode()+b'(\n);\n'+b''.join(rng.choice(lines)for _ in range(rng.randrange(1,15)))+b'endmodule\n'for i in range(rng.randrange(1,6)));self.check(data)
 def test_restores_scanner_hash_namespace_on_error(self):
  old=scanner.hashlib;self.reject(b'module A(\n);\n/*\nendmodule\n');self.assertIs(scanner.hashlib,old);self.assertIs(old,hashlib)
 def test_real_collector_same_output_schema(self):
  import frontend_observation_metadata as collector
  data=b'module A(\n);\n// @[/a.scala 1:2]\nendmodule\nmodule B(\n);\nendmodule\n'
  with tempfile.TemporaryDirectory()as td:
   p=pathlib.Path(td)/'fixture.sv';p.write_bytes(data);out=pathlib.Path(td)/'identity.json';r=collector.observe_sv(p,M,out);expected=inventory(p,scanner)
   self.assertEqual({k:r[k]for k in expected},expected);self.assertEqual(r['schema'],'OBSERVED_FRONTEND_SV_V1');self.assertFalse(r['numerical_pass']);self.assertEqual(r['scanner_sha256'],collector.SCANNER_SHA)
if __name__=='__main__':unittest.main()
