"""Pure stdlib/static/mock tests. Never call worker.run or the launch path."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent))
import gate_common as C
import prepare_gate as P
import run_gate as R
import worker as W


class GateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
    def tearDown(self):
        self.temp.cleanup()
    def test_no_target_imports(self):
        self.assertFalse(any(x == 'torch' or x.startswith('torch.') or x == 'numpy' or x.startswith('numpy.') or x == 'transformers' or x.startswith('transformers.') for x in sys.modules))
    def test_sha_identity(self):
        p = self.root / 'x'; p.write_bytes(b'abc')
        self.assertEqual(C.file_id(p), {'bytes': 3, 'sha256': C.sha(b'abc')})
    def test_write_new_no_overwrite(self):
        p = self.root / 'out'; C.write_new(p, {'x': 1})
        with self.assertRaises(FileExistsError): C.write_new(p, {'x': 2})
    def test_exact_json_sha(self):
        p = self.root / 'out'; i = C.write_new(p, {'x': 1})
        self.assertEqual(C.read_checked(p, i['sha256']), {'x': 1})
        with self.assertRaises(ValueError): C.read_checked(p, '0' * 64)
    def test_class_full_code_and_source(self):
        # Only synthetic pure-Python mock code is executed, never model source.
        raw = b'class Fake:\n    def __init__(self, x: int):\n        self.x = x\n    def forward(self):\n        def nested():\n            return self.x\n        return nested()\n'
        filename = str(self.root / 'fake.py')
        expected = C.class_static_identity(raw, 'Fake', filename)
        ns = {'__name__': 'fake'}
        exec(compile(raw, filename, 'exec', dont_inherit=True, optimize=0), ns)
        m = types.ModuleType('fake'); m.__file__ = filename
        actual = C.actual_class_identity(ns['Fake'], expected, m)
        self.assertTrue(actual['own_method_code_exact'])
        self.assertEqual(set(expected['methods']), {'__init__', 'forward'})
        self.assertEqual(expected['methods']['forward']['nested'][0]['name'], 'nested')
        self.assertEqual(expected['file_sha256'], C.sha(raw))
    def test_class_code_substitution_rejected(self):
        raw = b'class Fake:\n    def forward(self):\n        return 1\n'
        filename = str(self.root / 'fake.py')
        expected = C.class_static_identity(raw, 'Fake', filename)
        ns = {'__name__': 'fake'}; exec(compile(raw.replace(b'return 1', b'return 2'), filename, 'exec', dont_inherit=True, optimize=0), ns)
        m = types.ModuleType('fake'); m.__file__ = filename
        self.assertFalse(C.actual_class_identity(ns['Fake'], expected, m)['own_method_code_exact'])
    def test_class_filename_substitution_rejected(self):
        raw = b'class Fake:\n    def forward(self):\n        return 1\n'
        expected = C.class_static_identity(raw, 'Fake', '/exact/fake.py')
        ns = {'__name__': 'fake'}; exec(compile(raw, '/other/fake.py', 'exec', dont_inherit=True, optimize=0), ns)
        m = types.ModuleType('fake'); m.__file__ = '/exact/fake.py'
        self.assertFalse(C.actual_class_identity(ns['Fake'], expected, m)['own_method_code_exact'])
    def test_missing_class_method_rejected(self):
        raw = b'class Fake:\n    def forward(self):\n        return 1\n'
        expected = C.class_static_identity(raw, 'Fake', '/exact/fake.py')
        class Fake: pass
        m = types.ModuleType('fake'); m.__file__ = '/exact/fake.py'
        self.assertFalse(C.actual_class_identity(Fake, expected, m)['own_method_code_exact'])
    def test_selected_bindings_never_call_activation_instantiator(self):
        class PretrainedConfig: pass
        class Module: pass
        class Config(PretrainedConfig): pass
        class Layer(Module): pass
        class SiLU:
            def __init__(self): raise AssertionError('must not instantiate activation')
        class ClassInstantier(dict):
            def __getitem__(self, key): raise AssertionError('must bypass custom getitem')
        Attention, Flash, Sdpa, MLP = object(), object(), object(), object()
        def mod(name, values):
            m = types.ModuleType(name); vars(m).update(values); return m
        mapping = ClassInstantier(silu=SiLU)
        modules = {
            'transformers.configuration_utils': mod('configuration_utils', {'PretrainedConfig': PretrainedConfig}),
            'torch.nn': mod('nn', {'Module': Module, 'SiLU': SiLU}),
            'transformers.activations': mod('activations', {'ACT2FN': mapping, 'ClassInstantier': ClassInstantier}),
            'transformers.models.qwen2.modeling_qwen2': mod('modeling_qwen2', {
                'QWEN2_ATTENTION_CLASSES': {'eager': Attention, 'flash_attention_2': Flash, 'sdpa': Sdpa},
                'Qwen2FlashAttention2': Flash, 'Qwen2SdpaAttention': Sdpa, 'Qwen2MLP': MLP, 'ACT2FN': mapping})}
        imported = {'Qwen2Config': Config, 'Qwen2DecoderLayer': Layer, 'Qwen2Attention': Attention, 'Qwen2MLP': MLP}
        self.assertTrue(C.selected_bindings(imported, modules)['passed'])
        vars(modules['torch.nn'])['SiLU'] = object()
        self.assertFalse(C.selected_bindings(imported, modules)['passed'])
    def test_dynamic_modules_retained(self):
        m = types.ModuleType('torch.fake_generated')
        exec(compile('def generated(x):\n    return x\n', '<generated>', 'exec', dont_inherit=True), vars(m))
        result = C.collect_modules({'torch.fake_generated': m, 'sentinel': None})
        self.assertEqual(len(result), 2)
        dynamic = [x for x in result if x['name'] == 'torch.fake_generated'][0]
        self.assertEqual(dynamic['kind'], 'dynamic_no_file_unproven')
        self.assertFalse(dynamic['code_origin_proven'])
        members = {x['name']: x for x in dynamic['all_dictionary_members']}
        self.assertEqual(set(members), set(vars(m)))
        self.assertEqual(members['generated']['code']['filename'], '<generated>')
    def test_opaque_cython_like_metatype_does_not_execute_descriptors(self):
        class Meta(type):
            @property
            def __module__(cls):
                raise AssertionError('must not read custom metatype module')
            def __getattribute__(cls, key):
                if key in ('__dict__', '__qualname__'):
                    raise AssertionError('must not read custom metatype attributes')
                return super().__getattribute__(key)
        class Opaque(metaclass=Meta):
            pass
        m = types.ModuleType('torch.fake'); m.Opaque = Opaque
        records = C.collect_modules({'torch.fake': m})
        self.assertEqual(records[0]['errors'], [])
        self.assertEqual(len(records[0]['all_dictionary_members']), len(vars(m)))
        json.dumps(records)
    def test_module_subclass_getattribute_not_invoked(self):
        class HostileModule(types.ModuleType):
            def __getattribute__(self, name):
                raise AssertionError('no arbitrary module getters')
        m = HostileModule('hostile')
        d = types.ModuleType.__dict__['__dict__'].__get__(m, types.ModuleType)
        d['__file__'] = '/exact/hostile.py'
        self.assertEqual(C.collect_modules({'hostile': m})[0]['file'], '/exact/hostile.py')
    def test_unknown_metadata_never_iterated_compared_or_serialized_directly(self):
        class Hostile:
            def __eq__(self, other): raise AssertionError('no eq')
            def __iter__(self): raise AssertionError('no iteration')
            def __repr__(self): raise AssertionError('no repr')
            def __str__(self): raise AssertionError('no str')
        m = types.ModuleType('hostile')
        m.__file__ = Hostile(); m.__cached__ = Hostile(); m.__package__ = Hostile(); m.__path__ = Hostile()
        m.__spec__ = importlib.util.spec_from_loader('hostile', loader=None)
        m.__spec__.origin = Hostile()
        result = C.collect_modules({'hostile': m})
        json.dumps(result)
        self.assertEqual(len(result[0]['errors']), 2)
        self.assertFalse(C.verify_observed_files(result, [], {})['passed'])
    def test_opaque_spec_no_vars_or_getattr(self):
        class Hostile:
            def __getattribute__(self, key): raise AssertionError('no spec getters')
        m = types.ModuleType('hostile'); m.__spec__ = Hostile()
        json.dumps(C.collect_modules({'hostile': m}))
    def test_unknown_module_entry_retained(self):
        class Hostile:
            def __getattribute__(self, key): raise AssertionError('no module getter')
        rows = C.collect_modules({'a': Hostile(), 'b': types.ModuleType('b')})
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['kind'], 'non_module_entry')
        json.dumps(rows)
    def test_generated_origin_marker_preserved_not_mistaken_for_file(self):
        m = types.ModuleType('_remote_module_non_scriptable')
        m.__spec__ = importlib.util.spec_from_loader(m.__name__, loader=None, origin='torch-git')
        m.__spec__.has_location = False
        rows = C.collect_modules({m.__name__: m})
        self.assertEqual(rows[0]['spec_origin'], 'torch-git')
        self.assertIs(rows[0]['spec_has_location'], False)
        self.assertEqual(len(rows[0]['all_dictionary_members']), len(vars(m)))
        result = C.verify_observed_files(rows, [], {})
        self.assertTrue(result['passed'])
        self.assertEqual(result['nonfile_origin_markers'][0]['origin'], 'torch-git')
        self.assertFalse(result['nonfile_origin_markers'][0]['code_origin_proven'])
    def test_relative_location_origin_still_rejected(self):
        m = types.ModuleType('fake')
        m.__spec__ = importlib.util.spec_from_loader('fake', loader=None, origin='relative.py')
        m.__spec__.has_location = True
        self.assertFalse(C.verify_observed_files(C.collect_modules({'fake': m}), [], {})['passed'])
    def test_absolute_nonlocation_origin_still_hashed(self):
        p = self.root / 'source.py'; p.write_text('x = 1')
        m = types.ModuleType('fake')
        m.__spec__ = importlib.util.spec_from_loader('fake', loader=None, origin=str(p))
        m.__spec__.has_location = False
        rows = C.collect_modules({'fake': m})
        self.assertFalse(C.verify_observed_files(rows, [], {})['passed'])
        self.assertTrue(C.verify_observed_files(rows, [], {str(p): C.file_id(p)})['passed'])
    def test_builtin_not_dynamic_proof(self):
        m = types.ModuleType('fake')
        m.__spec__ = importlib.util.spec_from_loader('fake', loader=None, origin='built-in')
        self.assertEqual(C.collect_modules({'fake': m})[0]['kind'], 'built-in')
    def test_maps_complete_and_spaces(self):
        raw = '0010-0020 r-xp 00000000 08:01 123 /a\\040b.so\n0020-0030 rw-p 00000000 00:00 0\n0030-0040 r-xp 00000000 00:00 0 [vdso]\n'
        rows = C.parse_maps(raw)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]['decoded_pathname'], '/a b.so')
        self.assertEqual([x['kind'] for x in rows], ['file', 'anonymous', 'named_nonfile'])
    def test_exact_file_not_root_allowlist(self):
        p = self.root / 'a.py'; p.write_bytes(b'abc')
        modules = [{'name': 'a', 'file': str(p)}]
        self.assertTrue(C.verify_observed_files(modules, [], {str(p): C.file_id(p)})['passed'])
        self.assertFalse(C.verify_observed_files(modules, [], {})['passed'])
        p.write_bytes(b'different')
        self.assertFalse(C.verify_observed_files(modules, [], {str(p): {'bytes': 3, 'sha256': C.sha(b'abc')}})['passed'])
    def test_maps_file_hash_checked(self):
        p = self.root / 'a.so'; p.write_bytes(b'abc')
        rows = C.parse_maps('0010-0020 r-xp 00000000 08:01 123 ' + str(p))
        self.assertFalse(C.verify_observed_files([], rows, {})['passed'])
        self.assertTrue(C.verify_observed_files([], rows, {str(p): C.file_id(p)})['passed'])
    def test_pinned_but_excluded_native_map_rejected(self):
        p = self.root / '_tkinter.so'; p.write_bytes(b'abc')
        rows = C.parse_maps('0010-0020 r-xp 00000000 08:01 123 ' + str(p))
        self.assertFalse(C.verify_observed_files([], rows, {str(p): C.file_id(p)}, mapped_manifest={})['passed'])
    def test_gui_import_guard_is_narrow(self):
        with patch.object(sys, 'addaudithook') as audit, patch.object(sys, 'setprofile'):
            W.install_guards({'target': '/target', 'excluded_module_prefixes': ['tkinter', '_tkinter']})
            hook = audit.call_args.args[0]
            hook('import', ('torch',))
            hook('import', ('numpy',))
            for name in ('tkinter', 'tkinter.ttk', '_tkinter'):
                with self.assertRaises(RuntimeError): hook('import', (name,))
    def test_deleted_mapping_is_not_silently_dropped(self):
        rows = C.parse_maps('0010-0020 r-xp 00000000 08:01 123 /missing.so (deleted)')
        self.assertFalse(C.verify_observed_files([], rows, {})['passed'])
    def test_nonabsolute_origin_rejected(self):
        self.assertFalse(C.verify_observed_files([{'name': 'x', 'file': 'relative.py'}], [], {})['passed'])
    def test_existing_pyc_checked(self):
        p = self.root / 'x.pyc'; p.write_bytes(b'cache')
        self.assertFalse(C.verify_observed_files([{'name': 'x', 'cached': str(p)}], [], {})['passed'])
    def test_absent_cache_record_preserved_not_claimed_loaded(self):
        self.assertTrue(C.verify_observed_files([{'name': 'x', 'cached': str(self.root / 'absent.pyc')}], [], {})['passed'])
    def valid_review(self):
        return {'schema': 1, 'status': 'APPROVED_FOR_SINGLE_IMPORT_ONLY', 'config_sha256': 'cfg',
                'limits': C.LIMITS, 'blockers': [], 'model_import_executed': False, 'reviewer': 'independent'}
    def valid_approval(self):
        return {'schema': 1, 'action': 'single_official_normal_import_only', 'config_sha256': 'cfg',
                'review_sha256': 'review', 'maximum_invocations': 1, 'no_retry': True,
                'issued_by': 'parent', 'exclusive_import_slot': True, 'run_id': 'cold01'}
    def test_review_and_approval_gate(self):
        R.validate_review(self.valid_review(), 'cfg', 'review', self.valid_approval(), {'limits': C.LIMITS})
    def test_wrong_review_hash_rejected(self):
        with self.assertRaises(ValueError): R.validate_review(self.valid_review(), 'cfg', 'different', self.valid_approval(), {'limits': C.LIMITS})
    def test_approval_requires_independence(self):
        a = self.valid_approval(); a['issued_by'] = 'independent'
        with self.assertRaises(ValueError): R.validate_review(self.valid_review(), 'cfg', 'review', a, {'limits': C.LIMITS})
    def test_fixed_import_limits_not_full_reference_limits(self):
        review = self.valid_review(); review['limits'] = {**C.LIMITS, 'cpu_seconds_hard': 60}
        with self.assertRaises(ValueError): R.validate_review(review, 'cfg', 'review', self.valid_approval(), {'limits': C.LIMITS})
    def test_dynamic_compile_is_not_blocked(self):
        with patch.object(sys, 'addaudithook') as audit, patch.object(sys, 'setprofile') as profile:
            W.install_guards({'target': '/target'})
            audit_hook = audit.call_args.args[0]
            audit_hook('compile', (b'1', '<string>'))
            audit_hook('exec', (compile('1', '<string>', 'eval'),))
            for event in ('socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.sendto'):
                with self.assertRaises(RuntimeError): audit_hook(event, ())
    def test_process_spawn_guard_does_not_deny_compile_or_threads(self):
        with patch.object(sys, 'addaudithook') as audit, patch.object(sys, 'setprofile'):
            W.install_guards({'target': '/target'})
            hook = audit.call_args.args[0]
            for event in ('subprocess.Popen', 'os.fork', 'os.forkpty', 'os.posix_spawn', 'os.exec', 'os.system'):
                with self.assertRaises(RuntimeError): hook(event, ())
            for event in ('compile', 'exec', '_thread.start_new_thread', 'ctypes.dlopen'):
                hook(event, ())
    def test_fake_model_constructor_guard(self):
        with patch.object(sys, 'addaudithook'), patch.object(sys, 'setprofile') as profile:
            W.install_guards({'target': '/target'})
            fn = profile.call_args.args[0]
            frame = types.SimpleNamespace(f_code=types.SimpleNamespace(co_filename='/target/transformers/models/qwen2/modeling_qwen2.py', co_name='__init__', co_qualname='Qwen2DecoderLayer.__init__', co_firstlineno=1))
            with self.assertRaises(RuntimeError): fn(frame, 'call', None)
            frame.f_code.co_filename = '/runtime/torch/internal.py'
            fn(frame, 'call', None)  # normal PyTorch initialization allowed
    def test_no_target_access_prepare_import(self):
        self.assertEqual(C.LIMITS['affinity_count'], 1)
        self.assertEqual(C.LIMITS['cpu_seconds_hard'], 30)
        self.assertEqual(C.LIMITS['wall_seconds'], 45)
        self.assertFalse(C.LIMITS['rss_is_hard_cap'])
        self.assertFalse(C.LIMITS['address_space_limit_changed'])
    def test_environment_does_not_copy_secrets(self):
        with patch.dict(os.environ, {'SECRET_TOKEN': 'not-to-copy'}):
            env = R.runtime_environment(self.root)
            self.assertNotIn('SECRET_TOKEN', env)
            self.assertEqual(env['OMP_NUM_THREADS'], '1')
            self.assertEqual(env['HF_HUB_OFFLINE'], '1')
    def test_reused_parent_pid_does_not_adopt_unrelated_descendant(self):
        tracked = {10: 100, 11: 110}
        table = {10: {'pid': 10, 'ppid': 1, 'pgrp': 10, 'start_ticks': 999, 'state': 'S'},
                 11: {'pid': 11, 'ppid': 1, 'pgrp': 11, 'start_ticks': 999, 'state': 'S'},
                 12: {'pid': 12, 'ppid': 11, 'pgrp': 11, 'start_ticks': 120, 'state': 'S'}}
        self.assertEqual(R.expand_owned_tree(table, 10, tracked, 9999), {})
        self.assertNotIn(12, tracked)
    def test_reused_group_number_without_valid_anchor_is_not_adopted(self):
        tracked = {10: 100}
        table = {20: {'pid': 20, 'ppid': 1, 'pgrp': 10, 'start_ticks': 200, 'state': 'S'}}
        self.assertEqual(R.expand_owned_tree(table, 10, tracked, 9999), {})
    def test_real_descendant_and_adopted_child_are_tracked(self):
        tracked = {10: 100}
        table = {10: {'pid': 10, 'ppid': 9999, 'pgrp': 10, 'start_ticks': 100, 'state': 'S'},
                 11: {'pid': 11, 'ppid': 10, 'pgrp': 11, 'start_ticks': 110, 'state': 'S'},
                 12: {'pid': 12, 'ppid': 11, 'pgrp': 12, 'start_ticks': 120, 'state': 'S'},
                 13: {'pid': 13, 'ppid': 9999, 'pgrp': 13, 'start_ticks': 130, 'state': 'S'}}
        self.assertEqual(set(R.expand_owned_tree(table, 10, tracked, 9999)), {10, 11, 12, 13})
    def test_postflight_retains_all_differences(self):
        a = self.root / 'a'; b = self.root / 'b'
        a.write_bytes(b'a'); b.write_bytes(b'b')
        manifest = {str(a): C.file_id(a), str(b): C.file_id(b)}
        a.write_bytes(b'changed'); b.unlink()
        result = R.manifest_postflight(manifest)
        self.assertFalse(result['passed'])
        self.assertEqual(set(result['differences']), set(manifest))
    def test_torch_style_inherited_pseudofile_remains_dynamic(self):
        class Ops(types.ModuleType):
            __file__ = '_ops.py'
        rows = C.collect_modules({'torch.ops': Ops('torch.ops')})
        self.assertIsNone(rows[0]['file'])
        self.assertEqual(rows[0]['kind'], 'dynamic_no_file_unproven')
        self.assertEqual(rows[0]['errors'], [])
    def test_symlink_escape_rejected(self):
        nested = self.root / 'nested'; nested.mkdir()
        (self.root / 'secret').write_text('x')
        (nested / 'escape').symlink_to(self.root / 'secret')
        with self.assertRaises(ValueError): P.inventory(nested)


class LoopbackGuardTests(unittest.TestCase):
    """Synthetic source, synthetic frames, and mocked native socket metadata only.

    No real socket is created and no dependency source is executed.
    """
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / 'synthetic_probe.py'
        self.raw = b'def _has_ipv6(host):\n    sock = mock_socket\n    dispatch("socket.bind", (sock, (host, port)), sys._getframe(), "audit")\n    closed["value"] = close_result\n    finish(sys._getframe(), "return", outcome)\n    return outcome\n'
        self.source.write_bytes(self.raw)
        self.module = types.ModuleType('synthetic_probe')
        self.module.__file__ = str(self.source)
        self.mock_socket = object()
        self.closed = {'value': False}
        self.config = {'loopback_probe': {'module': 'synthetic_probe',
            'function': C.function_static_identity(self.raw, '_has_ipv6', str(self.source))}}
        self.capture, self.profile, self.state = W.network_guard(self.config)
        ns = vars(self.module)
        ns.update({'sys': sys, 'mock_socket': self.mock_socket, 'dispatch': self.capture,
                   'finish': self.profile, 'port': 0, 'outcome': True,
                   'close_result': True, 'closed': self.closed})
        exec(compile(self.raw, str(self.source), 'exec', dont_inherit=True, optimize=0), ns)
        self.module_patch = patch.dict(sys.modules, {'synthetic_probe': self.module})
        self.module_patch.start()
        self.socket_patch = patch.object(W, 'socket_record', side_effect=self.fake_socket_record)
        self.socket_patch.start()
    def tearDown(self):
        self.socket_patch.stop(); self.module_patch.stop(); self.temp.cleanup()
    def fake_socket_record(self, sock):
        return {'object': C.value_record(sock), 'exact_socket_type': sock is self.mock_socket,
                'family': 10, 'type': 1, 'proto': 0,
                'fileno': -1 if self.closed['value'] else 7,
                'fd_identity': {'device': 9, 'inode': 42, 'is_socket': True}}
    def call(self, host='::1'):
        self.module.HAS_IPV6 = self.module._has_ipv6(host)
        return W.probe_terminal(self.config, self.state)
    def test_exact_single_probe_with_bool_and_closed_fd(self):
        result = self.call()
        self.assertTrue(result['passed'])
        self.assertTrue(result['HAS_IPV6'])
        self.assertEqual(result['allowed_bind_count'], 1)
        e = self.state['events'][0]
        self.assertEqual(e['decision'], 'allowed')
        self.assertTrue(e['caller']['evidence_complete'])
        self.assertTrue(e['caller']['module_dict_is_frame_globals'])
        self.assertTrue(e['caller']['bound_function_code_is_frame_code'])
        self.assertTrue(e['audit_event_is_pre_operation'])
        self.assertEqual(e['address']['tuple_items'][0]['scalar'], '::1')
        json.dumps(self.state)
    def test_false_original_result_is_not_patched(self):
        self.module.outcome = False
        result = self.call()
        self.assertTrue(result['passed'])
        self.assertIs(result['HAS_IPV6'], False)
        self.assertTrue(result['audit_allowance_is_not_syscall_success'])
    def test_non_loopback_host_denied(self):
        for host in ('::', '2001:db8::1', 'example.com', 'localhost'):
            with self.assertRaises(RuntimeError): self.call(host)
        self.assertEqual(len(self.state['denied_events']), 4)
        self.assertEqual(len(self.state['allowed_bind_events']), 0)
    def test_ipv4_address_denied(self):
        with self.assertRaises(RuntimeError): self.call('127.0.0.1')
    def test_nonzero_port_denied(self):
        self.module.port = 1
        with self.assertRaises(RuntimeError): self.call()
    def test_bool_port_is_not_exact_integer_zero(self):
        self.module.port = False
        with self.assertRaises(RuntimeError): self.call()
    def test_address_subclasses_and_lists_denied(self):
        class TupleSubclass(tuple): pass
        for addr in (['::1', 0], TupleSubclass(('::1', 0)), ('::1', 0, 0, 0)):
            def wrapped(event, args, frame, origin):
                self.capture(event, (args[0], addr), frame, origin)
            self.module.dispatch = wrapped
            with self.assertRaises(RuntimeError): self.call()
    def test_ipv4_socket_wrong_socket_type_and_protocol_denied(self):
        base = self.fake_socket_record(self.mock_socket)
        for field, value in (('family', 2), ('type', 2), ('proto', 6), ('exact_socket_type', False)):
            with patch.object(W, 'socket_record', return_value={**base, field: value}):
                with self.assertRaises(RuntimeError): self.call()
    def test_foreign_caller_denied_and_retained(self):
        with self.assertRaises(RuntimeError):
            self.capture('socket.bind', (self.mock_socket, ('::1', 0)), sys._getframe(), 'audit')
        self.assertFalse(self.state['events'][0]['checks']['caller_exact'])
    def test_missing_caller_evidence_denied(self):
        with self.assertRaises(RuntimeError):
            self.capture('socket.bind', (self.mock_socket, ('::1', 0)), None, 'audit')
        self.assertFalse(self.state['events'][0]['caller']['evidence_complete'])
    def test_function_filename_substitution_denied(self):
        self.module._has_ipv6.__code__ = self.module._has_ipv6.__code__.replace(co_filename='/wrong/filename.py')
        with self.assertRaises(RuntimeError): self.call()
    def test_complete_code_substitution_denied(self):
        new = self.raw.replace(b'close_result', b'other_close_result')
        exec(compile(new, str(self.source), 'exec', dont_inherit=True, optimize=0), vars(self.module))
        with self.assertRaises(RuntimeError): self.call()
    def test_module_globals_identity_substitution_denied(self):
        foreign = dict(vars(self.module))
        fn = types.FunctionType(self.module._has_ipv6.__code__, foreign)
        self.module._has_ipv6 = fn
        with self.assertRaises(RuntimeError): self.call()
    def test_module_object_substitution_denied(self):
        with patch.dict(sys.modules, {'synthetic_probe': types.ModuleType('synthetic_probe')}):
            with self.assertRaises(RuntimeError): self.call()
    def test_modified_source_byte_denied(self):
        self.source.write_bytes(self.raw + b' ')
        with self.assertRaises(RuntimeError): self.call()
        self.assertFalse(self.state['events'][0]['caller']['source_exact'])
    def test_probe_duplicate_denied(self):
        self.assertTrue(self.call()['passed'])
        self.closed['value'] = False
        with self.assertRaises(RuntimeError): self.call()
        self.assertEqual(len(self.state['allowed_bind_events']), 1)
        self.assertEqual(len(self.state['denied_events']), 1)
        self.assertFalse(W.probe_terminal(self.config, self.state)['passed'])
    def test_no_event_is_not_a_probe_pass(self):
        self.module.HAS_IPV6 = False
        self.assertFalse(W.probe_terminal(self.config, self.state)['passed'])
    def test_missing_original_return_evidence_rejected(self):
        self.module.finish = lambda *args: None
        self.assertFalse(self.call()['passed'])
    def test_open_fd_at_original_return_rejected(self):
        self.module.close_result = False
        self.assertFalse(self.call()['passed'])
    def test_nonbool_return_rejected(self):
        self.module.outcome = 1
        self.assertFalse(self.call()['passed'])
    def test_replaced_module_at_terminal_rejected(self):
        self.assertTrue(self.call()['passed'])
        other = types.ModuleType('synthetic_probe'); vars(other).update(vars(self.module))
        with patch.dict(sys.modules, {'synthetic_probe': other}):
            self.assertFalse(W.probe_terminal(self.config, self.state)['passed'])
    def test_metadata_collection_error_is_denied_and_retained(self):
        with patch.object(W, 'socket_record', side_effect=ValueError('synthetic failure')):
            with self.assertRaises(RuntimeError): self.call()
        self.assertEqual(len(self.state['collection_errors']), 1)
        self.assertEqual(self.state['events'][0]['decision'], 'denied')
    def test_unknown_values_not_compared_or_stringified(self):
        class Hostile:
            def __eq__(self, other): raise AssertionError('no eq')
            def __repr__(self): raise AssertionError('no repr')
            def __str__(self): raise AssertionError('no str')
            def __getattribute__(self, key): raise AssertionError('no attr')
        self.socket_patch.stop()
        try:
            with self.assertRaises(RuntimeError):
                self.capture('socket.bind', (Hostile(), (Hostile(), Hostile())), sys._getframe(), 'audit')
            json.dumps(self.state)
        finally:
            self.socket_patch.start()
    def test_all_other_socket_audit_events_denied(self):
        for event in ('socket.connect', 'socket.connect_ex', 'socket.listen', 'socket.send',
                      'socket.sendall', 'socket.sendto', 'socket.accept', 'socket.getaddrinfo',
                      'socket.gethostbyname', 'socket.gethostbyaddr', 'socket.getnameinfo', 'socket.unknown'):
            with self.assertRaises(RuntimeError):
                self.capture(event, (self.mock_socket, ('::1', 0)), sys._getframe(), 'audit')
        self.assertEqual(len(self.state['allowed_bind_events']), 0)
    def test_construction_does_not_consume_bind_allowance(self):
        self.capture('socket.__new__', (self.mock_socket, 10, 1, 0), sys._getframe(), 'audit')
        self.assertEqual(len(self.state['allowed_bind_events']), 0)
        self.assertTrue(self.call()['passed'])
    def test_no_audit_profile_path_denies_mock_native_method(self):
        # Use exact built-in list methods as synthetic stand-ins. No socket exists.
        owner = []
        with patch.object(W, '_SOCKET_CLASS', list), patch.object(W, '_SOCKET_NATIVE', list), \
             patch.object(W, '_UNAUDITED_SOCKET_CALLS', frozenset(('append',))):
            with self.assertRaises(RuntimeError): self.profile(sys._getframe(), 'c_call', owner.append)
        row = self.state['events'][0]
        self.assertEqual(row['origin'], 'profile_c_call_no_audit_event')
        self.assertEqual(row['decision'], 'denied')
        self.assertFalse(row['audit_event_is_pre_operation'])
    def test_one_byte_config_and_review_mutations_rejected(self):
        for name in ('CONFIG.json', 'REVIEW.json'):
            p = self.root / name
            identity = C.write_new(p, {'bound': 'exact'})
            raw = p.read_bytes(); p.write_bytes(raw.replace(b'exact', b'exacu'))
            with self.assertRaises(ValueError): C.read_checked(p, identity['sha256'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
