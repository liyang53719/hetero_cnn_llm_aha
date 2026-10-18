"""Bounded source/JSON cold checks; no C++ compiler, constructor, or tensor payload."""
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
PACKAGE = json.loads((HERE / 'PROJECT_SOURCE_HASHES.json').read_text())
raw = (HERE / 'verify_binding.py').read_bytes()
if {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()} != PACKAGE['files']['verify_binding.py']:
    raise ValueError('validator source differs before execution')
check = types.ModuleType('verified_binding_source')
check.__file__ = str(HERE / 'verify_binding.py')
exec(compile(raw, 'verify_binding.py', 'exec', dont_inherit=True), check.__dict__)
IDENTITY, LAYOUT = check.load(ROOT)


class ColdBinding(unittest.TestCase):
    def test_01_package_hashes(self):
        for name, expected in PACKAGE['files'].items():
            raw = (HERE / name).read_bytes()
            self.assertEqual(dict(bytes=len(raw), sha256=check.sha(raw)), expected, name)

    def test_02_real_sources_exact16_and_full_arena(self):
        result = check.verify(ROOT)
        self.assertEqual(result['inputs'], 16)
        self.assertEqual(result['reservations'], 35)
        self.assertEqual(result['regions'], 4)
        self.assertEqual(result['ram_bytes'], 213473600)
        self.assertEqual(result['backing_arrays_bytes'], 426947200)
        self.assertFalse(result['factory_called'])
        self.assertFalse(any(n.split('.')[0] in ('numpy', 'torch', 'heteronpu') for n in sys.modules))
        inputs = check.derive(IDENTITY, LAYOUT)['inputs']
        self.assertEqual((inputs[9]['name'], inputs[15]['name']), ('gamma0', 'x'))

    def test_03_metadata_order_not_provider_name_sort(self):
        changed = copy.deepcopy(LAYOUT)
        changed['allocations'][0], changed['allocations'][1] = changed['allocations'][1], changed['allocations'][0]
        with self.assertRaisesRegex(ValueError, 'metadata input order'):
            check.derive(IDENTITY, changed)

    def test_04_wrong_provider_name_or_size(self):
        for key, value in (('name', 'wrong'), ('bytes', 1025), ('bytes', True)):
            changed = copy.deepcopy(IDENTITY)
            changed['projection']['providers'][0][key] = value
            with self.subTest(field=key, value=value), self.assertRaises(ValueError):
                check.derive(changed, LAYOUT)

    def test_05_permission_and_overlap_rejected(self):
        changed = copy.deepcopy(LAYOUT)
        changed['regions'][0]['write'] = True
        with self.assertRaisesRegex(ValueError, 'permission order'):
            check.derive(IDENTITY, changed)
        changed = copy.deepcopy(LAYOUT)
        named = {a['name']: a for a in changed['allocations']}
        named['qraw']['base'] = named['n0']['base']
        with self.assertRaisesRegex(ValueError, 'overlap'):
            check.derive(IDENTITY, changed)

    def test_06_table_and_reservation_boundary_rejected(self):
        changed = copy.deepcopy(LAYOUT)
        changed['tables']['commands']['bytes'] = 336
        with self.assertRaisesRegex(ValueError, 'table identities'):
            check.derive(IDENTITY, changed)
        changed = copy.deepcopy(LAYOUT)
        changed['allocations'][0]['reserved_bytes'] = 1 << 30
        with self.assertRaisesRegex(ValueError, 'outside its fixture region'):
            check.derive(IDENTITY, changed)

    def test_07_bad_repository_source_rejected(self):
        pin = json.loads((HERE / 'SOURCE_PIN.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for entry in pin['repository_source_files']:
                path = root / entry['path']
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((ROOT / entry['path']).read_bytes())
            path = root / check.PATHS[0]
            raw = path.read_bytes()
            path.write_bytes(b'!' + raw[1:])
            with self.assertRaisesRegex(ValueError, 'source bytes/hash differ'):
                check.verify(root)

    def test_08_header_change_rejected(self):
        original = check.HERE
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            for name in ('SOURCE_PIN.json', 'initialization_ram.hpp', 'same_buffer_loader.hpp',
                         'sha256.hpp', 'canonical16_binding.hpp'):
                (target / name).write_bytes((HERE / name).read_bytes())
            path = target / 'canonical16_binding.hpp'
            path.write_bytes(path.read_bytes().replace(b'4482204160ULL', b'4482204224ULL', 1))
            check.HERE = target
            try:
                with self.assertRaisesRegex(ValueError, 'fixed binding source differs'):
                    check.verify(ROOT)
            finally:
                check.HERE = original

    def test_09_pure_projection_never_reopens_sources(self):
        original = check.checked_bytes
        def fail(*args, **kwargs):
            raise AssertionError('source reopened during pure JSON projection')
        check.checked_bytes = fail
        try:
            self.assertEqual(check.render(check.derive(IDENTITY, LAYOUT)),
                             (HERE / 'canonical16_binding.hpp').read_bytes())
        finally:
            check.checked_bytes = original

    def test_10_duplicate_json_and_path_escape(self):
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            check.parse(b'{"bytes":1,"bytes":2}')
        for name in ('../x', '/x', 'a//b', 'a\\b'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'unsafe source path'):
                check.relative(name)


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0], *remaining])
