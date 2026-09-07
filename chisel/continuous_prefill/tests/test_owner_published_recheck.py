#!/usr/bin/env python3
"""Exercise storage-audit rejection rules; these are not hardware tests."""
from pathlib import Path
import hashlib,json,os,tempfile,unittest,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import recheck_published_owner_regression as audit

ROOT=Path(os.environ['OWNER_TEST_ARTIFACTS']) if 'OWNER_TEST_ARTIFACTS' in os.environ else Path(tempfile.mkdtemp(prefix='owner_published_recheck_'))
ROOT.mkdir(parents=True,exist_ok=True)

class InventoryTests(unittest.TestCase):
    def fixture(self):
        p=Path(tempfile.mkdtemp(prefix='case_',dir=ROOT));data=b'raw simulation log\n'
        (p/'run.log').write_bytes(data)
        manifest={'run.log':hashlib.sha256(data).hexdigest()}
        (p/'PUBLISHED_SHA256.json').write_text(json.dumps(manifest))
        return p,manifest
    def write(self,p,m):
        (p/'PUBLISHED_SHA256.json').write_text(json.dumps(m))
    def test_exact_bytes(self):
        p,m=self.fixture();self.assertEqual(audit.inventory(p),m)
    def test_empty_manifest(self):
        p,_=self.fixture();self.write(p,{})
        with self.assertRaises(ValueError):audit.inventory(p)
    def test_missing_original_log(self):
        p,m=self.fixture();(p/'run.log').rename(p/'retained_original.log')
        with self.assertRaises(ValueError):audit.inventory(p)
    def test_changed_log(self):
        p,m=self.fixture();(p/'run.log').write_bytes(b'PASS\n')
        with self.assertRaises(ValueError):audit.inventory(p)
    def test_extra_unhashed_file(self):
        p,m=self.fixture();(p/'unexpected.bin').write_bytes(b'not in evidence manifest')
        with self.assertRaises(ValueError):audit.inventory(p)
    def test_traversal(self):
        p,m=self.fixture();self.write(p,{'../run.log':m['run.log']})
        with self.assertRaises(ValueError):audit.inventory(p)
    def test_absolute_path(self):
        p,m=self.fixture();self.write(p,{str(p/'run.log'):m['run.log']})
        with self.assertRaises(ValueError):audit.inventory(p)
    def test_symlink(self):
        p,m=self.fixture();(p/'run.log').rename(p/'retained_raw.log');(p/'run.log').symlink_to(p/'retained_raw.log')
        with self.assertRaises(ValueError):audit.inventory(p)
    def test_bad_digest(self):
        p,m=self.fixture();self.write(p,{'run.log':'x'})
        with self.assertRaises(ValueError):audit.inventory(p)
    def test_wrong_type_digest(self):
        p,m=self.fixture();self.write(p,{'run.log':1})
        with self.assertRaises(ValueError):audit.inventory(p)
    def test_duplicate_json_key(self):
        p,m=self.fixture();(p/'PUBLISHED_SHA256.json').write_text('{"run.log":"'+m['run.log']+'","run.log":"'+m['run.log']+'"}')
        with self.assertRaises(ValueError):audit.inventory(p)
    def test_noncanonical_path(self):
        p,m=self.fixture();self.write(p,{'./run.log':m['run.log']})
        with self.assertRaises(ValueError):audit.inventory(p)

if __name__=='__main__':unittest.main()
