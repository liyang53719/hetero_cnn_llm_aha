"""Cold recipe proofs. All constructed receipts are ephemeral synthetic fixtures."""
import copy
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('ci_dut_recipe_tests',HERE/'recipe.py')
R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)

class RecipeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pins=R.C.O.load_pins()
        cls.outputs,cls.expected_source=R.source_expectations(cls.pins)
        cls.source={'bytes':1,'sha256':'a'*64}
        cls.closure='b'*64
        cls.observed={'bytes':1,'sha256':'c'*64}

    def setUp(self):
        p=patch.dict(os.environ,{'QWEN2_BOOTSTRAP_CERTIFICATE_SHA256':'d'*64})
        p.start();self.addCleanup(p.stop)

    def test_wrong_or_missing_reference_certificate(self):
        for expected in ('e'*64,''):
            with patch.dict(os.environ,{'QWEN2_BOOTSTRAP_CERTIFICATE_SHA256':expected}):
                with self.assertRaises(ValueError):self.validate(*self.documents())

    def documents(self,observed=None):
        p=self.pins
        boundary=dict(source_manifest=self.source,pins=observed or self.observed,
            effective_pins_sha256=R.sha(R.encoded(p)),source_closure_sha256=self.closure,
            historical_receipts_revalidated=False,native_files=p['runtime_native_files'],
            raw13={s['path']:{k:s[k] for k in ('bytes','sha256')} for s in p['raw_tensors']},
            sources={k:{f:v[f] for f in ('bytes','sha256')} for k,v in p['sources'].items()},
            input_proofs={},raw_support={},external_certificate_sha256='d'*64)
        resources=dict(returncode=0,limit_reason=None,rss_limit_bytes=1536*(1<<20),
            overall_wall_limit_seconds=120,external_watchdog_deadline_seconds=122,
            independent_overall_watchdog_enabled=True,cleanup_pids=[],descendant_cleanup={'remaining_descendants':{}},
            overall_elapsed_seconds=1.0,peak_sampled_process_tree_rss_bytes=1)
        manifest=dict(status='BOOTSTRAP_UNACCEPTED_NO_NUMERICAL_VERDICT',stage='bootstrap',
            source_pins_sha256=R.PINS_SHA256,official_model_ast_nodes=38,official_activation_ast_nodes=14,
            official_ast_subset_executed=True,prior18_fresh_hash_matches=True,frozen29_hash_matches=None,
            wrapper_boundary_unchanged=True,dut_executed=False,actual_or_typed_input_read=False,
            materialized_producer_payload_read=False,saved_reference_payload_read=False,
            numerical_acceptance_claimed=False,old_pass_inherited=False,full_official_forward_executed=False,
            dynamic_cache_executed=False,full_29_node_acceptance=False,outputs=copy.deepcopy(self.outputs),
            source_manifest=self.source,resources=resources,
            boundary=dict(unchanged=True,before_sha256=R.sha(R.encoded(boundary)),after_sha256=R.sha(R.encoded(boundary))))
        files={n+'.f32le':{k:s[k] for k in ('bytes','sha256')} for n,s in self.outputs.items()}
        files['mask.bf16le']=dict(bytes=p['mask_contract']['native_bytes'],sha256=p['mask_contract']['native_sha256'])
        files.update({n:dict(bytes=len(R.encoded(boundary)),sha256=R.sha(R.encoded(boundary))) for n in R.METADATA_NAMES})
        seal=dict(schema=1,status='SEALED_BOOTSTRAP_OBSERVATIONS_UNACCEPTED',mode='bootstrap',run_id='ci01',
            manifest=R.REFERENCE_MANIFEST,numerical_acceptance_claimed=False,dut_executed=False,retries=0,
            files=files,source_manifest=self.source,resources=resources)
        return seal,manifest,{n:copy.deepcopy(boundary) for n in R.BOUNDARIES}

    def validate(self,seal,manifest,boundaries,observed=None):
        return R.validate_bootstrap_documents(self.pins,self.outputs,seal,manifest,boundaries,
            reference_source=self.source,bootstrap_closure=self.closure,observed_binding=observed or self.observed,proof_files={})

    def test_private_original_recipe_identity_and_no_global_rebinding(self):
        self.assertEqual(R.sha((R.ROOT/R.CI_SOURCE).read_bytes()),R.CI_SOURCE_SHA)
        self.assertEqual(R.sha((R.ROOT/R.CI_MANIFEST).read_bytes()),R.CI_MANIFEST_SHA)
        self.assertIsNot(sys.modules.get('recipe'),R.C)
        self.assertFalse(any(n.split('.')[0] in ('torch','numpy','transformers') for n in sys.modules))

    def test_dependency_map_is_verified_before_original_import(self):
        original=Path.read_bytes
        def drift(path):
            if path==R.ROOT/'candidates/qwen2_fullblock_ci_reference/dependencies.json':return b'{}'
            return original(path)
        with patch.object(Path,'read_bytes',drift):
            with self.assertRaisesRegex(ValueError,'package dependency identity'):R._load_ci_recipe()

    def test_default_cli_is_cold(self):
        result=subprocess.run([sys.executable,'-B',str(HERE/'recipe.py')],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('NOT_EXECUTED',result.stdout)

    def test_default_binding_is_cold(self):
        with patch.object(R,'load_pins',side_effect=AssertionError('unexpected input read')):
            self.assertEqual(R.bind_bootstrap(seal_sha256='a'*64)['status'],'NOT_EXECUTED')

    def test_expected_source_read_never_opens_historical_work(self):
        original=io.open
        def guard(path,*a,**k):
            if '/work/' in str(path):raise AssertionError('historical work opened')
            return original(path,*a,**k)
        with patch('io.open',side_effect=guard):
            outputs,identity=R.source_expectations(self.pins)
        self.assertEqual(len(outputs),29)
        self.assertEqual(identity['sha256'],R.FROZEN_CONTRACT_SHA256)

    def test_matching_bootstrap_remains_honestly_unaccepted(self):
        seal,manifest,boundaries=self.documents()
        before=copy.deepcopy((seal,manifest,boundaries))
        result=self.validate(seal,manifest,boundaries)
        self.assertEqual(result['status'],R.STATUS)
        self.assertTrue(result['bootstrap_status_preserved'])
        self.assertFalse(result['old_pass_inherited'])
        self.assertEqual((seal,manifest,boundaries),before)

    def test_frozen_or_pass_claim_cannot_be_substituted(self):
        for target,key,value in [('seal','status','SEALED_FRESH_FROZEN_REPRODUCTION_REFERENCE_ONLY'),
            ('manifest','frozen29_hash_matches',True),('manifest','old_pass_inherited',True),
            ('manifest','numerical_acceptance_claimed',True),('manifest','stage','frozen')]:
            seal,manifest,boundaries=self.documents()
            (seal if target=='seal' else manifest)[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.validate(seal,manifest,boundaries)

    def test_all29_outputs_must_exactly_match_source(self):
        seal,manifest,boundaries=self.documents()
        manifest['outputs']['y']['sha256']='e'*64
        with self.assertRaisesRegex(ValueError,'full29 differs'):self.validate(seal,manifest,boundaries)

    def test_boundary_raw_native_source_or_binding_drift_rejected(self):
        for key,value in [('raw13',{}),('native_files',{}),('source_closure_sha256','e'*64),
            ('pins',{'bytes':2,'sha256':'e'*64}),('effective_pins_sha256','e'*64),('historical_receipts_revalidated',True)]:
            seal,manifest,boundaries=self.documents()
            for boundary in boundaries.values():boundary[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.validate(seal,manifest,boundaries)

    def test_before_after_difference_rejected(self):
        seal,manifest,boundaries=self.documents();boundaries['BOUNDARY_AFTER.json']['extra']=True
        with self.assertRaisesRegex(ValueError,'boundary drift'):self.validate(seal,manifest,boundaries)

    def test_missing_or_extra_sealed_files_rejected(self):
        for extra in (False,True):
            seal,manifest,boundaries=self.documents()
            if extra:seal['files']['EXTRA.json']={'bytes':1,'sha256':'a'*64}
            else:del seal['files']['y.f32le']
            with self.assertRaisesRegex(ValueError,'inventory'):self.validate(seal,manifest,boundaries)

    def test_failed_or_unbounded_resources_rejected(self):
        for key,value in [('returncode',1),('returncode',False),('overall_elapsed_seconds',123),
            ('rss_limit_bytes',2**40),('peak_sampled_process_tree_rss_bytes',2**40),
            ('external_watchdog_deadline_seconds',999),('cleanup_pids',[5])]:
            seal,manifest,boundaries=self.documents()
            seal['resources'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.validate(seal,manifest,boundaries)

    def fixture(self,root):
        binding=root/R.C.BINDING;binding.parent.mkdir(parents=True);binding.write_bytes(b'{"synthetic":true}')
        observed=R.identity(binding)
        seal,manifest,boundaries=self.documents(observed)
        out=root/R.REFERENCE;out.mkdir(parents=True)
        go=dict(schema=1,action='single-bootstrap',run_id='ci01',source_manifest=self.source,
            maximum_invocations=1,no_retry=True,exclusive_numeric_slot=True,issued_by='root-source-policy-issuer',
            source_review={'synthetic_fixture_only':True})
        go_record=dict(content=go,receipt=dict(path='work/qwen2_fullblock_ci_reference/ci01/GO.json',
            bytes=len(R.encoded(go)),sha256=R.sha(R.encoded(go))))
        manifest['go_identity']=go_record['receipt']
        docs={**boundaries,R.REFERENCE_MANIFEST:manifest,'GO.json':go_record,
              'OBSERVATIONS.json':{k:v for k,v in manifest.items() if k not in ('resources','wrapper_boundary_unchanged','go_identity')}}
        for name in R.METADATA_NAMES:
            data=R.encoded(docs[name]) if name.endswith('.json') else b'synthetic test only\n'
            (out/name).write_bytes(data);seal['files'][name]=R.identity(out/name)
        for name in set(seal['files'])-set(R.METADATA_NAMES):
            with (out/name).open('wb') as f:f.truncate(seal['files'][name]['bytes'])
        (out/'SEAL.json').write_bytes(R.encoded(seal))
        return R.identity(out/'SEAL.json')['sha256']

    def metadata(self,root,seal):
        original=io.open
        def guard(path,*a,**k):
            if str(path).endswith(('.f32le','.bf16le','.bin')):raise AssertionError('operand opened by metadata gate')
            return original(path,*a,**k)
        with patch.object(R,'ROOT',root),patch.object(R,'load_pins',return_value=self.pins), \
             patch.object(R,'source_check',return_value={'proof_files':{}}), \
             patch.object(R,'source_expectations',return_value=(self.outputs,self.expected_source)), \
             patch.object(R,'reference_source_manifest',return_value=self.source), \
             patch.object(R,'bootstrap_source_closure',return_value=self.closure),patch('io.open',side_effect=guard):
            return R.validate_bootstrap_metadata(self.pins,seal_sha256=seal)

    def test_metadata_never_reads_any_operand(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);seal=self.fixture(root)
            result=self.metadata(root,seal)
            self.assertFalse(result['oracle_payload_read'])
            self.assertEqual(len(result['outputs']),29)

    def test_seal_digest_must_be_explicit_and_exact(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixture(root)
            with self.assertRaisesRegex(ValueError,'bootstrap seal digest'):self.metadata(root,'f'*64)

    def test_sparse_fixture_is_never_a_valid_payload_binding(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);seal=self.fixture(root);metadata=self.metadata(root,seal)
            with patch.object(R,'ROOT',root),patch.object(R.C,'CI_ROOT',root), \
                 patch.object(R,'load_pins',return_value=self.pins),patch.object(R,'execution_context',return_value={}), \
                 patch.object(R,'validate_bootstrap_metadata',return_value=metadata):
                with self.assertRaisesRegex(ValueError,'payload hash'):R.bind_bootstrap(seal_sha256=seal,execute=True)
            self.assertFalse((root/R.FROZEN_BINDING).exists())

    def test_local_binding_requires_launch_pinned_digest(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/R.FROZEN_BINDING;p.parent.mkdir(parents=True);p.write_bytes(b'{}')
            with patch.object(R,'ROOT',root),patch.object(R,'load_pins',return_value=self.pins), \
                 patch.dict(os.environ,{R.BINDING_ENV:'e'*64}):
                with self.assertRaisesRegex(ValueError,'launch-pinned'):R.require_frozen_references(self.pins,root)

    def test_binding_record_has_honest_scope_and_all_current_identities(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);seal=self.fixture(root);record=self.metadata(root,seal)
            context={'synthetic_context_only':True}
            binding=R._binding_record(self.pins,record,context)
            self.assertEqual(binding['context'],context)
            self.assertEqual(len(binding['raw13']),13);self.assertEqual(len(binding['producer14']),14)
            self.assertTrue(binding['bootstrap_status_preserved'])
            self.assertFalse(binding['independent_new_numeric_review_claimed'])
            self.assertFalse(binding['numerical_acceptance_claimed'])
            self.assertNotIn('outputs',binding)

    def test_read13_uses_only_fixed_raw_paths(self):
        p={'raw_tensors':[{'local_name':'synthetic','path':'work/synthetic.bin','bytes':1,'sha256':'a'*64}]}
        with patch.object(R,'load_pins',return_value=p),patch.object(R,'checked',return_value=b'x') as read:
            self.assertEqual(R.read13(pins=p),{'synthetic':b'x'})
        read.assert_called_once_with(R.ROOT,'work/synthetic.bin',p['raw_tensors'][0])

if __name__=='__main__':unittest.main()
