"""Sparse synthetic fixtures exercise metadata wiring without reading operands."""
import copy
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('ci_metadata_recipe',HERE/'recipe.py')
R = importlib.util.module_from_spec(spec);spec.loader.exec_module(R)

class MetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.Q = R.dependency('candidates/qwen2_live_qkv_inputs_m128/recipe.py')
        cls.qp = cls.Q.load_pins()
        cls.T = R.dependency('candidates/qwen2_fullblock_ci_prepare/fresh_tail.py')
        cls.a,cls.n,cls.tp = cls.T.contract()
        cls.original = R.O.load_pins()

    def fixtures(self,root):
        Q,T,a,qp,tp = self.Q,self.T,self.a,self.qp,self.tp
        def put(path,data):
            p=root/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        def sparse(path,size):
            p=root/path;p.parent.mkdir(parents=True,exist_ok=True)
            with p.open('wb') as f:f.truncate(size)
        prefix=Q.report(R.ROOT,qp,'acquire')
        prefix.update(status='RECOVERED_PINNED_QWEN2_PREFIX_SUBSET_ONLY',payload_bytes=7085056,
            acquisition='fresh_HTTP206',tensors=[])
        for t in qp['tensors']:
            receipt=dict(acquired_at='2026-10-15T00:00:01+00:00',requested_url=qp['shard']['url'],
                request_range=f"bytes={t['start']}-{t['end']}",status=206,
                content_range=f"bytes {t['start']}-{t['end']}/{qp['shard']['file_bytes']}",
                bytes=t['bytes'],sha256=t['sha256'])
            prefix['tensors'].append({**t,'http_ranges':[receipt]})
            put(R.PREFIX+'/raw/'+t['local_name']+'.receipt.json',R.encoded(receipt))
            sparse(R.PREFIX+'/raw/'+t['file'],t['bytes'])
        prefix_raw=R.encoded(prefix);put(R.INPUT_PATHS['prefix_raw'],prefix_raw)
        put(Q.SCALAR_SOURCE,(R.ROOT/Q.SCALAR_SOURCE).read_bytes())
        support=R.PREFIX+'/inputs/rope_build/'
        put(support+'independent.c',Q.rope_source(root,qp).encode())
        put(support+'independent.so',b'synthetic support binary never loaded')
        put(support+'build.log',b'')
        sparse(R.PREFIX+'/inputs/rope_full.f32le',328448)
        build=dict(command=Q.compile_command(root/(R.PREFIX+'/inputs')),
            source_sha256=qp['rope_c_source_sha256'],
            binary_sha256=R.sha(b'synthetic support binary never loaded'),
            compiler_sha256='a'*64,compiler='synthetic cold compiler identity',
            historical_binary_identity_claimed=False)
        ready=Q.report(R.ROOT,qp,'materialize')
        roles={k:v['record'] for k,v in self.original['producer_roles'].items() if k not in tp['roles']}
        ready.update(status='PINNED_PREFIX_INPUTS_READY_NO_MODEL_EXECUTION',roles=roles,
            subset=R.PREFIX+'/raw',subset_manifest_sha256=R.sha(prefix_raw),rope={**qp['rope'],'file':'rope_full.f32le'},rope_build=build,
            python='synthetic',python_executable='synthetic',torch_imported=False,numpy_imported=False)
        put(R.INPUT_PATHS['prefix_ready'],R.encoded(ready))
        for k,v in roles.items():sparse(R.PREFIX+'/inputs/'+k+'.bin',v['bytes'])
        tensors=[]
        for t in tp['tensors']:
            receipts=[]
            for s in t['segments']:
                receipts.append(dict(acquired_at='2026-10-15T00:00:01+00:00',requested_url=a.URL,
                    request_range=f"bytes={s['start']}-{s['end']}",status=206,
                    content_range=f"bytes {s['start']}-{s['end']}/{tp['shard']['checkpoint_file_bytes']}",
                    bytes=s['bytes'],sha256=s['sha256']))
            tensors.append({**t,'file':t['local_name']+'.bin','http_ranges':receipts})
            sparse(R.TAIL+'/raw/'+t['local_name']+'.bin',t['bytes'])
        tail=dict(schema=1,status=a.STATUS,acquisition='fresh_HTTP206',model_id=tp['model_id'],
            revision=tp['revision'],pins_sha256=a.PIN_SHA256,output_directory=R.TAIL+'/raw',
            payload_bytes=87297024,http_range_count=14,boundaries=a.BOUNDARIES,
            started_at='2026-10-15T00:00:00+00:00',completed_at='2026-10-15T00:00:02+00:00',
            before={},after={},tensors=tensors)
        tail_raw=R.encoded(tail);put(R.INPUT_PATHS['tail_raw'],tail_raw)
        put(T.SOURCE,b'cold synthetic source identity only')
        tail_ready=dict(schema=1,recipe_id=T.RECIPE,status='FIVE_ALL_FRESH_TAIL_ROLES_READY',
            subset=R.TAIL+'/raw',output=R.TAIL+'/inputs',raw_seal_sha256=R.sha(tail_raw),pins_sha256=a.PIN_SHA256,
            fresh_http206_receipts=14,reused_tensors=0,created_at='2026-10-15T00:00:03+00:00',
            sources={T.SOURCE:a.identity(root/T.SOURCE)},roles={k:{**v,'sha256':T.OUTPUT_HASHES[k]} for k,v in tp['roles'].items()},
            model_executed=False,rtl_executed=False,old_pass_inherited=False)
        put(R.INPUT_PATHS['tail_ready'],R.encoded(tail_ready))
        for k,v in tp['roles'].items():sparse(R.TAIL+'/inputs/'+k+'.bin',v['bytes'])
        header=self.original['shard']['header']['path'];put(header,(R.ROOT/header).read_bytes())
        pins=copy.deepcopy(self.original)
        pins['input_metadata']={k:dict(path=p,**R.identity(root/p)) for k,p in R.INPUT_PATHS.items()}
        for t in pins['raw_tensors']:
            t['path']=str(Path(pins['input_metadata'][t['manifest_role']]['path']).parent/(t['local_name']+'.bin'))
        for k,v in pins['producer_roles'].items():
            v['path']=(R.TAIL if k in tp['roles'] else R.PREFIX)+'/inputs/'+k+'.bin'
        return pins

    def check(self,root,pins):
        original=io.open
        def guarded(path,*args,**kwargs):
            if (str(path).endswith('.bin') and Path(path) != root/pins['shard']['header']['path']) or Path(path).name in ('rope_full.f32le','independent.c','independent.so','build.log'):
                raise AssertionError('oracle metadata opened operand')
            return original(path,*args,**kwargs)
        recipe_identity=self.Q.recipe_identity(R.ROOT)
        with patch.object(R,'load_pins',return_value=pins),patch.object(self.Q,'load_pins',return_value=self.qp), \
             patch.object(self.Q,'recipe_identity',return_value=recipe_identity), \
             patch.object(self.Q,'compiler_identity',side_effect=AssertionError('compiler invoked')), \
             patch.object(self.Q,'check_rope_build',side_effect=AssertionError('tool byte reader invoked')), \
             patch.object(self.Q,'read_inputs',side_effect=AssertionError('full prefix reader called')), \
             patch.object(self.T,'contract',return_value=(self.a,self.n,self.tp)), \
             patch.object(self.a,'snapshot',return_value={}),patch('io.open',side_effect=guarded), \
             patch.object(self.T,'audit_raw',side_effect=AssertionError('full tail audit called')), \
             patch.object(self.a,'read_new',side_effect=AssertionError('full tail reader called')):
            return R.metadata_check(root,pins)

    def test_full_metadata_wiring_never_opens_any_operand(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);pins=self.fixtures(root)
            result=self.check(root,pins)
            self.assertFalse(result['raw_payload_read']);self.assertFalse(result['producer_payload_read'])
            self.assertEqual((result['raw_tensors'],result['producer_roles'],result['fresh_tail_receipts']),(13,14,14))
            self.assertEqual(len(result['proof_files']),10)

    def test_standalone_prefix_receipt_drift_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);pins=self.fixtures(root)
            p=next((root/(R.PREFIX+'/raw')).glob('*.receipt.json'))
            value=R.parse(p.read_bytes());value['status']=200;p.write_bytes(R.encoded(value))
            with self.assertRaisesRegex(ValueError,'standalone'):self.check(root,pins)

    def test_extra_prefix_operand_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);pins=self.fixtures(root)
            (root/(R.PREFIX+'/inputs/extra.bin')).touch()
            with self.assertRaisesRegex(ValueError,'inventory'):self.check(root,pins)

    def test_real_producer_inventory_has_twelve_entries(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);pins=self.fixtures(root)
            self.assertEqual(len(list((root/R.PREFIX/'inputs').iterdir())),12)
            self.check(root,pins)

    def test_rope_support_extra_missing_and_alias_rejected(self):
        for change in ('extra','missing','alias'):
            for name in ('independent.c','independent.so','build.log'):
                with self.subTest(change=change,name=name),tempfile.TemporaryDirectory() as d:
                    root=Path(d);pins=self.fixtures(root)
                    p=root/R.PREFIX/'inputs/rope_build'/name
                    if change=='extra':(p.parent/'unexpected').touch()
                    elif change=='missing':p.unlink()
                    else:
                        target=root/'alias-target';target.write_bytes(p.read_bytes())
                        p.unlink();p.symlink_to(target)
                    with self.assertRaises(ValueError):self.check(root,pins)

    def test_rope_full_missing_size_and_alias_rejected(self):
        for change in ('missing','size','alias','build_alias'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as d:
                root=Path(d);pins=self.fixtures(root)
                p=root/R.PREFIX/'inputs/rope_full.f32le'
                if change=='missing':p.unlink()
                elif change=='size':
                    with p.open('wb') as f:f.truncate(328447)
                elif change=='alias':
                    target=root/'alias-target';p.rename(target);p.symlink_to(target)
                else:
                    p=p.parent/'rope_build';target=root/'aliased-build';p.rename(target);p.symlink_to(target,target_is_directory=True)
                with self.assertRaises(ValueError):self.check(root,pins)

    def test_empty_rope_source_and_binary_rejected(self):
        for name in ('independent.c','independent.so'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as d:
                root=Path(d);pins=self.fixtures(root)
                (root/R.PREFIX/'inputs/rope_build'/name).write_bytes(b'')
                with self.assertRaises(ValueError):self.check(root,pins)

    def test_rope_metadata_drift_rejected_even_when_rebound(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);pins=self.fixtures(root)
            p=root/R.INPUT_PATHS['prefix_ready'];value=R.parse(p.read_bytes())
            value['rope']['bytes']=328447;p.write_bytes(R.encoded(value))
            pins['input_metadata']['prefix_ready'].update(R.identity(p))
            with self.assertRaisesRegex(ValueError,'RoPE metadata'):self.check(root,pins)

    def test_missing_tail_receipt_rejected_even_with_rehashed_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);pins=self.fixtures(root)
            p=root/R.INPUT_PATHS['tail_raw'];m=R.parse(p.read_bytes());m['tensors'][-1]['http_ranges'].pop();p.write_bytes(R.encoded(m))
            pins['input_metadata']['tail_raw'].update(R.identity(p))
            p=root/R.INPUT_PATHS['tail_ready'];m=R.parse(p.read_bytes());m['raw_seal_sha256']=pins['input_metadata']['tail_raw']['sha256'];p.write_bytes(R.encoded(m))
            pins['input_metadata']['tail_ready'].update(R.identity(p))
            with self.assertRaisesRegex(ValueError,'range coverage'):self.check(root,pins)

if __name__ == '__main__':unittest.main()
