"""Cold stdlib tests. Fixtures are small byte patterns or metadata, never runs.

Usage: python -I -B test_replay_identity.py [--source-root FROZEN_SOURCE]
Repeat with -O. No external command, native code or numerical package is used.
"""
import argparse
import ast
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE=Path(__file__).resolve().parent
MODULE=HERE/'emitter.py'
if not MODULE.exists():MODULE=HERE/'replay_identity.py'
S=importlib.util.spec_from_file_location('tested_replay_identity',MODULE)
E=importlib.util.module_from_spec(S);exec(compile(MODULE.read_bytes(),str(MODULE),'exec'),E.__dict__)
REAL_PRODUCER_PROJECTION=E.producer_projection
DEFAULT=(HERE.parents[2] if MODULE.name=='replay_identity.py' else
         HERE.parents[1]/'same_host_m128_strict_cleanup_20261017_freeze_e83fb26b/source')
SOURCE=DEFAULT
H='a'*64


def const(source,name):
    tree=ast.parse(source.read_bytes())
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(name)


class SchemaTests(unittest.TestCase):
    def test_exact_source_inventory(self):
        stages=const(SOURCE/'scripts/qwen2_layer0_model_gate.py','REQUIRED_STAGES')
        self.assertEqual(set(E.STAGES),stages);self.assertEqual(len(stages),29)
        self.assertEqual(const(SOURCE/'scripts/qwen2_layer0_model_gate.py','EXPORT_TOKEN_MAJOR'),{'q','k'})
        scalar=const(SOURCE/(E.BASE+'dense_block_reduce/reference/workload.py'),'STAGES')
        self.assertEqual(dict(scalar),E.WIDTHS)
        self.assertEqual(len(E.ACTUAL_WIDTHS),20);self.assertEqual(len(E.PROVIDERS)+2,14)
        for rows in (16,128):
            self.assertEqual(len(E.shapes(rows)),29)
            self.assertEqual(E.shapes(rows)['q'],[1,12,rows,128])
            self.assertEqual(E.export_shape(rows,'q'),[1,rows,1536])
            self.assertEqual(E.export_shape(rows,'pv'),[1,12,rows,128])

    def test_pinned_recipe_sources_exist(self):
        for path in E.RECIPE_SOURCES.values():self.assertTrue((SOURCE/path).is_file(),path)
        self.assertEqual(E.sha((SOURCE/E.LEDGER).read_bytes()),E.LEDGER_SHA)
        self.assertEqual(E.sha((SOURCE/E.CONFIG).read_bytes()),E.CONFIG_SHA)
        self.assertEqual(E.sha((SOURCE/'spec/numerical_contract.md').read_bytes()),E.POLICY_SHA)
        ledger=json.loads((SOURCE/E.LEDGER).read_bytes())
        self.assertEqual([x['local_name'] for x in ledger['tensors']],list(E.PAYLOAD_NAMES))
        self.assertEqual(sum(x['bytes'] for x in ledger['tensors']),94382080)

    def test_shapes_match_original_function(self):
        tree=ast.parse((SOURCE/'scripts/qwen2_layer0_model_gate.py').read_bytes())
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='expected_shapes')
        ns={};exec(compile(ast.Module(body=[node],type_ignores=[]),'original-shapes','exec'),ns)
        cfg=dict(hidden_size=1536,intermediate_size=8960,num_attention_heads=12,num_key_value_heads=2)
        for rows in (16,128):self.assertEqual(E.shapes(rows),ns['expected_shapes'](cfg,rows,0))

    def test_scalar_output_geometry_source(self):
        path=SOURCE/(E.BASE+'dense_block_reduce/reference/workload.py')
        ns={};exec(compile(path.read_bytes(),'cold-workload-schema','exec'),ns)
        for rows in (16,128):
            outputs=ns['output_shapes'](rows);self.assertEqual(len(outputs),22)
            for i,(name,width) in enumerate(E.WIDTHS.items()):self.assertEqual(outputs[f'phase_{i}_{name}_recipe.f32le'],(1,rows,width))
            self.assertEqual(outputs['cache_k.f32le'],(1,rows,2,128))

    def test_flags_exact_source(self):
        for role in ('qkv','qk'):
            self.assertEqual(const(SOURCE/(E.BASE+f'raw_kv_native_{role}/kernel.py'),'FLAGS'),E.RECIPE_FLAGS)
        self.assertEqual(tuple(const(SOURCE/(E.BASE+'dense_block_reduce/reference/builder.py'),'FLAGS')),E.SCALAR_FLAGS)
        self.assertEqual(const(SOURCE/(E.BASE+'official_bf16/dense_silu.py'),'STRICT_FLAGS'),E.LIBRARY_FLAGS)

    def test_no_numerical_or_process_imports(self):
        tree=ast.parse(MODULE.read_bytes())
        imports=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):imports.extend(x.name.split('.')[0] for x in node.names)
            if isinstance(node,ast.ImportFrom):imports.append(node.module.split('.')[0])
            self.assertFalse(isinstance(node,ast.Assert),'validation must survive -O')
        self.assertEqual(set(imports),{'hashlib','json','math','os','pathlib','re','stat','time'})
        for module in ('numpy','torch','transformers','safetensors','ctypes'):self.assertNotIn(module,sys.modules)

    def test_row_type_rejects_boolean(self):
        for rows in (True,False,0,1,15,129,16.0,'16'):
            with self.subTest(rows=rows),self.assertRaises(E.IdentityError):E.shapes(rows)


