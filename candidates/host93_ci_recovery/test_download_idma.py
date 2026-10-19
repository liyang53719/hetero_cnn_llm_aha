"""Synthetic fixed-download tests; no network or real signal changes."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('Use -I -S -B')
import hashlib, io, pathlib, tempfile, types, unittest
from unittest.mock import patch
P = pathlib.Path(__file__).with_name('download_idma.py')
RAW = P.read_bytes()
if len(RAW) != 5414 or hashlib.sha256(RAW).hexdigest() != '0cf2f4cb4c28c9551f44350ca6a2be670083edb3404c9e80fc7c420f29f6ccfe':
    raise SystemExit('download source identity')
M = types.ModuleType('fixed_download')
M.__file__ = str(P)
exec(compile(RAW, str(P), 'exec', dont_inherit=True), M.__dict__)

class Body(io.BytesIO):
    status = 200
    headers = {}

class Tests(unittest.TestCase):
    def test_redirect_positive(self):
        self.assertEqual(M.signed_target('https://example.blob.core.windows.net/blob?sig=synthetic'), 'https://example.blob.core.windows.net/blob?sig=synthetic')
    def test_redirect_rejects(self):
        for value in ['http://example.blob.core.windows.net/x', 'https://evil.invalid/x', 'https://example.blob.core.windows.net.evil.invalid/x', 'https://u:p@example.blob.core.windows.net/x', 'https://example.blob.core.windows.net:444/x', 'https://example.blob.core.windows.net/x#f']:
            with self.subTest(value=value), self.assertRaises(ValueError): M.signed_target(value)
    def stream(self, raw):
        with patch.object(M, 'SIZE', 3), patch.object(M, 'SHA', hashlib.sha256(b'abc').hexdigest()):
            sink=io.BytesIO(); M.copy_archive(Body(raw),sink,M.time.monotonic()+5); return sink.getvalue()
    def test_good_body(self): self.assertEqual(self.stream(b'abc'), b'abc')
    def test_short_body(self):
        with self.assertRaises(ValueError): self.stream(b'ab')
    def test_long_body(self):
        with self.assertRaises(ValueError): self.stream(b'abcd')
    def test_wrong_hash(self):
        with self.assertRaises(ValueError): self.stream(b'xyz')
    def test_status(self):
        b=Body(b'abc');b.status=206
        with self.assertRaises(ValueError): M.copy_archive(b,io.BytesIO(),M.time.monotonic()+5)
    def test_deadline(self):
        with self.assertRaises(ValueError): M.copy_archive(Body(b'abc'),io.BytesIO(),0)
    def test_signal_preconditions(self):
        with patch.object(M.signal,'pthread_sigmask',return_value={M.signal.SIGALRM}), patch.object(M.signal,'setitimer') as arm:
            with self.assertRaises(ValueError): M.fetch('/unused')
            arm.assert_not_called()
        with patch.object(M.signal,'pthread_sigmask',return_value=set()), patch.object(M.signal,'getitimer',return_value=(1.0,0.0)), patch.object(M.signal,'setitimer') as arm:
            with self.assertRaises(ValueError): M.fetch('/unused')
            arm.assert_not_called()
    def test_token_only_exact_api(self):
        calls=[]
        class Opener:
            def open(self, req, timeout):
                calls.append(req)
                if len(calls)==1:
                    raise M.urllib.error.HTTPError(req.full_url,302,'redirect',{'Location':'https://example.blob.core.windows.net/x?sig=synthetic'},None)
                return Body(b'abc')
        with tempfile.TemporaryDirectory() as tmp, patch.dict(M.os.environ,{'GITHUB_ACTIONS':'true','GH_TOKEN':'synthetic-token'}), patch.object(M.signal,'pthread_sigmask',return_value=set()), patch.object(M.signal,'getitimer',return_value=(0.0,0.0)), patch.object(M.signal,'signal'), patch.object(M.signal,'setitimer'), patch.object(M.urllib.request,'build_opener',return_value=Opener()), patch.object(M,'SIZE',3), patch.object(M,'SHA',hashlib.sha256(b'abc').hexdigest()):
            out=pathlib.Path(tmp)/'a.zip';r=M.fetch(out)
            self.assertEqual(out.read_bytes(),b'abc');self.assertEqual(r['bytes'],3)
            self.assertEqual(calls[0].full_url,M.API)
            self.assertEqual(calls[0].get_header('Authorization'),'Bearer synthetic-token')
            self.assertIsNone(calls[1].get_header('Authorization'))
            self.assertFalse(out.with_name('a.zip.part').exists())

if __name__ == '__main__': unittest.main()
