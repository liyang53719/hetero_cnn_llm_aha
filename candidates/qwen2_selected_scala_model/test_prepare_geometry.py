"""Bounded source-only composition and issued-work accounting, no model import."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(add_help=False)
parser.add_argument('--source-root', required=True)
args, unittest_args = parser.parse_known_args()
SOURCE = Path(args.source_root).absolute()
sys.argv = [sys.argv[0], *unittest_args]


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prepare, geometry = load('prepare'), load('geometry')


class CompositionTests(unittest.TestCase):
    def test_exact_owner_overlay(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'fresh'
            report = prepare.compose(SOURCE, target)
            self.assertEqual(len(report['composed_files']), 6)
            self.assertEqual(report['composed_files'][prepare.TARGETS[0]], prepare.SELECTED_POST)
            self.assertEqual(report['composed_files'][prepare.TARGETS[1]], prepare.BASE_POST[1])
            self.assertFalse(report['full_numeric_admission'])
            self.assertFalse(report['scala_or_rtl_execution'])
            self.assertFalse(report['inherited_historical_pass'])
            self.assertTrue(all('offset' not in log for log in report['patch_logs']))
            with self.assertRaisesRegex(ValueError, 'fresh'):
                prepare.compose(SOURCE, target)

    def test_modified_raw_source_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root, target = Path(temp) / 'raw', Path(temp) / 'output'
            pins = json.loads((HERE / 'INPUT_PINS.json').read_text())
            for name in pins['sources']:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(SOURCE / name, path)
            with (root / prepare.TARGETS[0]).open('a') as handle:
                handle.write('\n# changed\n')
            with self.assertRaisesRegex(ValueError, 'fixed source pin mismatch'):
                prepare.compose(root, target)
            self.assertFalse(target.exists())

    def test_offset_and_reapply_reject(self):
        pins, sources = prepare.verified_sources(SOURCE)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in prepare.TARGETS:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b'\n' + sources[name])
            with self.assertRaisesRegex(ValueError, 'exact patch composition failed'):
                prepare.patch(root, sources[prepare.BASE + 'attention_packed_owner/owner.patch'])

    def test_symlink_input_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            link = Path(temp) / 'raw'
            link.symlink_to(SOURCE, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'non-symlink'):
                prepare.verified_sources(link)


class GeometryTests(unittest.TestCase):
    def test_m2_matches_real_owner_control_test(self):
        plan = geometry.plan(2)
        self.assertEqual(plan['qk']['steps'], 192)
        self.assertEqual(plan['pv']['steps'], 288)
        self.assertEqual(plan['qk']['groups'] + plan['pv']['groups'], 216)
        self.assertEqual(plan['attention_useful_macs'], 9216)
        self.assertEqual(plan['memory_beats'], dict(q_reads=192, k_reads=288,
                                                  v_reads=288, output_write_acks=192))

    def test_true_m128_source_work_not_execution(self):
        plan = geometry.plan(128)
        self.assertEqual(plan['prefill_jobs'], 1)
        self.assertEqual(plan['installed_mac_lanes'], 4096)
        self.assertEqual(plan['qk']['steps'], 55296)
        self.assertEqual(plan['qk']['groups'], 6912)
        self.assertEqual(plan['pv']['steps'], 792576)
        self.assertEqual(plan['pv']['groups'], 12288)
        self.assertEqual(plan['attention_useful_macs'], 25362432)
        self.assertEqual(plan['attention_issued_active_capacity_macs'], 632291328)
        self.assertEqual(plan['whole_block_useful_macs'], 6014828544)
        self.assertIsNone(plan['hardware_cycles'])
        self.assertIsNone(plan['hardware_utilization'])

    def test_all_valid_lengths_conserve_work(self):
        for m in range(1, 129):
            plan = geometry.plan(m)
            self.assertEqual(plan['qk']['useful_macs'], plan['pv']['useful_macs'])
            self.assertLess(plan['qk']['useful_macs'], plan['qk']['issued_active_capacity_macs'])
            self.assertEqual(plan['pv']['issued_active_capacity_macs'], 32 * plan['pv']['useful_macs'])
            self.assertEqual(plan['qk']['issue_m'] * plan['qk']['issue_n'], 4096)
            self.assertEqual(plan['pv']['issue_m'] * plan['pv']['issue_n'], 512)
            self.assertEqual(plan['installed_mac_lanes'], 4096)

    def test_noncanonical_lengths_reject(self):
        for m in (True, False, 0, -1, 129, 1.0, '128', None):
            with self.assertRaises(ValueError):
                geometry.plan(m)


if __name__ == '__main__':
    unittest.main()
