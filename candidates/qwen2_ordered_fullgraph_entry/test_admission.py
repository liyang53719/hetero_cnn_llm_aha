"""Pure metadata fixtures, not real provider or arithmetic execution."""
import copy
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
a=importlib.import_module('admission')
if Path(a.__file__).resolve()!=HERE/'admission.py': raise RuntimeError('foreign admission import')


def fixture():
    source=dict(source_files={f'source/{i}.py':dict(bytes=0,sha256='0'*64) for i in range(316)},
                source_file_count=316,default_enabled=False,inherited_runtime_pass=False)
    providers={}
    for name,(shape,size) in a.ROLES.items():
        total=size
        for n in shape: total*=n
        providers[name]=dict(bytes=total,sha256='1'*64,
            record=dict(bytes=total,sha256='1'*64,shape=list(shape),dtype='float32' if size==4 else 'uint16'))
    pins=dict(producer_roles=providers,raw_tensors=[dict(local_name=str(i),dtype='BF16',shape=[1],bytes=2,sha256='2'*64) for i in range(13)],reference_freeze=dict(status='NOT_CAPTURED_SOURCE_ONLY'))
    paths=['/private/runtime/'+str(i) for i in range(19)]
    files={p:dict(bytes=1,sha256='3'*64,needed=[]) for p in paths}
    files[paths[0]]['sha256']=a.ELF_SHA
    graph=dict(roots=paths[:5],files=files,edges=[{'from':paths[0],'target':paths[1],'needed':'libfixture.so','kind':'needed'} for _ in range(51)])
    return source,pins,dict(elf=paths[0],runtime_graph=graph)


class AdmissionTests(unittest.TestCase):
    def setUp(self): self.s,self.p,self.r=fixture()
    def run_prepare(self,**kw): return a.prepare(self.s,self.p,self.r,**kw)
    def test_preparation_not_permission(self):
        result=self.run_prepare()
        self.assertEqual(result['status'],'NOT_READY_PREPARATION_ONLY')
        self.assertFalse(result['default_enabled']); self.assertEqual(len(result['blockers']),7)
        for k in ('native_loaded','native_executed','reference_executed','payload_bytes_rehashed','runtime_files_rehashed'): self.assertFalse(result[k])
    def test_full_roles_and_raw(self):
        r=self.run_prepare();self.assertEqual(len(r['provider14']),14);self.assertEqual(len(r['raw13']),13)
    def test_no_private_paths(self): self.assertNotIn('/private',json.dumps(self.run_prepare()))
    def test_x_view_not_whole_hash(self):
        v=self.run_prepare()['provider14']['x']['active_view'];self.assertEqual(v['bytes'],98304);self.assertIsNone(v['sha256'])
    def test_fixed_resource_limit(self):
        r=self.run_prepare();self.assertEqual(r['fixed_physical_macs'],4096);self.assertEqual(r['legacy_pv_upper_bound_percent'],63.57);self.assertIsNone(r['hardware_cycles'])
    def test_optin_rejected(self):
        with self.assertRaises(ValueError): self.run_prepare(enabled=True)
    def test_m128_not_run_profile(self):
        with self.assertRaises(ValueError): self.run_prepare(rows=128)
    def test_component_rejected(self):
        self.p['producer_roles']={x:{} for x in ('qr','kr','v')}
        with self.assertRaises(ValueError): self.run_prepare()
    def test_old_pv2_rejected(self):
        with self.assertRaises(ValueError): self.run_prepare(pv_profile=2)
    def test_wrong_qk_rejected(self):
        with self.assertRaises(ValueError): self.run_prepare(qk_profile=1)
    def test_rawkv_rejected(self):
        with self.assertRaises(ValueError): self.run_prepare(raw_kv_transport=True)
    def test_source_missing(self):
        self.s['source_files'].pop('source/0.py')
        with self.assertRaises(ValueError): self.run_prepare()
    def test_source_escape(self):
        self.s['source_files']['../escape.py']=self.s['source_files'].pop('source/0.py')
        with self.assertRaises(ValueError): self.run_prepare()
    def test_source_default_on(self):
        self.s['default_enabled']=True
        with self.assertRaises(ValueError): self.run_prepare()
    def test_historical_pass(self):
        self.s['inherited_runtime_pass']=True
        with self.assertRaises(ValueError): self.run_prepare()
    def test_wrong_shape(self):
        self.p['producer_roles']['x']['record']['shape']=[16,1536]
        with self.assertRaises(ValueError): self.run_prepare()
    def test_wrong_extent(self):
        self.p['producer_roles']['rope']['bytes']-=4
        with self.assertRaises(ValueError): self.run_prepare()
    def test_wrong_dtype(self):
        self.p['producer_roles']['wq']['record']['dtype']='float32'
        with self.assertRaises(ValueError): self.run_prepare()
    def test_wrong_producer_hash(self):
        self.p['producer_roles']['x']['record']['sha256']='a'*64
        with self.assertRaises(ValueError): self.run_prepare()
    def test_raw_missing(self):
        self.p['raw_tensors'].pop()
        with self.assertRaises(ValueError): self.run_prepare()
    def test_raw_duplicate(self):
        self.p['raw_tensors'][1]['local_name']='0'
        with self.assertRaises(ValueError): self.run_prepare()
    def test_raw_wrong_encoding(self):
        self.p['raw_tensors'][0]['dtype']='float32'
        with self.assertRaises(ValueError): self.run_prepare()
    def test_wrong_elf(self):
        self.r['runtime_graph']['files'][self.r['elf']]['sha256']='f'*64
        with self.assertRaises(ValueError): self.run_prepare()
    def test_missing_dependency(self):
        self.r['runtime_graph']['files'].pop('/private/runtime/18')
        with self.assertRaises(ValueError): self.run_prepare()
    def test_unknown_dependency_edge(self):
        self.r['runtime_graph']['edges'][0]['target']='/unlisted'
        with self.assertRaises(ValueError): self.run_prepare()
    def test_bad_digest(self):
        self.p['raw_tensors'][0]['sha256']='not sha'
        with self.assertRaises(ValueError): self.run_prepare()
    def test_exact_metadata_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.json';p.write_text('{}')
            digest=a.hashlib.sha256(p.read_bytes()).hexdigest()
            self.assertEqual(a.read_pinned(p,digest),{})
            p.write_text('{} ')
            with self.assertRaises(ValueError):a.read_pinned(p,digest)
    def test_nonmutating(self):
        before=copy.deepcopy((self.s,self.p,self.r));self.run_prepare();self.assertEqual(before,(self.s,self.p,self.r))

if __name__=='__main__': unittest.main()
