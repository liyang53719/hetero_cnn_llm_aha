"""Small synthetic helper controls, not hardware or numerical tests."""
import importlib.util,json,tempfile,unittest,hashlib
from pathlib import Path
spec=importlib.util.spec_from_file_location('helper',Path(__file__).with_name('rebuild_metadata.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Controls(unittest.TestCase):
    def test_patch(self):
        patch=b'--- a/a.scala\n+++ b/a.scala\n@@ -1,2 +1,2 @@\n a\n-b\n+c\n'
        self.assertEqual(m.apply_patch(b'a\nb\n',patch,'a.scala'),b'a\nc\n')
        for p in [patch.replace(b'--- a/',b'--- x/'),patch.replace(b'@@ -1,2',b'@@ -2,2'),patch.replace(b'-b',b'-x'),patch.replace(b'+1,2',b'+1,3'),patch+b'?bad\n',patch.replace(b'+1,2',b'+2,2')]:
            with self.assertRaises(ValueError):m.apply_patch(b'a\nb\n',p,'a.scala')
    def test_paths_hashes(self):
        with tempfile.TemporaryDirectory()as t:
            p=Path(t);(p/'a').write_text('x');identity={'bytes':1,'sha256':hashlib.sha256(b'x').hexdigest()}
            self.assertEqual(m.checked(p,'a',identity),b'x')
            for n in ['../a','/a','b\\a','./a']:
                with self.assertRaises(ValueError):m.read(p,n)
            with self.assertRaises(ValueError):m.checked(p,'a',dict(identity,bytes=2))
            with self.assertRaises(ValueError):m.checked(p,'a',dict(identity,sha256='0'*64))
            (p/'sym').symlink_to('a')
            with self.assertRaises(ValueError):m.read(p,'sym')
            (p/'bin').write_bytes(b'\0')
            with self.assertRaises(ValueError):m.read(p,'bin')
    def test_classes(self):
        r={'relative':'a/X.class','bytes':2,'sha256':'a'*64}
        self.assertEqual(len(m.classmap([r])),1)
        for rows in [[r,r],[dict(r,relative='../X.class')],[dict(r,bytes=0)],[dict(r,sha256='bad')],[dict(r,relative='X.scala')]]:
            with self.assertRaises(ValueError):m.classmap(rows)

if __name__=='__main__':unittest.main()
