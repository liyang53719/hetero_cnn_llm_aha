"""Existing accepted-event tests plus narrow composition/retirement integration."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('handoff_under_test', Path(__file__).with_name('replay_handoff.py'))
handoff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handoff)
ROOT = None
WORK = None
REPORT = None


class Integration(unittest.TestCase):
    def test_cold_standalone_cli_has_no_unittest_import_dependencies(self):
        with tempfile.TemporaryDirectory(prefix='qk_cold_cli_') as directory:
            command = [sys.executable, '-I', '-B']
            if sys.flags.optimize:
                command.append('-O')
            command += [str(Path(__file__).with_name('replay_handoff.py')),
                        '--source-root', str(ROOT), '--output', str(Path(directory) / 'output')]
            result = subprocess.run(command, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 2, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report['status'], 'INCOMPLETE')
            self.assertEqual(report['composition']['installed_files'], 5)
            self.assertEqual(len(report['retirement_cases']), 17)

    def test_composition_is_expected_not_missing_architecture(self):
        self.assertEqual(REPORT['composition']['production_files'], 77)
        self.assertEqual(REPORT['composition']['donor_files'], 13)
        self.assertEqual(REPORT['composition']['installed_files'], 5)
        self.assertEqual(REPORT['binding']['installed_postimage_sha256'],
                         '31b618680b4c750398a0dcf21fa34185dd9fc9b1732e370cfce502915814bd68')
        self.assertEqual(REPORT['binding']['production_preimage_sha256'],
                         '2118e101b61510adb3d57129a07fe6064dd3160aea341e495cd2bd1e6ab7a558')
        self.assertEqual(REPORT['binding']['donor_sha256'],
                         '4375ccf715cf408975c3e45ae595955767b824404ef8337bb260ed807527dc1e')

    def test_all_tail_cases_retire_exactly_once(self):
        cases = REPORT['retirement_cases']
        self.assertEqual(len(cases), 17)
        self.assertEqual([x['keys'] for x in cases[:16]], list(range(1, 17)))
        self.assertEqual((cases[-1]['token'], cases[-1]['base']), (127, 112))
        for case in cases:
            self.assertEqual(case['scores'], case['keys'])
            self.assertEqual((case['result_acks'], case['done_acks'], case['completion_acks']), (1, 1, 1))
            self.assertEqual(case['model_state'], 'complete')
            self.assertLess(case['ticks'], 10000)

    def test_real_planned_repository_source_selection(self):
        self.assertEqual(REPORT['composition']['planned_repository_scala_sources_verified'], 72)
        self.assertEqual(REPORT['composition']['external_hardfloat_source_bodies_not_verified'], 20)
        self.assertFalse(REPORT['composition']['full_92_source_compiler_closure_verified'])

    def test_stall_lengths_do_not_change_retirement(self):
        for stalls, delay in ((0, 0), (1, 1), (7, 9)):
            with self.subTest(stalls=stalls, delay=delay):
                result = handoff.exercise_retirement(ROOT, 15, 0, stalls, delay)
                self.assertEqual(result['result_acks'], 1)
                self.assertEqual(result['scores'], 16)

    def test_software_provenance_is_not_composed_scala_execution(self):
        self.assertTrue(REPORT['binding']['m128_contract_binds_bare_scala_as_provenance'])
        self.assertFalse(REPORT['binding']['m128_operationally_executes_composed_scala'])
        self.assertTrue(REPORT['binding']['sequential_softmax_pv_byte_preserved'])
        self.assertEqual(REPORT['status'], 'INCOMPLETE')
        for name in ('scala_behavior_executed', 'softmax_pv_behavior_executed',
                     'native_arithmetic_imported', 'rtl_generated', 'full_m128_reexecuted',
                     'historical_acceptance_inherited', 'numerical_equivalence',
                     'hardware_cycles_claimed', 'full_block_acceptance'):
            self.assertFalse(REPORT['scope'][name])

    def test_existing_output_rejected(self):
        with self.assertRaisesRegex(ValueError, 'fresh output'):
            handoff.compose(ROOT, WORK)

    def test_missing_source_rejected(self):
        with tempfile.TemporaryDirectory(prefix='qk_missing_') as directory:
            with self.assertRaisesRegex(ValueError, 'source size'):
                handoff.verify(Path(directory))

    def test_changed_source_rejected(self):
        pins = handoff.verify(ROOT)
        name = next(iter(pins['sources']))
        original = Path.read_bytes
        def altered(path):
            raw = original(path)
            return raw[:-1] + b' ' if path == ROOT / name else raw
        with patch.object(Path, 'read_bytes', altered):
            with self.assertRaisesRegex(ValueError, 'source identity'):
                handoff.verify(ROOT)

    def test_cached_wrong_control_model_rejected(self):
        name = 'candidates.qwen2_resident_matrix.attention_qk16_owner_route.model'
        wrong = types.ModuleType(name)
        wrong.__file__ = '/tmp/not_the_selected_qwen2_model.py'
        with patch.dict(sys.modules, {name: wrong}):
            with self.assertRaisesRegex(ValueError, 'cached module origin'):
                handoff.bound_import(name, ROOT)

    def test_unpinned_package_initializer_rejected_before_import(self):
        with tempfile.TemporaryDirectory(prefix='qk_initializer_') as directory:
            root = Path(directory)
            initializer = root / 'candidates/__init__.py'
            initializer.parent.mkdir()
            initializer.write_text('raise RuntimeError("must never execute")\n')
            with self.assertRaisesRegex(ValueError, 'unexpected package initializer'):
                handoff.verify(root)

    def test_cached_wrong_package_rejected(self):
        wrong = types.ModuleType('candidates')
        wrong.__file__ = '/tmp/unpinned_initializer.py'
        wrong.__path__ = ['/tmp/unpinned_candidates']
        with patch.dict(sys.modules, {'candidates': wrong}):
            with self.assertRaisesRegex(ValueError, 'cached package origin'):
                handoff.prepare_packages(ROOT)

    def test_selected_source_bytecode_rejected(self):
        pins = handoff.verify(ROOT)
        name = next(n for n in pins['sources'] if n.endswith('.py'))
        for cached in (False, True):
            with self.subTest(cached=cached), tempfile.TemporaryDirectory(prefix='qk_bytecode_') as directory:
                root = Path(directory)
                source = root / name
                target = (source.parent / '__pycache__' / (source.stem + '.cpython-311.pyc')
                          if cached else source.with_suffix('.pyc'))
                target.parent.mkdir(parents=True)
                target.write_bytes(b'not executable, must reject before import')
                with self.assertRaisesRegex(ValueError, 'unexpected selected-source bytecode'):
                    handoff.verify(root)

    def test_source_guard_mutation_rejected(self):
        with tempfile.TemporaryDirectory(prefix='qk_guard_') as directory:
            out = Path(directory)
            for tree in ('installed', 'production/source', 'donor'):
                target = out / tree / handoff.S / 'Qwen2Block.scala'
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(WORK / tree / handoff.S / 'Qwen2Block.scala', target)
            target = out / 'installed' / handoff.S / 'Qwen2Block.scala'
            source = target.read_text()
            self.assertEqual(source.count('}.elsewhen(!packedBusy){'), 1)
            target.write_text(source.replace('}.elsewhen(!packedBusy){', '}.elsewhen(true.B){'))
            with self.assertRaisesRegex(ValueError, 'production handoff source binding'):
                handoff.source_binding(ROOT, out)

    def test_no_numerical_module_imported(self):
        for name in sys.modules:
            self.assertFalse(name.startswith(('torch', 'numpy', 'candidates.qwen2_resident_matrix.dense_block_reduce.check_public_numeric')))
        self.assertEqual(handoff.verify(ROOT)['source_reference_commit'],
                         'cacc259d8893754b8cae968b5355ccf37e5b79cf')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    handoff.limits()
    ROOT = args.source_root.absolute()
    with tempfile.TemporaryDirectory(prefix='qwen2_bound_handoff_') as directory:
        WORK = Path(directory) / 'composed'
        REPORT = handoff.run(ROOT, WORK)
        # Reuse the existing nine control tests, not their Source class, compiler,
        # numerical entry, or a rewritten control implementation.
        existing = handoff.bound_import('candidates.qwen2_resident_matrix.attention_qk16_owner_route.test_route', ROOT)
        suite = unittest.TestSuite((unittest.defaultTestLoader.loadTestsFromTestCase(existing.Control),
                                    unittest.defaultTestLoader.loadTestsFromTestCase(Integration)))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        sys.exit(0 if result.wasSuccessful() else 1)
