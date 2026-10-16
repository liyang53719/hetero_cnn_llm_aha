"""Cold metadata/control tests. No native module, arrays, build, or payloads."""
import ast
import copy
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock,patch

from . import phase
from ..raw_kv_native_qk import kernel
from ..raw_kv_native_qkv import kernel as qkv_kernel


def fixture(tokens=16,cause=None):
    """Source-derived original receipt metadata; all tensor hashes are synthetic."""
    funcs,stages,policy=phase.helpers();shapes=funcs['expected_shapes'](phase.CONFIG,tokens,0)
    sources={kernel.ORIGINAL:qkv_kernel.FIXED[kernel.ORIGINAL],phase.SOURCE:phase.IMPORTED_SHA256,
        'candidates/qwen2_resident_matrix/raw_kv_public_fresh/setup.py':'a'*64}
    library=dict(library_sha256='b'*64,receipt_sha256='c'*64,source_sha256={kernel.ORIGINAL:qkv_kernel.FIXED[kernel.ORIGINAL]},pins_sha256='d'*64)
    qkv_library=dict(library_sha256='6'*64,receipt_sha256='7'*64,
        source_sha256={kernel.ORIGINAL:qkv_kernel.FIXED[kernel.ORIGINAL]},pins_sha256='8'*64)
    recipe=phase.combined_identity(library,qkv_library)
    identity=dict(runner_sha256='e'*64,independent_qkv_recipe=recipe)
    value=dict(schema_version=1,tokens=tokens,carried=False,layer=0,torch_threads=4,
        official_framework_forward=True,rtl_execution=False,hardware_recipe_acceptance=False,
        logits=False,full_model_quality=False,policy=policy,identity=identity,
        arithmetic={'independent_qkv':recipe,'PRIVATE':'/private/sentinel?secret=DO_NOT_LEAK'},
        payload_manifest_sha256='f'*64,m16_gate_sha256=None if tokens==16 else '1'*64,modes={})
    for mode in ('bf16','fp32'):
        observed={}
        for name in stages:
            shape=shapes[name]
            item=dict(shape=shape,elements=__import__('math').prod(shape),max_abs=0.0,mean_abs=0.0,finite=True,bit_exact=True,
                actual_f32_sha256='2'*64,reference_f32_sha256='3'*64)
            if mode=='bf16' and name=='gate' and cause=='budget':item.update(max_abs=0.0625,bit_exact=False)
            item.update(funcs['stage_verdict'](name,item,mode,policy))
            for kind in ('native','independent'):
                item[kind+'_file']=f'{mode}/phase_0/{kind}_{name}.f32le'
                item[kind+'_export_shape']=[shape[0],shape[2],shape[1]*shape[3]] if name in ('q','k') else shape
                item[kind+'_file_sha256']='2'*64 if kind=='native' else '3'*64
            observed[name]=item
        semantic={key:True for key in phase.SEMANTICS}
        if cause==mode+'_semantics':semantic['independent_future_probability_zero']=False
        failed=[name for name in stages if observed[name]['passed'] is False];exact=all(semantic.values())
        status=('PASS_BF16_STAGE_BUDGET' if not failed and exact else 'FAIL_BF16_STAGE_BUDGET') if mode=='bf16' else ('DIAGNOSTIC_FP32' if exact else 'FAIL_FP32_SEMANTICS')
        value['modes'][mode]={'phases':[dict(phase=0,past_tokens=0,token_ids=list(range(tokens)),position_ids=list(range(tokens)),
            stages=observed,semantics=semantic,failed_stages=failed,all_semantics_exact=exact,status=status)]}
    value['status']='PASS_BF16_STAGE_BUDGET' if cause is None else 'FAIL_BF16_STAGE_BUDGET'
    kwargs=dict(tokens=tokens,result_sha256='4'*64,source_sha256=sources,contract_sha256='5'*64,
        generated_module_sha256='e'*64,library=library,qkv_library=qkv_library,
        payload_manifest_sha256='f'*64,m16_result_sha256=value['m16_gate_sha256'])
    return value,kwargs


def report_fixture(tokens=16,cause=None):
    value,kwargs=fixture(tokens,cause)
    return phase.project_result(value,**kwargs)


