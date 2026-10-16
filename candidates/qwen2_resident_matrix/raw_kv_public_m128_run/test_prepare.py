"""Cold linked-M128 composition tests. No producer or numerical execution."""
import ast
import builtins
from contextlib import ExitStack
from copy import deepcopy
import difflib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

from . import prepare
from ..raw_kv_public_m128 import prerequisite
from ..raw_kv_public_m128_runtime import runtime
from ..raw_kv_public_m128_runtime.test_setup_runtime import load_source

ROOT=prepare.ROOT


class LaunchPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='m128-launch-composition-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.out=Path(cls.temp.name)/'prior'
        cls.baseline=prepare.previous.prepare(cls.out,enable_raw_kv=True)
        cls.originals={name:(cls.out/name).read_bytes() for name in prepare.BRIDGE_TARGETS}
        subprocess.run(['patch','--batch','--fuzz=0','-p1'],cwd=cls.out,
            input=prepare.read_source(prepare.PATCH),check=True,capture_output=True,timeout=10)
        cls.generated=prepare.previous._inventory(cls.out)
        cls.bridged={name:(cls.out/name).read_bytes() for name in prepare.BRIDGE_TARGETS}

    def control_snapshot(self):
        """Source-only fixture for testing preparer checks, not launch admission."""
        inputs=dict(self.baseline['inputs'])
        for name in ('prepare.py','launch_bridge.patch','test_prepare.py'):
            path=prepare.PREFIX+name; inputs[path]=prepare.sha(prepare.read_source(path))
        return dict(inputs=inputs,generated=dict(self.generated))

    def test_bridge_is_exactly_three_imports_and_seven_unchanged_overlays(self):
        prepare.check_bridge_scope(self.originals,self.bridged)
        self.assertEqual(len(self.generated),10)
        self.assertEqual(set(self.generated),set(self.baseline['generated']))
        changed={name for name in self.generated if self.generated[name]!=self.baseline['generated'][name]}
        self.assertEqual(changed,set(prepare.BRIDGE_TARGETS))
        self.assertEqual(len(set(self.generated)-changed),7)
        lines=prepare.read_source(prepare.PATCH).decode().splitlines()
        self.assertEqual([line for line in lines if line.startswith('--- ')],
                         ['--- a/'+name for name in prepare.BRIDGE_TARGETS])
        additions=[line for line in lines if line.startswith('+') and not line.startswith('+++')]
        self.assertEqual(len(additions),4)
        self.assertEqual(sum(line.startswith('+from ..raw_kv_public_m128_run import launch as ') for line in additions),3)
        self.assertEqual(sum(line.startswith("+    code='from pathlib import Path; from '") for line in additions),1)

    def test_whole_ast_scope_rejects_enabled_only_callback_or_guard_change(self):
        for name in prepare.BRIDGE_TARGETS:
            changed=dict(self.bridged); tree=ast.parse(changed[name])
            if name==prerequisite.ENTRY:
                branch=next(n for n in ast.walk(tree) if isinstance(n,ast.If)
                            and isinstance(n.test,ast.Name) and n.test.id=='m128_selected')
                branch.body.append(ast.parse('unapproved_callback()').body[0])
            else:
                fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef))
                fn.body.append(ast.parse('unapproved_callback()').body[0])
            changed[name]=ast.unparse(tree)
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'reviewed import/diagnostic scope'):
                prepare.check_bridge_scope(self.originals,changed)
        changed=dict(self.bridged)
        changed[prerequisite.ASSETS]=changed[prerequisite.ASSETS].replace(
            b'need(file_sha(Path(__file__)) == IMPORTED_SOURCE_SHA256',b'need(True')
        with self.assertRaisesRegex(ValueError,'reviewed import/diagnostic scope'):
            prepare.check_bridge_scope(self.originals,changed)
        for mutation in ('missing','duplicate'):
            changed=dict(self.bridged)
            if mutation=='missing': del changed[prerequisite.SETUP]
            else: changed[prerequisite.SETUP]+=b'\nfrom ..raw_kv_public_m128_run import launch as m128_runtime\n'
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                prepare.check_bridge_scope(self.originals,changed)

    def test_backend_dispatch_preserves_validator_and_subprocess_deadline_ast(self):
        functions=lambda raw:{n.name:n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef)}
        before=functions(self.originals[prerequisite.SETUP]);after=functions(self.bridged[prerequisite.SETUP])
        for name in ('backend_identity','backend_threads','backend_preflight'):
            self.assertEqual(ast.dump(before[name]),ast.dump(after[name]),name)
        calls=lambda node:[ast.dump(n) for n in ast.walk(node) if isinstance(n,ast.Call)
            and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name)
            and n.func.value.id=='subprocess']
        self.assertEqual(calls(before['_phase_environment']),calls(after['_phase_environment']))
        code=next(n.value for n in after['_phase_environment'].body if isinstance(n,ast.Assign)
                  and any(isinstance(t,ast.Name) and t.id=='code' for t in n.targets))
        value=eval(compile(ast.Expression(code),'<diagnostic dispatch>','eval'),{'workspace':Path('/CONTROL_ONLY/setup')})
        self.assertEqual(value,"from pathlib import Path; from candidates.qwen2_resident_matrix.raw_kv_public_m128_run.launch import backend_preflight; backend_preflight(Path('/CONTROL_ONLY/setup/context.json'))")
        for mutation in ('dispatch','deadline','validator'):
            changed=dict(self.bridged)
            if mutation=='dispatch':
                changed[prerequisite.SETUP]=changed[prerequisite.SETUP].replace(
                    b"+'candidates.qwen2_resident_matrix.raw_kv_public_m128_run.launch'+",b'+MODULE+')
            elif mutation=='deadline':
                changed[prerequisite.SETUP]=changed[prerequisite.SETUP].replace(
                    b'timeout=remaining(context,30)',b'timeout=remaining(context,300)')
            else:
                tree=ast.parse(changed[prerequisite.SETUP]);fn=next(n for n in tree.body
                    if isinstance(n,ast.FunctionDef) and n.name=='backend_identity')
                fn.body.append(ast.Pass());changed[prerequisite.SETUP]=ast.unparse(tree)
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                prepare.check_bridge_scope(self.originals,changed)

    def test_flags_existing_output_and_symlink_ancestor_reject_before_contract(self):
        from . import launch
        with tempfile.TemporaryDirectory() as temp,patch.object(launch,'contract_snapshot') as contract:
            root=Path(temp)
            for bad in (False,1,0,None,'true'):
                with self.subTest(flag=bad),self.assertRaises(ValueError):
                    prepare.prepare(root/'out',enable_raw_kv=bad)
            with self.assertRaises(ValueError): prepare.prepare(root,enable_raw_kv=True)
            link=root/'link'; link.symlink_to(root,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'ancestor symlink'):
                prepare.prepare(link/'out',enable_raw_kv=True)
            contract.assert_not_called(); self.assertFalse((root/'out').exists())

    def test_real_runtime_then_bridge_preparer_matches_exact_expected_source(self):
        from . import launch
        before=runtime.contract_snapshot()
        with tempfile.TemporaryDirectory() as temp,patch.object(launch,'contract_snapshot',return_value=self.control_snapshot()):
            result=prepare.prepare(Path(temp)/'out',enable_raw_kv=True)
        self.assertEqual(result['generated'],self.generated)
        self.assertEqual(result['status'],'PASS_PREPARATION_ONLY')
        for field in ('numerical_execution','native_execution','m128_executed','full_29_node_acceptance'):
            self.assertIs(result[field],False)
        self.assertEqual(runtime.contract_snapshot(),before)

    def test_patch_pin_header_and_generated_hash_negatives(self):
        from . import launch
        original_read=prepare.read_source; original_patch=original_read(prepare.PATCH)
        callback=dict(self.bridged)
        callback[prerequisite.ENTRY]+=b'\nunapproved_callback()\n'
        altered=''.join(''.join(difflib.unified_diff(self.originals[name].decode().splitlines(keepends=True),
            callback[name].decode().splitlines(keepends=True),fromfile='a/'+name,tofile='b/'+name))
            for name in prepare.BRIDGE_TARGETS).encode()
        cases=(('pin',original_patch+b'\n','patch source drift',False),
               ('header',original_patch.replace(b'--- a/',b'--- b/',1),'target scope',True),
               ('generated',altered,'generated source identity drift',True))
        for name,raw,reason,update_pin in cases:
            snapshot=self.control_snapshot()
            if update_pin:snapshot['inputs'][prepare.PATCH]=prepare.sha(raw)
            with self.subTest(case=name),tempfile.TemporaryDirectory() as temp, \
                    patch.object(launch,'contract_snapshot',return_value=snapshot), \
                    patch.object(prepare,'read_source',side_effect=lambda p:raw if p==prepare.PATCH else original_read(p)):
                with self.assertRaisesRegex(ValueError,reason): prepare.prepare(Path(temp)/'out',enable_raw_kv=True)

    def test_published_input_and_source_postflight_drift_reject(self):
        from . import launch
        before=self.control_snapshot()
        for kind in ('input','postflight'):
            changed=deepcopy(before)
            changed['inputs'][next(iter(self.baseline['inputs']))]='f'*64
            values=[changed] if kind=='input' else [before,changed]
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temp, \
                    patch.object(launch,'contract_snapshot',side_effect=values):
                with self.assertRaisesRegex(ValueError,'published runtime input drift|source postflight drift'):
                    prepare.prepare(Path(temp)/'out',enable_raw_kv=True)

    def backend_stub_modules(self):
        """Already-loaded CONTROL_ONLY module metadata, with no native imports."""
        def module(name,**values):
            result=types.ModuleType(name);vars(result).update(values);return result
        def unavailable():raise RuntimeError('SECRET backend detail')
        return {
            'numpy':module('numpy',__version__='2.3.5'),
            'torch':module('torch',__version__='SECRET version',get_num_threads=lambda:4,
                get_num_interop_threads=lambda:1,are_deterministic_algorithms_enabled=lambda:True),
            'torch.version':module('torch.version',git_version='449b1768410104d3ed79d3bcfe4ba1d65c7f22c0'),
            'torch.backends.cpu':module('torch.backends.cpu',get_cpu_capability=unavailable),
            'torch.backends.mkldnn':module('torch.backends.mkldnn',enabled=True),
            'torch.__config__':module('torch.__config__',show=lambda:'SECRET 3.7.1 8d263e693366ef8db40acc569cc7d8edf644556d'),
            'transformers':None}

    def test_backend_wrapper_success_calls_original_once_without_diagnostics(self):
        from . import launch
        package=sys.modules['candidates.qwen2_resident_matrix.raw_kv_public_fresh']
        marker=object();setup=types.SimpleNamespace(backend_preflight=Mock(return_value=marker),atomic_json=Mock())
        path=Path('/CONTROL_ONLY/context.json')
        with patch.object(package,'setup',setup),patch.object(launch,'contract_snapshot') as contract, \
                patch.object(launch,'_backend_checks') as checks:
            self.assertIs(launch.backend_preflight(path),marker)
        setup.backend_preflight.assert_called_once_with(path)
        setup.atomic_json.assert_not_called();contract.assert_not_called();checks.assert_not_called()

    def test_backend_failure_retains_original_exception_and_fixed_safe_checks(self):
        from . import launch
        from ..raw_kv_public_fresh import setup as original_setup
        package=sys.modules['candidates.qwen2_resident_matrix.raw_kv_public_fresh']
        error=RuntimeError('SECRET raw_tensor=[1,2,3] /private/token https://signed.example/')
        setup=types.SimpleNamespace(backend_preflight=Mock(side_effect=error),atomic_json=original_setup.atomic_json)
        original_import=builtins.__import__
        def no_numerics(name,*args,**kwargs):
            if name.split('.')[0] in ('numpy','torch','transformers'):
                raise AssertionError('diagnostic attempted a package import')
            return original_import(name,*args,**kwargs)
        with tempfile.TemporaryDirectory() as temp:
            context=Path(temp)/'context.json';context.write_text('{}')
            with patch.object(package,'setup',setup),patch.object(launch,'contract_snapshot',return_value={'sources':{}}), \
                    patch.dict(sys.modules,self.backend_stub_modules()),patch('builtins.__import__',side_effect=no_numerics):
                with self.assertRaises(RuntimeError) as caught:launch.backend_preflight(context)
            self.assertIs(caught.exception,error);setup.backend_preflight.assert_called_once_with(context)
            path=context.with_name('backend.failure.json');raw=path.read_text();value=json.loads(raw)
            self.assertEqual(set(value),{'schema','stage','diagnostic','checks'})
            self.assertEqual(value['stage'],'unknown_backend')
            self.assertEqual(value['diagnostic'],dict(phase='environment',exception='RuntimeError',frames=[]))
            self.assertEqual(set(value['checks']),set(launch._backend_failure_spec()[1]))
            self.assertEqual(len(value['checks']),14)
            self.assertTrue(all(v is None or type(v) is bool for v in value['checks'].values()))
            self.assertIs(value['checks']['numpy_235'],True)
            self.assertIs(value['checks']['torch_210_cpu'],False)
            self.assertIsNone(value['checks']['cpu_avx512'])
            self.assertIsNone(value['checks']['transformers_4401'])
            self.assertIs(value['checks']['mkldnn_version'],True)
            self.assertLessEqual(len(raw.encode()),4096)
            for secret in ('SECRET','raw_tensor','/private/','https://',temp):self.assertNotIn(secret,raw)
            checked=launch.validate_backend_failure(value,{})
            self.assertEqual(checked,value);self.assertIsNot(checked,value)

    def test_backend_import_failure_and_failed_record_write_never_replace_original_error(self):
        from . import launch
        package=sys.modules['candidates.qwen2_resident_matrix.raw_kv_public_fresh']
        original_import=builtins.__import__
        for mode in ('import','write'):
            error=ModuleNotFoundError('SECRET missing runtime') if mode=='import' else RuntimeError('SECRET failed validator')
            def guarded_import(name,globals=None,locals=None,fromlist=(),level=0):
                if name=='raw_kv_public_fresh' and 'setup' in fromlist and mode=='import':raise error
                if name.split('.')[0] in ('numpy','torch','transformers'):raise AssertionError('native import')
                return original_import(name,globals,locals,fromlist,level)
            setup=types.SimpleNamespace(backend_preflight=Mock(side_effect=error),
                atomic_json=Mock(side_effect=OSError('SECRET diagnostic write failed')))
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as temp:
                context=Path(temp)/'context.json';context.write_text('{}')
                with patch.object(package,'setup',setup),patch.object(launch,'contract_snapshot',return_value={'sources':{}}), \
                        patch.dict(sys.modules,{name:None for name in self.backend_stub_modules()}), \
                        patch('builtins.__import__',side_effect=guarded_import):
                    with self.assertRaises(type(error)) as caught:launch.backend_preflight(context)
                self.assertIs(caught.exception,error)
                if mode=='import':
                    setup.backend_preflight.assert_not_called()
                    value=json.loads(context.with_name('backend.failure.json').read_text())
                    self.assertEqual(value['stage'],'setup_import')
                    self.assertEqual(value['diagnostic']['exception'],'ModuleNotFoundError')
                    self.assertNotIn('SECRET',json.dumps(value))
                    self.assertEqual({p.name for p in context.parent.iterdir()},{'context.json','backend.failure.json'})
                else:
                    setup.backend_preflight.assert_called_once_with(context)
                    setup.atomic_json.assert_called_once()
                    self.assertFalse(context.with_name('backend.failure.json').exists())

    def test_backend_diagnostic_schema_rejects_type_aliases_unknown_keys_and_private_text(self):
        from . import launch
        good=dict(schema=1,stage='unknown_backend',
            diagnostic=dict(phase='environment',exception='RuntimeError',frames=[]),
            checks=dict.fromkeys(launch._backend_failure_spec()[1],None))
        cases=[]
        for key,bad in (('schema',True),('schema',1.0),('stage','SECRET private stage')):
            value=deepcopy(good);value[key]=bad;cases.append(value)
        for bad in (0,1,'SECRET',[],{}):
            value=deepcopy(good);value['checks']['python_312']=bad;cases.append(value)
        for target in ('top','diagnostic','checks'):
            value=deepcopy(good);(value if target=='top' else value[target])['SECRET']='private';cases.append(value)
        value=deepcopy(good);value['diagnostic']['exception']='SECRET Error';cases.append(value)
        for frame in ({'source':'/private/context','line':1},
                      {'source':prepare.PREFIX+'launch.py','line':True},
                      {'source':prepare.PREFIX+'launch.py','line':100000}):
            value=deepcopy(good);value['diagnostic']['frames']=[frame];cases.append(value)
        self.assertEqual(launch.validate_backend_failure(good,{}),good)
        private_error=type('SECRET_BACKEND_TYPE',(RuntimeError,),{})('SECRET private detail')
        stage,diagnostic=launch._backend_diagnostic(private_error,{},setup_loaded=True)
        self.assertEqual(stage,'unknown_backend')
        self.assertEqual(diagnostic,dict(phase='environment',exception='OtherError',frames=[]))
        self.assertNotIn('SECRET',json.dumps(diagnostic))
        for index,value in enumerate(cases):
            with self.subTest(case=index),self.assertRaises(ValueError):launch.validate_backend_failure(value,{})

    def native_failure_fixture(self, cause='bf16_budget'):
        """Original-schema CONTROL_ONLY metadata; no tensor or native execution.

        Extract the original inventories, policy reader, scalar verdict, initial
        result and phase-status expression. This does not validate any payload.
        """
        from . import launch
        script='scripts/qwen2_layer0_model_gate.py'
        raw=(ROOT/script).read_bytes();tree=ast.parse(raw)
        functions={node.name:node for node in tree.body if isinstance(node,ast.FunctionDef)}
        stages=ast.literal_eval(next(node.value for node in tree.body if isinstance(node,ast.Assign)
            and any(isinstance(t,ast.Name) and t.id=='REQUIRED_STAGES' for t in node.targets)))
        semantic=next(node.value for node in ast.walk(functions['run_gate']) if isinstance(node,ast.Assign)
            and any(isinstance(t,ast.Name) and t.id=='semantic' for t in node.targets))
        semantics=tuple(ast.literal_eval(key) for key in semantic.keys)
        namespace={'Path':Path,'sha':lambda path:launch.sha(path.read_bytes())}
        exec(compile(ast.Module(body=[functions['load_policy'],functions['stage_verdict']],type_ignores=[]),
            script,'exec'),namespace)
        policy=namespace['load_policy'](ROOT)
        sources={script:launch.sha(raw),policy['source']:policy['sha256']}
        namespace.update(tokens=128,carried=False,threads=4,policy=policy,
            identity={'runner_sha256':sources[script],'CONTROL_ONLY':'SECRET /private/runtime'},
            sha=lambda path:'a'*64,small_gate=Path('/CONTROL_ONLY/native_m16/RESULT.json'),
            payload_dir=Path('/CONTROL_ONLY/payload'),os=types.SimpleNamespace(environ={}))
        initial=next(node.value for node in functions['run_gate'].body if isinstance(node,ast.Assign)
            and any(isinstance(t,ast.Name) and t.id=='result' for t in node.targets))
        result=eval(compile(ast.Expression(initial),script,'eval'),namespace)
        geometry={'ROWS':128,'need':launch.need}
        asset_tree=ast.parse(self.bridged[prerequisite.ASSETS])
        exec(compile(ast.Module(body=[node for node in asset_tree.body if isinstance(node,ast.FunctionDef)
            and node.name in ('shapes','export_shapes')],type_ignores=[]),'<source-only geometry>','exec'),geometry)
        shapes=geometry['shapes']();exports=geometry['export_shapes']()
        self.assertEqual(set(shapes),stages);self.assertEqual(len(stages),29);self.assertEqual(len(semantics),9)
        phase_node=next(node.args[0] for node in ast.walk(functions['run_gate']) if isinstance(node,ast.Call)
            and isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name)
            and node.func.value.id=='phases' and node.func.attr=='append')
        for mode in ('bf16','fp32'):
            metrics={}
            for name in sorted(stages):
                item=dict(shape=shapes[name],elements=math.prod(shapes[name]),max_abs=0.0,mean_abs=0.0,
                    relative_l2=0.0,cosine=1.0,normalized_max_abs=0.0,different_elements=0,
                    bit_exact=True,first_difference_flat=None,actual_f32_sha256='b'*64,
                    reference_f32_sha256='b'*64,finite=True,
                    actual_storage_dtype='torch.bfloat16' if mode=='bf16' else 'torch.float32',
                    actual_storage_sha256='b'*64)
                if cause=='bf16_budget' and mode=='bf16' and name=='y':
                    item.update(max_abs=policy['block']['max_abs']*2,mean_abs=policy['block']['mean_abs']*2,
                        bit_exact=False,different_elements=1,first_difference_flat=0)
                item.update(namespace['stage_verdict'](name,item,mode,policy))
                for prefix in ('native','independent'):
                    item.update({prefix+'_file':mode+'/phase_0/'+prefix+'_'+name+'.f32le',
                        prefix+'_export_shape':exports[name],prefix+'_file_sha256':'b'*64})
                metrics[name]=item
            checks=dict.fromkeys(semantics,True)
            if cause==mode+'_semantic':checks['native_future_probability_zero']=False
            phase=eval(compile(ast.Expression(phase_node),script,'eval'),dict(namespace,mode=mode,
                phase=0,ids=list(range(128)),stage_results=metrics,semantic=checks,
                failed=[name for name,value in metrics.items() if value['passed'] is False],
                time=types.SimpleNamespace(monotonic=lambda:0.1),phase_started=0.0))
            result['modes'][mode]=dict(phases=[phase],seconds=0.1)
        result.update(status='FAIL_BF16_STAGE_BUDGET',seconds=0.2,peak_rss_kib=123,
            CONTROL_ONLY_private='SECRET weights=[1,2,3] /private/checkpoint https://signed.example/')
        return result,sources

    def project_native_fixture(self,value,sources):
        from . import launch
        raw=json.dumps(value,sort_keys=True,allow_nan=False).encode()
        return launch.project_native_failure(value,result_sha256=launch.sha(raw),
            source_sha256=sources['scripts/qwen2_layer0_model_gate.py'])

    def test_native_failure_original_schema_and_all_three_failure_classes(self):
        from . import launch
        original_import=builtins.__import__
        def no_numerics(name,*args,**kwargs):
            if name.split('.')[0] in ('numpy','torch','transformers','ctypes'):
                raise AssertionError('native diagnostic attempted a numerical import')
            return original_import(name,*args,**kwargs)
        for cause in ('bf16_budget','bf16_semantic','fp32_semantic'):
            with self.subTest(cause=cause),patch('builtins.__import__',side_effect=no_numerics):
                value,sources=self.native_failure_fixture(cause)
                projected=self.project_native_fixture(value,sources)
                self.assertEqual(set(projected['bf16_stages']),set(value['modes']['bf16']['phases'][0]['stages']))
                self.assertEqual(len(projected['bf16_stages']),29)
                self.assertEqual(projected['approved_limits'],{k:value['policy'][k] for k in ('operator','block')})
                self.assertEqual(projected['status'],'NATIVE128_FAILURE_DIAGNOSTIC')
                self.assertEqual(projected['native_status'],'FAIL_BF16_STAGE_BUDGET')
                self.assertIs(projected['incomplete'],True)
                self.assertIs(projected['postflight_complete'],False)
                self.assertIs(projected['numerical_acceptance'],False)
                self.assertIs(projected['actual_chain_executed'],False)
                for mode in ('bf16','fp32'):
                    original=value['modes'][mode]['phases'][0]
                    self.assertEqual(projected['modes'][mode],{k:original[k] for k in
                        ('status','failed_stages','semantics','all_semantics_exact')})
                self.assertEqual(projected['modes']['bf16']['failed_stages'],['y'] if cause=='bf16_budget' else [])
                self.assertEqual(projected['modes']['fp32']['status'],
                    'FAIL_FP32_SEMANTICS' if cause=='fp32_semantic' else 'DIAGNOSTIC_FP32')
                self.assertIsNone(projected['bf16_stages']['softmax_fp32']['passed'])
                self.assertIsNone(projected['bf16_stages']['softmax_fp32']['limits'])
                self.assertIsNone(projected['bf16_stages']['mask']['limits'])
                self.assertEqual(launch.validate_native_failure(projected),projected)
                raw=json.dumps(projected,sort_keys=True)
                self.assertLessEqual(len(raw.encode()),16384)
                for private in ('SECRET','CONTROL_ONLY','weights=','/private/','https://','native_file',
                                'export_shape','actual_f32_sha256','identity'):
                    self.assertNotIn(private,raw)

    def test_native_failure_rejects_canonical_identity_geometry_and_source_drift(self):
        from . import launch
        good,sources=self.native_failure_fixture();cases=[]
        for key,bad in (('schema_version',True),('layer',False),('tokens',128.0),('tokens',16),
                ('carried',0),('official_framework_forward',1),('rtl_execution',0),
                ('hardware_recipe_acceptance',0),('status','PASS_BF16_STAGE_BUDGET')):
            value=deepcopy(good);value[key]=bad;cases.append(value)
        value=deepcopy(good);value['identity']['runner_sha256']='0'*64;cases.append(value)
        for key,bad in (('source','/private/policy'),('sha256','0'*64),('operator',{'max_abs':1,'mean_abs':True})):
            value=deepcopy(good);value['policy'][key]=bad;cases.append(value)
        for key,bad in (('phase',False),('past_tokens',False),('token_ids',[False]+list(range(1,128))),
                        ('position_ids',list(range(127,-1,-1)))):
            value=deepcopy(good);value['modes']['bf16']['phases'][0][key]=bad;cases.append(value)
        for index,value in enumerate(cases):
            with self.subTest(case=index),self.assertRaises(ValueError):self.project_native_fixture(value,sources)
        for result_hash,source_hash in (('bad',sources['scripts/qwen2_layer0_model_gate.py']),('a'*64,'0'*64)):
            with self.assertRaises(ValueError):launch.project_native_failure(good,
                result_sha256=result_hash,source_sha256=source_hash)
        original_read=launch.read_source
        with patch.object(launch,'read_source',side_effect=lambda name,*a:
                b'drift' if name=='scripts/qwen2_layer0_model_gate.py' else original_read(name,*a)), \
                self.assertRaises(ValueError):self.project_native_fixture(good,sources)

    def test_native_failure_rejects_nonfinite_and_bool_int_scalar_aliases(self):
        from . import launch
        good,sources=self.native_failure_fixture()
        for mode in ('bf16','fp32'):
            for key,bad in (('max_abs',True),('mean_abs',False),('max_abs',float('nan')),
                    ('mean_abs',float('inf')),('max_abs',-1.0),('finite',1),('bit_exact',0),
                    ('bit_exact',1),('passed',1),('passed',0),('max_abs','SECRET')):
                value=deepcopy(good);value['modes'][mode]['phases'][0]['stages']['x'][key]=bad
                with self.subTest(mode=mode,key=key,bad=repr(bad)),self.assertRaises(ValueError):
                    launch.project_native_failure(value,result_sha256='a'*64,
                        source_sha256=sources['scripts/qwen2_layer0_model_gate.py'])
            for key,bad in (('mask_exact',0),('native_future_probability_zero',1)):
                value=deepcopy(good);value['modes'][mode]['phases'][0]['semantics'][key]=bad
                with self.subTest(mode=mode,key=key),self.assertRaises(ValueError):self.project_native_fixture(value,sources)
            value=deepcopy(good);value['modes'][mode]['phases'][0]['all_semantics_exact']=1
            with self.assertRaises(ValueError):self.project_native_fixture(value,sources)

    def test_native_failure_rejects_foreign_inventories_and_inconsistent_verdicts(self):
        good,sources=self.native_failure_fixture();cases=[]
        for section in ('modes','stages','semantics'):
            for mutation in ('missing','extra'):
                value=deepcopy(good)
                selected=value['modes'] if section=='modes' else value['modes']['bf16']['phases'][0][section]
                if mutation=='missing':selected.pop(next(iter(selected)))
                else:selected['SECRET /private/foreign']=next(iter(selected.values()))
                cases.append(value)
        for key,bad in (('failed_stages',[]),('failed_stages',['y','y']),('failed_stages',['SECRET']),
                ('status','PASS_BF16_STAGE_BUDGET'),('all_semantics_exact',False)):
            value=deepcopy(good);value['modes']['bf16']['phases'][0][key]=bad;cases.append(value)
        value=deepcopy(good);value['modes']['bf16']['phases']*=2;cases.append(value)
        for key,bad in (('limits',{'max_abs':0.2,'mean_abs':0.2}),('passed',True),
                        ('contract','SECRET'),('finite',False)):
            value=deepcopy(good);value['modes']['bf16']['phases'][0]['stages']['y'][key]=bad;cases.append(value)
        value=deepcopy(good);value['modes']['fp32']['phases'][0]['stages']['x']['status']='PASS';cases.append(value)
        value=deepcopy(good);phase=value['modes']['bf16']['phases'][0]
        phase['semantics']['mask_exact']=False;phase['all_semantics_exact']=False;cases.append(value)
        value,same_sources=self.native_failure_fixture('all_pass');cases.append(value)
        self.assertEqual(sources,same_sources)
        for index,value in enumerate(cases):
            with self.subTest(case=index),self.assertRaises(ValueError):self.project_native_fixture(value,sources)

    def test_native_failure_safe_schema_rejects_aliases_private_fields_and_oversize(self):
        from . import launch
        good,sources=self.native_failure_fixture();safe=self.project_native_fixture(good,sources);cases=[]
        for key,bad in (('schema',True),('tokens',128.0),('carried',0),('incomplete',1),
                ('postflight_complete',0),('numerical_acceptance',0),('actual_chain_executed',0),('status','PASS')):
            value=deepcopy(safe);value[key]=bad;cases.append(value)
        for where in ('top','stage','mode'):
            value=deepcopy(safe)
            selected=value if where=='top' else value['bf16_stages']['y'] if where=='stage' else value['modes']['fp32']
            selected['SECRET']='private';cases.append(value)
        value=deepcopy(safe);value['modes']['fp32']['semantics']['mask_exact']=1;cases.append(value)
        value=deepcopy(safe);value['bf16_stages']['y']['max_abs']=float('inf');cases.append(value)
        for index,value in enumerate(cases):
            with self.subTest(case=index),self.assertRaises(ValueError):launch.validate_native_failure(value)
        # Finite metadata integers can still exceed the public byte bound. Every
        # stage verdict is kept consistent so rejection reaches the size guard.
        large=deepcopy(good);phase=large['modes']['bf16']['phases'][0]
        for name,item in phase['stages'].items():
            item['max_abs']=item['mean_abs']=10**300
            if name not in ('mask','softmax_fp32'):item['passed']=False
        phase['failed_stages']=[name for name in sorted(phase['stages']) if phase['stages'][name]['passed'] is False]
        with self.assertRaises(ValueError):self.project_native_fixture(large,sources)

    def test_native_failure_real_parent_publish_roundtrip_retains_failed_only(self):
        from . import launch,run_ci
        for cause in ('bf16_budget','bf16_semantic','fp32_semantic'):
            with self.subTest(cause=cause),tempfile.TemporaryDirectory() as temp:
                private=Path(temp)/'private';path=private/'assets/native/RESULT.json';path.parent.mkdir(parents=True)
                value,sources=self.native_failure_fixture(cause)
                raw=(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode();path.write_bytes(raw)
                summary=dict(schema=1,status='FAILED',phase='setup',setup_phase='native128',elapsed_seconds=1.0,
                    rows=128,enable_raw_kv=True,fresh_profile=True,rtl_executed=False,scala_executed=False,
                    full_29_node_acceptance=False)
                run_ci.project_native_failure(summary,private,sources)
                self.assertEqual(summary['native128_failure']['status'],'NATIVE128_FAILURE_DIAGNOSTIC')
                self.assertEqual(summary['native128_failure']['result_sha256'],launch.sha(raw))
                out=Path(temp)/'public';out.mkdir();run_ci.publish(out,summary)
                saved=json.loads((out/'summary.json').read_bytes())
                self.assertEqual(saved,summary);self.assertEqual(saved['status'],'FAILED')
                self.assertIs(saved['full_29_node_acceptance'],False)
                self.assertIs(saved['native128_failure']['numerical_acceptance'],False)
                self.assertIs(saved['native128_failure']['postflight_complete'],False)
                self.assertIs(saved['native128_failure']['actual_chain_executed'],False)
                self.assertLessEqual((out/'summary.json').stat().st_size,32768)
                self.assertEqual({p.name for p in out.iterdir()},{'summary.json','progress.json'})
                self.assertEqual(path.read_bytes(),raw)
                for filename in ('summary.json','progress.json'):
                    text=(out/filename).read_text()
                    for forbidden in ('SECRET','CONTROL_ONLY','/private/','https://','weights=',temp):
                        self.assertNotIn(forbidden,text)

    def authorization_fixture(self):
        from . import launch
        # Execute the original snapshot encoder AST, rather than assuming the
        # compact source-contract encoding matches original indented snapshots.
        path=ROOT/'candidates/qwen2_resident_matrix/ffn_public/check_prefix_numeric.py'
        encoder=next(n for n in ast.parse(path.read_bytes()).body
                     if isinstance(n,ast.FunctionDef) and n.name=='encoded')
        namespace={'json':json}
        exec(compile(ast.Module(body=[encoder],type_ignores=[]),str(path),'exec'),namespace)
        sources={'CONTROL_ONLY/source.py':'1'*64}
        frozen=dict(sources=sources,inputs=sources,contract_sha256='2'*64)
        manifest=Path('/CONTROL_ONLY/setup/ASSETS.json')
        identity=types.SimpleNamespace(checkout_commit='a'*40,manifest=manifest,
            manifest_sha256='3'*64,receipt_sha256='4'*64,source_sha256=tuple(sources.items()))
        snapshot=dict(rows=128,enable_raw_kv=True,fresh_profile=True,source_sha256=sources,
            source_manifest_sha256=launch.sha(namespace['encoded'](sources)),
            fresh_assets=dict(profile='qwen2-public-pv16-fresh-assets-m128-v1',
                manifest=str(manifest),manifest_sha256=identity.manifest_sha256,enable_raw_kv=True),
            independent_reference=dict(rows=128,past_tokens=0))
        linked=dict(profile=launch.PROFILE,checkout_commit=identity.checkout_commit,
            launch_contract_sha256=frozen['contract_sha256'],setup_receipt_sha256=identity.receipt_sha256,
            m16_evidence_sha256=prerequisite.EVIDENCE_SHA256)
        return frozen,identity,snapshot,linked

    def test_bind_and_authorize_preserve_original_snapshot_encoder_and_revalidate(self):
        from . import launch,admission
        frozen,identity,snapshot,linked=self.authorization_fixture()
        original=deepcopy(snapshot)
        with patch.object(launch,'contract_snapshot',return_value=frozen), \
                patch.object(admission,'verify_setup',return_value=identity) as verify, \
                patch.object(admission,'revalidate') as revalidate:
            bound=launch.bind_snapshot(snapshot,identity,dict(contract_sha256=frozen['contract_sha256'],
                checkout_commit=identity.checkout_commit))
            self.assertEqual(snapshot,original)
            self.assertEqual(bound['m128_launch'],linked)
            self.assertEqual(set(linked),{'profile','checkout_commit','launch_contract_sha256',
                'setup_receipt_sha256','m16_evidence_sha256'})
            self.assertIs(launch.authorize_run(bound,wall_budget=2400,enable_raw_kv=True,fresh_profile=True),identity)
            verify.assert_called_once_with(identity.manifest.parent,Path('/CONTROL_ONLY/setup_evidence/summary.json'),
                checkout_commit=identity.checkout_commit,enable_raw_kv=True,rows=128)
            self.assertEqual(revalidate.call_count,2); revalidate.assert_called_with(identity)
        self.assertNotEqual(snapshot['source_manifest_sha256'],launch.sha(prerequisite.encoded(frozen['sources'])))

    def test_authorize_canonical_budget_mode_and_linked_schema_fail_closed(self):
        from . import launch,admission
        frozen,identity,snapshot,linked=self.authorization_fixture(); snapshot['m128_launch']=linked
        cases=[]
        for bad in (True,False,0,-1,2401,float('inf'),float('nan'),'2400',None):
            cases.append((deepcopy(snapshot),dict(wall_budget=bad,enable_raw_kv=True,fresh_profile=True)))
        for flag in ('enable_raw_kv','fresh_profile'):
            for bad in (False,1,0,None):
                kwargs=dict(wall_budget=2400,enable_raw_kv=True,fresh_profile=True);kwargs[flag]=bad
                cases.append((deepcopy(snapshot),kwargs))
        for key,bad in (('rows',16),('rows',128.0),('rows',True),('enable_raw_kv',1),('fresh_profile',1)):
            value=deepcopy(snapshot);value[key]=bad
            cases.append((value,dict(wall_budget=2400,enable_raw_kv=True,fresh_profile=True)))
        for key in linked:
            value=deepcopy(snapshot);del value['m128_launch'][key]
            cases.append((value,dict(wall_budget=2400,enable_raw_kv=True,fresh_profile=True)))
        value=deepcopy(snapshot);value['m128_launch']['unapproved']=True
        cases.append((value,dict(wall_budget=2400,enable_raw_kv=True,fresh_profile=True)))
        for index,(value,kwargs) in enumerate(cases):
            with self.subTest(case=index),patch.object(launch,'contract_snapshot',return_value=frozen), \
                    patch.object(admission,'verify_setup') as verify,patch.object(admission,'revalidate') as revalidate:
                with self.assertRaises(ValueError): launch.authorize_run(value,**kwargs)
                verify.assert_not_called();revalidate.assert_not_called()

    def test_authorize_source_profile_receipt_and_reference_drift_rejects(self):
        from . import launch,admission
        frozen,identity,snapshot,linked=self.authorization_fixture();snapshot['m128_launch']=linked
        for change in ('source','source_digest','compact_digest','profile','contract','receipt','identity_sources','past'):
            value=deepcopy(snapshot);returned=deepcopy(identity)
            if change=='source': value['source_sha256']={}
            elif change=='source_digest':value['source_manifest_sha256']='f'*64
            elif change=='compact_digest':value['source_manifest_sha256']=launch.sha(prerequisite.encoded(frozen['sources']))
            elif change=='profile':value['fresh_assets']['profile']='qwen2-public-pv16-fresh-assets-v1'
            elif change=='contract':value['m128_launch']['launch_contract_sha256']='f'*64
            elif change=='receipt':returned.receipt_sha256='f'*64
            elif change=='identity_sources':returned.source_sha256=()
            else:value['independent_reference']['past_tokens']=1
            with self.subTest(change=change),patch.object(launch,'contract_snapshot',return_value=frozen), \
                    patch.object(admission,'verify_setup',return_value=returned),patch.object(admission,'revalidate') as revalidate:
                with self.assertRaises(ValueError):launch.authorize_run(value,wall_budget=2400,enable_raw_kv=True,fresh_profile=True)
                revalidate.assert_not_called()
        with patch.object(launch,'contract_snapshot',return_value=frozen), \
                patch.object(admission,'verify_setup',return_value=identity), \
                patch.object(admission,'revalidate',side_effect=ValueError('CONTROL_ONLY receipt changed')):
            with self.assertRaises(ValueError):launch.authorize_run(snapshot,wall_budget=2400,enable_raw_kv=True,fresh_profile=True)

    def test_bind_refuses_existing_link_or_commit_source_and_revalidation_drift(self):
        from . import launch,admission
        frozen,identity,snapshot,linked=self.authorization_fixture()
        context=dict(contract_sha256=frozen['contract_sha256'],checkout_commit=identity.checkout_commit)
        for change in ('existing','rows','source','contract','commit','revalidation'):
            value=deepcopy(snapshot);ctx=dict(context)
            if change=='existing':value['m128_launch']=linked
            elif change=='rows':value['rows']=True
            elif change=='source':value['source_sha256']={}
            elif change=='contract':ctx['contract_sha256']='f'*64
            elif change=='commit':ctx['checkout_commit']='b'*40
            with self.subTest(change=change),patch.object(launch,'contract_snapshot',return_value=frozen), \
                    patch.object(admission,'revalidate',side_effect=ValueError('CONTROL_ONLY drift') if change=='revalidation' else None):
                with self.assertRaises(ValueError):launch.bind_snapshot(value,identity,ctx)

    def test_real_launch_contract_preparation_preserves_old_contracts(self):
        from . import launch
        before=runtime.contract_snapshot()
        with tempfile.TemporaryDirectory() as temp:
            result=prepare.prepare(Path(temp)/'out',enable_raw_kv=True)
        frozen=launch.contract_snapshot()
        self.assertEqual(result['inputs'],frozen['inputs'])
        self.assertEqual(result['generated'],frozen['generated'])
        self.assertEqual(len(result['inputs']),221)
        self.assertEqual(len(result['generated']),10)
        self.assertEqual(runtime.contract_snapshot(),before)

    def test_final_entry_asset_and_setup_helpers_equal_exact_221_source_map(self):
        from . import launch
        import ctypes
        frozen=launch.contract_snapshot()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in frozen['inputs']:
                path=root/name; path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes((ROOT/name).read_bytes())
            for name in frozen['generated']:(root/name).write_bytes((self.out/name).read_bytes())
            expected=dict(frozen['inputs']); expected.update(frozen['generated'])
            self.assertEqual(len(expected),221)
            def extract(relative,assignments,methods,namespace):
                tree=ast.parse((root/relative).read_bytes())
                selected=[n for n in tree.body if
                    (isinstance(n,ast.FunctionDef) and n.name in methods) or
                    (isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in assignments for t in n.targets))]
                self.assertEqual({n.name for n in selected if isinstance(n,ast.FunctionDef)},set(methods))
                self.assertEqual({t.id for n in selected if isinstance(n,ast.Assign)
                    for t in n.targets if isinstance(t,ast.Name)},set(assignments))
                exec(compile(ast.Module(body=selected,type_ignores=[]),str(root/relative),'exec'),namespace)
                return types.SimpleNamespace(**namespace)
            original_import=builtins.__import__
            def no_numerics(name,*args,**kwargs):
                if name.split('.')[0] in ('numpy','torch','transformers'):
                    raise AssertionError('numerical import forbidden: '+name)
                return original_import(name,*args,**kwargs)
            package=sys.modules['candidates.qwen2_resident_matrix.raw_kv_public_fresh']
            with ExitStack() as stack:
                for module in (launch,runtime,runtime.prior,prerequisite):
                    stack.enter_context(patch.object(module,'ROOT',root))
                stack.enter_context(patch('builtins.__import__',side_effect=no_numerics))
                stack.enter_context(patch.object(ctypes,'CDLL',side_effect=AssertionError('native load forbidden')))
                stack.enter_context(patch.object(ctypes,'PyDLL',side_effect=AssertionError('native load forbidden')))
                assets=load_source(root/prerequisite.ASSETS,
                    'candidates.qwen2_resident_matrix.raw_kv_public_fresh._assets128_launch_closure')
                stack.enter_context(patch.object(package,'assets',assets))
                setup=load_source(root/prerequisite.SETUP,
                    'candidates.qwen2_resident_matrix.raw_kv_public_fresh._setup128_launch_closure')
                self.assertEqual(assets.own_sources(),expected)
                self.assertEqual(assets.source_snapshot(enable_raw_kv=True),expected)
                self.assertEqual(setup.source_snapshot(True),expected)
                self.assertEqual(setup.asset_sources(expected),expected)
                prefix='candidates/qwen2_resident_matrix/ffn_public/'
                helper=load_source(root/(prefix+'check_numeric.py'),'launch_fullgraph_base_identity')
                base=load_source(root/(prefix+'check_prefix_numeric.py'),'launch_prefix_identity',allow_ctypes=True)
                stack.enter_context(patch.dict(sys.modules,{
                    'candidates.qwen2_resident_matrix.ffn_public.check_numeric':helper}))
                fullgraph=extract(prefix+'check_fullgraph_numeric.py',('LIBRARY_SOURCES',),('source_hashes',),
                    dict(ROOT=root,base=base,file_sha=base.file_sha,importlib=importlib,sys=sys))
                self.assertEqual(len(fullgraph.source_hashes()),75)
                official=extract('candidates/qwen2_resident_matrix/official_bf16/check_numeric.py',
                    ('PREFIX','NEW_SOURCES'),('source_hashes',),
                    dict(ROOT=root,old=fullgraph,require=base.require,file_sha=base.file_sha,fresh_assets=assets))
                entry=extract(prerequisite.ENTRY,
                    ('PREFIX','EXECUTION_FILES','RAW_KV_SOURCES','RAW_KV_COMPOSITION_SHA256'),
                    ('source_hashes','_verify_raw_kv_composition','_raw_kv_mode'),
                    dict(ROOT=root,prior=official,require=base.require,file_sha=base.file_sha))
                self.assertEqual(entry.source_hashes(fresh_profile=True,enable_raw_kv=True),expected)


if __name__=='__main__':
    unittest.main()
