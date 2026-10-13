"""Torch-free source/diagnostic regression, no checkpoint acceptance."""
import ast,struct,unittest
from pathlib import Path
from . import chunk_reference as r

class ChunkReferenceTests(unittest.TestCase):
 def test_exact_suffix_and_no_double_preparation(self):
  module,identity=r._source_ast();text=ast.unparse(module)
  self.assertIn('solve_triangular',text);self.assertFalse(any(isinstance(n,ast.Name) and n.id=='l2norm' for n in ast.walk(module)))
  self.assertNotIn('query = query * scaling',text)
  self.assertEqual(r.source_identity(),identity)
 def test_complete_input_geometry_and_padding(self):
  r.validate_inputs(bytes(51200),1)
  for raw,tokens in [(bytes(51200),True),(bytes(51200-4),1),(bytes(51200),0)]:
   with self.assertRaises(ValueError):r.validate_inputs(raw,tokens)
  raw=bytearray(51200);raw[12290*4:12290*4+4]=struct.pack('<I',1)
  with self.assertRaises(ValueError):r.validate_inputs(bytes(raw),1)
 def test_complete_state_diagnostics_do_not_assign_pass(self):
  raw=dict(output=bytes(8192),state=bytes(2097152));result=r.diagnose(raw,raw)
  self.assertIsNone(result['passed']);self.assertIsNone(result['thresholds'])
  self.assertEqual(result['state']['bit_mismatches'],0)
  with self.assertRaises(ValueError):r.diagnose(dict(raw,state=bytes(64)),raw)
 def test_reference_has_no_candidate_or_setters(self):
  text=Path(r.__file__).read_text();tree=ast.parse(text)
  for node in ast.walk(tree):
   if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
    self.assertFalse(node.func.attr.startswith('set_'))
  self.assertNotIn('chunk.model',text);self.assertNotIn('TypedChunkDriver',text)
if __name__=='__main__':unittest.main()