def diagnostic_controls():
    """Metadata only; no CPU probe, library load, or numerical package import."""
    from . import dispatch_diagnostic as diagnostic
    line=(b'onednn_verbose,v1,primitive,exec,cpu,matmul,brg_matmul:avx512_core_bf16,undef,'
        b'src:bf16::blocked:ab::f0 wei:bf16::blocked:ab::f0 dst:bf16::blocked:ab::f0,'
        b'attr-scratchpad:user,,16x1536:1536x256,0.01\n')
    verbose=diagnostic.parse_verbose(line)
    cpu=diagnostic.cpu_features(('processor : 0\nflags : '+' '.join(diagnostic.FLAGS)+'\n').encode())
    snapshot=dict(status='OBSERVED',x87_round=0,sse_round=0,ftz=False,daz=False)
    environment=dict(libraries={key:dict(snapshot) for key in ('before','after_qkv','after_qk')},
        **{key:dict(snapshot) for key in ('before_recipe','after_recipe','after_gate')})
    tree=ast.parse(kernel.source(kernel.ORIGINAL))
    sources=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and
        any(isinstance(t,ast.Name) and t.id=='SOURCE_HASHES' for t in n.targets)))
    backend=dict(torch_build='PRIVATE torch build /token?DO_NOT_LEAK',numpy_build='PRIVATE numpy config',
        source_sha256=sources,installed_sources_verified_exact=True)
    manifest={'tensors':[dict(local_name=name,shape=shape,dtype='BF16',sha256='9'*64)
        for name,shape in diagnostic.PAYLOAD_SHAPES.items()]}
    return dict(bf16=verbose,fp32=copy.deepcopy(verbose)),cpu,environment,backend,manifest


def diagnostics_fixture(tokens=16,cause=None):
    value,kwargs=fixture(tokens,cause);report=phase.project_result(value,**kwargs)
    observed,cpu,environment,backend,manifest=diagnostic_controls()
    context={key:kwargs[key] for key in ('source_sha256','contract_sha256','generated_module_sha256')}
    return phase.diagnostic_record(context,tokens,kwargs['library'],kwargs['qkv_library'],observed,
        cpu,phase.backend_build(backend),environment,(value,report,manifest))


