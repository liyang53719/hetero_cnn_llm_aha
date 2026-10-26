"""Tiny source mutations / boolean connection truth tables; no Scala/JVM/RTL."""
from pathlib import Path
import importlib.util,itertools,unittest
H=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('contract',H/'check_source_contract.py');c=importlib.util.module_from_spec(s);s.loader.exec_module(c)
CORE=(H/'source/OrderedQkRealMatrixCore.scala').read_text();COL=(H/'source/OrderedQkRealMatrixCollection.scala').read_text()
class Source(unittest.TestCase):
 def test_exact(self):self.assertEqual(c.check(CORE,COL)['common_abi_roots'],4)
 def test_each_mux_field_mutation(self):
  for field in c.FORWARD:
   target=f'Mux(select,p.{field},l.{field})';self.assertIn(target,CORE)
   with self.assertRaises(ValueError):c.check(CORE.replace(target,f'Mux(select,l.{field},p.{field})',1),COL)
 def test_each_reverse_mutation(self):
  for field in c.REVERSE:
   with self.assertRaises(ValueError):c.check(CORE.replace(f'client.{field}:=chosen&&',f'client.{field}:=true.B&&'),COL)
 def test_no_stub_drained(self):
  with self.assertRaises(ValueError):c.check(CORE.replace('core.io.packedQkStepsDrained.get:=matrix.io.packedStepsDrained.get','core.io.packedQkStepsDrained.get:=true.B'),COL)
 def test_no_forced_lease(self):
  with self.assertRaises(ValueError):c.check(CORE.replace('val select=core.io.packedQkActive.get','val select=false.B'),COL)
 def test_no_new_arithmetic(self):
  with self.assertRaises(ValueError):c.check(CORE.replace('new OrderedQkBehaviorCore(true)','new OrderedQkBehaviorCore(false)'),COL)
 def test_each_abi_leaf_required(self):
  for leaf in ('Pre','Mul','Post','Round'):
   with self.assertRaises(ValueError):c.check(CORE,COL.replace('Module(new HeteroBF16Fma'+leaf+')','Module(new Replacement'+leaf+')'))
 def test_no_collection_runtime_entry(self):
  with self.assertRaises(ValueError):c.check(CORE,COL+'\nobject AccidentalRun extends App {}')
 def test_single_selected_control_truth_table(self):
  # Independent indexing model for a two-input mux, not a DUT state-machine model.
  for select,p,l,m in itertools.product((False,True),repeat=4):
   forward=p if select else l
   reverse_p=select and m;reverse_l=(not select) and m
   self.assertEqual(forward,[l,p][select]);self.assertFalse(reverse_p and reverse_l);self.assertEqual(reverse_p or reverse_l,m)
 def test_lease_no_early_release_source(self):
  p=(H/'reference_source/Qwen2Block.scala').read_text()
  self.assertIn('io.packedQkActive.get:=packedBusy',p);self.assertIn('val packedBusy=packedOwned.getOrElse(false.B)',p);self.assertIn('when(c.io.completion.fire){packedOwned.get:=false.B}',p)
if __name__=='__main__':unittest.main()