class BytesTests(unittest.TestCase):
    def test_transpose_known_byte_words(self):
        rows,heads,dim=3,2,2
        raw=b''.join(struct.pack('<I',i) for i in range(rows*heads*dim))
        expected=b''.join(struct.pack('<I',(m*heads+h)*dim+d) for h in range(heads) for m in range(rows) for d in range(dim))
        self.assertEqual(E.token_to_head(raw,rows,heads,dim),expected)
        self.assertNotEqual(E.sha(raw),E.sha(expected))

    def test_qk_permutation_has_no_float_conversion(self):
        # Includes NaN, infinity and signed-zero bit patterns, copied verbatim.
        words=[0x7fc12345,0xff800000,0x80000000,0x00000001]
        raw=b''.join(struct.pack('<I',x) for x in words)
        self.assertEqual(E.token_to_head(raw,2,2,1),raw[:4]+raw[8:12]+raw[4:8]+raw[12:])

    def test_permutation_shape_rejection(self):
        for args in ((b'',1,1,1),(b'x'*4,True,1,1),(b'x'*8,1,1,1),(b'x'*4,1,0,1),(b'x'*4,1,1,129)):
            with self.subTest(args=args),self.assertRaises(E.IdentityError):E.token_to_head(*args)

    def test_kv_planes_not_interleaved(self):
        rows=2;heads=2;dim=1
        k=b''.join(struct.pack('<I',x) for x in (10,11,12,13));v=b''.join(struct.pack('<I',x) for x in (20,21,22,23))
        kv=k+v
        self.assertEqual(E.token_to_head(kv[:16],rows,heads,dim),b''.join(struct.pack('<I',x) for x in (10,12,11,13)))
        self.assertEqual(E.token_to_head(kv[16:],rows,heads,dim),b''.join(struct.pack('<I',x) for x in (20,22,21,23)))

    def capture(self,rows,name):
        shape=E.capture_shape(rows,name);count=1
        for n in shape:count*=n
        width=16 if name=='dot_parts' else 3 if name=='normalizer' else 128 if name in ('pv_raw','pv_bf16') else 1
        raw=[];presence=[];freq=[];selected=[]
        for h in range(12):
            for q in range(rows):
                for k in range(rows) if name in E.CAUSAL_FIELDS else (0,):
                    yes=name not in E.CAUSAL_FIELDS or k<=q
                    for lane in range(width):
                        word=struct.pack('<I',1000*h+100*q+10*k+lane) if yes else bytes.fromhex('c33c96a5')
                        raw.append(word);presence.append(int(yes));freq.append(struct.pack('<H',int(yes)))
                        if yes:selected.append(word)
        return b''.join(raw),bytes(presence),b''.join(freq),b''.join(selected)

    def test_all_capture_geometries_and_present_hashes(self):
        for name in E.FIELDS:
            raw,p,f,selected=self.capture(3,name)
            with self.subTest(name=name):
                self.assertEqual(E.present_bytes(raw,p,f,3,name),selected)
                if name in E.CAUSAL_FIELDS:self.assertNotEqual(E.sha(raw),E.sha(selected))
                else:self.assertEqual(E.sha(raw),E.sha(selected))

    def test_bad_presence_frequency_and_sentinel(self):
        raw,p,f,_=self.capture(3,'scores_bf16')
        for changed in ((raw,b'\x02'+p[1:],f),(raw,p,b'\x02\x00'+f[2:]),
                        (raw[:4]+b'\0'*4+raw[8:],p,f),(raw[:-1],p,f),(raw,p[:-1],f)):
            with self.subTest(),self.assertRaises(E.IdentityError):E.present_bytes(*changed,3,'scores_bf16')

    def test_m128_causal_observation_counts(self):
        observed=12*128*129//2;total=12*128*128
        self.assertEqual((observed,total,total-observed),(99072,196608,97536))

    def test_select_causal_exact(self):
        raw,p,f,selected=self.capture(3,'scores_bf16')
        self.assertEqual(E.select_causal(raw,3),selected)

    def test_tensor_canonical_qk_binding(self):
        rows=16;raw=bytes(range(256))*((rows*1536*4)//256)
        item=dict(path='native16/bf16/phase_0/native_q.f32le',bytes=len(raw),sha256=E.sha(raw))
        with mock.patch.object(E,'read_record',return_value=raw):
            result=E.tensor(None,item,rows,Path('/synthetic'),item['path'],'q')
        self.assertEqual(result['content_sha256'],E.sha(E.token_to_head(raw,rows,12)))
        self.assertEqual(result['file_sha256'],E.sha(raw))

    def test_descriptor_size_and_shape(self):
        d=E.descriptor(H,H,[1,2],[2],size=8)
        self.assertEqual(d['bytes'],8)
        self.assertEqual(E.descriptor(H,H,[47010816],[47010816],size=188043264)['bytes'],188043264)
        with self.assertRaises(E.IdentityError):E.descriptor(H,H,[1],[1],encoding='float32_be')
        for stored,logical,size in (([],[1],4),([0],[0],0),([True],[1],4),([2],[3],8),([2],[2],16)):
            with self.subTest(),self.assertRaises(E.IdentityError):E.descriptor(H,H,stored,logical,size=size)


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='replay-identity-cold-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.path=self.root/'sample';self.path.write_bytes(b'pattern-only\x00')
        self.expected=E.sha(self.path.read_bytes());self.reader=E.Reader(time.monotonic()+30)

    def test_read_and_reverify(self):
        raw=self.reader.read(self.path,self.expected,capture=True,limit=1024)
        self.assertEqual(raw,b'pattern-only\x00');self.reader.verify()
        self.assertEqual(len(self.reader.files),1)

    def test_wrong_hash_size_and_zero(self):
        for kwargs in ({'expected':H},{'expected':self.expected,'size':1},{'expected':self.expected,'size':True},
                       {'expected':self.expected,'limit':1}):
            with self.subTest(),self.assertRaises(E.IdentityError):self.reader.read(self.path,**kwargs)
        self.path.write_bytes(b'')
        with self.assertRaises(E.IdentityError):self.reader.read(self.path,E.sha(b''))

    def test_symlink_file_and_ancestor(self):
        link=self.root/'link';link.symlink_to(self.path)
        with self.assertRaises(E.IdentityError):self.reader.read(link,self.expected)
        directory=self.root/'directory';directory.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(E.IdentityError):self.reader.read(directory/'sample',self.expected)

    def test_hardlink_alias(self):
        link=self.root/'link';os.link(self.path,link)
        with self.assertRaises(E.IdentityError):self.reader.read(self.path,self.expected)
        with self.assertRaises(E.IdentityError):self.reader.read(link,self.expected)

    def test_directory_and_fifo(self):
        with self.assertRaises(E.IdentityError):self.reader.read(self.root,self.expected)
        fifo=self.root/'fifo';os.mkfifo(fifo)
        with self.assertRaises(E.IdentityError):self.reader.read(fifo,self.expected)

    def test_traversal_rejected(self):
        for value in ('foo','/tmp/../tmp/foo',str(self.root)+'//sample',str(self.root)+'/./sample','/tmp/a\\b','/tmp/a\0b'):
            with self.subTest(value=value),self.assertRaises(E.IdentityError):self.reader.read(value,self.expected)
        for value in ('/foo','../foo','a/../b','a//b','a/./b','a\\b',''):
            with self.subTest(value=value),self.assertRaises(E.IdentityError):E.relative(value)

    def test_drift_between_stages(self):
        self.reader.read(self.path,self.expected)
        self.path.write_bytes(b'pattern-only\x00')
        with self.assertRaises(E.IdentityError):self.reader.verify()

    def test_replacement_same_bytes_rejected(self):
        self.reader.read(self.path,self.expected)
        other=self.root/'other';other.write_bytes(self.path.read_bytes());os.replace(other,self.path)
        with self.assertRaises(E.IdentityError):self.reader.verify()

    def test_growth_during_read(self):
        original=E.os.read;done=False
        def changing(fd,n):
            nonlocal done
            block=original(fd,n)
            if block and not done:
                done=True
                with self.path.open('ab') as f:f.write(b'x')
            return block
        with mock.patch.object(E.os,'read',side_effect=changing),self.assertRaises(E.IdentityError):
            self.reader.read(self.path,self.expected)

    def test_shrink_during_read(self):
        original=E.os.read;done=False
        def changing(fd,n):
            nonlocal done
            block=original(fd,n)
            if block and not done:done=True;self.path.write_bytes(b'x')
            return block
        with mock.patch.object(E.os,'read',side_effect=changing),self.assertRaises(E.IdentityError):
            self.reader.read(self.path,self.expected)

    def test_close_failure_preserves_primary_deadline(self):
        original_close=E.os.close
        def close_then_fail(fd):
            original_close(fd);raise OSError('private close details')
        with mock.patch.object(E.os,'read',side_effect=TimeoutError('REPLAY_IDENTITY_DEADLINE')),mock.patch.object(E.os,'close',side_effect=close_then_fail):
            with self.assertRaisesRegex(TimeoutError,'REPLAY_IDENTITY_DEADLINE'):self.reader.read(self.path,self.expected)
        with mock.patch.object(E.os,'close',side_effect=close_then_fail):
            with self.assertRaisesRegex(E.IdentityError,'FILE_CLOSE'):self.reader.read(self.path,self.expected)

    def test_total_and_record_caps(self):
        with mock.patch.object(E,'MAX_TOTAL',1),self.assertRaises(E.IdentityError):self.reader.read(self.path,self.expected)
        other=E.Reader(time.monotonic()+30)
        with mock.patch.object(E,'MAX_RECORDS',0),self.assertRaises(E.IdentityError):other.read(self.path,self.expected)

    def test_expired_and_near_expiry(self):
        with self.assertRaises(TimeoutError):E.Reader(time.monotonic()-1)
        original=E.time.monotonic
        stop=original()+10
        r=E.Reader(stop)
        with mock.patch.object(E.time,'monotonic',side_effect=[stop-0.1,stop+0.1]),self.assertRaises(TimeoutError):
            r.read(self.path,self.expected)
        for d in (True,float('nan'),float('inf'),0,'123'):
            with self.subTest(d=d),self.assertRaises(E.IdentityError):E.remaining(d)


class MetadataTests(unittest.TestCase):
    def test_duplicate_nonfinite_and_bounds(self):
        values=(b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":Infinity}',b'{"x":1e999}',b'',b'{'*50,
                b'['*50+b'0'+b']'*50,E.encoded({'x':'a'*131073}),E.encoded({'x':2**128}))
        for raw in values:
            with self.subTest(raw=raw[:30]),self.assertRaises(E.IdentityError):E.strict(raw)
        with mock.patch.object(E,'MAX_JSON',2),self.assertRaises(E.IdentityError):E.strict(b'{"x":1}')

    def test_compiler_safe_projection(self):
        p=E.compiler_projection(dict(path='/private/compiler',sha256=H,version='g++ (Ubuntu 13.3.0-6ubuntu2~24.04) 13.3.0'))
        self.assertEqual(p['version_components'],[13,3,0]);self.assertNotIn('/private',E.encoded(p).decode())
        self.assertNotIn('Ubuntu',E.encoded(p).decode())
        derived=E.compiler_projection(dict(sha256=H,version='x86_64-linux-gnu-g++-14 (Debian 14.2.0-19) 14.2.0'))
        self.assertEqual(derived['version_components'],[14,2,0])
        for version in ('/private/compiler 13.3.0','g++ (/private/host) 13.3.0','g++ 13.3.0\nsecret','g++ 123.3.0','g++ 13.3.0 --secret'):
            with self.subTest(version=version),self.assertRaises(E.IdentityError):E.compiler_projection(dict(sha256=H,version=version))

    def test_loaded_provider_metadata_is_explicit(self):
        identity=dict(payload={n:dict(content_sha256=H) for n in E.PAYLOAD_NAMES},readonly=dict(
            input_x=dict(file_sha256=E.INPUT_PINS[16][0]),table=dict(content_sha256=E.TABLE_SHA)))
        loaded={}
        for name,(shape,dtype,_,__) in E.PROVIDERS.items():loaded[name]=dict(bytes=__import__('math').prod(shape)*(2 if dtype=='bfloat16' else 4),sha256=H)
        loaded.update(x=dict(bytes=16*1536*4,sha256=E.INPUT_PINS[16][0]),rope=dict(bytes=2*1024*64*4,sha256=H))
        got=E.loaded_providers(dict(loaded_inputs=loaded),identity,16)
        self.assertEqual(len(got),14)
        self.assertEqual(got['x']['verification'],'DIRECT_FILE_REHASH')
        for name in set(got)-{'x'}:
            self.assertEqual(got[name]['verification'],'QUALIFIED_METADATA_ONLY')
            self.assertIsNone(got[name]['file_sha256']);self.assertTrue(got[name]['reconstruction']['recipe'])
        loaded['wq']['bytes']+=1
        with self.assertRaises(E.IdentityError):E.loaded_providers(dict(loaded_inputs=loaded),identity,16)

    def test_record_target_origin_and_types(self):
        out=Path('/private/run')
        item=dict(path='readonly/input_x.f32le',bytes=1,sha256=H)
        self.assertEqual(E.record_path(item,16,out,item['path']),out/'m16/setup/producer/readonly/input_x.f32le')
        rooted=dict(item,root='upstream')
        self.assertEqual(E.record_path(rooted,128,out,item['path']),out/'m16/setup/producer/readonly/input_x.f32le')
        for changed in (dict(item,path='../x'),dict(item,path='other'),dict(item,bytes=True),dict(item,sha256='/private'),dict(rooted,root='origin')):
            with self.subTest(),self.assertRaises(E.IdentityError):E.record_path(changed,128 if 'root' in changed else 16,out,item['path'])

    def test_identity_digest_independent_of_provenance(self):
        identity=dict(tensor=dict(content_sha256=H),recipe='FIXED')
        a=dict(identity=identity,identity_sha256=E.sha(E.encoded(identity)),provenance=dict(ci=dict(commit='a'*40,run_id='1',run_attempt='1'),receipt_sha256='b'*64))
        b=copy.deepcopy(a);b['provenance']['ci']['run_id']='2';b['provenance']['receipt_sha256']='c'*64
        self.assertEqual(a['identity_sha256'],b['identity_sha256']);self.assertNotEqual(E.sha(E.encoded(a)),E.sha(E.encoded(b)))

    def test_error_code_exact_type_and_fixed_allowlist(self):
        self.assertEqual(E.error_code(E.IdentityError('FILE_DRIFT')),'FILE_DRIFT')
        class Sneaky(E.IdentityError):
            def __str__(self):raise AssertionError('must never stringify')
        for error in (E.IdentityError('/private/path'),E.IdentityError('FILE_DRIFT','secret'),E.IdentityError(),
                      E.IdentityError(['FILE_DRIFT']),E.IdentityError('FILE_DRIFT\n/path'),Sneaky('FILE_DRIFT'),
                      ValueError('FILE_DRIFT'),TimeoutError('REPLAY_IDENTITY_DEADLINE'),object()):
            with self.subTest(kind=type(error).__name__):self.assertEqual(E.error_code(error),'UNKNOWN')

    def test_finalize_rejects_missing_preparation(self):
        with self.assertRaises(E.IdentityError):E.finalize(prepared=None,full_receipt_sha256=H,sources={},deadline=time.monotonic()+1)


def source_terminal_fixture(rows,path):
    """Use original cold writer-schema fixture, without allocating its masks."""
    folder=SOURCE/(E.BASE+f'attention_packed_m{rows}_same_host')
    v=type('Namespace',(),{})()
    namespace={'__file__':str(folder/'terminal_validator.py')}
    exec(compile((folder/'terminal_validator.py').read_bytes(),'source-validator-schema','exec'),namespace)
    for name,value in namespace.items():setattr(v,name,value)
    v.field_geometry=lambda name:(E.capture_shape(rows,name),b'\x01',b'\x01\x00')
    tree=ast.parse((folder/'test_terminal_validator.py').read_bytes())
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('hash_of','metric','source_map','fixture')]
    ns={'V':v,'copy':copy};exec(compile(ast.Module(body=nodes,type_ignores=[]),'source-cold-fixture','exec'),ns)
    return ns['fixture'](path)


