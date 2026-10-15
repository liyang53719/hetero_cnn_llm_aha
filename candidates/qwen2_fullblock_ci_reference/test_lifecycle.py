"""Synthetic GO/source-policy fixtures exercise fail-closed admission, never capture."""
import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('ci_lifecycle_recipe',HERE/'recipe.py')
R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)
with patch.dict(sys.modules,{'recipe':R}):
    spec=importlib.util.spec_from_file_location('issuer',HERE/'issuer.py')
    I=importlib.util.module_from_spec(spec);spec.loader.exec_module(I)
with patch.dict(sys.modules,{'recipe':R,'issuer':I}):
    spec=importlib.util.spec_from_file_location('ci_lifecycle',HERE/'lifecycle.py')
    L=importlib.util.module_from_spec(spec);spec.loader.exec_module(L)

class LifecycleTests(unittest.TestCase):
    def fixtures(self,root):
        self.source=dict(bytes=1,sha256='a'*64)
        self.policy=R.bootstrap_policy()
        self.pins={'synthetic_test_only':True}
        self.review=dict(status='APPROVED_SOURCE_FOR_SINGLE_BOOTSTRAP',source_manifest=self.source,
            mode='bootstrap',numeric_executed=False,reviewer='synthetic-independent-reviewer',
            ci_binding_policy=self.policy,historical_receipts_revalidated=False,
            observed_bindings_independently_reviewed=False,
            tool_identity=dict(implementation='cpython',python_major_minor=[3,12],source_manifest=self.source))
        self.go=dict(schema=1,action='single-bootstrap',run_id='ci01',source_manifest=self.source,
            issued_by=I.ISSUER,maximum_invocations=1,no_retry=True,exclusive_numeric_slot=True)
        self.review_path=root/R.WORK/'synthetic-review.json'
        self.review_path.parent.mkdir(parents=True)
        self.go_path=root/R.WORK/'synthetic-go.json'

    def admission(self,root,mutate_pins=False):
        self.review_path.write_bytes(R.encoded(self.review))
        self.go['source_review']=dict(path=str(self.review_path.relative_to(root)),**R.identity(self.review_path))
        self.go_path.write_bytes(R.encoded(self.go))
        with patch.object(R,'ROOT',root),patch.object(R,'source_manifest',return_value=self.source), \
             patch.object(R,'bootstrap_policy',return_value=self.policy), \
             patch.object(R,'load_pins',return_value={} if mutate_pins else self.pins), \
             patch.object(I,'validate_expansion',return_value={}):
            # Certificate validation is tested separately in test_issuer.py.
            return L.validate_go(R,self.pins,str(self.go_path.relative_to(root)),'ci01','bootstrap')

    def test_source_policy_authorizes_only_unaccepted_bootstrap_procedure(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixtures(root)
            result=self.admission(root)
            self.assertEqual(result['content']['action'],'single-bootstrap')
            self.assertFalse(self.policy['observed_bindings_independently_reviewed'])
            self.assertFalse(self.policy['numerical_acceptance_allowed'])
            self.assertEqual(self.policy['output_scope'],'SEALED_BOOTSTRAP_OBSERVATIONS_UNACCEPTED')

    def test_cannot_claim_unknown_bindings_were_reviewed(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixtures(root);self.review['observed_bindings_independently_reviewed']=True
            with self.assertRaisesRegex(ValueError,'source-policy'):self.admission(root)

    def test_self_signed_review_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixtures(root);self.review['reviewer']=self.go['issued_by']
            with self.assertRaisesRegex(ValueError,'distinct'):self.admission(root)

    def test_policy_scope_or_paths_cannot_widen(self):
        for key,value in [('output_scope','FROZEN_PASS'),('root','/tmp'),('frozen_mode_available',True)]:
            with self.subTest(key=key),tempfile.TemporaryDirectory() as d:
                root=Path(d);self.fixtures(root)
                self.review['ci_binding_policy']=copy.deepcopy(self.policy)
                self.review['ci_binding_policy'][key]=value
                with self.assertRaisesRegex(ValueError,'source-policy'):self.admission(root)

    def test_observed_binding_drift_rejected_at_admission(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixtures(root)
            with self.assertRaisesRegex(ValueError,'bindings drift'):self.admission(root,mutate_pins=True)

    def test_one_use_no_retry_exclusive_slot_are_mandatory(self):
        for key,value in [('maximum_invocations',True),('maximum_invocations',2),('no_retry',False),('exclusive_numeric_slot',False)]:
            with self.subTest(key=key,value=value),tempfile.TemporaryDirectory() as d:
                root=Path(d);self.fixtures(root);self.go[key]=value
                with self.assertRaisesRegex(ValueError,'single go'):self.admission(root)

    def test_frozen_and_bad_run_ids_rejected(self):
        with self.assertRaisesRegex(ValueError,'frozen mode'):L.run_path(R,'ci01','frozen')
        with self.assertRaisesRegex(ValueError,'canonical run id'):L.run_path(R,'../escape','bootstrap')

    def test_missing_pipe_capability_rejected(self):
        with self.assertRaisesRegex(ValueError,'live bounded-wrapper'):
            L.claim_capability(R,{},R.ROOT/R.WORK/'synthetic01/bootstrap','bootstrap',None)

if __name__=='__main__':unittest.main()
