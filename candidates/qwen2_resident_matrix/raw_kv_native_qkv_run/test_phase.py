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
from ..raw_kv_native_qkv import kernel


def fixture(tokens=16,cause=None):
    """Source-derived original receipt metadata; all tensor hashes are synthetic."""
    funcs,stages,policy=phase.helpers();shapes=funcs['expected_shapes'](phase.CONFIG,tokens,0)
    sources={kernel.ORIGINAL:kernel.FIXED[kernel.ORIGINAL],phase.SOURCE:phase.IMPORTED_SHA256,
        'candidates/qwen2_resident_matrix/raw_kv_public_fresh/setup.py':'a'*64}
    library=dict(library_sha256='b'*64,receipt_sha256='c'*64,source_sha256={kernel.ORIGINAL:kernel.FIXED[kernel.ORIGINAL]},pins_sha256='d'*64)
    recipe=dict(profile=kernel.PROFILE,library_sha256=library['library_sha256'],source_sha256=library['source_sha256'],pins_sha256=library['pins_sha256'])
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
        generated_module_sha256='e'*64,library=library,payload_manifest_sha256='f'*64,m16_result_sha256=value['m16_gate_sha256'])
    return value,kwargs


def report_fixture(tokens=16,cause=None):
    value,kwargs=fixture(tokens,cause)
    return phase.project_result(value,**kwargs)


