import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

p=Path(__file__).resolve().parents[1]/'materialize.py'
s=importlib.util.spec_from_file_location('new_tail_materializer',p)
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


class MaterializeTests(unittest.TestCase):
    def test_default_no_payload_or_network(self):
        with patch.object(m,'snapshot',side_effect=AssertionError('raw')),\
             patch.object(m.a,'download',side_effect=AssertionError('network')),\
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(m.main([])['status'],'NOT_EXECUTED')

    def test_required_flags(self):
        for args in [['--action','materialize','--out','x','--subset','y'],
                     ['--action','audit','--execute','--subset','y','--out','x'],
                     ['--execute']]:
            with self.subTest(args=args),patch.object(m.a,'load_contract',side_effect=AssertionError('read')):
                with self.assertRaises(ValueError):m.main(args)

    def test_existing_output_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)
            with patch.object(m.r,'stage',return_value=path),self.assertRaises(ValueError):
                m.materialize('out','subset',{}, {})

    def test_original_transpose_and_correspondence(self):
        namespace,pins=m.a.load_contract();_,transpose=namespace['conversion_functions'](m.ROOT,pins)
        raw=bytes(range(12));out=transpose(raw,3,2)
        namespace['verify_correspondence'](raw,out,dict(bytes=12,widened=False,source_shape=[3,2]))
        bad=bytes([out[0]^1])+out[1:]
        with self.assertRaises(ValueError):
            namespace['verify_correspondence'](raw,bad,dict(bytes=12,widened=False,source_shape=[3,2]))

    def test_original_gamma_and_correspondence(self):
        namespace,pins=m.a.load_contract();widen,_=namespace['conversion_functions'](m.ROOT,pins)
        raw=bytes(range(6));out=widen(raw)
        namespace['verify_correspondence'](raw,out,dict(bytes=12,widened=True))
        with self.assertRaises(ValueError):
            namespace['verify_correspondence'](raw,b'\x01'+out[1:],dict(bytes=12,widened=True))


if __name__=='__main__':unittest.main()