class ProjectionTests(unittest.TestCase):
    def test_complete_diagnostics_bind_hashes_without_changing_numeric_report(self):
        for tokens in (16,128):
            for cause in (None,'budget','bf16_semantics','fp32_semantics'):
                with self.subTest(tokens=tokens,cause=cause):
                    before=report_fixture(tokens,cause)
                    observed=diagnostics_fixture(tokens,cause)
                    self.assertEqual(observed['status'],'COMPLETE_DIAGNOSTICS')
                    self.assertIs(observed['numerical_acceptance'],False)
                    self.assertIs(observed['postflight_complete'],True)
                    self.assertEqual(observed['result_sha256'],before['result_sha256'])
                    self.assertEqual(observed['payload_tensor_map_sha256'],kernel.sha(kernel.encoded(observed['payload_sha256'])))
                    self.assertEqual(set(observed['payload_sha256']),set(diagnostic_controls()[-1]['tensors'][i]['local_name'] for i in range(13)))
                    self.assertEqual(len(observed['stage_sha256']['bf16']),29)
                    self.assertEqual(phase.validate_diagnostics(json.loads(json.dumps(observed))),observed)
                    self.assertNotIn('PRIVATE',kernel.encoded(observed).decode())
                    self.assertEqual(before,report_fixture(tokens,cause))

    def test_diagnostic_schema_privacy_type_fenv_and_identity_negatives(self):
        for case in ('path','backend_text','backend_commit','backend_bool','payload','stage','metric','acceptance','change','fenv_bool','result','capture','postflight','payload_map_hash'):
            value=diagnostics_fixture()
            if case=='path':value['private_path']='/private/log'
            elif case=='backend_text':value['backend_build']['torch_build']='private config'
            elif case=='backend_commit':value['backend_build']['torch_commit']='0'*40
            elif case=='backend_bool':value['backend_build']['installed_sources_verified_exact']=1
            elif case=='payload':value['payload_sha256']['unexpected']='0'*64
            elif case=='stage':value['stage_sha256']['bf16']['q']['actual_f32_sha256']='private'
            elif case=='metric':value['stage_sha256']['bf16']['q']['max_abs']=0
            elif case=='acceptance':value['numerical_acceptance']=True
            elif case=='change':value['fenv_changes']['qkv_load']=True
            elif case=='fenv_bool':value['fenv']['before_recipe']['ftz']=0
            elif case=='result':value['result_sha256']=None
            elif case=='postflight':value['postflight_complete']=False
            elif case=='payload_map_hash':value['payload_tensor_map_sha256']='0'*64
            else:value['capture']['bf16']['error']='secret'
            with self.subTest(case=case),self.assertRaises(ValueError):phase.validate_diagnostics(value)

    def test_unknown_observations_and_partial_exceptions_never_complete(self):
        from . import dispatch_diagnostic
        for missing in ('capture','cpu','fenv','backend'):
            value=diagnostics_fixture()
            if missing=='capture':value['capture']['bf16']=dispatch_diagnostic.parse_verbose(b'')
            elif missing=='cpu':value['cpu']=None
            elif missing=='fenv':
                value['fenv']['after_gate']={'status':'UNSUPPORTED'}
                value['fenv_changes']=phase.fenv_changes(value['fenv'])
            else:value['backend_build']=None
            with self.subTest(missing=missing),self.assertRaises(ValueError):phase.validate_diagnostics(value)
            value['status']='INCOMPLETE_DIAGNOSTICS';phase.validate_diagnostics(value)
        value,kwargs=fixture();observed,cpu,environment,backend,_=diagnostic_controls()
        context={key:kwargs[key] for key in ('source_sha256','contract_sha256','generated_module_sha256')}
        partial=phase.diagnostic_record(context,16,kwargs['library'],kwargs['qkv_library'],observed,cpu,
            phase.backend_build(backend),environment)
        self.assertEqual(partial['status'],'INCOMPLETE_DIAGNOSTICS')
        self.assertIsNone(partial['result_sha256']);self.assertIsNone(partial['payload_sha256'])
        self.assertIsNone(partial['payload_tensor_map_sha256'])
        self.assertIs(partial['postflight_complete'],False)

    def test_completed_fp32_absence_is_diagnostic_without_backend_or_acceptance_claim(self):
        from . import dispatch_diagnostic
        for tokens in (16,128):
            for cause in (None,'budget','bf16_semantics','fp32_semantics'):
                value=diagnostics_fixture(tokens,cause)
                value['capture']['fp32']=dispatch_diagnostic.parse_verbose(b'')
                checked=phase.validate_diagnostics(value)
                self.assertEqual(checked['status'],'COMPLETE_DIAGNOSTICS')
                self.assertEqual(checked['capture']['fp32']['status'],'NO_ONEDNN_EXECUTION_OBSERVED')
                self.assertIs(checked['backend_order_proven'],False)
                self.assertIs(checked['numerical_acceptance'],False)
                self.assertIs(report_fixture(tokens,cause)['native_acceptance'],cause is None)
        value,kwargs=fixture();observed,cpu,environment,backend,_=diagnostic_controls()
        observed['fp32']=dispatch_diagnostic.parse_verbose(b'')
        context={key:kwargs[key] for key in ('source_sha256','contract_sha256','generated_module_sha256')}
        partial=phase.diagnostic_record(context,16,kwargs['library'],kwargs['qkv_library'],observed,
            cpu,phase.backend_build(backend),environment)
        self.assertEqual(partial['status'],'INCOMPLETE_DIAGNOSTICS')
        self.assertIs(partial['postflight_complete'],False)
        self.assertIsNone(partial['result_sha256'])

    def test_absent_bf16_unknown_malformed_or_truncated_capture_cannot_complete(self):
        from . import dispatch_diagnostic
        for mode in ('bf16','fp32'):
            for raw,truncated in ((b'onednn_verbose,v1,info,PRIVATE_UNKNOWN\n',False),
                                  (b'malformed private text\n',False),(b'',True)):
                value=diagnostics_fixture()
                value['capture'][mode]=dispatch_diagnostic.parse_verbose(raw,truncated=truncated)
                with self.subTest(mode=mode,raw=raw,truncated=truncated),self.assertRaises(ValueError):
                    phase.validate_diagnostics(value)
                value['status']='INCOMPLETE_DIAGNOSTICS';phase.validate_diagnostics(value)
        value=diagnostics_fixture();value['capture']['bf16']=dispatch_diagnostic.parse_verbose(b'')
        with self.assertRaises(ValueError):phase.validate_diagnostics(value)
        value['status']='INCOMPLETE_DIAGNOSTICS';phase.validate_diagnostics(value)

    def test_combined_identity_matches_frozen_adapter_schema_and_binds_both_receipts(self):
        value,kwargs=fixture();library=kwargs['library'];qkv_library=kwargs['qkv_library']
        source=kernel.source(kernel.PREFIX+'adapter.py')
        tree=ast.parse(source);recipe=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Recipe')
        method=next(n for n in recipe.body if isinstance(n,ast.FunctionDef) and n.name=='identity')
        namespace={'PROFILE':kernel.PROFILE}
        exec(compile(ast.Module(body=[method],type_ignores=[]),'CONTROL_ONLY_adapter_identity','exec'),namespace)
        expected_qkv=dict(profile=qkv_kernel.PROFILE,library_sha256=qkv_library['library_sha256'],
            source_sha256=qkv_library['source_sha256'],pins_sha256=qkv_library['pins_sha256'])
        control=types.SimpleNamespace(receipt=library,revalidate=Mock(),
            qkv=types.SimpleNamespace(identity=lambda:expected_qkv))
        self.assertEqual(namespace['identity'](control),phase.combined_identity(library,qkv_library))
        for role in ('library','qkv_library'):
            for key in ('library_sha256','source_sha256','pins_sha256'):
                changed=copy.deepcopy(kwargs)
                changed[role][key]={'foreign':'0'*64} if key=='source_sha256' else '0'*64
                with self.subTest(role=role,key=key),self.assertRaises(ValueError):phase.project_result(value,**changed)
        value['identity']['independent_qkv_recipe']['backend_order_proven']=True
        with self.assertRaises(ValueError):phase.project_result(value,**kwargs)

    def test_original_inventory_and_policy_helpers_are_source_bound(self):
        tree=ast.parse(kernel.source(kernel.ORIGINAL))
        gate=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run_gate')
        semantic=next(n.value for n in ast.walk(gate) if isinstance(n,ast.Assign) and
            any(isinstance(t,ast.Name) and t.id=='semantic' for t in n.targets))
        self.assertEqual({ast.literal_eval(k) for k in semantic.keys},set(phase.SEMANTICS))
        self.assertEqual(len(phase.helpers()[1]),29)
        with patch.object(kernel,'source',return_value=b'mutated'),self.assertRaises(ValueError):phase.helpers()

    def test_both_sizes_pass_and_all_three_failure_classes_remain_visible(self):
        for tokens in (16,128):
            for cause in (None,'budget','bf16_semantics','fp32_semantics'):
                with self.subTest(tokens=tokens,cause=cause):
                    value=report_fixture(tokens,cause)
                    self.assertIs(value['native_acceptance'],cause is None)
                    self.assertEqual(value['assigned_bf16_checks'],28)
                    self.assertIs(value['backend_order_proven'],False)
                    self.assertEqual(value['qkv_library_sha256'],'6'*64)
                    self.assertIsNone(value['bf16_stages']['softmax_fp32']['passed'])
                    self.assertEqual(len(value['bf16_stages']),29)
                    self.assertLessEqual(len(kernel.encoded(value)),phase.MAX_REPORT)
                    self.assertNotIn('DO_NOT_LEAK',kernel.encoded(value).decode())
                    self.assertEqual(phase.validate_report(json.loads(json.dumps(value))),value)

    def test_original_receipt_identity_type_and_false_verdict_negatives(self):
        for change in ('tokens','phase','ids','shape','elements','metric','finite','passed','limits','status','identity','recipe','semantics','inventory','small'):
            value,kwargs=fixture(128);item=value['modes']['bf16']['phases'][0];stage=item['stages']['gate']
            if change=='tokens':value['tokens']=128.0
            elif change=='phase':item['phase']=False
            elif change=='ids':item['token_ids'][0]=False
            elif change=='shape':stage['shape'][0]=True
            elif change=='elements':stage['elements']=float(stage['elements'])
            elif change=='metric':stage['max_abs']=True
            elif change=='finite':stage['finite']=1
            elif change=='passed':stage['passed']=1
            elif change=='limits':stage['limits']={'max_abs':99.0,'mean_abs':99.0}
            elif change=='status':value['status']='PASS_FROM_HISTORY'
            elif change=='identity':value['identity']['runner_sha256']='0'*64
            elif change=='recipe':value['arithmetic']['independent_qkv']={}
            elif change=='semantics':item['semantics']['mask_exact']=1
            elif change=='inventory':del item['stages']['qr']
            else:value['m16_gate_sha256']=None
            with self.subTest(change=change),self.assertRaises((ValueError,TypeError)):phase.project_result(value,**kwargs)

    def test_safe_report_rejects_private_fields_nonfinite_and_alias_types(self):
        for change in ('path','class','count','metric','inf','acceptance','limits','missing','fake_pass','unknown_stage','backend','qkv_hash'):
            value=report_fixture(128,'budget')
            if change=='path':value['path']='/private/payload'
            elif change=='class':value['error']='secret'
            elif change=='count':value['assigned_bf16_checks']=28.0
            elif change=='metric':value['bf16_stages']['gate']['mean_abs']=False
            elif change=='inf':value['bf16_stages']['gate']['max_abs']=float('inf')
            elif change=='acceptance':value['native_acceptance']=0
            elif change=='limits':value['approved_limits']['operator']['max_abs']=100
            elif change=='missing':del value['modes']['fp32']['semantics']['mask_exact']
            elif change=='unknown_stage':value['bf16_stages']['private']='secret'
            elif change=='backend':value['backend_order_proven']=0
            elif change=='qkv_hash':value['qkv_recipe_pins_sha256']='private/path'
            else:value.update(status='COMPLETE_NATIVE_VALIDATION',native_status='PASS_BF16_STAGE_BUDGET',native_acceptance=True)
            with self.subTest(change=change),self.assertRaises((ValueError,TypeError)):phase.validate_report(value)

    def test_json_roundtrip_preserves_tuple_compatibility_without_bool_int_aliases(self):
        self.assertTrue(phase.same(phase.canonical({'x':((1,2),)}),{'x':[[1,2]]}))
        self.assertFalse(phase.same({'x':True},{'x':1}))
        self.assertFalse(phase.same({'x':1.0},{'x':1}))
        for item in (float('inf'),float('nan')):
            with self.assertRaises(ValueError):phase.canonical({'x':item})

    def test_tiny_control_only_export_hash_path_shape_and_alias_checks(self):
        # Geometry is reduced to one scalar solely for filesystem-validation tests.
        value,_=fixture();stages=phase.helpers()[1]
        shapes={n:([1,1,1,1] if n in ('q','k') else [1]) for n in stages}
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for mode in ('bf16','fp32'):
                for name,item in value['modes'][mode]['phases'][0]['stages'].items():
                    for kind in ('native','independent'):
                        path=root/item[kind+'_file'];path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'\0'*4)
                        item[kind+'_export_shape']=[1,1,1] if name in ('q','k') else [1]
                        item[kind+'_file_sha256']=kernel.sha(b'\0'*4)
                    item['actual_f32_sha256']=item['reference_f32_sha256']=kernel.sha(b'\0'*4)
            with patch.object(phase,'helpers',return_value=({'expected_shapes':lambda *args:shapes},stages,{})):
                phase.verify_exports(value,root,16)
                target=value['modes']['bf16']['phases'][0]['stages']['x'];path=root/target['native_file']
                path.write_bytes(b'bad!')
                with self.assertRaises(ValueError):phase.verify_exports(value,root,16)
                path.write_bytes(b'\0'*4);target['native_file']='../escape'
                with self.assertRaises(ValueError):phase.verify_exports(value,root,16)
                target['native_file']='bf16/phase_0/native_x.f32le';path.unlink()
                path.hardlink_to(root/target['independent_file'])
                with self.assertRaises(ValueError):phase.verify_exports(value,root,16)


