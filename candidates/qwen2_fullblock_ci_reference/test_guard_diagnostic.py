"""Actual guard wrapper failure paths, with no numeric/native execution."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from contextlib import redirect_stderr
from . import test_lifecycle as fixture
from . import failure_diagnostic as D
from . import comparison_diagnostic as CDF
from . import all_comparisons as ACD
from . import backend_policy as BP
from . import repeat_observation as RO
HERE=Path(__file__).resolve().parent
with patch.dict(sys.modules,{'recipe':fixture.R,'lifecycle':fixture.L,'issuer':fixture.I,'failure_diagnostic':D,'comparison_diagnostic':CDF,'all_comparisons':ACD,'backend_policy':BP,'repeat_observation':RO}):
    spec=importlib.util.spec_from_file_location('ci_guard_diagnostic_test',HERE/'guard.py')
    G=importlib.util.module_from_spec(spec);spec.loader.exec_module(G)

class GuardDiagnosticTests(unittest.TestCase):
    def test_supervisor_exception_identity_and_arguments_preserved(self):
        error=ValueError('private');stream=io.StringIO()
        with patch.object(G,'_original_run',side_effect=error) as original,redirect_stderr(stream):
            with self.assertRaises(ValueError) as caught:G.observed_run('bootstrap','ci01','go')
        self.assertIs(caught.exception,error);original.assert_called_once_with('bootstrap','ci01','go')
        record=D.checked(json.loads(stream.getvalue()));self.assertEqual(record['origin'],'SUPERVISOR')
        self.assertNotIn('private',str(record))
    def test_success_return_unchanged_and_no_record(self):
        value=object();stream=io.StringIO()
        with patch.object(G,'_original_run',return_value=value),redirect_stderr(stream):
            self.assertIs(G.observed_run(1,thing=2),value)
        self.assertEqual(stream.getvalue(),'')
    def test_worker_returns_original_failure_status(self):
        stream=io.StringIO()
        with patch.dict(sys.modules,{'lifecycle':G.L}),patch.object(G.R,'legacy',side_effect=TypeError('private')),redirect_stderr(stream):
            self.assertEqual(G.worker('3','bootstrap','unused'),2)
        records=[json.loads(x) for x in stream.getvalue().splitlines()]
        self.assertEqual(D.checked(records[0])['origin'],'WORKER')
        self.assertEqual(records[1]['status'],'WORKER_FAILED_UNSEALED')
    def test_diagnostic_failure_does_not_mask_original(self):
        error=ValueError('original')
        with patch.object(G,'_original_run',side_effect=error),patch.object(D,'project',side_effect=OSError('disk')):
            with self.assertRaises(ValueError) as caught:G.observed_run()
        self.assertIs(caught.exception,error)
    def test_worker_emits_comparison_without_changing_failure(self):
        record=dict(schema=1,status='CI_REFERENCE_COMPARISON',node='NODE_06',categories=['HASH'],mismatch_count=3)
        stream=io.StringIO()
        with patch.dict(sys.modules,{'lifecycle':G.L}),patch.object(G.R,'legacy',side_effect=ValueError('private')), \
             patch.object(CDF,'project',return_value=record),redirect_stderr(stream):
            self.assertEqual(G.worker('3','bootstrap','unused'),2)
        records=[json.loads(line) for line in stream.getvalue().splitlines()]
        self.assertEqual(records[1],CDF.checked(record))
        self.assertEqual(records[2]['status'],'WORKER_FAILED_UNSEALED')

    def test_comparison_failure_does_not_mask_worker_failure(self):
        stream=io.StringIO()
        with patch.dict(sys.modules,{'lifecycle':G.L}),patch.object(G.R,'legacy',side_effect=ValueError('original')), \
             patch.object(CDF,'project',side_effect=ValueError('projection')),redirect_stderr(stream):
            self.assertEqual(G.worker('3','bootstrap','unused'),2)
        self.assertNotIn('projection',stream.getvalue())
        self.assertIn('WORKER_FAILED_UNSEALED',stream.getvalue())

    def test_preloaded_expectations_exact_identity(self):
        actual=G.comparison_expectations()
        self.assertEqual(set(actual),set(ACD.NAMES))
        with patch.object(G.R,'sha',return_value='0'*64):
            with self.assertRaises(ValueError):G.comparison_expectations()

    def test_all_observation_failure_does_not_mask_original(self):
        error=ValueError('original');stream=io.StringIO()
        with patch.object(ACD,'project',side_effect=ValueError('diagnostic')),redirect_stderr(stream):
            G.emit_failure(error,'WORKER',{'unused':True})
        self.assertNotIn('diagnostic',stream.getvalue())
        self.assertEqual(D.checked(json.loads(stream.getvalue()))['origin'],'WORKER')

if __name__=='__main__':unittest.main()
