import importlib.util
from pathlib import Path
import tempfile
import unittest
spec=importlib.util.spec_from_file_location('inventory',Path(__file__).with_name('platform_inventory.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class InventoryTests(unittest.TestCase):
    def test_complete_inventory_never_admits_execution(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'synthetic';p.write_bytes(b'fixture only')
            r=m.collect(dict.fromkeys(m.NAMES,p),p)
            self.assertFalse(r['numeric_execution_allowed']);self.assertFalse(r['model_executed'])
            self.assertEqual(r['missing_native_names'],[]);self.assertEqual(len(r['native_files']),6)
            self.assertEqual(r['native_files']['python']['bytes'],12)
    def test_missing_names_are_explicit(self):
        r=m.collect(dict.fromkeys(m.NAMES,None))
        self.assertEqual(r['missing_native_names'],list(m.NAMES));self.assertIsNone(r['compiler'])
        self.assertFalse(r['numeric_execution_allowed'])
    def test_extra_or_missing_identity_rejected(self):
        for p in ({},{**dict.fromkeys(m.NAMES,None),'extra':None}):
            with self.assertRaises(ValueError):m.collect(p)
    def test_ambiguous_native_path_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'a.so').touch();(p/'b.so').touch()
            self.assertIsNone(m.one(p,'*.so'))
    def test_directory_not_file(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):m.identity(d)
if __name__=='__main__':unittest.main()
