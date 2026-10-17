import ast,json,tempfile,unittest
from pathlib import Path
import run_sv,check_sv,owned_compile
P=Path(__file__).resolve().parent
class Cold(unittest.TestCase):
 def test_no_execute_default(self):
  class A:execute=False
  with self.assertRaises(ValueError):run_sv.run(A())
 def test_syntax(self):
  for f in P.glob('*.py'):ast.parse(f.read_text())
  ast.parse(owned_compile.CHILD)
 def test_modules(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'a.sv';base='module ProductionQk16KernelBench(input clock); endmodule\n';p.write_text(base+'// module ignored(); endmodule\n');self.assertEqual(check_sv._inventory_check(p)['definition_count'],1)
   for text in [base+base,base+'  module x(); endmodule module x(); endmodule',base+'module unknown; endmodule',base+'module tc_clk_gating(); endmodule']:
    p.write_text(text)
    with self.assertRaises(ValueError):check_sv._inventory_check(p)
 def test_strings(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'a.sv';p.write_text('module ProductionQk16KernelBench(input clock); initial $display("module fake(); endmodule"); endmodule');self.assertEqual(check_sv._inventory_check(p)['definition_count'],1)
 def fixture(self):
  spec=json.loads((P/'EXTERNAL_INTERFACE_PINS.json').read_text());lines=['module ProductionQk16KernelBench(input clock);']
  for name,row in spec.items():
   params='' if not row['parameters'] else '#('+','.join('.'+k+'('+v+')' for k,v in row['parameters'].items())+')'
   for i in range(row['instance_count']):lines.append(name+' '+params+' i_'+name+'_'+str(i)+'('+','.join('.'+n+"(1'b0)" for n in row['ports'])+');')
  return '\n'.join(lines+['endmodule'])
 def test_external_counts_and_ports(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'a.sv';s=self.fixture();p.write_text(s);self.assertEqual(check_sv.check(p)['external_inventory']['reachable_external_counts']['qwen2_matrix_command_endpoint'],8)
   for bad in [s.replace('qwen2_matrix_command_endpoint #(.ENABLE_ACCUMULATOR_SEED(1)) i_qwen2_matrix_command_endpoint_0','unknown_type i_qwen2_matrix_command_endpoint_0'),s.replace('.seed_abort_i(','.wrong_abort_i(',1),s.replace('ENABLE_ACCUMULATOR_SEED(1)','ENABLE_ACCUMULATOR_SEED(0)',1),'module ProductionQk16KernelBench(input clock); endmodule']:
    p.write_text(bad)
    with self.assertRaises(ValueError):check_sv.check(p)
 def test_unreachable_resources(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'a.sv';p.write_text(self.fixture().replace('ProductionQk16KernelBench','Unused')+'\nmodule ProductionQk16KernelBench(input clock); endmodule')
   with self.assertRaises(ValueError):check_sv.check(p)
 def test_conditional_ghosts(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'a.sv';s=self.fixture();head,body=s.split(';',1);body=body.rsplit('endmodule',1)[0]
   for text in [head+'; generate if (0) begin : ghost '+body+' end endgenerate endmodule',head+'; if (0) '+body+' endmodule',head+'; `ifdef UNKNOWN\n'+body+'`endif\nendmodule']:
    p.write_text(text)
    with self.assertRaises(ValueError):check_sv.check(p)
 def test_limits_and_scope(self):
  self.assertIn('2147483648',owned_compile.CHILD);self.assertIn('134217728',owned_compile.CHILD);self.assertIn('O_EXCL',owned_compile.CHILD)
  s=(P/'run_sv.py').read_text();self.assertNotIn('scala.tools.nsc.Main',s);self.assertNotIn('--lint-only',s);self.assertIn('time.monotonic()+150',s)
if __name__=='__main__':unittest.main()
