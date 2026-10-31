"""Synthetic identity checks only; no actual execution identity is generated."""
import copy
import math
import pathlib
import unittest
from unittest.mock import patch
import executor_identity as e

class Tests(unittest.TestCase):
    def fixture(self):
        return dict(schema='CLOUD_EXECUTOR_IDENTITY_V1',source_commit='a'*40,execution_id='11111111-2222-4333-8444-555555555555',boot_id='aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',controller_pid=123,start_tick=456,host_identity_sha256='b'*64,started_monotonic=10.5)
    def stat(self):
        return '123 (a name ) inner) '+' '.join(['S']+['0']*18+['456'])
    def read(self,p):
        if str(p)=='/proc/123/stat':return self.stat()
        if str(p)=='/proc/sys/kernel/random/boot_id':return self.fixture()['boot_id']+'\n'
        raise AssertionError('unexpected path')
    def current(self,v):
        with patch.object(e.os,'getpid',return_value=123),patch.object(e.pathlib.Path,'read_text',lambda p:self.read(p)),patch.object(e.time,'monotonic',return_value=20):return e.verify_current(v)
    def test_valid_copy(self):
        v=self.fixture();r=e.validate(v);self.assertEqual(r,v);self.assertIsNot(r,v)
    def test_current(self):self.assertEqual(self.current(self.fixture()),self.fixture())
    def test_exact_keys_no_builder_or_pass(self):
        for k in ('run_id','launch_commit','builder_identity','numerical_pass'):
            v=self.fixture();v[k]=True
            with self.assertRaises(ValueError):e.validate(v)
        for k in e.FIELDS:
            v=self.fixture();del v[k]
            with self.assertRaises(ValueError):e.validate(v)
    def test_numeric_bounds(self):
        for k in ('controller_pid','start_tick'):
            for value in (True,0,-1,1.0,2**63,'123'):
                v=self.fixture();v[k]=value
                with self.assertRaises(ValueError):e.validate(v)
        for value in (True,-1,float('inf'),float('nan'),2**63,'0'):
            v=self.fixture();v['started_monotonic']=value
            with self.assertRaises(ValueError):e.validate(v)
    def test_hashes_uuid(self):
        for k in ('source_commit','host_identity_sha256','execution_id','boot_id'):
            for value in ('',None,'Z'*40,'00000000-0000-0000-0000-000000000000'):
                v=self.fixture();v[k]=value
                with self.assertRaises(ValueError):e.validate(v)
    def test_other_process_boot_start_future(self):
        for k,value in [('controller_pid',124),('start_tick',457),('boot_id','11111111-2222-4333-8444-555555555555'),('started_monotonic',21)]:
            v=self.fixture();v[k]=value
            with self.assertRaises(ValueError):self.current(v)
    def test_worker_can_verify_live_original_owner(self):
        with patch.object(e.os,'getpid',return_value=999),patch.object(e.pathlib.Path,'read_text',lambda p:self.read(p)),patch.object(e.time,'monotonic',return_value=20):
            self.assertEqual(e.verify_owner(self.fixture()),self.fixture())
            with self.assertRaises(ValueError):e.verify_current(self.fixture())
    def test_dead_or_reused_owner_refused(self):
        for state in ('Z','X','x'):
            with patch.object(e.pathlib.Path,'read_text',return_value=self.stat().replace(' S ',' '+state+' ')):
                with self.assertRaises(ValueError):e.verify_owner(self.fixture())
        with patch.object(e.pathlib.Path,'read_text',side_effect=FileNotFoundError):
            with self.assertRaises(FileNotFoundError):e.verify_owner(self.fixture())
        with patch.object(e.pathlib.Path,'read_text',return_value=self.stat().replace('456','457')):
            with self.assertRaises(ValueError):e.verify_owner(self.fixture())
    def test_no_github_environment_read(self):
        with patch.dict(e.os.environ,{'GITHUB_RUN_ID':'fake','GITHUB_SHA':'fake'},clear=True):self.current(self.fixture())
if __name__=='__main__':unittest.main()
