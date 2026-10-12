"""Exact source/metadata closure; no model weights or actual-input dependency."""
from pathlib import Path
import hashlib,json,unittest
HERE=Path(__file__).resolve().parent
class DeliveryTests(unittest.TestCase):
    def test_exact_files_and_acceptance_scope(self):
        m=json.loads((HERE/'delivery_manifest.json').read_text())
        names={p.name for p in HERE.iterdir() if p.is_file() and p.name!='delivery_manifest.json'}
        self.assertEqual(names,set(m['files']))
        for name,identity in m['files'].items():
            data=(HERE/name).read_bytes()
            self.assertEqual(len(data),identity['bytes'],name)
            self.assertEqual(hashlib.sha256(data).hexdigest(),identity['sha256'],name)
        self.assertFalse(m['rtl_generated'])
        self.assertFalse(m['hardware_arithmetic_executed'])
        self.assertFalse(m['full_host_execution'])
        self.assertEqual(m['native_acceptance'],'UNCHANGED_FAIL_POLICY_PENDING')
if __name__=='__main__':unittest.main()
