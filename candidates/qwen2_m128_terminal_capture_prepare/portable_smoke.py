"""Six NEW public-package smoke cases. Not the original 58-case private suite.

Only stdlib, source parsing/hash, and synthetic oracle control. Never imports
RoPE, any target package, NumPy/Torch/Transformers, or a native library.
"""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
POST = HERE / 'postimage/candidates/qwen2_ordered_fullgraph_entry'


def load_local(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


composer = load_local('public_source_composer', HERE / 'compose_source_only.py')
gate = load_local('public_oracle_gate', POST / 'oracle_path_gate.py')
runner = load_local('public_defaultoff_runner', POST / 'runner.py')


class PublicPackageSmoke(unittest.TestCase):
    def test_eight_runtime_source_identities_and_parse(self):
        pins = json.loads((HERE / 'COMPOSITION_PINS.json').read_text())
        self.assertEqual(len(pins['files']), 8)
        for rel, pin in pins['files'].items():
            raw = (HERE / 'postimage' / rel).read_bytes()
            self.assertEqual(composer.identity(raw), pin['postimage'])
            ast.parse(raw)
        self.assertFalse(set(sys.modules) & {'torch', 'numpy', 'transformers'})

    def test_public_patch_and_synthetic_hunk_roundtrip(self):
        pins = json.loads((HERE / 'COMPOSITION_PINS.json').read_text())
        raw = (HERE / 'SOURCE_ONLY.patch').read_bytes()
        self.assertEqual(composer.identity(raw), pins['patch'])
        self.assertEqual(set(composer.sections(raw)), set(pins['files']))
        hunk = ['@@ -1,2 +1,2 @@\n', ' a\n', '-b\n', '+c\n']
        self.assertEqual(composer.apply_hunks(b'a\nb\n', hunk), b'a\nc\n')
        with self.assertRaises(ValueError):
            composer.apply_hunks(b'CHANGED\nb\n', hunk)

    def test_composer_rejects_missing_exact_base(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises((ValueError, FileNotFoundError)):
                composer.build(Path(directory))

    def test_caught_oracle_and_relative_denials_remain_sticky(self):
        for relative in (False, True):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); payload = root / 'synthetic.txt'
                payload.write_bytes(b'NOT-TENSOR-NOT-ORACLE')
                guard = gate.ExactOraclePathGate([root], [payload])
                with patch.object(gate.sys, 'addaudithook'):
                    guard.install({}, '')
                target = 'synthetic.txt' if relative else str(payload)
                try:
                    guard.audit('open', (target, 'r', 0))
                except gate.OracleAccessDenied:
                    pass
                calls = []
                with self.assertRaises(gate.OracleAccessDenied):
                    guard.compare_after_live_terminal(lambda: None, lambda: calls.append(True))
                self.assertEqual(calls, [])
                self.assertEqual(len(guard.denied), 1)

    def test_defaultoff_refuses_before_any_target_import(self):
        with self.assertRaises(ValueError):
            runner.run_actual(None, {}, {}, Path('unused-synthetic-output'))
        self.assertFalse(any(k.startswith('candidates.') for k in sys.modules))

    def test_rope_is_explicitly_unbound_not_runtime_importable(self):
        template = json.loads((HERE / 'ROPE_SOURCE_PINS_UNBOUND.json').read_text())
        self.assertEqual(template['status'], 'UNBOUND_TEMPLATE_NOT_RUNTIME_CONFIG')
        self.assertFalse(template['runtime_allowed'])
        self.assertFalse((POST / 'rope_operand_capture/SOURCE_PINS.json').exists())
        self.assertTrue(all('path' not in row for row in template['sources'].values()))


if __name__ == '__main__':
    unittest.main(verbosity=2)
