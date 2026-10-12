"""The isolation harness must discover, run and account for every file."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("isolated_public", ROOT / "scripts/run_isolated_public_tests.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class IsolatedPublicTests(unittest.TestCase):
    def execute(self, sources, timeout=10):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            suite = root / "suite"
            suite.mkdir()
            for name, source in sources.items():
                (suite / name).write_text(source)
            result = runner.run_suite(root, suite, root / "results", timeout)
            self.assertEqual(result, json.loads((root / "results/summary.json").read_text()))
            return result

    def test_every_file_is_counted_and_environment_is_isolated(self):
        source = "import os, unittest\nclass T(unittest.TestCase):\n def test_a(self):\n  self.assertNotIn('PUBLIC_TEST_MUTATION', os.environ)\n  os.environ['PUBLIC_TEST_MUTATION']='1'\n"
        result = self.execute({"test_z.py": source, "test_a.py": source, "helper.py": "raise RuntimeError()"})
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["total_tests"], 2)
        self.assertEqual([x["path"] for x in result["inventory"]], ["suite/test_a.py", "suite/test_z.py"])
        self.assertTrue(all(x["test_count"] == 1 and x["returncode"] == 0 for x in result["results"]))

    def test_failure_does_not_skip_later_files_and_fails_aggregate(self):
        result = self.execute({"test_a.py": "import unittest\nclass T(unittest.TestCase):\n def test_a(self): self.fail('expected fixture failure')\n",
                               "test_z.py": "import unittest\nclass T(unittest.TestCase):\n def test_a(self): pass\n"})
        self.assertEqual(result["exit_code"], 1)
        self.assertEqual(result["total_tests"], 2)
        self.assertEqual([x["returncode"] for x in result["results"]], [1, 0])

    def test_empty_skipped_and_import_error_are_not_success(self):
        for source in ["", "raise ImportError('fixture')\n",
                       "import unittest\nclass T(unittest.TestCase):\n @unittest.skip('fixture')\n def test_a(self): pass\n"]:
            with self.subTest(source=source):
                self.assertEqual(self.execute({"test_a.py": source})["exit_code"], 1)

    def test_timeout_is_recorded_and_fails(self):
        result = self.execute({"test_a.py": "import time\ntime.sleep(3)\n"}, timeout=1)
        self.assertTrue(result["results"][0]["timed_out"])
        self.assertEqual(result["results"][0]["returncode"], 124)
        self.assertEqual(result["exit_code"], 1)

    def test_empty_discovery_and_invalid_timeout_rejected(self):
        with self.assertRaisesRegex(ValueError, "discovery"):
            self.execute({})
        for timeout in [0, 301]:
            with self.assertRaisesRegex(ValueError, "timeout"):
                self.execute({"test_a.py": ""}, timeout)

    def test_workflow_uses_isolation_without_public_file_exclusions(self):
        workflow = (ROOT / ".github/workflows/qwen2-matrix-interface-frontend.yml").read_text()
        command = "python scripts/run_isolated_public_tests.py --out work/matrix-interface-tests/public-tests"
        self.assertEqual(workflow.count(command), 1)
        self.assertNotIn("python -m unittest discover -s candidates/qwen2_resident_matrix/ffn_public", workflow)
        self.assertIn("python -m unittest discover -s tests -p test_isolated_public_tests.py -v", workflow)


if __name__ == "__main__":
    unittest.main()
