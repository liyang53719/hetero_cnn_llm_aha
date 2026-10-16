"""Cold linkage tests. Synthetic metadata is never asset/numerical readiness.

No producer, Torch, ELF, full-size payload, numerical entry or CI is executed.
A separate real-source fixture exercises the final 221-source launch checker.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch

from . import admission as a
import builtins
import importlib.util
import subprocess
import types
from contextlib import ExitStack
from ..raw_kv_public_fresh import assets as original_assets, setup as original_setup
from ..raw_kv_public_m128.test_assets128 import manifest_fixture

assets = original_assets
setup = None


def load_m128_assets(out):
    name = 'candidates/qwen2_resident_matrix/raw_kv_public_fresh/assets.py'
    path = out/name; path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(Path(original_assets.__file__).read_bytes())
    patch_path = Path(__file__).resolve().parent.parent/'raw_kv_public_m128/assets128.patch'
    subprocess.run(['patch','--batch','--fuzz=0','-p1'],cwd=out,input=patch_path.read_bytes(),
                   check=True,capture_output=True,timeout=10)
    spec = importlib.util.spec_from_file_location(
        'candidates.qwen2_resident_matrix.raw_kv_public_fresh._m128_admission_control',path)
    module = importlib.util.module_from_spec(spec)
    imported = builtins.__import__
    def cold_import(name,*args,**kwargs):
        if name.split('.')[0] in ('numpy','torch','transformers','ctypes'):
            raise AssertionError('numerical import forbidden')
        return imported(name,*args,**kwargs)
    with patch('builtins.__import__',side_effect=cold_import):spec.loader.exec_module(module)
    return module


def setup_control():
    # Names/geometry are authentic; no source authority or producer PASS is claimed.
    result = types.SimpleNamespace(**vars(original_setup))
    result.PROFILE = 'qwen2-public-fresh-m128-setup-v1'
    result.BASE_COMMIT = '72ca5e52f97490fa80fd94eac056f338e25ba7fc'
    result.PROFILE_PATH = 'candidates/qwen2_resident_matrix/raw_kv_public_m128_run/launch-contract.json'
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
        self.sources = {'CONTROL_ONLY/source_%03d.py'%i:'a'*64 for i in range(220)}
        self.sources[setup.PROFILE_PATH] = 'c'*64
        self.asset_sources = self.sources
        self.manifest = manifest_fixture(assets)
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
        cls.source_temp = tempfile.TemporaryDirectory(prefix='m128-admission-source-')
        cls.addClassCleanup(cls.source_temp.cleanup)
        assets = load_m128_assets(Path(cls.source_temp.name))
        setup = setup_control()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.context = ExitStack();self.addCleanup(self.context.close)
        self.context.enter_context(patch.object(a,'assets',assets))
        self.context.enter_context(patch.object(a,'setup',setup))
        self.f = ControlFixture(self.root)
        self.launch_control = types.SimpleNamespace(contract_snapshot=Mock(side_effect=lambda **kw:dict(sources=deepcopy(self.f.sources))))
        self.context.enter_context(patch.object(a,'selected_profile',return_value=self.launch_control))
        self.context.enter_context(patch.object(setup,'asset_sources',side_effect=lambda sources:dict(sources)))

    def test_complete_control_linkage_and_safe_projection(self):
        result = self.f.admit()
        self.assertEqual(result.manifest,self.f.workspace/'ASSETS.json')
        self.assertEqual(result.source_sha256,self.f.sources)
        copied = result.source_sha256;copied.clear();self.assertEqual(len(result.source_sha256),221)
        safe = a.safe_identity(result)
        self.assertFalse(safe['actual_chain_executed']);self.assertFalse(safe['numerical_acceptance'])
        self.assertEqual(safe['completed_phase_count'],8)
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
                    return_value=dict(sources=expected)):
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


class RealSourceClosureTests(unittest.TestCase):
    def test_final_launch_closure_and_inert_m16_rejection(self):
        from . import launch,prepare
        from ..raw_kv_public_m128 import profile,prerequisite
        from ..raw_kv_public_m128_runtime import runtime
        before=runtime.contract_snapshot()
        with self.assertRaises(ValueError):a.selected_profile()
        with tempfile.TemporaryDirectory(prefix='m128-admission-closure-') as directory:
            root=Path(directory)/'tree';out=Path(directory)/'generated'
            result=prepare.prepare(out,enable_raw_kv=True)
            for name in result['inputs']:
                target=root/name;target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes((launch.ROOT/name).read_bytes())
            for name in result['generated']:(root/name).write_bytes((out/name).read_bytes())
            expected=dict(result['inputs']);expected.update(result['generated'])
            self.assertEqual(len(expected),221)
            package=__import__('candidates.qwen2_resident_matrix.raw_kv_public_fresh',fromlist=['assets'])
            def load(relative,name):
                spec=importlib.util.spec_from_file_location(name,root/relative)
                module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
            imported=builtins.__import__
            def cold_import(name,*args,**kwargs):
                if name.split('.')[0] in ('numpy','torch','transformers','ctypes'):
                    raise AssertionError('numerical import forbidden')
                return imported(name,*args,**kwargs)
            with ExitStack() as stack:
                for module in (launch,runtime,profile,prerequisite):
                    stack.enter_context(patch.object(module,'ROOT',root))
                stack.enter_context(patch('builtins.__import__',side_effect=cold_import))
                generated_assets=load(prerequisite.ASSETS,
                    'candidates.qwen2_resident_matrix.raw_kv_public_fresh._admission_assets_exact')
                stack.enter_context(patch.object(package,'assets',generated_assets))
                generated_setup=load(prerequisite.SETUP,
                    'candidates.qwen2_resident_matrix.raw_kv_public_fresh._admission_setup_exact')
                stack.enter_context(patch.object(a,'assets',generated_assets))
                stack.enter_context(patch.object(a,'setup',generated_setup))
                self.assertIs(a.selected_profile(),launch)
                self.assertEqual(a.source_snapshot(True),expected)
                target=root/'candidates/qwen2_resident_matrix/official_bf16/owners.py'
                target.write_bytes(target.read_bytes()+b'\n# drift\n')
                with self.assertRaises(ValueError):a.source_snapshot(True)
        self.assertEqual(runtime.contract_snapshot(),before)


if __name__ == '__main__':unittest.main()
