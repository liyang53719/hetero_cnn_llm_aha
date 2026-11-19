import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from receipt_verify import verify


class ReceiptTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'cp').mkdir()
        for p in ('cp/host', 'identity'):
            (self.root/p).write_bytes(b'test')
        h = hashlib.sha256(b'test').hexdigest()
        self.doc = {'directory':'cp','next_cycle':100,'files':{'host':h},'identity':{'identity':h}}

    def check(self, raw=None):
        (self.root/'receipt').write_text(json.dumps(self.doc) if raw is None else raw)
        return verify('receipt', self.root, required_files=('host',), required_identity=('identity',))

    def test_valid(self):
        self.assertEqual(self.check()['next_cycle'],100)

    def test_missing_required(self):
        self.doc['files'] = {'other':'a'*64}
        with self.assertRaises(ValueError):
            self.check()

    def test_traversal(self):
        self.doc['directory']='cp/../cp'
        with self.assertRaises(ValueError):
            self.check()

    def test_symlink(self):
        (self.root/'alias').symlink_to('cp')
        self.doc['directory']='alias'
        with self.assertRaises(ValueError):
            self.check()

    def test_digest_mismatch(self):
        (self.root/'cp/host').write_text('corrupt')
        with self.assertRaises(ValueError):
            self.check()

    def test_wrong_identity(self):
        self.doc['identity']={'cp/host':self.doc['identity']['identity']}
        with self.assertRaises(ValueError):
            self.check()

    def test_duplicate(self):
        with self.assertRaises(ValueError):
            self.check('{"directory":"cp","directory":"elsewhere"}')

    def test_bool_cycle(self):
        self.doc['next_cycle']=True
        with self.assertRaises(ValueError):
            self.check()


if __name__ == '__main__':
    unittest.main()
