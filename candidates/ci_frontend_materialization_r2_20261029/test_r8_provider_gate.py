from pathlib import Path
import unittest,tempfile,json,sys,argparse
import provider_root_gate as g
parser=argparse.ArgumentParser();parser.add_argument("--providers-dir",type=Path,required=True);options,rest=parser.parse_known_args()
class Tests(unittest.TestCase):
 def setUp(self):self.root=options.providers_dir.resolve();self.inputs=[self.root/n for n in ['qwen2_matrix_command_endpoint.sv','tc_clk.sv','idma_backend_rw_axi_flat_wrap.sv']]
 def test_exact(self):
  r=g.validate_provider_roots(self.inputs);self.assertEqual([r['roots'][n]['ports'] for n in ['qwen2_matrix_command_endpoint','tc_clk_gating','idma_backend_rw_axi_flat_wrap']],[45,4,15])
 def test_missing_wrapper(self):self.assertRaises(ValueError,g.validate_provider_roots,self.inputs[:-1])
 def test_duplicate_root(self):self.assertRaises(ValueError,g.validate_provider_roots,self.inputs+[self.inputs[-1]])
 def test_changed_source(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'changed.sv';p.write_text(self.inputs[-1].read_text()+'\n');self.assertRaises(ValueError,g.validate_provider_roots,self.inputs[:-1]+[p])
 def test_changed_contract_width(self):
  with tempfile.TemporaryDirectory() as d:
   c=json.loads((Path(g.__file__).parent/'EXTERNAL_ROOT_ABI.json').read_text());c['roots']['idma_backend_rw_axi_flat_wrap']['ports']['src_addr_i'][1]=32;p=Path(d)/'abi.json';p.write_text(json.dumps(c));self.assertRaises(ValueError,g.validate_provider_roots,self.inputs,p)
 def test_unsupported_ansi(self):self.assertRaises(ValueError,g.ansi_ports,'module z(input mystery a);endmodule','z')
if __name__=='__main__':unittest.main(argv=[sys.argv[0],*rest])
