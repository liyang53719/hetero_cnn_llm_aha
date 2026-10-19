#!/usr/bin/env python3
"""Synthetic local-loader counterexamples only; never native code."""
import hashlib
from pathlib import Path
import shutil
import tempfile
import types
import unittest

ROOT=Path(__file__).resolve().parent
raw=(ROOT/'cold_entry.py').read_bytes()
m=types.ModuleType('loader_under_test');m.__file__=str(ROOT/'cold_entry.py');exec(compile(raw,m.__file__,'exec'),m.__dict__)

class LoaderNegative(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='owner-mock-loader-')
        self.p=Path(self.tmp.name)
        for n in m.FILES+['PRODUCTION_MANIFEST.json','test_owner_cold.py']:
            shutil.copyfile(ROOT/n,self.p/n)
    def tearDown(self):self.tmp.cleanup()
    def test_valid(self):
        buffers,test=m.load(self.p)
        self.assertEqual(set(buffers),set(m.FILES));self.assertTrue(test)
    def test_swap_cpp(self):
        p=self.p/'owner_micro.cpp';x=p.read_bytes();p.write_bytes(bytes([x[0]^1])+x[1:])
        with self.assertRaises(ValueError):m.load(self.p)
    def test_truncate(self):
        p=self.p/'owner_micro.cpp';p.write_bytes(p.read_bytes()[:-1])
        with self.assertRaises(ValueError):m.load(self.p)
    def test_symlink(self):
        p=self.p/'owner_micro.cpp';p.rename(self.p/'copy.cpp');p.symlink_to(self.p/'copy.cpp')
        with self.assertRaises(OSError):m.load(self.p)
    def test_missing(self):
        (self.p/'PORTS.json').unlink()
        with self.assertRaises(OSError):m.load(self.p)
    def test_manifest_substitution(self):
        p=self.p/'PRODUCTION_MANIFEST.json';p.write_bytes(p.read_bytes()+b' ')
        with self.assertRaises(ValueError):m.load(self.p)
    def test_test_substitution(self):
        p=self.p/'test_owner_cold.py';x=p.read_bytes();p.write_bytes(bytes([x[0]^1])+x[1:])
        with self.assertRaises(ValueError):m.load(self.p)
    def test_checked_buffer_not_reopened(self):
        buffers,test=m.load(self.p);original=buffers['owner_micro.cpp']
        (self.p/'owner_micro.cpp').write_bytes(b'x'*len(original))
        self.assertEqual(hashlib.sha256(buffers['owner_micro.cpp']).hexdigest(),m.load(ROOT)[0] and hashlib.sha256(original).hexdigest())
        self.assertEqual(buffers['owner_micro.cpp'],original)

if __name__=='__main__':unittest.main(verbosity=2)