class ProjectionTests(unittest.TestCase):
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
        for change in ('path','class','count','metric','inf','acceptance','limits','missing','fake_pass','unknown_stage'):
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
        import candidates.qwen2_resident_matrix.raw_kv_native_qkv_run as package
        import candidates.qwen2_resident_matrix.raw_kv_public_fresh as fresh
        root=Path(temp);(root/'payload').mkdir();(root/'payload/manifest.json').write_bytes(b'{}')
        generated=root/'generated/scripts/qwen2_layer0_model_gate.py';generated.parent.mkdir(parents=True);generated.write_bytes(b'# CONTROL_ONLY')
        _,kwargs=fixture();sources=kwargs['source_sha256'];library=kwargs['library']
        start=phase.time.monotonic_ns()
        context=dict(schema=1,profile='CONTROL_ONLY',workspace=str(root),checkout_commit='0'*40,source_sha256=sources,
            contract_sha256=kwargs['contract_sha256'],start_ns=start,deadline_ns=start+900*10**9,
            generated_module=str(generated),generated_module_sha256=kernel.sha(generated.read_bytes()))
        runtime=types.SimpleNamespace(read_context=Mock(return_value=(context,root)),source_snapshot=Mock(return_value=sources),remaining=Mock(return_value=1))
        recipe=Mock();identity=dict(profile=kernel.PROFILE,library_sha256=library['library_sha256'],source_sha256=library['source_sha256'],pins_sha256=library['pins_sha256'])
        recipe.identity.return_value=identity
        native=types.SimpleNamespace()
        native.runtime_identity=lambda root:(None,{'runner_sha256':context['generated_module_sha256']})
        def run_gate(repo,payload,out,tokens,*,carried,threads,small_gate,qkv_recipe):
            self.assertEqual((repo,payload,carried,threads,qkv_recipe),(phase.ROOT,root/'payload',False,4,recipe))
            value,_=fixture(tokens,cause)
            value['identity']['runner_sha256']=context['generated_module_sha256']
            value['payload_manifest_sha256']=kernel.sha(b'{}')
            value['m16_gate_sha256']=kernel.sha(small_gate.read_bytes()) if small_gate else None
            out.mkdir();(out/'RESULT.json').write_bytes(kernel.encoded(value))
            return value
        native.run_gate=Mock(side_effect=run_gate)
        setup=types.SimpleNamespace(IMPORTED_SETUP_SHA256='a'*64,backend_identity=Mock(return_value=('TORCH_CONTROL_ONLY',{})),backend_threads=Mock())
        adapter=types.ModuleType('candidates.qwen2_resident_matrix.raw_kv_native_qkv.adapter');adapter.Recipe=Mock(return_value=recipe)
        return package,fresh,root,context,runtime,native,setup,adapter,library

    def invoke(self,parts,name):
        package,fresh,root,context,runtime,native,setup,adapter,library=parts
        from contextlib import ExitStack
        with ExitStack() as stack:
            stack.enter_context(patch.dict(phase.os.environ,{'QWEN2_NATIVE_QKV_PHASE_END_NS':str(context['start_ns']+phase.PHASE_CAPS[name]*10**9)}))
            stack.enter_context(patch.object(package,'runtime',runtime,create=True))
            stack.enter_context(patch.object(fresh,'setup',setup,create=True))
            stack.enter_context(patch.dict(sys.modules,{adapter.__name__:adapter}))
            stack.enter_context(patch.object(phase,'_generated',return_value=native))
            stack.enter_context(patch.object(kernel,'verify',return_value=library))
            stack.enter_context(patch.object(phase,'verify_exports'))
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

    def test_authentic_failure_writes_bounded_receipt_and_blocks_native128(self):
        for cause in ('budget','bf16_semantics','fp32_semantics'):
            with self.subTest(cause=cause),tempfile.TemporaryDirectory() as temp:
                parts=self.harness(temp,cause)
                self.assertEqual(self.invoke(parts,'native16'),1)
                value=phase.validate_report(kernel.json_bytes((parts[2]/'phase_native16.json').read_bytes()))
                self.assertFalse(value['native_acceptance'])
                with self.assertRaises(ValueError):self.invoke(parts,'native128')
                self.assertEqual(parts[5].run_gate.call_count,1)

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

    def test_kernel_dispatch_is_explicit_bounded_and_non_numerical(self):
        with tempfile.TemporaryDirectory() as temp:
            parts=self.harness(temp)
            with patch.object(kernel,'build',return_value=parts[-1]) as build:
                self.assertEqual(self.invoke(parts,'kernel'),0)
            build.assert_called_once_with(parts[2]/'recipe_library',execute=True,
                deadline_ns=parts[3]['start_ns']+23*10**9)
            parts[5].run_gate.assert_not_called()
            report=phase.validate_kernel_report(kernel.json_bytes((parts[2]/'phase_kernel.json').read_bytes()))
            self.assertIs(report['numerical_execution'],False)
            for update in ({'path':'/private'},{'numerical_execution':0},{'schema':True}):
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
                with self.subTest(raw=raw),patch.dict(phase.os.environ,{'QWEN2_NATIVE_QKV_PHASE_END_NS':raw}),self.assertRaises(ValueError):
                    phase.phase_deadline(context,'kernel')
            with patch.dict(phase.os.environ,{'QWEN2_NATIVE_QKV_PHASE_END_NS':'130000000000'}):
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
        import candidates.qwen2_resident_matrix.raw_kv_native_qkv_run as package
        with tempfile.TemporaryDirectory() as temp:
            parts=self.harness(temp);context=parts[3];end=context['start_ns']+30*10**9
            argv=['phase','--phase','kernel','--context',str(parts[2]/'validation_context.json')]
            with patch.object(package,'runtime',parts[4],create=True),patch.object(sys,'argv',argv), \
                    patch.dict(phase.os.environ,{'QWEN2_NATIVE_QKV_PHASE_END_NS':str(end)}), \
                    patch.object(phase,'run',side_effect=ValueError('/private/token?secret=DO_NOT_LEAK')):
                self.assertEqual(phase.main(),1)
            raw=(parts[2]/'kernel.failure.json').read_bytes();value=kernel.json_bytes(raw)
            self.assertNotIn(b'DO_NOT_LEAK',raw);self.assertNotIn(b'/private',raw)
            self.assertEqual(value['phase'],'kernel');self.assertEqual(value['exception'],'ValueError')
            value['phase']='preflight';setup.validate_diagnostic(value,'preflight',context['source_sha256'])


if __name__=='__main__':unittest.main()
