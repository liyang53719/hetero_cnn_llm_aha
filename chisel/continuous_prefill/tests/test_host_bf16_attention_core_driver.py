"""Small source/contract/adversarial tests, not a fake numerical DUT run."""
from pathlib import Path
import json
import sys
import tempfile
import unittest

CANDIDATE=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(CANDIDATE/'chisel/continuous_prefill/scripts'))
import host_bf16_attention_core_fixture as fixture
import host_bf16_attention_core_execution as execution
from host_bf16_attention_core_descriptor import validate_carried_attention_commands

class LayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.layout,cls.pairs=fixture.build_layout()
    def test_real_stream_geometry_and_carried_state(self):
        current=validate_carried_attention_commands(*self.pairs[0],*self.pairs[1])
        self.assertEqual((current.token_base,current.token_count,current.expected_length,current.expected_generation,current.query_start),(1,1,1,1,1))
        self.assertFalse(current.cold)
        for commands,records in self.pairs:self.assertEqual((len(commands),len(records)),(12,172))
        self.assertEqual(sum(fixture.RECORDS),172)
    def test_shared_actual_cache_and_parameters_only(self):
        a,b=self.layout['launches'];h=self.layout['header']
        self.assertGreater(h['base'],2**32);self.assertLessEqual(h['limit'],2**56)
        self.assertLess(h['limit']-h['base'],64*1024*1024)
        for index in (0,1,2,3,4):self.assertEqual(a['commands'][index]['constant'],b['commands'][index]['constant'])
        self.assertEqual(b['commands'][5]['constant']-a['commands'][5]['constant'],128)
        for index in (8,9):self.assertEqual(b['spans'][index]['begin']-a['spans'][index]['begin'],1024)
        self.assertEqual(a['spans'][9]['begin']-a['spans'][8]['begin'],256*1024)
        for old in a['spans']:
            for new in b['spans']:
                self.assertFalse(old['begin']<new['begin']+new['bytes'] and new['begin']<old['begin']+old['bytes'])
    def test_no_reference_output_cache_or_scratch_preloads(self):
        h=self.layout['header'];self.assertEqual(len(self.layout['preloads']),11)
        for preload in self.layout['preloads']:
            self.assertTrue(fixture.inside(preload['address'],preload['bytes'],h['base'],h['scratch']-h['base']))
            self.assertNotIn('expected',preload['file'])
        for launch in self.layout['launches']:
            self.assertEqual(sum(s['bytes'] for s in launch['spans']),30720)
            self.assertEqual(sum(s['bytes'] for s in launch['spans'] if s['pc']==10),4096)
            self.assertEqual(launch['commands'][8]['input_bytes'],0)
            self.assertEqual(launch['commands'][9]['input_bytes'],0)
            self.assertEqual(launch['commands'][11]['input_bytes'],0)
    def test_preserved_two_launch_protocol_not_carried127(self):
        text=fixture.layout_text(self.layout).decode()
        self.assertTrue(text.startswith(fixture.SCHEMA+'\n'))
        self.assertEqual([l['first'] for l in self.layout['launches']],[0,1])
        self.assertEqual([l['position'] for l in self.layout['launches']],[0,1])
        self.assertEqual([l['old_generation'] for l in self.layout['launches']],[0,1])
        self.assertEqual([l['count'] for l in self.layout['launches']],[1,1])

