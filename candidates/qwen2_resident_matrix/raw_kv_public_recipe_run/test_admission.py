"""Cold linkage tests. Synthetic metadata is never asset/numerical readiness.

No producer, Torch, ELF, full-size payload, numerical entry or CI is executed.
All legacy receipt, inode and source links remain enforced; six recipe
metadata files are bound without invoking their numerical/native validators.
"""
from copy import deepcopy
import ast
import sys
from pathlib import Path
import hashlib
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch

from . import admission as a, launch
import builtins
import importlib.util
import types
from contextlib import ExitStack
from ..raw_kv_public_fresh import assets as original_assets, setup as original_setup
from ..raw_kv_public_m128.test_assets128 import manifest_fixture
from ..raw_kv_public_recipe_runtime import runtime as pair_runtime, prepare as pair_prepare
from ..raw_kv_public_recipe_runtime import admission as pair_admission

SOURCE_COUNT = launch.SOURCE_COUNT
GENERATED_COUNT = launch.GENERATED_COUNT

assets = original_assets
setup = None


def load_pair_assets(out):
    # Real reviewed source composition in a temporary tree; no producer call.
    pair_prepare.prepare(out)
    path = out / 'candidates/qwen2_resident_matrix/raw_kv_public_fresh/assets.py'
    spec = importlib.util.spec_from_file_location(
        'candidates.qwen2_resident_matrix.raw_kv_public_fresh._pair_admission_control',path)
    module = importlib.util.module_from_spec(spec)
    imported = builtins.__import__
    def cold_import(name,*args,**kwargs):
        if name.split('.')[0] in ('numpy','torch','transformers','ctypes'):
            raise AssertionError('numerical import forbidden')
        return imported(name,*args,**kwargs)
    with patch('builtins.__import__',side_effect=cold_import):spec.loader.exec_module(module)
    return module


def recipe_fixture():
    def record(path, digest='0' * 64):return dict(path=path,bytes=1,sha256=digest)
    value=dict(generated_module=record('generated/qwen2_layer0_model_gate.py',pair_runtime.GENERATED_MODULE_SHA256))
    for role in ('qk','qkv'):
        value[role]=dict(binary=record(role+'_library/'+role+'_pair.so'),
            receipt=record(role+'_library/'+role+'_pair_compile.json'))
    for name in ('native16','native128'):
        value[name]=dict(report=record('phase_'+name+'.json'),
            diagnostics=record('phase_'+name+'_diagnostics.json'))
    return value


def setup_control():
    # Names/geometry are authentic; no source authority or producer PASS is claimed.
    result = types.SimpleNamespace(**vars(original_setup))
    result.PROFILE = pair_runtime.SETUP_PROFILE
    result.BASE_COMMIT = pair_runtime.BASE_COMMIT
    result.PROFILE_PATH = 'candidates/qwen2_resident_matrix/raw_kv_public_recipe_run/launch-contract.json'
    result.TOTAL_SECONDS = 900
    result.PHASES = a.PHASES
    return result

CHECKOUT = '1' * 40


