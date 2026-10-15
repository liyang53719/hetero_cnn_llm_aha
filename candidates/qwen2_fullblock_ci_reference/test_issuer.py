"""Ephemeral synthetic certificates, never real approvals or reference execution."""
import copy
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('ci_issuer_recipe',HERE/'recipe.py')
R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)
with patch.dict(sys.modules,{'recipe':R}):
    spec=importlib.util.spec_from_file_location('ci_issuer',HERE/'issuer.py')
    I=importlib.util.module_from_spec(spec);spec.loader.exec_module(I)

class IssuerTests(unittest.TestCase):
    def setUp(self):
        self.source=dict(bytes=123,sha256='a'*64)
        self.policy=R.bootstrap_policy();self.budget=I.budgets();self.pins={'synthetic_only':True}
        self.closure='b'*64

    def fixture(self,root):
        path=root/R.WORK/'synthetic-certificate.json';path.parent.mkdir(parents=True)
        (root/R.BINDING).write_bytes(b'{"synthetic_only":true}')
        cert=dict(schema=1,status='APPROVED_SOURCE_POLICY_FOR_SINGLE_BOOTSTRAP',
            source_manifest=self.source,source_closure_sha256=self.closure,
            policy_sha256=R.sha(R.encoded(self.policy)),run_id='ci01',mode='bootstrap',
            output_scope='SEALED_BOOTSTRAP_OBSERVATIONS_UNACCEPTED',maximum_invocations=1,
            no_retry=True,exclusive_numeric_slot=True,numeric_executed=False,
            observed_bindings_independently_reviewed=False,historical_receipts_revalidated=False,
            frozen_mode_available=False,numerical_acceptance_allowed=False,budgets=self.budget,
            reviewer='SYNTHETIC_TEST_REVIEWER_NOT_AN_ACTUAL_APPROVAL',
            tool_identity=dict(implementation='cpython',python_major_minor=[3,12],source_manifest=self.source))
        return path,cert

    def operation(self,root,path,cert,operation,env_override=None):
        path.write_bytes(R.encoded(cert));digest=R.identity(path)['sha256']
        env={I.CERTIFICATE_ENV:digest,I.CLOSURE_ENV:self.closure}
        if env_override:env.update(env_override)
        with patch.dict(os.environ,env),patch.object(R,'ROOT',root),patch.object(R,'CI_ROOT',root), \
             patch.object(R,'source_manifest',return_value=self.source),patch.object(R,'bootstrap_policy',return_value=self.policy), \
             patch.object(I,'budgets',return_value=self.budget),patch.object(R,'load_pins',return_value=self.pins), \
             patch.object(R,'source_check',return_value={}),patch.object(I,'source_closure_digest',return_value=self.closure):
            return operation(str(path.relative_to(root)),digest)

    def test_default_issuer_is_cold(self):
        p=subprocess.run([sys.executable,'-B',str(HERE/'issuer.py')],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('NOT_EXECUTED',p.stdout)
        self.assertIn('"approval_generated": false',p.stdout)

    def test_missing_external_digest_never_self_approves(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaisesRegex(ValueError,'external SHA256'):I.external_pins()

    def test_argument_cannot_override_external_launch_digest(self):
        with patch.dict(os.environ,{I.CERTIFICATE_ENV:'a'*64,I.CLOSURE_ENV:'b'*64}):
            with self.assertRaisesRegex(ValueError,'certificate argument'):I.external_pins('c'*64,'b'*64)
            with self.assertRaisesRegex(ValueError,'closure argument'):I.external_pins('a'*64,'c'*64)

    def test_certificate_bytes_must_match_external_digest(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);path,cert=self.fixture(root)
            with self.assertRaisesRegex(ValueError,'byte identity'):
                self.operation(root,path,cert,lambda p,h:I.validate_certificate(p),{I.CERTIFICATE_ENV:'c'*64})

    def test_static_scope_and_budget_cannot_expand(self):
        cases=[('mode','frozen'),('run_id','ci02'),('maximum_invocations',True),
            ('observed_bindings_independently_reviewed',True),('numerical_acceptance_allowed',True),
            ('source_closure_sha256','c'*64),('policy_sha256','c'*64),('budgets',{})]
        for key,value in cases:
            with self.subTest(key=key),tempfile.TemporaryDirectory() as d:
                root=Path(d);path,cert=self.fixture(root);cert[key]=value
                with self.assertRaisesRegex(ValueError,'source-policy certificate'):
                    self.operation(root,path,cert,lambda p,h:I.validate_certificate(p))

    def test_real_source_policy_expansion_is_disclosed_and_revalidated(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);path,cert=self.fixture(root)
            def operation(p,h):
                document,spec=I.validate_certificate(p,h,self.closure)
                review=I.expand(document,spec,self.pins)
                self.assertEqual(review['generated_by'],I.ISSUER)
                self.assertEqual(review['approval_basis'],I.APPROVAL_BASIS)
                self.assertEqual(review['reviewer'],cert['reviewer'])
                self.assertFalse(review['observed_bindings_independently_reviewed'])
                self.assertEqual(I.validate_expansion(review,self.pins),document)
                review['generated_by']=cert['reviewer']
                with self.assertRaisesRegex(ValueError,'expansion|expanded'):I.validate_expansion(review,self.pins)
            self.operation(root,path,cert,operation)

    def test_issuer_never_claims_reviewer_authored_dynamic_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);path,cert=self.fixture(root)
            def operation(p,h):
                result=I.issue(p,h,self.closure,'ci01')
                self.assertFalse(result['numeric_executed'])
                review=R.parse((root/R.WORK/'ci01/SOURCE_REVIEW.json').read_bytes())
                go=R.parse((root/R.WORK/'ci01/GO.json').read_bytes())
                self.assertNotEqual(review['generated_by'],review['reviewer'])
                self.assertEqual(go['issued_by'],I.ISSUER)
                self.assertFalse(review['observed_bindings_independently_reviewed'])
                with self.assertRaisesRegex(ValueError,'fresh one-use'):I.issue(p,h,self.closure,'ci01')
            self.operation(root,path,cert,operation)

    def test_actual_source_closure_drift_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);path,cert=self.fixture(root)
            def operation(p,h):
                with patch.object(I,'source_closure_digest',return_value='c'*64):
                    with self.assertRaisesRegex(ValueError,'actual source closure'):I.validate_certificate(p,h,self.closure)
            self.operation(root,path,cert,operation)

    def test_validate_only_never_reads_observed_bindings_or_runtime(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);path,cert=self.fixture(root)
            def operation(p,h):
                with patch.object(R,'load_pins',side_effect=AssertionError('observed bindings read')), \
                     patch.object(R,'source_check',side_effect=AssertionError('runtime/source preflight called')):
                    self.assertEqual(I.main(['--validate-only','--certificate',p,'--certificate-sha256',h,
                        '--source-closure-sha256',self.closure,'--run-id','ci01']),0)
                self.assertFalse((root/R.WORK/'ci01/GO.json').exists())
            self.operation(root,path,cert,operation)

    def test_unknown_certificate_fields_and_self_issued_review_rejected(self):
        for key,value in [('extra','not allowed'),('reviewer',I.ISSUER)]:
            with self.subTest(key=key),tempfile.TemporaryDirectory() as d:
                root=Path(d);path,cert=self.fixture(root);cert[key]=value
                with self.assertRaises(ValueError):self.operation(root,path,cert,lambda p,h:I.validate_certificate(p))

if __name__=='__main__':unittest.main()
