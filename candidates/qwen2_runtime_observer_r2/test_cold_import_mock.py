"""Pure mocks and synthetic temporary files only; never execute a cold/native run."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

PATH = Path(__file__).with_name('cold_import.py')
SPEC = importlib.util.spec_from_file_location('_test_cold_import_module', PATH)
cold = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cold)


def pin(raw=b'synthetic code\n'):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


class ColdPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cold_mock_')
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.observer = self.root / 'observer'
        self.buffer = self.root / 'capture.py'
        self.elf = self.root / 'matrix.so'
        self.output = self.root / 'out'
        self.output.mkdir()
        self.config = {'files': {}, 'source_root': str(self.source),
                       'observer_root': str(self.observer),
                       'buffer_source': str(self.buffer), 'elf': str(self.elf),
                       'inputs': {}, 'runtime_graph': {'files': {}}}

    def tearDown(self):
        self.temp.cleanup()

    def test_payload_and_matrix_elf_never_admitted_even_if_pinned(self):
        tensor = self.root / 'task.f32le'
        disguised = self.root / 'declared_input.py'
        source = self.source / 'module.py'
        observer_pins = self.observer / 'SOURCE_PINS.json'
        self.config['inputs'] = {'qr': {'path': str(tensor)},
                                 'kr': {'path': str(disguised)}}
        names = [tensor, disguised, self.elf, source, observer_pins,
                 self.root / 'metadata.json', self.root / 'model.bin']
        self.config['files'] = {str(name): pin() for name in names}
        self.config['runtime_graph']['files'] = {str(self.elf): pin()}
        with patch.object(cold, 'digest', side_effect=AssertionError('must not hash')):
            files, excluded = cold.select_cold_files(self.config)
        self.assertEqual(set(files), {str(source), str(observer_pins)})
        self.assertEqual(excluded, {str(tensor), str(disguised), str(self.elf)})

    def test_noncanonical_and_malformed_pins_rejected(self):
        self.config['files'] = {str(self.source / '..' / 'source' / 'a.py'): pin()}
        with self.assertRaisesRegex(ValueError, 'noncanonical'):
            cold.select_cold_files(self.config)
        self.config['files'] = {str(self.source / 'a.py'): {'bytes': -1, 'sha256': 'bad'}}
        with self.assertRaisesRegex(ValueError, 'malformed'):
            cold.select_cold_files(self.config)

    def test_no_process_network_explicit_cdll_or_payload_reads(self):
        guard = cold.ColdGuard(self.config, {}, self.output)
        forbidden = [('subprocess.Popen', ('git',)), ('os.system', ('echo',)),
                     ('os.posix_spawn', ('anything',)), ('os.exec', ('anything',)),
                     ('socket.__new__', ()), ('ctypes.dlopen', (str(self.elf),)),
                     ('import', ('torch', None)),
                     ('open', (str(self.root / 'qr.f32le'), 'rb', 0)),
                     ('open', (str(self.root / 'elsewhere.txt'), 'w', 0)),
                     ('open', (str(self.root / 'cache.pyc'), 'rb', 0))]
        for event, args in forbidden:
            with self.subTest(event=event, args=args), self.assertRaises(PermissionError):
                guard.audit(event, args)
        guard.audit('ctypes.dlopen', (None,))
        guard.audit('open', ('/proc/self/maps', 'r', 0))
        guard.audit('open', (str(self.output / 'evidence.json'), 'x', 0))
        self.assertEqual(len(guard.events), 1)

    def test_task_profile_blocks_functions_generated_init_and_recipe(self):
        guard = cold.ColdGuard(self.config, {}, self.output)
        for name in ('__init__', 'run', 'tick', 'op', 'configure_library',
                     'extract_sources', 'run_recipe', 'other_arithmetic'):
            frame = types.SimpleNamespace(
                f_code=types.SimpleNamespace(co_filename=str(self.source / 'dut.py'),
                                             co_name=name, co_qualname=name, co_flags=2),
                f_globals={})
            with self.subTest(name=name), self.assertRaises(PermissionError):
                guard.profile(frame, 'call', None)
        generated = types.SimpleNamespace(
            f_code=types.SimpleNamespace(co_filename='<string>', co_name='__init__',
                                         co_qualname='Record.__init__', co_flags=2),
            f_globals={'__file__': str(self.source / 'dut.py')})
        with self.assertRaises(PermissionError):
            guard.profile(generated, 'call', None)
        for name in ('<module>', 'DutClass'):
            frame = types.SimpleNamespace(
                f_code=types.SimpleNamespace(co_filename=str(self.source / 'dut.py'),
                                             co_name=name, co_qualname=name, co_flags=0),
                f_globals={})
            guard.profile(frame, 'call', None)
        dependency = types.SimpleNamespace(
            f_code=types.SimpleNamespace(co_filename='/pinned/numpy/__init__.py',
                                         co_name='_sanity_check', co_qualname='_sanity_check',
                                         co_flags=2), f_globals={})
        guard.profile(dependency, 'call', None)

    def test_pin_collector_retains_each_drift(self):
        first, second = self.root / 'first.py', self.root / 'second.py'
        first.write_bytes(b'first')
        second.write_bytes(b'second')
        rows = [cold.pin_record(path, pin(b'wrong')) for path in (first, second)]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(not row['match'] and 'sha256' in row for row in rows))

    def test_map_unknown_and_matrix_are_recorded_without_content_reads(self):
        unknown = self.root / 'unknown.f32le'
        unknown.write_bytes(b'synthetic not user data')
        self.elf.write_bytes(b'synthetic not ELF')
        raw = '\n'.join('1000-2000 r--p 00000000 00:00 1 ' + str(path)
                        for path in (unknown, self.elf))
        with patch.object(cold, 'digest', side_effect=AssertionError('must not hash unknown')):
            report = cold.collect_maps(raw, {}, str(self.elf))
        self.assertEqual(len(report['failures']), 2)
        self.assertTrue(report['matrix_elf_loaded'])
        self.assertTrue(all('sha256' not in row for row in report['mappings']))

    def test_map_collector_aggregates_two_pinned_mismatches(self):
        paths = [self.root / 'one.so', self.root / 'two.so']
        for path in paths:
            path.write_bytes(b'changed')
        raw = '\n'.join('1000-2000 r--p 00000000 00:00 1 ' + str(path) for path in paths)
        report = cold.collect_maps(raw, {str(p): pin() for p in paths}, str(self.elf))
        self.assertEqual(len(report['failures']), 2)
        self.assertTrue(all('mapped_file_pin_differs' in row['reasons']
                            for row in report['failures']))

    def test_both_raw_ledgers_and_full_reports_precede_validation(self):
        stage = self.output / 'snapshot'
        unknown = self.root / 'unknown.so'
        unknown.write_bytes(b'synthetic')
        raw = '1000-2000 r--p 00000000 00:00 1 ' + str(unknown)
        events = []
        def collect(*args, **kwargs):
            self.assertTrue((stage / 'MODULES_RAW.json').exists())
            self.assertTrue((stage / 'MAPS.txt').exists())
            events.append('collect')
            return {'status': 'FAIL', 'failures': ['module one', 'module two']}
        def validate(report):
            self.assertTrue((stage / 'MODULE_AUDIT.json').exists())
            self.assertTrue((stage / 'MAP_AUDIT.json').exists())
            events.append('validate')
            raise ValueError('two module failures')
        helper = types.SimpleNamespace(collect_modules=collect, validate_modules=validate)
        with patch.object(cold.Path, 'read_text', return_value=raw):
            errors = cold.snapshot_stage(self.output, 'snapshot', helper, {}, self.config, {})
        self.assertEqual(events, ['collect', 'validate'])
        self.assertEqual([error['gate'] for error in errors], ['modules', 'maps'])
        self.assertEqual(json.loads((stage / 'MODULE_AUDIT.json').read_text())['failures'],
                         ['module one', 'module two'])

    def test_failed_module_collector_still_retains_maps(self):
        helper = types.SimpleNamespace(
            collect_modules=lambda *a, **k: (_ for _ in ()).throw(ValueError('collector failure')),
            validate_modules=lambda report: (_ for _ in ()).throw(ValueError('rejected')))
        with patch.object(cold.Path, 'read_text', return_value=''):
            errors = cold.snapshot_stage(self.output, 'failure', helper, {}, self.config, {})
        target = self.output / 'failure'
        self.assertTrue((target / 'MAP_AUDIT.json').exists())
        self.assertEqual(json.loads((target / 'MODULE_AUDIT.json').read_text())['status'],
                         'FAIL_COLLECTOR')
        self.assertEqual(errors[0]['gate'], 'modules')

    def test_fixed_namespace_and_explicit_import_coverage(self):
        names = cold.cold_namespaces(self.source)
        self.assertEqual(set(names), set(cold.COLD_NAMESPACE_NAMES))
        self.assertEqual(names['scripts'], {'paths': [str(self.source / 'scripts')]})
        self.assertIn('candidates.qwen2_resident_matrix.official_bf16.owners', cold.DUT_MODULE_NAMES)
        self.assertIn('candidates.qwen2_resident_matrix.production_qk16_model.entry', cold.DUT_MODULE_NAMES)
        self.assertEqual(cold.RECIPE_MODULE, 'scripts.qwen2_block_recipe_model')
        self.assertEqual(set(cold.LOCAL_MODULE_NAMES), {'harness', 'runtime_observer', 'reference_capture'})

    def test_raw_metadata_is_json_safe_without_custom_hooks(self):
        class Hostile:
            def __repr__(self):
                raise AssertionError('must not repr')
            def __getattr__(self, name):
                raise AssertionError('must not getattr')
        module = types.ModuleType('mock_module')
        module.__file__ = Hostile()
        module.__package__ = Hostile()
        module.__spec__ = Hostile()
        module.__path__ = Hostile()
        result = cold.raw_modules({'mock_module': module, 7: Hostile()})
        encoded = json.dumps(result)
        self.assertIn('Hostile', encoded)
        self.assertEqual(result['module_count'], 2)

    def test_pinned_mapping_outside_explicit_allowlist_is_not_read(self):
        path = self.root / 'otherwise_pinned.so'
        path.write_bytes(b'synthetic')
        raw = '1000-2000 r--p 00000000 00:00 1 ' + str(path)
        with patch.object(cold, 'digest', side_effect=AssertionError('must not hash')):
            report = cold.collect_maps(raw, {str(path): pin()}, str(self.elf), [])
        self.assertIn('mapping_outside_allowlist_not_read', report['failures'][0]['reasons'])
        self.assertNotIn('sha256', report['failures'][0])

    def test_raw_collector_failure_still_saves_maps_and_full_audits(self):
        helper = types.SimpleNamespace(
            collect_modules=lambda *a, **k: {'status': 'PASS', 'modules': []},
            validate_modules=lambda report: report)
        with patch.object(cold, 'raw_modules', side_effect=ValueError('raw failure')), \
                patch.object(cold.Path, 'read_text', return_value=''):
            errors = cold.snapshot_stage(self.output, 'raw_failure', helper, {}, self.config, {})
        target = self.output / 'raw_failure'
        self.assertTrue((target / 'MAPS.txt').exists())
        self.assertTrue((target / 'MAP_AUDIT.json').exists())
        self.assertEqual(errors[0]['gate'], 'raw_modules')

    def test_disarmed_profile_and_swallowed_violation_fail_closed(self):
        guard = cold.ColdGuard(self.config, {}, self.output)
        callback = guard.profile
        for current in (None, object()):
            with patch.object(cold.sys, 'getprofile', return_value=current), \
                    patch.object(cold.sys, 'setprofile') as clear:
                errors = cold.stop_task_profile(guard, callback)
            self.assertIn('removed or replaced', errors[0]['error'])
            clear.assert_called_once_with(None)
        guard.blocked = [{'kind': 'task_execution_forbidden', 'detail': 'caught by importer'}]
        with patch.object(cold.sys, 'getprofile', return_value=callback), \
                patch.object(cold.sys, 'setprofile'):
            errors = cold.stop_task_profile(guard, callback)
        self.assertEqual(errors[0]['violations'], guard.blocked)
        guard.blocked = [{'kind': 'bytecode_cache_not_admitted', 'detail': 'normal import fallback'}]
        with patch.object(cold.sys, 'getprofile', return_value=callback), \
                patch.object(cold.sys, 'setprofile'):
            self.assertEqual(cold.stop_task_profile(guard, callback), [])

    def factory_fixture(self, txt=None):
        path = self.root / 'dataclasses.py'
        raw = b'def _create_fn(name, args, body, *, globals=None, locals=None):\n    return None\n'
        path.write_bytes(raw)
        code = compile(raw, str(path), 'exec', dont_inherit=True, optimize=cold.sys.flags.optimize)
        caller_code = next(item for item in code.co_consts if type(item) is types.CodeType)
        dependency = types.ModuleType('dataclasses')
        dependency.__file__ = str(path)
        dependency._create_fn = types.FunctionType(caller_code, vars(dependency))
        if txt is None:
            txt = ('def __create_fn__(_default):\n'
                   ' def __init__(self, value=_default):\n'
                   '  self.value = value\n'
                   ' return __init__')
        complete = compile(txt, '<string>', 'exec', dont_inherit=True, optimize=cold.sys.flags.optimize)
        factory_code = next(item for item in complete.co_consts if type(item) is types.CodeType)
        task_globals = {'__file__': str(self.source / 'dut.py'), '__name__': 'mock_dut'}
        factory = types.FunctionType(factory_code, task_globals)
        arguments = {'_default': object()}
        caller = types.SimpleNamespace(f_code=caller_code, f_globals=vars(dependency),
            f_locals={'txt': txt, 'ns': {'__create_fn__': factory}, 'locals': arguments,
                      'globals': task_globals, 'name': '__init__'})
        frame = types.SimpleNamespace(f_code=factory_code, f_globals=task_globals,
                                      f_locals=dict(arguments), f_back=caller)
        guard = cold.ColdGuard(self.config, {str(path): pin(raw)}, self.output)
        return guard, dependency, frame

    def test_exact_pinned_dataclass_factory_only_defines_method(self):
        guard, dependency, frame = self.factory_fixture()
        with patch.dict(cold.sys.modules, {'dataclasses': dependency}), \
                patch.object(cold.sys, 'base_prefix', str(self.root)):
            guard.profile(frame, 'call', None)
        self.assertEqual(guard.codegen_events[0]['kind'], 'pinned_dataclass_method_definition')
        self.assertEqual(guard.codegen_events[0]['method'], '__init__')
        # The generated constructor itself is never allowed, even with same caller.
        method = next(item for item in frame.f_code.co_consts if type(item) is types.CodeType)
        frame.f_code = method
        with self.assertRaises(PermissionError):
            guard.profile(frame, 'call', None)

    def test_factory_caller_matches_full_actual_stdlib_compile_without_execution(self):
        guard, dependency, frame = self.factory_fixture()
        path = Path(cold.sys.base_prefix) / 'lib' / ('python%d.%d' % cold.sys.version_info[:2]) / 'dataclasses.py'
        raw = path.read_bytes()
        complete = compile(raw, str(path), 'exec', dont_inherit=True, optimize=cold.sys.flags.optimize)
        caller_code = next(item for item in complete.co_consts
                           if type(item) is types.CodeType and item.co_name == '_create_fn')
        dependency.__file__ = str(path)
        dependency._create_fn = types.FunctionType(caller_code, vars(dependency))
        frame.f_back.f_code = caller_code
        guard.files = {str(path): pin(raw)}
        with patch.dict(cold.sys.modules, {'dataclasses': dependency}):
            guard.profile(frame, 'call', None)
        self.assertEqual(guard.codegen_events[0]['caller_source_sha256'], pin(raw)['sha256'])
        # Source is compiled for identity only; neither _create_fn nor a DUT runs.

    def test_dataclass_factory_binds_pin_caller_globals_and_factory_text(self):
        for changed in ('pin', 'caller_code', 'caller_globals', 'factory_text',
                        'factory_object', 'argument_object', 'task_globals', 'parent'):
            guard, dependency, frame = self.factory_fixture()
            if changed == 'pin':
                guard.files[str(self.root / 'dataclasses.py')] = pin(b'drift')
            elif changed == 'caller_code':
                frame.f_back.f_code = compile('pass', '<string>', 'exec')
            elif changed == 'caller_globals':
                frame.f_back.f_globals = {}
            elif changed == 'factory_text':
                frame.f_back.f_locals['txt'] += '\n# altered line table source'
                frame.f_back.f_locals['txt'] = frame.f_back.f_locals['txt'].replace('self.value = value', 'self.value = None')
            elif changed == 'factory_object':
                frame.f_back.f_locals['ns']['__create_fn__'] = lambda: None
            elif changed == 'argument_object':
                frame.f_locals['_default'] = object()
            elif changed == 'task_globals':
                frame.f_back.f_locals['globals'] = {}
            else:
                frame.f_back = None
            with self.subTest(changed=changed), \
                    patch.dict(cold.sys.modules, {'dataclasses': dependency}), \
                    patch.object(cold.sys, 'base_prefix', str(self.root)), \
                    self.assertRaises(PermissionError):
                guard.profile(frame, 'call', None)

    def test_codegen_factory_cannot_execute_annotations_defaults_or_decorators(self):
        examples = [
            'def __create_fn__():\n side_effect()\n def method(): pass\n return method',
            '@side_effect()\ndef __create_fn__():\n def method(): pass\n return method',
            'def __create_fn__(x=side_effect()):\n def method(): pass\n return method',
            'def __create_fn__():\n @side_effect()\n def method(): pass\n return method',
            'def __create_fn__():\n def method(x=side_effect()): pass\n return method',
            'def __create_fn__():\n def method(x: side_effect()): pass\n return method',
            'def __create_fn__():\n def method() -> side_effect(): pass\n return method',
            'def __create_fn__():\n def method(): pass\n return method()',
            'def unrelated():\n def method(): pass\n return method',
        ]
        for txt in examples:
            with self.subTest(txt=txt):
                self.assertFalse(cold.definition_factory_text(txt))
        self.assertTrue(cold.definition_factory_text(
            'def __create_fn__(_type, _default):\n'
            ' def method(self, value:_type=_default) -> _type: return value\n'
            ' return method'))

    def test_arbitrary_string_factory_is_not_dependency_admission(self):
        guard, dependency, frame = self.factory_fixture()
        with patch.dict(cold.sys.modules, {'dataclasses': dependency}), \
                patch.object(cold.sys, 'base_prefix', str(self.root)):
            # A same-name function not bound to pinned caller code cannot pass.
            wrong_code = compile('def _create_fn(): return 99', str(self.root / 'dataclasses.py'), 'exec')
            wrong = next(item for item in wrong_code.co_consts if type(item) is types.CodeType)
            dependency._create_fn = types.FunctionType(wrong, vars(dependency))
            frame.f_back.f_code = wrong
            with self.assertRaises(PermissionError):
                guard.profile(frame, 'call', None)

    def test_wrong_config_digest_saves_raw_evidence_without_imports(self):
        config = self.root / 'untrusted_config.json'
        config.write_text('{"files": {"/must/not/read.f32le": {}}}')
        target = self.root / 'rejected_config'
        with patch.object(cold.importlib, 'import_module', side_effect=AssertionError('no import')):
            result = cold.main(['--config', str(config), '--config-sha', '0' * 64,
                                '--output', str(target)])
        self.assertEqual(result, 1)
        self.assertTrue((target / 'MODULES_RAW_ON_FAILURE.json').exists())
        self.assertTrue((target / 'MAPS_ON_FAILURE.txt').exists())
        report = json.loads((target / 'RESULT.json').read_text())
        self.assertEqual(report['status'], 'FAIL_COLD_IMPORT')
        self.assertIn('exact config SHA256', report['errors'][0]['error'])
        self.assertFalse(report['task_payloads_hashed'])


if __name__ == '__main__':
    unittest.main()
