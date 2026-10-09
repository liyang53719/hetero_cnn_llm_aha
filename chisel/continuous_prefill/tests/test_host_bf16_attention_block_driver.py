"""Focused descriptor/layout/auditor controls; no fabricated DUT execution."""
from pathlib import Path
import copy
import json
import re
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parents[1]/'scripts'
CPP_PATH=Path(__file__).with_name('host_bf16_attention_block.cpp')
sys.path.insert(0,str(HERE))
import host_bf16_attention_block_fixture as fixture
import host_bf16_attention_block_execution as execution
from host_bf16_attention_block_descriptor import validate_carried_attention_block_commands


class LayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.layout,cls.pairs=fixture.build_layout()

    def test_real_public_stream_geometry_and_carried_state(self):
        p,n,r,core,block=validate_carried_attention_block_commands(*self.pairs[0],*self.pairs[1])
        self.assertEqual((core.rows,core.token_base,core.token_count,core.expected_length,core.expected_generation,core.query_start),(1,0,1,1,1,1))
        self.assertFalse(core.cold)
        for commands,records in self.pairs:self.assertEqual((len(commands),len(records)),(22,296))
        self.assertEqual(sum(fixture.RECORDS),296)
        self.assertEqual((fixture.COMMAND_BYTES,fixture.DESCRIPTOR_BYTES),(384,4736))

    def test_descriptor_tables_cannot_retain_old_stride(self):
        first,second=self.layout['launches']
        self.assertLess(first['dl'],second['cb'])
        self.assertGreater(first['dl']-first['db'],4096)
        bad=copy.deepcopy(self.layout)
        for p in bad['preloads']:
            if p['file']=='carried1_commands.bin':p['address']=bad['header']['base']+8192
        with self.assertRaisesRegex(ValueError,'overlap'):fixture.validate_physical_layout(bad)

    def test_exact_existing_ddr_capacity_and_receipts(self):
        h=self.layout['header']
        self.assertEqual(h['limit']-h['base'],37670144)
        self.assertLess(h['limit']-h['base'],64*1024*1024)
        self.assertEqual(sum(fixture.INPUTS.values()),36742144)
        self.assertEqual((fixture.ACK_BYTES,fixture.DENSE_MACS,fixture.OWNER_JOBS),(68608,18350080,19))
        self.assertTrue(fixture.validate_physical_layout(self.layout))

    def test_metadata_input_output_overlap_rejected(self):
        for target in ('input','output','old_final','internal'):
            bad=copy.deepcopy(self.layout);h=bad['header'];a,b=bad['launches']
            if target=='input':bad['preloads'][-1]['address']=h['scratch']
            elif target=='output':a['spans'][0]['allocation']=a['spans'][0]['begin']=h['meta']
            elif target=='old_final':b['spans'][-1]['allocation']=b['spans'][-1]['begin']=a['spans'][-1]['begin']
            else:a['internal'][0]['address']=a['spans'][0]['begin']
            with self.subTest(target=target),self.assertRaises(ValueError):fixture.validate_physical_layout(bad)

    def test_only_raw_hidden_weights_and_shared_trig_preload(self):
        files={p['file'] for p in self.layout['preloads']}
        self.assertEqual(files,{*('input/'+n for n in fixture.INPUTS),*(p+'_'+k+'.bin' for p in fixture.PHASES for k in ('commands','descriptors'))})
        self.assertEqual(len(files),18)
        self.assertEqual(sum(n.startswith('weight_') for n in fixture.INPUTS),11)
        self.assertFalse(any('activation' in n or 'expected' in n or 'cache' in n for n in files))
        a,b=self.layout['launches']
        for pc in (0,1,2,3,4,5,13,15,16,17,19):self.assertEqual(a['commands'][pc]['constant'],b['commands'][pc]['constant'])
        self.assertEqual(b['commands'][6]['constant']-a['commands'][6]['constant'],128)

    def test_complete_m1_allocations_and_active_cache_slices(self):
        a,b=self.layout['launches'];h=self.layout['header']
        for launch in (a,b):
            self.assertEqual((launch['rows'],launch['first'],launch['count']),(1,0,1))
            self.assertEqual(sum(s['bytes'] for s in launch['spans']),68608)
            for s in launch['spans']:
                if s['name'].startswith('cache_'):self.assertEqual((s['allocation'],s['allocation_bytes']),(h['cache'],256*2048))
                else:self.assertEqual((s['allocation'],s['allocation_bytes']),(s['begin'],s['bytes']))
            for pc in (9,10,21):self.assertEqual(launch['commands'][pc]['input_bytes'],0)
        for index in (9,10):self.assertEqual(b['spans'][index]['begin']-a['spans'][index]['begin'],1024)
        self.assertEqual([x['source_token'] for x in (a,b)],[0,1])
        self.assertEqual([x['position'] for x in (a,b)],[0,1])

    def test_every_actual_producer_feeds_next_consumers(self):
        for l in self.layout['launches']:
            spans={s['name']:s for s in l['spans']};cs=l['commands']
            for pc in (1,2,3):self.assertEqual(cs[pc]['input'],spans['input_norm']['begin'])
            for pc,name in ((4,'q'),(5,'k'),(6,'norm_q'),(7,'norm_k'),(8,'rope_k'),(11,'rope_q'),
                            (12,'gate'),(13,'sigmoid_mul'),(15,'residual1'),(16,'post_norm'),
                            (17,'post_norm'),(18,'ffn_gate'),(19,'silu_mul'),(20,'residual1')):
                self.assertEqual(cs[pc]['input'],spans[name]['begin'])
            for pc,name in ((8,'v'),(12,'context'),(14,'o'),(18,'ffn_up'),(20,'down')):
                self.assertEqual(cs[pc]['constant'],spans[name]['begin'])
            self.assertEqual(cs[0]['input'],cs[14]['input'])

    def test_cpp_public_wire_inventory_matches_python_builder(self):
        # This detects divergent hand-maintained parsers without compiling any
        # RTL/C++ or substituting a mock VHostBlockTop.
        source=CPP_PATH.read_text()
        for name,wanted in (('records',fixture.RECORDS),('engines',fixture.ENGINES),
                            ('pcs',fixture.PCS),('widths',fixture.WIDTHS)):
            match=re.search(r'\b'+name+r'=\{([0-9,]+)\}',source)
            self.assertIsNotNone(match,name)
            self.assertEqual(tuple(map(int,match.group(1).split(','))),wanted)
        self.assertEqual(int(re.search(r'ACK_BYTES=(\d+)',source).group(1)),fixture.ACK_BYTES)
        self.assertIn('#include "VHostBlockTop.h"',source)
        self.assertIn('#include "host_physical_axi.h"',source)


