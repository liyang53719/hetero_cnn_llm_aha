"""Synthetic stdlib source-integrity tests only, never model execution."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('public_source_verifier', Path(__file__).with_name('verify_sources.py'))
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


def synthetic_manifest(raw=b'# synthetic source only\n'):
    return {'schema_version': 1, 'source_commit': v.SOURCE_COMMIT, 'source_tree': v.SOURCE_TREE,
            'scope': 'Synthetic test only', 'source_count': 1, 'files': {
                'pkg/example.py': {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                                   'git_blob_sha': hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest(),
                                   'git_mode': '100644'}}}


class SourceVerifierTests(unittest.TestCase):
    def fixture(self, root, raw=b'# synthetic source only\n'):
        path = root / 'pkg/example.py'
        path.parent.mkdir()
        path.write_bytes(raw)
        return synthetic_manifest(raw)

    def test_valid_source_bytes_only_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = v.verify_sources(root, self.fixture(root))
            self.assertEqual(result['selected_files_verified'], 1)
            self.assertFalse(result['model_executed'])
            self.assertFalse(result['git_head_checked'])
            self.assertIsNone(result['numerical_acceptance'])

    def test_published_manifest_digest_and_count(self):
        manifest = v.load_manifest(Path(__file__).with_name('SOURCE_PINS.json'))
        self.assertEqual(manifest['source_count'], 111)
        self.assertEqual(len(manifest['files']), 111)

    def test_manifest_byte_drift_rejects(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'pins.json'
            path.write_bytes(Path(__file__).with_name('SOURCE_PINS.json').read_bytes() + b' ')
            with self.assertRaisesRegex(ValueError, 'manifest changed'):
                v.load_manifest(path)

    def test_duplicate_json_keys_reject(self):
        with self.assertRaisesRegex(ValueError, 'duplicate JSON'):
            json.loads('{"x":1,"x":2}', object_pairs_hook=v.unique_object)

    def test_empty_inventory_rejects(self):
        m = synthetic_manifest()
        m.update(source_count=0, files={})
        with self.assertRaises(ValueError):
            v.validate_manifest(m)

    def test_count_mismatch_and_boolean_reject(self):
        for count in (True, 2, -1, 2049):
            with self.subTest(count=count), self.assertRaises(ValueError):
                m = synthetic_manifest()
                m['source_count'] = count
                v.validate_manifest(m)

    def test_absolute_traversal_alias_and_binary_paths_reject(self):
        for name in ('/absolute.py', '../escape.py', 'pkg/../escape.py', 'pkg//example.py',
                     'pkg/./example.py', 'pkg\\example.py', 'pkg/example.npz', 'pkg/example.bin', 'pkg/example\n.py'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                m = synthetic_manifest()
                m['files'] = {name: next(iter(m['files'].values()))}
                v.validate_manifest(m)

    def test_unknown_fields_reject(self):
        m = synthetic_manifest()
        m['extra'] = True
        with self.assertRaises(ValueError):
            v.validate_manifest(m)
        m = synthetic_manifest()
        m['files']['pkg/example.py']['extra'] = True
        with self.assertRaises(ValueError):
            v.validate_manifest(m)

    def test_provenance_and_schema_reject(self):
        for field, value in (('source_commit', '0' * 40), ('source_tree', '0' * 40), ('schema_version', True)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                m = synthetic_manifest()
                m[field] = value
                v.validate_manifest(m)

    def test_invalid_pin_fields_reject(self):
        for field, value in (('bytes', True), ('bytes', -1), ('bytes', v.MAX_SOURCE_BYTES + 1),
                             ('sha256', '0'), ('git_blob_sha', '0'), ('git_mode', '120000')):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                m = synthetic_manifest()
                m['files']['pkg/example.py'][field] = value
                v.validate_manifest(m)

    def test_missing_source_rejects(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'missing selected source'):
                v.verify_sources(Path(directory), synthetic_manifest())

    def test_source_size_drift_rejects(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            m = self.fixture(root)
            (root / 'pkg/example.py').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'source size changed'):
                v.verify_sources(root, m)

    def test_same_size_hash_drift_rejects(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            m = self.fixture(root)
            path = root / 'pkg/example.py'
            path.write_bytes(b'x' * path.stat().st_size)
            with self.assertRaisesRegex(ValueError, 'source hash changed'):
                v.verify_sources(root, m)

    def test_git_blob_mismatch_rejects(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            m = self.fixture(root)
            m['files']['pkg/example.py']['git_blob_sha'] = '0' * 40
            with self.assertRaisesRegex(ValueError, 'Git blob hash changed'):
                v.verify_sources(root, m)

    def test_file_and_directory_symlinks_reject(self):
        for directory_alias in (False, True):
            with self.subTest(directory_alias=directory_alias), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                m = self.fixture(root)
                if directory_alias:
                    (root / 'pkg').rename(root / 'target')
                    (root / 'pkg').symlink_to(root / 'target', target_is_directory=True)
                else:
                    path = root / 'pkg/example.py'
                    path.rename(root / 'target.py')
                    path.symlink_to(root / 'target.py')
                with self.assertRaisesRegex(ValueError, 'source path alias'):
                    v.verify_sources(root, m)

    def test_root_symlink_rejects(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / 'actual'
            root.mkdir()
            m = self.fixture(root)
            alias = base / 'alias'
            alias.symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'source root'):
                v.verify_sources(alias, m)


if __name__ == '__main__':
    unittest.main()
