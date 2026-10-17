#!/usr/bin/env python3
"""Cold archive fixtures only. No network, subprocess, or binary execution."""
import gzip,hashlib,io,json,lzma,signal,tarfile,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import bootstrap_tools as b

def tar(rows):
 data=io.BytesIO()
 with tarfile.open(fileobj=data,mode='w') as t:
  for name,kind,content in rows:
   m=tarfile.TarInfo(name)
   if kind=='file':m.size=len(content);t.addfile(m,io.BytesIO(content))
   elif kind=='dir':m.type=tarfile.DIRTYPE;t.addfile(m)
   elif kind=='link':m.type=tarfile.SYMTYPE;m.linkname=content;t.addfile(m)
   elif kind=='hard':m.type=tarfile.LNKTYPE;m.linkname=content;t.addfile(m)
   else:m.type=tarfile.FIFOTYPE;t.addfile(m)
 return data.getvalue()

def ar(rows):
 data=b'!<arch>\n'
 for name,body in rows:
  header=(name.ljust(16)+'0'.ljust(12)+'0'.ljust(6)+'0'.ljust(6)+'100644'.ljust(8)+str(len(body)).ljust(10)+'`\n').encode()
  data+=header+body+(b'\n' if len(body)%2 else b'')
 return data

def deb(raw):
 return ar([('debian-binary',b'2.0\n'),('control.tar.xz',lzma.compress(tar([]))),('data.tar.xz',lzma.compress(raw))])

