"""Shallow-checkout prerequisites and real failed-child diagnostics; no RTL."""
import ast
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from . import run_tests as runner

FRONTEND_BASELINE_SHA256 = '898e1ced4a9b83641d5fe1944bffdbb3c3e4a71d4d51193cbd17bd7a94ff8aa4'
FULLGRAPH_FETCH = '          git fetch --no-tags --depth=1 origin 37b7de74431ed79b7e9f3d52d308ed7f46727b7a'
FULLGRAPH_PROBE = '          git cat-file -e 37b7de74431ed79b7e9f3d52d308ed7f46727b7a:candidates/qwen2_resident_matrix/ffn_public/fullgraph_numerical_receipt.json'


def validate_frontend_extension(current):
    """Retain the frozen body; admit only c554's exact fullgraph fetch/probe."""
    # Preserve the original comment-only normalization. The two added lines
    # must each occur once, consecutively at the reviewed baseline-fetch site.
    lines = [line for line in current.splitlines() if not line.lstrip().startswith('#')]
    if lines.count(FULLGRAPH_FETCH) != 1 or lines.count(FULLGRAPH_PROBE) != 1:
        raise ValueError('frontend fullgraph fetch/probe identity or count changed')
    fetch, probe = lines.index(FULLGRAPH_FETCH), lines.index(FULLGRAPH_PROBE)
    previous = '          git cat-file -e df18ba25a439fd90c846b22b9aafe992a2a6ae79:candidates/qwen2_resident_matrix/ffn_public/prefix_numerical_receipt.json'
    if not (fetch > 0 and probe == fetch + 1 and probe + 1 < len(lines) and
            lines[fetch - 1] == previous and lines[probe + 1] == '      - uses: actions/setup-java@v4'):
        raise ValueError('frontend fullgraph fetch/probe order changed')
    body = '\n'.join(lines[:fetch] + lines[probe + 1:])
    if hashlib.sha256(body.encode()).hexdigest() != FRONTEND_BASELINE_SHA256:
        raise ValueError('frozen frontend budget or existing checks changed')
    return FRONTEND_BASELINE_SHA256


def source_constant(relative, name):
    for node in ast.walk(ast.parse((runner.ROOT / relative).read_text())):
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == name for target in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError('missing source baseline: ' + name)


class ModelWorkflowGuards(unittest.TestCase):
    def test_frontend_budget_retains_all_existing_checks(self):
        relative = '.github/workflows/qwen2-matrix-interface-frontend.yml'
        current = (runner.ROOT / relative).read_text()
        # Keep the original a2e4 + 15->20 minute body identity. The c554
        # historical-receipt fetch/probe is the only admitted later extension.
        self.assertEqual(validate_frontend_extension(current),
                         '898e1ced4a9b83641d5fe1944bffdbb3c3e4a71d4d51193cbd17bd7a94ff8aa4')
        for line in (FULLGRAPH_FETCH, FULLGRAPH_PROBE):
            for kind, changed in (
                ('missing', current.replace(line + '\n', '')),
                ('duplicate', current.replace(line, line + '\n' + line)),
                ('commit drift', current.replace(line, line.replace('37b7de', '000000'))),
                ('command drift', current.replace(line, line + ' --unreviewed')),
            ):
                with self.subTest(line=line, mutation=kind), self.assertRaisesRegex(ValueError, 'fetch/probe'):
                    validate_frontend_extension(changed)
        pair = FULLGRAPH_FETCH + '\n' + FULLGRAPH_PROBE
        for changed in (current.replace(pair, FULLGRAPH_PROBE + '\n' + FULLGRAPH_FETCH),
                        current.replace(pair + '\n', '') + pair + '\n',
                        current.replace(FULLGRAPH_PROBE, FULLGRAPH_PROBE.replace('fullgraph_numerical', 'prefix_numerical'))):
            with self.subTest(mutation='order or probe path'), self.assertRaisesRegex(ValueError, 'fetch/probe'):
                validate_frontend_extension(changed)
        with self.assertRaisesRegex(ValueError, 'frozen frontend'):
            validate_frontend_extension(current.replace('timeout-minutes: 20', 'timeout-minutes: 21'))
        # Every old Python test, build, and frontend command stays inside the
        # original whole-body guard; no wildcard excludes future drift.
        commands = [line for line in current.splitlines()
                    if line.startswith('          ') and 'python ' in line]
        self.assertGreater(len(commands), 30)
        for command in commands:
            with self.subTest(command=command), self.assertRaisesRegex(ValueError, 'frozen frontend'):
                validate_frontend_extension(current.replace(command, command + ' --unreviewed'))

    def test_exact_model_baselines_and_failure_artifacts(self):
        # Reuse the frontend's immutable-fetch validator, but only require the
        # two baselines actually used by this model/source-only workflow.
        spec = importlib.util.spec_from_file_location(
            'matrix_baseline_guards', runner.ROOT / 'tests/test_matrix_interface_candidate.py')
        guards = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guards)
        required = {
            source_constant('scripts/qwen2_dense_residency_numeric.py', 'SOURCE_PASS_COMMIT'),
            source_constant('candidates/qwen2_resident_matrix/transposed_seed/check_frontend.py', 'COMMIT'),
        }
        workflow = (runner.ROOT / '.github/workflows/qwen2-prefill-model-contract.yml').read_text()
        guards.validate_baseline_fetches(workflow, required)
        for ref in required:
            fetch = 'git fetch --no-tags --depth=1 origin ' + ref
            probe = 'git cat-file -e ' + ref + ':'
            self.assertLess(workflow.index(probe), workflow.index('python candidates/qwen2_resident_matrix/dense_block_reduce/run_tests.py'))
            for broken in (workflow.replace(fetch, '# missing fetch'),
                           workflow.replace(fetch, fetch[:-40] + 'main'),
                           workflow.replace(probe, 'git cat-file -e ' + '0' * 40 + ':')):
                with self.subTest(ref=ref), self.assertRaisesRegex(ValueError, 'baseline'):
                    guards.validate_baseline_fetches(broken, required)
        self.assertNotIn('fetch-depth: 0', workflow)
        self.assertNotIn('--unshallow', workflow)
        artifact = workflow.split('- name: Retain compact source-bound traffic evidence', 1)[1]
        self.assertRegex(artifact, r'(?m)^        if: always\(\)$')
        self.assertIn('work/qwen2_model_contract/dense-block-reduce-tests/', artifact)


