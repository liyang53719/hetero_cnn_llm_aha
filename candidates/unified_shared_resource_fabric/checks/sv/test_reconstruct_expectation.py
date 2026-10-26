"""Small packaging controls only; no actual FIR/SV, JVM or native target."""
from pathlib import Path
import hashlib, importlib.util, json, tempfile, unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('expectation_packaging', HERE / 'reconstruct_expectation.py')
helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)

class PackagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = helper.build()

    def test_original_exact_bytes(self):
        self.assertEqual(len(self.raw), 1868089)
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), helper.EXPECTED_SHA256)

    def test_strict_missing_outputs_still_required(self):
        x = json.loads(self.raw); ports = x['selected_module_ports']['UnifiedSharedResourceTop']
        self.assertEqual(len(ports), 4599)
        self.assertEqual(ports['io_completeBlockImplemented'], {'direction':'output','signed':False,'width':1})
        self.assertEqual(ports['io_result_bits_version'], {'direction':'output','signed':False,'width':8})

    def test_collection_is_separate(self):
        x = json.loads(self.raw)
        self.assertEqual(len(x['top_ports']), 4618)
        self.assertEqual(len(x['selected_module_ports']), 7)
        self.assertNotEqual(x['product'], x['top'])

    def test_new_output_only(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'new.json'; helper.write_new(p, self.raw)
            self.assertEqual(p.read_bytes(), self.raw)
            with self.assertRaises(ValueError): helper.write_new(p, b'changed')
            self.assertEqual(p.read_bytes(), self.raw)

    def test_broken_symlink_output_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'link';p.symlink_to(Path(d)/'absent')
            with self.assertRaises(ValueError): helper.write_new(p,self.raw)

    def test_symlink_parent_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'real').mkdir();(p/'alias').symlink_to(p/'real',target_is_directory=True)
            with self.assertRaises(ValueError): helper.write_new(p/'alias'/'new.json',self.raw)

    def test_missing_parent_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError): helper.write_new(Path(d)/'absent'/'new.json',self.raw)

    def test_pinned_input_mutation_and_size_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'input';p.write_bytes(b'a')
            with self.assertRaises(ValueError): helper.pinned(p,'0'*64,10)
            with self.assertRaises(ValueError): helper.pinned(p,hashlib.sha256(b'a').hexdigest(),0)

if __name__ == '__main__': unittest.main()
