"""Tiny in-memory archives only; never download/execute a package or read real SV."""
import hashlib,importlib.util,io,sys,tarfile,tempfile,unittest
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent

def module(name):
 spec=importlib.util.spec_from_file_location(name,ROOT/'source'/f'{name}.py')
 m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
OLD=module('restore_package');NEW=module('extract_verified_package_r2')

def archive(entries):
 b=io.BytesIO()
 with tarfile.open(fileobj=b,mode='w') as tf:
  for name,kind,value in entries:
   m=tarfile.TarInfo(name);m.mode=0o755 if kind=='dir' else 0o644
   if kind=='file':m.size=len(value);tf.addfile(m,io.BytesIO(value))
   else:
    m.type={'dir':tarfile.DIRTYPE,'sym':tarfile.SYMTYPE,'hard':tarfile.LNKTYPE,'fifo':tarfile.FIFOTYPE}[kind]
    m.linkname=value;tf.addfile(m)
 return b.getvalue()

def ar(entries):
 b=b'!<arch>\n'
 for name,value in entries:
  header=(name+'/').ljust(16)+'0'.ljust(12)+'0'.ljust(6)+'0'.ljust(6)+'100644'.ljust(8)+str(len(value)).ljust(10)+'`\n'
  b+=header.encode()+value+(b'\n' if len(value)%2 else b'')
 return b

class SmallControls(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory(prefix='lint_archive_controls_',dir='/tmp');self.base=Path(self.tmp.name)
 def tearDown(self):self.tmp.cleanup()
 def unpack(self,entries,m=NEW):return m.unpack(archive(entries),self.base/'out')
 def test_01_lock_same(self):self.assertEqual((OLD.URL,OLD.SIZE,OLD.SHA),(NEW.URL,NEW.SIZE,NEW.SHA))
 def test_02_ar_even_odd(self):self.assertEqual(NEW.members_ar(ar([('a',b'12'),('b',b'3')])),{'a':b'12','b':b'3'})
 def test_03_ar_bad_magic(self):
  with self.assertRaises(ValueError):NEW.members_ar(b'bad')
 def test_04_ar_short_header(self):
  with self.assertRaises(ValueError):NEW.members_ar(b'!<arch>\n123')
 def test_05_ar_duplicate(self):
  with self.assertRaises(ValueError):NEW.members_ar(ar([('a',b''),('a',b'')]))
 def test_06_ar_truncated(self):
  with self.assertRaises(ValueError):NEW.members_ar(ar([('a',b'12')])[:-1])
 def test_07_regular(self):
  rows=self.unpack([('dir','dir',''),('dir/a','file',b'ABC')]);self.assertEqual((self.base/'out/dir/a').read_bytes(),b'ABC');self.assertEqual(rows[1]['sha256'],hashlib.sha256(b'ABC').hexdigest())
 def test_08_fresh_target(self):
  (self.base/'out').mkdir()
  with self.assertRaises(FileExistsError):self.unpack([('a','file',b'a')])
 def test_09_traversal(self):
  with self.assertRaises(ValueError):self.unpack([('../escape','file',b'a')])
 def test_10_absolute(self):
  with self.assertRaises(ValueError):self.unpack([('/escape','file',b'a')])
 def test_11_duplicate_tar(self):
  with self.assertRaises(ValueError):self.unpack([('a','file',b'a'),('a','file',b'b')])
 def test_12_fifo(self):
  with self.assertRaises(ValueError):self.unpack([('pipe','fifo','')])
 def test_13_valid_symlink(self):
  self.unpack([('a','file',b'a'),('b','sym','a')]);self.assertTrue((self.base/'out/b').is_symlink());self.assertEqual((self.base/'out/b').read_bytes(),b'a')
 def test_14_absolute_symlink(self):
  with self.assertRaises(ValueError):self.unpack([('b','sym','/escape')])
 def test_15_escaping_symlink(self):
  with self.assertRaises(ValueError):self.unpack([('b','sym','../escape')])
 def test_16_missing_non_doc(self):
  with self.assertRaises(ValueError):self.unpack([('b','sym','missing')])
 def test_17_missing_doc_old_rejects(self):
  with self.assertRaises(ValueError):self.unpack([('usr/share/doc/verilator/a','sym','missing')],OLD)
 def test_18_missing_doc_new_accepts(self):
  rows=self.unpack([('usr/share/doc/verilator/a','sym','missing')]);self.assertFalse(rows[0]['target_member_present']);self.assertTrue((self.base/'out/usr/share/doc/verilator/a').is_symlink())
 def test_19_doc_escape_rejected(self):
  with self.assertRaises(ValueError):self.unpack([('usr/share/doc/verilator/a','sym','../../../../../escape')])
 def test_20_missing_doc_hardlink_rejected(self):
  with self.assertRaises(ValueError):self.unpack([('usr/share/doc/verilator/a','hard','usr/share/doc/verilator/missing')])
 def test_21_valid_hardlink(self):
  self.unpack([('a','file',b'a'),('b','hard','a')]);self.assertEqual((self.base/'out/a').stat().st_ino,(self.base/'out/b').stat().st_ino)
 def test_22_digest(self):
  p=self.base/'tiny';p.write_bytes(b'tiny');self.assertEqual(NEW.digest(p),hashlib.sha256(b'tiny').hexdigest())
 def test_23_explicit_need(self):
  with self.assertRaises(ValueError):NEW.need(False,'negative')
 def test_24_original_regular(self):self.assertEqual(self.unpack([('a','file',b'x')],OLD)[0]['bytes'],1)

if __name__=='__main__':unittest.main(verbosity=2)
