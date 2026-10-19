"""Bounded data-only tests for the actual cold loader; no fixture cleanup."""
import hashlib
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent
ENTRY = (2375, 'ef0e1e1a7e3dba494d57775cd291110b1b36b5e6dac39bd230bf334a97ff0383')
raw = (ROOT / 'source_entry.py').read_bytes()
if (len(raw), hashlib.sha256(raw).hexdigest()) != ENTRY:
    raise ValueError('ENTRY_TEST_SOURCE_PIN')
scope = {'__name__': 'pc01_entry_tested', '__file__': str(ROOT / 'source_entry.py')}
exec(compile(raw, str(ROOT / 'source_entry.py'), 'exec'), scope)
checked = scope['checked']
if len(sys.argv) != 2:
    raise SystemExit('one fresh private fixture directory required')
FIXTURES = Path(sys.argv[1]).absolute()
FIXTURES.mkdir(parents=False, exist_ok=False)


class EntryChecks(unittest.TestCase):
    def make(self, leaf, payload=b'alpha'):
        p = FIXTURES / leaf
        p.write_bytes(payload)
        return p, (len(payload), hashlib.sha256(payload).hexdigest())

    def test_exact_buffer_returned(self):
        p, pin = self.make('exact')
        self.assertEqual(checked(p, pin), b'alpha')

    def test_same_length_drift(self):
        p, pin = self.make('changed')
        p.write_bytes(b'bravo')
        with self.assertRaisesRegex(ValueError, 'COLD_HASH'):
            checked(p, pin)

    def test_short_rejected(self):
        p, pin = self.make('short')
        p.write_bytes(b'a')
        with self.assertRaisesRegex(ValueError, 'COLD_SIZE'):
            checked(p, pin)

    def test_long_rejected(self):
        p, pin = self.make('long')
        p.write_bytes(b'alpha!')
        with self.assertRaisesRegex(ValueError, 'COLD_SIZE'):
            checked(p, pin)

    def test_file_symlink_rejected(self):
        p, pin = self.make('symlink_target')
        link = FIXTURES / 'link'
        link.symlink_to(p)
        with self.assertRaisesRegex(ValueError, 'COLD_SYMLINK'):
            checked(link, pin)

    def test_parent_symlink_rejected(self):
        p, pin = self.make('parent_target')
        link = FIXTURES / 'parent_link'
        link.symlink_to(FIXTURES, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'COLD_SYMLINK'):
            checked(link / p.name, pin)

    def test_relative_rejected(self):
        with self.assertRaisesRegex(ValueError, 'COLD_PATH'):
            checked(Path('not_absolute'), (1, 'a' * 64))

    def test_parent_component_rejected(self):
        with self.assertRaisesRegex(ValueError, 'COLD_PATH'):
            checked(FIXTURES / '..' / 'bad', (1, 'a' * 64))

    def test_pinned_original_manifest(self):
        value = checked(ROOT / 'PRODUCTION_MANIFEST.json', scope['MANIFEST_PIN'])
        self.assertEqual(len(value), 4472)


suite = unittest.defaultTestLoader.loadTestsFromTestCase(EntryChecks)
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