class EvidenceTests(unittest.TestCase):
    def test_rejects_empty_unknown_duplicate_missing_and_negative_events(self):
        bad=['','HOST_ATTN_PASS numerical=1','HOST_ATTN_FAIL: broken',
             'HOST_ATTN_READ run=0 pc=0 cycle=1 address=64 bytes=64 bytes=64',
             'HOST_ATTN_READ run=0 pc=0 cycle=1 address=64',
             'HOST_ATTN_READ run=0 pc=0 cycle=-1 address=64 bytes=64']
        for text in bad:
            with self.subTest(text=text),self.assertRaises(ValueError):execution.parse_events(text)
    def test_failed_ack_retains_physical_staging_and_old_prefix(self):
        # Tiny transaction model tests the auditor only, never emits a run log.
        mem=bytearray(b'P'*64+b'S'*128);span={'begin':0x1040,'bytes':128};ref=b'A'*64+b'B'*64
        execution.apply_ack(mem,0x1000,span,ref,0x1040,64,0,1)
        execution.apply_ack(mem,0x1000,span,ref,0x1080,64,1,1)
        self.assertEqual(mem,b'P'*64+b'A'*64+b'B'*64)
        with self.assertRaises(ValueError):execution.apply_ack(mem,0x1000,span,ref,0x1000,64,0,1)
    def test_fused_execution_pc_is_not_completion_pc(self):
        self.assertTrue(execution.allowed_owner_pc(8,10))
        for pair in ((8,8),(8,9),(9,10),(10,10),(11,11),(7,10),(3,4)):
            self.assertFalse(execution.allowed_owner_pc(*pair))
    def test_path_escape_and_symlinks_rejected(self):
        with tempfile.TemporaryDirectory(dir=CANDIDATE) as tmp:
            p=Path(tmp);(p/'a').write_bytes(b'a');(p/'alias').symlink_to(p/'a')
            with self.assertRaises(ValueError):fixture.safe_file(p,'../outside')
            with self.assertRaises(ValueError):fixture.safe_file(p,'alias')
            with self.assertRaises(ValueError):fixture.checked(p,'a',dict(bytes=1,sha256='0'*64))
            self.assertEqual(fixture.checked(p,'a',dict(bytes=1,sha256=fixture.sha(b'a'))),b'a')
    def test_reference_source_windows_and_fma_witness_contract(self):
        # Receipt-field validation only; these placeholders are never fixture
        # files, independent authority, arithmetic evidence, or DUT output.
        receipt=dict(status='PREPARED_ADJACENT_ATTENTION_CORE_EXPECTED_ONLY',expected_only=True,
            actual_cache_execution=False,intermediate_preload_allowed=False,input_injection=False,
            official_manifest_sha256='a'*64,original_operator_gate_pass=False,original_operator_criteria={},
            native_full_block_failures={},inputs={},expected={'cold0':{},'carried1':{}},cases={})
        for token,phase in enumerate(fixture.PHASES):
            receipt['cases'][phase]=dict(source_phase='cold',source_token=token,absolute_position=token,
                host_cold=token==0,host_expected_length=token,host_expected_generation=token,
                numerical_rtl_executed=False,projection_reference={'test_only':True},norm_rope_reference={'test_only':True},
                matrix_reference=dict(status='PASS_INTEGER_C_EVERY_QK_PV_FMA',fmas=4096*(token+1),bit_mismatches=0,flag_mismatches=0))
        self.assertEqual(fixture.reference_inventory(receipt),{})
        for key,value in [('source_phase','carried'),('source_token',127),('absolute_position',255),('host_expected_generation',0)]:
            bad=json.loads(json.dumps(receipt));bad['cases']['carried1'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):fixture.reference_inventory(bad)
        bad=json.loads(json.dumps(receipt));bad['cases']['carried1']['matrix_reference']['flag_mismatches']=1
        with self.assertRaises(ValueError):fixture.reference_inventory(bad)
    def test_reference_receipt_cannot_be_missing_or_claim_executed_cache(self):
        with self.assertRaises(ValueError):fixture.reference_inventory({})
        with self.assertRaises(ValueError):fixture.reference_inventory(dict(status='PREPARED_ADJACENT_ATTENTION_CORE_EXPECTED_ONLY',expected_only=True,actual_cache_execution=True))
    def test_artifact_audit_never_issues_numerical_acceptance(self):
        source=(CANDIDATE/'chisel/continuous_prefill/scripts/host_bf16_attention_core_execution.py').read_text()
        self.assertIn("status='CONSISTENT_ATTENTION_CORE_ARTIFACTS_ONLY'",source)
        self.assertIn('actual_dut_identity_verified=False',source)
        self.assertIn('numerical_acceptance_eligible=False',source)
        self.assertNotIn('numerical_acceptance_eligible=True',source)

if __name__=='__main__':unittest.main()
