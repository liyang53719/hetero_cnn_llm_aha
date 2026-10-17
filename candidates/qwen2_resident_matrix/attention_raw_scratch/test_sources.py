import tempfile,unittest
from pathlib import Path
from . import prepare as p
class Tests(unittest.TestCase):
 def test_real_parent_patch_and_unchanged_physical_bank_sites(self):
  with tempfile.TemporaryDirectory() as d:
   old=Path(d)/'old';p.parent.compose(old);new=Path(d)/'new';p.compose(new)
   name=p.parent.TARGETS[0];a=(old/name).read_text();b=(new/name).read_text()
   # Physical SRAM declarations/address/data/enable logic remain byte-identical.
   x=a.index('  if(enableFfnTiles){',a.index('    when(p.softReset'))
   y=b.index('  if(enableFfnTiles){',b.index('    when(p.softReset'))
   self.assertEqual(a[x:a.index('class RawKvKey')],b[y:b.index('class RawKvKey')])
   self.assertEqual(a.count('SyncReadMem('),b.count('SyncReadMem('))
   self.assertIn('canonical(p.request.bits.key) && readable',b);self.assertIn('canonical(p.ack.bits,forAck=true)',b)
   self.assertIn('when(p.ack.fire && key.line>=4096.U && key.write && !poison && !stop)',b)
   self.assertIn('enableAttentionScratch:Boolean=false',b)
   owner=(new/p.parent.TARGETS[2]).read_text();self.assertIn('banks.io.rawKv.get.parentDrained:=rawLocalDrained',owner)
   self.assertIn('b.scratchBegin.get<>p.scratchBegin.get',owner)
 def test_control_storage_only(self):
  patch=(p.HERE/'scratch.patch').read_text();added='\n'.join(x[1:] for x in patch.splitlines() if x.startswith('+') and not x.startswith('+++'))
  self.assertNotIn('SyncReadMem(',added);self.assertNotIn('Reg(UInt(512.W))',added)
  self.assertEqual(added.count('Some(Reg'),5)
  self.assertIn('96.W',added);self.assertIn('forAck.B',added)
 def test_pins_and_mutation(self):
  pins=p.check();self.assertEqual(len(pins['generated']),3)
  self.assertIn('candidates/qwen2_resident_matrix/raw_kv_parent/compose.py',pins['sources'])
  with tempfile.TemporaryDirectory() as d:
   out=Path(d)/'out';actual=p.compose(out);f=out/p.parent.TARGETS[0];f.write_bytes(f.read_bytes()+b'\n')
   self.assertNotEqual(p.sha(f),actual[p.parent.TARGETS[0]])
if __name__=='__main__':unittest.main()
