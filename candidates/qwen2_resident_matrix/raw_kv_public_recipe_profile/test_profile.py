"""Cold source-contract checks; no numerical imports or execution."""
import json
import unittest
from unittest.mock import patch
from . import profile


class ProfileTests(unittest.TestCase):
    def test_real_source_snapshot_is_preparation_only(self):
        value=profile.snapshot()
        self.assertEqual(value['status'],profile.STATUS)
        for field in ('numerical_execution_enabled','setup_overlay_implemented','asset_overlay_implemented',
                      'actual_chain_executed','full_29_node_acceptance'):
            self.assertIs(value[field],False)
        self.assertIn(profile.PUBLIC_CONTRACT,value['source_sha256'])
        self.assertIn(profile.native.GATE,value['source_sha256'])
        self.assertIn(profile.PINS,value['source_sha256'])

    def test_canonical_profile_and_budget_scope_rejects_changes(self):
        original=profile.native.read_source
        for key,value in (('schema',True),('rows',16),('past_tokens',True),('profile','legacy'),
                          ('work_budget_seconds',1800),('numerical_execution_enabled',True),
                          ('native_contract_sha256','0'*64),('public_contract_sha256','0'*64)):
            data=json.loads(original(profile.PINS));data[key]=value
            def read(name,*args):return json.dumps(data).encode() if name==profile.PINS else original(name,*args)
            with self.subTest(key=key),patch.object(profile.native,'read_source',side_effect=read),self.assertRaises(ValueError):
                profile.snapshot()

    def test_source_inventory_missing_extra_and_identity_drift_reject(self):
        original=profile.native.read_source
        for case in ('missing','extra','changed'):
            data=json.loads(original(profile.PINS));sources=data['source_sha256'];name=profile.PREFIX+'dispatch.py'
            if case=='missing':sources.pop(name)
            elif case=='extra':sources[profile.PREFIX+'extra.py']='0'*64
            else:sources[name]='0'*64
            def read(path,*args):return json.dumps(data).encode() if path==profile.PINS else original(path,*args)
            with self.subTest(case=case),patch.object(profile.native,'read_source',side_effect=read),self.assertRaises(ValueError):
                profile.snapshot()

    def test_own_source_bytes_and_loaded_identity_remain_bound(self):
        original=profile.native.read_source
        target=profile.PREFIX+'dispatch.py'
        def read(path,*args):return original(path,*args)+b'\n# drift\n' if path==target else original(path,*args)
        with patch.object(profile.native,'read_source',side_effect=read),self.assertRaises(ValueError):profile.snapshot()
        with patch.object(profile,'IMPORTED_SHA256','0'*64),self.assertRaises(ValueError):profile.snapshot()

    def test_no_ready_evidence_or_flag_can_authorize_execution(self):
        for args in ((),({'status':'PASS_NATIVE_QKV_QK_M16_M128'},)):
            with self.assertRaises(ValueError):profile.authorize_run(*args,enable_raw_kv=True)

if __name__=='__main__':unittest.main()
