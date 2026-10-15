"""Tiny synthetic files exercise native identity handoff, never load native code."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from . import native_artifact as n

class NativeBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.directory=self.root/'native';self.directory.mkdir()
        self.binding=self.root/'binding.json';context={}
        for key,name in [('native_library','official_bf16_matrix_silu.so'),('native_receipt','official_bf16_compile.json')]:
            raw=name.encode();(self.directory/name).write_bytes(raw)
            context[key]=dict(path='native/'+name,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
        raw=json.dumps(dict(status='LOCAL_FRESH_BOOTSTRAP_EXACT_SOURCE_MATCH_ORACLE_ONLY',context=context)).encode()
        self.binding.write_bytes(raw)
        for key,value in [('ROOT',self.root),('DIRECTORY',self.directory),('BINDING',self.binding)]:
            p=patch.object(n,key,value);p.start();self.addCleanup(p.stop)
        p=patch.dict(os.environ,{n.BINDING_ENV:hashlib.sha256(raw).hexdigest()});p.start();self.addCleanup(p.stop)
    def test_exact_current_identity(self):self.assertEqual(set(n.identity()),{'library','receipt'})
    def test_binding_tamper_rejected(self):
        self.binding.write_bytes(self.binding.read_bytes()+b' ')
        with self.assertRaises(ValueError):n.identity()
    def test_library_tamper_rejected(self):
        (self.directory/'official_bf16_matrix_silu.so').write_bytes(b'changed')
        with self.assertRaises(ValueError):n.identity()
    def test_missing_handoff_rejected(self):
        with patch.dict(os.environ,{n.BINDING_ENV:''}):
            with self.assertRaises(ValueError):n.identity()
if __name__=='__main__':unittest.main()
