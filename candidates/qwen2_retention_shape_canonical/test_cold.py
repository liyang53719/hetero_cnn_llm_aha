"""Synthetic serialization/retention differential only; no numerical execution."""
from array import array
import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from . import retention as c
from candidates.qwen2_exact64_diagnostic_fullblock import retention as original


def observation(rows):
    return dict(schema='qwen2-pv32-readonly-observation-v1',status='COMPLETE_PV32_OWNER_OBSERVATION_NOT_OFFICIAL_ACCEPTED',
      job=dict(m=rows),fields={n:dict(shape=s) for n,s in c.expected_shapes(rows).items()},metadata=dict(unchanged=[1,2]))


def synthetic(out,rows):
    actual={name:array('I',[0x3f800000]) for name in original.ACTUAL_NAMES};silu=array('I',[0x3f000000]).tobytes()
    values={name:value.tobytes() for name,value in actual.items()};values['silu']=silu
    for name,raw in values.items():(out/('actual_'+name+'.f32le')).write_bytes(raw)
    fields={n:dict(observed=b'\1') for n in original.ATTENTION_NAMES}
    def data(name,key=None):return b'\1\0' if key=='frequency' else b'\0\0\x80\x3f'
    capture=SimpleNamespace(closed=True,active=False,fields=fields,_bytes=data)
    observed=observation(rows);directory=out/'attention_observation';directory.mkdir()
    for name in fields:
        for suffix,raw in (('.u32le',data(name)),('.presence',b'\1'),('.count.u16le',data(name,'frequency'))):
            (directory/(name+suffix)).write_bytes(raw)
    (directory/'summary.json').write_text(json.dumps(observed)+'\n')
    report=dict(whole_block_terminal=True,finalfence=True,actual_outputs_sealed=False,observation=observed,
      execution=dict(host=dict(launch_result=dict(completed=21,jobs=17),accepted=dict(completion_fire=21,owner_result_fire=17,result_fire=1))),
      sealed_actual_outputs={name:dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()) for name,raw in values.items()})
    return actual,silu,capture,report


class Cold(unittest.TestCase):
    def test_fixed_geometries(self):
        for rows in (16,128):
            expected=c.expected_shapes(rows);self.assertEqual(len(expected),10)
            self.assertEqual(expected['dot_parts'],(12,rows,rows,16));self.assertEqual(expected['pv_raw'],(12,rows,128))
        for rows in (True,False,0,1,15,17,64,129,16.0,'16',None):
            with self.assertRaises(ValueError):c.expected_shapes(rows)
    def test_shapes_only_canonicalization(self):
        for rows in (16,128):
            source=dict(observation=observation(rows),other={'unchanged':object()});before=copy.deepcopy(source['observation'])
            view=c.canonical_report_view(source)
            self.assertEqual(source['observation'],before);self.assertIs(view['other'],source['other'])
            self.assertTrue(all(type(v['shape']) is tuple for v in source['observation']['fields'].values()))
            self.assertTrue(all(type(v['shape']) is list for v in view['observation']['fields'].values()))
            self.assertEqual(c.canonical_report_view(view),view)
            view['observation']['metadata']['unchanged'].append(3)
            self.assertEqual(source['observation']['metadata']['unchanged'],[1,2])
    def test_each_bad_shape_rejected(self):
        for name,shape in c.expected_shapes(16).items():
            for value in (list(shape[:-1]),[*shape,1],(True,*shape[1:]),tuple(float(v) for v in shape),None,str(shape)):
                source=dict(observation=observation(16));source['observation']['fields'][name]['shape']=value
                with self.assertRaises(ValueError):c.canonical_report_view(source)
    def test_field_schema_rejected(self):
        for change in ('missing','extra','incomplete','other-schema'):
            source=dict(observation=observation(16))
            if change=='missing':del source['observation']['fields']['dot_parts']
            elif change=='extra':source['observation']['fields']['unexpected']={}
            elif change=='incomplete':source['observation']['status']='INCOMPLETE'
            else:source['observation']['schema']='other'
            with self.assertRaises(ValueError):c.canonical_report_view(source)
    def test_original_failure_new_view_pass(self):
        for rows in (16,128):
            with tempfile.TemporaryDirectory() as d:
                out=Path(d);actual,silu,capture,report=synthetic(out,rows);before=copy.deepcopy(report)
                with self.assertRaisesRegex(ValueError,'saved observer receipt differs'):original.seal(out,actual,silu,capture,report)
                self.assertFalse((out/'LOCAL_RETENTION.json').exists())
                receipt=c.seal(out,actual,silu,capture,report)
                self.assertTrue(original.verify(out,receipt));self.assertEqual(report,before)
                self.assertEqual(len(receipt['inventory']),51)
    def test_nonshape_mismatch_still_rejected(self):
        for changed in ([1,2,3],(1,2)):
            with tempfile.TemporaryDirectory() as d:
                out=Path(d);actual,silu,capture,report=synthetic(out,16)
                report['observation']['metadata']['unchanged']=changed
                with self.assertRaisesRegex(ValueError,'saved observer receipt differs'):c.seal(out,actual,silu,capture,report)
    def test_original_payload_and_terminal_gates(self):
        for mode in ('actual','observation','commitment','terminal','capture'):
            with tempfile.TemporaryDirectory() as d:
                out=Path(d);actual,silu,capture,report=synthetic(out,16)
                if mode=='actual':(out/'actual_n1.f32le').write_bytes(b'\0'*4)
                elif mode=='observation':(out/'attention_observation/pv_bf16.u32le').write_bytes(b'\0'*4)
                elif mode=='commitment':report['sealed_actual_outputs']['n1']['sha256']='0'*64
                elif mode=='terminal':report['execution']['host']['accepted']['completion_fire']=20
                else:capture.closed=False
                with self.assertRaises(ValueError):c.seal(out,actual,silu,capture,report)
                self.assertFalse((out/'LOCAL_RETENTION.json').exists())
    def test_list_input_also_passes(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);actual,silu,capture,report=synthetic(out,128)
            report['observation']=json.loads(json.dumps(report['observation']))
            self.assertTrue(c.verify(out,c.seal(out,actual,silu,capture,report)))
if __name__=='__main__':unittest.main()
