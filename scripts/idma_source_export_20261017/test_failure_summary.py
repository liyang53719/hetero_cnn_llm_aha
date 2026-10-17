#!/usr/bin/env python3
"""Cold-only tests: synthetic private receipts, no subprocess or network."""
import json
import os
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import patch
import safe_failure as sf


class FailureSummaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.receipt = self.root / 'receipt.json'
        self.output = self.root / 'safe.json'

    def run_summary(self, value):
        self.receipt.write_text(json.dumps(value))
        self.assertEqual(sf.emit(self.receipt, self.output), 0)
        return json.loads(self.output.read_text())

    def test_strict_projection(self):
        secret = 'SECRET/private/source.v boot-id argv credentials'
        value = {'status': 'FAILED', 'error': secret, 'error_category': 'validation_failed',
                 'python_sha256': 'a'*64, 'manifest_sha256': secret,
                 'cleanup_failure_evidence': secret, 'stages': [
                     {'exit': 1, 'error': secret, 'error_category': 'command_failed',
                      'cleanup_scope': sf.SCOPE, 'cleanup_complete': True,
                      'cleanup_proof': secret, 'argv': [secret], 'cwd': secret}]}
        result = self.run_summary(value)
        text = self.output.read_text()
        self.assertNotIn('SECRET', text)
        self.assertNotIn('cleanup_proof', text)
        self.assertNotIn('argv', text)
        self.assertEqual(result['hashes'], {'python_sha256': 'a'*64})
        self.assertTrue(result['stages'][0]['cleanup_verified'])
        self.assertFalse(result['global_cleanup_verified'])

    def test_missing(self):
        self.assertEqual(sf.emit(self.receipt, self.output), 0)
        self.assertEqual(json.loads(self.output.read_text())['receipt_state'], 'missing')

    def test_broken_json(self):
        self.receipt.write_text('{SECRET')
        self.assertEqual(sf.emit(self.receipt, self.output), 0)
        self.assertEqual(json.loads(self.output.read_text())['receipt_state'], 'invalid')

    def test_duplicate_keys(self):
        self.receipt.write_text('{"status":"FAILED","stages":[],"stages":[]}')
        self.assertEqual(sf.emit(self.receipt, self.output), 0)
        self.assertEqual(json.loads(self.output.read_text())['receipt_state'], 'invalid')

    def test_malformed_types(self):
        for value in (None, [], {'stages': {}}, {'stages': [None]}, {'stages': [{}]*(sf.MAX_STAGES+1)}):
            with self.subTest(value_type=type(value)):
                self.assertEqual(sf.project(value)['receipt_state'], 'invalid')
        result = sf.project({'status': [], 'error_category': {}, 'stages': [
            {'exit': True, 'cleanup_complete': 1, 'cleanup_scope': sf.SCOPE,
             'error_category': ['SECRET']}]})
        self.assertIsNone(result['stages'][0]['exit'])
        self.assertFalse(result['stages'][0]['cleanup_verified'])
        self.assertEqual(result['stages'][0]['error_category'], 'unknown_error')

    def test_unknown_scope(self):
        result = sf.project({'stages': [{'cleanup_scope': '/SECRET', 'cleanup_complete': True}]})
        self.assertFalse(result['stages'][0]['cleanup_verified'])
        self.assertNotIn('SECRET', json.dumps(result))

    def test_no_inferred_cleanup(self):
        result = sf.project({'status': 'PASS_SOURCE_EXPORT_ONLY', 'stages': []})
        self.assertFalse(result['global_cleanup_verified'])

    def test_oversize(self):
        with self.receipt.open('wb') as stream:
            stream.truncate(sf.MAX_BYTES+1)
        self.assertEqual(sf.emit(self.receipt, self.output), 0)
        self.assertEqual(json.loads(self.output.read_text())['receipt_state'], 'invalid')

    def test_fifo(self):
        os.mkfifo(self.receipt)
        self.assertEqual(sf.emit(self.receipt, self.output), 0)
        self.assertEqual(json.loads(self.output.read_text())['receipt_state'], 'invalid')

    def test_symlink(self):
        self.receipt.symlink_to(self.root/'absent')
        self.assertEqual(sf.emit(self.receipt, self.output), 0)
        self.assertEqual(json.loads(self.output.read_text())['receipt_state'], 'invalid')

    def test_output_no_overwrite(self):
        self.output.write_text('KEEP')
        self.assertEqual(sf.emit(self.receipt, self.output), 2)
        self.assertEqual(self.output.read_text(), 'KEEP')

    def test_read_timeout(self):
        with patch.object(sf, 'read_receipt', side_effect=TimeoutError('SECRET')):
            self.assertEqual(sf.emit(self.receipt, self.output), 0)
        self.assertEqual(json.loads(self.output.read_text())['receipt_state'], 'read_timeout')
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    def test_existing_deadline_unchanged(self):
        signal.setitimer(signal.ITIMER_REAL, 60)
        try:
            self.assertEqual(sf.emit(self.receipt, self.output), 2)
            self.assertGreater(signal.getitimer(signal.ITIMER_REAL)[0], 59)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)

    def test_hash_and_exit_bounds(self):
        result = sf.project({'stages': [{'exit': -9, 'stdout_sha256': 'b'*64,
                                        'stderr_sha256': 'c'*64, 'sha256': 'd'*64,
                                        'arbitrary_sha256': 'e'*64},
                                       {'exit': 1000000, 'stdout_sha256': '/SECRET'}]})
        first, second = result['stages']
        self.assertEqual(first['exit'], -9)
        self.assertEqual(first['stdout_sha256'], 'b'*64)
        self.assertEqual(first['stderr_sha256'], 'c'*64)
        self.assertNotIn('sha256', first)
        self.assertNotIn('arbitrary_sha256', first)
        self.assertIsNone(second['exit'])
        self.assertNotIn('stdout_sha256', second)
        self.assertNotIn('stderr_sha256', second)
        self.assertFalse(second['cleanup_verified'])

    def test_scope_matches_pinned_helper(self):
        # Read only, never execute the process-cleanup helper during this test.
        import ast
        tree = ast.parse(Path(sf.__file__).with_name('strict_cleanup.py').read_text())
        values = [ast.literal_eval(node.value) for node in tree.body
                  if isinstance(node, ast.Assign) and any(
                      isinstance(target, ast.Name) and target.id == 'SCOPE'
                      for target in node.targets)]
        self.assertEqual(values, [sf.SCOPE])

    def test_nonfinite_and_deep_json(self):
        for data in ('{"stages":[],"x":NaN}', '['*2000+']'*2000):
            self.receipt.write_text(data)
            self.assertEqual(sf.emit(self.receipt, self.output), 0)
            self.assertEqual(json.loads(self.output.read_text())['receipt_state'], 'invalid')
            self.output.unlink()


if __name__ == '__main__':
    unittest.main()
