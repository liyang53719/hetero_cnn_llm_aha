"""Cold identity-only checks; never permits numerical execution."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from . import closure as c

class ClosureTests(unittest.TestCase):
    def test_current_bootstrap_stays_fixed(self):
        self.assertEqual(c.bootstrap.digest(),c.BOOTSTRAP_SHA)
    def test_stale_bootstrap_refused(self):
        with patch.object(c.bootstrap,'digest',return_value='0'*64):
            with self.assertRaises(ValueError):c.source_manifest()
    def fixture(self,root):
        for name in ('.github/workflows/qwen2-fullblock-ci-dut.yml',
                     'candidates/qwen2_ci_prepare_diagnostic/diagnostic.py',
                     'candidates/qwen2_supervisor_recovery/launch.py',
                     'candidates/qwen2_supervisor_recovery/observation.py',
                     'candidates/qwen2_retained_write_recovery/debts.py'):
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('fixed')
        directory=root/c.PACKAGE;directory.mkdir(parents=True)
        (directory/'recipe.py').write_text('x=1\n')
        return directory
    def test_source_change_changes_identity(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);d=self.fixture(root)
            with patch.object(c.bootstrap,'digest',return_value=c.BOOTSTRAP_SHA),patch.object(c.bootstrap,'source_manifest',return_value={}),patch.object(c,'preserved_sources',return_value={}):
                a=c.digest(root);(d/'recipe.py').write_text('x=2\n');self.assertNotEqual(a,c.digest(root))
    def test_alias_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);d=self.fixture(root);(d/'alias.py').symlink_to(d/'recipe.py')
            with patch.object(c.bootstrap,'digest',return_value=c.BOOTSTRAP_SHA),patch.object(c.bootstrap,'source_manifest',return_value={}),patch.object(c,'preserved_sources',return_value={}):
                with self.assertRaises(ValueError):c.source_manifest(root)
    def test_generated_payload_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);d=self.fixture(root);(d/'payload.bin').write_bytes(b'x')
            with patch.object(c.bootstrap,'digest',return_value=c.BOOTSTRAP_SHA),patch.object(c.bootstrap,'source_manifest',return_value={}),patch.object(c,'preserved_sources',return_value={}):
                with self.assertRaises(ValueError):c.source_manifest(root)
if __name__=='__main__':unittest.main()
