import unittest,sys
from emit_cold128_programs import *
class Programs(unittest.TestCase):
 def test_complete_all_runtime_profiles(self):
  for p,n in [(1,17),(2,22),(3,13),(4,18)]:
   b,block=common(p);cb,db,m=b.finish();self.assertIsNone(block);self.assertEqual(len(cb),n*16);self.assertLessEqual(n,64)
   self.assertEqual(m['schedule'][-1]['name'],'final_fence')
   for pc,w in enumerate(b.commands):
    op=w&255;self.assertEqual((w>>8)&7,2 if op in (0x20,0x23,0x24) else 4 if op==0x41 else 3)
    self.assertEqual((w>>24)&65535,pc);self.assertEqual((w>>40)&65535,pc+1)
    for j in range(3):
     r=(w>>(56+j*24))&NULL
     if r==NULL:self.assertEqual((op,j),(0x33,1))
     else:self.assertLess(r,len(b.records))
   for r in b.records:
    self.assertEqual((r>>8)&0xffffff,0)
    nxt=(r>>32)&NULL;self.assertTrue(nxt==NULL or nxt<len(b.records))
   for a in m['tensors'].values():
    self.assertTrue(all(0<x<1<<18 for x in a['dims']))
    self.assertEqual(a['address']%64,0)
 def test_producer_graph(self):
  for p in range(1,5):
   b,_=common(p);written=set()
   for c in b.schedule:
    for name in (c['a'],c['b']):
     if name and not b.t[name]['readonly']:self.assertIn(name,written,c['name'])
    for name in c['outputs']:
     self.assertFalse(b.t[name]['readonly']);self.assertNotIn(name,written);written.add(name)
   self.assertIn('output',written)
 def test_moe_identity_and_padding(self):
  for p in (3,4):
   b,_=common(p);moe=b.schedule[-2];post=b.schedule[-3]
   self.assertEqual(moe['roots'][0],post['roots'][2]);root=moe['roots'][1]
   for role in range(8):
    w=b.records[root+role];payload=w>>56
    self.assertEqual(w&255,0x60);self.assertEqual((payload>>8)&7,role)
    self.assertEqual((w>>32)&NULL,root+role+1 if role<7 else NULL)
   self.assertEqual(b.t['moe_shared_gate_padded']['dims'],[2048,32])
 def test_no_overlap(self):
  for p in range(1,5):
   b,_=common(p);alloc=sorted((t['address'],t['address']+ALIGN(t['bytes'])) for t in b.t.values())
   for x,y in zip(alloc,alloc[1:]):self.assertLessEqual(x[1],y[0])
 def test_scratch_exact_capacity(self):
  for p,heads in [(1,16),(3,32)]:
   b,_=common(p);t=b.t['chunk_scratch'];self.assertEqual(t['dims'],[heads,128,3280]);self.assertEqual(t['bytes'],heads*1679360)
if __name__=='__main__':unittest.main()
