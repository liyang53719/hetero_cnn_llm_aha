import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fresh_tail',HERE/'acquire.py')
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


class Response:
    def __init__(self, raw=b'\x01\x02\x03\x04'):
        self.status = 206
        self.headers = {'Content-Range':'bytes 10-13/100','Content-Length':'4'}
        self.raw, self.reads = raw, []
    def read(self, count):
        self.reads.append(count)
        return self.raw


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.pins = {'shard':{'url':a.URL,'checkpoint_file_bytes':100}}
        self.segment = {'start':10,'end':13,'bytes':4,'sha256':a.digest(b'\x01\x02\x03\x04')}

    def test_valid_response_exact_bound(self):
        response = Response()
        raw, receipt = a.response_bytes(response,self.segment,self.pins)
        self.assertEqual(response.reads,[5])
        self.assertEqual(raw,response.raw)
        self.assertEqual(receipt['status'],206)
        self.assertEqual(receipt['requested_url'],a.URL)
        self.assertEqual(a.parse_time(receipt['acquired_at']).utcoffset().total_seconds(),0)

    def test_bad_status_rejected_before_body(self):
        for status in (200,204,301,403):
            with self.subTest(status=status):
                response=Response(); response.status=status
                with self.assertRaises(a.Rejected): a.response_bytes(response,self.segment,self.pins)
                self.assertEqual(response.reads,[])

    def test_bad_headers_rejected_before_body(self):
        for header, value in [('Content-Range','bytes 11-14/100'),('Content-Range','bytes 10-13/101'),
                ('Content-Length','5'),('Content-Length',None),('Content-Encoding','gzip')]:
            with self.subTest(header=header,value=value):
                response=Response(); response.headers[header]=value
                with self.assertRaises(a.Rejected): a.response_bytes(response,self.segment,self.pins)
                self.assertEqual(response.reads,[])

    def test_short_overlong_wrong_hash_rejected(self):
        for data in (b'123',b'12345',b'1234'):
            with self.subTest(data=data):
                with self.assertRaises(a.Rejected): a.response_bytes(Response(data),self.segment,self.pins)

    def test_unbounded_range_rejected_before_body(self):
        for size in (0,-1,8388609,True):
            segment={**self.segment,'bytes':size}
            response=Response()
            with self.subTest(size=size):
                with self.assertRaises(a.Rejected): a.response_bytes(response,segment,self.pins)
                self.assertEqual(response.reads,[])

    def test_nonofficial_url_rejected_before_request(self):
        self.pins['shard']['url']='https://example.invalid/model'
        with patch('urllib.request.urlopen',side_effect=AssertionError('network')):
            with self.assertRaises(a.Rejected): a.download(self.segment,self.pins)

    def test_safe_path_rejects_aliases(self):
        for relative in ('/tmp/raw','work/../raw','work//raw','./work/raw','work\\raw'):
            with self.subTest(path=relative),self.assertRaises(a.Rejected): a.safe_path(a.ROOT,relative)

    def test_stage_namespace_is_exact(self):
        for relative in ('work/qwen2_tail_ranges_20261014','work/qwen2_live_tail_inputs_m128/new/raw',
                         a.PREFIX+'/new/raw/extra',a.PREFIX+'/new/.raw'):
            with self.subTest(path=relative),self.assertRaises(a.Rejected): a.stage_path(a.ROOT,relative)

    def test_stage_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); (root/'work').symlink_to(root)
            with self.assertRaises(a.Rejected): a.stage_path(root,a.PREFIX+'/new/raw')

    def test_existing_output_rejected_without_request(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); relative=a.PREFIX+'/new/raw'
            (root/relative).mkdir(parents=True)
            with patch.object(a,'download',side_effect=AssertionError('network')):
                with self.assertRaises(a.Rejected): a.acquire(root,relative,{},self.pins)

    def test_exclusive_write(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'raw'; a.write_new(path,b'first')
            with self.assertRaises(FileExistsError): a.write_new(path,b'second')
            self.assertEqual(path.read_bytes(),b'first')

    def test_missing_optins_rejected_before_contract(self):
        options=[['--execute'],['--action','acquire','--out',a.PREFIX+'/new/raw'],
                 ['--action','acquire','--execute','--out',a.PREFIX+'/new/raw'],
                 ['--action','audit','--execute','--subset',a.PREFIX+'/new/raw','--download']]
        with patch.object(a,'load_contract',side_effect=AssertionError('contract read')):
            for args in options:
                with self.subTest(args=args),self.assertRaises(a.Rejected): a.main(args)

    def test_default_is_source_only(self):
        real_open = io.open
        def guarded(file,*args,**kwargs):
            path=str(file)
            if '/work/' in path or path.startswith('work/'):
                raise AssertionError('raw/work read')
            if args and any(c in args[0] for c in 'wax+'):
                raise AssertionError('write')
            return real_open(file,*args,**kwargs)
        with patch('io.open',side_effect=guarded), \
             patch.object(a,'download',side_effect=AssertionError('network')), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            result=a.main([])
        self.assertEqual(result['status'],'NOT_EXECUTED')
        self.assertFalse(result['network_used'])
        self.assertFalse(result['raw_payload_read'])
        self.assertEqual(json.loads(output.getvalue()),result)

    def test_original_source_and_pin_identities(self):
        namespace,pins=a.load_contract()
        self.assertEqual(len(pins['tensors']),5)
        self.assertEqual(sum(t['bytes'] for t in pins['tensors']),87297024)
        self.assertEqual(sum(len(t['segments']) for t in pins['tensors']),14)
        self.assertEqual(namespace['PINS_SHA256'],a.PIN_SHA256)

    def test_timestamp_timezone_required(self):
        for value in (True,None,'2026-10-15T00:00:00','2026-10-15T01:00:00+01:00'):
            with self.subTest(value=value),self.assertRaises((ValueError,TypeError)): a.parse_time(value)


if __name__ == '__main__':
    unittest.main()
