import ast,json,hashlib,unittest
from pathlib import Path
import run_structure
from check_silu import check_text
P=Path(__file__).resolve().parent
class Cold(unittest.TestCase):
 def test_source_closure(self):
  p=json.loads((P/'SOURCE_PINS.json').read_text());b=json.loads((P/'BASELINE_CLASS_PINS.json').read_text());self.assertEqual(len(p),95);self.assertEqual(len(b['classes']),557);self.assertEqual({n:h for n,h in p.items() if not n.startswith('structure/')},b['source_sha256'])
 def test_no_execute_default(self):
  class A:execute=False
  with self.assertRaises(ValueError):run_structure.run(A())
 def test_syntax(self):
  for f in P.glob('*.py'):ast.parse(f.read_text())
 def test_scope(self):
  s=(P/'source/ProductionQk16KernelCollection.scala').read_text();self.assertIn('selected=true',s);self.assertNotIn('emitSystemVerilog',s);self.assertIn('48*1024*1024',s)
  r=(P/'run_structure.py').read_text();self.assertNotIn('org.scalatest.tools.Runner',r);self.assertIn('source_count=95,reused_classes=557',r)
 def test_parser_no_resource_cut(self):
  s=(P/'check_structure.py').read_text();self.assertIn("'qwen2_matrix_command_endpoint':8",s);self.assertIn("==16,'SFU16",s);self.assertIn('exact two debt updates required',s)
 def original_ir(self):return (P.parent/'production_qk16_kernel_structure_attempt_v1_20261017/structure/ProductionQk16KernelBench.fir').read_text()
 def proposed_ir(self):return self.original_ir().replace('connect io.silu.abort, bad @','connect io.silu.abort, or(io.abort, poison) @',1)
 def test_original_loop_expression_rejected(self):
  with self.assertRaisesRegex(ValueError,'SFU abort'):check_text(self.original_ir())
 def test_synthetic_rewrite_only(self):self.assertTrue(check_text(self.proposed_ir())['tiles_abort_still_bad'])
 def test_poison_combination_rejected(self):
  with self.assertRaises(ValueError):check_text(self.proposed_ir().replace('regreset poison : UInt<1>, clock, reset, UInt<1>(0h0) @[scala/candidates/qwen2_resident_matrix/ffn_group/FfnTileSiluBridge','node poison = io.silu.result.valid @[scala/candidates/qwen2_resident_matrix/ffn_group/FfnTileSiluBridge',1))
 def test_tile_delay_rejected(self):
  with self.assertRaises(ValueError):check_text(self.proposed_ir().replace('connect io.tiles.abort, bad @','connect io.tiles.abort, poison @',1))
 def test_late_override_rejected(self):
  with self.assertRaises(ValueError):check_text(self.proposed_ir().replace('connect io.silu.abort, or(io.abort, poison) @','connect io.silu, other\n    connect io.silu.abort, or(io.abort, poison) @',1))
class CollectionCold(unittest.TestCase):
 def synthetic(self):
  t=(P.parent/'production_silu_feedback_structure_attempt_v2_20261017/structure/ProductionQk16KernelBench.fir').read_text().replace('circuit ProductionQk16KernelBench :','circuit ProductionQk16KernelCollection :',1)
  t+='\n  module ProductionQk16KernelCollection :\n'
  for n,m in [('top','ProductionQk16KernelBench'),('pre','HeteroBF16FmaPre'),('mul','HeteroBF16FmaMul'),('post','HeteroBF16FmaPost'),('round','HeteroBF16FmaRound')]:t+=f'    inst {n} of {m}\n'
  for m in ['HeteroBF16FmaPre','HeteroBF16FmaMul','HeteroBF16FmaPost','HeteroBF16FmaRound']:t+=f'  module {m} :\n'
  return t
 def verify(self,t):
  import tempfile
  from check_structure import check
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'synthetic.fir';p.write_text(t);return check(p)
 def test_collection_subtree(self):
  r=self.verify(self.synthetic());self.assertEqual(r['resource_counts']['qwen2_matrix_command_endpoint'],8);self.assertEqual(r['qualification_top'],'ProductionQk16KernelBench')
 def test_missing_provider(self):
  with self.assertRaises(ValueError):self.verify(self.synthetic().replace('    inst round of HeteroBF16FmaRound\n',''))
 def test_extra_bench(self):
  with self.assertRaises(ValueError):self.verify(self.synthetic().replace('    inst top of ProductionQk16KernelBench','    inst extra of ProductionQk16KernelBench\n    inst top of ProductionQk16KernelBench'))
 def test_class_inventory(self):
  s=(P/'run_structure.py').read_text();self.assertIn('ProductionQk16KernelCollection.class',s);self.assertIn('EmitProductionQk16KernelCollection$delayedInit$body.class',s)
if __name__=='__main__':unittest.main()
