import sys,unittest,hashlib,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from memory_provider import MemoryProvider,BytesReader,ZeroReader,MemoryAccessError,metadata_from_directory

def tensor(a,n,ro):return {'address':a,'bytes':n,'readonly':ro}
def provider():return MemoryProvider({'tensors':{'r':tensor(4090,6,True),'a':tensor(4096,8,False),'b':tensor(4104,8,False),'z':tensor(8192,8,True)}},{'r':BytesReader(b'abcdef'),'z':ZeroReader(8)},metadata=[('cmd',12288,b'CMD')])
class Tests(unittest.TestCase):
 def test_uninitialized_and_masked_atomicity(self):
  p=provider()
  with self.assertRaises(MemoryAccessError):p.read(4096,1)
  p.write(4096,b'12345678',b'\1\0\1\0\1\0\1\0')
  self.assertEqual(p.read(4096,1),b'1')
  with self.assertRaises(MemoryAccessError):p.read(4096,2)
  before=(p.bytes_written,bytes(p.pages[1]),bytes(p.valid[1]))
  for a,b,s in [(4095,b'xx',None),(4111,b'xx',None),(4096,b'xx',b'\1\2'),(4095,b'xx',b'\0\0')]:
   with self.assertRaises(MemoryAccessError):p.write(a,b,s)
   self.assertEqual((p.bytes_written,bytes(p.pages[1]),bytes(p.valid[1])),before)
 def test_crossregion_rw_and_bounds(self):
  p=provider();p.write(4096,b'0123456789abcdef');self.assertEqual(p.read(4090,22),b'abcdef0123456789abcdef')
  self.assertEqual(p.read(8192,8),bytes(8));self.assertEqual(p.read(12288,3),b'CMD')
  for a,n in [(-1,1),(4096,-1),(True,1),(4096,False),(2**64,1),(2**64,0),(2**64+1,0),(-1,0),(4112,1),(8199,2)]:
   before=p.bytes_read
   with self.assertRaises(MemoryAccessError):p.read(a,n)
   self.assertEqual(p.bytes_read,before)
 def test_no_output_preload(self):
  with self.assertRaises(MemoryAccessError):MemoryProvider({'tensors':{'out':tensor(10,4,False)}},{'out':BytesReader(b'xxxx')})
 def test_short_reader(self):
  class Bad:
   size=4
   def read(self,o,n):return b''
  p=MemoryProvider({'tensors':{'r':tensor(10,4,True)}},{'r':Bad()})
  with self.assertRaises(MemoryAccessError):p.read(10,4)
  with self.assertRaises(MemoryAccessError):p.stream_ro_hashes()
 def test_constructor_ranges(self):
  # Accepted malformed metadata/extra RW must become explicit failures.
  for a in [-1,True,2**64,2**64-1,1.5]:
   with self.subTest(kind='metadata',address=a):
    with self.assertRaises((MemoryAccessError,TypeError)):MemoryProvider({'tensors':{}},{},metadata=[('m',a,b'xx')])
   with self.subTest(kind='extra_rw',address=a):
    with self.assertRaises((MemoryAccessError,TypeError)):MemoryProvider({'tensors':{}},{},extra_rw=[('m',a,2)])
 def test_aliases_preserve_gaps_and_uninitialized(self):
  m={'tensors':{'whole':tensor(100,16,False),'k':tensor(100,8,False),'v':tensor(108,8,False)}}
  with self.assertRaises(MemoryAccessError):MemoryProvider(m,{})
  p=MemoryProvider(m,{},rw_alias_groups=[('whole','k','v')])
  p.write(107,b'XY');self.assertEqual(p.read(107,2),b'XY')
  for a in (99,100,106,109,115,116):
   with self.assertRaises(MemoryAccessError):p.read(a,1)
  m={'tensors':{'a':tensor(100,4,False),'b':tensor(108,4,False)}}
  p=MemoryProvider(m,{},rw_alias_groups=[('a','b')]);p.write(100,b'AAAA');p.write(108,b'BBBB')
  with self.assertRaises(MemoryAccessError):p.read(100,12)
  before=p.bytes_written
  with self.assertRaises(MemoryAccessError):p.write(102,b'XXXXXXXX')
  self.assertEqual(p.bytes_written,before);self.assertEqual(p.read(100,4),b'AAAA')
 def test_alias_cannot_override_ro(self):
  m={'tensors':{'a':tensor(100,8,False),'b':tensor(104,8,True)}}
  with self.assertRaises(MemoryAccessError):MemoryProvider(m,{'b':BytesReader(b'12345678')},rw_alias_groups=[('a','b')])
 def test_metadata_pins_and_padding(self):
  import tempfile
  with tempfile.TemporaryDirectory() as td:
   q=Path(td);cmd=bytes(range(16));desc=bytes(range(32));m={'launch':{'commandBase':100,'commandLimit':132,'descriptorBase':200,'descriptorLimit':248,'commands':1,'descriptors':2},'sha256':{'commands':hashlib.sha256(cmd).hexdigest(),'descriptors':hashlib.sha256(desc).hexdigest()}}
   (q/'manifest.json').write_text(json.dumps(m));(q/'commands.bin').write_bytes(cmd);(q/'descriptors.bin').write_bytes(desc)
   result=metadata_from_directory(q);self.assertEqual(result,[('command_bytes',100,cmd+bytes(16)),('descriptor_bytes',200,desc+bytes(16))])
   (q/'commands.bin').write_bytes(bytes(16))
   with self.assertRaises(MemoryAccessError):metadata_from_directory(q)
   (q/'commands.bin').write_bytes(cmd);(q/'descriptors.bin').write_bytes(desc[:-1])
   with self.assertRaises(MemoryAccessError):metadata_from_directory(q)
 def test_tensor_bool_rejected(self):
  for a,n in [(True,2),(10,True)]:
   with self.subTest(a=a,n=n):
    with self.assertRaises(MemoryAccessError):MemoryProvider({'tensors':{'x':tensor(a,n,False)}},{})
if __name__=='__main__':unittest.main(verbosity=2)
