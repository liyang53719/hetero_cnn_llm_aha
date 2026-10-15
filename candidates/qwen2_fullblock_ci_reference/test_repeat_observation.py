"""Cold fake-tensor native-byte snapshots, no Torch imports or arithmetic."""
import copy
import json
import math
from pathlib import Path
import tempfile
from types import ModuleType,SimpleNamespace
import unittest
from unittest.mock import patch
from . import repeat_observation as D

class Tensor:
    events=[]
    def __init__(self,name,byte=0):
        self.shape=tuple(D.SHAPES[name]);self.dtype='torch.float32' if name=='softmax_fp32' else 'torch.bfloat16'
        self.size=math.prod(self.shape)*(4 if name=='softmax_fp32' else 2);self.byte=byte
    def stride(self):
        return tuple(math.prod(self.shape[i+1:]) for i in range(len(self.shape)))
    def storage_offset(self):return 0
    def is_contiguous(self):return True
    def contiguous(self):self.events.append('contiguous');return self
    def view(self,dtype):
        if dtype!='uint8':raise AssertionError('dtype')
        self.events.append('view');return self
    def numpy(self):self.events.append('numpy');return self
    def tobytes(self):self.events.append('tobytes');return bytes([self.byte])*self.size


def failure(root,*,changed=False,line=265,boundary_drift=False,enabled=False,hook_override=None):
    torch=ModuleType('torch');torch.Tensor=Tensor;torch.uint8='uint8'
    torch.backends=SimpleNamespace(mkldnn=SimpleNamespace(enabled=enabled))
    outputs={name:Tensor(name,int(changed and name=='q')) for name in D.A.NAMES}
    hook_records={name:dict(shape=list(outputs[name].shape),native_dtype=outputs[name].dtype,
        native_stride=list(outputs[name].stride()),storage_offset=0,is_contiguous=True) for name in ('gate','silu','up','act','down')}
    if hook_override is not None:hook_records['gate']=hook_override
    R=ModuleType('recipe');R.same=lambda a,b:type(a) is type(b) and a==b
    identity=dict(bytes=1,sha256='a'*64)
    before=dict(external_certificate_sha256='b'*64,source_closure_sha256='c'*64,
        source_manifest=dict(identity),pins=dict(identity),effective_pins_sha256='d'*64,
        sources={'source':dict(identity)},raw13={str(i):dict(identity) for i in range(13)},
        native_files={str(i):dict(path='/native/'+str(i),**identity) for i in range(6)},
        input_proofs={'proof':dict(identity)},raw_support={},historical_receipts_revalidated=False)
    L=ModuleType('lifecycle');calls=[]
    def snapshot(recipe,pins):
        calls.append(1)
        result=copy.deepcopy(before)
        if boundary_drift and len(calls)==2:result['source_closure_sha256']='e'*64
        return result
    L.snapshot=snapshot;pins={}
    namespace={};source='def capture(torch,outputs,R,L,pins,before,hook_records):\n'+'\n'*(line-2)+"    raise ValueError('original failure')\n"
    exec(compile(source,str(root/D.A.C.SOURCE),'exec'),namespace)
    try:namespace['capture'](torch,outputs,R,L,pins,before,hook_records)
    except ValueError as error:return error,calls


