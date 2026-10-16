"""Cold linked-M128 composition tests. No producer or numerical execution."""
import ast
import builtins
from contextlib import ExitStack
from copy import deepcopy
import difflib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

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
        self.assertEqual(len(additions),3)
        self.assertTrue(all(line.startswith('+from ..raw_kv_public_m128_run import launch as ') for line in additions))

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
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'import-only scope'):
                prepare.check_bridge_scope(self.originals,changed)
        changed=dict(self.bridged)
        changed[prerequisite.ASSETS]=changed[prerequisite.ASSETS].replace(
            b'need(file_sha(Path(__file__)) == IMPORTED_SOURCE_SHA256',b'need(True')
        with self.assertRaisesRegex(ValueError,'import-only scope'):
            prepare.check_bridge_scope(self.originals,changed)
        for mutation in ('missing','duplicate'):
            changed=dict(self.bridged)
            if mutation=='missing': del changed[prerequisite.SETUP]
            else: changed[prerequisite.SETUP]+=b'\nfrom ..raw_kv_public_m128_run import launch as m128_runtime\n'
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
