"""Only tiny temporary files / AST / direct pure functions. No real archive."""
import ast
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('packet_checker_io',HERE/'check_packets.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)

class IoContract(unittest.TestCase):
    def test_no_execute_is_fail_closed_before_input_open(self):
        with patch.object(c,'open_regular',side_effect=AssertionError('input opened')):
            with self.assertRaisesRegex(ValueError,'explicit offline'):
                c.main(['--plan','never','--plan-sha256','0'*64,'--output','never'])
    def test_pin_small_file_and_no_final_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'small';p.write_bytes(b'hello')
            pin=dict(path=str(p),bytes=5,sha256=hashlib.sha256(b'hello').hexdigest())
            self.assertEqual(c.read_pinned(pin,5),b'hello')
            with self.assertRaises(ValueError):c.read_pinned(pin,4)
            with self.assertRaises(ValueError):c.read_pinned(dict(pin,sha256='0'*64),5)
            with self.assertRaises(ValueError):c.read_pinned(dict(pin,bytes=4),5)
            link=Path(d)/'link';link.symlink_to(p)
            with self.assertRaises(OSError):c.read_pinned(dict(pin,path=str(link)),5)
            with self.assertRaises(ValueError):c.open_regular(d)
    def test_plan_shape_resource_rejected_before_read(self):
        base=dict(schema=c.SCHEMA,rows=128,resources=dict(c.RESOURCES),inputs={})
        with patch.object(c,'read_pinned',side_effect=AssertionError('input read')):
            for p in [dict(base,rows=16),dict(base,schema='other'),dict(base,resources={}),base]:
                with self.subTest(p=p), self.assertRaises(ValueError):c.execute_plan(p)
    def test_full_geometry_constants_without_data(self):
        self.assertEqual(c.expected_counts(128),dict(groups=19200,qk_groups=6912,pv_groups=12288,qk_packets=55296,pv_packets=792576,packets=847872,events=2478339))
        # Static work count only; no real event decoding.
        gs=list(c.group_cursor(128));self.assertEqual(len(gs),19200)
        self.assertEqual(gs[0],(0x23,2,255,8,0,0,0,1))
        self.assertEqual(gs[-1],(0x24,0,1,128,127,11,112,None))
    def test_source_import_boundary(self):
        tree=ast.parse((HERE/'check_packets.py').read_text())
        imports=[]
        for n in ast.walk(tree):
            if isinstance(n,ast.Import):imports.extend(x.name for x in n.names)
            elif isinstance(n,ast.ImportFrom):imports.append(n.module)
        self.assertEqual(set(imports),{'argparse','array','hashlib','json','os','pathlib','resource','signal','stat','struct','sys','time'})
        self.assertFalse(any(isinstance(n,ast.Assert) for n in ast.walk(tree)))
    def test_missing_footer_never_success(self):
        r=c.FramedEvents(io.BytesIO(b'Q2EVT1\r\n'),expected_bytes=52,expected_sha256='0'*64,expected_events=1)
        with self.assertRaisesRegex(ValueError,'truncated'):r.next()

if __name__=='__main__':unittest.main(verbosity=2)
