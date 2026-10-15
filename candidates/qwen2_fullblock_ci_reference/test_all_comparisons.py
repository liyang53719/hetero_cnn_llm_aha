"""Cold synthetic existing-output observations; no model computation."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
from types import ModuleType
import unittest
from . import all_comparisons as D
ROOT='/reviewed/root'

class Fake:
    events=[]
    shape=(1,128,1)
    dtype='torch.bfloat16'
    def float(self):self.events.append('float');return self
    def contiguous(self):self.events.append('contiguous');return self
    def numpy(self):self.events.append('numpy');return self
    def astype(self,dtype,copy):
        if dtype!='<f4' or copy is not False:raise AssertionError('dtype/copy')
        self.events.append('astype');return self
    def tobytes(self):self.events.append('tobytes');return b'local-only'
    def view(self,dtype):self.events.append('view');return self
    def transpose(self,a,b):
        if (a,b)!=(1,2):raise AssertionError('transpose')
        self.events.append('transpose');return self
    def reshape(self,*shape):
        if shape!=(1,128,-1):raise AssertionError('reshape')
        self.events.append('reshape');return self
    def stride(self):return (128,1,1)
    def storage_offset(self):return 0
    def is_contiguous(self):return True


def fixture():
    torch=ModuleType('torch');torch.Tensor=Fake;torch.uint8='uint8'
    outputs={name:Fake() for name in D.NAMES};expected={}
    for name,value in outputs.items():
        meta=D._observe(value,name,torch,{},dict(export_dtype='FP32 exact BF16 widening'))
        expected[name]={**meta,'file':name+'.f32le'}
    Fake.events=[]
    return torch,outputs,expected


def fail(torch,outputs,hook_records=None,line=265):
    ns={};source='def capture(torch,outputs,hook_records):\n'+'\n'*(line-2)+"    raise ValueError('private')\n"
    exec(compile(source,ROOT+'/'+D.C.SOURCE,'exec'),ns)
    try:ns['capture'](torch,outputs,{} if hook_records is None else hook_records)
    except ValueError as error:return error

class AllTests(unittest.TestCase):
    def test_all29_existing_outputs_only_no_value_leak(self):
        torch,outputs,expected=fixture();error=fail(torch,outputs)
        before={k:id(v) for k,v in outputs.items()};result=D.project(error,ROOT,expected)
        self.assertEqual(result['compared_count'],29)
        self.assertTrue(all(r['mismatch_count']==0 for r in result['records']))
        self.assertEqual(before,{k:id(v) for k,v in outputs.items()})
        self.assertEqual(Fake.events.count('transpose'),7);self.assertEqual(Fake.events.count('reshape'),7)
        self.assertEqual(Fake.events.count('tobytes'),87)
        text=json.dumps(result)
        for secret in ('local-only','private','sha256','torch.','1536',ROOT):self.assertNotIn(secret,text)
        self.assertFalse(result['numeric_acceptance_claimed'])

    def test_all_categories_and_hook_layout_preserved(self):
        torch,outputs,expected=fixture();name=D.NAMES[0]
        expected[name].update(sha256='a'*64,shape=[2,128,1],native_stride=[129,1,1],
            native_dtype='torch.float32',bytes=1,storage_offset=4)
        hook={name:dict(shape=[1,128,1],native_dtype='torch.bfloat16',native_stride=[128,1,1],storage_offset=0,is_contiguous=True)}
        result=D.project(fail(torch,outputs,hook),ROOT,expected)
        self.assertEqual(result['records'][0]['categories'],list(D.C.CATEGORIES))
        self.assertEqual(result['records'][0]['mismatch_count'],6)

    def test_missing_or_wrong_type_or_site_observes_nothing(self):
        for change in ('missing','tensor','expected','site'):
            torch,outputs,expected=fixture()
            if change=='missing':outputs.pop('x')
            if change=='tensor':outputs['x']=object()
            if change=='expected':expected['x']['unknown']='secret'
            error=fail(torch,outputs,line=264 if change=='site' else 265)
            self.assertIsNone(D.project(error,ROOT,expected));self.assertEqual(Fake.events,[])

    def test_observation_error_preserves_original_error(self):
        torch,outputs,expected=fixture();error=fail(torch,outputs);trace=error.__traceback__
        original=Fake.numpy
        try:
            def broken(self):raise RuntimeError('local conversion failure')
            Fake.numpy=broken
            with self.assertRaises(RuntimeError):D.project(error,ROOT,expected)
        finally:Fake.numpy=original
        self.assertIs(error.__traceback__,trace);self.assertEqual(error.args,('private',))

    def test_standalone_import(self):
        directory=Path(__file__).resolve().parent
        result=subprocess.run([sys.executable,'-B','-c',
            "import all_comparisons; assert len(all_comparisons.NAMES)==29"],
            cwd=directory,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0)

    @unittest.skipUnless(os.environ.get('QWEN2_TINY_OBSERVATION_TEST')=='1','explicit tiny runtime test only')
    def test_real_torch_tiny_existing_outputs_unchanged(self):
        import torch
        outputs={name:torch.zeros((1,1,128,2) if name in D.TOKEN_MAJOR else (1,128,2),
            dtype=torch.float32 if name=='softmax_fp32' else torch.bfloat16) for name in D.NAMES}
        hook={name:dict(shape=list(outputs[name].shape),native_dtype=str(outputs[name].dtype),
            native_stride=list(outputs[name].stride()),storage_offset=outputs[name].storage_offset(),
            is_contiguous=outputs[name].is_contiguous()) for name in ('gate','silu','up','act','down')}
        expected={name:{**D._observe(value,name,torch,hook,{}),'file':name+'.f32le'} for name,value in outputs.items()}
        before={name:(value.clone(),value._version,value.data_ptr()) for name,value in outputs.items()}
        result=D.project(fail(torch,outputs,hook),ROOT,expected)
        self.assertTrue(all(row['mismatch_count']==0 for row in result['records']))
        for name,(old,version,pointer) in before.items():
            self.assertTrue(torch.equal(outputs[name],old))
            self.assertEqual(outputs[name]._version,version)
            self.assertEqual(outputs[name].data_ptr(),pointer)
        self.assertEqual(sum(v.numel() for v in outputs.values()),7424)

    def test_strict_output_schema(self):
        torch,outputs,expected=fixture();valid=D.project(fail(torch,outputs),ROOT,expected)
        for key,value in [('extra','secret'),('compared_count',True),('numeric_acceptance_claimed',0),('scope','PASS')]:
            with self.assertRaises(ValueError):D.checked({**valid,key:value})
        for mutation in ('node','count','extra'):
            bad=copy.deepcopy(valid)
            bad['records'][0].update({'node':'x'} if mutation=='node' else {'mismatch_count':True} if mutation=='count' else {'hash':'secret'})
            with self.assertRaises(ValueError):D.checked(bad)

if __name__=='__main__':unittest.main()
