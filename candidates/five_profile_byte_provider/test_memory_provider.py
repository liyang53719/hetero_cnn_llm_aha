import unittest
from memory_provider import MemoryProvider,BytesReader,ZeroReader,MemoryAccessError
class TestMemory(unittest.TestCase):
 def build(self):
  return MemoryProvider({'tensors':{'x':{'address':64,'bytes':64,'readonly':True},'state':{'address':128,'bytes':32,'readonly':True},'y':{'address':4090,'bytes':128,'readonly':False}}},{'x':BytesReader(bytes(range(64))),'state':ZeroReader(32)},[('meta',0,bytes(range(16)))])
 def test_ro(self):
  p=self.build()
  for n in range(65):
   for o in range(65-n):self.assertEqual(p.read(64+o,n),bytes(range(64))[o:o+n])
  self.assertEqual(p.read(100,60),bytes(range(36,64))+bytes(32))
 def test_rw(self):
  p=self.build()
  with self.assertRaises(MemoryAccessError):p.read(4090,1)
  p.write(4090,bytes(range(128)))
  self.assertEqual(p.read(4090,128),bytes(range(128)))
  p.write(4090,b'Z'*128,bytes(i%2 for i in range(128)))
  self.assertEqual(p.read(4090,128),bytes(90 if i%2 else i for i in range(128)))
 def test_partial_uninitialized(self):
  p=self.build();p.write(4090,b'ab',b'\1\0')
  self.assertEqual(p.read(4090,1),b'a')
  with self.assertRaises(MemoryAccessError):p.read(4090,2)
 def test_failclosed(self):
  p=self.build()
  for a,n in [(-1,1),(0,-1),(2**64,1),(15,2),(160,1),(4089,2),(4217,2)]:
   with self.assertRaises(MemoryAccessError):p.read(a,n)
  for a,d in [(64,b'x'),(63,b'ab'),(4217,b'ab')]:
   with self.assertRaises(MemoryAccessError):p.write(a,d)
  self.assertEqual(p.bytes_written,0)
 def test_strobes(self):
  p=self.build()
  for mask in [b'\2',b'',b'\1\0',None]:
   if mask is None:continue
   with self.assertRaises(MemoryAccessError):p.write(4090,b'a',mask)
  with self.assertRaises(MemoryAccessError):p.write(64,b'a',b'\0')
 def test_ro_binding(self):
  for readers in [{},{'x':ZeroReader(63)},{'x':ZeroReader(64),'z':ZeroReader(1)}]:
   with self.assertRaises(MemoryAccessError):MemoryProvider({'tensors':{'x':{'address':0,'bytes':64,'readonly':True}}},readers)
 def test_overlap(self):
  with self.assertRaises(MemoryAccessError):MemoryProvider({'tensors':{'x':{'address':0,'bytes':64,'readonly':False}}},{},[('m',32,b'a')])
 def test_hash(self):
  p=self.build();self.assertEqual(p.stream_ro_hashes(7),p.stream_ro_hashes(1024));self.assertFalse(p.pages)
if __name__=='__main__':unittest.main()