def synthetic_producer(rows):
    """Source-shaped JSON only; no real tensor, native output or run claim."""
    ledger=json.loads((SOURCE/E.LEDGER).read_bytes());metadata={}
    def record(path,size=4,digest=H,upstream=False):
        r=dict(path=path,bytes=size,sha256=digest)
        if rows==128:r['root']='upstream' if upstream else 'current'
        return r
    def meta_record(path,value,upstream=False):
        metadata[path]=value;raw=E.encoded(value)
        return record(path,len(raw),E.sha(raw),upstream)
    compiler=dict(path='/synthetic/compiler',sha256=H,version='x86_64-linux-gnu-g++-13 (Ubuntu 13.3.0-6ubuntu2~24.04) 13.3.0')
    runtime=dict(python='3.12.15',torch='2.10.0+cpu',numpy='2.3.5',transformers='4.40.1',
        device='cpu',attention='eager',model_revision=E.REVISION,forward_revision=E.FORWARD,
        installed_sources_verified_exact=True,runner_sha256=E.RUNNER_SHA,cache_utils_sha256=H,
        mask_utils_sha256=H,activations_sha256=H,torch_build='/private/build',numpy_build='/private/build',
        independent_qkv_recipe={},source_sha256=const(SOURCE/'scripts/qwen2_layer0_model_gate.py','SOURCE_HASHES'))
    observation=dict(compiler=compiler,fenv=dict(status='OBSERVED',x87_round=0,sse_round=0,ftz=False,daz=False),
        blas_environment=dict(OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4',OMP_NUM_THREADS='4'),
        mkldnn_enabled=True,torch_commit='449b1768410104d3ed79d3bcfe4ba1d65c7f22c0',
        python_executable_sha256=H,runtime_libc_sha256={'libm.so.6':H,'libc.so.6':H},cpu={'synthetic':True})
    p=dict(schema=1,profile='SYNTHETIC_COLD_TEST_ONLY',status=f'COMPLETE_FRESH_M{rows}_REFERENCE_OUTPUTS',
        rows=rows,past_tokens=0,attempt_nonce='b'*64,ci=dict(commit='c'*40,run_id='1',run_attempt='1'),host={'synthetic':True},
        runtime_identity=runtime,runtime_observation=observation,source_sha256={'synthetic.py':H},
        source_manifest_sha256=E.sha(E.encoded({'synthetic.py':H})),driver_sha256=H,source_lock_sha256=H,
        claims={k:False for k in ('actual_chain_executed','full_public_admission','full_29_node_acceptance','rtl_execution','hardware_recipe_acceptance','old_pass_inherited')},
        original_small_gate_revalidated=True,dispatch={'bf16':{},'fp32':{}})
    payload_meta=dict(full_checkpoint_sha256_verified=False,tensors=[]);payload={}
    for pin in ledger['tensors']:
        item=dict(pin,file=pin['local_name']+'.bin');payload_meta['tensors'].append(item)
        payload[pin['local_name']]=record('payload/'+item['file'],pin['bytes'],pin['sha256'],True)
    p['payload']=dict(manifest=meta_record('payload/manifest.json',payload_meta,True),tensors=payload)
    x,arena=E.INPUT_PINS[rows]
    p['readonly']=dict(arena=record('readonly/readonly_arena.f32le',188043264,arena),
        table=record('readonly/tables.f32le',328448,E.TABLE_SHA),input_x=record('readonly/input_x.f32le',rows*1536*4,x),
        input_x_sha256=x,intermediate_preloads=0)
    outputs={};modes={}
    for mode in E.MODES:
        outputs[mode]={method:{} for method in E.METHODS};stages={}
        for name in E.STAGES:
            entry=dict(shape=E.shapes(rows)[name],actual_f32_sha256=H,reference_f32_sha256=H,
                actual_storage_dtype='torch.bfloat16' if mode=='bf16' and name!='softmax_fp32' else 'torch.float32',actual_storage_sha256=H)
            for method,prefix in zip(E.METHODS,('native','independent')):
                path=f'{mode}/phase_0/{prefix}_{name}.f32le'
                entry.update({prefix+'_file':path,prefix+'_file_sha256':H,prefix+'_export_shape':E.export_shape(rows,name)})
                outputs[mode][method][name]=record(f'native{rows}/'+path,4*E.math.prod(E.shapes(rows)[name]))
            stages[name]=entry
        modes[mode]=dict(phases=[dict(phase=0,past_tokens=0,token_ids=list(range(rows)),position_ids=list(range(rows)),stages=stages)])
    result=dict(tokens=rows,carried=False,layer=0,torch_threads=4,official_framework_forward=True,model_id=E.MODEL,
                manifest_whole_checkpoint_hash_verified=False,identity=runtime,modes=modes,blas_environment=observation['blas_environment'])
    p['native']=dict(producer='generated-paired-qkv-qk.run_gate',result=meta_record(f'native{rows}/RESULT.json',result),outputs=outputs)
    # Execute only the original stdlib workload geometry writer.
    work={};path=SOURCE/(E.BASE+'dense_block_reduce/reference/workload.py')
    exec(compile(path.read_bytes(),'source-workload-geometry','exec'),work)
    for role in ('sequential','reduced'):
        records=dict(producer='SYNTHETIC_COLD_TEST_ONLY',cpp=record(role+'/candidate.cpp'),header=record(role+'/block_layout.h'),executable=record(role+'/candidate'))
        records['outputs']={name:record(role+'/raw_stages/'+name,4*E.math.prod(shape)) for name,shape in work['output_shapes'](rows).items()}
        compile_record=dict(returncode=0,argv=[compiler['path'],*E.SCALAR_FLAGS,role+'/candidate.cpp','-o',role+'/candidate'],compiler=compiler,
                            cpp_sha256=H,header_sha256=H,binary_sha256=H)
        records['compile']=meta_record(role+'/compile.json',compile_record)
        records['run']=meta_record(role+'/run.json',dict(status='COMPLETE_REFERENCE_ONLY',returncode=0,
            output_sha256={n:r['sha256'] for n,r in records['outputs'].items()},readonly_sha256=arena,input_x_sha256=x,
            table_sha256=E.TABLE_SHA,actual_chain_executed=False))
        if role=='sequential':
            exports=[dict(name=n,path='candidate_'+n+'.f32le',shape=E.shapes(rows)[n],export_shape=E.export_shape(rows,n),sha256=H) for n in E.STAGES]
            records['export_receipt']=meta_record('sequential/exports.json',exports)
            records['tensors']={e['name']:record('sequential/tensors/'+e['path'],4*E.math.prod(e['shape'])) for e in exports}
        p[role]=records
    p['libraries']={}
    for role in ('qkv','qk'):
        receipt=dict(argv=[compiler['path'],*E.RECIPE_FLAGS,role+'_pair.cpp','-o',role+'_pair.so'],library_sha256=H,
            returncode=0,cpp_sha256=H,generated_module_sha256=E.RUNNER_SHA,compiler=compiler)
        p['libraries'][role]=dict(binary=record(f'{role}_library/{role}_pair.so',4,H,True),
            receipt=meta_record(f'{role}_library/{role}_pair_compile.json',receipt,True))
    if rows==128:p.update(roots=dict(current='/synthetic/out/producer128',upstream='/synthetic/out/m16/setup/producer'),
                         upstream={},parent_context_sha256=H)
    top=const(SOURCE/(E.BASE+('portable_official_producer/' if rows==16 else 'portable_official_producer_m128/')+'driver.py'),'TOP_KEYS')
    if set(p)!=top:raise AssertionError(('real producer TOP_KEYS',set(p)^top))
    return p,metadata,ledger


def fake_tensor(reader,item,rows,out,path,name,mode='bf16',raw_cache=False):
    shape=E.shapes(rows)[name];stored=[1,rows,2,128] if raw_cache else E.export_shape(rows,name)
    return E.descriptor(item['sha256'],H,stored,shape,dtype='float32' if mode=='fp32' or name=='softmax_fp32' else 'bfloat16')


class ProjectionControlTests(unittest.TestCase):
    def project_producer(self,rows,mutate=None):
        producer,metadata,ledger=synthetic_producer(rows)
        if mutate:mutate(producer,metadata)
        reader=mock.Mock()
        def read(_reader,item,row,out,path,**kwargs):
            E.record_path(item,row,out,path)
            if kwargs.get('size') is not None:E.need(kwargs['size']==item['bytes'],'TEST_RECORD_SIZE')
            return E.encoded(metadata[path]) if path in metadata else item['bytes']
        with mock.patch.object(E,'read_record',side_effect=read),mock.patch.object(E,'tensor',side_effect=fake_tensor):
            return REAL_PRODUCER_PROJECTION(reader,producer,rows,Path('/synthetic/out'),ledger)

    def test_both_real_producer_metadata_schemas(self):
        for rows in (16,128):
            result,builds,raw=self.project_producer(rows)
            self.assertEqual(len(result['native']),116);self.assertEqual(len(result['payload']),13)
            self.assertEqual(len(result['scalar_raw']['sequential']),22);self.assertEqual(len(result['scalar_raw']['reduced']),22)
            self.assertEqual(len(result['sequential_exports']),29);self.assertEqual(len(raw),116)
            self.assertEqual(result['readonly']['arena']['bytes'],188043264)
            for name,item in result['native'].items():
                if '.independent_self_cache.' in name:self.assertIsNone(item['native_storage']['content_sha256'])
                else:self.assertEqual(item['native_storage']['verification'],'QUALIFIED_METADATA_ONLY')

    def test_native_missing_extra_storage_and_shape_rejected(self):
        mutations=[lambda p,m:p['native']['outputs']['bf16']['official_self_cache'].pop('mask'),
            lambda p,m:p['native']['outputs']['fp32'].update(extra={}),
            lambda p,m:m['native16/RESULT.json']['modes']['bf16']['phases'][0]['stages']['q'].update(native_export_shape=[1,12,16,128]),
            lambda p,m:m['native16/RESULT.json']['modes']['bf16']['phases'][0]['stages']['q'].update(actual_storage_dtype='torch.float32'),
            lambda p,m:p['sequential']['tensors'].pop('silu'),
            lambda p,m:p['reduced']['outputs'].pop('cache_v.f32le'),
            lambda p,m:m['sequential/compile.json']['argv'].insert(1,'-ffast-math')]
        for mutation in mutations:
            with self.subTest(),self.assertRaises(E.IdentityError):self.project_producer(16,mutation)

    def test_logical_references_resolve(self):
        run=dict(payload={'p':dict(content_sha256=H)},readonly={'table':dict(content_sha256=H)},native={'bf16.official_self_cache.x':{}},
            scalar_raw=dict(sequential={},reduced={'x':{}}),sequential_exports={},full=dict(
            persisted_actual={'kv':{}},actual_stages={'cache_k':dict(reconstruction=dict(source_tensors=['full.persisted_actual:kv'])),
                'repeat_k':dict(reconstruction=dict(source_tensors=['full.actual_stages:cache_k']))},
            loaded_providers={'w':dict(reconstruction=dict(source_tensor='payload:p',source_content_sha256=H))},
            gate_bindings={'official':{'x':dict(actual_tensor='full.actual_stages:cache_k',reference_tensor='native:bf16.official_self_cache.x')}},fixed_arithmetic_bindings={}))
        E.validate_logical_references(run)
        run['full']['actual_stages']['repeat_k']['reconstruction']['source_tensors']=['actual:cache_k']
        with self.assertRaises(E.IdentityError):E.validate_logical_references(run)

    def control_fixture(self):
        source_root=Path('/synthetic/source');out=Path('/synthetic/out');values={}
        def put(path,value):values[str(path)]=copy.deepcopy(value);return E.sha(E.encoded(value))
        def pointer(path):return dict(path=str(path),sha256=E.sha(E.encoded(values[str(path)])))
        p16,meta16,ledger=synthetic_producer(16);p128,meta128,_=synthetic_producer(128)
        ci=p16['ci'];nonce=p16['attempt_nonce'];stop=time.monotonic()+60
        put(source_root/E.LEDGER,ledger)
        source_pins={p:H for p in E.RECIPE_SOURCES.values()}
        source_pins.update({E.LEDGER:E.LEDGER_SHA,E.CONFIG:E.CONFIG_SHA,'spec/numerical_contract.md':E.POLICY_SHA,
            E.BASE+'portable_same_host_m128_launch/replay_identity.py':H,E.BASE+'portable_official_producer_launch/wheel-lock.json':H})
        # The fake reader has a dedicated expected canonical-ledger exception: production Reader does not.
        manifest16=put(out/'m16/setup/producer/PRODUCER_M16.json',p16)
        q16=dict(status='PASS_FRESH_M16_PRODUCER',producer_native_gate_validated=True,owned_group_cleanup_complete=True,child_exit_code=0,
            producer_manifest_sha256=manifest16,producer_source_manifest_sha256=p16['source_manifest_sha256'],
            runtime_identity_sha256=E.sha(E.encoded(p16['runtime_identity'])),host_sha256=E.sha(E.encoded(p16['host'])),ci=ci,attempt_nonce=nonce)
        put(out/'m16/setup/QUALIFICATION.json',q16)
        summaries={};snapshots={};sources={};receipts={}
        for rows in (16,128):
            prefix=out/('m16/full_m16' if rows==16 else 'full_m128')
            summaries[rows],snapshots[rows],sources[rows]=source_terminal_fixture(rows,prefix/'snapshot/SNAPSHOT.json')
            binaries=dict(library_sha256=H)
            summaries[rows]['binaries']=snapshots[rows]['binaries']=binaries
            snap_sha=put(prefix/'snapshot/SNAPSHOT.json',snapshots[rows]);summaries[rows]['snapshot_sha256']=snap_sha
            summary_sha=put(prefix/'actual/summary.json',summaries[rows])
            validation=dict(rows=rows,summary_sha256=summary_sha,snapshot_sha256=snap_sha,official_observed_stages=28,
                assigned_official_gates=27,diagnostic_fp32_stages=1,fixed_arithmetic_pass=True,observed_official_gates_pass=True,
                full_29_node_acceptance=False,rtl_acceptance=False,hardware_acceptance=False,source_manifest_sha256=E.sha(E.encoded(sources[rows])))
            child=dict(summary_sha256=summary_sha,snapshot_sha256=snap_sha,validation=validation,source_manifest_sha256=validation['source_manifest_sha256'])
            ch=put(prefix/'CHILD_RESULT.json',child)
            receipts[rows]=dict(status=f'PASS_FRESH_SAME_HOST_M{rows}_ASSIGNED27',child_exit_code=0,owned_group_cleanup_complete=True,
                ci=ci,attempt_nonce=nonce,validation=validation,child_result_sha256=ch)
        put(out/'m16/evidence/full_m16_summary.json',receipts[16])
        build=dict(library_sha256=H,argv=['/synthetic/compiler',*E.LIBRARY_FLAGS,'/synthetic/a.cpp','-o','/synthetic/a.so'],
            returncode=0,compiler=p16['runtime_observation']['compiler'],source_sha256={'synthetic.cpp':H})
        put(out/'m16/setup/tiny/build/official_bf16_compile.json',build)
        record_paths=dict(producer_manifest='setup/producer/PRODUCER_M16.json',producer_qualification='setup/QUALIFICATION.json',
            actual='full_m16/actual/summary.json',snapshot='full_m16/snapshot/SNAPSHOT.json',child_result='full_m16/CHILD_RESULT.json',full_receipt='evidence/full_m16_summary.json')
        prerequisite=dict(status='VERIFIED_CURRENT_JOB_FULL_M16_SAME_ELF',parent_pid=os.getpid(),ci=ci,attempt_nonce=nonce,
            m16_root=str(out/'m16'),records={n:pointer(out/'m16'/p) for n,p in record_paths.items()},source_sha256=sources[16],
            source_manifest_sha256=E.sha(E.encoded(sources[16])),library=dict(binary=dict(path=str(out/'m16/setup/tiny/build/official_bf16_matrix_silu.so'),bytes=4,sha256=H),
                receipt=pointer(out/'m16/setup/tiny/build/official_bf16_compile.json')))
        prereq_sha=put(out/'M16_PREREQUISITE.json',prerequisite)
        context=dict(parent_pid=os.getpid(),ci=ci,attempt_nonce=nonce,root=str(source_root),workspace=str(out/'producer128'),
            receipt_deadline_ns=int(stop*1e9),upstream={})
        context_sha=put(out/'M128_CONTEXT.json',context);p128['parent_context_sha256']=context_sha
        manifest128=put(out/'producer128/PRODUCER_M128.json',p128)
        verifier=dict(status='PASS_ORIGINAL_M128_NATIVE_AND_SCALAR_GATES',producer_manifest_sha256=manifest128,
            parent_context_sha256=context_sha,original_array_gate_revalidated=True,native_exports=116,scalar_outputs_each=22)
        verifier_sha=put(out/'VERIFIED_M128_PRODUCER.json',verifier)
        q=dict(status='PASS_FRESH_M128_PRODUCER',owned_group_cleanup_complete=True,child_exit_code=0,original_array_gate_revalidated=True,
            parent_context_sha256=context_sha,ci=ci,attempt_nonce=nonce,producer_manifest_sha256=manifest128,
            producer_source_manifest_sha256=p128['source_manifest_sha256'],runtime_identity_sha256=q16['runtime_identity_sha256'],
            host_sha256=q16['host_sha256'],verifier_receipt_sha256=verifier_sha)
        q_sha=put(out/'M128_QUALIFICATION.json',q)
        receipts[128].update(producer_receipt_sha256=q_sha,m16_prerequisite_sha256=prereq_sha)
        final_sha=put(out/'evidence/full_m128_summary.json',receipts[128])
        events=[]
        class FakeReader:
            def __init__(self,deadline):self.deadline=deadline;self.total=0;self.files={};self.inodes={}
            def json(self,path,expected):
                E.remaining(self.deadline);key=str(path);value=values[key];actual=E.sha(E.encoded(value))
                E.need(actual==expected or key==str(source_root/E.LEDGER) and expected==E.LEDGER_SHA,'TEST_METADATA_HASH')
                self.files[key]=(actual,(0,0,0,1,len(E.encoded(value)),0,0));events.append(('read',key));return copy.deepcopy(value)
            def pointer(self,item,expected_path=None):
                E.need(expected_path is None or str(expected_path)==item['path'],'TEST_POINTER');return self.json(item['path'],item['sha256'])
            def read(self,*args,**kwargs):E.remaining(self.deadline);return kwargs.get('size',4)
            def verify(self):
                E.remaining(self.deadline);events.append(('verify',None))
                for path,(expected,_) in self.files.items():E.need(E.sha(E.encoded(values[path]))==expected,'TEST_METADATA_DRIFT')
        def producer_projection(reader,p,rows,out,ledger):
            result,build,native=self.project_producer(rows)
            return result,build,native
        def full_projection(reader,summary,snapshot,rows,out,producer,identity,native,combined):
            events.append(('full',rows));return dict(persisted_actual={},actual_stages={},loaded_providers={},gate_bindings={},fixed_arithmetic_bindings={})
        patches=[mock.patch.object(E,'Reader',FakeReader),mock.patch.object(E,'source_map',side_effect=lambda r,p,s:E.sha(E.encoded(s))),
            mock.patch.object(E,'producer_projection',side_effect=producer_projection),mock.patch.object(E,'full_projection',side_effect=full_projection)]
        kwargs=dict(root=source_root,out=out,source_pins=source_pins,qualification_sha256=q_sha,
            m16_prerequisite_sha256=prereq_sha,context_sha256=context_sha,deadline=stop)
        return patches,kwargs,dict(full_receipt_sha256=final_sha,sources=sources[128],deadline=stop+60),values,events

    def run_control(self,change=None):
        patches,prepare_args,final_args,values,events=self.control_fixture()
        from contextlib import ExitStack
        with ExitStack() as stack:
            for patch in patches:stack.enter_context(patch)
            prepared=E.prepare(**prepare_args)
            if change:return change(prepared,final_args,values,events)
            manifest,digest=E.finalize(prepared=prepared,**final_args)
            self.assertEqual(digest,E.sha(E.encoded(manifest)))
            self.assertEqual(set(manifest['identity']['runs']),{'16','128'})
            self.assertEqual([e for e in events if e[0]=='full'],[('full',16),('full',128)])
            self.assertFalse(manifest['authority']['numerical_acceptance_granted'])
            self.assertFalse(manifest['authority']['freeze_readiness_granted'])
            self.assertNotIn('/synthetic',E.encoded(manifest).decode());self.assertNotIn('/private',E.encoded(manifest).decode())
            with self.assertRaises(E.IdentityError):E.finalize(prepared=prepared,**final_args)
            return manifest

    def test_real_prepare_finalize_control_and_no_public_paths(self):self.run_control()

    def test_prepare_finalize_metadata_drift(self):
        def change(p,args,values,events):
            values['/synthetic/out/M128_QUALIFICATION.json']['child_exit_code']=1
            with self.assertRaises(E.IdentityError):E.finalize(prepared=p,**args)
        self.run_control(change)

    def test_prepared_identity_mutation_rejected(self):
        def change(p,args,values,events):
            p.identity['stimulus']['past_tokens']=1
            with self.assertRaises(E.IdentityError):E.finalize(prepared=p,**args)
        self.run_control(change)

    def test_final_expiry_preserves_numerical_receipt(self):
        def change(p,args,values,events):
            args['deadline']=time.monotonic()-1
            with self.assertRaises(TimeoutError):E.finalize(prepared=p,**args)
            self.assertIn('/synthetic/out/evidence/full_m128_summary.json',values)
        self.run_control(change)

    def test_wrong_final_receipt_hash(self):
        def change(p,args,values,events):
            args['full_receipt_sha256']='f'*64
            with self.assertRaises(E.IdentityError):E.finalize(prepared=p,**args)
        self.run_control(change)

    def test_final_summary_drift(self):
        def change(p,args,values,events):
            values['/synthetic/out/full_m128/actual/summary.json']['rows']=16
            with self.assertRaises(E.IdentityError):E.finalize(prepared=p,**args)
        self.run_control(change)

    def test_preparation_wrong_receipt_and_deadline(self):
        from contextlib import ExitStack
        for name in ('qualification_sha256','m16_prerequisite_sha256','context_sha256','deadline'):
            patches,kwargs,final,values,events=self.control_fixture()
            kwargs[name]=kwargs[name]+1 if name=='deadline' else 'f'*64
            with ExitStack() as stack:
                for patch in patches:stack.enter_context(patch)
                with self.subTest(name=name),self.assertRaises(E.IdentityError):E.prepare(**kwargs)

    def test_final_receipt_missing_prevents_readiness(self):
        def change(p,args,values,events):
            del values['/synthetic/out/evidence/full_m128_summary.json']
            with self.assertRaises(KeyError):E.finalize(prepared=p,**args)
        self.run_control(change)


class FullProjectionTests(unittest.TestCase):
    """Real full projector over source-shaped, virtual zero-word byte fixtures."""
    def fixture(self):
        rows=16;out=Path('/synthetic/out');root=out/'m16/full_m16/actual'
        summary,snapshot,_=source_terminal_fixture(rows,out/'m16/full_m16/snapshot/SNAPSHOT.json')
        producer,_,_=synthetic_producer(rows)
        summary['binaries']=snapshot['binaries']=dict(library_sha256=H)
        buffers={};identity=dict(payload={n:dict(content_sha256=H) for n in E.PAYLOAD_NAMES},readonly={},native={},scalar_raw={'reduced':{}},sequential_exports={})
        native_raw={}
        def remember(path,raw):buffers[str(path)]=raw;return E.sha(raw)
        def change_record(record,path,raw):
            record.update(path=path,bytes=len(raw),sha256=remember(out/'m16/setup/producer'/path,raw));return record
        for name,width in E.ACTUAL_WIDTHS.items():
            raw=b'\0'*(rows*width*4);h=remember(root/('actual_'+name+'.f32le'),raw)
            if name=='silu':summary['sealed_silu_sha256']=h
            else:summary['sealed_actual_outputs'][name]=dict(bytes=len(raw),sha256=h)
        for name in E.FIELDS:
            shape=E.capture_shape(rows,name);width=16 if name=='dot_parts' else 3 if name=='normalizer' else 128 if name in ('pv_raw','pv_bf16') else 1
            parts=[];presence=[];frequency=[];observed=0
            for head in range(12):
                for q in range(rows):
                    for k in range(rows) if name in E.CAUSAL_FIELDS else (0,):
                        yes=name not in E.CAUSAL_FIELDS or k<=q
                        parts.append((b'\0'*4 if yes else bytes.fromhex('c33c96a5'))*width)
                        presence.append(bytes([int(yes)])*width);frequency.append((b'\x01\0' if yes else b'\0\0')*width)
                        observed+=width*int(yes)
            raw,p,f=b''.join(parts),b''.join(presence),b''.join(frequency)
            summary['observation']['fields'][name]=dict(shape=shape,words=E.math.prod(shape),observed_words=observed,writes=observed,identical_repeats=0,
                raw_sha256=remember(root/'attention_observation'/(name+'.u32le'),raw),
                presence_sha256=remember(root/'attention_observation'/(name+'.presence'),p),
                frequency_sha256=remember(root/'attention_observation'/(name+'.count.u16le'),f))
        for name in ('input_x','table'):
            path='readonly/'+('input_x.f32le' if name=='input_x' else 'tables.f32le')
            raw=b'\0'*(rows*1536*4 if name=='input_x' else 328448)
            record=change_record(producer['readonly'][name],path,raw)
            identity['readonly'][name]=dict(content_sha256=record['sha256'],file_sha256=record['sha256'])
        for name in (*E.PROVIDERS,'x','rope'):
            if name=='x':size=rows*1536*4;h=identity['readonly']['input_x']['file_sha256']
            elif name=='rope':size=2*1024*64*4;h=H
            else:
                shape,dtype,_,__=E.PROVIDERS[name];size=E.math.prod(shape)*(2 if dtype=='bfloat16' else 4);h=H
            snapshot['loaded_inputs'][name]=dict(bytes=size,sha256=h)
        summary['loaded_inputs']=copy.deepcopy(snapshot['loaded_inputs'])
        for mode in E.MODES:
            for method,prefix in zip(E.METHODS,('native','independent')):
                for name in E.STAGES:
                    size=E.math.prod(E.shapes(rows)[name])*4;raw=b'\0'*size
                    path=f'native16/{mode}/phase_0/{prefix}_{name}.f32le'
                    item=change_record(producer['native']['outputs'][mode][method][name],path,raw)
                    native_raw[(mode,method,name)]=item
                    identity['native'][mode+'.'+method+'.'+name]=dict(content_sha256=E.sha(raw))
        for filename,item in producer['reduced']['outputs'].items():
            raw=b'\0'*item['bytes'];change_record(item,'reduced/raw_stages/'+filename,raw)
            name=filename.removesuffix('.f32le')
            if name.startswith('phase_'):name=name.split('_')[2]
            identity['scalar_raw']['reduced'][name]=dict(file_sha256=E.sha(raw))
        c=summary['comparison']
        for method in E.METHODS:
            for name,entry in c['methods'][method]['stages'].items():
                count=12*rows*(rows+1)//2 if name in ('scores','logits','prob','softmax_fp32') else E.math.prod(E.shapes(rows)[name])
                h=E.sha(b'\0'*(count*4));entry['metrics'].update(actual_f32_sha256=h,reference_f32_sha256=h)
        for name,metric in c['whole_outputs'].items():
            h=summary['sealed_actual_outputs'][name]['sha256'];metric.update(actual_f32_sha256=h,reference_f32_sha256=h)
        for name,metric in c['actual_observed_nodes'].items():
            count=12*rows*(rows+1)//2 if name in ('scores','logits','prob','softmax_fp32') else E.math.prod(E.shapes(rows)[name])
            h=E.sha(b'\0'*(count*4));metric.update(actual_f32_sha256=h,reference_f32_sha256=h)
        class VirtualReader:
            def read(self,path,expected,*,size=None,capture=False,**kwargs):
                raw=buffers[str(path)]
                E.need(E.sha(raw)==expected and (size is None or size==len(raw)),'VIRTUAL_FILE_IDENTITY')
                return raw if capture else len(raw)
        return VirtualReader(),summary,snapshot,rows,out,producer,identity,native_raw,snapshot['binaries']['library_sha256'],buffers

    def project(self,mutate=None):
        args=self.fixture()
        if mutate:mutate(*args)
        return E.full_projection(*args[:-1])

    def test_real_full_projection_source_fixture(self):
        result=self.project()
        self.assertEqual(len(result['persisted_actual']),20)
        self.assertEqual(len(result['attention_captures']),10)
        self.assertEqual(len(result['actual_stages']),28)
        self.assertEqual(len(result['loaded_providers']),14)
        self.assertEqual(sum(x['assigned'] for x in result['gate_bindings']['official_self_cache'].values()),27)
        self.assertNotIn('mask',result['actual_stages'])
        score=result['actual_stages']['scores']
        self.assertNotEqual(score['content_sha256'],score['present_content_sha256'])
        self.assertEqual(score['content_hash_scope'],'FULL_STORAGE_INCLUDING_UNOBSERVED_SENTINELS')
        self.assertIsNone(result['gate_bindings']['official_self_cache']['softmax_fp32']['qualified_verdict'])
        self.assertEqual(result['persisted_actual']['kv']['stored_shape'],[2,16,2,128])
        self.assertEqual(result['actual_stages']['repeat_k']['reconstruction']['source_tensors'],['full.actual_stages:cache_k'])

    def make_nonuniform_qk(self,reader,summary,snapshot,rows,out,producer,identity,native_raw,combined,buffers):
        for name,heads,index in (('q',12,4),('k',2,5)):
            raw=b''.join(struct.pack('<I',0x3f800000+100*m+h)*128 for m in range(rows) for h in range(heads))
            canonical=b''.join(struct.pack('<I',0x3f800000+100*m+h)*128 for h in range(heads) for m in range(rows))
            stored_hash,logical_hash=E.sha(raw),E.sha(canonical)
            buffers[str(out/'m16/full_m16/actual'/('actual_'+name+'.f32le'))]=raw
            summary['sealed_actual_outputs'][name]['sha256']=stored_hash
            filename=f'phase_{index}_{name}_recipe.f32le'
            reduced=producer['reduced']['outputs'][filename];reduced['sha256']=stored_hash
            buffers[str(out/'m16/setup/producer'/reduced['path'])]=raw
            identity['scalar_raw']['reduced'][name]['file_sha256']=stored_hash
            summary['comparison']['whole_outputs'][name].update(actual_f32_sha256=stored_hash,reference_f32_sha256=stored_hash)
            for method in E.METHODS:
                record=native_raw[('bf16',method,name)];record['sha256']=stored_hash
                buffers[str(out/'m16/setup/producer'/record['path'])]=raw
                identity['native']['bf16.'+method+'.'+name]['content_sha256']=logical_hash
                summary['comparison']['methods'][method]['stages'][name]['metrics'].update(actual_f32_sha256=logical_hash,reference_f32_sha256=logical_hash)

    def test_nonuniform_qk_actual_gate_integration(self):
        result=self.project(self.make_nonuniform_qk)
        for name in ('q','k'):
            record=result['persisted_actual'][name]
            self.assertNotEqual(record['file_sha256'],record['content_sha256'])
            gate=result['gate_bindings']['official_self_cache'][name]
            self.assertEqual(gate['actual_comparison_sha256'],record['content_sha256'])
            fixed=result['fixed_arithmetic_bindings'][name]
            self.assertEqual(fixed['actual_comparison_sha256'],record['file_sha256'])

    def test_stored_qk_digest_cannot_replace_canonical(self):
        def mutate(*args):
            self.make_nonuniform_qk(*args)
            summary=args[1]
            summary['comparison']['methods']['official_self_cache']['stages']['q']['metrics']['actual_f32_sha256']=summary['sealed_actual_outputs']['q']['sha256']
        with self.assertRaises(E.IdentityError):self.project(mutate)

    def test_bad_actual_seal_rejected(self):
        def mutate(reader,summary,*rest):summary['sealed_actual_outputs']['q']['sha256']=H
        with self.assertRaises(E.IdentityError):self.project(mutate)

    def test_full_capture_hash_used_as_causal_metric_rejected(self):
        def mutate(reader,summary,*rest):
            summary['comparison']['methods']['official_self_cache']['stages']['scores']['metrics']['actual_f32_sha256']=summary['observation']['fields']['scores_bf16']['raw_sha256']
        with self.assertRaises(E.IdentityError):self.project(mutate)

    def test_missing_capture_and_actual_rejected(self):
        def mutate(reader,summary,*rest):summary['observation']['fields'].pop('normalizer')
        with self.assertRaises(E.IdentityError):self.project(mutate)
        def mutate(reader,summary,*rest):summary['sealed_actual_outputs'].pop('qraw')
        with self.assertRaises(E.IdentityError):self.project(mutate)

    def test_fixed_reference_hash_rejected(self):
        def mutate(reader,summary,*rest):summary['comparison']['actual_observed_nodes']['pv']['reference_f32_sha256']=H
        with self.assertRaises(E.IdentityError):self.project(mutate)

    def test_wrong_loaded_provider_size_rejected(self):
        def mutate(reader,summary,snapshot,*rest):
            summary['loaded_inputs']['wk']['bytes']+=2;snapshot['loaded_inputs']['wk']['bytes']+=2
        with self.assertRaises(E.IdentityError):self.project(mutate)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source-root',type=Path);args,left=parser.parse_known_args()
    if args.source_root is not None:SOURCE=args.source_root.resolve()
    unittest.main(argv=[sys.argv[0],*left])