class PhaseControlTests(unittest.TestCase):
    def harness(self,temp,cause=None):
        import candidates.qwen2_resident_matrix.raw_kv_native_qk_run as package
        import candidates.qwen2_resident_matrix.raw_kv_public_fresh as fresh
        observed,cpu,environment,backend,manifest=diagnostic_controls()
        payload_raw=kernel.encoded(manifest)
        root=Path(temp);(root/'payload').mkdir();(root/'payload/manifest.json').write_bytes(payload_raw)
        generated=root/'generated/scripts/qwen2_layer0_model_gate.py';generated.parent.mkdir(parents=True);generated.write_bytes(b'# CONTROL_ONLY')
        _,kwargs=fixture();sources=kwargs['source_sha256'];library=kwargs['library'];qkv_library=kwargs['qkv_library']
        start=phase.time.monotonic_ns()
        context=dict(schema=1,profile='CONTROL_ONLY',workspace=str(root),checkout_commit='0'*40,source_sha256=sources,
            contract_sha256=kwargs['contract_sha256'],start_ns=start,deadline_ns=start+900*10**9,
            generated_module=str(generated),generated_module_sha256=kernel.sha(generated.read_bytes()))
        runtime=types.SimpleNamespace(read_context=Mock(return_value=(context,root)),source_snapshot=Mock(return_value=sources),remaining=Mock(return_value=1))
        recipe=Mock();identity=phase.combined_identity(library,qkv_library)
        recipe.identity.return_value=identity
        native=types.SimpleNamespace()
        native.runtime_identity=lambda root:(None,{'runner_sha256':context['generated_module_sha256']})
        def run_gate(repo,payload,out,tokens,*,carried,threads,small_gate,qkv_recipe,diagnostics):
            self.assertEqual((repo,payload,carried,threads,qkv_recipe),(phase.ROOT,root/'payload',False,4,recipe))
            self.assertIs(diagnostics,native.capture)
            value,_=fixture(tokens,cause)
            value['identity']['runner_sha256']=context['generated_module_sha256']
            value['payload_manifest_sha256']=kernel.sha(payload_raw)
            value['m16_gate_sha256']=kernel.sha(small_gate.read_bytes()) if small_gate else None
            out.mkdir();(out/'RESULT.json').write_bytes(kernel.encoded(value))
            return value
        native.run_gate=Mock(side_effect=run_gate)
        native.capture=Mock();native.capture.report.return_value=observed
        native.cpu=cpu;native.environment=environment
        library['library_path']='/CONTROL_ONLY/qk.so';qkv_library['library_path']='/CONTROL_ONLY/qkv.so'
        setup=types.SimpleNamespace(IMPORTED_SETUP_SHA256='a'*64,backend_identity=Mock(return_value=('TORCH_CONTROL_ONLY',backend)),backend_threads=Mock())
        adapter=types.ModuleType('candidates.qwen2_resident_matrix.raw_kv_native_qk.adapter');adapter.Recipe=Mock(return_value=recipe)
        return package,fresh,root,context,runtime,native,setup,adapter,library,qkv_library

    def invoke(self,parts,name,*,qk_verify=None,qkv_verify=None):
        package,fresh,root,context,runtime,native,setup,adapter,library,qkv_library=parts
        from . import dispatch_capture
        from contextlib import ExitStack
        with ExitStack() as stack:
            stack.enter_context(patch.dict(phase.os.environ,{'QWEN2_NATIVE_QK_PHASE_END_NS':str(context['start_ns']+phase.PHASE_CAPS[name]*10**9)}))
            stack.enter_context(patch.object(package,'runtime',runtime,create=True))
            stack.enter_context(patch.object(fresh,'setup',setup,create=True))
            stack.enter_context(patch.dict(sys.modules,{adapter.__name__:adapter}))
            stack.enter_context(patch.object(phase,'_generated',return_value=native))
            stack.enter_context(patch.object(kernel,'verify',return_value=library,side_effect=qk_verify))
            stack.enter_context(patch.object(qkv_kernel,'verify',return_value=qkv_library,side_effect=qkv_verify))
            stack.enter_context(patch.object(phase,'verify_exports'))
            stack.enter_context(patch.object(dispatch_capture,'Capture',return_value=native.capture))
            stack.enter_context(patch.object(dispatch_capture,'library_fenv',return_value=native.environment['libraries']))
            stack.enter_context(patch.object(dispatch_capture,'fenv_snapshot',return_value=native.environment['before_recipe']))
            stack.enter_context(patch.object(phase,'read_cpu_features',return_value=native.cpu))
            return phase.run(name,root/'validation_context.json')

    def test_separate_native_phases_bind_real_m16_result_and_safe_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            parts=self.harness(temp)
            self.assertEqual(self.invoke(parts,'native16'),0)
            self.assertEqual(self.invoke(parts,'native128'),0)
            root=parts[2];report=phase.validate_report(kernel.json_bytes((root/'phase_native128.json').read_bytes()))
            self.assertEqual(report['m16_result_sha256'],kernel.sha((root/'native16/RESULT.json').read_bytes()))
            self.assertEqual(parts[5].run_gate.call_count,2)
            self.assertEqual(parts[6].backend_threads.call_count,2)
            parts[7].Recipe.assert_called_with(root/'qkv_library',root/'qk_library')

    def test_authentic_failure_writes_bounded_receipt_and_blocks_native128(self):
        for cause in ('budget','bf16_semantics','fp32_semantics'):
            with self.subTest(cause=cause),tempfile.TemporaryDirectory() as temp:
                parts=self.harness(temp,cause)
                self.assertEqual(self.invoke(parts,'native16'),1)
                value=phase.validate_report(kernel.json_bytes((parts[2]/'phase_native16.json').read_bytes()))
                self.assertFalse(value['native_acceptance'])
                observation=phase.validate_diagnostics(kernel.json_bytes((parts[2]/'phase_native16_diagnostics.json').read_bytes()))
                self.assertEqual(observation['status'],'COMPLETE_DIAGNOSTICS')
                with self.assertRaises(ValueError):self.invoke(parts,'native128')
                self.assertEqual(parts[5].run_gate.call_count,1)

    def test_absent_bf16_keeps_genuine_pass_report_but_blocks_phase_and_m128(self):
        from . import dispatch_diagnostic
        with tempfile.TemporaryDirectory() as temp:
            parts=self.harness(temp)
            parts[5].capture.report.return_value['bf16']=dispatch_diagnostic.parse_verbose(b'')
            self.assertEqual(self.invoke(parts,'native16'),1)
            report=phase.validate_report(kernel.json_bytes((parts[2]/'phase_native16.json').read_bytes()))
            observation=phase.validate_diagnostics(kernel.json_bytes((parts[2]/'phase_native16_diagnostics.json').read_bytes()))
            self.assertTrue(report['native_acceptance']);self.assertEqual(observation['status'],'INCOMPLETE_DIAGNOSTICS')
            with self.assertRaises(ValueError):self.invoke(parts,'native128')
            self.assertEqual(parts[5].run_gate.call_count,1)

    def test_completed_fp32_absence_allows_both_phases_with_no_backend_proof(self):
        from . import dispatch_diagnostic
        with tempfile.TemporaryDirectory() as temp:
            parts=self.harness(temp)
            parts[5].capture.report.return_value['fp32']=dispatch_diagnostic.parse_verbose(b'')
            for name in ('native16','native128'):
                self.assertEqual(self.invoke(parts,name),0)
                observation=phase.validate_diagnostics(kernel.json_bytes((parts[2]/('phase_'+name+'_diagnostics.json')).read_bytes()))
                self.assertEqual(observation['status'],'COMPLETE_DIAGNOSTICS')
                self.assertIs(observation['postflight_complete'],True)
                self.assertIs(observation['numerical_acceptance'],False)
                self.assertIs(observation['backend_order_proven'],False)

    def test_native_exception_retains_partial_observations_without_text(self):
        from . import dispatch_diagnostic
        with tempfile.TemporaryDirectory() as temp:
            parts=self.harness(temp);failure=RuntimeError('PRIVATE token /private/path')
            parts[5].capture.report.return_value['fp32']=dispatch_diagnostic.parse_verbose(b'')
            parts[5].run_gate.side_effect=failure
            with self.assertRaises(RuntimeError) as caught:self.invoke(parts,'native16')
            self.assertIs(caught.exception,failure)
            path=parts[2]/'phase_native16_diagnostics.json';raw=path.read_bytes()
            value=phase.validate_diagnostics(kernel.json_bytes(raw))
            self.assertEqual(value['status'],'INCOMPLETE_DIAGNOSTICS')
            self.assertFalse(value['postflight_complete']);self.assertIsNone(value['result_sha256'])
            self.assertNotIn(b'PRIVATE',raw);self.assertNotIn(b'/private',raw)
            self.assertFalse((parts[2]/'phase_native16.json').exists())

    def test_failed_capture_report_retains_other_bounded_observations(self):
        with tempfile.TemporaryDirectory() as temp:
            parts=self.harness(temp);failure=RuntimeError('PRIVATE capture failure')
            parts[5].capture.report.side_effect=failure
            with self.assertRaises(RuntimeError) as caught:self.invoke(parts,'native16')
            self.assertIs(caught.exception,failure)
            value=phase.validate_diagnostics(kernel.json_bytes((parts[2]/'phase_native16_diagnostics.json').read_bytes()))
            self.assertEqual(value['status'],'INCOMPLETE_DIAGNOSTICS');self.assertIsNone(value['capture'])
            self.assertIsNotNone(value['backend_build']);self.assertIsNone(value['result_sha256'])
            # The genuine numerical verdict was already committed and survives.
            numerical=phase.validate_report(kernel.json_bytes((parts[2]/'phase_native16.json').read_bytes()))
            self.assertTrue(numerical['native_acceptance'])

    def test_either_library_rejection_or_postflight_drift_blocks_receipt(self):
        for role in ('qk','qkv'):
            with self.subTest(role=role,when='before'),tempfile.TemporaryDirectory() as temp:
                parts=self.harness(temp)
                options={role+'_verify':ValueError('CONTROL_ONLY receipt rejection')}
                with self.assertRaises(ValueError):self.invoke(parts,'native16',**options)
                parts[5].run_gate.assert_not_called()
                self.assertFalse((parts[2]/'phase_native16.json').exists())
            with self.subTest(role=role,when='after'),tempfile.TemporaryDirectory() as temp:
                parts=self.harness(temp);receipt=parts[8 if role=='qk' else 9]
                options={role+'_verify':[receipt,dict(receipt,library_sha256='0'*64)]}
                with self.assertRaises(ValueError):self.invoke(parts,'native16',**options)
                self.assertEqual(parts[5].run_gate.call_count,1)
                self.assertFalse((parts[2]/'phase_native16.json').exists())

    def test_native128_rejects_each_qkv_m16_hash_mismatch(self):
        for key in ('qkv_library_sha256','qkv_library_receipt_sha256','qkv_recipe_pins_sha256'):
            with self.subTest(key=key),tempfile.TemporaryDirectory() as temp:
                parts=self.harness(temp);self.assertEqual(self.invoke(parts,'native16'),0)
                path=parts[2]/'phase_native16.json';value=kernel.json_bytes(path.read_bytes())
                value[key]='0'*64;path.write_bytes(kernel.encoded(value))
                with self.assertRaises(ValueError):self.invoke(parts,'native128')
                self.assertEqual(parts[5].run_gate.call_count,1)
                self.assertFalse((parts[2]/'phase_native128.json').exists())

    def test_deadline_and_source_drift_cannot_start_native_or_publish_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            parts=self.harness(temp);parts[4].remaining.side_effect=TimeoutError()
            with self.assertRaises(TimeoutError):self.invoke(parts,'native16')
            parts[5].run_gate.assert_not_called()
            self.assertFalse((parts[2]/'phase_native16.json').exists())
        with tempfile.TemporaryDirectory() as temp:
            parts=self.harness(temp);sources=parts[3]['source_sha256']
            parts[4].source_snapshot.side_effect=[sources,dict(sources,unexpected='0'*64)]
            with self.assertRaises(ValueError):self.invoke(parts,'native16')
            self.assertFalse((parts[2]/'phase_native16.json').exists())

    def test_kernel_dispatch_verifies_both_without_compiling(self):
        with tempfile.TemporaryDirectory() as temp:
            parts=self.harness(temp)
            with patch.object(kernel,'build') as build,patch.object(qkv_kernel,'build') as old_build:
                self.assertEqual(self.invoke(parts,'kernel'),0)
            build.assert_not_called();old_build.assert_not_called()
            parts[5].run_gate.assert_not_called()
            report=phase.validate_kernel_report(kernel.json_bytes((parts[2]/'phase_kernel.json').read_bytes()))
            self.assertIs(report['numerical_execution'],False)
            self.assertIs(report['backend_order_proven'],False)
            self.assertEqual(report['qkv_library_receipt_sha256'],'7'*64)
            for update in ({'path':'/private'},{'numerical_execution':0},{'schema':True},{'backend_order_proven':True}):
                with self.assertRaises(ValueError):phase.validate_kernel_report(dict(report,**update))

    def test_returned_and_disk_type_mismatch_cannot_publish_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            parts=self.harness(temp);original=parts[5].run_gate.side_effect
            def changed(*args,**kwargs):
                value=original(*args,**kwargs);value['modes']['bf16']['phases'][0]['phase']=False
                return value
            parts[5].run_gate.side_effect=changed
            with self.assertRaises(ValueError):self.invoke(parts,'native16')
            self.assertFalse((parts[2]/'phase_native16.json').exists())

    def test_generated_loader_uses_checked_bytes_and_rejects_inside_checkout(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'generated.py';path.write_bytes(b'CONTROL_ONLY = 17\n')
            module=phase._generated(path,kernel.sha(path.read_bytes()))
            self.assertEqual(module.CONTROL_ONLY,17)
            with self.assertRaises(ValueError):phase._generated(path,'0'*64)
        with self.assertRaises(ValueError):phase._generated(phase.ROOT/phase.SOURCE,phase.IMPORTED_SHA256)

    def test_canonical_phase_deadline_and_postflight_expiry(self):
        with patch.object(phase.time,'monotonic_ns',return_value=100*10**9):
            context={'deadline_ns':200*10**9}
            for raw in ('', '00110000000000','+110000000000','110.0','100000000000','201000000000','131000000000'):
                with self.subTest(raw=raw),patch.dict(phase.os.environ,{'QWEN2_NATIVE_QK_PHASE_END_NS':raw}),self.assertRaises(ValueError):
                    phase.phase_deadline(context,'kernel')
            with patch.dict(phase.os.environ,{'QWEN2_NATIVE_QK_PHASE_END_NS':'130000000000'}):
                self.assertEqual(phase.phase_deadline(context,'kernel'),130*10**9)
        with tempfile.TemporaryDirectory() as temp:
            parts=self.harness(temp);clock=[parts[3]['start_ns']]
            original=parts[4].source_snapshot.return_value;calls=[0]
            def late_snapshot():
                calls[0]+=1
                if calls[0]==2:clock[0]+=55*10**9
                return original
            parts[4].source_snapshot.side_effect=late_snapshot
            with patch.object(phase.time,'monotonic_ns',side_effect=lambda:clock[0]):
                with self.assertRaises(TimeoutError):self.invoke(parts,'native16')
            self.assertFalse((parts[2]/'phase_native16.json').exists())

    def test_main_safe_failure_diagnostic_has_no_exception_text(self):
        from ..raw_kv_public_fresh import setup
        import candidates.qwen2_resident_matrix.raw_kv_native_qk_run as package
        with tempfile.TemporaryDirectory() as temp:
            parts=self.harness(temp);context=parts[3];end=context['start_ns']+30*10**9
            argv=['phase','--phase','kernel','--context',str(parts[2]/'validation_context.json')]
            with patch.object(package,'runtime',parts[4],create=True),patch.object(sys,'argv',argv), \
                    patch.dict(phase.os.environ,{'QWEN2_NATIVE_QK_PHASE_END_NS':str(end)}), \
                    patch.object(phase,'run',side_effect=ValueError('/private/token?secret=DO_NOT_LEAK')):
                self.assertEqual(phase.main(),1)
            raw=(parts[2]/'kernel.failure.json').read_bytes();value=kernel.json_bytes(raw)
            self.assertNotIn(b'DO_NOT_LEAK',raw);self.assertNotIn(b'/private',raw)
            self.assertEqual(value['phase'],'kernel');self.assertEqual(value['exception'],'ValueError')
            value['phase']='preflight';setup.validate_diagnostic(value,'preflight',context['source_sha256'])


if __name__=='__main__':unittest.main()
