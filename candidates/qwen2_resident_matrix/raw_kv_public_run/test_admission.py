"""Cold linkage tests. Synthetic metadata is never asset/numerical readiness.

No producer, Torch, ELF, full-size payload, numerical entry or CI is executed.
A separate real-source fixture exercises the published 187/183 source checker.
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
from ..raw_kv_public_fresh import assets, setup, prepare
from ..raw_kv_public_fresh.test_assets import metadata_fixture

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
        self.asset_sources = {'CONTROL_ONLY/source_%03d.py'%i:'a'*64 for i in range(183)}
        self.sources = dict(self.asset_sources,**{name:'b'*64 for name in setup.SETUP_SOURCES},
                            **{setup.PROFILE_PATH:'c'*64})
        self.manifest = metadata_fixture()
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
            enable_raw_kv=True,rows=16,past_tokens=0,
            workspace=dict(path=str(self.workspace),device=info.st_dev,inode=info.st_ino),
            checkout_commit=CHECKOUT,completed_phases=list(setup.PHASES),source_recheck='UNCHANGED',
            deadline_monotonic_ns=10**12,elapsed_seconds=12.0,total_budget_seconds=600,
            actual_chain_executed=False,numerical_acceptance=False)
        self.summary = dict(schema=1,status=setup.SETUP_STATUS,phase='seal',elapsed_seconds=12.0,
            completed_phases=list(setup.PHASES),total_budget_seconds=600,cleanup_grace_seconds=5,
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
        kwargs = dict(checkout_commit=CHECKOUT,enable_raw_kv=True,rows=16);kwargs.update(changes)
        with patch.object(setup,'source_snapshot',return_value=deepcopy(self.sources)):
            return a.verify_setup(self.workspace,self.summary_path,**kwargs)


class LinkedAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name);self.f = ControlFixture(self.root)

    def test_complete_control_linkage_and_safe_projection(self):
        result = self.f.admit()
        self.assertEqual(result.manifest,self.f.workspace/'ASSETS.json')
        self.assertEqual(result.source_sha256,self.f.sources)
        copied = result.source_sha256;copied.clear();self.assertEqual(len(result.source_sha256),187)
        safe = a.safe_identity(result)
        self.assertFalse(safe['actual_chain_executed']);self.assertFalse(safe['numerical_acceptance'])
        self.assertEqual(safe['completed_phase_count'],7)
        self.assertNotIn(str(self.root),json.dumps(safe))
        with patch.object(setup,'source_snapshot',return_value=deepcopy(self.f.sources)):
            self.assertEqual(a.revalidate(result),result)

    def test_request_domain_before_any_file_access(self):
        for changed in ({'rows':True},{'rows':128},{'enable_raw_kv':1},{'checkout_commit':'bad'},
                        {'checkout_commit':'A'*40}):
            with self.subTest(changed=changed), patch.object(assets,'safe_path',side_effect=AssertionError('file access')):
                with self.assertRaises(ValueError):self.f.admit(**changed)

    def test_standalone_ready_cannot_bypass_private_commit(self):
        (self.f.workspace/'SETUP.json').unlink()
        with patch.object(setup,'source_snapshot',side_effect=AssertionError('source work')):
            with self.assertRaises(FileNotFoundError):self.f.admit()

    def test_provisional_failed_or_incomplete_summary_rejected(self):
        for status in ('READY_FOR_ACTUAL_M16','SETUP_VERIFYING','SETUP_FAILED','SETUP_TIMEOUT','SETUP_INTERRUPTED'):
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
        bad = (('rows',True),('rows',128),('past_tokens',False),('past_tokens',1),
            ('enable_raw_kv',1),('enable_raw_kv',False),('schema',True),('profile','wrong'),
            ('base_profile','wrong'),('base_commit','2'*40),('checkout_commit','2'*40),
            ('source_recheck','FAILED'),('total_budget_seconds',True),('total_budget_seconds',601),
            ('deadline_monotonic_ns',True),('deadline_monotonic_ns',0),('elapsed_seconds',True),
            ('elapsed_seconds',601),('actual_chain_executed',0),('numerical_acceptance',0),
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
        self.f.seal();self.f.manifest['source_sha256']['CONTROL_ONLY/source_000.py'] = 'e'*64
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
    def test_published_setup_source_closure_in_real_composed_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'tree';generated=Path(directory)/'overlay'
            report=prepare.prepare(generated,enable_raw_kv=True)
            names=set(report['inputs']) | set(setup.SETUP_SOURCES) | {setup.PROFILE_PATH}
            for name in names:
                destination=root/name;destination.parent.mkdir(parents=True,exist_ok=True)
                destination.write_bytes((assets.ROOT/name).read_bytes())
            for name in report['generated']:
                (root/name).write_bytes((generated/name).read_bytes())
            here=root/'candidates/qwen2_resident_matrix/raw_kv_public_fresh'
            with patch.multiple(assets,ROOT=root,HERE=here),patch.multiple(setup,ROOT=root,HERE=here):
                sources=setup.source_snapshot(True)
                self.assertEqual(len(sources),187);self.assertEqual(len(setup.asset_sources(sources)),183)
                path=root/'candidates/qwen2_resident_matrix/raw_kv_public/model.py'
                path.write_bytes(path.read_bytes()+b'\n# source drift\n')
                with self.assertRaises(ValueError):setup.source_snapshot(True)


if __name__ == '__main__':unittest.main()
