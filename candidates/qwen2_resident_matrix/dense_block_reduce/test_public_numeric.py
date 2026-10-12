"""Small comparison/provenance guards; never run a full model or reference."""
from array import array
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
from . import check_public_numeric as R
from scripts import qwen2_layer0_model_gate as native


class NumericGuards(unittest.TestCase):
    def test_artifact_bytes_hash_and_unique_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'raw_stages').mkdir();p=root/'raw_stages/x.f32le';p.write_bytes(b'1234')
            record=dict(path='raw_stages/x.f32le',bytes=4,sha256=R.sha(b'1234'))
            spec=dict(directory=tmp,artifacts=[record])
            self.assertEqual(R.independent_bytes(spec,'x.f32le'),b'1234')
            for items in ([],[record,record],[dict(record,bytes=8)],[dict(record,sha256='0'*64)]):
                with self.assertRaises(ValueError):R.independent_bytes(dict(spec,artifacts=items),'x.f32le')
            p.write_bytes(b'1235')
            with self.assertRaises(ValueError):R.independent_bytes(spec,'x.f32le')

    def test_new_recipe_comparison_retains_official_failure_and_future_absence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'raw_stages').mkdir();rows=16;artifacts=[]
            def save(name,raw):
                (root/'raw_stages'/name).write_bytes(raw)
                artifacts.append(dict(path='raw_stages/'+name,bytes=len(raw),sha256=R.sha(raw)))
            actual={name:array('f',[0])*(rows*width) for name,width in R.prior.old.STAGE_WIDTHS.items()}
            for i,(name,value) in enumerate(actual.items()):save('phase_%d_%s_recipe.f32le'%(i,name),value.tobytes())
            fields={};data={};m=np.tri(rows,dtype=np.uint8)[None].repeat(12,axis=0)
            for name in ('scores_bf16','softmax_fp32','prob_bf16'):
                fields[name]=dict(shape=(12,rows,rows),observed=m.reshape(-1).tobytes())
                data[name]=bytes(12*rows*rows*4)
            fields['pv_bf16']=dict(shape=(12,rows,128),observed=bytes([1])*(12*rows*128))
            data['pv_bf16']=bytes(12*rows*128*4)
            for name in ('scores','logits','softmax_fp32','prob'):
                a=np.zeros((12,rows,rows),dtype='<f4');a[m==0]=999
                save(name+'.f32le',a.tobytes())
            silu=bytes(rows*8960*4);save('silu.f32le',silu)
            capture=SimpleNamespace(fields=fields,_bytes=lambda name:data[name])
            original=dict(whole_outputs={'old':{'bit_exact':False}},actual_observed_nodes={},fixed_arithmetic_pass=False,
                methods={'official_self_cache':{'numerical_status':'FAIL','failed_stages':['qr']}},
                full_29_node_acceptance=False,partially_observed_nodes=['scores','logits','prob','softmax_fp32'])
            s=dict(rows=rows,independent_reference=dict(directory=tmp,artifacts=artifacts))
            with patch.object(R.prior,'compare',return_value=deepcopy(original)):
                result=R.compare(s,actual,{},capture,silu,native)
            self.assertTrue(result['fixed_arithmetic_pass'])
            self.assertEqual(result['methods'],original['methods'])
            self.assertFalse(result['old_sequential_producer_diagnostic']['fixed_arithmetic_pass'])
            self.assertFalse(result['full_29_node_acceptance'])
            actual['y'][0]=1
            with patch.object(R.prior,'compare',return_value=deepcopy(original)):
                self.assertFalse(R.compare(s,actual,{},capture,silu,native)['fixed_arithmetic_pass'])

    def test_fresh_output_guard_precedes_execution_and_snapshot_guard_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(R,'verify_snapshot',side_effect=AssertionError('must not execute')):
                with self.assertRaises(ValueError):R.run(tmp,'absent','0'*64)
            p=Path(tmp)/'snapshot.json';p.write_text('{}')
            with self.assertRaises(ValueError):R.verify_snapshot(p,'0'*64)

if __name__=='__main__':unittest.main()
