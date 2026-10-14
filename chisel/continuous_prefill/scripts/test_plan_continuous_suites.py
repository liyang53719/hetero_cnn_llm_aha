#!/usr/bin/env python3
"""Cold classification gate; executes no RTL or checkpoint arithmetic."""
import tempfile
import unittest
from pathlib import Path
from plan_continuous_suites import plan, FIXTURE_SUITES, EXTERNAL_FIXTURE_SUITES, RUN_GROUPS

class FixtureClassificationTest(unittest.TestCase):
    def project(self, root):
        directory=root/'src/test/scala/heteronpu/continuous'
        directory.mkdir(parents=True)
        names=list(FIXTURE_SUITES.values())+list(EXTERNAL_FIXTURE_SUITES.values())+['heteronpu.continuous.OrdinarySpec']
        for name in names:(directory/(name.split('.')[-1]+'.scala')).write_text('// fixture classification only\n')
        return directory,names
    def test_complete_disjoint_external_classification(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);_,names=self.project(root);result=plan(root)
            self.assertEqual(sorted(sum(result.values(),[])),sorted(names))
            for name in EXTERNAL_FIXTURE_SUITES.values():
                self.assertFalse(any(name in result[g] for g in RUN_GROUPS))
            self.assertEqual(result['general'],['heteronpu.continuous.OrdinarySpec'])
    def test_missing_external_suite_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);directory,_=self.project(root)
            (directory/'ElementwiseRegisterLoanReplaySpec.scala').unlink()
            with self.assertRaisesRegex(ValueError,'MISSING_FIXTURE_SUITE'):plan(root)
    def test_new_general_suite_is_still_discovered(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);directory,_=self.project(root)
            (directory/'NewControlSpec.scala').write_text('// ordinary suite\n')
            self.assertIn('heteronpu.continuous.NewControlSpec',plan(root)['general'])
    def test_actual_repository_external_has_explicit_runner(self):
        root=Path(__file__).resolve().parents[1];result=plan(root)
        self.assertEqual(result['frozen_actual_rms_epilogue'],[EXTERNAL_FIXTURE_SUITES['frozen_actual_rms_epilogue']])
        repo=root.parents[1]
        runner=(repo/'scripts/run_elementwise_register_loan_tests.py').read_text()
        self.assertIn('ElementwiseRegisterLoanReplaySpec',runner)
        self.assertIn('--actual-fixture-root',runner)
        source=(root/'src/test/scala/heteronpu/continuous/ElementwiseRegisterLoanReplaySpec.scala').read_text()
        self.assertIn('sys.env("HETERO_RMS_LOAN_FIXTURE_ROOT")',source)
        self.assertNotIn('assume(',source)
        self.assertNotIn('cancel(',source)
        h2048=(root/'src/test/scala/heteronpu/continuous/GdnRmsNormFixedBankReplaySpec.scala').read_text()
        self.assertIn('sys.env("HETERO_H2048_FIXTURE_ROOT")',h2048)
        self.assertNotIn('assume(',h2048)
        self.assertNotIn('cancel(',h2048)
        self.assertIn('GdnRmsNormFixedBankReplaySpec',(repo/'scripts/run_h2048_rms_borrower_tests.py').read_text())

if __name__=='__main__':unittest.main()
