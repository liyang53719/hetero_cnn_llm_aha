import unittest,tempfile,pathlib,struct,copy,json,unittest.mock as mock
import runtime_abi as a
P=pathlib.Path
class T(unittest.TestCase):
 def elf(self,root,needed=b'libc.so.6\0',tag=1,interp=b'/lib64/ld-linux-x86-64.so.2\0'):
  b=bytearray(1024);b[:16]=b'\x7fELF\x02\x01\x01'+b'\0'*9;b[16:64]=struct.pack('<HHIQQQIHHHHHH',3,62,1,0,64,0,0,64,56,3,0,0,0)
  b[64:120]=struct.pack('<IIQQQQQQ',1,4,0,0x400000,0,1024,1024,4096)
  b[120:176]=struct.pack('<IIQQQQQQ',3,4,256,0x400100,0,len(interp),len(interp),1)
  dyn=[(5,0x400300),(10,len(needed)),(tag,0),(0,0)];b[176:232]=struct.pack('<IIQQQQQQ',2,4,384,0x400180,0,64,64,8);b[256:256+len(interp)]=interp
  for i,v in enumerate(dyn):b[384+16*i:400+16*i]=struct.pack('<qQ',*v)
  b[768:768+len(needed)]=needed;p=root/'dut';p.write_bytes(b);return p
 def test_valid_parser_no_execution(self):
  with tempfile.TemporaryDirectory()as d:self.assertEqual(a.elf_info(self.elf(P(d)))['needed'],['libc.so.6'])
 def test_bad_needed_audit_and_interpreter(self):
  with tempfile.TemporaryDirectory()as d:
   for kw in [dict(needed=b'/forbidden/x\0'),dict(tag=29),dict(tag=0x6ffffefc),dict(interp=b'/forbidden/loader\0')]:
    with self.subTest(kw=kw),self.assertRaises(ValueError):a.elf_info(self.elf(P(d),**kw))
 def test_wrong_machine_and_offsets(self):
  with tempfile.TemporaryDirectory()as d:
   p=self.elf(P(d));b=bytearray(p.read_bytes());b[18:20]=struct.pack('<H',183);p.write_bytes(b)
   with self.assertRaises(ValueError):a.elf_info(p)
   p=self.elf(P(d));b=bytearray(p.read_bytes());b[32:40]=struct.pack('<Q',2**63);p.write_bytes(b)
   with self.assertRaises(ValueError):a.elf_info(p)
 def test_loader_output(self):
  s='linux-vdso.so.1 (0x123)\nlibc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x456)\n/lib64/ld-linux-x86-64.so.2 (0x789)\n';r=a.parse_list(s);self.assertEqual(len(r),2)
  for extra in ['libbad.so => not found\n','unexpected diagnostic\n','libc.so.6 => /other/path (0x999)\n']:
   with self.assertRaises(ValueError):a.parse_list(s+extra)
 def test_environment(self):
  self.assertFalse(any(k.startswith('LD_')or k=='GLIBC_TUNABLES'for k in a.clean_env()));self.assertEqual(a.clean_env()['LC_ALL'],'C')
 def test_pin_alias_drift(self):
  with tempfile.TemporaryDirectory()as d:
   p=P(d)/'lib';p.write_bytes(b'a');link=P(d)/'link';link.symlink_to(p);first=a.pin(link);p.write_bytes(b'b');self.assertNotEqual(first,a.pin(link))
 def test_loader_inherits_outer_owned_group(self):
  class Child:
   returncode=0
   def wait(self,timeout=None):return 0
   def poll(self):return 0
  def launch(argv,**kw):
   self.assertNotIn('start_new_session',kw);self.assertEqual(kw['env'],a.clean_env());kw['stdout'].write(b'linux-vdso.so.1 (0x1)\n');return Child()
  with mock.patch.object(a.subprocess,'Popen',side_effect=launch):self.assertIn('linux-vdso',a._list('/approved/loader','/approved/dut'))
if __name__=='__main__':unittest.main()
