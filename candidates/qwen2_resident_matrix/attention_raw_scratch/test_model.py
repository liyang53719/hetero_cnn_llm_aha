import unittest
from dataclasses import replace
from candidates.qwen2_resident_matrix.transposed_down.model import Banks
from .model import Port,Key,Request,Context,Obligations,location
class Tests(unittest.TestCase):
 def port(self,scratch=True):
  p=Port(Banks(1376),enabled=True,scratch=scratch);self.assertTrue(p.tick(acquire=7)['acquired'])
  if scratch:self.assertTrue(p.tick(begin=Context(7,1,16,0))['begun'])
  return p
 def key(self,line=4096,write=True,tag=1):return Key(7,tag,line,write,1,16,0)
 def transact(self,p,k,data=0):
  self.assertTrue(p.tick(request=Request(k,data))['accepted']);self.assertIsNone(p.response)
  a,b,w=location(k.line,scratch_enabled=p.scratch);self.assertEqual(p.banks.writes if k.write else p.banks.reads,{a:w,b:w})
  self.assertFalse(p.tick(ack=k)['acked']);r=p.response
  self.assertTrue(p.tick(ack=k)['acked']);self.assertFalse(p.banks.reads or p.banks.writes);return r.data
 def test_all96_lines_raw_bits_and_no_shadow(self):
  p=self.port();identity=id(p.banks.words);cells=set();raw=int.from_bytes(bytes.fromhex('0000807f0100c07f00000080000080ff')*4,'little')
  for line in range(4096,4192):
   a,b,w=location(line,scratch_enabled=True);cells.update(((a,w),(b,w)));self.transact(p,self.key(line),raw^line)
  self.assertEqual(p.written,(1<<96)-1)
  for line in range(4096,4192):self.assertEqual(self.transact(p,self.key(line,False),0),raw^line)
  self.assertEqual(len(cells),192);self.assertEqual(id(p.banks.words),identity)
  self.assertEqual({w for _,w in cells},set(range(512,524)))
 def test_boundaries_default_off(self):
  p=self.port(False);self.transact(p,Key(7,1,4095,True),5)
  for n in (4096,4191,4192,8191):self.assertFalse(p.tick(request=Request(Key(7,1,n,True)))['accepted'])
  q=self.port();self.transact(q,self.key(4096),8);self.transact(q,self.key(4191),9)
  self.assertFalse(q.tick(request=Request(self.key(4192)))['accepted'])
  self.assertEqual(location(4095),(14,15,511));self.assertEqual(location(4096,scratch_enabled=True),(0,1,512));self.assertEqual(location(4191,scratch_enabled=True),(14,15,523))
 def test_written_only_clean_ack(self):
  p=self.port();k=self.key();self.assertFalse(p.tick(request=Request(replace(k,write=False)))['accepted'])
  p.tick(request=Request(k,123));self.assertEqual(p.written,0);p.tick();self.assertEqual(p.written,0)
  p.tick(ack=k);self.assertEqual(p.written,1)
 def test_context_invalidate_and_stale_keys(self):
  p=self.port();k=self.key();self.transact(p,k,3)
  self.assertTrue(p.tick(begin=Context(7,2,17,1))['begun']);self.assertEqual(p.written,0)
  self.assertFalse(p.tick(request=Request(k))['accepted'])
  fresh=Key(7,2,4096,False,2,17,1);self.assertFalse(p.tick(request=Request(fresh))['accepted'])
  self.transact(p,replace(fresh,write=True),4)
 def test_pending_held_block_context_release(self):
  p=self.port();k=self.key();p.tick(request=Request(k,4))
  self.assertFalse(p.tick(begin=Context(7,2,17,1))['begun']);held=p.response
  for _ in range(4):
   self.assertFalse(p.tick(release=7)['released']);self.assertFalse(p.tick(begin=Context(7,2,17,1))['begun']);self.assertIs(p.response,held)
  p.tick(ack=k);self.assertTrue(p.tick(begin=Context(7,2,17,1))['begun'])
 def test_foreign_acks_never_retire(self):
  p=self.port();k=self.key();p.tick(request=Request(k));p.tick()
  for field,val in [('owner',8),('tag',2),('generation',2),('query',17),('kv_head',1),('line',4192),('write',False)]:
   self.assertFalse(p.tick(ack=replace(k,**{field:val}))['acked']);self.assertFalse(p.drained)
  self.assertTrue(p.tick(ack=k)['acked'])
 def test_abort_pending_and_held_drains_without_validity(self):
  for pending in (True,False):
   p=self.port();k=self.key();p.tick(request=Request(k,99))
   if not pending:p.tick()
   p.tick(abort=True,ack=k);self.assertTrue(p.poison);self.assertEqual(p.written,0)
   if not p.drained:self.assertTrue(p.tick(ack=k)['acked'])
   self.assertTrue(p.tick(release=7)['released']);self.assertFalse(p.tick(acquire=7)['acquired'])
   p.tick(soft_reset=True);self.assertTrue(p.tick(acquire=7)['acquired']);self.assertFalse(p.tick(begin=Context(7,1,16,0))['begun'])
   self.assertTrue(p.tick(begin=Context(7,2,16,0))['begun'])
 def test_abort_ack_same_edge_never_publishes(self):
  p=self.port();k=self.key();p.tick(request=Request(k,9));p.tick();self.assertTrue(p.tick(ack=k,abort=True)['acked']);self.assertEqual(p.written,0)
 def test_raw_metadata_isolation(self):
  p=self.port();self.transact(p,Key(7,1,0,True),88);self.assertEqual(p.written,0)
  self.assertFalse(p.tick(request=Request(Key(7,2,0,True,1,16,0)))['accepted'])
  self.assertFalse(p.tick(request=Request(Key(7,2,4096,True)))['accepted'])
 def test_generation_exhaustion_and_context_types(self):
  p=self.port()
  for x in (Context(7,True,1,0),Context(7,0,1,0),Context(7,1,1,0),Context(8,2,1,0),Context(7,2,128,0),Context(7,2,1,2)):
   self.assertFalse(p.tick(begin=x)['begun'])
  self.assertTrue(p.tick(begin=Context(7,2**32-1,127,1))['begun']);self.assertFalse(p.tick(begin=Context(7,2**32,0,0))['begun'])
 def test_exclusive_lease_and_three_edges(self):
  p=Port(Banks(1376),enabled=True,scratch=True)
  self.assertFalse(p.tick(acquire=7,obligations=Obligations(matrix=True))['acquired'])
  self.assertTrue(p.tick(acquire=7)['acquired']);p.tick(begin=Context(7,1,16,0));k=self.key()
  self.assertTrue(p.tick(request=Request(k))['accepted']);self.assertFalse(p.tick(request=Request(k))['accepted'])
  o=p.tick(ack=k,request=Request(k),dense=True,tile=True,clear=True);self.assertTrue(o['acked']);self.assertFalse(o['accepted']);self.assertFalse(o['dense_allowed'] or o['tile_allowed'] or o['clear_allowed'])
  self.assertTrue(p.tick(request=Request(k))['accepted'])
 def test_disabled_profile_and_identity(self):
  b=Banks(1376);p=Port(b);self.assertIs(p.banks,b);self.assertFalse(p.tick(acquire=7)['acquired'])
  with self.assertRaises(ValueError):Port(b,scratch=True)
  with self.assertRaises(ValueError):Port(b,enabled=1)
if __name__=='__main__':unittest.main()
