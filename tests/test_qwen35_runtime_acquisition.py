"""No-network tests for exact-source bounded acquisition."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('acquirer', ROOT / 'scripts/acquire_qwen35_official_runtime.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Response:
    def __init__(self, body=b'', status=200, headers=None):
        self.body = body
        self.status = status
        self.headers = headers or {}
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, count):
        result, self.body = self.body[:count], self.body[count:]
        return result


class Opener:
    def __init__(self, *responses): self.responses = list(responses); self.calls = []
    def open(self, request, timeout):
        self.calls.append(request.full_url)
        return self.responses.pop(0)


class BoundedAcquisitionTests(unittest.TestCase):
    def pin(self, body): return dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
    def test_exact_body_and_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp); target = output/'artifact.whl'
            opener = Opener(Response(b'known', headers={'Content-Length':'5'}))
            collector = MODULE.BoundedAcquisition(output, opener=opener)
            collector.fetch('https://files.pythonhosted.org/known.whl',target,self.pin(b'known'))
            self.assertEqual(target.read_bytes(),b'known');self.assertEqual(collector.total,5)
    def test_body_overrun_preserves_failure_not_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp);target=output/'artifact.whl'
            collector=MODULE.BoundedAcquisition(output,opener=Opener(Response(b'knownX')))
            with self.assertRaisesRegex(ValueError,'budget exceeded'):
                collector.fetch('https://files.pythonhosted.org/known.whl',target,self.pin(b'known'))
            self.assertFalse(target.exists());self.assertTrue(target.with_name(target.name+'.partial').exists())
    def test_hash_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp);target=output/'artifact.whl'
            collector=MODULE.BoundedAcquisition(output,opener=Opener(Response(b'wrong')))
            with self.assertRaisesRegex(ValueError,'identity differs'):
                collector.fetch('https://files.pythonhosted.org/known.whl',target,self.pin(b'known'))
            self.assertFalse(target.exists())
    def test_declared_size_mismatch_before_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp);response=Response(b'known',headers={'Content-Length':'999'})
            collector=MODULE.BoundedAcquisition(output,opener=Opener(response))
            with self.assertRaisesRegex(ValueError,'Declared size'):
                collector.fetch('https://files.pythonhosted.org/known.whl',output/'a',self.pin(b'known'))
            self.assertEqual(response.body,b'known')
    def test_unapproved_redirect_rejected_without_second_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            opener=Opener(Response(status=302,headers={'Location':'https://example.org/no'}))
            collector=MODULE.BoundedAcquisition(Path(tmp),opener=opener)
            with self.assertRaises(ValueError):
                collector.fetch('https://github.com/huggingface/transformers/archive/pin.zip',Path(tmp)/'a',self.pin(b'x'))
            self.assertEqual(len(opener.calls),1)
    def test_existing_output_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'a';target.write_bytes(b'old');opener=Opener()
            collector=MODULE.BoundedAcquisition(Path(tmp),opener=opener)
            with self.assertRaisesRegex(ValueError,'overwrite'):
                collector.fetch('https://files.pythonhosted.org/a',target,self.pin(b'x'))
            self.assertEqual(target.read_bytes(),b'old');self.assertFalse(opener.calls)
    def test_unsafe_urls_rejected(self):
        for url in ['http://files.pythonhosted.org/a','https://user:secret@files.pythonhosted.org/a','https://files.pythonhosted.org/a?token=x','https://files.pythonhosted.org:444/a','https://evil.example/a']:
            with self.subTest(url=url),self.assertRaises(ValueError):MODULE.checked_url(url)
    def test_public_lock_exact_reviewed_identity(self):
        path=ROOT/'config/upstream/qwen3_5_0p8b/official_runtime_lock_20261023.json'
        self.assertEqual(MODULE.sha(path),MODULE.LOCK_SHA256)
        content=path.read_text()
        for private in ['/workspace/','/tmp/','/home/']:self.assertNotIn(private,content)


if __name__=='__main__':unittest.main()
