"""Real isolated source selection only. No Chisel/RTL/model or shared producer grant."""
import pathlib,sys,json,hashlib,unittest,copy
D=pathlib.Path(__file__).resolve().parents[1];R=D.parents[1];sys.path.insert(0,str(D));import selected159 as gate

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
class Selected159(unittest.TestCase):
 def setUp(self):self.original=json.loads((R/'candidates/fresh_original_top_recovery_20261028/SOURCE_AND_TOOLCHAIN_PINS.json').read_text())
 def test_three_selectors_exact159(self):
  for name in gate.SOURCE_CHOICES:
   s=gate.selected_inputs(R,name);paths=gate.checked_paths(R,s['overlay'],self.original,s['contract']);self.assertEqual(len(paths),159)
 def test_six_exact_deltas_keep_fixed_banks(self):
  old=gate.selected_inputs(R,gate.ADDRESS_SOURCE);new=gate.selected_inputs(R,gate.SUPPLY_SOURCE);a=json.loads(old['overlay'].read_text())['files'];b=json.loads(new['overlay'].read_text())['files'];self.assertEqual([x['name']for x,y in zip(b,a)if x!=y],['BurstProtocol.scala','DenseOwnerIO.scala','HostBlockTopV4.scala','IdmaWeightBurst.scala','QwenOwnerProtocol.scala','TransposedDenseOwner.scala']);self.assertEqual(next(x for x in a if x['name']=='TransposedDenseBanks.scala'),next(x for x in b if x['name']=='TransposedDenseBanks.scala'))
 def test_catalog_covers_actual_selected_sources(self):
  cat={r['path']:r for r in json.loads((R/'candidates/same_job_execution_20261030/SOURCE_PINS.json').read_text())['files']};s=gate.selected_inputs(R,gate.SUPPLY_SOURCE)
  for name in gate.checked_paths(R,s['overlay'],self.original,s['contract'])+[str(D/'selected159.py')]:
   p=pathlib.Path(name);r=cat[str(p.relative_to(R))];self.assertEqual((p.stat().st_size,sha(p)),(r['bytes'],r['sha256']))
 def test_no_readonly_new_hardware_admission(self):
  for first,terminal in ((True,False),(False,True),(True,True)):
   with self.assertRaises(ValueError):gate.selected_inputs(R,gate.SUPPLY_SOURCE,first,terminal)
 def test_no_numerical_or_fullTop_authority(self):
  s=gate.selected_inputs(R,gate.SUPPLY_SOURCE);self.assertFalse(s['contract']['numeric_execution_authorized']);self.assertFalse(s['contract']['final_rtl_accepted']);self.assertEqual(s['contract']['matrix_macs'],4096);self.assertEqual(s['contract']['vector_lanes'],32)
 def test_invalid_selector_rejected_before_io(self):
  for name in ('../else','',None,True):
   with self.assertRaises(ValueError):gate.selected_inputs(pathlib.Path('/absent'),name)
if __name__=='__main__':unittest.main(verbosity=2)
