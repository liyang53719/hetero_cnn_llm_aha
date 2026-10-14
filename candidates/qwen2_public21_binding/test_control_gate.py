#!/usr/bin/env python3
"""Cold runner contracts and fresh metadata only; never compile or simulate."""
from pathlib import Path
import importlib.util
import json
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import compose as c
import run_control as runner


class ControlRunnerCold(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest, _, _, _ = c.load_inputs()
        cls.temp = tempfile.TemporaryDirectory(prefix='public21-runner-cold-', dir=ROOT / 'work')
        cls.work = Path(cls.temp.name)
        cls.fixture = cls.work / 'fixture'
        cls.expected = dict(cls.manifest['fixture_dependency_sha256'])
        for group in cls.manifest['additional_repo_inputs']:
            cls.expected.update({name: digest for name, digest in group['sha256'].items()
                                 if name.endswith(('/generate_contract.py', '/source_pins.json'))})
        subprocess.run([sys.executable, str(ROOT / 'candidates/qwen2_resident_matrix/public_dispatch/generate_contract.py'),
                        '--out', str(cls.fixture)], cwd=ROOT, check=True, stdout=subprocess.DEVNULL,
                       env=dict(__import__('os').environ, PYTHONDONTWRITEBYTECODE='1'))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_default_not_executed_without_toolchain_or_outputs(self):
        out = self.work / 'never-created'
        result = subprocess.run([sys.executable, str(HERE / 'run_control.py'), '--out', str(out)],
                                capture_output=True, text=True, check=True)
        summary = json.loads(result.stdout)
        self.assertEqual(summary['status'], 'NOT_EXECUTED')
        self.assertFalse(summary['rtl_executed'])
        self.assertFalse(out.exists())

    def test_opt_in_requires_explicit_toolchain_and_hardfloat(self):
        result = subprocess.run([sys.executable, str(HERE / 'run_control.py'), '--run-rtl'],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('requires explicit', result.stderr)

    def test_fresh_generator_metadata_matches_fixed_inputs(self):
        records = runner.fixture_inputs(ROOT, self.fixture, self.expected)
        self.assertEqual(len(records), 10)
        self.assertEqual(len([p for p in records if p.endswith('.bin')]), 6)

    def test_tampered_metadata_and_unexpected_payload_rejected(self):
        for index, name in enumerate(('m16/command.bin', 'm128/manifest.json')):
            target = self.work / ('tampered-' + str(index)); shutil.copytree(self.fixture, target)
            path = target / name; path.write_bytes(path.read_bytes() + b'\n')
            with self.assertRaisesRegex(ValueError, 'identity drift'):
                runner.fixture_inputs(ROOT, target, self.expected)
        target = self.work / 'extra-payload'; shutil.copytree(self.fixture, target)
        (target / 'unexpected.bin').write_bytes(b'not allowed')
        with self.assertRaisesRegex(ValueError, 'unexpected fixture payload'):
            runner.fixture_inputs(ROOT, target, self.expected)

    def test_fixture_source_pin_drift_rejected(self):
        altered = dict(self.expected); altered[next(iter(altered))] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'unpinned or changed sources'):
            runner.fixture_inputs(ROOT, self.fixture, altered)

    def marker_text(self):
        lines = ['PUBLIC21_CURRENT_PARSER_CONTROL_PASS arithmetic=false'] * 4
        lines += ['PUBLIC21_CURRENT_PARSER_REJECTION_PASS arithmetic=false']
        lines += ['PUBLIC21_REDUCTION_DISPATCH_CONTROL_PASS arithmetic=false'] * 3
        lines += ['PUBLIC21_REDUCTION_DISPATCH_REJECT_PASS fault=' + fault + ' arithmetic=false'
                  for fault in sorted(runner.FAULTS)]
        return '\n'.join(lines)

    def test_exact_22_markers_and_all_14_faults_required(self):
        text = self.marker_text()
        self.assertTrue(runner.checked_markers(text)[0])
        self.assertEqual(len(runner.checked_markers(text)[1]), 22)
        for changed in (text + '\n' + text.splitlines()[0], '\n'.join(text.splitlines()[:-1]),
                        text.replace('fault=window_tag', 'fault=held_reset'), text.replace('arithmetic=false', 'arithmetic=true', 1)):
            self.assertFalse(runner.checked_markers(changed)[0])

    def test_watchdog_terminates_process_group_then_kills_after_grace(self):
        process = mock.Mock(pid=12345)
        process.wait.side_effect = [subprocess.TimeoutExpired('mock', 600), subprocess.TimeoutExpired('mock', 15), 0]
        with mock.patch.object(runner.subprocess, 'Popen', return_value=process) as popen, \
             mock.patch.object(runner.os, 'killpg') as killpg:
            code = runner.run_group(['not-executed'], self.work, {}, self.work / 'watchdog.log')
        self.assertEqual(code, 124)
        self.assertTrue(popen.call_args.kwargs['start_new_session'])
        self.assertEqual(killpg.call_args_list, [mock.call(12345, signal.SIGTERM), mock.call(12345, 0), mock.call(12345, signal.SIGKILL)])
        self.assertEqual(process.wait.call_args_list[:2], [mock.call(timeout=600), mock.call(timeout=15)])


    def test_watchdog_kills_surviving_group_after_leader_exits_on_term(self):
        process = mock.Mock(pid=23456)
        process.wait.side_effect = [subprocess.TimeoutExpired('mock', 600), 0, 0]
        with mock.patch.object(runner.subprocess, 'Popen', return_value=process), \
             mock.patch.object(runner.os, 'killpg') as killpg:
            code = runner.run_group(['not-executed'], self.work, {}, self.work / 'surviving-group.log')
        self.assertEqual(code, 124)
        self.assertEqual(killpg.call_args_list,
                         [mock.call(23456, signal.SIGTERM), mock.call(23456, 0), mock.call(23456, signal.SIGKILL)])
        self.assertEqual(process.wait.call_args_list, [mock.call(timeout=600), mock.call(timeout=15), mock.call()])

    def test_watchdog_does_not_kill_a_group_that_already_drained(self):
        process = mock.Mock(pid=34567)
        process.wait.side_effect = [subprocess.TimeoutExpired('mock', 600), 0, 0]
        with mock.patch.object(runner.subprocess, 'Popen', return_value=process), \
             mock.patch.object(runner.os, 'killpg', side_effect=[None, ProcessLookupError]) as killpg:
            code = runner.run_group(['not-executed'], self.work, {}, self.work / 'drained-group.log')
        self.assertEqual(code, 124)
        self.assertEqual(killpg.call_args_list, [mock.call(34567, signal.SIGTERM), mock.call(34567, 0)])

    def test_failed_or_inconclusive_build_never_claims_rtl_execution(self):
        for text in ('', '[error] compilation failed', 'Generated Public21DispatchHarness.sv',
                     'PUBLIC21_SOURCE_LIST_PASS compile=91 tests=2', 'PUBLIC21_UNKNOWN_PASS arithmetic=false'):
            with self.subTest(text=text):
                flags = runner.execution_flags(text)
                self.assertFalse(flags['rtl_executed'])
                self.assertFalse(flags['rtl_simulated'])
                self.assertFalse(flags['control_acceptance_passed'])
                self.assertEqual(flags['rtl_execution_evidence'], 'NOT_ESTABLISHED')
        with self.assertRaisesRegex(ValueError, 'without testbench execution evidence'):
            runner.execution_flags('[error] compilation failed', accepted=True)

    def test_partial_rtl_evidence_is_separate_from_aggregate_acceptance(self):
        text = 'PUBLIC21_CURRENT_PARSER_CONTROL_PASS arithmetic=false\n[error] later test failed'
        flags = runner.execution_flags(text)
        self.assertTrue(flags['rtl_executed'])
        self.assertTrue(flags['rtl_simulated'])
        self.assertFalse(flags['control_acceptance_passed'])
        self.assertEqual(flags['rtl_execution_evidence'], 'TESTBENCH_PASS_MARKER')
        accepted = runner.execution_flags(self.marker_text(), accepted=True)
        self.assertTrue(accepted['rtl_executed'])
        self.assertTrue(accepted['control_acceptance_passed'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
