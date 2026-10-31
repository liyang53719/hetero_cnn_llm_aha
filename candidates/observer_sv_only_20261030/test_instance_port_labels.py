"""Exact banks named-port label classification, not generic dot-token ignoring."""
import pathlib,sys,unittest,re
D=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(D))
import instance_port_labels as h
import sv_difference_projection as p
FIELDS=('identity','slot','ng','index')
def block(kind='TransposedDownDenseBanks',instance='banks'):
 rows=[f'  {kind} {instance} (']+[f'    .io_tiles_response_bits_key_{f}(banks_io_tiles_response_bits_key_{f})'+(','if f!='index'else'')for f in FIELDS]+['  );']
 return ('\n'.join(rows)+'\n').encode()
def data(b=None):return b'module TransposedDenseDownOwner(\n input clock\n);\n'+(block()if b is None else b)+b'endmodule\n'
class Tests(unittest.TestCase):
 def classify(self,x,sourceinfo=None,diagnostic=None):
  allowed,_=p.removable_code_starts(x,h.LABELS);return h.label_offsets(x,'TransposedDenseDownOwner',allowed,p.LEX,sourceinfo,diagnostic)
 def test_only_four_label_offsets(self):
  x=data();out=self.classify(x);self.assertEqual(len(out),4)
  for f in FIELDS:
   name=('io_tiles_response_bits_key_'+f).encode();self.assertIn(x.index(b'.'+name)+1,out);self.assertNotIn(x.index(b'(banks_'+name)+1,out)
 def test_port_expression_real_parent_reference_rejected(self):
  self.assertEqual(self.classify(data(block().replace(b'(banks_io_tiles_response_bits_key_identity)',b'(io_tiles_response_bits_key_identity)'))),set())
 def test_member_or_hierarchical_reference_not_label(self):
  for expr in [b'struct.io_tiles_response_bits_key_identity',b'banks.io_tiles_response_bits_key_identity',b'f(banks_io_tiles_response_bits_key_identity)']:
   self.assertEqual(self.classify(data(block().replace(b'banks_io_tiles_response_bits_key_identity)',expr+b')'))),set())
 def test_wrong_type_or_instance(self):
  for b in [block('Other'),block(instance='notbanks')]:self.assertEqual(self.classify(data(b)),set())
 def test_comment_string_conditional_or_procedural_fake(self):
  for wrap in [lambda b:b'/*\n'+b+b'*/\n',lambda b:b'"\n'+b+b'"\n',lambda b:b'`ifdef X\n'+b+b'`endif\n',lambda b:b'initial begin\n'+b+b'end\n',lambda b:b'generate\n'+b+b'endgenerate\n']:
   self.assertEqual(self.classify(data(wrap(block()))),set())
 def test_duplicate_or_missing_label(self):
  b=block();self.assertEqual(self.classify(data(b.replace(b'io_tiles_response_bits_key_index',b'io_tiles_response_bits_key_slot'))),set());self.assertEqual(self.classify(data(b.replace(b'    .io_tiles_response_bits_key_index(banks_io_tiles_response_bits_key_index)\n',b''))),set())
 def test_malformed_connection_list_not_instance(self):
  for b in [block().replace(b'.io_tiles_response_bits_key_slot',b'io_tiles_response_bits_key_slot'),block().replace(b'  );',b'  ); assign x=y;'),block().replace(b'key_slot),',b'key_slot);'),block().replace(b'key_slot),',b'key_slot]),')]:self.assertEqual(self.classify(data(b)),set())
 def test_other_module_no_exemption(self):
  x=data();allowed,_=p.removable_code_starts(x,h.LABELS);self.assertEqual(h.label_offsets(x,'Public21QkvReductionRouter',allowed,p.LEX),set())
 def test_scoped_type_prefix_is_not_exact_instance_type(self):
  for prefix in [b'pkg::\n',b'pkg:: /* fake delimiter ; */\n',b'pkg:: // fake delimiter ;\n']:
   self.assertEqual(self.classify(data(prefix+block())),set())
 def test_instance_fileinfo_only_if_passed_grammar_recognizes_exact_body(self):
  info=b' @[TransposedDenseOwner.scala 819:19]'
  x=data(block().replace(b'banks (\n',b'banks ( //'+info+b'\n'))
  grammar=re.compile(re.escape(info))
  self.assertEqual(len(self.classify(x,grammar)),4)
  self.assertEqual(self.classify(x),set())
  for comment in (b' arbitrary',b' verilator lint_off WIDTH',b' synthesis translate_off',info+b' extra',b' @[/secret/not-scala 1:1]'):
   y=data(block().replace(b'banks (\n',b'banks ( //'+comment+b'\n'))
   events=[];self.assertEqual(self.classify(y,grammar,lambda reason,counts:events.append((reason,counts))),set())
   self.assertEqual(events[-1][0],'START_COMMENT_NOT_SOURCEINFO')
 def test_existing_end_and_named_port_comments_preserved_not_removed(self):
  x=data(block().replace(b'key_identity),',b'key_identity), // @[TransposedDenseOwner.scala 819:19]').replace(b'  );',b'  ); // @[TransposedDenseOwner.scala 819:19]'))
  before=bytes(x);self.assertEqual(len(self.classify(x)),4);self.assertEqual(x,before)
 def test_classifier_reason_counts_are_finite(self):
  for x,expected in [(data(),'EXACT_FOUR_LABELS'),(data(block('Other')),'START_COUNT'),(data(block().replace(b'(banks_io_tiles_response_bits_key_slot)',b'(parent.io_tiles_response_bits_key_slot)')),'KEY_EXPRESSION_NOT_EXACT')]:
   events=[];self.classify(x,diagnostic=lambda reason,counts:events.append((reason,counts)))
   self.assertEqual(len(events),1);self.assertEqual(events[0][0],expected);self.assertIn(events[0][0],h.REASONS)
   self.assertEqual(set(events[0][1]),{'start_count','block_bytes','tokens','ports','key_labels'})
   self.assertTrue(all(type(v)is int and v>=0 for v in events[0][1].values()))
if __name__=='__main__':unittest.main()