class IsolatedRunnerGuards(unittest.TestCase):
    def run_children(self, children, timeout=120):
        with tempfile.TemporaryDirectory(prefix='reduction_runner_test_') as directory:
            root = Path(directory)
            suites = root / 'suites'
            suites.mkdir()
            (suites / '__init__.py').write_text('')
            for name, body in children.items():
                (suites / name).write_text(body)
            out = root / 'evidence'
            console = io.StringIO()
            with patch.object(runner, 'ROOT', root), patch.object(runner, 'HERE', suites), contextlib.redirect_stdout(console):
                report = runner.run(out, timeout)
            self.assertEqual(report, json.loads((out / 'summary.json').read_text()))
            logs = {entry['path']: (out / entry['log']).read_bytes() for entry in report['results']}
            for entry in report['results']:
                self.assertEqual(entry['log_sha256'], hashlib.sha256(logs[entry['path']]).hexdigest())
            return report, console.getvalue(), logs

    def test_setup_failure_is_visible_preserved_and_later_suite_runs(self):
        report, console, logs = self.run_children({
            'test_a_missing_baseline.py': '''import unittest
class SourceScope(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raise RuntimeError("missing immutable baseline 825caff3a6c618419c49c7da452e009ce86ae8b5")
    def test_source(self):
        pass
''',
            'test_b_pass.py': '''import unittest
class Good(unittest.TestCase):
    def test_pass(self):
        self.assertEqual(2 + 2, 4)
''',
        })
        self.assertEqual(report['status'], 'FAIL')
        self.assertEqual([entry['passed'] for entry in report['results']], [False, True])
        self.assertEqual(report['total_tests'], 1)
        self.assertIn('RuntimeError: missing immutable baseline 825caff3a6c618419c49c7da452e009ce86ae8b5', console)
        self.assertIn('Ran 0 tests', console)
        self.assertIn('Traceback', logs['suites/test_a_missing_baseline.py'].decode())

    def test_zero_exit_with_skip_still_fails(self):
        report, console, _ = self.run_children({
            'test_skip.py': '''import unittest
class Skip(unittest.TestCase):
    @unittest.skip("unavailable input")
    def test_skip(self):
        pass
''',
        })
        self.assertEqual(report['results'][0]['returncode'], 0)
        self.assertEqual(report['status'], 'FAIL')
        self.assertFalse(report['skips_allowed'])
        self.assertIn('OK (skipped=1)', console)

    def test_failed_console_tail_is_bounded_without_truncating_artifact(self):
        report, console, logs = self.run_children({
            'test_noisy.py': '''import unittest
class Noisy(unittest.TestCase):
    def test_fail(self):
        print("OLD_DIAGNOSTIC" + "x" * 50000)
        for i in range(120):
            print("filler", i)
        self.fail("FINAL_DIAGNOSTIC")
''',
        })
        self.assertEqual(report['status'], 'FAIL')
        tail = console.split('--- failure tail ', 1)[1].split('\n', 1)[1].split('--- end failure tail ---', 1)[0]
        self.assertLessEqual(len(tail.encode()), runner.FAILURE_TAIL_BYTES + 1)
        self.assertLessEqual(len(tail.splitlines()), runner.FAILURE_TAIL_LINES)
        self.assertNotIn('OLD_DIAGNOSTIC', console)
        self.assertIn('FINAL_DIAGNOSTIC', console)
        self.assertIn(b'OLD_DIAGNOSTIC', logs['suites/test_noisy.py'])

    def test_timeout_is_visible_and_fails(self):
        report, console, logs = self.run_children({
            'test_timeout.py': '''import time, unittest
class Timeout(unittest.TestCase):
    def test_timeout(self):
        time.sleep(10)
''',
        }, timeout=1)
        self.assertEqual(report['status'], 'FAIL')
        self.assertEqual(report['results'][0]['returncode'], 124)
        self.assertIn('Isolated suite timed out after 1 seconds.', console)
        self.assertIn(b'Isolated suite timed out', logs['suites/test_timeout.py'])


if __name__ == '__main__':
    unittest.main()