class EvidenceTests(unittest.TestCase):
    def test_strict_trace_field_parser(self):
        bad=['','HOST_ATTN_BLOCK_PASS numerical=1','HOST_ATTN_BLOCK_FAIL: broken',
             'HOST_ATTN_BLOCK_READ run=0 pc=0 cycle=1 address=64 bytes=64 bytes=64',
             'HOST_ATTN_BLOCK_READ run=0 pc=0 cycle=1 address=64',
             'HOST_ATTN_BLOCK_READ run=0 pc=0 cycle=-1 address=64 bytes=64']
        for value in bad:
            with self.subTest(value=value),self.assertRaises(ValueError):execution.parse_events(value)

    def test_failed_ack_writes_staging_but_preserves_old_prefix_and_output(self):
        # In-memory audit-image unit test only. No trace or DUT evidence emitted.
        memory=bytearray(b'K'*64+b'F'*64+b'S'*128+b'G'*64)
        span=dict(begin=0x1080,bytes=128);reference=b'A'*64+b'B'*64
        execution.apply_ack(memory,0x1000,span,reference,0x1080,64,0,1)
        execution.apply_ack(memory,0x1000,span,reference,0x10c0,64,1,1)
        self.assertEqual(memory,b'K'*64+b'F'*64+b'A'*64+b'B'*64+b'G'*64)
        with self.assertRaises(ValueError):execution.apply_ack(memory,0x1000,span,reference,0x1040,64,1,1)

    def test_fused_physical_owner_and_later_ffn_progression(self):
        self.assertTrue(execution.allowed_owner_pc(9,11))
        for pc in (*range(9),*range(12,21)):self.assertTrue(execution.allowed_owner_pc(pc,pc))
        for pair in ((9,9),(9,10),(10,11),(11,11),(21,21),(8,11),(12,11),(20,19)):
            self.assertFalse(execution.allowed_owner_pc(*pair))

    def test_fault_is_after_entire_core_and_ffn(self):
        self.assertEqual(execution.completion_plan(False),list(range(22)))
        self.assertEqual(execution.completion_plan(True),list(range(21)))
        self.assertEqual(execution.MODES,('pass','final-residual-ack-error'))

    def test_publication_needs_final_residual_ack_and_final_fence(self):
        layout,_=fixture.build_layout();l=layout['launches'][1]
        acked=[sum(s['bytes'] for s in l['spans'] if s['pc']==pc) for pc in range(22)]
        self.assertEqual(execution.accept_final_fence(set(range(22)),acked,l['spans'],failing=False),l['spans'][-1]['begin'])
        for failing,published,counts in ((True,set(range(22)),acked),(False,set(range(21)),acked),
                (False,set(range(22)),acked[:20]+[acked[20]-64,0])):
            with self.subTest(failing=failing,published=len(published)),self.assertRaises(ValueError):
                execution.accept_final_fence(published,counts,l['spans'],failing=failing)

    def test_missing_or_core_only_authority_rejected(self):
        for receipt in ({},dict(status='PREPARED_ADJACENT_ATTENTION_CORE_EXPECTED_ONLY'),
                        dict(status='PREPARED_FULL_BLOCK_EXPECTED_ONLY_NOT_NATIVE_PASS',expected_only=True,actual_cache_execution=True)):
            with self.assertRaises(ValueError):fixture.reference_inventory(receipt)

    def test_path_escape_symlink_and_hash_rejected(self):
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            p=Path(tmp);(p/'a').write_bytes(b'a');(p/'alias').symlink_to(p/'a')
            with self.assertRaises(ValueError):fixture.safe_file(p,'../outside')
            with self.assertRaises(ValueError):fixture.safe_file(p,'alias')
            with self.assertRaises(ValueError):fixture.checked(p,'a',dict(bytes=1,sha256='0'*64))

    def test_artifact_auditor_cannot_issue_numerical_acceptance(self):
        source=(HERE/'host_bf16_attention_block_execution.py').read_text()
        self.assertIn("status='CONSISTENT_ATTENTION_BLOCK_ARTIFACTS_ONLY'",source)
        self.assertIn('actual_dut_identity_verified=False',source)
        self.assertNotIn('numerical_acceptance_eligible=True',source)
        self.assertNotIn('native_full_block_accepted=True',source)


if __name__=='__main__':unittest.main()
