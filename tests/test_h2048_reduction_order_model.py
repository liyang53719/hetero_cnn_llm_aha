#!/usr/bin/env python3
"""Cold packaging guards only: never evaluates the reduction model or fixtures."""
import ast
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

PACKAGE=Path(__file__).resolve().parents[1]
SCRIPT=PACKAGE/'scripts/check_h2048_reduction_order_model.py'
spec=importlib.util.spec_from_file_location('h2048_reduction_order_model',SCRIPT)
model=importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)
REPOSITORY=Path(os.environ.get('H2048_REDUCTION_MODEL_ROOT') or subprocess.check_output(
    ['git','-C',str(PACKAGE),'rev-parse','--show-toplevel'],text=True).strip()).resolve()


class ColdPackagingTests(unittest.TestCase):
    def setUp(self):
        self.old_root=model.ROOT
        self.old_fixture_root=model.FIXTURE_ROOT
        self.temp=tempfile.TemporaryDirectory(prefix='h2048-model-cold-')
        self.base=Path(self.temp.name).resolve()
        model.ROOT=REPOSITORY
        model.FIXTURE_ROOT=self.base
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(setattr,model,'ROOT',self.old_root)
        self.addCleanup(setattr,model,'FIXTURE_ROOT',self.old_fixture_root)

    def test_core_ast_inventory_is_preserved(self):
        actual=model.core_ast_inventory(SCRIPT.read_bytes())
        self.assertEqual(set(actual),{'load_arithmetic','rational_flags','ArithmeticFailure','Graph',
            'scalar_order','grouped_order','compare_graphs','update_hashes','directed_checks','run_fixture'})

    def test_changed_numeric_ast_rejected_without_execution(self):
        text=SCRIPT.read_text().replace('range(16):','range(15):',1)
        with self.assertRaisesRegex(AssertionError,'preserved arithmetic AST mismatch'):
            model.core_ast_inventory(text)

    def test_historical_source_uses_exact_git_object(self):
        path=next(iter(model.PINS))
        raw=subprocess.check_output(['git','-C',str(REPOSITORY),'show',model.HEAD+':'+path])
        with patch.object(model,'git_bytes',return_value=raw) as git:
            self.assertEqual(model.historical_source(path),raw)
        git.assert_called_once_with('show',model.HEAD+':'+path)

    def test_source_guard_rejects_wrong_bytes(self):
        with patch.object(model,'git_bytes',return_value=b'changed source'):
            with self.assertRaisesRegex(AssertionError,'historical source SHA mismatch'):
                model.historical_source(next(iter(model.PINS)))

    def test_source_guard_rejects_unlisted_source(self):
        with patch.object(model,'git_bytes') as git:
            with self.assertRaisesRegex(AssertionError,'unlisted historical source'):
                model.historical_source('arbitrary_current.py')
        git.assert_not_called()

    def test_validate_sources_never_resolves_current_head(self):
        calls=[]
        original=model.git_bytes
        def spy(*args):
            calls.append(args)
            return original(*args)
        with patch.object(model,'git_bytes',side_effect=spy):
            records=model.validate_sources()
        self.assertEqual(len(records),12)
        self.assertEqual(calls[0],('rev-parse',model.HEAD+'^{commit}'))
        self.assertTrue(all(args[0]=='show' and args[1].startswith(model.HEAD+':') for args in calls[1:]))

    def test_extract_uses_historical_bytes_without_running_numeric_function(self):
        text=b'def witness():\n    return 123\n'
        with patch.object(model,'historical_source',return_value=text) as source:
            namespace=model.extract('witness.py',{'witness'},{})
        source.assert_called_once_with('witness.py')
        self.assertTrue(callable(namespace['witness']))
        self.assertEqual(namespace['witness'].__code__.co_filename,model.HEAD+':witness.py')

    def test_legacy_paths_map_to_explicit_fixture_root(self):
        p=self.base/'work/example/manifest.json'
        p.parent.mkdir(parents=True);p.write_text('{}')
        old=model.LEGACY_FIXTURE_PREFIX/'work/example/manifest.json'
        self.assertEqual(model.historical_fixture_path(old),p)
        self.assertEqual(model.within('work/example/manifest.json'),p)
        self.assertEqual(model.within(p),p)

    def test_nested_relocation_does_not_remap_local_path_twice(self):
        root=self.base/'relocated';root.mkdir()
        p=root/'work/manifest.json';p.parent.mkdir();p.write_bytes(b'{}')
        model.FIXTURE_ROOT=root
        with patch.object(model,'LEGACY_FIXTURE_PREFIX',self.base):
            local=model.historical_fixture_path(self.base/'work/manifest.json')
            self.assertEqual(local,p)
            self.assertEqual(model.checked(local,model.sha(b'{}'),2)['path'],str(p))

    def test_historical_foreign_prefix_rejected(self):
        with self.assertRaisesRegex(AssertionError,'outside pinned prefix'):
            model.historical_fixture_path('/foreign/work/manifest.json')

    def test_fixture_access_requires_explicit_root(self):
        model.FIXTURE_ROOT=None
        with self.assertRaisesRegex(AssertionError,'--fixture-root is required'):
            model.within('work/manifest.json')

    def test_fixture_traversal_and_foreign_absolute_paths_rejected(self):
        for name in ('../escape','work/../escape','/unapproved/manifest.json'):
            with self.subTest(name=name):
                with self.assertRaises(AssertionError):model.within(name)

    def test_symlink_escape_rejected(self):
        child=self.base/'fixtures';child.mkdir()
        outside=self.base/'outside';outside.write_text('metadata')
        (child/'escape').symlink_to(outside)
        model.FIXTURE_ROOT=child
        with self.assertRaisesRegex(AssertionError,'symlink escapes'):
            model.within('escape')

    def test_byte_count_and_digest_guards(self):
        p=self.base/'metadata.json';p.write_bytes(b'{}')
        pin=hashlib.sha256(b'{}').hexdigest()
        self.assertEqual(model.checked(p,pin,2)['bytes'],2)
        with self.assertRaisesRegex(AssertionError,'byte count mismatch'):model.checked(p,pin,3)
        with self.assertRaisesRegex(AssertionError,'SHA mismatch'):model.checked(p,'0'*64,2)

    def test_inventory_is_metadata_only(self):
        with patch.object(Path,'open',side_effect=AssertionError('fixture read attempted')):
            inventory=model.frozen_inventory()
        self.assertFalse(inventory['fixture_payloads_opened'])
        self.assertEqual(inventory['unique_file_records'],44)
        self.assertEqual([f['tokens'] for f in inventory['fixtures']],[1,16,128])

    def test_inventory_pin_corruption_rejected(self):
        changed=[dict(r) for r in model.HISTORICAL_FIXTURE_INVENTORY]
        next(r for r in changed if r['path'].endswith('/manifest.json'))['sha256']='0'*64
        with patch.object(model,'HISTORICAL_FIXTURE_INVENTORY',changed):
            with self.assertRaisesRegex(AssertionError,'manifest inventory mismatch'):model.frozen_inventory()

    def test_runner_guard_rejects_replaced_old_receipt(self):
        p=self.base/model.RUNNER;p.parent.mkdir(parents=True);p.write_text('{}')
        with self.assertRaisesRegex(AssertionError,'SHA mismatch'):model.verified_runner()

    def invoke(self,*extra):
        out=self.base/'output'
        with contextlib.redirect_stdout(io.StringIO()):
            code=model.main(['--root',str(REPOSITORY),'--out',str(out),*extra])
        return code,json.loads((out/'summary.json').read_text()),out

    def test_default_cold_mode_never_opens_fixtures_or_loads_arithmetic(self):
        with patch.object(model,'fixture_from_runner',side_effect=AssertionError('fixture read')) as fixtures, \
             patch.object(model,'load_arithmetic',side_effect=AssertionError('arithmetic load')) as arithmetic:
            code,summary,out=self.invoke('--fixture-root',str(self.base/'nonexistent'))
        self.assertEqual(code,0)
        fixtures.assert_not_called();arithmetic.assert_not_called()
        self.assertEqual(summary['status'],'PASS_COLD_STRUCTURE_ONLY')
        self.assertFalse(summary['original_success_inherited'])
        self.assertTrue(summary['behavior_model_rerun_required'])
        self.assertFalse(summary['current_owner_proven'])
        self.assertEqual(summary['groups']['external_actual_fixtures']['status'],'NOT_EXECUTED')
        self.assertEqual(summary['groups']['directed_arithmetic']['status'],'NOT_EXECUTED')
        self.assertEqual(sorted(p.name for p in out.iterdir()),['failures.json','receipt.json','summary.json'])

    def test_actual_missing_external_root_does_not_execute(self):
        with patch.object(model,'load_arithmetic') as arithmetic:
            code,summary,_=self.invoke('--run-actual')
        self.assertEqual(code,1);arithmetic.assert_not_called()
        self.assertEqual(summary['status'],'FAILED')
        self.assertEqual(summary['groups']['external_actual_fixtures']['status'],'NOT_EXECUTED')
        self.assertIn('--fixture-root',summary['failures'][0]['message'])

    def test_actual_unavailable_pinned_bytes_does_not_execute(self):
        with patch.object(model,'load_arithmetic') as arithmetic:
            code,summary,_=self.invoke('--run-actual','--fixture-root',str(self.base))
        self.assertEqual(code,1);arithmetic.assert_not_called()
        self.assertEqual(summary['groups']['external_actual_fixtures']['status'],'NOT_EXECUTED')
        self.assertEqual(summary['groups']['directed_arithmetic']['status'],'NOT_EXECUTED')

    def test_require_is_effective_under_optimization(self):
        with self.assertRaisesRegex(AssertionError,'still enforced'):model.require(False,'still enforced')
        self.assertFalse(any(isinstance(n,ast.Assert) for n in ast.walk(ast.parse(SCRIPT.read_text()))))


if __name__=='__main__':unittest.main()
