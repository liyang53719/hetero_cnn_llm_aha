import copy
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('fresh_tail',Path(__file__).with_name('fresh_tail.py'))
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
class Fresh14Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.a,cls.n,cls.pins=f.contract()
    def manifest(self):
        a,n,pins=self.a,self.n,self.pins
        tensors=[]
        for t in pins['tensors']:
            receipts=[]
            for seg in t['segments']:
                start,end=seg['start'],seg['end']
                receipts.append(dict(acquired_at='2026-10-15T00:00:01+00:00',requested_url=a.URL,
                    request_range=f'bytes={start}-{end}',status=206,
                    content_range=f"bytes {start}-{end}/{pins['shard']['checkpoint_file_bytes']}",
                    bytes=seg['bytes'],sha256=seg['sha256']))
            tensors.append({**t,'file':t['local_name']+'.bin','http_ranges':receipts})
        return dict(schema=1,status=a.STATUS,acquisition='fresh_HTTP206',model_id=pins['model_id'],
            revision=pins['revision'],pins_sha256=a.PIN_SHA256,output_directory=a.PREFIX+'/synthetic/raw',
            payload_bytes=87297024,http_range_count=14,boundaries=a.BOUNDARIES,
            started_at='2026-10-15T00:00:00+00:00',completed_at='2026-10-15T00:00:02+00:00',
            before={},after={},tensors=tensors)
    def validate(self,m):return f.validate_manifest(m,self.a.PREFIX+'/synthetic/raw',self.n,self.pins,{},self.a)
    def test_real_pin_shape_fourteen_synthetic_receipts(self):
        self.assertEqual(len(self.validate(self.manifest())['tensors']),5)
    def test_reused_or_missing_receipt_rejected(self):
        for mutate in ('delete','reuse','duplicate'):
            m=self.manifest();t=m['tensors'][-1]
            if mutate=='delete':t['http_ranges'].pop()
            elif mutate=='reuse':t['http_ranges'][0]['provenance']='reused'
            else:t['http_ranges'][1]=copy.deepcopy(t['http_ranges'][0])
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):self.validate(m)
    def test_wrong_identity_and_types(self):
        for field,value in [('revision','bad'),('http_range_count',True),('payload_bytes',1),('acquisition','reused')]:
            m=self.manifest();m[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.validate(m)
    def test_time_chain(self):
        for value in ['2026-10-14T23:59:59+00:00','2026-10-15T00:00:03+00:00','2026-10-15T00:00:01+01:00']:
            m=self.manifest();m['tensors'][0]['http_ranges'][0]['acquired_at']=value
            with self.subTest(value=value),self.assertRaises(ValueError):self.validate(m)
    def test_metadata_reader_never_opens_bin(self):
        a=self.a;m=self.manifest();relative=m['output_directory']
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/relative;p.mkdir(parents=True)
            raw=a.encode(m);(p/a.SEAL).write_bytes(raw)
            # Sparse stat-only fixtures: zero disk payload data, not official input bytes.
            for t in self.pins['tensors']:
                with (p/(t['local_name']+'.bin')).open('wb') as stream:stream.truncate(t['bytes'])
            original=io.open
            def guarded(path,*args,**kwargs):
                if str(path).endswith('.bin'):raise AssertionError('operand opened')
                return original(path,*args,**kwargs)
            with patch.object(f,'contract',return_value=(a,self.n,self.pins)),patch.object(a,'snapshot',return_value={}),patch('io.open',side_effect=guarded):
                r=f.metadata(root,relative,f.sha(raw));self.assertFalse(r['raw_payloads_read'])
                with self.assertRaises(ValueError):f.metadata(root,relative,'0'*64)
    def test_input_metadata_reader_and_negative_boundaries(self):
        a=self.a;m=self.manifest();subset=m['output_directory'];out=a.PREFIX+'/synthetic/inputs'
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/subset;p.mkdir(parents=True);target=root/out;target.mkdir()
            source=root/f.SOURCE;source.parent.mkdir(parents=True);source.write_bytes(b'cold fixture source')
            raw=a.encode(m);(p/a.SEAL).write_bytes(raw);seal=f.sha(raw)
            for t in self.pins['tensors']:
                with (p/(t['local_name']+'.bin')).open('wb') as stream:stream.truncate(t['bytes'])
            for role,spec in self.pins['roles'].items():
                with (target/(role+'.bin')).open('wb') as stream:stream.truncate(spec['bytes'])
            ready=dict(schema=1,recipe_id=f.RECIPE,status='FIVE_ALL_FRESH_TAIL_ROLES_READY',
                subset=subset,output=out,raw_seal_sha256=seal,pins_sha256=a.PIN_SHA256,
                fresh_http206_receipts=14,reused_tensors=0,created_at='2026-10-15T00:00:03+00:00',
                sources={f.SOURCE:a.identity(source)},roles={role:{**spec,'sha256':f.OUTPUT_HASHES[role]}
                for role,spec in self.pins['roles'].items()},model_executed=False,rtl_executed=False,old_pass_inherited=False)
            original=io.open
            def guarded(path,*args,**kwargs):
                if str(path).endswith('.bin'):raise AssertionError('operand opened')
                return original(path,*args,**kwargs)
            with patch.object(f,'contract',return_value=(a,self.n,self.pins)),patch.object(a,'snapshot',return_value={}),patch('io.open',side_effect=guarded):
                payload=a.encode(ready);(target/'INPUTS_READY.json').write_bytes(payload)
                result=f.input_metadata(root,out,f.sha(payload),seal)
                self.assertFalse(result['typed_payloads_read']);self.assertFalse(result['raw_payloads_read'])
                for field,value in [('reused_tensors',2),('fresh_http206_receipts',True),
                    ('created_at','2026-10-15T00:00:01+00:00'),('raw_seal_sha256','0'*64)]:
                    changed=copy.deepcopy(ready);changed[field]=value;data=a.encode(changed)
                    (target/'INPUTS_READY.json').write_bytes(data)
                    with self.subTest(field=field),self.assertRaises(ValueError):f.input_metadata(root,out,f.sha(data),seal)

    def test_full_raw_audit_reports_actual_payload_reads(self):
        meta=dict(status='FRESH14_METADATA_VERIFIED_PAYLOAD_NOT_READ',raw_payloads_read=False)
        seal='a'*64
        with patch.object(f,'metadata',return_value=meta),patch.object(f,'contract',return_value=(self.a,self.n,self.pins)), \
             patch.object(self.a,'read_new',return_value={'manifest_sha256':seal}) as reader:
            r=f.audit_raw(f.ROOT,self.a.PREFIX+'/synthetic/raw',seal)
            reader.assert_called_once()
            self.assertTrue(r['raw_payloads_read']);self.assertEqual(r['status'],'FRESH14_RAW_PAYLOADS_VERIFIED')
            self.assertFalse(meta['raw_payloads_read'])

    def test_materialize_postwrite_source_boundary(self):
        a=self.a;subset=a.PREFIX+'/synthetic/raw';out=a.PREFIX+'/synthetic/inputs'
        pins={'tensors':[{'role':'unit','local_name':'unit'}],
            'roles':{'unit':{'bytes':1,'widened':True,'source_shape':[1,1]}}}
        ns={'conversion_functions':lambda root,pins:(lambda raw:raw,lambda raw,*shape:raw),
            'validate_raw_bytes':lambda raw,tensor:None,'verify_correspondence':lambda raw,data,spec:None}
        for drift in (False,True):
            with self.subTest(drift=drift),tempfile.TemporaryDirectory() as d:
                root=Path(d);source=root/f.SOURCE;source.parent.mkdir(parents=True);source.write_bytes(b'before')
                directory=root/subset;directory.mkdir(parents=True);(directory/'unit.bin').write_bytes(b'x')
                original=a.write_new
                def write(path,data):
                    original(path,data)
                    if drift and path.name=='unit.bin':source.write_bytes(b'changed')
                with patch.object(f,'contract',return_value=(a,ns,pins)),patch.object(a,'snapshot',return_value={}), \
                    patch.object(f,'audit_raw',return_value={'manifest':{'completed_at':'2026-10-15T00:00:00+00:00'}}) as audit, \
                    patch.object(f,'OUTPUT_HASHES',{'unit':f.sha(b'x')}),patch.object(a,'write_new',side_effect=write):
                    if drift:
                        with self.assertRaisesRegex(ValueError,'source drift during output'):f.materialize(root,subset,out,'a'*64)
                        self.assertFalse((root/out/'INPUTS_READY.json').exists())
                    else:
                        result=f.materialize(root,subset,out,'a'*64)
                        self.assertEqual(result['reused_tensors'],0)
                        self.assertTrue((root/out/'INPUTS_READY.json').is_file())
                    self.assertEqual(audit.call_count,3)

    def test_source_boundary_drift(self):
        m=self.manifest();m['after']={'unexpected':{}}
        with self.assertRaises(ValueError):self.validate(m)
if __name__=='__main__':unittest.main()
