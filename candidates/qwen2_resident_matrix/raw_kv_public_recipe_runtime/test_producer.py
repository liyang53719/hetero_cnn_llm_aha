"""Scripted metadata only: no tensor arrays, compiler, library load or native math."""
from contextlib import ExitStack
from copy import deepcopy
import ast
import builtins
import ctypes
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import types
import unittest
from unittest.mock import Mock, patch

from . import producer as P, runtime
from ..raw_kv_native_qk_run import dispatch_capture as capture
from ..raw_kv_native_qk_run import runtime as native_runtime
from ..raw_kv_native_qk_run.test_phase import fixture, diagnostic_controls
from ..raw_kv_native_qk import adapter, prepare
from ..raw_kv_public_fresh import setup


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(P.kernel.encoded(value))


class ProducerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Source composition only. Never import or execute the generated gate.
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / 'generated'
            prepare.prepare(out)
            native_runtime.apply_dispatch_patch(out, {'sources': {
                native_runtime.DISPATCH_PATCH:P.kernel.sha(native_runtime.read_source(native_runtime.DISPATCH_PATCH))}})
            cls.gate = (out / P.kernel.ORIGINAL).read_bytes()
        if P.kernel.sha(cls.gate) != P.GENERATED_SHA256:
            raise ValueError('cold source fixture drift')

    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.directory = tempfile.TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.workspace = Path(self.directory.name)
        (self.workspace / 'generated').mkdir()
        (self.workspace / 'generated/qwen2_layer0_model_gate.py').write_bytes(self.gate)
        self.sources = {P.SOURCE:P.IMPORTED_SHA256, P.phase.SOURCE:P.phase.IMPORTED_SHA256,
            P.kernel.ORIGINAL:P.qkv_kernel.FIXED[P.kernel.ORIGINAL],
            'candidates/qwen2_resident_matrix/raw_kv_public_fresh/setup.py':setup.IMPORTED_SETUP_SHA256}
        self.context = dict(schema=1, workspace=str(self.workspace), source_sha256=self.sources,
            asset_source_sha256=self.sources, enable_raw_kv=True, checkout_commit='a'*40,
            contract_sha256='b'*64, work_deadline_ns=time.monotonic_ns()+894*10**9,
            generated_module=str(self.workspace / 'generated/qwen2_layer0_model_gate.py'),
            generated_module_sha256=P.GENERATED_SHA256)
        self.library = dict(library_sha256='c'*64, receipt_sha256='d'*64, pins_sha256='e'*64,
            library_path=str(self.workspace/'qk_library'/P.kernel.LIBRARY),
            source_sha256={P.kernel.ORIGINAL:self.sources[P.kernel.ORIGINAL]})
        self.qkv_library = dict(library_sha256='f'*64, receipt_sha256='1'*64, pins_sha256='2'*64,
            library_path=str(self.workspace/'qkv_library'/P.qkv_kernel.LIBRARY),
            source_sha256={P.kernel.ORIGINAL:self.sources[P.kernel.ORIGINAL]})
        _, self.cpu, self.environment, self.backend, manifest = diagnostic_controls()
        write(self.workspace/'payload/manifest.json', manifest)
        write(self.workspace/'context.json', {'fixture':'CONTROL_ONLY; runtime admission explicitly mocked'})
        self.stack.enter_context(patch.object(runtime,'source_snapshot',side_effect=lambda:deepcopy(self.sources)))
        self.stack.enter_context(patch.object(runtime,'read_context',side_effect=lambda path:(deepcopy(self.context),self.workspace)))
        self.stack.enter_context(patch.object(runtime,'remaining',return_value=1))
        self.stack.enter_context(patch.object(P.kernel,'verify',side_effect=lambda path:deepcopy(self.library)))
        self.stack.enter_context(patch.object(P.qkv_kernel,'verify',side_effect=lambda path:deepcopy(self.qkv_library)))
        self.build = self.stack.enter_context(patch.object(P.kernel,'build',side_effect=AssertionError('native phase reached compiler')))
        self.qkv_build = self.stack.enter_context(patch.object(P.qkv_kernel,'build',side_effect=AssertionError('native phase reached compiler')))
        self.stack.enter_context(patch.object(ctypes,'CDLL',side_effect=AssertionError('cold test reached native load')))
        real_import = builtins.__import__
        def cold_import(name,*args,**kwargs):
            if name.split('.')[0] in ('numpy','torch','transformers'):
                raise AssertionError('cold test reached numerical import')
            return real_import(name,*args,**kwargs)
        self.stack.enter_context(patch.object(builtins,'__import__',side_effect=cold_import))
        self.stack.enter_context(patch.object(setup,'backend_identity',return_value=(object(),self.backend)))
        self.threads = self.stack.enter_context(patch.object(setup,'backend_threads'))
        self.stack.enter_context(patch.object(P.phase,'read_cpu_features',return_value=self.cpu))
        self.stack.enter_context(patch.object(capture,'library_fenv',return_value=self.environment['libraries']))
        self.stack.enter_context(patch.object(capture,'fenv_snapshot',return_value=self.environment['after_gate']))
        owner = self
        class ScriptedCapture:
            def __init__(self,directory,torch):
                self.tokens=16 if directory.name=='native16_dispatch' else 128
            def report(self):
                observed=diagnostic_controls(self.tokens)[0]
                if owner.diagnostic_mutation:owner.diagnostic_mutation(observed)
                return observed
        self.stack.enter_context(patch.object(capture,'Capture',ScriptedCapture))
        self.recipe=Mock()
        self.recipe.identity.side_effect=lambda:P.phase.combined_identity(self.library,self.qkv_library)
        self.stack.enter_context(patch.object(adapter,'Recipe',return_value=self.recipe))
        self.exports=self.stack.enter_context(patch.object(P.phase,'verify_exports'))
        self.calls=[];self.failure=None;self.disk_mutation=None;self.diagnostic_mutation=None
        def run_gate(root,payload,directory,tokens,**kwargs):
            self.calls.append((directory,tokens,kwargs))
            if self.failure=='raise':raise RuntimeError('SECRET /private tensor payload')
            value,_=fixture(tokens,'budget' if self.failure=='numeric' else None)
            value['identity']=dict(runner_sha256=P.GENERATED_SHA256,
                independent_qkv_recipe=self.recipe.identity())
            value['arithmetic']['independent_qkv']=self.recipe.identity()
            value['payload_manifest_sha256']=P.kernel.sha(P.kernel.read(payload/'manifest.json',1048576))
            value['m16_gate_sha256']=None if tokens==16 else P.kernel.sha(P.kernel.read(kwargs['small_gate'],1048576))
            disk=deepcopy(value)
            if self.disk_mutation:self.disk_mutation(disk)
            write(directory/'RESULT.json',disk)
            return value
        self.native=types.SimpleNamespace(run_gate=Mock(side_effect=run_gate),
            runtime_identity=Mock(return_value=(None,dict(runner_sha256=P.GENERATED_SHA256))))
        self.generated=self.stack.enter_context(patch.object(P.phase,'_generated',return_value=self.native))

    def run_size(self,tokens):
        return P.run_native(self.context,self.workspace,time.monotonic_ns()+P.CAPS[tokens]*10**9,tokens=tokens)

    def test_fresh_pair_uses_original_paths_exact_gate_kwargs_and_real_metadata_validators(self):
        small=self.run_size(16);large=self.run_size(128)
        self.assertEqual([item[0].name for item in self.calls],['native_m16','native'])
        self.assertEqual([item[1] for item in self.calls],[16,128])
        for directory,tokens,kwargs in self.calls:
            self.assertIs(kwargs['carried'],False);self.assertEqual(kwargs['threads'],4)
            self.assertIs(kwargs['qkv_recipe'],self.recipe)
            self.assertEqual(kwargs['small_gate'],None if tokens==16 else self.workspace/'native_m16/RESULT.json')
        self.assertEqual(large['m16_result_sha256'],small['result_sha256'])
        pair=P.kernel.json_bytes(P.kernel.read(self.workspace/'recipe_pair.json'))
        self.assertEqual(pair['status'],'NUMERICAL_PREREQUISITE_ONLY')
        self.assertIs(pair['runtime_ready'],False);self.assertIs(pair['public_execution'],False)
        self.assertIs(pair['backend_order_proven'],False)
        self.assertEqual(pair['native16']['report_sha256'],P.kernel.sha(P.kernel.read(self.workspace/'phase_native16.json')))
        self.assertGreaterEqual(self.exports.call_count,5)
        self.assertEqual(self.threads.call_count,2)
        self.build.assert_not_called();self.qkv_build.assert_not_called()

    def test_request_domain_deadline_source_and_context_fail_before_native(self):
        for tokens,end in ((True,20),(32,20),(16,0),(16,61),(128,121)):
            with self.subTest(tokens=tokens,end=end),self.assertRaises((ValueError,TimeoutError)):
                P.run_native(self.context,self.workspace,time.monotonic_ns()+end*10**9,tokens=tokens)
        for field in ('contract_sha256','generated_module_sha256','source_sha256','work_deadline_ns'):
            changed=deepcopy(self.context);changed[field]={} if field=='source_sha256' else 0
            with self.subTest(field=field),self.assertRaises((ValueError,TimeoutError)):
                P.run_native(changed,self.workspace,time.monotonic_ns()+30*10**9,tokens=16)
        self.generated.assert_not_called()
        with patch.object(runtime,'source_snapshot',return_value={}):
            with self.assertRaises(ValueError):self.run_size(16)
        self.generated.assert_not_called()

    def test_reused_or_symlink_output_rejects_before_native(self):
        for relative in ('phase_native16.json','phase_native16_diagnostics.json','native_m16'):
            path=self.workspace/relative;path.symlink_to('missing')
            with self.subTest(relative=relative),self.assertRaises(ValueError):self.run_size(16)
            path.unlink()
        self.generated.assert_not_called()

    def test_small_gate_required_and_current_before_m128(self):
        with self.assertRaises(OSError):self.run_size(128)
        self.native.run_gate.assert_not_called()
        # Failed attempts retain diagnostics, so use separate phase artifacts for retry fixture only.
        (self.workspace/'phase_native128_diagnostics.json').unlink()
        (self.workspace/'producer_native128.failure.json').unlink()
        self.run_size(16)
        small=self.workspace/'native_m16/RESULT.json';small.write_bytes(small.read_bytes()+b' ')
        with self.assertRaises(ValueError):self.run_size(128)
        self.assertEqual(self.native.run_gate.call_count,1)

    def test_numeric_failure_preserves_failure_report_never_pair(self):
        self.failure='numeric'
        with self.assertRaises(ValueError):self.run_size(16)
        value=P.phase.validate_report(P.kernel.json_bytes(P.kernel.read(self.workspace/'phase_native16.json')))
        self.assertIs(value['native_acceptance'],False)
        self.assertEqual(value['modes']['bf16']['failed_stages'],['gate'])
        self.assertFalse((self.workspace/'recipe_pair.json').exists())

    def test_same_byte_disk_result_mismatch_rejects_before_postflight_receipt(self):
        self.disk_mutation=lambda value:value.update(tokens=128)
        with self.assertRaises(ValueError):self.run_size(16)
        self.assertFalse((self.workspace/'phase_native16.json').exists())
        self.exports.assert_not_called()

    def test_exact_bf16_dispatch_and_fenv_remain_stricter_than_numerical_continuation(self):
        def mutation(observed):
            for item in observed['bf16']['records']:
                item.update(implementation='brg_matmul:avx512_core_amx',isa='avx512_core_amx')
        self.diagnostic_mutation=mutation
        with self.assertRaises(ValueError):self.run_size(16)
        report=P.phase.validate_report(P.kernel.json_bytes(P.kernel.read(self.workspace/'phase_native16.json')))
        observation=P.phase.validate_diagnostics(P.kernel.json_bytes(P.kernel.read(self.workspace/'phase_native16_diagnostics.json')))
        self.assertIs(report['native_acceptance'],True)
        self.assertIs(P.phase.continuation_eligible(observation),True)
        self.assertFalse((self.workspace/'recipe_pair.json').exists())

    def test_fenv_change_rejects_even_with_original_numerical_pass(self):
        altered=dict(self.environment['after_gate'],ftz=True)
        with patch.object(capture,'fenv_snapshot',side_effect=[self.environment['before_recipe'],
                self.environment['after_recipe'],altered]),self.assertRaises(ValueError):
            self.run_size(16)
        report=P.phase.validate_report(P.kernel.json_bytes(P.kernel.read(self.workspace/'phase_native16.json')))
        observation=P.phase.validate_diagnostics(P.kernel.json_bytes(P.kernel.read(self.workspace/'phase_native16_diagnostics.json')))
        self.assertIs(report['native_acceptance'],True)
        self.assertIs(observation['fenv_changes']['gate'],True)
        self.assertFalse((self.workspace/'recipe_pair.json').exists())

    def test_m128_numeric_failure_cannot_reuse_completed_m16_as_pair(self):
        self.run_size(16);self.failure='numeric'
        with self.assertRaises(ValueError):self.run_size(128)
        report=P.phase.validate_report(P.kernel.json_bytes(P.kernel.read(self.workspace/'phase_native128.json')))
        self.assertIs(report['native_acceptance'],False)
        self.assertEqual([item[1] for item in self.calls],[16,128])
        self.assertFalse((self.workspace/'recipe_pair.json').exists())

    def test_source_only_gate_preparation_keeps_original_gate_unchanged(self):
        target=Path(self.context['generated_module']);target.unlink();target.parent.rmdir()
        original=P.kernel.source(P.kernel.ORIGINAL)
        self.sources[native_runtime.DISPATCH_PATCH]=P.kernel.sha(native_runtime.read_source(native_runtime.DISPATCH_PATCH))
        P._prepare_gate(self.context,self.workspace,self.sources)
        self.assertEqual(target.read_bytes(),self.gate)
        self.assertEqual(P.kernel.source(P.kernel.ORIGINAL),original)
        self.assertEqual(list(self.workspace.glob('recipe_source_*')),[])
        self.build.assert_not_called();self.qkv_build.assert_not_called()
        self.generated.assert_not_called()

    def test_source_drift_after_gate_cannot_issue_validated_report(self):
        self.recipe.revalidate.side_effect=lambda:self.sources.update({P.SOURCE:'0'*64})
        with self.assertRaises(ValueError):self.run_size(16)
        self.assertFalse((self.workspace/'phase_native16.json').exists())

    def test_private_failure_projection_never_contains_exception_or_payload_text(self):
        self.failure='raise'
        with self.assertRaises(RuntimeError):self.run_size(16)
        value=P.kernel.json_bytes(P.kernel.read(self.workspace/'phase_native16_diagnostics.json'))
        self.assertIs(value['postflight_complete'],False);self.assertIsNone(value['result_sha256'])
        safe=(self.workspace/'producer_native16.failure.json').read_text()
        for forbidden in ('SECRET','/private','tensor payload'):self.assertNotIn(forbidden,safe)
        self.assertFalse((self.workspace/'phase_native16.json').exists())

    def test_both_builds_share_one_deadline_and_no_timer_owner(self):
        calls=[]
        with patch.object(P,'_prepare_gate') as prepare_gate, \
             patch.object(P.qkv_kernel,'build',side_effect=lambda path,**kw:(calls.append(('qkv',kw)),self.qkv_library)[1]), \
             patch.object(P.kernel,'build',side_effect=lambda path,**kw:(calls.append(('qk',kw)),self.library)[1]):
            end=time.monotonic_ns()+30*10**9
            result=P.build_libraries(self.context,self.workspace,end)
        prepare_gate.assert_called_once()
        self.assertEqual(calls,[('qkv',dict(execute=True,deadline_ns=end-10**9)),
                                ('qk',dict(execute=True,deadline_ns=end-10**9))])
        self.assertEqual(result['status'],'COMPLETE_KERNEL_BUILD')
        self.assertIs(result['numerical_execution'],False)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))
        with patch.object(P.signal,'getitimer',return_value=(1.0,0.0)),self.assertRaises(ValueError):
            P.build_libraries(self.context,self.workspace,end)

    def test_build_failure_stops_second_compiler_without_kernel_receipt(self):
        with patch.object(P,'_prepare_gate'),patch.object(P.qkv_kernel,'build',side_effect=TimeoutError()), \
             patch.object(P.kernel,'build') as second,self.assertRaises(TimeoutError):
            P.build_libraries(self.context,self.workspace,time.monotonic_ns()+30*10**9)
        second.assert_not_called();self.assertFalse((self.workspace/'phase_kernel.json').exists())

    def test_manifest_extension_binds_exact_known_files_and_rejects_symlinks(self):
        files={'qk_library/'+P.kernel.LIBRARY:b'CONTROL_ONLY ELF',
               'qk_library/'+P.kernel.RECEIPT:b'CONTROL_ONLY receipt',
               'qkv_library/'+P.qkv_kernel.LIBRARY:b'CONTROL_ONLY ELF2',
               'qkv_library/'+P.qkv_kernel.RECEIPT:b'CONTROL_ONLY receipt2'}
        for name in ('native16','native128'):
            files['phase_'+name+'.json']=b'CONTROL_ONLY report'
            files['phase_'+name+'_diagnostics.json']=b'CONTROL_ONLY diagnostics'
        for relative,raw in files.items():
            path=self.workspace/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        value=P.manifest_extension(self.workspace)
        self.assertEqual(set(value),{'generated_module','qk','qkv','native16','native128'})
        self.assertEqual(value['generated_module']['sha256'],P.GENERATED_SHA256)
        self.assertEqual(value['qk']['binary']['sha256'],P.kernel.sha(files['qk_library/'+P.kernel.LIBRARY]))
        path=self.workspace/'phase_native16.json';path.unlink();path.symlink_to('phase_native128.json')
        with self.assertRaises(ValueError):P.manifest_extension(self.workspace)

    def test_actual_composed_setup_wrappers_preserve_workspace_and_shared_deadline(self):
        from . import prepare as composition
        with tempfile.TemporaryDirectory() as temporary:
            out=Path(temporary)/'composed'
            composition.previous.prepare(out,enable_raw_kv=True)
            subprocess.run(['patch','--batch','--fuzz=0','-p1'],cwd=out,
                input=runtime.read_source(composition.PATCH),check=True,
                capture_output=True,timeout=10)
            raw=(out/runtime.TARGETS[2]).read_bytes()
            pinned=P.kernel.json_bytes(P.kernel.read(runtime.ROOT/runtime.PINS_PATH))
            self.assertEqual(P.kernel.sha(raw),pinned['generated_sha256'][runtime.TARGETS[2]])
        names={'_phase_native16','_phase_native128'}
        nodes=[n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef) and n.name in names]
        self.assertEqual({n.name for n in nodes},names)
        now=100*10**9
        derived=object();derive=Mock(return_value=derived);remaining=Mock()
        namespace=dict(__package__=setup.__package__,
            time=types.SimpleNamespace(monotonic_ns=lambda:now),
            m128_runtime=types.SimpleNamespace(producer_context=derive),
            PHASE_LIMITS=runtime.PHASE_LIMITS,remaining=remaining)
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'<actual-composed-setup>','exec'),namespace)
        for tokens in (16,128):
            for budget in (10,1000):
                context=dict(self.context,work_deadline_ns=now+budget*10**9)
                derive.reset_mock();remaining.reset_mock()
                with patch.object(P,'run_native') as run:
                    namespace['_phase_native'+str(tokens)](context,self.workspace)
                derive.assert_called_once_with(context,self.workspace)
                run.assert_called_once_with(derived,self.workspace,
                    now+min(budget,P.CAPS[tokens])*10**9,tokens=tokens)
                remaining.assert_called_once_with(context,1)
        self.generated.assert_not_called();self.build.assert_not_called();self.qkv_build.assert_not_called()


if __name__=='__main__':unittest.main()
