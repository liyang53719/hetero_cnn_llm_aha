import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from . import gates, launch, runner


class V2ColdTests(unittest.TestCase):
    def test_default_does_not_load_numeric_or_inputs(self):
        for entry in (runner, launch):
            stream = io.StringIO()
            with patch.object(runner, 'dependencies', side_effect=AssertionError('numeric runtime forbidden')), \
                 patch.object(subprocess, 'Popen', side_effect=AssertionError('spawn forbidden')), \
                 contextlib.redirect_stdout(stream):
                self.assertEqual(entry.main([]), 0)
            result = json.loads(stream.getvalue())
            self.assertEqual(result['status'], 'NOT_EXECUTED')
            self.assertFalse(result['actual_execution_authorized'] or result['input_loading'])

    def test_v1_closure_remains_exact(self):
        p = gates.verify_dependencies()
        self.assertEqual(len(p['dependency_sha256']), 178)
        self.assertEqual(p['parent_source_manifest_sha256'], '18075282b8093ad33a85f20c736d134a4d36276930a0e4f1712c5251901fe08b')

    def test_review_required(self):
        for value in (None, '', '0' * 64):
            with self.assertRaises(ValueError): gates.require_review(value)

    def test_real_audit_scalar_initialization(self):
        argv = [sys.executable, '-B']
        if sys.flags.optimize: argv.append('-O')
        argv += [str(gates.HERE / 'environment_probe.py'), '--environment-only']
        completed = subprocess.run(argv, cwd=gates.ROOT, text=True, capture_output=True, timeout=20)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result['status'], 'PASS_REAL_SCALAR_ENVIRONMENT_INITIALIZATION')
        self.assertTrue(result['real_audit_hook'] and result['scalar_initialized'])
        self.assertEqual(result['fixed_environment_primitive_probes'], 5)
        self.assertFalse(result['model_chain_executed'] or result['model_inputs_loaded'] or result['matrix_fma_executed'])
        self.assertEqual(len(result['environment_events']), 2)
        self.assertGreaterEqual(len(result['negative_controls']), 25)


if __name__ == '__main__': unittest.main()
