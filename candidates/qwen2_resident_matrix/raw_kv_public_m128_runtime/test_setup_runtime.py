"""Cold M128 setup/runtime controls. Mock receipts are not numerical evidence.

Source patches are composed in temporary directories. No packages, producers,
native libraries, downloads or actual-chain execution are permitted here.
"""
import ast
import builtins
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import importlib.util
import math
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

from ..raw_kv_public_fresh import assets as old_assets
from ..raw_kv_public_fresh import setup as old_setup
from ..raw_kv_public_m128 import profile as frozen_preparation
from ..raw_kv_public_m128 import prerequisite

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
COMMIT = 'a' * 40


def functions(raw):
    return {node.name: node for node in ast.parse(raw).body if isinstance(node, ast.FunctionDef)}


def load_source(path, name, *, allow_ctypes=False):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    original_import = builtins.__import__
    def cold_import(name, *args, **kwargs):
        if name.split('.')[0] in ('numpy', 'torch', 'transformers') or (name == 'ctypes' and not allow_ctypes):
            raise AssertionError('numerical/native import forbidden: ' + name)
        return original_import(name, *args, **kwargs)
    with patch('builtins.__import__', side_effect=cold_import):
        spec.loader.exec_module(module)
    return module


class SetupRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from . import runtime
        cls.runtime = runtime
        cls.temp = tempfile.TemporaryDirectory(prefix='setup128-cold-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.tree = Path(cls.temp.name) / 'composed'
        cls.baseline = frozen_preparation.prepare(cls.tree, enable_raw_kv=True)
        cls.before_bridge = {name: (cls.tree / name).read_bytes()
            for name in (prerequisite.ASSETS, prerequisite.ENTRY)}
        (cls.tree / prerequisite.SETUP).write_bytes((ROOT / prerequisite.SETUP).read_bytes())
        for filename in ('setup128.patch', 'bridging.patch'):
            subprocess.run(['patch', '--batch', '--fuzz=0', '-p1'], cwd=cls.tree,
                input=(HERE / filename).read_bytes(), capture_output=True, check=True, timeout=10)
        cls.assets = load_source(cls.tree / prerequisite.ASSETS,
            'candidates.qwen2_resident_matrix.raw_kv_public_fresh._assets128_runtime_control')
        package = sys.modules['candidates.qwen2_resident_matrix.raw_kv_public_fresh']
        # Import-time receipt projection is a CONTROL_ONLY fixture. Real frozen
        # maps are independently exercised by test_runtime and the preparer test.
        with patch.object(package, 'assets', cls.assets), \
                patch.object(runtime, 'base_verifier_sources', return_value={'CONTROL_ONLY/source.py': '0'*64}):
            cls.setup = load_source(cls.tree / prerequisite.SETUP,
                'candidates.qwen2_resident_matrix.raw_kv_public_fresh._setup128_runtime_control')
        cls.generated = functions((cls.tree / prerequisite.SETUP).read_bytes())
        cls.original = functions((ROOT / prerequisite.SETUP).read_bytes())

    def test_source_guards_cleanup_backend_and_original_supervisor_are_unchanged(self):
        for name in ('_cleanup', 'run_group', 'phase_command', 'child_environment', 'phase_receipt',
                     'remaining', 'backend_identity', 'backend_threads', 'backend_preflight',
                     '_phase_environment', '_phase_acquisition', '_phase_library', '_read_context',
                     'safe_diagnostic', 'validate_diagnostic', 'save_evidence', 'atomic_json',
                     'fresh_directories', 'internal_phase', 'main'):
            self.assertEqual(ast.dump(self.generated[name]), ast.dump(self.original[name]), name)
        run = deepcopy(self.generated['run'])
        row_keywords = [node for node in ast.walk(run) if isinstance(node, ast.keyword) and node.arg == 'rows']
        self.assertEqual(len(row_keywords), 1)
        self.assertEqual(row_keywords[0].value.value, 128)
        row_keywords[0].value = ast.Constant(16)
        self.assertEqual(ast.dump(run), ast.dump(self.original['run']))
        self.assertEqual((self.setup.TOTAL_SECONDS, self.setup.CLEANUP_SECONDS, self.setup.RECEIPT_SECONDS), (900,5,1))
        self.assertEqual(self.setup.PHASE_LIMITS, dict(preflight=20, environment=120, acquisition=420,
            references=140, native16=60, native128=120, library=40, seal=30))
        self.assertEqual(tuple(self.setup.PRODUCERS), self.setup.PHASES)

    def test_references_only_change_rows_and_reviewed_45_second_ceiling(self):
        node = deepcopy(self.generated['_phase_references'])
        class RestoreRows(ast.NodeTransformer):
            def visit_Constant(self, node):
                if type(node.value) is int and node.value in (128,45):
                    return ast.Constant({128:16,45:30}[node.value])
                if node.value == '128': return ast.Constant('16')
                return node
        restored = RestoreRows().visit(node)
        self.assertEqual(ast.dump(restored), ast.dump(self.original['_phase_references']))
        calls = [node for node in ast.walk(self.generated['_phase_references']) if isinstance(node, ast.Call)]
        by_attribute = {node.func.attr: node for node in calls if isinstance(node.func, ast.Attribute)}
        self.assertEqual(by_attribute['write_arena'].args[2].value, 128)
        self.assertEqual(by_attribute['software_ack'].args[1].value, 128)
        self.assertEqual(by_attribute['load_actual'].args[-1].value, 128)
        ceilings = [node.args[1].value for node in calls if isinstance(node.func, ast.Name) and node.func.id == 'remaining']
        self.assertEqual(sorted(ceilings), [1,10,45])

    def exercise(self, root, *, step=10, deadline=None, fail_phase=None):
        """Real supervisor/tiny receipts, with no child processes executed."""
        setup = self.setup; clock = [1000.0]; calls = []
        sources = {'CONTROL_ONLY/source.py':'0'*64, setup.PROFILE_PATH:'1'*64}
        def child(command, **kwargs):
            phase = command[command.index('--internal-phase') + 1]
            calls.append((phase, clock[0], kwargs['timeout'], kwargs['grace'], command))
            workspace = root / 'private'
            if phase == fail_phase: return 9
            receipt = dict(schema=1, phase=phase, status='COMPLETE_SETUP_PHASE',
                source_manifest_sha256=setup.assets.sha(setup.assets.encoded(sources)))
            if phase == 'seal':
                (workspace/'ASSETS.json').write_text('{}')
                receipt['manifest_sha256'] = setup.digest(workspace/'ASSETS.json')
            (workspace/(phase+'.complete.json')).write_text(json.dumps(receipt))
            clock[0] += step
            return 0
        with ExitStack() as stack:
            for target, name, options in (
                (setup,'source_snapshot',dict(return_value=sources)),
                (setup,'asset_sources',dict(side_effect=lambda value: dict(value))),
                (setup,'run_group',dict(side_effect=child)),
                (setup.time,'monotonic',dict(side_effect=lambda: clock[0])),
                (setup.signal,'getitimer',dict(return_value=(0.0,0.0))),
                (setup.signal,'setitimer',{}), (setup.signal,'signal',{})):
                stack.enter_context(patch.object(target, name, **options))
            code, summary = setup.run(root/'private', root/'evidence', checkout_commit=COMMIT,
                enable_raw_kv=True, deadline_ns=deadline)
        return code, summary, calls

    def test_supervisor_orders_two_native_children_under_one_900_second_budget(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); code, summary, calls = self.exercise(root)
            self.assertEqual((code,summary['status']), (0,self.setup.SETUP_STATUS))
            self.assertEqual([call[0] for call in calls], list(self.setup.PHASES))
            self.assertEqual(summary['completed_phases'], list(self.setup.PHASES))
            self.assertIs(summary['actual_chain_executed'], False)
            self.assertIs(summary['numerical_acceptance'], False)
            context = json.loads((root/'private/context.json').read_text())
            receipt = json.loads((root/'private/SETUP.json').read_text())
            self.assertEqual(context['work_deadline_ns'], 1894_000_000_000)
            self.assertEqual(receipt['deadline_monotonic_ns'], 1900_000_000_000)
            self.assertEqual((receipt['rows'],receipt['past_tokens'],receipt['total_budget_seconds']), (128,0,900))
            self.assertEqual(context['asset_source_sha256'], context['source_sha256'])
            for phase, started, timeout, grace, command in calls:
                self.assertEqual(timeout, min(self.setup.PHASE_LIMITS[phase],1894-started))
                self.assertEqual(grace,5)
                self.assertEqual(command[0], sys.executable if phase in ('preflight','environment')
                                 else str(root/'private/venv/bin/python'))
            self.assertNotIn(temp, ''.join(p.read_text() for p in (root/'evidence').iterdir()))

    def test_deadline_cannot_restart_between_native_phases_or_expand(self):
        for delta, step, expected_calls in ((6000,10,8), (60,10,6), (5,0,0)):
            with self.subTest(delta=delta), tempfile.TemporaryDirectory() as temp:
                root=Path(temp); code, summary, calls = self.exercise(root,step=step,deadline=(1000+delta)*10**9)
                self.assertEqual(len(calls), expected_calls)
                if delta == 6000:
                    self.assertEqual(code,0)
                    self.assertEqual(json.loads((root/'private/context.json').read_text())['work_deadline_ns'],1894*10**9)
                else:
                    self.assertNotEqual(code,0)
                    self.assertEqual(summary['reason'],'deadline')
                    self.assertFalse((root/'private/SETUP.json').exists())
                for _, started, timeout, _, _ in calls:
                    self.assertLessEqual(timeout, min(1900,1000+delta)-6-started)

    def test_native16_failure_stops_before_native128_and_never_accepts(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); code, summary, calls = self.exercise(root,fail_phase='native16')
            self.assertEqual((code,summary['status']), (1,'SETUP_FAILED'))
            self.assertEqual([c[0] for c in calls], list(self.setup.PHASES[:5]))
            self.assertEqual(summary['completed_phases'], list(self.setup.PHASES[:4]))
            self.assertIs(summary['numerical_acceptance'],False)
            self.assertFalse((root/'private/SETUP.json').exists())

    def test_original_native_gate_called_once_per_phase_with_bound_small_gate(self):
        setup=self.setup; native=Mock(); native.run_gate.return_value={'status':'PASS_BF16_STAGE_BUDGET'}
        scripts=types.ModuleType('scripts'); scripts.qwen2_layer0_model_gate=native
        torch=object(); context={'CONTROL_ONLY':True}
        with tempfile.TemporaryDirectory() as temp:
            workspace=Path(temp); small=workspace/'native_m16/RESULT.json'
            small.parent.mkdir(); small.write_text('{}')
            with patch.dict(sys.modules,{'scripts':scripts}), \
                    patch.object(setup,'backend_identity',return_value=(torch,{})), \
                    patch.object(setup,'backend_threads') as threads, patch.object(setup,'remaining') as remaining:
                setup._phase_native16(context,workspace)
                setup._phase_native128(context,workspace)
            self.assertEqual(native.run_gate.call_count,2)
            first, second=native.run_gate.call_args_list
            self.assertEqual(first.args,(setup.ROOT,workspace/'payload',workspace/'native_m16'))
            self.assertEqual(first.kwargs,dict(tokens=16,carried=False,threads=4))
            self.assertEqual(second.args,(setup.ROOT,workspace/'payload',workspace/'native'))
            self.assertEqual(second.kwargs,dict(tokens=128,carried=False,threads=4,small_gate=small))
            self.assertEqual(threads.call_count,2); threads.assert_called_with(torch)
            self.assertEqual(remaining.call_count,2); remaining.assert_called_with(context,1)
            native.run_gate.reset_mock(); small.unlink()
            with patch.dict(sys.modules,{'scripts':scripts}), patch.object(setup,'backend_identity',return_value=(torch,{})):
                with self.assertRaises((ValueError,OSError)): setup._phase_native128(context,workspace)
            native.run_gate.assert_not_called()

    def test_seal_constructs_all_232_native_metadata_exports(self):
        setup=self.setup; a=setup.assets; sources={'CONTROL_ONLY/source.py':'0'*64}
        with tempfile.TemporaryDirectory() as temp:
            workspace=Path(temp)
            def CONTROL_ONLY_record(workspace,path):
                name=path.name; parts=path.relative_to(workspace).parts; size=1; identity='0'*64
                if parts[0]=='payload' and name.endswith('.bin'):
                    pin=a.TENSOR_PINS[name[:-4]]; size=pin['bytes']; identity=pin['sha256']
                elif parts[0]=='readonly':
                    size,identity={'readonly_arena.f32le':(a.ARENA_BYTES,a.ARENA_SHA256),
                        'rope_full.f32le':(328448,a.TABLE_SHA256),
                        'input_x.f32le':(128*1536*4,a.INPUT_X_SHA256)}[name]
                elif name=='candidate.cpp': identity=a.CPP_SHA256[parts[0]]
                elif name=='block_layout.h': identity=a.HEADER_SHA256
                elif 'raw_stages' in parts: size=a.output_inventory()[name]
                elif 'tensors' in parts: size=4*math.prod(a.shapes()[name[len('candidate_'):-len('.f32le')]])
                elif parts[0] in ('native_m16','native') and name.endswith('.f32le'):
                    rows=16 if parts[0]=='native_m16' else 128
                    node=name.split('_',1)[1][:-len('.f32le')]
                    size=4*math.prod(a.shapes(rows)[node])
                    if node=='x': identity=a.M16_X_SHA256 if rows==16 else a.INPUT_X_SHA256
                return dict(path=str(path.relative_to(workspace)),bytes=size,sha256=identity)
            context=dict(asset_source_sha256=sources,enable_raw_kv=True)
            with patch.object(setup,'file_record',side_effect=CONTROL_ONLY_record), \
                    patch.object(a,'verify') as verify, patch.object(setup,'remaining'):
                identity=setup._phase_seal(context,workspace)
            m=json.loads((workspace/'ASSETS.json').read_text())
            self.assertEqual((m['rows'],m['past_tokens']), (128,0))
            self.assertEqual(m['source_sha256'],sources)
            for role in ('native_m16','native'):
                self.assertEqual(sum(len(nodes) for methods in m[role]['outputs'].values() for nodes in methods.values()),116)
            self.assertEqual(m['native_m16']['outputs']['bf16']['official_self_cache']['x']['bytes'],98304)
            self.assertEqual(m['native']['outputs']['bf16']['official_self_cache']['x']['bytes'],786432)
            verify.assert_called_once_with(workspace/'ASSETS.candidate.json',identity,rows=128,enable_raw_kv=True)
            self.assertEqual([p.name for p in workspace.iterdir()],['ASSETS.json'])

    def test_bridge_scope_rejects_callback_or_loaded_source_guard_drift(self):
        from . import prepare
        after={name:(self.tree/name).read_bytes() for name in prepare.BRIDGE_TARGETS}
        prepare.check_bridge_scope(self.before_bridge,after)
        for name in prepare.BRIDGE_TARGETS:
            changed=dict(after)
            tree=ast.parse(changed[name]); node=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef))
            node.body.insert(0,ast.parse('unapproved_callback()').body[0])
            changed[name]=ast.unparse(tree)
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'source-identity plumbing|guard/return'):
                prepare.check_bridge_scope(self.before_bridge,changed)
        changed=dict(after); tree=ast.parse(changed[prerequisite.ASSETS])
        own=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='own_sources')
        own.body[0]=ast.Pass(); changed[prerequisite.ASSETS]=ast.unparse(tree)
        with self.assertRaisesRegex(ValueError,'guard/return'): prepare.check_bridge_scope(self.before_bridge,changed)

    def test_source_map_helpers_delegate_exactly_and_reject_noncanonical_flag(self):
        setup=self.setup; runtime=self.runtime; sources={'CONTROL_ONLY/source.py':'0'*64}
        with patch.object(runtime,'verify_loaded_setup') as loaded, \
                patch.object(runtime,'setup_source_snapshot',return_value=sources) as snapshot:
            self.assertIs(setup.source_snapshot(True),sources)
            loaded.assert_called_once_with(setup.IMPORTED_SETUP_SHA256); snapshot.assert_called_once_with(True)
            for bad in (1,0,None,'true'):
                with self.subTest(flag=bad),self.assertRaises(setup.SetupError): setup.source_snapshot(bad)
            self.assertEqual(snapshot.call_count,1)
        with patch.object(runtime,'asset_sources',return_value=sources) as select:
            self.assertIs(setup.asset_sources(sources),sources); select.assert_called_once_with(sources)
        preflight=ast.unparse(self.generated['_phase_preflight'])
        self.assertIn('for name in m128_runtime.setup_git_sources():',preflight)
        self.assertIn("['git', 'show', 'HEAD:' + name]",preflight)

    def test_actual_entry_asset_and_setup_source_helpers_equal_exact_composed_map(self):
        # Importing the full original entry crosses its numerical owners. Extract
        # only its actual source-hash functions; all unions and file hashes run.
        # The prefix helpers and Matrix metadata module are original source, not
        # a stubbed source map. No runtime(), prepare() or numerical run() is used.
        import ctypes
        frozen=self.runtime.contract_snapshot()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in frozen['inputs']:
                path=root/name; path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes((ROOT/name).read_bytes())
            for name in frozen['generated']:
                (root/name).write_bytes((self.tree/name).read_bytes())
            expected=dict(frozen['inputs']); expected.update(frozen['generated'])
            self.assertEqual(len(expected),210)
            def extract(relative, assignments, methods, namespace):
                tree=ast.parse((root/relative).read_bytes())
                selected=[node for node in tree.body if
                    (isinstance(node,ast.FunctionDef) and node.name in methods) or
                    (isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id in assignments for t in node.targets))]
                self.assertEqual({node.name for node in selected if isinstance(node,ast.FunctionDef)},set(methods))
                self.assertEqual({t.id for node in selected if isinstance(node,ast.Assign)
                                  for t in node.targets if isinstance(t,ast.Name)},set(assignments))
                exec(compile(ast.Module(body=selected,type_ignores=[]),str(root/relative),'exec'),namespace)
                return types.SimpleNamespace(**namespace)
            imported=builtins.__import__
            def no_numerics(name,*args,**kwargs):
                if name.split('.')[0] in ('numpy','torch','transformers'):
                    raise AssertionError('numerical import forbidden: '+name)
                return imported(name,*args,**kwargs)
            package=sys.modules['candidates.qwen2_resident_matrix.raw_kv_public_fresh']
            with ExitStack() as stack:
                for module in (self.runtime,frozen_preparation,prerequisite):
                    stack.enter_context(patch.object(module,'ROOT',root))
                stack.enter_context(patch('builtins.__import__',side_effect=no_numerics))
                stack.enter_context(patch.object(ctypes,'CDLL',side_effect=AssertionError('native load forbidden')))
                stack.enter_context(patch.object(ctypes,'PyDLL',side_effect=AssertionError('native load forbidden')))
                assets=load_source(root/prerequisite.ASSETS,
                    'candidates.qwen2_resident_matrix.raw_kv_public_fresh._assets128_exact_closure')
                stack.enter_context(patch.object(package,'assets',assets))
                setup=load_source(root/prerequisite.SETUP,
                    'candidates.qwen2_resident_matrix.raw_kv_public_fresh._setup128_exact_closure')
                self.assertEqual(assets.own_sources(),expected)
                self.assertEqual(assets.source_snapshot(enable_raw_kv=True),expected)
                self.assertEqual(setup.source_snapshot(True),expected)
                self.assertEqual(setup.asset_sources(expected),expected)
                prefix='candidates/qwen2_resident_matrix/ffn_public/'
                helper=load_source(root/(prefix+'check_numeric.py'),'cold_fullgraph_base_identity')
                base=load_source(root/(prefix+'check_prefix_numeric.py'),'cold_prefix_identity',allow_ctypes=True)
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
                actual=entry.source_hashes(fresh_profile=True,enable_raw_kv=True)
                self.assertEqual(actual,expected)
                self.assertEqual(set(actual),set(expected))
                self.assertEqual(self.assets.sha(self.assets.encoded(actual)),
                                 self.assets.sha(self.assets.encoded(expected)))

    def test_real_ten_overlay_preparation_preserves_frozen_inputs(self):
        from . import prepare
        before=frozen_preparation.contract_snapshot()
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'prepared'; result=prepare.prepare(out,enable_raw_kv=True)
            self.assertEqual(result['status'],'PASS_PREPARATION_ONLY')
            self.assertEqual(len(result['generated']),10)
            self.assertEqual(result['generated'],self.runtime.contract_snapshot()['generated'])
            for field in ('numerical_execution','native_execution','m128_executed','full_29_node_acceptance'):
                self.assertIs(result[field],False)
            with self.assertRaises(ValueError): prepare.prepare(out,enable_raw_kv=True)
        self.assertEqual(frozen_preparation.contract_snapshot(),before)
        self.assertEqual(old_setup.TOTAL_SECONDS,600)
        self.assertEqual(old_assets.PROFILE,'qwen2-public-pv16-fresh-assets-v1')


if __name__=='__main__':
    unittest.main()
