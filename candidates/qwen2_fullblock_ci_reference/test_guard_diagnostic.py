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
HERE=Path(__file__).resolve().parent
with patch.dict(sys.modules,{'recipe':fixture.R,'lifecycle':fixture.L,'issuer':fixture.I,'failure_diagnostic':D}):
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
if __name__=='__main__':unittest.main()
