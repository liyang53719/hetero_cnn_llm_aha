import copy
import importlib.util
import io
import hashlib
import json
import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

p=Path(__file__).resolve().parents[1]/'strict_reader.py'
s=importlib.util.spec_from_file_location('independent_strict_reader',p)
v=importlib.util.module_from_spec(s);s.loader.exec_module(v)


class StrictReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module,cls.namespace,cls.pins=v.load_contract()
        # Synthetic metadata only. No historical receipt is copied or recreated.
        # Public source pins supply tensor names/ranges/hashes; these timestamps
        # are synthetic and are never reported as HTTP acquisition evidence.
        reused=[]
        for tensor in cls.pins['tensors'][:2]:
            name=tensor['local_name']+'.bin'
            reused.append(dict(role=tensor['role'],file=name,bytes=tensor['bytes'],sha256=tensor['sha256'],
                provenance='hash_verified_local_copy_from_incomplete_attempt',source_file=name,
                source_directory=v.REUSE_SOURCE,http_receipts_available=False,http_acquired_at=None,
                copied_at='2026-10-15T00:27:55Z'))
        cls.state=dict(created_at='2026-10-15T00:27:56Z',reused=reused)
        tensors=[]
        for tensor in cls.pins['tensors']:
            if tensor['role'] in ('wo','gamma1'):
                provenance=copy.deepcopy(next(x for x in reused if x['role']==tensor['role']));receipts=[]
            else:
                provenance=dict(provenance='fresh_HTTP206',http_receipts_available=True);receipts=[]
                for segment in tensor['segments']:
                    receipts.append(dict(requested_url=cls.pins['shard']['url'],
                        request_range=f"bytes={segment['start']}-{segment['end']}",status=206,
                        content_range=f"bytes {segment['start']}-{segment['end']}/{cls.pins['shard']['checkpoint_file_bytes']}",
                        bytes=segment['bytes'],sha256=segment['sha256'],acquired_at='2026-10-15T00:30:41Z'))
            tensors.append({**tensor,'file':tensor['local_name']+'.bin','provenance':provenance,'http_ranges':receipts})
        cls.ready=dict(completed_at='2026-10-15T00:30:49Z',payload_bytes=87297024,
            verified_segment_hashes=14,fresh_http206_receipts=12,reused_tensors_without_http_receipts=2,tensors=tensors)
        cls.inputs=dict(created_at='2026-10-15T00:33:39Z',
            raw_provenance=dict(fresh_http206_receipts=12,reused_tensors_without_http_receipts=2))

    def validate(self,state=None,ready=None,inputs=None):
        return v.validate_provenance(state or self.state,ready or self.ready,self.pins,inputs or self.inputs)

    def test_synthetic_record_coverage(self):
        result=self.validate()
        self.assertEqual(result['reused_records_verified'],2)
        self.assertEqual(result['fresh_http206_receipts'],12)
        self.assertTrue(result['time_chain_verified'])

    def test_pure_validator_forbids_all_file_access(self):
        with patch('builtins.open',side_effect=AssertionError('file access')),\
             patch('io.open',side_effect=AssertionError('file access')):
            self.validate()

    def test_metadata_gate_forbids_payload_and_full_readers(self):
        real_open=io.open
        def guard(file,*args,**kwargs):
            value=str(file)
            if '/work/' in value and value.endswith('.bin'):raise AssertionError('tensor payload access')
            if args and any(c in args[0] for c in 'wax+'):raise AssertionError('write')
            return real_open(file,*args,**kwargs)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);hashes={}
            for relative,value in ((v.RAW+'/RECOVERY_STATE.json',self.state),
                                   (v.RAW+'/RAW_READY.json',self.ready),
                                   (v.INPUTS+'/INPUTS_READY.json',self.inputs)):
                path=root/relative;path.parent.mkdir(parents=True,exist_ok=True)
                data=(json.dumps(value,sort_keys=True)+'\n').encode();path.write_bytes(data)
                hashes[relative]=hashlib.sha256(data).hexdigest()
            # These hashes and files are explicitly synthetic, temporary test
            # inputs; the actual recovery JSON and its fixed hashes are untouched.
            with patch.object(v,'ROOT',root),patch.object(v,'METADATA_SHA256',hashes),\
                 patch.object(v,'load_contract',return_value=(self.module,self.namespace,self.pins)),\
                 patch.object(self.module,'read_inputs',side_effect=AssertionError('full reader')),\
                 patch.object(self.module,'snapshot',side_effect=AssertionError('full snapshot')),\
                 patch.object(self.module.r,'verify_all',side_effect=AssertionError('full raw verification')),\
                 patch.object(self.module.r,'state_read',side_effect=AssertionError('two reused raw reads')),\
                 patch('io.open',side_effect=guard):
                self.assertEqual(v.verify_metadata()['result']['verification_scope'],'metadata_only_no_tensor_payload_read')

    def test_reused_identity_and_type_mutations(self):
        mutations={
            'role':['bad','wg',None], 'file':['wrong.bin','../raw.bin',None],
            'bytes':[1,True,'4718592'], 'sha256':['0'*64,'bad',None],
            'provenance':['fresh_HTTP206',None],
            'source_file':['wrong.bin','../raw.bin',None],
            'http_receipts_available':[True,0,None],
            'http_acquired_at':['2026-10-15T00:00:00Z',False],
            'copied_at':['bad','2026-10-15T00:27:57+00:00','2026-10-15T00:00:00',
                         '2026-10-15T01:00:00+01:00',True,None],
            'source_directory':['/tmp/raw','work/../raw','work//qwen2_live_tail_acquisition_m128/x/raw',
                'work/qwen2_live_tail_acquisition_m128/x/../raw',
                'work/qwen2_live_tail_acquisition_m128/another_run/raw',
                'work/qwen2_live_tail_inputs_m128/x/raw',None]}
        for index in (0,1):
            for field,values in mutations.items():
                for value in values:
                    with self.subTest(index=index,field=field,value=value):
                        state=copy.deepcopy(self.state);state['reused'][index][field]=value
                        # Mutate the mirrored record too: detection must not rely
                        # only on state/ready equality or the outer receipt hash.
                        ready=copy.deepcopy(self.ready);ready['tensors'][index]['provenance']=copy.deepcopy(state['reused'][index])
                        with self.assertRaises((ValueError,TypeError,KeyError)):
                            self.validate(state,ready)

    def test_reused_exact_field_set(self):
        for index in (0,1):
            for field in list(self.state['reused'][index])+['extra']:
                with self.subTest(index=index,field=field):
                    state=copy.deepcopy(self.state)
                    if field=='extra':state['reused'][index][field]='unrecognized'
                    else:del state['reused'][index][field]
                    ready=copy.deepcopy(self.ready);ready['tensors'][index]['provenance']=copy.deepcopy(state['reused'][index])
                    with self.assertRaises((ValueError,TypeError,KeyError)):self.validate(state,ready)

    def test_ready_state_reuse_mismatch(self):
        ready=copy.deepcopy(self.ready);ready['tensors'][0]['provenance']['bytes']=1
        with self.assertRaises(ValueError):self.validate(ready=ready)

    def test_raw_completion_time_chain(self):
        for value in ('2026-10-15T00:00:00Z','2026-10-15T00:28:15Z','bad',True,None,
                      '2026-10-15T00:30:49','2026-10-15T01:30:49+01:00'):
            with self.subTest(value=value):
                ready=copy.deepcopy(self.ready);ready['completed_at']=value
                with self.assertRaises((ValueError,TypeError,KeyError)):self.validate(ready=ready)

    def test_input_creation_time_chain(self):
        for value in ('2026-10-15T00:30:48Z','bad',True,None,'2026-10-15T00:33:39'):
            with self.subTest(value=value):
                inputs=copy.deepcopy(self.inputs);inputs['created_at']=value
                with self.assertRaises((ValueError,TypeError,KeyError)):self.validate(inputs=inputs)

    def test_fresh_receipts_required_with_exact_types(self):
        for field,value in [('status',206.0),('status',200),('bytes',True),('sha256','0'*64),
                            ('acquired_at','2026-10-15T00:00:00Z'),
                            ('acquired_at','2026-10-15T00:31:00Z')]:
            with self.subTest(field=field,value=value):
                ready=copy.deepcopy(self.ready);ready['tensors'][2]['http_ranges'][0][field]=value
                with self.assertRaises((ValueError,TypeError,KeyError)):self.validate(ready=ready)

    def test_reused_receipts_cannot_be_invented(self):
        ready=copy.deepcopy(self.ready);ready['tensors'][0]['http_ranges']=[{'status':206}]
        with self.assertRaises(ValueError):self.validate(ready=ready)

    def test_legacy_code_has_not_changed(self):
        self.assertEqual(v.load_contract()[2]['raw_bytes'],87297024)

    @unittest.skipUnless(os.environ.get('QWEN2_STRICT_REAL_METADATA')=='1',
                         'explicit real-receipt integration opt-in required')
    def test_actual_original_metadata_integration(self):
        if not all((v.ROOT/name).is_file() for name in v.METADATA_SHA256):
            self.skipTest('real ignored recovery JSON is absent')
        result=v.verify_metadata()
        self.assertEqual(result['result']['reused_records_verified'],2)
        self.assertEqual(result['result']['fresh_http206_receipts'],12)
        self.assertTrue(result['result']['time_chain_verified'])


if __name__=='__main__':unittest.main()
