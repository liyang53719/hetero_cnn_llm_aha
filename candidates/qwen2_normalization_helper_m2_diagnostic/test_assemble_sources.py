"""Stdlib tests of packaging utility only; no target modules, tensors or native code."""
from pathlib import Path
import copy
import hashlib
import importlib.util
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('source_assembler', Path(__file__).with_name('assemble_sources.py'))
assembler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assembler)

class Assembly(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        self.out = self.root / 'output'
        self.data = b'raise RuntimeError("must never execute")\n'
        (self.repo / 'source.py').write_bytes(self.data)
        self.row = {'repo_path': 'source.py', 'target': 'wrapper/source.py', 'bytes': len(self.data), 'sha256': hashlib.sha256(self.data).hexdigest()}
        self.manifest = {'schema': 'source-only-byte-assembly-v1', 'files': [self.row]}

    def test_copy_exact_bytes_without_execution(self):
        result = assembler.assemble(self.repo, self.out, self.manifest)
        self.assertEqual((self.out / self.row['target']).read_bytes(), self.data)
        self.assertEqual(result, {'files': 1, 'bytes': len(self.data), 'target_executed': False})

    def test_modified_source_rejected_before_output(self):
        (self.repo / 'source.py').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            assembler.assemble(self.repo, self.out, self.manifest)
        self.assertFalse(self.out.exists())

    def test_duplicate_target_rejected_before_output(self):
        self.manifest['files'].append(copy.deepcopy(self.row))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            assembler.assemble(self.repo, self.out, self.manifest)
        self.assertFalse(self.out.exists())

    def test_parent_target_rejected(self):
        self.row['target'] = '../escape.py'
        with self.assertRaisesRegex(ValueError, 'unsafe'):
            assembler.assemble(self.repo, self.out, self.manifest)
        self.assertFalse(self.out.exists())

    def test_parent_source_rejected(self):
        self.row['repo_path'] = '../source.py'
        with self.assertRaisesRegex(ValueError, 'unsafe'):
            assembler.assemble(self.repo, self.out, self.manifest)
        self.assertFalse(self.out.exists())

    def test_existing_output_preserved(self):
        self.out.mkdir()
        marker = self.out / 'preserve'
        marker.write_bytes(b'unique')
        with self.assertRaisesRegex(ValueError, 'fresh'):
            assembler.assemble(self.repo, self.out, self.manifest)
        self.assertEqual(marker.read_bytes(), b'unique')

    def test_source_symlink_rejected(self):
        (self.repo / 'link.py').symlink_to(self.repo / 'source.py')
        self.row['repo_path'] = 'link.py'
        with self.assertRaisesRegex(ValueError, 'symlink'):
            assembler.assemble(self.repo, self.out, self.manifest)
        self.assertFalse(self.out.exists())

    def test_symlink_directory_rejected(self):
        (self.repo / 'linked').symlink_to(self.repo, target_is_directory=True)
        self.row['repo_path'] = 'linked/source.py'
        with self.assertRaisesRegex(ValueError, 'symlink'):
            assembler.assemble(self.repo, self.out, self.manifest)
        self.assertFalse(self.out.exists())

    def test_missing_source_rejected_before_output(self):
        self.row['repo_path'] = 'missing.py'
        with self.assertRaisesRegex(ValueError, 'missing'):
            assembler.assemble(self.repo, self.out, self.manifest)
        self.assertFalse(self.out.exists())

    def test_invalid_manifest_rejected(self):
        with self.assertRaisesRegex(ValueError, 'invalid'):
            assembler.assemble(self.repo, self.out, {'schema': 'other', 'files': []})
        self.assertFalse(self.out.exists())

if __name__ == '__main__':
    unittest.main()
