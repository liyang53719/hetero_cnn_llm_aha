"""Source-only exact composition; no numerical/native/RTL execution."""
import argparse
import ast
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(add_help=False)
parser.add_argument('--source-root', required=True)
args, remaining = parser.parse_known_args()
SOURCE = Path(args.source_root).absolute()
sys.argv = [sys.argv[0], *remaining]
spec = importlib.util.spec_from_file_location('_direct_prepare_tested', HERE / 'prepare.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class PreparationTests(unittest.TestCase):
    def test_exact_nine_file_overlay_and_unchanged_driver_loop(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'overlay'
            report = prepare.compose(SOURCE, output)
            self.assertEqual(len(report['composed_files']), 9)
            self.assertEqual(report['composed_files'][prepare.PUBLIC[0]], prepare.GUARDED_POST)
            self.assertEqual(report['composed_files'][prepare.PUBLIC[1]], prepare.PUBLIC_POST[1])
            prior = json.loads((output / 'SCHEDULE_COMPOSITION.json').read_text())
            for name, sha in prior['composed_files'].items():
                self.assertEqual(report['composed_files'][name], sha)
            self.assertFalse(report['raw_kv_enabled'])
            self.assertFalse(report['additional_payload_or_cache_allocation'])
            self.assertFalse(report['full_numeric_admission'])
            def loop(path):
                tree = ast.parse(path.read_text())
                function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                                and n.name == 'execute_attention_owner')
                return ast.dump(next(n for n in function.body if isinstance(n, ast.While)),
                                include_attributes=False)
            self.assertEqual(loop(SOURCE / prepare.PUBLIC[1]), loop(output / prepare.PUBLIC[1]))
            with self.assertRaisesRegex(ValueError, 'fresh'):
                prepare.compose(SOURCE, output)

    def test_changed_original_public_source_rejects_before_output(self):
        with tempfile.TemporaryDirectory() as temp:
            source, output = Path(temp) / 'source', Path(temp) / 'output'
            pins = json.loads((HERE / 'INPUT_PINS.json').read_text())
            for name in pins['sources']:
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(SOURCE / name, path)
            with (source / prepare.PUBLIC[0]).open('a') as stream:
                stream.write('\n# drift\n')
            with self.assertRaisesRegex(ValueError, 'fixed input source differs'):
                prepare.compose(source, output)
            self.assertFalse(output.exists())

    def test_candidate_source_drift_rejects_before_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ('INPUT_PINS.json', 'CODE_PINS.json', 'direct_transport.py', 'direct_guard.patch'):
                shutil.copyfile(HERE / name, root / name)
            with (root / 'direct_transport.py').open('a') as stream:
                stream.write('\n# changed\n')
            with mock.patch.object(prepare, 'HERE', root):
                with self.assertRaisesRegex(ValueError, 'direct candidate source differs'):
                    prepare.compose(SOURCE, root / 'output')
            self.assertFalse((root / 'output').exists())

    def test_unknown_candidate_file_pin_rejects(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shutil.copyfile(HERE / 'INPUT_PINS.json', root / 'INPUT_PINS.json')
            (root / 'CODE_PINS.json').write_text('{}')
            with mock.patch.object(prepare, 'HERE', root):
                with self.assertRaisesRegex(ValueError, 'exact direct runtime pin set'):
                    prepare.verify(SOURCE)

    def test_input_symlink_rejects(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'source'
            path.symlink_to(SOURCE, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'non-symlink'):
                prepare.verify(path)

    def test_binding_does_not_allocate_payload_resources(self):
        tree = ast.parse((HERE / 'direct_transport.py').read_text())
        forbidden = {'ParentLoan', 'KvSupply', 'PublicKvTransport', 'ScratchMux', 'Banks',
                     'MatrixService', 'bytearray', 'bytes'}
        calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name)}
        self.assertFalse(calls & forbidden)
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'run')
        call = next(n for n in ast.walk(function) if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Name) and n.func.id == 'execute_attention_owner')
        option = next(n.value for n in call.keywords if n.arg == 'enable_raw_kv')
        self.assertIsInstance(option, ast.Constant)
        self.assertIs(option.value, False)


if __name__ == '__main__':
    unittest.main()