class RepeatTests(unittest.TestCase):
    def paths(self,d):
        root=Path(d);one=root/'work/one';two=root/'work/two';one.mkdir(parents=True);two.mkdir()
        return root,one,two

    def pair(self,d,changed=False):
        root,one,two=self.paths(d)
        error,calls=failure(root);trace=error.__traceback__;first=D.write(error,root,one)
        self.assertIs(error.__traceback__,trace);self.assertEqual(error.args,('original failure',));self.assertEqual(len(calls),2)
        error,_=failure(root,changed=changed);second=D.write(error,root,two)
        return first,second

    def test_equal_complete_native_bytes_and_no_public_values(self):
        with tempfile.TemporaryDirectory() as d:
            Tensor.events=[];first,second=self.pair(d);result=D.compare(first,second)
            self.assertEqual((result['same_count'],result['diff_count']),(29,0))
            self.assertEqual(Tensor.events,['contiguous','view','numpy','tobytes']*58)
            text=json.dumps(result)
            for private in ('bfloat','1536','stride','sha256',str(first),'original failure'):self.assertNotIn(private,text)
            self.assertEqual(result['status'],'DIAGNOSTIC_ONLY')

    def test_native_bytes_difference_is_not_hidden_by_equal_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            first,second=self.pair(d,changed=True)
            self.assertEqual((first/D.META).read_bytes(),(second/D.META).read_bytes())
            result=D.compare(first,second);self.assertEqual((result['same_count'],result['diff_count']),(28,1))
            self.assertFalse(result['records'][D.A.NAMES.index('q')]['equal'])

    def test_wrong_site_and_enabled_backend_never_write(self):
        with tempfile.TemporaryDirectory() as d:
            root,one,_=self.paths(d);error,_=failure(root,line=264)
            self.assertIsNone(D.write(error,root,one));self.assertEqual(list(one.iterdir()),[])
            error,_=failure(root,enabled=True)
            with self.assertRaises(ValueError):D.write(error,root,one)
            self.assertEqual(list(one.iterdir()),[])

    def test_boundary_change_leaves_no_complete_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            root,one,_=self.paths(d);error,calls=failure(root,boundary_drift=True)
            with self.assertRaises(ValueError):D.write(error,root,one)
            self.assertEqual(len(calls),2);self.assertFalse((one/D.DIRECTORY/D.META).exists())

    def test_existing_and_aliased_directories_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root,one,two=self.paths(d);error,_=failure(root)
            first=D.write(error,root,one)
            with self.assertRaises(FileExistsError):D.write(error,root,one)
            (two/D.DIRECTORY).symlink_to(first,target_is_directory=True)
            with self.assertRaises(ValueError):D.write(error,root,two)

    def test_inventory_missing_unknown_alias_and_truncated_refused(self):
        with tempfile.TemporaryDirectory() as d:
            first,second=self.pair(d)
            extra=second/'extra';extra.touch()
            with self.assertRaises(ValueError):D.compare(first,second)
            extra.unlink();p=second/D.FILES[0];backup=p.read_bytes();p.unlink()
            with self.assertRaises(ValueError):D.compare(first,second)
            p.symlink_to(first/D.FILES[0])
            with self.assertRaises(ValueError):D.compare(first,second)
            p.unlink();p.write_bytes(backup[:-1])
            with self.assertRaises(ValueError):D.compare(first,second)

    def test_metadata_unknown_and_wrong_types_refused(self):
        with tempfile.TemporaryDirectory() as d:
            first,second=self.pair(d);p=second/D.META;value=json.loads(p.read_bytes())
            for mutate in ('extra','bool','shape'):
                bad=copy.deepcopy(value)
                if mutate=='extra':bad['private']='secret'
                elif mutate=='bool':bad['records'][0]['bytes']=True
                else:bad['records'][0]['shape']=[2**50]
                p.write_text(json.dumps(bad))
                with self.assertRaises(ValueError):D.compare(first,second)

    def test_failed_readback_cannot_complete_marker(self):
        with tempfile.TemporaryDirectory() as d:
            root,one,_=self.paths(d);error,_=failure(root)
            with patch.object(D,'_read',return_value=b'corrupt'):
                with self.assertRaises(ValueError):D.write(error,root,one)
            self.assertFalse((one/D.DIRECTORY/D.META).exists())

    def test_only_certificate_digest_is_removed_from_common_boundary(self):
        with tempfile.TemporaryDirectory() as d:
            root,_,_=self.paths(d);error,_=failure(root)
            trace=error.__traceback__
            while trace.tb_frame.f_code.co_name!='capture':trace=trace.tb_next
            before=trace.tb_frame.f_locals['before'];other=copy.deepcopy(before)
            other['external_certificate_sha256']='f'*64
            self.assertEqual(D._boundary(before,True),D._boundary(other,True))
            other['raw13']['0']['sha256']='f'*64
            self.assertNotEqual(D._boundary(before,True),D._boundary(other,True))
            other['unknown']='private'
            with self.assertRaises(ValueError):D._boundary(other,True)

    def test_first_self_validation_and_cross_boundary_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            first,second=self.pair(d)
            self.assertEqual(D.compare(first,first)['same_count'],29)
            path=second/D.META;value=json.loads(path.read_bytes())
            value['boundary']['source_closure_sha256']='e'*64
            path.write_text(json.dumps(value))
            with self.assertRaises(ValueError):D.compare(first,second)

    def test_original_hook_layout_wins_over_clone_layout(self):
        with tempfile.TemporaryDirectory() as d:
            root,one,two=self.paths(d)
            original=dict(shape=D.SHAPES['gate'],native_dtype='torch.bfloat16',
                native_stride=[2000000,9000,1],storage_offset=7,is_contiguous=False)
            error,_=failure(root,hook_override=original);first=D.write(error,root,one)
            error,_=failure(root);second=D.write(error,root,two)
            record=json.loads((first/D.META).read_bytes())['records'][D.A.NAMES.index('gate')]
            for key in ('native_stride','storage_offset','is_contiguous'):
                self.assertEqual(record[key],original[key])
            self.assertEqual((first/D.FILES[D.A.NAMES.index('gate')]).read_bytes(),
                (second/D.FILES[D.A.NAMES.index('gate')]).read_bytes())
            self.assertEqual(D.compare(first,second)['diff_count'],1)

    def test_unknown_hook_fields_fail_before_payload_write(self):
        with tempfile.TemporaryDirectory() as d:
            root,one,_=self.paths(d);error,_=failure(root,hook_override={'unknown':'secret'})
            with self.assertRaises(ValueError):D.write(error,root,one)
            self.assertEqual(list(one.iterdir()),[])

    def test_public_schema_rejects_unknown_fields_and_claims(self):
        value=dict(schema=1,status='DIAGNOSTIC_ONLY',compared_count=29,same_count=29,diff_count=0,
            records=[dict(node=node,equal=True) for node in D.A.NODES])
        self.assertEqual(D.checked(value),value)
        for key,item in [('status','PASS'),('same_count',True),('extra','private'),('diff_count',1)]:
            with self.assertRaises(ValueError):D.checked({**value,key:item})

if __name__=='__main__':unittest.main()
