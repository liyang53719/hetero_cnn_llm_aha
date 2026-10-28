import ast, contextlib, hashlib, json, tempfile, threading, unittest
from pathlib import Path
from unittest.mock import patch
SOURCE=Path(__file__).with_name('acquire.py')
class Response:
 def __init__(self,status=206,body=b'abcd',headers=None):
  self.status=status;self.body=body;self.url='https://us.aws.cdn.hf.co/object'
  self.headers={'Content-Range':'bytes 4-7/20','Content-Length':'4','Content-Encoding':'identity','ETag':'mock'}
  if headers:self.headers.update(headers)
 def __enter__(self):return self
 def __exit__(self,*args):pass
 def read(self,n):return self.body[:n]
class Transport(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.ns={}
  tree=ast.parse(SOURCE.read_text());tree.body=[n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom,ast.FunctionDef)) and not (isinstance(n,ast.ImportFrom) and (n.module or '').startswith('heteronpu'))]
  exec(compile(tree,str(SOURCE),'exec'),self.ns)
  self.ns.update(OUT=Path(self.tmp.name),MAX=8*1024*1024,BODY_CAP=4,stop=threading.Event(),lock=threading.Lock(),totals={'requested':0,'received':0,'requests':0})
 def tearDown(self):self.tmp.cleanup()
 def call(self,r):
  with patch('urllib.request.urlopen',return_value=r):return self.ns['fetch']('https://huggingface.co/model/resolve/pin/file',4,7,20,'mock')
 def test_success(self):
  self.assertEqual(self.call(Response()),b'abcd');self.assertEqual(self.ns['totals']['received'],4)
  x=json.loads((self.ns['OUT']/'requests.jsonl').read_text());self.assertEqual(x['sha256'],hashlib.sha256(b'abcd').hexdigest());self.assertEqual(x['etag'],'mock')
 def test_wrong_status(self):
  with self.assertRaises(ValueError):self.call(Response(status=200))
 def test_wrong_range(self):
  with self.assertRaises(ValueError):self.call(Response(headers={'Content-Range':'bytes 0-3/20'}))
 def test_wrong_length(self):
  with self.assertRaises(ValueError):self.call(Response(headers={'Content-Length':'5'}))
 def test_encoding(self):
  with self.assertRaises(ValueError):self.call(Response(headers={'Content-Encoding':'gzip'}))
 def test_short(self):
  with self.assertRaises(ValueError):self.call(Response(body=b'abc'))
 def test_long(self):
  with self.assertRaises(ValueError):self.call(Response(body=b'abcde'))
 def test_stop(self):
  self.ns['stop'].set()
  with self.assertRaises(ValueError):self.call(Response())
 def test_cap(self):
  self.ns['BODY_CAP']=3
  with self.assertRaises(ValueError):self.call(Response())
 def test_non_https_redirect(self):
  r=Response();r.url='http://example.com/file'
  with self.assertRaises(ValueError):self.call(r)
if __name__=='__main__':unittest.main()
