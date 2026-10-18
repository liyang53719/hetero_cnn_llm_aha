"""Small stdlib-only source identity checks; no producer, numerical library, or network."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--repo', required=True, type=Path)
args, remaining = parser.parse_known_args()
ROOT = args.repo.resolve(strict=True)
PACKAGE_HASHES = json.loads((HERE / 'PROJECT_SOURCE_HASHES.json').read_text())
raw = (HERE / 'verify_identity.py').read_bytes()
expected = PACKAGE_HASHES['files']['verify_identity.py']
if {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()} != expected:
    raise ValueError('verifier source differs before execution')
check = types.ModuleType('checked_identity_source')
check.__file__ = str(HERE / 'verify_identity.py')
exec(compile(raw, 'verify_identity.py', 'exec', dont_inherit=True), check.__dict__)
IDENTITY = check.load_identity()
SOURCES = check.load_sources(ROOT, IDENTITY)


def tiny_repository(root):
    for name, data in SOURCES.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


class IdentityCold(unittest.TestCase):
    def test_01_package_bytes(self):
        for name, expected in PACKAGE_HASHES['files'].items():
            raw = (HERE / name).read_bytes()
            self.assertEqual(dict(bytes=len(raw), sha256=check.sha(raw)), expected, name)

    def test_02_real_selected_source_identity(self):
        result = check.verify(ROOT)
        self.assertEqual(result['status'], 'PASS_SOURCE_INPUT_IDENTITIES_ONLY')
        self.assertEqual(result['source_files_checked'], 7)
        self.assertEqual(result['provider_identities'], 14)
        self.assertEqual(result['provider_payload_bytes'], 94916608)
        self.assertEqual(result['payload_with_tables_bytes'], 94920448)
        self.assertEqual(result['payload_bytes_read'], 0)
        self.assertFalse(any(n.split('.')[0] in ('numpy', 'torch', 'heteronpu')
                             for n in sys.modules))

    def test_03_bad_source_bytes_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tiny_repository(root)
            path = root / check.SOURCE_PATHS[2]
            raw = path.read_bytes()
            path.write_bytes(b'!' + raw[1:])
            with self.assertRaisesRegex(ValueError, 'source SHA256 differs'):
                check.verify(root)

    def test_04_wrong_provider_name_rejected(self):
        changed = copy.deepcopy(IDENTITY)
        changed['projection']['providers'][0]['name'] = 'not_a_provider'
        with self.assertRaisesRegex(ValueError, 'projection differs'):
            check.verify_projection(changed, SOURCES)

    def test_05_wrong_provider_size_rejected(self):
        for value in (1025, True, 1024.0):
            changed = copy.deepcopy(IDENTITY)
            changed['projection']['providers'][0]['bytes'] = value
            with self.subTest(size=value), self.assertRaisesRegex(ValueError, 'projection differs'):
                check.verify_projection(changed, SOURCES)

    def test_06_missing_duplicate_extra_provider_rejected(self):
        for mutation in ('missing', 'duplicate', 'extra'):
            changed = copy.deepcopy(IDENTITY)
            providers = changed['projection']['providers']
            if mutation == 'missing':
                providers.pop()
            elif mutation == 'duplicate':
                providers[-1] = copy.deepcopy(providers[0])
            else:
                providers.append(copy.deepcopy(providers[0]))
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, 'projection differs'):
                check.verify_projection(changed, SOURCES)

    def test_07_source_receipt_and_metadata_provider_disagreement(self):
        for key, value in (('bytes', 1025), ('name', 'not_a_provider')):
            changed = dict(SOURCES)
            layout = check.parse_json(changed[check.SOURCE_PATHS[6]])
            allocation = next(a for a in layout['allocations'] if a['name'] == 'bk')
            allocation[key] = value
            changed[check.SOURCE_PATHS[6]] = check.json_bytes(layout)
            with self.subTest(field=key), self.assertRaisesRegex(ValueError, 'provider (size|inventory) differs'):
                check.derive_projection(changed)

    def test_08_same_checked_buffers_are_parsed_without_reopening(self):
        original = check.read_exact
        def refuse_read(*args, **kwargs):
            raise AssertionError('projection reopened a source file')
        check.read_exact = refuse_read
        try:
            self.assertEqual(check.verify_projection(IDENTITY, SOURCES), IDENTITY['projection'])
        finally:
            check.read_exact = original

    def test_09_tampered_identity_rejected_before_parsing(self):
        raw = (HERE / 'INPUT_IDENTITY.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'frozen identity bytes differ'):
            check.identity_from_bytes(raw[:-1] + b' ')

    def test_10_duplicate_json_key_and_unsafe_path_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            check.parse_json(b'{"bytes":1,"bytes":2}')
        for name in ('../escape', '/absolute', 'a//b', 'a/./b', 'a\\b'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'unsafe relative'):
                check.relative(name)

    def test_11_source_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'repository'
            tiny_repository(root)
            path = root / check.SOURCE_PATHS[0]
            target = Path(directory) / 'outside.json'
            target.write_bytes(path.read_bytes())
            path.unlink()
            path.symlink_to(target)
            with self.assertRaisesRegex(ValueError, 'escapes repository or is a symlink'):
                check.verify(root)


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0], *remaining])
