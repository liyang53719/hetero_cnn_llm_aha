import tempfile,unittest
from pathlib import Path
import export_source as e
HERE=Path(__file__).parent
class Conditional(unittest.TestCase):
 def run_case(self,text,defines=None,headers=None):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'x.sv';p.write_text(text)
   for n,v in (headers or {}).items():(root/n).write_text(v)
   return e.verify_include_closure([p],[root],root,defines)
 def test_official_assertion_macro_body(self):
  self.assertEqual(self.run_case((HERE/'fixtures/assertions.svh').read_text()),1)
 def test_unbalanced_macro_conditional_rejected(self):
  with self.assertRaises(ValueError):self.run_case('`define HIDE `ifdef OFF\n`HIDE\n`include "absent"\n`endif\n')
 def test_string_cannot_balance_macro_condition(self):
  text='`define OPEN `ifdef NEVER_DEFINED "`endif"\n`define CLOSE "`ifdef" `endif\n`define FLAG\n`OPEN\n`undef FLAG\n`CLOSE\n`ifdef FLAG\n`include "missing.svh"\n`endif\n'
  with self.assertRaises(ValueError):self.run_case(text)
 def test_dynamic_macro_name_rejected(self):
  with self.assertRaises(ValueError):self.run_case('`define HIDE `inc``lude "absent"\n')
 def test_dynamic_macro_argument_rejected(self):
  with self.assertRaises(ValueError):self.run_case('`define PASS(x) x\n`PASS(`if``def OFF)\n')
 def test_backtick_formal_directive_rejected(self):
  text='`define INVOKE(D) `D\n`INVOKE(define) UVM\n`ifdef UVM\n`include "missing"\n`endif\n'
  with self.assertRaises(ValueError):self.run_case(text)
 def test_bare_backtick_argument_rejected(self):
  text='`define CAT(A,B) A``B\n`CAT(`,define) UVM\n`ifdef UVM\n`include "missing"\n`endif\n'
  with self.assertRaises(ValueError):self.run_case(text)
 def test_official_uvm_disabled(self):
  self.assertEqual(self.run_case((HERE/'fixtures/assert_rpt_pkg.sv').read_text()),1)
 def test_official_uvm_enabled_requires_header(self):
  with self.assertRaises(ValueError):self.run_case((HERE/'fixtures/assert_rpt_pkg.sv').read_text(),{'UVM':''})
 def test_uvm_enabled_resolves(self):
  self.assertEqual(self.run_case((HERE/'fixtures/assert_rpt_pkg.sv').read_text(),{'UVM':''},{'uvm_macros.svh':'// fixture'}),2)
 def test_nested_else_elsif(self):
  text='`ifdef OFF\n`include "absent"\n`elsif ON\n`ifndef OTHER\n`include "yes"\n`else\n`include "absent"\n`endif\n`else\n`include "absent"\n`endif\n'
  self.assertEqual(self.run_case(text,{'ON':''},{'yes':''}),2)
 def test_define_undef_and_inactive_pollution(self):
  text='`ifdef OFF\n`define UVM\n`endif\n`define UVM\n`undef UVM\n`ifdef UVM\n`include "absent"\n`endif\n'
  self.assertEqual(self.run_case(text),1)
 def test_header_macro_state(self):
  with self.assertRaises(ValueError):self.run_case('`include "h"\n`ifdef UVM\n`include "absent"\n`endif\n',headers={'h':'`define UVM\n'})
 def test_ordered_source_macro_state(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);a=root/'a';b=root/'b';a.write_text('`define UVM\n');b.write_text('`ifdef UVM\n`include "absent"\n`endif\n')
   with self.assertRaises(ValueError):e.verify_include_closure([a,b],[],root)
 def test_unknown_conditional_expression_rejected(self):
  for text in ['`ifdef UNKNOWN && OTHER\n`endif\n','`ifdef `M\n`endif\n','`elsif A\n','`else\n','`ifdef A\n','`ifdef A\n`else\n`else\n`endif\n']:
   with self.subTest(text=text),self.assertRaises(ValueError):self.run_case(text)
 def test_macro_body_is_not_immediate_condition(self):
  text='`define ASSERT(x) \\\n`ifdef UVM \\\n x; \\\n`endif\n`ifdef UVM\n`include "absent"\n`endif\n'
  self.assertEqual(self.run_case(text),1)
 def test_directive_producing_macro_rejected(self):
  with self.assertRaises(ValueError):self.run_case('`define POLLUTE `define UVM\n')
 def test_repeated_header_reprocessed_after_undef(self):
  text='`include "h"\n`undef GUARD\n`define UVM\n`include "h"\n'
  h='`ifndef GUARD\n`define GUARD\n`ifdef UVM\n`include "absent"\n`endif\n`endif\n'
  with self.assertRaises(ValueError):self.run_case(text,headers={'h':h})
 def test_filelist_defs_recorded(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'x').write_text('`ifdef UVM\n`include "absent"\n`endif\n');f=root/'f';f.write_text('+define+OTHER=1\n@ROOT@/x\n')
   self.assertEqual(e.check_filelist(f,root)['initial_defines'],{'OTHER':'1'})
   f.write_text('+define+UVM\n@ROOT@/x\n')
   with self.assertRaises(ValueError):e.check_filelist(f,root)
 def test_inline_and_macro_include_rejected(self):
  for text in ['module m; `include "absent"\n','`include `DYNAMIC\n']:
   with self.assertRaises(ValueError):self.run_case(text)
if __name__=='__main__':unittest.main()
