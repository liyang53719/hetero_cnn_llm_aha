"""Cold CI wiring regressions. Mock builds are not native qualification."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

from . import build_ci_fixtures as fixtures
from . import run_tests


class CiFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='gdn-ci-fixture-control-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.out = self.root / 'vector'
        self.github_env = self.root / 'github.env'
        self.github_env.write_text('EXISTING=value\n')
        self.legacy = self.out / 'gdn_vector16.so'
        self.r2 = self.out / 'gdn_vector16_finite_mul_tininess_r2.so'

    def invoke(self):
        output = io.StringIO()
        with patch.dict(os.environ, {'GITHUB_ENV': str(self.github_env)}), contextlib.redirect_stdout(output):
            fixtures.main(['--out', str(self.out)])
        return json.loads(output.getvalue())

    def test_two_builds_then_two_verifications_export_three_exact_paths(self):
        events = []

        def build(directory, *, arithmetic_backend):
            self.assertEqual(directory, self.out)
            events.append(('build', arithmetic_backend))
            return self.legacy if arithmetic_backend == fixtures.LEGACY_BACKEND else self.r2

        def verify(library, *, arithmetic_backend):
            events.append(('verify', arithmetic_backend))
            self.assertEqual(library, self.legacy if arithmetic_backend == fixtures.LEGACY_BACKEND else self.r2)
            self.assertEqual(self.github_env.read_text(), 'EXISTING=value\n')

        with patch.object(fixtures, 'build_library', side_effect=build), \
                patch.object(fixtures, 'verify_library', side_effect=verify):
            values = self.invoke()
        self.assertEqual(events, [(action, backend) for action in ('build', 'verify')
                                 for backend in (fixtures.LEGACY_BACKEND, fixtures.FINITE_MUL_UF_BACKEND)])
        self.assertEqual(values, {
            'GDN_VECTOR16_LIBRARY': str(self.legacy),
            'GDN_VECTOR16_FINITE_MUL_UF_LIBRARY': str(self.r2),
            'GDN_VECTOR16_R2_LIBRARY': str(self.r2),
        })
        self.assertEqual(self.github_env.read_text().splitlines(), ['EXISTING=value'] +
                         [f'{name}={values[name]}' for name, _ in fixtures.VECTOR_ENVIRONMENT])

    def test_each_failed_compilation_preserves_environment_without_verification(self):
        for index in range(2):
            with self.subTest(index=index):
                self.out = self.root / f'build-failure-{index}'
                outcomes = [self.legacy, self.r2]
                outcomes[index] = RuntimeError('compiler failed')
                with patch.object(fixtures, 'build_library', side_effect=outcomes), \
                        patch.object(fixtures, 'verify_library') as verify:
                    with self.assertRaisesRegex(RuntimeError, 'compiler failed'):
                        self.invoke()
                    verify.assert_not_called()
                self.assertEqual(self.github_env.read_text(), 'EXISTING=value\n')

    def test_each_rejected_receipt_preserves_environment(self):
        for index in range(2):
            with self.subTest(index=index):
                self.out = self.root / f'receipt-failure-{index}'
                outcomes = [None, None]
                outcomes[index] = ValueError('strict receipt rejected')
                with patch.object(fixtures, 'build_library', side_effect=[self.legacy, self.r2]) as build, \
                        patch.object(fixtures, 'verify_library', side_effect=outcomes):
                    with self.assertRaisesRegex(ValueError, 'strict receipt rejected'):
                        self.invoke()
                    self.assertEqual(build.call_count, 2)
                self.assertEqual(self.github_env.read_text(), 'EXISTING=value\n')

    def test_existing_output_is_rejected_without_overwrite_or_compile(self):
        self.out.mkdir()
        self.legacy.write_bytes(b'PRESERVE_EXISTING_FIXTURE')
        with patch.object(fixtures, 'build_library') as build:
            with self.assertRaises(FileExistsError):
                self.invoke()
            build.assert_not_called()
        self.assertEqual(self.legacy.read_bytes(), b'PRESERVE_EXISTING_FIXTURE')
        self.assertEqual(self.github_env.read_text(), 'EXISTING=value\n')

    def test_multiline_path_rejected_before_compile_or_environment_export(self):
        for suffix in ('\nINJECT=value', '\rINJECT=value'):
            self.out = self.root / ('vector' + suffix)
            with patch.object(fixtures, 'build_library') as build:
                with self.assertRaisesRegex(ValueError, 'single-line fixture directory'):
                    self.invoke()
                build.assert_not_called()
            self.assertFalse(self.out.exists())
            self.assertEqual(self.github_env.read_text(), 'EXISTING=value\n')

    def test_standalone_cli_reports_same_paths_without_github_environment(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(fixtures, 'build_library', side_effect=[self.legacy, self.r2]), \
                patch.object(fixtures, 'verify_library'), contextlib.redirect_stdout(io.StringIO()) as output:
            fixtures.main(['--out', str(self.out)])
        self.assertEqual(json.loads(output.getvalue())['GDN_VECTOR16_R2_LIBRARY'], str(self.r2))
        self.assertEqual(self.github_env.read_text(), 'EXISTING=value\n')

    def test_workflow_builds_before_aggregate_and_retains_both_receipts(self):
        workflow = yaml.load((run_tests.ROOT / run_tests.CI_FIXTURE_INPUTS[0]).read_text(), Loader=yaml.BaseLoader)
        steps = workflow['jobs']['synthetic-model']['steps']
        build = 'python -m candidates.qwen35_gdn_prefill.build_ci_fixtures --out work/qwen35_gdn_model/vector'
        aggregate = 'python -m candidates.qwen35_gdn_prefill.run_tests --out work/qwen35_gdn_model/tests'
        commands = [step.get('run') for step in steps]
        self.assertEqual(commands.count(build), 1)
        self.assertEqual(commands.count(aggregate), 1)
        self.assertLess(commands.index(build), commands.index(aggregate))
        for command in (build, aggregate):
            self.assertNotIn('continue-on-error', steps[commands.index(command)])
        artifacts = next(step for step in steps if step.get('uses', '').startswith('actions/upload-artifact@'))
        self.assertEqual(artifacts['if'], 'always()')
        self.assertIn('work/qwen35_gdn_model/vector/*.json', artifacts['with']['path'].splitlines())
        for path in run_tests.CI_FIXTURE_INPUTS:
            self.assertIn(path, workflow['on']['push']['paths'])

    def test_source_evidence_and_discovery_include_required_native_inputs_and_suites(self):
        self.assertEqual(run_tests.CI_FIXTURE_INPUTS, (
            '.github/workflows/qwen35-gdn-prefill-model.yml',
            'candidates/qwen35_uf_predicate_r2/vector16_tininess.cpp',
            'candidates/qwen35_uf_predicate_r2/STIMULI.json',
        ))
        files = set(run_tests.source_files())
        for name in run_tests.CI_FIXTURE_INPUTS:
            self.assertIn(run_tests.ROOT / name, files)
        tests = {path for directory in run_tests.SOURCE_DIRS for path in directory.glob('test_*.py')}
        for name in ('candidates/qwen35_35b_exp/test_range_contract.py',
                     'candidates/qwen35_gdn_prefill/chunk/test_backend_native.py',
                     'candidates/qwen35_gdn_prefill/test_ci_fixtures.py'):
            self.assertIn(run_tests.ROOT / name, tests)

    def test_postterminal_helpers_are_pinned_separately_and_suites_are_discovered(self):
        self.assertEqual(run_tests.POSTTERMINAL_SOURCE_INPUTS, (
            'scripts/idma_source_export_20261017/strict_cleanup.py',
            'scripts/idma_source_export_20261017/bounded_run.py',
        ))
        self.assertTrue(set(run_tests.CI_FIXTURE_INPUTS).isdisjoint(run_tests.POSTTERMINAL_SOURCE_INPUTS))
        files = set(run_tests.source_files())
        for name in run_tests.POSTTERMINAL_SOURCE_INPUTS:
            self.assertIn(run_tests.ROOT / name, files)
        tests = {path for directory in run_tests.SOURCE_DIRS for path in directory.glob('test_*.py')}
        for name in ('test_terminal_gate.py', 'test_cold_postterminal.py', 'test_launch_cold.py'):
            self.assertIn(run_tests.ROOT / 'candidates/qwen35_gdn_prefill/postterminal' / name, tests)


if __name__ == '__main__':
    unittest.main()
