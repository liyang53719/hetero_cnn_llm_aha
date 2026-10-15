"""Synthetic exact-site traces only; no tensors, reference capture or file reads."""
import copy
import json
import unittest
from . import comparison_diagnostic as D
ROOT='/explicit/reviewed/root'
BASE=dict(shape=[1,128,1536],bytes=786432,native_dtype='torch.bfloat16',
    export_dtype='FP32 exact BF16 widening',native_bytes=393216,sha256='a'*64,
    native_sha256='b'*64,token_major_sha256='c'*64,native_stride=[196608,1536,1],
    storage_offset=0,is_contiguous=True)


def fail(actual=None,name='att',pins=None,line=265,filename=None,function='capture',error=None):
    source='def '+function+'(actual,pins,name,error):\n'+ '\n'*(line-2)+'    raise error\n'
    namespace={};exec(compile(source,filename or ROOT+'/'+D.SOURCE,'exec'),namespace)
    error=error if error is not None else ValueError('PRIVATE secret hash '+BASE['sha256'])
    if pins is None:pins={'prior18_expectations':{n:copy.deepcopy(BASE) for n in D.NODES}}
    try:namespace[function](copy.deepcopy(BASE) if actual is None else actual,pins,name,error)
    except BaseException as caught:return caught
    raise AssertionError('missing synthetic failure')


class ComparisonTests(unittest.TestCase):
    def test_every_field_classified_without_values(self):
        changes=dict(shape=[2,128,1536],bytes=7,native_dtype='torch.float32',
            export_dtype='FP32 unchanged',native_bytes=8,sha256='d'*64,native_sha256='e'*64,
            token_major_sha256='f'*64,native_stride=[196607,1536,1],storage_offset=1,is_contiguous=False)
        for field,value in changes.items():
            with self.subTest(field=field):
                result=D.project(fail({**BASE,field:value}),ROOT)
                self.assertEqual(result,dict(schema=1,status='CI_REFERENCE_COMPARISON',node='NODE_00',
                    categories=[D.FIELDS[field]],mismatch_count=1))
                text=json.dumps(result)
                for private in ('PRIVATE',ROOT,'torch.',BASE['sha256'],'1536','att'):
                    self.assertNotIn(private,text)
        result=D.project(fail(changes),ROOT)
        self.assertEqual(result['categories'],list(D.CATEGORIES));self.assertEqual(result['mismatch_count'],11)

    def test_node_mapping_and_zero_difference(self):
        for name,node in zip(D.NODES,D.NODE_ENUMS):
            result=D.project(fail(name=name),ROOT)
            self.assertEqual(result['node'],node);self.assertEqual(result['mismatch_count'],0)

    def test_only_exact_site_accepted(self):
        for kwargs in ({'line':264},{'line':266},{'function':'other'},
                       {'filename':ROOT+'/../root/'+D.SOURCE},{'name':'unknown'}):
            self.assertIsNone(D.project(fail(**kwargs),ROOT))
        self.assertIsNone(D.project(ValueError(),ROOT))

    def test_malicious_and_non_native_values_are_rejected_without_callbacks(self):
        class Bad:
            def __eq__(self,other):raise AssertionError('comparison callback')
            def __str__(self):raise AssertionError('string callback')
            def __repr__(self):raise AssertionError('repr callback')
        class Alias(dict):
            def get(self,*args):raise AssertionError('dict callback')
        class Number(int):pass
        for actual in (Alias(BASE),{**BASE,'sha256':Bad()},{**BASE,'shape':[Bad()]},
                       {**BASE,'bytes':True},{**BASE,'bytes':Number(786432)},
                       {**BASE,'native_stride':tuple(BASE['native_stride'])},
                       {**BASE,'extra':'private'}):
            self.assertIsNone(D.project(fail(actual),ROOT))
        self.assertIsNone(D.project(fail(pins=Alias()),ROOT))
        self.assertIsNone(D.project(fail(pins={'prior18_expectations':{'att':BASE}}),ROOT))

    def test_exception_unchanged_and_never_formatted(self):
        class BadError(ValueError):
            def __str__(self):raise AssertionError('exception string')
            def __repr__(self):raise AssertionError('exception repr')
            def __getattribute__(self,name):
                if name=='__traceback__':raise AssertionError('custom traceback access')
                return super().__getattribute__(name)
        error=fail(error=BadError('private'));trace=BaseException.__traceback__.__get__(error)
        self.assertIsNotNone(D.project(error,ROOT))
        self.assertIs(BaseException.__traceback__.__get__(error),trace)
        self.assertEqual(error.args,('private',))

    def test_checked_rejects_unknown_types_fields_enums_and_counts(self):
        valid=D.project(fail({**BASE,'bytes':7}),ROOT)
        mutations=[('schema',True),('node','att'),('categories',['OTHER']),('categories',('BYTES',)),
            ('categories',['BYTES','BYTES']),('mismatch_count',True),('mismatch_count',12),
            ('mismatch_count',0),('extra','private'),('status','private')]
        for key,value in mutations:
            with self.subTest(key=key),self.assertRaises(ValueError):D.checked({**valid,key:value})
        self.assertEqual(D.checked(valid),valid)

if __name__=='__main__':unittest.main()
