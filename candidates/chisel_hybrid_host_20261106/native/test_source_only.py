"""Read-only source preservation tests. No compiler, model, or native library is used."""
from pathlib import Path
import copy
import json
import unittest
from unittest.mock import patch

D = Path(__file__).resolve().parent
P = D / 'check_source_only.py'
M = {'__file__': str(P), '__name__': 'native_source_contract'}
exec(compile(P.read_bytes(), str(P), 'exec'), M)


class NativeSourceIdentity(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads((D / 'SOURCES.json').read_bytes())

    def reject(self, change):
        value = copy.deepcopy(self.catalog)
        change(value)
        with self.assertRaises(ValueError):
            M['validate'](value)

    def test_exact_preservation_without_process(self):
        with patch('subprocess.run', side_effect=AssertionError('no process')):
            result = M['validate'](self.catalog)
        self.assertFalse(result['native_compiled'])
        self.assertFalse(result['native_executed'])

    def test_changed_source_identity_rejected(self):
        self.reject(lambda c: c['files'][0].update(sha256='0' * 64))

    def test_duplicate_source_rejected(self):
        self.reject(lambda c: c['files'].__setitem__(0, c['files'][1]))

    def test_changed_include_order_rejected(self):
        def change(c):
            row = next(r for r in c['files'] if len(r['quoted_includes']) > 1)
            row['quoted_includes'].reverse()
        self.reject(change)

    def test_hidden_generated_dependency_rejected(self):
        self.reject(lambda c: c['external_headers'].pop('verilated.h'))

    def test_missing_source_rejected(self):
        self.reject(lambda c: c['files'].pop())

    def test_path_escape_rejected(self):
        self.reject(lambda c: c['files'][0].update(path='../escape.cpp'))


if __name__ == '__main__':
    unittest.main()
