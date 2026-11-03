"""Narrow repair identity and actual controller mock checks; no network/numerics."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from fixture_gate import FixtureMismatch
import run_portable
from safe_export import REPAIR_CANDIDATE_ID, REASONS
import test_controller_mock
import validate_reference_repair_launch as launch


class ReferenceRepairTests(unittest.TestCase):
    def test_full_repair_reaches_both_forwards_gate_and_rope(self):
        result,calls,files,terminal=test_controller_mock.ControllerMockTests().exercise('success',repair=True)
        self.assertEqual(result,0);self.assertEqual(calls,['runtime','weights','reference','rope','finalize'])
        self.assertEqual(files['RESULT.json']['candidate_id'],REPAIR_CANDIDATE_ID)
        self.assertEqual(terminal['repair_lineage'],dict(failed_run_id=41720209902,header_proof_run_id=41732318207))

    def test_weight_code_stops_before_reference_and_is_exported(self):
        result,calls,files,terminal=test_controller_mock.ControllerMockTests().exercise('weight_http_failure',repair=True)
        self.assertEqual(result,1);self.assertEqual(calls,['runtime','weights'])
        self.assertEqual(files['RESULT.json']['reason'],'WEIGHT_HTTP403');self.assertEqual(files['RESULT.json']['weight_checked'],0)
        self.assertEqual(files['RESULT.json']['tensor_checked'],0)

    def test_repair_identity_rejects_wrong_lineage_and_unknown_fields(self):
        identity=dict(schema='P0_DEFAULT_REFERENCE_REPAIR_IDENTITY_V1',run_id=123,source_commit='a'*40,launch_commit='b'*40,source_manifest_sha256='c'*64,nonce='d'*32,failed_run_id=41720209902,header_proof_run_id=41732318207)
        start=dict(schema='P0_DEFAULT_JOB_START_V1',run_id=123,launch_commit='b'*40,started_monotonic=time.monotonic(),job_budget_seconds=3600)
        env=dict(GITHUB_ACTIONS='true',GITHUB_RUN_ATTEMPT='1',RUNNER_ENVIRONMENT='github-hosted',GITHUB_RUN_ID='123',GITHUB_SHA='b'*40)
        with patch.dict(os.environ,env),patch.object(run_portable.subprocess,'check_output',return_value='a'*40+'\n'):
            run_portable.check_identity(identity,start,Path('/unused'))
            for key,value in (('failed_run_id',41720209903),('header_proof_run_id',41732318208),('failed_run_id',True),('unknown',1)):
                bad=dict(identity);bad[key]=value
                with self.assertRaises(FixtureMismatch):run_portable.check_identity(bad,start,Path('/unused'))

    def test_real_new_validator_with_mocked_git_rejects_old_nonce_or_wrong_proof(self):
        raw=b'fixed-source-manifest\n';digest=hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);previous=Path.cwd();os.chdir(root)
            try:
                path=root/launch.LAUNCH;path.parent.mkdir()
                event=root/'event.json';event.write_text(json.dumps(dict(after='b'*40,before='a'*40,forced=False,deleted=False)))
                value=dict(schema='P0_DEFAULT_REFERENCE_REPAIR_ONE_SHOT_V1',source_commit='a'*40,source_manifest_sha256=digest,nonce='c'*32,scope='REFERENCE_ONLY_NO_DUT_NO_EDA_THREE_JSON',failed_run_id=41720209902,header_proof_run_id=41732318207)
                def git(*args):
                    return {'rev-parse':('a'*40+'\n').encode(),'rev-list':b'1\n','diff-tree':('A\t'+launch.LAUNCH+'\n').encode(),'show':raw}[args[0]]
                env=dict(GITHUB_EVENT_NAME='push',GITHUB_REF='refs/heads/main',GITHUB_RUN_ATTEMPT='1',GITHUB_EVENT_PATH=str(event),GITHUB_SHA='b'*40,GITHUB_RUN_ID='123',RUNNER_TEMP=str(root),GITHUB_OUTPUT=str(root/'github_output'))
                with patch.dict(os.environ,env),patch.object(launch,'git',side_effect=git):
                    for bad in (dict(value,header_proof_run_id=41732318208),dict(value,failed_run_id=True),dict(value,source_manifest_sha256='0'*64),dict(value,unknown=1)):
                        path.write_text(json.dumps(bad))
                        with self.assertRaises(FixtureMismatch):launch.main()
                    path.write_text(json.dumps(value));launch.main()
                    observed=json.loads((root/'p0-reference-repair-identity.json').read_text())
                    self.assertEqual(observed['schema'],'P0_DEFAULT_REFERENCE_REPAIR_IDENTITY_V1')
                    self.assertEqual(observed['header_proof_run_id'],41732318207)
                    with patch.dict(os.environ,{'GITHUB_RUN_ATTEMPT':'2'}):
                        with self.assertRaises(FixtureMismatch):launch.main()
            finally:os.chdir(previous)

    def test_fresh_once_identity_has_no_old_nonce_path(self):
        self.assertEqual(launch.LAUNCH,'ci_launch/p0_portable_reference_repair_41720209902_once.json')
        self.assertEqual((launch.FAILED_RUN,launch.HEADER_PROOF_RUN),(41720209902,41732318207))
        self.assertIn('WEIGHT_HTTP403',REASONS);self.assertIn('WEIGHT_HEADER_HASH',REASONS)

if __name__=='__main__':unittest.main()
