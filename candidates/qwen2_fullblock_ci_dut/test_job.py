"""Cold fixed-scope orchestration tests. No install, download, native load or model."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from . import job as j

class JobTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);d=self.root/j.AUTH;d.mkdir(parents=True)
        self.path=d/'DUT_REVIEW.json'
        self.value=dict(schema=1,status='APPROVED_SINGLE_CI_M128_MODEL',job_total_minutes=75,
            reference_inner_seconds=120,reference_outer_seconds=122,dut_inner_seconds=3300,dut_outer_seconds=3330,
            maximum_invocations=1,no_retry=True,source_closure_sha256='a'*64,reference_certificate_sha256='b'*64,
            reference_source_closure_sha256=j.closure.BOOTSTRAP_SHA,reviewer='/root/review_fixture')
        self.write()
        for target,key,value in ((j,'ROOT',self.root),(j.inputs,'CI_ROOT',self.root)):
            p=patch.object(target,key,value);p.start();self.addCleanup(p.stop)
        p=patch.object(j.closure,'digest',return_value='a'*64);p.start();self.addCleanup(p.stop)
        p=patch.object(j.subprocess,'check_output',return_value='c'*40+'\n');p.start();self.addCleanup(p.stop)
        p=patch.dict(os.environ,dict(GITHUB_RUN_ATTEMPT='1',GITHUB_SHA='c'*40,QWEN2_DUT_SOURCE_CLOSURE_SHA256='',QWEN2_BOOTSTRAP_CERTIFICATE_SHA256=''));p.start();self.addCleanup(p.stop)
    def write(self):self.path.write_text(json.dumps(self.value))
    def test_fixed_authorization(self):self.assertEqual(j.authorize(),self.value)
    def test_reference_certificate_conflict(self):
        with patch.dict(os.environ,{'QWEN2_BOOTSTRAP_CERTIFICATE_SHA256':'e'*64}):
            with self.assertRaises(ValueError):j.authorize()
    def test_missing_review_closed(self):
        self.path.unlink()
        with self.assertRaises(FileNotFoundError):j.authorize()
    def test_source_drift(self):
        with patch.object(j.closure,'digest',return_value='d'*64):
            with self.assertRaises(ValueError):j.authorize()
    def test_no_rerun(self):
        with patch.dict(os.environ,{'GITHUB_RUN_ATTEMPT':'2'}):
            with self.assertRaises(ValueError):j.authorize()
    def test_budget_and_bool_types(self):
        for key,value in [('job_total_minutes',76),('maximum_invocations',True),('no_retry',1)]:
            before=dict(self.value);self.value[key]=value;self.write()
            with self.assertRaises(ValueError):j.authorize()
            self.value=before;self.write()
    def test_extra_metadata_refused(self):
        self.value['outputs']={};self.write()
        with self.assertRaises(ValueError):j.authorize()
    def test_wrong_checkout(self):
        with patch.dict(os.environ,{'GITHUB_SHA':'d'*40}):
            with self.assertRaises(ValueError):j.authorize()
    def test_reference_scope_cannot_change(self):
        self.value['reference_source_closure_sha256']='d'*64;self.write()
        with self.assertRaises(ValueError):j.authorize()
    def test_actual_uses_binder_returned_pin(self):
        from . import recipe
        captured={}
        def run(argv,**kwargs):
            captured['pin']=os.environ.get(recipe.BINDING_ENV)
            captured['argv']=argv
            return type('Completed',(),{'returncode':0})()
        with patch.object(j,'bind',return_value={'binding_sha256':'e'*64}),patch.object(j.subprocess,'run',side_effect=run):
            self.assertEqual(j.actual(),'ACTUAL_PROCESS_COMPLETED_REQUIRES_AGGREGATE')
        self.assertEqual(captured['pin'],'e'*64)
        self.assertIn('--actual',captured['argv'])
    def test_actual_bind_failure_never_spawns(self):
        with patch.object(j,'bind',side_effect=ValueError('bad binding')),patch.object(j.subprocess,'run') as run:
            with self.assertRaises(ValueError):j.actual()
            run.assert_not_called()
    def test_missing_action_cannot_start(self):
        with patch.object(j,'actual') as actual:
            with self.assertRaises(SystemExit):j.main([])
            actual.assert_not_called()
if __name__=='__main__':unittest.main()
