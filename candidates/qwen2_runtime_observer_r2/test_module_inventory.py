"""Bounded pure-software identity fixtures. No NumPy, DUT, oracle, or CDLL."""
import ast
import copy
import importlib.machinery
import importlib.util
import json
import hashlib
import os
from pathlib import Path
import resource
import signal
import sys
import tempfile
import types
import typing
import unittest
from unittest import mock

os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 ** 2,) * 2)
resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
signal.alarm(25)
HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('_pure_module_inventory_test', HERE / 'module_inventory.py')
inv = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inv)
REPLAY_SPEC = importlib.util.spec_from_file_location('_pure_inventory_replay_test', HERE / 'replay_inventory.py')
replay = importlib.util.module_from_spec(REPLAY_SPEC)
REPLAY_SPEC.loader.exec_module(replay)


def pin(path):
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    return importlib.util.module_from_spec(spec)


def create_namespace(path):
    result = types.ModuleType('_fixture_namespace')
    result.__path__ = [str(path)]
    return result


class ModuleInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.a = self.root / 'a.py'
        self.b = self.root / 'b.py'
        self.a.write_text('VALUE = 1\n')
        self.b.write_text('VALUE = 2\n')
        self.files = {str(p): pin(p) for p in (self.a, self.b)}

    def tearDown(self):
        self.temp.cleanup()

    def codes(self, report):
        return [failure['code'] for failure in report['failures']]

    def test_normal_file_and_aliases_preserved(self):
        a = module('a', self.a)
        report = inv.collect_modules({'a': a, 'alias': a}, self.files)
        inv.validate_modules(report)
        self.assertEqual(report['entry_count'], 2)
        self.assertEqual(report['unique_object_count'], 1)
        self.assertEqual([r['name'] for r in report['modules']], ['a', 'alias'])
        self.assertEqual(report['modules'][0]['aliases'], ['a', 'alias'])
        self.assertEqual(report['modules'][1]['file_identity']['sha256'], self.files[str(self.a)]['sha256'])
        json.dumps(report)

    def test_many_missing_modules_rejected_together(self):
        report = inv.collect_modules({'a': module('a', self.a), 'b': module('b', self.b),
                                      'none': None, 'empty': types.ModuleType('empty')}, {})
        self.assertEqual(report['entry_count'], 4)
        self.assertEqual({f['name'] for f in report['failures']}, {'a', 'b', 'none', 'empty'})
        with self.assertRaises(inv.ModuleInventoryError) as caught:
            inv.validate_modules(report)
        self.assertIs(caught.exception.report, report)
        self.assertGreaterEqual(len(report['failures']), 6)

    def test_unknown_file_never_opened(self):
        original = os.open
        def guarded(path, *args, **kwargs):
            if str(path) == str(self.a):
                raise AssertionError('unknown file read')
            return original(path, *args, **kwargs)
        with mock.patch.object(os, 'open', side_effect=guarded):
            report = inv.collect_modules({'a': module('a', self.a)}, {})
        row = report['modules'][0]['file_identity']
        self.assertEqual(row['bytes'], self.a.stat().st_size)
        self.assertEqual(row['realpath'], str(self.a))
        self.assertIsNone(row['sha256'])
        self.assertEqual(row['hash_status'], 'unbound_path_not_read')
        self.assertIn('file_identity.unknown_path', self.codes(report))

    def test_same_size_hash_drift_rejected(self):
        self.a.write_text('VALUE = 9\n')
        report = inv.collect_modules({'a': module('a', self.a)}, self.files)
        self.assertIn('file_identity.sha256_mismatch', self.codes(report))
        self.assertNotIn('file_identity.bytes_mismatch', self.codes(report))

    def test_size_and_hash_drift_both_reported(self):
        self.a.write_text('VALUE = 123456\n')
        report = inv.collect_modules({'a': module('a', self.a)}, self.files)
        self.assertIn('file_identity.sha256_mismatch', self.codes(report))
        self.assertIn('file_identity.bytes_mismatch', self.codes(report))

    def test_file_spec_conflict_even_when_both_pinned(self):
        a = module('a', self.a)
        a.__spec__.origin = str(self.b)
        report = inv.collect_modules({'a': a}, self.files)
        self.assertIn('file_spec_origin_conflict', self.codes(report))
        self.assertEqual(report['modules'][0]['origin_identity']['sha256'], self.files[str(self.b)]['sha256'])

    def test_canonical_file_symlink_alias_rejected_even_after_cache_hit(self):
        link = self.root / 'alias.py'
        link.symlink_to(self.a)
        report = inv.collect_modules({'a': module('a', self.a), 'alias': module('alias', link)}, self.files)
        self.assertIn('file_identity.noncanonical_path', self.codes(report))
        self.assertEqual({f['name'] for f in report['failures']}, {'alias'})
        self.assertEqual(report['modules'][1]['file_identity']['sha256'], self.files[str(self.a)]['sha256'])

    def test_file_module_actual_name_spec_name_conflict_rejected(self):
        a = module('a', self.a)
        a.__name__ = 'masquerading'
        report = inv.collect_modules({'a': a, 'masquerading': a}, self.files)
        self.assertIn('file_module_spec_name_conflict', self.codes(report))

    def test_loader_spec_conflict(self):
        a = module('a', self.a)
        a.__loader__ = importlib.machinery.SourceFileLoader('a', str(self.b))
        report = inv.collect_modules({'a': a}, self.files)
        self.assertIn('loader_spec_conflict', self.codes(report))
        self.assertIn('loader_file_conflict', self.codes(report))

    def test_main_script_without_spec_is_not_unknown(self):
        a = module('__main__', self.a)
        a.__spec__ = None
        report = inv.collect_modules({'__main__': a}, self.files)
        inv.validate_modules(report)
        self.assertEqual(report['modules'][0]['kind'], 'normal_main_script')
        a.__name__ = 'wrong'
        self.assertIn('missing_file_module_spec', self.codes(inv.collect_modules({'__main__': a}, self.files)))

    def test_no_file_and_fake_builtin_not_whitelisted(self):
        fake = types.ModuleType('not_a_real_builtin')
        fake.__loader__ = importlib.machinery.BuiltinImporter
        fake.__spec__ = importlib.machinery.ModuleSpec(fake.__name__, fake.__loader__, origin='built-in')
        report = inv.collect_modules({'mystery': types.ModuleType('mystery'), fake.__name__: fake}, self.files)
        self.assertIn('unregistered_no_file_module', self.codes(report))
        self.assertIn('unverified_builtin_or_frozen', self.codes(report))

    def test_spoofed_real_builtin_and_frozen_objects_rejected(self):
        files = {str(Path(sys.executable).resolve()): pin(Path(sys.executable).resolve())}
        modules = {'sys': sys, '_frozen_importlib': sys.modules['_frozen_importlib'],
                   'importlib._bootstrap': sys.modules['_frozen_importlib']}
        for name, original in (('spoof_builtin', sys), ('spoof_frozen', sys.modules['_frozen_importlib'])):
            fake = types.ModuleType(name)
            fake.__spec__ = original.__spec__
            fake.__loader__ = original.__loader__
            modules[name] = fake
        frozen_file = Path(sys.modules['_frozen_importlib'].__file__).resolve()
        files[str(frozen_file)] = pin(frozen_file)
        report = inv.collect_modules(modules, files)
        failed_names = {f['name'] for f in report['failures']}
        self.assertEqual(failed_names, {'spoof_builtin', 'spoof_frozen'})
        self.assertEqual(self.codes(report).count('builtin_or_frozen_object_alias_mismatch'), 2)

    def test_namespace_function_injection_and_wrong_loader_path_rejected(self):
        loader = importlib.machinery.NamespaceLoader('pkg', [str(self.root / 'wrong')], None)
        spec = importlib.machinery.ModuleSpec('pkg', loader, is_package=True)
        spec.submodule_search_locations = [str(self.root)]
        package = importlib.util.module_from_spec(spec)
        package.injected = lambda: 'unexpected executable attribute'
        report = inv.collect_modules({'pkg': package}, self.files, namespaces={'pkg': {'paths': [str(self.root)]}})
        self.assertIn('namespace_extra_attribute', self.codes(report))
        self.assertIn('namespace_loader_path_conflict', self.codes(report))

    def test_module_getattr_and_namespace_iter_hooks_never_called(self):
        mystery = types.ModuleType('mystery')
        def unexpected(name):
            raise AssertionError('module __getattr__ was executed')
        mystery.__getattr__ = unexpected
        report = inv.collect_modules({'mystery': mystery}, {})
        self.assertIn('unregistered_no_file_module', self.codes(report))
        self.assertNotIn('module_collection_error', self.codes(report))
        class Surprise:
            def __iter__(self):
                raise AssertionError('path iteration was executed')
        package = create_namespace(self.root)
        package.__path__ = Surprise()
        files = dict(self.files, **{str(Path(__file__).resolve()): pin(Path(__file__).resolve())})
        report = inv.collect_modules({package.__name__: package}, files, synthetic=self.synthetic(package))
        self.assertIn('module_path_invalid', self.codes(report))
        self.assertNotIn('module_collection_error', self.codes(report))

    def test_real_builtin_and_frozen_alias_keep_pin_identity(self):
        files = dict(self.files)
        runtime = Path(sys.executable).resolve()
        files[str(runtime)] = pin(runtime)
        frozen = sys.modules['_frozen_importlib']
        files[str(Path(frozen.__file__).resolve())] = pin(Path(frozen.__file__).resolve())
        report = inv.collect_modules({'sys': sys, '_frozen_importlib': frozen,
                                      'importlib._bootstrap': frozen}, files)
        inv.validate_modules(report)
        self.assertEqual(report['modules'][1]['kind'], 'frozen')
        self.assertIsNotNone(report['modules'][1]['file_identity'])
        del files[str(runtime)]
        failed = inv.collect_modules({'sys': sys}, files)
        self.assertIn('runtime_interpreter_not_pinned', self.codes(failed))

    def test_namespace_requires_explicit_exact_paths_and_pinned_descendant(self):
        loader = importlib.machinery.NamespaceLoader('pkg', [str(self.root)], None)
        spec = importlib.machinery.ModuleSpec('pkg', loader, is_package=True)
        spec.submodule_search_locations = [str(self.root)]
        package = importlib.util.module_from_spec(spec)
        report = inv.collect_modules({'pkg': package}, self.files)
        self.assertIn('unregistered_namespace_package', self.codes(report))
        register = {'pkg': {'paths': [str(self.root)]}}
        report = inv.collect_modules({'pkg': package}, self.files, namespaces=register)
        inv.validate_modules(report)
        names = [x['name'] for x in report['modules'][0]['namespace_directories'][0]['entries']]
        self.assertEqual(names, ['a.py', 'b.py'])
        report = inv.collect_modules({'pkg': package}, {}, namespaces=register)
        self.assertIn('namespace_without_pinned_descendant', self.codes(report))
        package.__path__ = [str(self.root / 'different')]
        report = inv.collect_modules({'pkg': package}, self.files, namespaces=register)
        self.assertIn('namespace_spec_path_conflict', self.codes(report))
        self.assertIn('namespace_path_mismatch', self.codes(report))

    def synthetic(self, package):
        return {package.__name__: {'kind': 'namespace_package', 'module': package,
                    'paths': [str(self.root)], 'allowed_children': ['a'],
                    'creator_source': str(Path(__file__).resolve()), 'creator_function': create_namespace}}

    def test_explicit_synthetic_namespace_not_normal_module(self):
        package = create_namespace(self.root)
        child = module(package.__name__ + '.a', self.a)
        package.a = child
        modules = {package.__name__: package, child.__name__: child}
        files = dict(self.files, **{str(Path(__file__).resolve()): pin(Path(__file__).resolve())})
        report = inv.collect_modules(modules, files, synthetic=self.synthetic(package))
        inv.validate_modules(report)
        self.assertEqual(report['modules'][0]['kind'], 'synthetic_namespace_package')
        self.assertTrue(report['modules'][0]['creator']['match'])

    def test_synthetic_namespace_extra_attribute_and_unregistered_child_rejected(self):
        package = create_namespace(self.root)
        package.a = module('_fixture_namespace.a', self.a)
        package.surprise = 'not allowed'
        files = dict(self.files, **{str(Path(__file__).resolve()): pin(Path(__file__).resolve())})
        report = inv.collect_modules({package.__name__: package}, files, synthetic=self.synthetic(package))
        self.assertIn('synthetic_namespace_extra_attributes', self.codes(report))
        self.assertIn('synthetic_child_unregistered', self.codes(report))

    def test_source_changed_after_identity_collection_rejected(self):
        package = create_namespace(self.root)
        files = dict(self.files, **{str(Path(__file__).resolve()): pin(Path(__file__).resolve())})
        original = Path.read_bytes
        def changed_source(path):
            if path == Path(__file__).resolve():
                return b'def create_namespace(path): return None\n'
            return original(path)
        with mock.patch.object(Path, 'read_bytes', changed_source):
            report = inv.collect_modules({package.__name__: package}, files, synthetic=self.synthetic(package))
        self.assertIn('creator_code_error', self.codes(report))
        self.assertTrue(any('source drift' in f['detail'] for f in report['failures']))

    def test_synthetic_creator_code_replacement_rejected(self):
        package = create_namespace(self.root)
        registration = self.synthetic(package)
        changed = types.FunctionType((lambda path: None).__code__, globals(), 'create_namespace')
        registration[package.__name__]['creator_function'] = changed
        files = dict(self.files, **{str(Path(__file__).resolve()): pin(Path(__file__).resolve())})
        report = inv.collect_modules({package.__name__: package}, files, synthetic=registration)
        self.assertIn('creator_code_mismatch', self.codes(report))

    def test_explicit_ast_source_code_identity_not_normal(self):
        self.a.write_text('def f(value):\n    return value + 1\n')
        files = {str(self.a): pin(self.a)}
        package = types.ModuleType('ast_fixture')
        tree = ast.parse(self.a.read_text(), filename=str(self.a))
        exec(compile(ast.Module(body=tree.body, type_ignores=[]), str(self.a), 'exec', dont_inherit=True,
                     optimize=sys.flags.optimize), package.__dict__)
        registration = {'ast_fixture': {'kind': 'ast_module', 'module': package, 'source': str(self.a), 'definitions': ['f']}}
        report = inv.collect_modules({'ast_fixture': package}, files, synthetic=registration)
        inv.validate_modules(report)
        self.assertEqual(report['modules'][0]['kind'], 'synthetic_ast_module')
        package.f = lambda x: x + 2
        self.assertIn('synthetic_code_mismatch', self.codes(inv.collect_modules({'ast_fixture': package}, files, synthetic=registration)))

    def test_save_complete_json_before_validation_failure(self):
        report = inv.collect_modules({'a': module('a', self.a), 'b': module('b', self.b)}, {})
        output = self.root / 'INVENTORY.json'
        with self.assertRaises(inv.ModuleInventoryError):
            inv.persist_and_validate(report, output)
        saved = json.loads(output.read_text())
        self.assertEqual(saved, report)
        self.assertEqual({r['name'] for r in saved['modules']}, {'a', 'b'})
        original = output.read_bytes()
        with self.assertRaises(FileExistsError):
            inv.persist_and_validate(report, output)
        self.assertEqual(output.read_bytes(), original)

    def test_validation_does_not_accept_deleted_failure_list(self):
        report = inv.collect_modules({'a': module('a', self.a)}, {})
        report['failures'] = []
        with self.assertRaises(ValueError):
            inv.validate_modules(report)

    def test_invalid_module_attribute_does_not_hide_later_modules(self):
        broken = module('broken', self.a)
        broken.__file__ = object()
        report = inv.collect_modules({'broken': broken, 'next': module('next', self.b)}, {})
        self.assertEqual(report['entry_count'], 2)
        self.assertIn('file_identity.invalid_absolute_path', self.codes(report))
        self.assertEqual({f['name'] for f in report['failures']}, {'broken', 'next'})
        json.dumps(report)

    def test_frozen_collections_abc_has_deliberately_different_actual_name(self):
        frozen = sys.modules['_collections_abc']
        source = Path(vars(frozen)['__file__']).resolve()
        runtime = Path(sys.executable).resolve()
        files = {str(source): pin(source), str(runtime): pin(runtime)}
        report = inv.collect_modules({'_collections_abc': frozen}, files)
        inv.validate_modules(report)
        self.assertEqual(report['modules'][0]['module_name'], 'collections.abc')

    def test_namespace_canonical_snapshot_key_required(self):
        loader = importlib.machinery.NamespaceLoader('pkg', [str(self.root)], None)
        spec = importlib.machinery.ModuleSpec('pkg', loader, is_package=True)
        spec.submodule_search_locations = [str(self.root)]
        package = importlib.util.module_from_spec(spec)
        report = inv.collect_modules({'alias_only': package}, self.files, namespaces={'pkg': {'paths': [str(self.root)]}})
        self.assertIn('namespace_canonical_object_mismatch', self.codes(report))

    def typing_inputs(self):
        data = vars(typing)
        source = Path(data['__file__']).resolve()
        files = {str(source): pin(source)}
        modules = {'typing': typing, 'typing.io': data['io'], 'typing.re': data['re']}
        registered = {name: {'kind': 'typing_compat_namespace', 'owner': 'typing', 'attribute': name.split('.')[1]}
                      for name in ('typing.io', 'typing.re')}
        return files, modules, registered

    def test_explicit_typing_class_namespace_source_and_code_binding(self):
        files, modules, registered = self.typing_inputs()
        report = inv.collect_modules(modules, files, registered_objects=registered)
        inv.validate_modules(report)
        self.assertEqual(report['modules'][1]['kind'], 'registered_typing_compat_namespace')
        self.assertEqual(report['modules'][2]['kind'], 'registered_typing_compat_namespace')
        failed = inv.collect_modules(modules, files)
        self.assertEqual(self.codes(failed).count('module_object_invalid'), 2)

    def test_typing_fake_class_same_name_and_owner_replacement_rejected(self):
        files, modules, registered = self.typing_inputs()
        modules['typing.io'] = type('typing.io', (), {'__module__': 'typing'})
        report = inv.collect_modules(modules, files, registered_objects=registered)
        self.assertIn('registered_object_identity_mismatch', self.codes(report))
        original = vars(typing)['io']
        try:
            typing.io = vars(typing)['re']
            modules['typing.io'] = vars(typing)['io']
            report = inv.collect_modules(modules, files, registered_objects=registered)
            self.assertIn('registered_object_binding_error', self.codes(report))
        finally:
            typing.io = original

    def test_typing_provider_and_unregistered_class_policy_rejected(self):
        files, modules, registered = self.typing_inputs()
        modules['typing'] = module('typing', Path(vars(typing)['__file__']))
        report = inv.collect_modules(modules, files, registered_objects=registered)
        self.assertIn('registered_object_owner_invalid', self.codes(report))
        files, modules, registered = self.typing_inputs()
        registered['typing.io']['attribute'] = 'some_other_class'
        report = inv.collect_modules(modules, files, registered_objects=registered)
        self.assertIn('registered_object_policy_invalid', self.codes(report))

    def test_builtin_display_name_is_diagnostic_not_identity(self):
        runtime = Path(sys.executable).resolve()
        original = vars(sys)['__name__']
        try:
            sys.__name__ = 'a_valid_different_display_name'
            report = inv.collect_modules({'sys': sys}, {str(runtime): pin(runtime)})
            inv.validate_modules(report)
            self.assertEqual(report['modules'][0]['module_name'], 'a_valid_different_display_name')
        finally:
            sys.__name__ = original

    def test_replacement_under_builtin_canonical_key_still_rejected(self):
        runtime = Path(sys.executable).resolve()
        fake = types.ModuleType('different_display_name')
        fake.__spec__, fake.__loader__ = sys.__spec__, sys.__loader__
        report = inv.collect_modules({'sys': fake}, {str(runtime): pin(runtime)})
        self.assertIn('builtin_or_frozen_object_alias_mismatch', self.codes(report))

    def saved_builtin_fixture(self):
        runtime = Path(sys.executable).resolve()
        report = inv.collect_modules({'sys': sys, 'sys_alias': sys}, {str(runtime): pin(runtime)})
        inv.validate_modules(report)
        return report

    def test_offline_replay_name_compatibility_does_not_claim_live_admission(self):
        saved = self.saved_builtin_fixture()
        error = {'code': 'builtin_or_frozen_object_alias_mismatch', 'detail': 'sys'}
        for row in saved['modules']:
            row.update(module_name='display_alias', errors=[dict(error)], match=False)
        saved['failures'] = [{'name': row['name'], **error} for row in saved['modules']]
        saved['status'] = 'FAIL_MODULE_IDENTITY'
        original = copy.deepcopy(saved)
        result = replay.replay_inventory(saved)
        self.assertFalse(result['failures'])
        self.assertEqual(len(result['reclassified_legacy_errors']), 2)
        self.assertIs(result['live_admission'], False)
        self.assertEqual(result['historical_result_unchanged'], 'FAIL_MODULE_IDENTITY')
        self.assertEqual(saved, original)

    def test_offline_replay_rejects_foreign_object_ids_loader_and_unknown_kind(self):
        for change, expected in (
            (lambda r: r['modules'][1].update(object_id='0xdeadbeef'), 'saved_canonical_object_id_mismatch'),
            (lambda r: r['modules'][1].update(loader='unrecognized.Loader'), 'saved_builtin_or_frozen_loader_conflict'),
            (lambda r: r['modules'][1].update(kind='unknown_no_file'), 'unknown_or_unverified_module_kind')):
            saved = self.saved_builtin_fixture()
            change(saved)
            result = replay.replay_inventory(saved)
            self.assertIn(expected, [failure['code'] for failure in result['failures']])

    def test_offline_replay_retains_unrelated_prior_failure(self):
        saved = self.saved_builtin_fixture()
        error = {'code': 'unverified_builtin_or_frozen', 'detail': 'sys'}
        saved['modules'][0].update(errors=[error], match=False)
        saved['failures'] = [{'name': 'sys', **error}]
        saved['status'] = 'FAIL_MODULE_IDENTITY'
        result = replay.replay_inventory(saved)
        self.assertIn('retained_original_failure', [failure['code'] for failure in result['failures']])
        self.assertFalse(result['reclassified_legacy_errors'])

    def test_no_task_or_numpy_imported(self):
        self.assertNotIn('numpy', sys.modules)
        self.assertFalse(any(n.startswith('candidates.qwen2_resident_matrix') for n in sys.modules))
        self.assertFalse(any(n.startswith('_terminal_only') for n in sys.modules))


if __name__ == '__main__':
    unittest.main()
