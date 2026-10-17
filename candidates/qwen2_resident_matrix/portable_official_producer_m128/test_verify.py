"""Exact-source, shape and verifier-control cold tests; no numerical execution."""
import ast
import copy
from contextlib import ExitStack
from unittest.mock import patch
import types
import hashlib
import importlib.util
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

HERE=Path(__file__).resolve().parent

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec)
    exec(compile(Path(path).read_bytes(),str(path),'exec'),m.__dict__);return m

D=load('verify_test_driver',HERE/'driver.py')
V=load('verify_test_verifier',HERE/'verify.py')


class ColdVerifier(unittest.TestCase):
    def test_exact_original_replay_body_and_storage_shift(self):
        raw=V.validate_replay_source(D)
        tree=ast.parse(raw);func=next(n for n in tree.body if isinstance(n,ast.FunctionDef))
        self.assertEqual(func.name,'validate_m128_gate')
        self.assertEqual(sum(isinstance(n,ast.Constant) and type(n.value) is int and n.value==128 for n in ast.walk(func)),6)
        self.assertIn('>> 16',raw.decode())
        self.assertIn("('bf16', 'fp32')",raw.decode());self.assertIn("('native', 'independent')",raw.decode())
        self.assertIn('audit_semantics(loaded[kind]',raw.decode())
        self.assertIn("entry['actual_storage_dtype']",raw.decode())
        self.assertIn("entry['actual_storage_sha256']",raw.decode())
        self.assertIn('compare(loaded',raw.decode());self.assertIn('stage_verdict(name',raw.decode())

    def test_116_hash_inventory_before_array_replay(self):
        raw=(HERE/'verify.py').read_text();tree=ast.parse(raw)
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='verify_handoff')
        calls=sorted((n.lineno,ast.unparse(n.func)) for n in ast.walk(function) if isinstance(n,ast.Call))
        positions={name:line for line,name in calls}
        self.assertLess(positions["m['phase'].verify_exports"],positions['replay_arrays'])
        self.assertIn('m16_gate_sha256',ast.unparse(function))
        self.assertIn('native16_result',ast.unparse(function))

    def test_parent_cli_cannot_skip_array_replay(self):
        tree=ast.parse((HERE/'verify.py').read_bytes());main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        call=next(n for n in ast.walk(main) if isinstance(n,ast.Call) and ast.unparse(n.func)=='verify_handoff')
        self.assertEqual(ast.literal_eval(next(k.value for k in call.keywords if k.arg=='decode_native')),True)
        self.assertNotIn('decode-native',ast.unparse(main))
        allcalls=[ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n,ast.Call)]
        self.assertNotIn('native.run_gate',allcalls);self.assertNotIn('subprocess.run',allcalls)

    def test_verifier_receipt_no_full_public_claim(self):
        value=dict(attempt_nonce='a'*64,ci=dict(commit='b'*40,run_id='12',run_attempt='1'),
            source_manifest_sha256='c'*64,runtime_identity=dict(example=1),host=dict(example=2))
        result=V.verification_receipt(D,value,'d'*64,'e'*64)
        self.assertEqual(result['native_exports'],116);self.assertEqual(result['native_stages'],29)
        self.assertEqual(result['scalar_outputs_each'],22);self.assertEqual(result['scalar_semantics_each'],12)
        self.assertTrue(result['original_array_gate_revalidated']);self.assertFalse(result['new_forward_executed'])
        self.assertEqual(result['claims'],D.CLAIMS);self.assertTrue(all(v is False for v in result['claims'].values()))

    def test_wrong_driver_hash_before_import(self):
        with self.assertRaisesRegex(ValueError,'driver hash'):V.driver('0'*64)

    def test_full_m16_prerequisite_is_strict_shared_verifier(self):
        raw=(HERE/'driver.py').read_text();tree=ast.parse(raw)
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='verify_full_prerequisite')
        text=ast.unparse(node)
        self.assertIn('package.prerequisite.verify',text)
        for field in ('parent_pid','attempt_nonce','host_sha256','runtime_identity_sha256','m16_root','ci'):
            self.assertIn(field+'=',text)
        self.assertIn('context exact same full-M16 Public receipt/ELF',text)
        self.assertIn('sys.modules.pop',text)

    def test_original_sources_and_rounding_are_pinned(self):
        sources,_=D.verify_sources(D.ROOT)
        self.assertEqual(sources['scripts/qwen2_layer0_model_gate.py'],'917d56f038c646606e9dc67d1d36752f70097adec9748db55b2a915af8147c85')
        self.assertEqual(sources['scripts/qwen2_bf16_materialization_candidate.py'],'357a74dd10b69fb78e2aff34410d1a01c881edbebbcf5d422bed2ee8acb47dbd')
        original=(D.ROOT/'scripts/qwen2_layer0_model_gate.py').read_bytes()
        nodes={n.name:n for n in ast.parse(original).body if isinstance(n,ast.FunctionDef)}
        self.assertIn('native_forward',nodes);self.assertIn('bf16',nodes)
        self.assertNotIn('native_forward',(HERE/'replay_original.py').read_text())
        self.assertEqual(D.RUNNER_SHA,'d7bd12077675984ed7cc20e57a55729fd62e66b773008fa631673086a5a87a64')

    def test_rebuild_exact_generated_runner_source_only(self):
        m=V.cold_modules(D)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);target=out/'scripts/qwen2_layer0_model_gate.py';target.parent.mkdir()
            target.write_bytes((D.ROOT/'scripts/qwen2_layer0_model_gate.py').read_bytes())
            prefix=D.ROOT/'candidates/qwen2_resident_matrix'
            for name in ('raw_kv_native_qkv/variant.patch','raw_kv_native_qk/variant.patch','raw_kv_native_qk_run/dispatch.patch'):
                subprocess.run(['patch','--batch','--fuzz=0','-p1'],cwd=out,input=(prefix/name).read_bytes(),
                    check=True,capture_output=True,timeout=10)
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(),D.RUNNER_SHA)
            self.assertEqual(m['gate'].verify_runner(D.ROOT,target),D.RUNNER_SHA)
        self.assertNotIn('torch',sys.modules);self.assertNotIn('numpy',sys.modules)

    def test_private_cold_metadata_has_no_source_namespace_pollution(self):
        before={k:v for k,v in sys.modules.items() if k=='candidates' or k.startswith('candidates.')}
        sentinel=types.ModuleType('candidates.qwen2_resident_matrix.raw_kv_public_fresh.assets')
        sentinel.__file__='/untrusted/composed/assets.py'
        poisoned='candidates.qwen2_resident_matrix.raw_kv_public_fresh.assets'
        saved=sys.modules.get(poisoned)
        sys.modules[poisoned]=sentinel
        try:
            m=V.cold_modules(D)
            self.assertIs(sys.modules[poisoned],sentinel)
        finally:
            if saved is None:sys.modules.pop(poisoned,None)
            else:sys.modules[poisoned]=saved
        after={k:v for k,v in sys.modules.items() if k=='candidates' or k.startswith('candidates.')}
        self.assertEqual(before,after)
        funcs,stages,policy=m['phase'].helpers()
        shapes=funcs['expected_shapes'](m['phase'].CONFIG,128,0)
        self.assertEqual(len(stages),29);self.assertEqual(shapes['scores'],[1,12,128,128])
        self.assertEqual(policy['operator'],dict(max_abs=0.03125,mean_abs=0.005))
        self.assertEqual(policy['block'],dict(max_abs=0.05,mean_abs=0.01))
        ack='\n'.join('SOFTWARE_RECIPE_STAGE phase=%d name=%s values=%d'%(i,n,128*w) for i,(n,w) in enumerate(m['workload'].STAGES))+'\n'
        ack+='SOFTWARE_RECIPE_COMPLETE tokens=128 stages=15\nSOFTWARE_FLOAT_ENV rounding=FE_TONEAREST probes=10\nCARRIED_LIFETIME readonly_exact=1 cache_prefix_exact=1 unused_sentinels_exact=1\n'
        self.assertIs(m['rms'].software_ack(ack,128,0)['process_completion_ack'],True)
        with self.assertRaises(ValueError):m['rms'].software_ack(ack,16,0)
        self.assertNotIn('numpy',sys.modules);self.assertNotIn('torch',sys.modules)

    def test_original_metadata_projection_forgery_rejections(self):
        m=V.cold_modules(D);phase=m['phase'];funcs,stages,policy=phase.helpers()
        shapes=funcs['expected_shapes'](phase.CONFIG,128,0)
        lib=dict(library_sha256='1'*64,source_sha256={},pins_sha256='2'*64,receipt_sha256='3'*64)
        recipe=phase.combined_identity(lib,lib)
        value=dict(schema_version=1,tokens=128,carried=False,layer=0,torch_threads=4,
            official_framework_forward=True,rtl_execution=False,hardware_recipe_acceptance=False,logits=False,
            full_model_quality=False,payload_manifest_sha256='4'*64,m16_gate_sha256='5'*64,
            identity=dict(runner_sha256=D.RUNNER_SHA,independent_qkv_recipe=recipe),
            arithmetic=dict(independent_qkv=recipe),policy=policy,modes={},status='PASS_BF16_STAGE_BUDGET')
        for mode in ('bf16','fp32'):
            observed={}
            for name in stages:
                metrics=dict(max_abs=0.0,mean_abs=0.0,finite=True,bit_exact=True)
                metrics.update(funcs['stage_verdict'](name,metrics,mode,policy))
                metrics.update(shape=shapes[name],elements=__import__('math').prod(shapes[name]))
                observed[name]=metrics
            value['modes'][mode]=dict(phases=[dict(phase=0,past_tokens=0,token_ids=list(range(128)),position_ids=list(range(128)),
                stages=observed,failed_stages=[],semantics={n:True for n in phase.SEMANTICS},all_semantics_exact=True,
                status='PASS_BF16_STAGE_BUDGET' if mode=='bf16' else 'DIAGNOSTIC_FP32')])
        sources,_=D.verify_sources(D.ROOT)
        def project(v):return phase.project_result(v,tokens=128,result_sha256='6'*64,source_sha256=sources,
            contract_sha256=D.baseline().POLICY_SHA,generated_module_sha256=D.RUNNER_SHA,library=lib,qkv_library=lib,
            payload_manifest_sha256='4'*64,m16_result_sha256='5'*64)
        self.assertIs(project(value)['native_acceptance'],True)
        mutations=[]
        for field,bad in (('tokens',16),('carried',True),('m16_gate_sha256','0'*64),('torch_threads',True)):
            v=copy.deepcopy(value);v[field]=bad;mutations.append(v)
        for field,bad in (('shape',[1,16,1536]),('elements',True),('finite',False),('max_abs',float('nan')),('passed',True)):
            v=copy.deepcopy(value);stage='softmax_fp32' if field=='passed' else 'y'
            v['modes']['bf16']['phases'][0]['stages'][stage][field]=bad;mutations.append(v)
        v=copy.deepcopy(value);del v['modes']['fp32']['phases'][0]['stages']['y'];mutations.append(v)
        v=copy.deepcopy(value);v['modes']['bf16']['phases'][0]['semantics']['mask_exact']=False;mutations.append(v)
        for index,v in enumerate(mutations):
            with self.subTest(index=index),self.assertRaises(ValueError):project(v)

    def test_replay_rejects_weakened_metric_storage_and_semantics_source(self):
        path=HERE/'replay_original.py';raw=path.read_text()
        mutations=(('>> 16','>> 128'),('expected_shapes(config, 128','expected_shapes(config, 16'),
            ("('native', 'independent')","('native',)"),('metrics = compare(', 'metrics = replacement_compare('),
            ('digest_array(stored)', 'digest_array(array)'),('not all(audit_semantics(', 'not all(replacement_semantics('))
        try:
            for before,after in mutations:
                self.assertIn(before,raw)
                path.write_text(raw.replace(before,after,1))
                with self.subTest(before=before),self.assertRaises(ValueError):V.validate_replay_source(D)
        finally:path.write_text(raw)

    def test_consumer_hash_only_handoff_with_composed_imports(self):
        # Private output contents are mocked here. Real source closure,
        # cold_modules, original metadata projection, full false-mode control
        # and canonical native record binding still execute. No arrays run.
        B=D.baseline();m=V.cold_modules(D);phase=m['phase'];funcs,stages,policy=phase.helpers()
        shapes=funcs['expected_shapes'](phase.CONFIG,128,0)
        lib=dict(library_sha256='1'*64,source_sha256={},pins_sha256='2'*64,receipt_sha256='3'*64)
        recipe=phase.combined_identity(lib,lib)
        original=ast.parse((D.ROOT/'scripts/qwen2_layer0_model_gate.py').read_bytes())
        official=ast.literal_eval(next(n.value for n in original.body if isinstance(n,ast.Assign) and
            any(isinstance(t,ast.Name) and t.id=='SOURCE_HASHES' for t in n.targets)))
        identity=dict(python='3.12.15',torch='2.10.0+cpu',numpy='2.3.5',transformers='4.40.1',device='cpu',attention='eager',
            model_revision='ba1cf1846d7df0a0591d6c00649f57e798519da8',forward_revision='9fe3f585bb4ea29f209dc705d269fbe292e1128f',
            source_sha256=official,installed_sources_verified_exact=True,torch_build='cold fixture',numpy_build='cold fixture',
            cache_utils_sha256='7'*64,mask_utils_sha256='8'*64,activations_sha256='9'*64,
            runner_sha256=D.RUNNER_SHA,independent_qkv_recipe=recipe)
        result=dict(schema_version=1,tokens=128,carried=False,layer=0,torch_threads=4,
            official_framework_forward=True,rtl_execution=False,hardware_recipe_acceptance=False,logits=False,
            full_model_quality=False,payload_manifest_sha256='4'*64,m16_gate_sha256='5'*64,identity=identity,
            arithmetic=dict(independent_qkv=recipe),policy=policy,modes={},status='PASS_BF16_STAGE_BUDGET')
        for mode in ('bf16','fp32'):
            observed={}
            for name in stages:
                metrics=dict(max_abs=0.0,mean_abs=0.0,finite=True,bit_exact=True)
                metrics.update(funcs['stage_verdict'](name,metrics,mode,policy))
                metrics.update(shape=shapes[name],elements=__import__('math').prod(shapes[name]))
                metrics.update({kind+'_file':f'{mode}/phase_0/{kind}_{name}.f32le' for kind in ('native','independent')})
                observed[name]=metrics
            result['modes'][mode]=dict(phases=[dict(phase=0,past_tokens=0,token_ids=list(range(128)),position_ids=list(range(128)),
                stages=observed,failed_stages=[],semantics={n:True for n in phase.SEMANTICS},all_semantics_exact=True,
                status='PASS_BF16_STAGE_BUDGET' if mode=='bf16' else 'DIAGNOSTIC_FP32')])
        with tempfile.TemporaryDirectory() as tmp:
            job=Path(tmp)/'job';workspace=job/'producer128';up=job/'m16/setup/producer'
            workspace.mkdir(parents=True);up.mkdir(parents=True)
            source=Path(tmp)/'consumer/candidates/qwen2_resident_matrix/raw_kv_public_fresh/assets.py'
            source.parent.mkdir(parents=True);source.write_bytes((D.ROOT/'candidates/qwen2_resident_matrix/raw_kv_public_fresh/assets.py').read_bytes())
            canonical='candidates.qwen2_resident_matrix.raw_kv_public_fresh.assets'
            composed=load(canonical,source)
            target=up/'generated/scripts/qwen2_layer0_model_gate.py';target.parent.mkdir(parents=True)
            target.write_bytes((D.ROOT/'scripts/qwen2_layer0_model_gate.py').read_bytes())
            prefix=D.ROOT/'candidates/qwen2_resident_matrix'
            for name in ('raw_kv_native_qkv/variant.patch','raw_kv_native_qk/variant.patch','raw_kv_native_qk_run/dispatch.patch'):
                subprocess.run(['patch','--batch','--fuzz=0','-p1'],cwd=up/'generated',input=(prefix/name).read_bytes(),check=True,capture_output=True,timeout=10)
            def record(name,root='current',size=1,digest=None):
                path=(workspace if root=='current' else up)/name;path.parent.mkdir(parents=True,exist_ok=True)
                if not path.exists():path.write_bytes(b'x')
                return dict(root=root,path=name,bytes=size,sha256=digest or D.sha(b'x'))
            native_path=workspace/'native128/RESULT.json';native_path.parent.mkdir();B.save(native_path,result)
            native_record=dict(root='current',**B.record(workspace,native_path))
            native_outputs={mode:{method:{name:record('native128/'+result['modes'][mode]['phases'][0]['stages'][name][kind+'_file'])
                for name in stages} for method,kind in zip(D.METHODS,('native','independent'))} for mode in D.MODES}
            payload=dict(manifest=dict(path='payload/manifest.json',bytes=1,sha256='4'*64),tensors={})
            record('payload/manifest.json','upstream')
            compiler=dict(path='/cold/compiler',sha256='c'*64,version='cold')
            observation=dict(compiler=compiler,blas_environment=m['gate'].environment())
            upstream=dict(payload=payload,libraries={},runtime_identity=identity,runtime_observation=observation)
            context=dict(driver_sha256=D.IMPORTED_DRIVER_SHA,workspace=str(workspace),root=str(D.ROOT),upstream_workspace=str(up),
                attempt_nonce='a'*64,ci=dict(commit='b'*40,run_id='123',run_attempt='1'),host=D.live_host(),upstream=dict(native16_result=dict(sha256='5'*64)))
            context_sha=D.sha(D.encoded(context));sources,lock=D.verify_sources(D.ROOT)
            scalar={role:dict(outputs={name:record(role+'/raw_stages/'+name) for name in m['workload'].output_inventory(128)}) for role in ('sequential','reduced')}
            value=dict(schema=1,profile=D.PROFILE,status=D.STATUS,rows=128,past_tokens=0,
                attempt_nonce=context['attempt_nonce'],ci=context['ci'],host=context['host'],roots=dict(current=str(workspace),upstream=str(up)),
                upstream=context['upstream'],parent_context_sha256=context_sha,runtime_identity=identity,runtime_observation=observation,
                source_sha256=sources,source_manifest_sha256=D.sha(D.encoded(sources)),driver_sha256=D.IMPORTED_DRIVER_SHA,source_lock_sha256=lock,
                payload=D.origin_records(payload,'upstream'),libraries={},
                readonly=dict(arena=record('readonly/arena',size=188043264,digest=D.ARENA_SHA),
                    input_x=record('readonly/input_x',size=786432,digest=D.INPUT_SHA),table=record('readonly/table',digest=B.TABLE_SHA),
                    input_x_sha256=D.INPUT_SHA,intermediate_preloads=0),**scalar,
                native=dict(producer='generated-paired-qkv-qk.run_gate',result=native_record,outputs=native_outputs),
                dispatch={mode:m['gate'].diagnostic.parse_verbose(b'') for mode in D.MODES},claims=D.CLAIMS,original_small_gate_revalidated=True)
            manifest_sha=B.save(workspace/'PRODUCER_M128.json',value)
            def resolve(ws,manifest,item):return Path(manifest['roots'][item['root']])/item['path']
            with ExitStack() as stack:
                stack.enter_context(patch.dict(sys.modules,{canonical:composed}))
                stack.enter_context(patch.object(V,'driver',return_value=D))
                stack.enter_context(patch.object(D,'baseline',return_value=B))
                stack.enter_context(patch.object(D,'verify_upstream',return_value=upstream))
                stack.enter_context(patch.object(D,'resolve_artifact',side_effect=resolve))
                stack.enter_context(patch.object(D,'modules',side_effect=AssertionError('numerical/mixed-root import attempted')))
                stack.enter_context(patch.object(B,'compiler_record',return_value=compiler))
                original_cold=V.cold_modules
                def real_cold(*args):
                    loaded=original_cold(*args)
                    loaded['qkv'].verify=lambda path:lib;loaded['qk'].verify=lambda path:lib
                    loaded['phase'].verify_exports=lambda result,path,rows:self.assertEqual(rows,128)
                    return loaded
                stack.enter_context(patch.object(V,'cold_modules',side_effect=real_cold))
                stack.enter_context(patch.object(V,'scalar_metadata',side_effect=lambda d,b,m,w,v,r:w/r/'raw_stages'))
                stack.enter_context(patch.object(V,'sequential_exports',return_value=[]))
                returned=V.verify_handoff(D.ROOT,workspace,manifest_sha,context=context,expected_context_sha256=context_sha,decode_native=False)
                self.assertEqual(returned,value);self.assertIs(sys.modules[canonical],composed)
                self.assertTrue(str(composed.__file__).startswith(str(Path(tmp)/'consumer')))
            self.assertNotIn('numpy',sys.modules);self.assertNotIn('torch',sys.modules)

    def test_no_numerical_imports_in_cold_tests(self):
        self.assertNotIn('numpy',sys.modules);self.assertNotIn('torch',sys.modules)


if __name__=='__main__':unittest.main()