def write(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    raw = assets.encoded(value)
    path.write_bytes(raw)
    return assets.sha(raw)


class ControlFixture:
    """Complete linked JSON fixture with stubbed source prerequisite only."""
    def __init__(self, root):
        self.workspace = root/'private';self.workspace.mkdir()
        self.summary_path = root/'safe/summary.json'
        self.sources = {'CONTROL_ONLY/source_%03d.py'%i:'a'*64 for i in range(SOURCE_COUNT - 1)}
        self.sources[setup.PROFILE_PATH] = 'c'*64
        self.asset_sources = self.sources
        self.manifest = manifest_fixture(assets)
        self.manifest['recipe'] = recipe_fixture()
        self.recipe_records = [self.manifest['recipe'][role]['receipt'] for role in ('qk','qkv')]
        self.recipe_records += [self.manifest['recipe'][case][key] for case in ('native16','native128')
            for key in ('report','diagnostics')]
        for item in self.recipe_records:
            path=self.workspace/item['path'];path.parent.mkdir(parents=True,exist_ok=True)
            raw=assets.encoded({'CONTROL_ONLY':item['path']});path.write_bytes(raw)
            item.update(bytes=len(raw),sha256=assets.sha(raw))
        self.manifest['source_sha256'] = self.asset_sources
        self.manifest['source_manifest_sha256'] = assets.sha(assets.encoded(self.asset_sources))
        library = self.workspace/self.manifest['library']['receipt']['path']
        raw = assets.encoded({'CONTROL_ONLY':True})
        library.parent.mkdir(parents=True);library.write_bytes(raw)
        self.manifest['library']['receipt'].update(bytes=len(raw),sha256=assets.sha(raw))
        info = self.workspace.stat()
        source_hash = assets.sha(assets.encoded(self.sources))
        self.receipt = dict(schema=1,profile=setup.PROFILE,status=setup.SETUP_STATUS,
            base_commit=setup.BASE_COMMIT,base_profile=assets.PROFILE,
            base_verifier_sha256=dict(setup.BASE_VERIFIER_SHA256),setup_profile_sha256=self.sources[setup.PROFILE_PATH],
            source_sha256=self.sources,source_manifest_sha256=source_hash,
            asset_source_manifest_sha256=self.manifest['source_manifest_sha256'],asset_manifest_sha256='',
            enable_raw_kv=True,rows=128,past_tokens=0,
            workspace=dict(path=str(self.workspace),device=info.st_dev,inode=info.st_ino),
            checkout_commit=CHECKOUT,completed_phases=list(setup.PHASES),source_recheck='UNCHANGED',
            deadline_monotonic_ns=10**12,elapsed_seconds=12.0,total_budget_seconds=900,
            actual_chain_executed=False,numerical_acceptance=False)
        self.summary = dict(schema=1,status=setup.SETUP_STATUS,phase='seal',elapsed_seconds=12.0,
            completed_phases=list(setup.PHASES),total_budget_seconds=900,cleanup_grace_seconds=5,
            actual_chain_executed=False,numerical_acceptance=False,source_manifest_sha256=source_hash,
            manifest_sha256='',reason='fresh_assets_verified',source_recheck='UNCHANGED',
            setup_profile=setup.PROFILE,setup_profile_sha256=self.sources[setup.PROFILE_PATH],
            asset_source_manifest_sha256=self.manifest['source_manifest_sha256'],setup_receipt_sha256='')
        self.seal()

    def seal(self):
        manifest_hash = write(self.workspace/'ASSETS.json',self.manifest)
        self.receipt['asset_manifest_sha256'] = self.summary['manifest_sha256'] = manifest_hash
        self.summary['setup_receipt_sha256'] = write(self.workspace/'SETUP.json',self.receipt)
        write(self.summary_path,self.summary)
        for phase in setup.PHASES:
            value = dict(schema=1,phase=phase,status='COMPLETE_SETUP_PHASE',
                         source_manifest_sha256=self.receipt['source_manifest_sha256'])
            if phase == 'seal':value['manifest_sha256'] = manifest_hash
            write(self.workspace/(phase+'.complete.json'),value)

    def admit(self, **changes):
        kwargs = dict(checkout_commit=CHECKOUT,enable_raw_kv=True,rows=128);kwargs.update(changes)
        with patch.object(setup,'source_snapshot',return_value=deepcopy(self.sources)):
            return a.verify_setup(self.workspace,self.summary_path,**kwargs)


class LinkedAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global assets,setup
        cls.source_temp = tempfile.TemporaryDirectory(prefix='pair-linked-admission-source-')
        cls.addClassCleanup(cls.source_temp.cleanup)
        assets = load_pair_assets(Path(cls.source_temp.name)/'composed')
        setup = setup_control()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.context = ExitStack();self.addCleanup(self.context.close)
        self.context.enter_context(patch.object(a,'assets',assets))
        self.context.enter_context(patch.object(a,'setup',setup))
        self.f = ControlFixture(self.root)
        self.generated = dict(list(self.f.sources.items())[:GENERATED_COUNT])
        self.launch_control = types.SimpleNamespace(SOURCE_COUNT=SOURCE_COUNT,GENERATED_COUNT=GENERATED_COUNT,
            contract_snapshot=Mock(side_effect=lambda **kw:dict(sources=deepcopy(self.f.sources),generated=self.generated)))
        self.context.enter_context(patch.object(a,'selected_profile',return_value=self.launch_control))
        self.context.enter_context(patch.object(setup,'asset_sources',side_effect=lambda sources:dict(sources)))

    def test_complete_control_linkage_and_safe_projection(self):
        result = self.f.admit()
        self.assertEqual(result.manifest,self.f.workspace/'ASSETS.json')
        self.assertEqual(result.source_sha256,self.f.sources)
        copied = result.source_sha256;copied.clear();self.assertEqual(len(result.source_sha256),SOURCE_COUNT)
        safe = a.safe_identity(result)
        self.assertFalse(safe['actual_chain_executed']);self.assertFalse(safe['numerical_acceptance'])
        self.assertEqual(safe['completed_phase_count'],9)
        self.assertNotIn(str(self.root),json.dumps(safe))
        with patch.object(setup,'source_snapshot',return_value=deepcopy(self.f.sources)):
            self.assertEqual(a.revalidate(result),result)

    def test_request_domain_before_any_file_access(self):
        for changed in ({'rows':True},{'rows':16},{'enable_raw_kv':1},{'enable_raw_kv':False},{'checkout_commit':'bad'},
                        {'checkout_commit':'A'*40}):
            with self.subTest(changed=changed), patch.object(assets,'safe_path',side_effect=AssertionError('file access')):
                with self.assertRaises(ValueError):self.f.admit(**changed)

    def test_standalone_ready_cannot_bypass_private_commit(self):
        (self.f.workspace/'SETUP.json').unlink()
        with patch.object(setup,'source_snapshot',side_effect=AssertionError('source work')):
            with self.assertRaises(FileNotFoundError):self.f.admit()

    def test_provisional_failed_or_incomplete_summary_rejected(self):
        for status in ('READY_FOR_ACTUAL_M128','SETUP_VERIFYING','SETUP_FAILED','SETUP_TIMEOUT','SETUP_INTERRUPTED'):
            with self.subTest(status=status):
                self.f.summary['status'] = status;self.f.seal()
                with self.assertRaises(ValueError):self.f.admit()
        self.f.summary['status'] = setup.SETUP_STATUS
        self.f.summary.pop('setup_receipt_sha256');write(self.f.summary_path,self.f.summary)
        with self.assertRaises(ValueError):self.f.admit()

    def test_exact_private_and_summary_schemas(self):
        for target in ('receipt','summary'):
            original = deepcopy(getattr(self.f,target))
            for mutation in ('extra','missing'):
                with self.subTest(target=target,mutation=mutation):
                    value = deepcopy(original)
                    if mutation == 'extra':value['unreviewed'] = True
                    else:value.pop('schema')
                    setattr(self.f,target,value);self.f.seal()
                    with self.assertRaises(ValueError):self.f.admit()
            setattr(self.f,target,original)

    def test_canonical_workload_profile_budget_and_completion(self):
        bad = (('rows',True),('rows',16),('past_tokens',False),('past_tokens',1),
            ('enable_raw_kv',1),('enable_raw_kv',False),('schema',True),('profile','wrong'),
            ('base_profile','wrong'),('base_commit','2'*40),('checkout_commit','2'*40),
            ('source_recheck','FAILED'),('total_budget_seconds',True),('total_budget_seconds',901),
            ('deadline_monotonic_ns',True),('deadline_monotonic_ns',0),('elapsed_seconds',True),
            ('elapsed_seconds',901),('actual_chain_executed',0),('numerical_acceptance',0),
            ('completed_phases',list(reversed(setup.PHASES))))
        original = deepcopy(self.f.receipt)
        for name,value in bad:
            with self.subTest(name=name,value=value):
                self.f.receipt = deepcopy(original);self.f.receipt[name] = value;self.f.seal()
                with self.assertRaises(ValueError):self.f.admit()
        self.f.receipt = original
        for name,value in (('cleanup_grace_seconds',True),('cleanup_grace_seconds',6),('phase','native'),
                           ('reason','awaiting_private_commit'),('elapsed_seconds',False)):
            original_summary = deepcopy(self.f.summary)
            with self.subTest(summary=name):
                self.f.summary[name] = value;self.f.seal()
                with self.assertRaises(ValueError):self.f.admit()
            self.f.summary = original_summary

    def test_each_source_and_receipt_link_fails_closed(self):
        for target,key in (('receipt','source_manifest_sha256'),('receipt','asset_source_manifest_sha256'),
            ('receipt','setup_profile_sha256'),('summary','source_manifest_sha256'),
            ('summary','asset_source_manifest_sha256'),('summary','setup_profile_sha256')):
            original = deepcopy(getattr(self.f,target))
            with self.subTest(target=target,key=key):
                getattr(self.f,target)[key] = 'f'*64;self.f.seal()
                with self.assertRaises(ValueError):self.f.admit()
            setattr(self.f,target,original)
        self.f.seal();self.f.summary['setup_receipt_sha256'] = 'f'*64;write(self.f.summary_path,self.f.summary)
        with self.assertRaises(ValueError):self.f.admit()
        self.f.seal();self.f.manifest['source_sha256'] = dict(self.f.manifest['source_sha256'])
        self.f.manifest['source_sha256']['CONTROL_ONLY/source_000.py'] = 'e'*64
        self.f.manifest['source_manifest_sha256'] = assets.sha(assets.encoded(self.f.manifest['source_sha256']))
        self.f.seal()
        with self.assertRaises(ValueError):self.f.admit()

    def test_every_phase_receipt_required_exactly(self):
        for phase in setup.PHASES:
            path = self.f.workspace/(phase+'.complete.json');raw = path.read_bytes()
            with self.subTest(phase=phase):
                path.unlink()
                with self.assertRaises(FileNotFoundError):self.f.admit()
                path.write_bytes(raw)
                value = assets.json_bytes(raw);value['schema'] = True;write(path,value)
                with self.assertRaises(ValueError):self.f.admit()
                path.write_bytes(raw)
        path = self.f.workspace/'seal.complete.json';value = assets.read_json(path)
        value['manifest_sha256'] = 'f'*64;write(path,value)
        with self.assertRaises(ValueError):self.f.admit()

    def test_both_native_phases_are_distinct_and_cannot_inherit_m16_completion(self):
        original = list(setup.PHASES)
        for phases in ([p for p in original if p == 'native16' or not p.startswith('native')],
                       ['native' if p == 'native16' else p for p in original],
                       ['native16' if p == 'native128' else p for p in original]):
            with self.subTest(phases=phases):
                self.f.receipt['completed_phases'] = phases
                self.f.summary['completed_phases'] = phases
                self.f.seal()
                with self.assertRaises(ValueError):self.f.admit()
        self.f.receipt['completed_phases'] = self.f.summary['completed_phases'] = original
        self.f.seal()
        small = self.f.workspace/'native16.complete.json'
        large = self.f.workspace/'native128.complete.json'
        large.unlink();os.link(small,large)
        with self.assertRaises(ValueError):self.f.admit()

    def test_exact_full_launch_map_no_m16_subset_or_same_size_substitution(self):
        for mutation in ('m16_subset','same_size','changed_digest'):
            expected = dict(self.f.sources)
            if mutation == 'm16_subset':
                expected = dict(list(expected.items())[:187])
            elif mutation == 'same_size':
                del expected['CONTROL_ONLY/source_000.py']
                expected['CONTROL_ONLY/substitute.py'] = 'a'*64
            else:
                expected['CONTROL_ONLY/source_000.py'] = 'f'*64
            with self.subTest(mutation=mutation), patch.object(self.launch_control,'contract_snapshot',
                    return_value=dict(sources=expected,generated=self.generated)):
                with self.assertRaises(ValueError):self.f.admit()

    def test_workspace_path_inode_and_directory_separation(self):
        for key,value in (('path',str(self.root)),('device',True),('inode',self.f.workspace.stat().st_ino+1)):
            original = deepcopy(self.f.receipt['workspace'])
            with self.subTest(key=key):
                self.f.receipt['workspace'][key] = value;self.f.seal()
                with self.assertRaises(ValueError):self.f.admit()
            self.f.receipt['workspace'] = original
        self.f.seal()
        nested = self.f.workspace/'summary.json';shutil.copyfile(self.f.summary_path,nested)
        with self.assertRaises(ValueError):a.verify_setup(self.f.workspace,nested,checkout_commit=CHECKOUT,enable_raw_kv=True)

    def test_symlinks_traversal_and_nonregular_metadata(self):
        path = self.f.workspace/'SETUP.json';original = path.read_bytes();other = self.root/'other.json'
        other.write_bytes(original);path.unlink();path.symlink_to(other)
        with self.assertRaises(ValueError):self.f.admit()
        path.unlink();os.mkfifo(path)
        with self.assertRaises(ValueError):self.f.admit()
        path.unlink();path.write_bytes(original)
        linked = self.root/'linked';linked.symlink_to(self.f.workspace,target_is_directory=True)
        with self.assertRaises(ValueError):a.verify_setup(linked,self.f.summary_path,checkout_commit=CHECKOUT,enable_raw_kv=True)
        self.f.manifest['library']['receipt']['path'] = '../other.json';self.f.seal()
        with self.assertRaises(ValueError):self.f.admit()

    def test_revalidation_rejects_relinked_change_and_identical_replacement(self):
        first = self.f.admit();self.f.receipt['elapsed_seconds'] = 13.0;self.f.seal()
        with patch.object(setup,'source_snapshot',return_value=deepcopy(self.f.sources)):
            with self.assertRaises(ValueError):a.revalidate(first)
        second = self.f.admit();path = self.f.workspace/'SETUP.json';raw = path.read_bytes()
        temporary = path.with_name('replacement');temporary.write_bytes(raw);temporary.replace(path)
        with patch.object(setup,'source_snapshot',return_value=deepcopy(self.f.sources)):
            with self.assertRaises(ValueError):a.revalidate(second)

    def test_compile_receipt_cannot_hardlink_phase_metadata(self):
        phase=self.f.workspace/'preflight.complete.json'
        library=self.f.workspace/self.f.manifest['library']['receipt']['path']
        library.unlink();os.link(phase,library)
        raw=phase.read_bytes()
        self.f.manifest['library']['receipt'].update(bytes=len(raw),sha256=assets.sha(raw))
        self.f.seal()
        with self.assertRaisesRegex(ValueError,'linked_receipt_inode_alias'):self.f.admit()

    def test_source_drift_during_admission(self):
        changed = deepcopy(self.f.sources);changed['CONTROL_ONLY/source_000.py'] = 'e'*64
        with patch.object(setup,'source_snapshot',side_effect=[deepcopy(self.f.sources),changed]):
            with self.assertRaises(ValueError):a.verify_setup(self.f.workspace,self.f.summary_path,
                checkout_commit=CHECKOUT,enable_raw_kv=True)

    def test_no_numerical_import_or_invocation(self):
        # Imported admission/setup/assets contain only standard-library imports;
        # the admission API must not call the separately gated numerical verifier.
        with patch.object(assets,'verify',side_effect=AssertionError('native verifier forbidden')):
            result = self.f.admit()
        self.assertFalse(a.safe_identity(result)['numerical_acceptance'])


    def test_six_recipe_metadata_files_are_bound_without_reading_payloads_or_elf(self):
        result=self.f.admit()
        self.assertEqual(len(result.linked_files),19)
        linked={item.path for item in result.linked_files}
        self.assertTrue(all(self.f.workspace/item['path'] in linked for item in self.f.recipe_records))
        self.assertFalse((self.f.workspace/self.f.manifest['recipe']['qk']['binary']['path']).exists())
        self.assertFalse((self.f.workspace/self.f.manifest['recipe']['generated_module']['path']).exists())
        self.assertEqual(result.compile_receipt,result.library_receipt)
        self.assertEqual(result.setup_receipt_sha256,result.receipt_sha256)

    def test_every_recipe_metadata_file_requires_exact_live_bytes(self):
        for item in self.f.recipe_records:
            path=self.f.workspace/item['path'];raw=path.read_bytes()
            with self.subTest(path=item['path']):
                path.unlink()
                with self.assertRaises(FileNotFoundError):self.f.admit()
                # Keep both byte count and valid JSON while changing its digest.
                path.write_bytes(raw.replace(b'CONTROL_ONLY',b'CONTROL_ONLX'))
                with self.assertRaisesRegex(ValueError,'linked_recipe_metadata_hash'):self.f.admit()
                path.write_bytes(raw)

    def test_every_recipe_metadata_inode_is_retained_for_revalidation(self):
        for item in self.f.recipe_records:
            first=self.f.admit();path=self.f.workspace/item['path'];raw=path.read_bytes()
            replacement=path.with_name(path.name+'.replacement');replacement.write_bytes(raw);replacement.replace(path)
            with self.subTest(path=item['path']),patch.object(setup,'source_snapshot',return_value=deepcopy(self.f.sources)):
                with self.assertRaisesRegex(ValueError,'linked_admission_drift'):a.revalidate(first)

    def test_recipe_metadata_cannot_alias_any_phase_receipt(self):
        phase=self.f.workspace/'preflight.complete.json'
        for item in self.f.recipe_records:
            path=self.f.workspace/item['path'];raw=path.read_bytes();saved=deepcopy(item)
            path.unlink();os.link(phase,path)
            other=phase.read_bytes();item.update(bytes=len(other),sha256=assets.sha(other));self.f.seal()
            try:
                with self.subTest(path=item['path']),self.assertRaisesRegex(ValueError,'linked_receipt_inode_alias'):
                    self.f.admit()
            finally:
                path.unlink();path.write_bytes(raw);item.update(saved);self.f.seal()

    def test_recipe_metadata_symlink_nonregular_and_size_bounds_fail_closed(self):
        for item in self.f.recipe_records:
            path=self.f.workspace/item['path'];raw=path.read_bytes()
            target=path.with_name(path.name+'.target');target.write_bytes(raw)
            path.unlink();path.symlink_to(target)
            try:
                with self.subTest(path=item['path']),self.assertRaises(ValueError):self.f.admit()
            finally:path.unlink();path.write_bytes(raw);target.unlink()
        for section,key,limit in (('qk','receipt',a.MAX_RECIPE_RECEIPT_BYTES),
                ('qkv','receipt',a.MAX_RECIPE_RECEIPT_BYTES),
                ('native16','report',a.MAX_RECIPE_REPORT_BYTES),('native128','report',a.MAX_RECIPE_REPORT_BYTES),
                ('native16','diagnostics',a.MAX_RECIPE_DIAGNOSTICS_BYTES),
                ('native128','diagnostics',a.MAX_RECIPE_DIAGNOSTICS_BYTES)):
            item=self.f.manifest['recipe'][section][key];saved=deepcopy(item);item['bytes']=limit+1;self.f.seal()
            try:
                with self.subTest(section=section,key=key),self.assertRaises(ValueError):self.f.admit()
            finally:item.update(saved);self.f.seal()

    def test_nine_phase_order_and_recipe_kernel_completion_cannot_be_skipped(self):
        phases=list(setup.PHASES)
        self.assertEqual(phases,list(pair_runtime.PHASE_LIMITS))
        for changed in ([p for p in phases if p!='recipe_kernel'],
                [p for p in phases if p!='recipe_kernel']+['recipe_kernel'],
                ['native16' if p=='recipe_kernel' else p for p in phases]):
            self.f.receipt['completed_phases']=changed;self.f.summary['completed_phases']=changed;self.f.seal()
            with self.subTest(phases=changed),self.assertRaises(ValueError):self.f.admit()

    def test_all_twelve_generated_identities_must_match_the_exact_source_closure(self):
        changes=[dict(list(self.generated.items())[:-1]),dict(self.generated,foreign='0'*64)]
        changed=dict(self.generated);changed[next(iter(changed))]='0'*64;changes.append(changed)
        for generated in changes:
            with self.subTest(generated=generated),patch.object(self.launch_control,'contract_snapshot',
                    return_value=dict(sources=self.f.sources,generated=generated)):
                with self.assertRaisesRegex(ValueError,'linked_launch_generated_closure'):self.f.admit()

    def test_schema_validation_does_not_promote_metadata_into_recipe_acceptance(self):
        imported=builtins.__import__
        def cold_import(name,*args,**kwargs):
            if name.split('.')[0] in ('numpy','torch','transformers','ctypes'):
                raise AssertionError('native/numerical import forbidden')
            return imported(name,*args,**kwargs)
        before={name for name in sys.modules if name.split('.')[0] in ('torch','numpy','transformers')}
        with patch('builtins.__import__',side_effect=cold_import), \
                patch.object(assets,'verify',side_effect=AssertionError('numerical verifier called')), \
                patch.object(pair_admission,'verify_recipe',side_effect=AssertionError('recipe verifier called')), \
                patch.object(pair_admission.phase.kernel,'verify',side_effect=AssertionError('ELF verifier called')), \
                patch.object(pair_admission.phase.qkv_kernel,'verify',side_effect=AssertionError('ELF verifier called')), \
                patch.object(pair_admission.phase,'project_result',side_effect=AssertionError('result validator called')):
            admitted=self.f.admit()
        self.assertFalse(a.safe_identity(admitted)['numerical_acceptance'])
        self.assertEqual(before,{name for name in sys.modules if name.split('.')[0] in ('torch','numpy','transformers')})


class PreservedContractTests(unittest.TestCase):
    def test_original_read_inode_credential_and_revalidation_logic_is_unchanged(self):
        from ..raw_kv_public_m128_run import admission as old
        original=ast.parse(Path(old.__file__).read_text());current=ast.parse(Path(a.__file__).read_text())
        names=('need','_integer','_file_identity','ReadIdentity','read_json','Admission','revalidate','safe_identity')
        for name in names:
            before=next(n for n in original.body if getattr(n,'name',None)==name)
            after=next(n for n in current.body if getattr(n,'name',None)==name)
            self.assertEqual(ast.dump(after),ast.dump(before),name)
        before=next(n for n in original.body if getattr(n,'name',None)=='validate_linkage')
        after=next(n for n in current.body if getattr(n,'name',None)=='validate_linkage')
        class RestoreCount(ast.NodeTransformer):
            def visit_Attribute(self,node):
                if isinstance(node.value,ast.Name) and node.value.id=='launch' and node.attr=='SOURCE_COUNT':
                    return ast.Name(id='SOURCE_COUNT',ctx=ast.Load())
                return self.generic_visit(node)
            def visit_Assign(self,node):
                if len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id=='launch':
                    return ast.Expr(value=node.value)
                return self.generic_visit(node)
        after=RestoreCount().visit(after)
        self.assertEqual(ast.dump(after),ast.dump(before))
        before=next(n for n in original.body if getattr(n,'name',None)=='verify_setup')
        after=next(n for n in current.body if getattr(n,'name',None)=='verify_setup')
        after.body=[node for node in after.body if not (
            isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id in ('recipe','recipe_records') for t in node.targets)
            or isinstance(node,ast.AugAssign) and isinstance(node.target,ast.Name) and node.target.id=='recipe_records'
            or isinstance(node,ast.For) and isinstance(node.iter,ast.Name) and node.iter.id=='recipe_records')]
        self.assertEqual(ast.dump(after),ast.dump(before))

    def test_actual_profile_constants_require_final_overlay_and_exact_phase_order(self):
        control=setup_control();asset_control=types.SimpleNamespace(PROFILE=pair_runtime.ASSET_PROFILE,same=original_assets.same)
        with patch.object(a,'setup',control),patch.object(a,'assets',asset_control), \
                patch.object(launch,'base_verifier_sources',return_value=control.BASE_VERIFIER_SHA256):
            self.assertIs(a.selected_profile(),launch)
            for name,bad in (('PROFILE','qwen2-public-fresh-m128-setup-v1'),
                    ('BASE_COMMIT','0'*40),('PROFILE_PATH',pair_runtime.PINS_PATH),
                    ('TOTAL_SECONDS',True),('CLEANUP_SECONDS',6),
                    ('PHASES',tuple(p for p in a.PHASES if p!='recipe_kernel'))):
                with self.subTest(name=name),patch.object(control,name,bad),self.assertRaises(ValueError):a.selected_profile()
            with patch.object(launch,'GENERATED_COUNT',10),self.assertRaises(ValueError):a.selected_profile()
            with patch.object(launch,'SOURCE_COUNT',True),self.assertRaises(ValueError):a.selected_profile()
        with self.assertRaises(ValueError):a.selected_profile()


class JsonAdmissionTests(unittest.TestCase):
    def test_same_byte_bounded_canonical_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'record.json'
            for raw in (b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":Infinity}',b'{"x":1e999}',b'x'*65):
                path.write_bytes(raw)
                with self.subTest(raw=raw),self.assertRaises(ValueError):a.read_json(path,limit=64)
            raw=b'{"x":1}\n';path.write_bytes(raw)
            value,identity=a.read_json(path,limit=64)
            self.assertEqual(value,{'x':1});self.assertEqual(identity.sha256,hashlib.sha256(raw).hexdigest())


if __name__ == '__main__':unittest.main()