class BootstrapTests(unittest.TestCase):
 def test_original_pins(self):
  self.assertEqual(b.ASSETS['bender'][1],'05c2c9c82ddc0b3f45141a1e30dbcfba3b9a98a7d2ad0f9003651c0655c7a2fe')
  self.assertEqual(b.ASSETS['uv'][1],'920cbcaad514cc185634f6f0dcd71df5e8f4ee4456d440a22e0f8c0f142a8203')
 def test_deb_selected_binary_only(self):
  raw=tar([('./usr/bin/verilator_bin','file',b'fixture'),('./docs/link','link','../../untrusted')])
  with tempfile.TemporaryDirectory() as d,patch.object(b,'VERILATOR_SHA',hashlib.sha256(b'fixture').hexdigest()):
   path,digest=b.extract_binary(deb(raw),'verilator',Path(d)/'out')
   self.assertEqual(path.read_bytes(),b'fixture');self.assertEqual([p.name for p in path.parent.iterdir()],['verilator_bin'])
 def test_tool_tar_variants(self):
  for name,compress in [('uv',gzip.compress),('bender',lzma.compress)]:
   with tempfile.TemporaryDirectory() as d:
    path,_=b.extract_binary(compress(tar([(f'tool/{name}','file',b'fake')])) ,name,Path(d)/'out')
    self.assertEqual(path.read_bytes(),b'fake')
 def test_binary_hash_mismatch(self):
  with tempfile.TemporaryDirectory() as d,self.assertRaises(ValueError):
   b.extract_binary(deb(tar([('usr/bin/verilator_bin','file',b'wrong')])), 'verilator',Path(d)/'out')
 def test_ar_duplicate_and_unexpected(self):
  for rows in [[('debian-binary',b'2.0\n')]*2,[('../data.tar.xz',b'x')],[('//',b'x')]]:
   with self.assertRaises(ValueError):b.ar_data(ar(rows))
 def test_ar_truncation_and_padding(self):
  for data in [b'',b'!<arch>\nX',ar([('debian-binary',b'x')])[:-1],deb(tar([]))[:-1]]:
   with self.assertRaises(ValueError):b.ar_data(data)
 def test_duplicate_tar_normalized(self):
  for rows in [[('a','file',b'1'),('./a','file',b'2')],[('a/','dir',b''),('a','dir',b'')]]:
   with self.assertRaises(ValueError):b.tar_members(tar(rows))
 def test_tar_paths_and_special(self):
  for name,kind in [('../x','file'),('/x','file'),('a/../x','file'),('a\\x','file'),('x','fifo')]:
   with self.assertRaises(ValueError):b.tar_members(tar([(name,kind,b'x')]),True)
 def test_selected_link_and_ancestor(self):
  for rows in [[('usr/bin/verilator_bin','link','/outside')], [('usr','link','/outside'),('usr/bin/verilator_bin','file',b'x')]]:
   with tempfile.TemporaryDirectory() as d,self.assertRaises(ValueError):
    b.extract_binary(deb(tar(rows)),'verilator',Path(d)/'out')
 def test_other_tools_reject_links(self):
  with self.assertRaises(ValueError):b.tar_members(tar([('x','link','outside')]))
 def test_decompression_cap_and_trailing(self):
  for compress in [gzip.compress,lzma.compress]:
   data=compress(b'A'*2048)
   with patch.object(b,'EXPANDED_LIMIT',1024),self.assertRaises((ValueError,lzma.LZMAError)):
    b.unpack_compression(data)
   with self.assertRaises(ValueError):b.unpack_compression(data+b'trailing')
 def test_member_count_and_size_caps(self):
  with self.assertRaises(ValueError):b.tar_members(tar([(f'd{i}','dir',b'') for i in range(1001)]))
  with patch.object(b,'MEMBER_LIMIT',2),self.assertRaises(ValueError):b.tar_members(tar([('x','file',b'123')]))
 def test_download_cap(self):
  with patch.object(b,'DOWNLOAD_LIMIT',8),self.assertRaises(ValueError):b.ar_data(b'x'*9)
 def test_signal_restored_on_existing_output(self):
  old=signal.getsignal(signal.SIGALRM)
  with tempfile.TemporaryDirectory() as d,self.assertRaises(FileExistsError):b.main(d)
  self.assertEqual(signal.getsignal(signal.SIGALRM),old);self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))
 def test_signal_restored_on_network_error(self):
  old=signal.getsignal(signal.SIGALRM)
  with tempfile.TemporaryDirectory() as d,patch.object(b.urllib.request,'urlopen',side_effect=TimeoutError('mock')),self.assertRaises(TimeoutError):
   b.main(Path(d)/'out')
  self.assertEqual(signal.getsignal(signal.SIGALRM),old);self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))
 def test_existing_alarm_untouched(self):
  signal.setitimer(signal.ITIMER_REAL,60)
  try:
   with self.assertRaises(ValueError):b.main('unused')
   self.assertGreater(signal.getitimer(signal.ITIMER_REAL)[0],59)
  finally:signal.setitimer(signal.ITIMER_REAL,0)
 def test_mocked_bootstrap_identity(self):
  with tempfile.TemporaryDirectory() as d:
   data=lzma.compress(tar([('bender','file',b'fake')]))
   with patch.object(b,'ASSETS',{'bender':('https://invalid.example/fixture',hashlib.sha256(data).hexdigest())}),patch.object(b.urllib.request,'urlopen',return_value=io.BytesIO(data)):
    b.main(Path(d)/'out')
   value=json.loads((Path(d)/'out/TOOLS.json').read_text())
   self.assertEqual(value['bender']['sha256'],hashlib.sha256(b'fake').hexdigest())

 def test_mocked_verilator_identity(self):
  data=deb(tar([('usr/bin/verilator_bin','file',b'fixture')]))
  digest=hashlib.sha256(data).hexdigest();binary_digest=hashlib.sha256(b'fixture').hexdigest()
  with tempfile.TemporaryDirectory() as d,patch.object(b,'ASSETS',{'verilator':('https://invalid.example/fixture.deb',digest)}),patch.object(b,'VERILATOR_SHA',binary_digest),patch.object(b.urllib.request,'urlopen',return_value=io.BytesIO(data)):
   b.main(Path(d)/'out')
   value=json.loads((Path(d)/'out/TOOLS.json').read_text())
   self.assertEqual(set(value),{'verilator'})
   self.assertEqual(value['verilator']['archive_sha256'],digest)
   self.assertEqual(value['verilator']['sha256'],binary_digest)
   self.assertEqual(Path(value['verilator']['path']).name,'verilator_bin')

if __name__=='__main__':unittest.main()
