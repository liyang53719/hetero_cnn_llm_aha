"""AVX512 admission/once/seal negatives. Metadata and mocked stages only."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from fixture_gate import FixtureMismatch
import host_checks
import run_portable
import test_controller_mock
import validate_avx512_launch as launch
from safe_export import CANDIDATE_ID, TENSOR_ORDER

class Avx512IdentityTests(unittest.TestCase):
    def test_required_physical_features_each_missing_rejected(self):
        flags=['sse2','avx','avx2','fma','avx512f','avx512dq','avx512bw','avx512vl']
        host_checks.admit_avx512({'flags_intersection':flags})
        for missing in flags:
            with self.subTest(missing=missing), self.assertRaises(FixtureMismatch) as caught:
                host_checks.admit_avx512({'flags_intersection':[x for x in flags if x!=missing]})
            self.assertEqual(caught.exception.reason,'CPU_AVX512')

    def test_cpu_denial_before_runtime_or_weights(self):
        code,calls,files,terminal=test_controller_mock.ControllerMockTests().exercise('cpu_missing')
        self.assertEqual((code,calls),(1,[]))
        self.assertEqual(files['RESULT.json']['reason'],'CPU_AVX512')
        self.assertEqual((files['RESULT.json']['weight_checked'],files['RESULT.json']['tensor_checked']),(0,0))
        self.assertIsNone(files['HOST_RESOURCES.json']['observed_capability'])
        self.assertEqual(terminal['repair_lineage'],{'default_failed_run_id':41734412224})

    def test_no_default_fallback_after_import_probe(self):
        code,calls,files,_=test_controller_mock.ControllerMockTests().exercise('wrong_runtime_capability')
        self.assertEqual((code,calls),(1,['runtime']))
        self.assertEqual(files['RESULT.json']['reason'],'CPU_PROOF')
        self.assertEqual(files['HOST_RESOURCES.json']['requested_capability'],'avx512')
        self.assertEqual(files['HOST_RESOURCES.json']['observed_capability'],'DEFAULT')

    def test_sixteenth_mismatch_remains_fatal(self):
        code,calls,files,_=test_controller_mock.ControllerMockTests().exercise('attention_mismatch')
        r=files['RESULT.json'];self.assertEqual((code,calls),(1,['runtime','weights','reference']))
        self.assertEqual((r['reason'],r['first_mismatch_name'],r['tensor_checked']),('REFERENCE_HASH','stage.self_attn.0.1',16))
        rows={v['name']:v for v in files['CHECKS.json']['checks']}
        self.assertTrue(all(rows[n]['status']=='PASS' for n in TENSOR_ORDER[:15]))
        self.assertTrue(all(rows[n]['status']=='NOT_REACHED' for n in (*TENSOR_ORDER[16:],'rope1024')))

    def test_identity_exact_new_lineage_only(self):
        identity=dict(schema='P0_AVX512_ONE_SHOT_IDENTITY_V1',run_id=123,source_commit='a'*40,launch_commit='b'*40,source_manifest_sha256='c'*64,nonce='d'*32,default_failed_run_id=41734412224)
        start=dict(schema='P0_AVX512_JOB_START_V1',run_id=123,launch_commit='b'*40,started_monotonic=time.monotonic(),job_budget_seconds=3600)
        env=dict(GITHUB_ACTIONS='true',GITHUB_RUN_ATTEMPT='1',RUNNER_ENVIRONMENT='github-hosted',GITHUB_RUN_ID='123',GITHUB_SHA='b'*40)
        with patch.dict(os.environ,env),patch.object(run_portable.subprocess,'check_output',return_value='a'*40+'\n'):
            run_portable.check_identity(identity,start,Path('/unused'))
            for key,value in (('default_failed_run_id',41720209902),('default_failed_run_id',True),('unknown',1),('schema','P0_DEFAULT_REFERENCE_REPAIR_IDENTITY_V1')):
                bad=dict(identity);bad[key]=value
                with self.assertRaises(FixtureMismatch):run_portable.check_identity(bad,start,Path('/unused'))

    def test_new_once_validator_no_old_path_attempt_or_manifest(self):
        raw=b'fixed-source-manifest\n';digest=hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);previous=Path.cwd();os.chdir(root)
            try:
                path=root/launch.LAUNCH;path.parent.mkdir()
                event=root/'event.json';event.write_text(json.dumps(dict(after='b'*40,before='a'*40,forced=False,deleted=False)))
                value=dict(schema='P0_AVX512_ONE_SHOT_V1',source_commit='a'*40,source_manifest_sha256=digest,nonce='c'*32,scope='REFERENCE_ONLY_NO_DUT_NO_EDA_THREE_JSON',default_failed_run_id=41734412224)
                def git(*args):
                    return {'rev-parse':('a'*40+'\n').encode(),'rev-list':b'1\n','diff-tree':('A\t'+launch.LAUNCH+'\n').encode(),'show':raw}[args[0]]
                env=dict(GITHUB_EVENT_NAME='push',GITHUB_REF='refs/heads/main',GITHUB_RUN_ATTEMPT='1',GITHUB_EVENT_PATH=str(event),GITHUB_SHA='b'*40,GITHUB_RUN_ID='123',RUNNER_TEMP=str(root),GITHUB_OUTPUT=str(root/'github_output'))
                with patch.dict(os.environ,env),patch.object(launch,'git',side_effect=git):
                    for bad in (dict(value,default_failed_run_id=41720209902),dict(value,default_failed_run_id=True),dict(value,source_manifest_sha256='0'*64),dict(value,unknown=1),dict(value,schema='P0_DEFAULT_REFERENCE_REPAIR_ONE_SHOT_V1')):
                        path.write_text(json.dumps(bad))
                        with self.assertRaises(FixtureMismatch):launch.main()
                    path.write_text(json.dumps(value));launch.main()
                    observed=json.loads((root/'p0-avx512-identity.json').read_text())
                    self.assertEqual(observed['schema'],'P0_AVX512_ONE_SHOT_IDENTITY_V1')
                    self.assertEqual(observed['default_failed_run_id'],41734412224)
                    with patch.dict(os.environ,{'GITHUB_RUN_ATTEMPT':'2'}):
                        with self.assertRaises(FixtureMismatch):launch.main()
            finally:os.chdir(previous)

    def test_unchanged_fixture_and_new_explicit_contract(self):
        here=Path(__file__).resolve().parent
        self.assertEqual(hashlib.sha256((here/'FROZEN_P0.json').read_bytes()).hexdigest(),'e93e1a8ff6e54f7f82ddd3d0134785350a09726e257c2cb73b6823625fa09c76')
        self.assertEqual(CANDIDATE_ID,'P0_QWEN2_FULL128_ORIGINAL_AVX512_REFERENCE_V1')
        self.assertEqual(launch.LAUNCH,'ci_launch/p0_original_avx512_reference_20261103_once.json')
        for file in ('run_reference.py','generate_p0_rope.py','prepare_runtime.py'):
            text=(here/file).read_text();self.assertNotIn("execution_identity",text)
            self.assertIn('AVX512',text);self.assertIn('avx512',text)

if __name__=='__main__':unittest.main()
