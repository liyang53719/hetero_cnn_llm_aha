"""Pure Python/mock PC01 compile/link contract tests. Never starts a child."""
import ast
import builtins
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
# Bound only after the production author freezes every source entry.
PINS = {'run_relink.py': (19837, 'd80f19af41760b96f8a8a60d2a45faab21b2addea39bf5e805fe2a2a338e798d'), 'launch.py': (2045, '22b45762f255279d78b4ae0ef89bc20f862806cadda602291cea0af659dd8413'), 'dependency_gate.py': (5122, '49281296cb6daa034c6e7f2f741ff6d7af9b0e61abdd96d77c1856349e8597c7'), 'reference_helpers.py': (14870, 'a1eef5869774d6b66aa332966d1de7a3b0cbca5fad640e65d9ee666d609f9684')}


def audit(event, args):
    if event.startswith(('socket.', 'subprocess.')) or event in (
        'os.system', 'os.fork', 'os.forkpty', 'os.exec', 'os.posix_spawn', 'ctypes.dlopen'
    ):
        raise RuntimeError('COLD_NATIVE_NETWORK_FORBIDDEN')
    if event == 'import' and str(args[0]).split('.')[0] in ('numpy', 'torch', 'ctypes'):
        raise RuntimeError('COLD_NUMERICAL_IMPORT_FORBIDDEN')

sys.addaudithook(audit)


def pin(raw):
    return (len(raw), hashlib.sha256(raw).hexdigest())


def load(name, directory=HERE):
    if PINS is None:
        raise RuntimeError('COLD_SOURCE_FREEZE_REQUIRED')
    path = directory / name
    raw = path.read_bytes()
    if pin(raw) != PINS[name]:
        raise RuntimeError('COLD_FIXED_SOURCE_IDENTITY')
    module = types.ModuleType('cold_' + name.replace('.', '_'))
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec', dont_inherit=True), module.__dict__)
    return module


R = load('run_relink.py')


class LoaderContract(unittest.TestCase):
    def test_own_loader_checks_size_before_compile(self):
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            root = Path(folder)
            (root / 'run_relink.py').write_bytes(b'raise RuntimeError("MUST_NOT_COMPILE")\n')
            with mock.patch.object(builtins, 'compile', side_effect=AssertionError('compiled unpinned bytes')) as compiler:
                with self.assertRaisesRegex(RuntimeError, 'COLD_FIXED_SOURCE_IDENTITY'):
                    load('run_relink.py', root)
                compiler.assert_not_called()

    def test_own_loader_checks_same_size_hash_before_compile(self):
        raw = (HERE / 'run_relink.py').read_bytes()
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            root = Path(folder)
            mutated = bytes([raw[0] ^ 1]) + raw[1:]
            self.assertEqual(len(mutated), len(raw))
            (root / 'run_relink.py').write_bytes(mutated)
            with mock.patch.object(builtins, 'compile', side_effect=AssertionError('compiled unpinned bytes')) as compiler:
                with self.assertRaisesRegex(RuntimeError, 'COLD_FIXED_SOURCE_IDENTITY'):
                    load('run_relink.py', root)
                compiler.assert_not_called()

    def test_loaded_source_has_no_top_level_run(self):
        raw = (HERE / 'run_relink.py').read_bytes()
        self.assertEqual(pin(raw), PINS['run_relink.py'])
        tree = ast.parse(raw)
        for node in tree.body:
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                self.assertNotEqual(getattr(node.value.func, 'id', ''), 'run')

    def test_plain_asserts_are_not_contract_guards(self):
        raw = (HERE / 'run_relink.py').read_bytes()
        self.assertEqual(pin(raw), PINS['run_relink.py'])
        self.assertFalse(any(isinstance(node, ast.Assert) for node in ast.walk(ast.parse(raw))))


class InputBuffers(unittest.TestCase):
    def setUp(self):
        self.source, self.repo, self.old = Path('/fixed/source'), Path('/fixed/repo'), Path('/fixed/old')
        self.production = {'files': {f'bridge/include/f{i}.hpp': R.identity(f'source{i}'.encode()) for i in range(27)}}
        self.production['files']['bridge/source/pc01_main.cpp'] = R.identity(b'main')
        self.original = {'sources': {f'original/f{i}': R.identity(f'origin{i}'.encode()) for i in range(44)}}
        self.reuse = {'old_work_readonly': str(self.old), 'files': {f'host_execution/obj/f{i}.h': R.identity(f'cache{i}'.encode()) for i in range(18)},
                      'original_build_log': {'path': 'log', **R.identity(b'log')},
                      'original_dependency_receipt': {'path': 'receipt', **R.identity(b'receipt')}}
        self.archive = 'host_execution/obj/VHostBlockTop__ALL.a'
        self.reuse['files'][self.archive] = R.identity(b'!<arch>\nregular payload')
        self.data = {self.source/f'bridge/include/f{i}.hpp': f'source{i}'.encode() for i in range(27)}
        self.data[self.source/'bridge/source/pc01_main.cpp'] = b'main'
        self.data.update({self.repo/f'original/f{i}': f'origin{i}'.encode() for i in range(44)})
        self.data.update({self.old/f'host_execution/obj/f{i}.h': f'cache{i}'.encode() for i in range(18)})
        self.data.update({self.old/self.archive: b'!<arch>\nregular payload', self.old/'log': b'log', self.old/'receipt': b'receipt'})
        self.checked_calls = []
        def checked(path, expected, cap=None, **kwargs):
            self.checked_calls.append((path, expected, cap, kwargs))
            data = self.data[path]
            if R.identity(data) != expected:
                raise ValueError('MOCK_FIXED_IDENTITY')
            return data
        self.g = types.SimpleNamespace(checked=checked, clean=Path)
        def read(path, expected):
            if path == self.source/'PRODUCTION_MANIFEST.json':
                self.assertEqual(expected, R.PRODUCTION_PIN); return json.dumps(self.production).encode()
            if path == self.source/'SOURCE_PINS.json':
                self.assertEqual(expected, R.ORIGINAL_PINS); return json.dumps(self.original).encode()
            raise AssertionError(path)
        self.reader = mock.patch.object(R, 'read', side_effect=read)
        self.reader.start(); self.addCleanup(self.reader.stop)

    def go(self): return R.input_buffers(self.g, self.repo, self.source, self.reuse)

    def test_exact_counts_and_all_inputs_checked(self):
        values = self.go()
        self.assertEqual(len(values), 47)
        self.assertEqual(sum(k.startswith('source/') for k in values), 28)
        self.assertEqual(sum(k.startswith('cache/') for k in values), 19)
        self.assertEqual(len(self.checked_calls), 44 + 28 + 19 + 2)
        for key, value in values.items():
            origin = self.source/key.removeprefix('source/') if key.startswith('source/') else self.old/key.removeprefix('cache/')
            self.assertIs(value, self.data[origin])

    def test_missing_source_rejected(self):
        self.production['files'].pop('bridge/include/f0.hpp')
        with self.assertRaisesRegex(ValueError, 'FIXED_SOURCE_COUNTS'): self.go()
        self.assertEqual(self.checked_calls, [])

    def test_extra_source_rejected(self):
        self.production['files']['bridge/include/extra.hpp'] = R.identity(b'extra')
        with self.assertRaisesRegex(ValueError, 'FIXED_SOURCE_COUNTS'): self.go()

    def test_missing_original_pin_rejected(self):
        self.original['sources'].pop('original/f0')
        with self.assertRaisesRegex(ValueError, 'FIXED_SOURCE_COUNTS'): self.go()

    def test_missing_cache_pin_rejected(self):
        self.reuse['files'].pop('host_execution/obj/f0.h')
        with self.assertRaisesRegex(ValueError, 'FIXED_SOURCE_COUNTS'): self.go()

    def test_source_path_traversal_rejected(self):
        self.production['files']['bridge/../outside'] = self.production['files'].pop('bridge/include/f0.hpp')
        with self.assertRaisesRegex(ValueError, 'FIXED_SOURCE_RELATIVE'): self.go()

    def test_cache_absolute_path_rejected(self):
        self.reuse['files']['/absolute'] = self.reuse['files'].pop('host_execution/obj/f0.h')
        with self.assertRaisesRegex(ValueError, 'FIXED_CACHE_RELATIVE'): self.go()

    def test_cache_parent_traversal_rejected(self):
        self.reuse['files']['../outside'] = self.reuse['files'].pop('host_execution/obj/f0.h')
        with self.assertRaisesRegex(ValueError, 'FIXED_CACHE_RELATIVE'): self.go()

    def test_same_length_source_drift_rejected(self):
        self.data[self.source/'bridge/source/pc01_main.cpp'] = b'evil'
        with self.assertRaisesRegex(ValueError, 'MOCK_FIXED_IDENTITY'): self.go()

    def test_same_length_cache_drift_rejected(self):
        self.data[self.old/'host_execution/obj/f0.h'] = b'evil00'
        with self.assertRaisesRegex(ValueError, 'MOCK_FIXED_IDENTITY'): self.go()

    def test_original_source_drift_rejected(self):
        self.data[self.repo/'original/f0'] = b'changed'
        with self.assertRaisesRegex(ValueError, 'MOCK_FIXED_IDENTITY'): self.go()

    def test_old_dependency_receipt_drift_rejected(self):
        self.data[self.old/'receipt'] = b'changed'
        with self.assertRaisesRegex(ValueError, 'MOCK_FIXED_IDENTITY'): self.go()

    def test_thin_archive_rejected_even_with_matching_pin(self):
        raw = b'!<thin>\nexternal members'
        self.data[self.old/self.archive] = raw
        self.reuse['files'][self.archive] = R.identity(raw)
        with self.assertRaisesRegex(ValueError, 'REGULAR_NOT_THIN_ARCHIVE'): self.go()

    def test_nonarchive_rejected_even_with_matching_pin(self):
        raw = b'not an archive'
        self.data[self.old/self.archive] = raw
        self.reuse['files'][self.archive] = R.identity(raw)
        with self.assertRaisesRegex(ValueError, 'REGULAR_NOT_THIN_ARCHIVE'): self.go()


class StageAndLoader(unittest.TestCase):
    def test_write_exact_exclusive_same_buffer(self):
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            path = Path(folder)/'fresh'/'copy'
            raw = b'fixed checked byte buffer\x00\xff'
            R.write_exact(path, raw)
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError): R.write_exact(path, b'replacement')
            self.assertEqual(path.read_bytes(), raw)

    def test_write_exact_rejects_parent_symlink(self):
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            root = Path(folder); (root/'actual').mkdir(); (root/'alias').symlink_to(root/'actual')
            with self.assertRaisesRegex(ValueError, 'STAGE_PATH'): R.write_exact(root/'alias'/'file', b'x')
            self.assertFalse((root/'actual'/'file').exists())

    def test_write_exact_handles_partial_writes(self):
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            path = Path(folder)/'partial'; original = os.write
            with mock.patch.object(R.os, 'write', side_effect=lambda fd, raw: original(fd, raw[:2])):
                R.write_exact(path, b'abcdefg')
            self.assertEqual(path.read_bytes(), b'abcdefg')

    def test_write_zero_fails_closed(self):
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            with mock.patch.object(R.os, 'write', return_value=0):
                with self.assertRaisesRegex(ValueError, 'STAGE_WRITE'):
                    R.write_exact(Path(folder)/'zero', b'x')

    def test_verify_copies_same_bytes_and_identity(self):
        calls = []
        buffers = {'source/a': b'one', 'cache/b': b'two'}
        def checked(path, expected, cap, **kw):
            rel = path.relative_to('/work').as_posix(); raw = buffers[rel]
            self.assertEqual(expected, R.identity(raw)); self.assertEqual(cap, 32*R.MIB)
            calls.append(rel); return raw
        R.verify_copies(types.SimpleNamespace(checked=checked), Path('/work'), buffers)
        self.assertEqual(calls, list(buffers))

    def test_verify_copies_rejects_changed_return_buffer(self):
        g = types.SimpleNamespace(checked=lambda *a, **k: b'changed')
        with self.assertRaisesRegex(ValueError, 'STAGED_BYTES_CHANGED'):
            R.verify_copies(g, Path('/work'), {'source/a': b'fixed'})

    def test_module_checked_buffer_used_once(self):
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            path = Path(folder)/'module.py'; raw = b'value = 73\n'; path.write_bytes(raw)
            original = builtins.compile; calls = []
            def compile_buffer(data, *args, **kwargs):
                calls.append(data)
                path.write_bytes(b'value = 99\n')
                return original(data, *args, **kwargs)
            with mock.patch.object(builtins, 'compile', side_effect=compile_buffer):
                module = R.module(path, pin(raw), 'same_checked_buffer')
            self.assertEqual(module.value, 73); self.assertEqual(calls, [raw])

    def test_module_size_and_hash_rejected_before_compile(self):
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            path = Path(folder)/'module.py'; raw = b'value = 73\n'
            for changed in (b'x', raw+b'\n', b'value = 74\n'):
                path.write_bytes(changed)
                with mock.patch.object(builtins, 'compile', side_effect=AssertionError('compiled changed source')) as compiler:
                    with self.assertRaises(ValueError): R.module(path, pin(raw), 'rejected')
                    compiler.assert_not_called()

    def test_module_symlink_rejected_before_compile(self):
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            root = Path(folder); path = root/'module.py'; raw=b'value = 73\n'; path.write_bytes(raw)
            (root/'alias.py').symlink_to(path)
            with mock.patch.object(builtins, 'compile', side_effect=AssertionError('compiled symlink')) as compiler:
                with self.assertRaisesRegex(ValueError, 'SOURCE_CANONICAL'): R.module(root/'alias.py', pin(raw), 'rejected')
                compiler.assert_not_called()


class Resources(unittest.TestCase):
    def go(self, mem=8*1024**3, disk=3*1024**3):
        with mock.patch.object(Path, 'read_text', return_value=f'MemAvailable: {mem//1024} kB\n'), mock.patch.object(R.os, 'statvfs', return_value=types.SimpleNamespace(f_bavail=disk, f_frsize=1)):
            return R.resource_gate(Path('/work'))
    def test_exact_resource_boundary(self):
        self.assertEqual(self.go(), {'mem_available_bytes': 8*1024**3, 'disk_available_bytes': 3*1024**3})
    def test_memory_under_gate(self):
        with self.assertRaisesRegex(ValueError, 'MEM_AVAILABLE_8G'): self.go(mem=8*1024**3-1024)
    def test_disk_under_gate(self):
        with self.assertRaisesRegex(ValueError, 'DISK_AVAILABLE_3G'): self.go(disk=3*1024**3-1)
    def test_duplicate_meminfo_rejected(self):
        with mock.patch.object(Path, 'read_text', return_value='MemAvailable: 999999999 kB\nMemAvailable: 999999999 kB\n'):
            with self.assertRaisesRegex(ValueError, 'MEM_AVAILABLE_8G'): R.resource_gate(Path('/work'))


class Sequence(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=HERE); self.addCleanup(self.folder.cleanup)
        self.work = Path(self.folder.name)
        self.calls, self.result = [], {'stages': [], 'rtl_executed': False, 'pc01_executable_invoked': False}
        self.argv = {'compile': ['/fixed/g++', '-B', '/search/', '-c', '/source/pc01_main.cpp'], 'link': ['/fixed/g++', '-B', '/search/', '/work/pc01_main.o', '-o', '/work/pc01']}
        self.env = {'PATH': '/search', 'LANG': 'C'}
        self.owner = {'deadline': 180, 'handler': object()}
        self.preflight = mock.Mock()
        self.binary = mock.Mock(return_value={'identity': 'fixed-binary'})
        self.behavior = {}
        self.clock = mock.patch.object(R.time, 'monotonic', return_value=0); self.clock.start(); self.addCleanup(self.clock.stop)
        self.resources = mock.patch.object(R, 'resource_gate', return_value={}); self.resources.start(); self.addCleanup(self.resources.stop)
        data = bytearray(64); data[:4] = b'\x7fELF'; data[16:18] = (1).to_bytes(2, 'little'); self.object = bytes(data)
        def phase(*args):
            self.calls.append(args); name=args[2].removeprefix('pc01_driver_')
            value=self.behavior.get(name)
            if isinstance(value, BaseException): raise value
            if name == 'compile': (self.work/'pc01_main.o').write_bytes(self.object)
            return value or ({'exit_code': 0, 'cleanup_confirmed': True}, '{}', {'maxrss_kib_cumulative_parent_children': 4096})
        self.supervisor = types.SimpleNamespace(run_phase=phase)
    def go(self, stop=180):
        return R.supervised_sequence(self.supervisor, 'support', 'base', self.work, self.argv, self.env, stop, self.owner, self.preflight, self.binary, self.result)
    def bad(self, name, **values):
        record={'exit_code':0, 'cleanup_confirmed':True}; record.update(values)
        self.behavior[name]=(record, '{}', {'maxrss_kib_cumulative_parent_children':4096})
    def test_exact_two_phases_and_never_binary_invocation(self):
        self.assertEqual(self.go(), {'identity':'fixed-binary'})
        self.assertEqual([a[2] for a in self.calls], ['pc01_driver_compile','pc01_driver_link'])
        self.assertEqual([a[3] for a in self.calls], [self.argv['compile'],self.argv['link']])
        self.assertTrue(all(a[3][0]=='/fixed/g++' for a in self.calls))
        self.assertFalse(self.result['rtl_executed']); self.assertFalse(self.result['pc01_executable_invoked'])
        self.assertEqual(self.preflight.call_count, 4); self.assertEqual(self.binary.call_count, 2)
    def test_same_owner_deadline_env(self):
        self.go()
        for args in self.calls:
            self.assertIs(args[6],self.env); self.assertEqual(args[8],180); self.assertIs(args[9],self.owner)
    def test_finite_phase_limits(self):
        self.go()
        self.assertEqual([(a[7]['total_seconds'],a[7]['work_seconds'],a[7]['cpu_seconds']) for a in self.calls],[(95,80,80),(25,10,10)])
        self.assertEqual(sum(a[7]['total_seconds'] for a in self.calls),120)
        for args in self.calls:
            self.assertEqual(args[7]['as_bytes'],6*1024**3)
            self.assertEqual(args[7]['fsize_bytes'],64*R.MIB)
            self.assertEqual(args[7]['log_bytes'],R.MIB)
    def test_compile_exception_stops_before_link_preserves_first(self):
        error=RuntimeError('compile first'); self.behavior['compile']=error
        with self.assertRaises(RuntimeError) as caught: self.go()
        self.assertIs(caught.exception,error); self.assertEqual(len(self.calls),1); self.assertEqual(len(self.result['stages']),1)
        self.binary.assert_not_called()
    def test_compile_nonzero_stops_before_link(self):
        self.bad('compile',exit_code=7)
        with self.assertRaisesRegex(ValueError,'PHASE_EXIT_OR_CLEANUP'): self.go()
        self.assertEqual(len(self.calls),1); self.assertEqual(self.result['stages'][0]['record']['exit_code'],7)
    def test_compile_boolean_exit_rejected(self):
        self.bad('compile',exit_code=False)
        with self.assertRaisesRegex(ValueError,'PHASE_EXIT_OR_CLEANUP'): self.go()
        self.assertEqual(len(self.calls),1)
    def test_compile_cleanup_false_stops_before_link(self):
        self.bad('compile',cleanup_confirmed=False)
        with self.assertRaisesRegex(ValueError,'PHASE_EXIT_OR_CLEANUP'): self.go()
        self.assertEqual(len(self.calls),1)
    def test_compile_object_must_be_relocatable(self):
        self.object=b'not-elf'+b'\0'*64
        with self.assertRaisesRegex(ValueError,'COMPILE_RELOCATABLE_ELF'): self.go()
        self.assertEqual(len(self.calls),1)
    def test_compile_object_empty_rejected(self):
        self.object=b''
        with self.assertRaisesRegex(ValueError,'COMPILE_OBJECT'): self.go()
        self.assertEqual(len(self.calls),1)
    def test_source_preflight_failure_stops_before_any_child(self):
        self.preflight.side_effect=ValueError('source drift')
        with self.assertRaisesRegex(ValueError,'source drift'): self.go()
        self.assertEqual(self.calls,[])
    def test_dependency_postflight_failure_stops_before_link(self):
        self.preflight.side_effect=[None,ValueError('dependency drift')]
        with self.assertRaisesRegex(ValueError,'dependency drift'): self.go()
        self.assertEqual(len(self.calls),1)
    def test_object_postflight_drift_stops_before_link(self):
        def before():
            if self.calls: (self.work/'pc01_main.o').write_bytes(b'changed')
        self.preflight.side_effect=before
        with self.assertRaisesRegex(ValueError,'OBJECT_CHANGED_POSTFLIGHT'): self.go()
        self.assertEqual(len(self.calls),1)
    def test_link_failure_has_no_complete_binary(self):
        error=RuntimeError('link'); self.behavior['link']=error
        with self.assertRaises(RuntimeError) as caught: self.go()
        self.assertIs(caught.exception,error); self.assertEqual(len(self.calls),2)
        self.assertNotIn('binary',self.result)
    def test_binary_postflight_drift_rejected(self):
        self.binary.side_effect=[{'identity':'fixed'},{'identity':'changed'}]
        with self.assertRaisesRegex(ValueError,'BINARY_CHANGED_POSTFLIGHT'): self.go()
        self.assertEqual(len(self.calls),2)
    def test_compile_window_tail_reserved(self):
        with self.assertRaisesRegex(ValueError,'INCOMPLETE_PHASE_WINDOW'): self.go(124)
        self.assertEqual(self.calls,[])
    def test_front_drift_rechecked_before_child(self):
        R.time.monotonic.side_effect=[0,56]
        with self.assertRaisesRegex(ValueError,'INCOMPLETE_PHASE_WINDOW'): self.go()
        self.assertEqual(self.calls,[])
    def test_link_window_tail_reserved(self):
        R.time.monotonic.side_effect=[0,0,126]
        with self.assertRaisesRegex(ValueError,'INCOMPLETE_PHASE_WINDOW'): self.go()
        self.assertEqual(len(self.calls),1)
    def test_exact_link_window_boundary(self):
        R.time.monotonic.side_effect=[0,0,125,125]
        self.go(); self.assertEqual(len(self.calls),2)

H = load('reference_helpers.py')
E = load('launch.py')
D = load('dependency_gate.py')
CONTRACT_RAW = (HERE/'RELINK_CONTRACT.json').read_bytes()
if pin(CONTRACT_RAW) != (3446, '6e35a033308211c65da7f8d0c647e287338599362dc85851c961f8b522de82b7'):
    raise RuntimeError('COLD_COMMAND_CONTRACT_IDENTITY')
CONTRACT = json.loads(CONTRACT_RAW)


class CommandsAndEnvironment(unittest.TestCase):
    def setUp(self):
        self.catalog={'programs':{'g++':'/fixed/usr/g++'},'libraries':{'libc.so.6':'/fixed/lib/libc.so.6','libatomic.so.1':'/fixed/lib/libatomic.so.1'}}
        self.work=Path('/fresh/work')
    def test_exact_compile_argv(self):
        actual=R.commands(self.catalog,self.work,CONTRACT)['compile']
        flags=['-MMD','-DVERILATOR=1','-DVM_COVERAGE=0','-DVM_SC=0','-DVM_TIMING=0','-DVM_TRACE=0','-DVM_TRACE_FST=0','-DVM_TRACE_VCD=0','-DVM_TRACE_SAIF=0','-DVM_VPI=0','-faligned-new','-fcf-protection=none','-Wno-bool-operation','-Wno-int-in-bool-context','-Wno-shadow','-Wno-sign-compare','-Wno-subobject-linkage','-Wno-tautological-compare','-Wno-uninitialized','-Wno-unused-but-set-parameter','-Wno-unused-but-set-variable','-Wno-unused-parameter','-Wno-unused-variable','-DVM_PREFIX_INCLUDE=<VHostBlockTop.h>','-DVM_PREFIX_INCLUDE_DPI=<VHostBlockTop__Dpi.h>','-std=c++17','-O0']
        expected=['/fixed/usr/g++','-B','/fresh/work/compiler-search/',*flags,
            '-I','/fresh/work/source/bridge/include','-I','/fresh/work/cache/host_execution/obj',
            '-I','/fresh/work/cache/toolchain/verilator/include','-I','/fresh/work/cache/toolchain/verilator/include/vltstd',
            '-c','/fresh/work/source/bridge/source/pc01_main.cpp','-o','/fresh/work/pc01_main.o']
        self.assertEqual(actual,expected)
    def test_exact_link_argv(self):
        actual=R.commands(self.catalog,self.work,CONTRACT)['link']
        self.assertEqual(actual,['/fixed/usr/g++','-B','/fresh/work/compiler-search/',
            '/fresh/work/pc01_main.o','/fresh/work/cache/host_execution/obj/verilated.o',
            '/fresh/work/cache/host_execution/obj/verilated_dpi.o','/fresh/work/cache/host_execution/obj/verilated_threads.o',
            '/fresh/work/cache/host_execution/obj/VHostBlockTop__ALL.a','-pthread','-lpthread','-latomic','-o','/fresh/work/pc01'])
    def test_unknown_placeholder_rejected(self):
        contract=copy.deepcopy(CONTRACT); contract['compile_command_template'].append('FIXED_UNBOUND')
        with self.assertRaisesRegex(ValueError,'FIXED_ARGV_MAPPING'): R.commands(self.catalog,self.work,contract)
    def test_wrong_compiler_template_rejected(self):
        contract=copy.deepcopy(CONTRACT); contract['compile_command_template'][0]='/unexpected/cxx'
        with self.assertRaisesRegex(ValueError,'FIXED_ARGV_MAPPING'): R.commands(self.catalog,self.work,contract)
    def test_fixed_environment_excludes_parent_overrides(self):
        with mock.patch.dict(os.environ,{'PATH':'/hostile','LD_PRELOAD':'/evil.so','CPATH':'/inject','CXX':'/evil','GCC_EXEC_PREFIX':'/evil'}):
            actual=R.environment(self.catalog,self.work)
        self.assertEqual(actual,{'PATH':'/fresh/work/compiler-search','LD_LIBRARY_PATH':'/fixed/lib','HOME':'/fresh/work/home','TMPDIR':'/fresh/work/tmp','LC_ALL':'C','LANG':'C','TZ':'UTC'})
    def test_multiple_library_directories_rejected(self):
        self.catalog['libraries']['new.so']='/other/new.so'
        with self.assertRaisesRegex(ValueError,'FIXED_LIBRARY_DIRECTORY'): R.environment(self.catalog,self.work)


class SourceEntry(unittest.TestCase):
    def test_entry_caller_pin_matches_frozen_source(self):
        self.assertEqual(E.CALLER_PIN,PINS['run_relink.py'])
    def test_checked_returns_exact_buffer(self):
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            p=Path(folder)/'source.py'; raw=b'value = 37\n'; p.write_bytes(raw)
            self.assertEqual(E.checked(p,pin(raw)),raw)
    def test_entry_same_size_short_long_mutation_rejected_before_compile(self):
        source=(HERE/'run_relink.py').read_bytes()
        for changed in (bytes([source[0]^1])+source[1:],source[:-1],source+b'\n'):
            with self.subTest(bytes=len(changed)), tempfile.TemporaryDirectory(dir=HERE) as folder:
                root=Path(folder); (root/'run_relink.py').write_bytes(changed)
                with mock.patch.object(E,'__file__',str(root/'launch.py')), mock.patch.object(E.time,'monotonic',return_value=1.0), mock.patch.object(builtins,'compile',side_effect=AssertionError('compiled changed entry')) as compiler:
                    with self.assertRaisesRegex(ValueError,'ENTRY_(SIZE|HASH_OR_DRIFT)'): E.main([],started=1.0)
                    compiler.assert_not_called()
    def test_entry_symlink_rejected_before_compile(self):
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            root=Path(folder); (root/'run_relink.py').symlink_to(HERE/'run_relink.py')
            with mock.patch.object(E,'__file__',str(root/'launch.py')), mock.patch.object(E.time,'monotonic',return_value=1.0), mock.patch.object(builtins,'compile',side_effect=AssertionError('compiled symlink')) as compiler:
                with self.assertRaisesRegex(ValueError,'ENTRY_CANONICAL'): E.main([],started=1.0)
                compiler.assert_not_called()
    def test_entry_exact_checked_buffer_used_and_no_execution_flag(self):
        source=(HERE/'run_relink.py').read_bytes(); seen=[]; original=builtins.compile
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            root=Path(folder); p=root/'run_relink.py'; p.write_bytes(source)
            def compile_buffer(raw,*args,**kwargs):
                seen.append(raw); p.write_bytes(b'mutated after checked read'); return original(raw,*args,**kwargs)
            with mock.patch.object(E,'__file__',str(root/'launch.py')), mock.patch.object(E.time,'monotonic',return_value=1.0), mock.patch.object(builtins,'compile',side_effect=compile_buffer), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises((ValueError,SystemExit)):
                    E.main(['--private-config','/unused'],started=1.0)
            self.assertEqual(seen,[source])
    def test_entry_stale_t0_rejected_before_compile(self):
        with mock.patch.object(E.time,'monotonic',return_value=31.0),mock.patch.object(builtins,'compile') as compiler:
            with self.assertRaisesRegex(ValueError,'ENTRY_T0'): E.main([],started=1.0)
            compiler.assert_not_called()
    def test_caller_requires_explicit_flag(self):
        with self.assertRaisesRegex(ValueError,'EXPLICIT_RELINK_AND_ISOLATION_REQUIRED'): R.run(Path('/unused'),False)
    def test_caller_requires_entry_t0(self):
        with self.assertRaisesRegex(ValueError,'ENTRY_T0_REQUIRED'): R.run(Path('/unused'),True)
    def test_audit_blocks_native_and_network_events(self):
        for name in ('subprocess.Popen','socket.connect','os.system','os.exec','os.posix_spawn','ctypes.dlopen'):
            with self.subTest(event=name),self.assertRaisesRegex(RuntimeError,'COLD_NATIVE_NETWORK_FORBIDDEN'): sys.audit(name)


class FailurePrecedence(unittest.TestCase):
    def test_first_failure_survives_receipt_failure(self):
        first=ValueError('compile'); second=OSError('receipt')
        with mock.patch.object(H,'write_result',side_effect=second):
            self.assertIs(H.save_preserving_failure(Path('/fake'),{},first),first)
    def test_receipt_failure_is_reported_without_prior_failure(self):
        second=OSError('receipt')
        with mock.patch.object(H,'write_result',side_effect=second):
            self.assertIs(H.save_preserving_failure(Path('/fake'),{},None),second)
    def test_restore_failure_does_not_mask_first(self):
        first=ValueError('first')
        with mock.patch.object(H.signal,'setitimer',side_effect=OSError('timer')),mock.patch.object(H.signal,'signal',side_effect=OSError('handler')):
            self.assertIs(H.restore_preserving_failure('old',first),first)
    def test_restore_first_failure_retained(self):
        first=OSError('timer')
        with mock.patch.object(H.signal,'setitimer',side_effect=first),mock.patch.object(H.signal,'signal',side_effect=OSError('handler')):
            self.assertIs(H.restore_preserving_failure('old',None),first)
    def test_no_work_no_receipt(self):
        with mock.patch.object(H,'write_result') as writer:
            self.assertIsNone(H.save_preserving_failure(None,{},None)); writer.assert_not_called()

class FullRun(unittest.TestCase):
    def setUp(self):
        self.stack=contextlib.ExitStack(); self.addCleanup(self.stack.close)
        self.folder=self.stack.enter_context(tempfile.TemporaryDirectory(dir=HERE)); self.root=Path(self.folder)
        self.work=self.root/'work'; self.repo=self.root/'repo'; self.source=self.root/'source'; self.old=self.root/'old'; self.bdir=self.root/'binding_source'
        self.config=self.root/'config.json'; self.reads=[]; self.calls=[]; self.phase_failure=None; self.after_phase=None
        self.programs={name:str(self.root/'tools'/name) for name in ('g++','cc1plus','collect2','as','ld')}
        (self.root/'tools').mkdir()
        for path in self.programs.values(): Path(path).write_bytes(b'non-executable synthetic fixture')
        cxx={'bytes':1,'sha256':'a'*64,'mode':'0755'}
        self.catalog={'files':{str(self.root/'file'/str(i)):{} for i in range(38)},'programs':self.programs,'libraries':{'libc.so.6':str(self.root/'lib/libc.so.6')}}
        self.catalog['files'][self.programs['g++']]=cxx
        self.binding={'system_programs':{'/usr/bin/g++':{'path':self.programs['g++'],**cxx},'/usr/bin/python3':{'path':str(Path(sys.executable).resolve(strict=True))}}}
        self.cfg={'schema':'PC01_RELINK_PRIVATE_BINDING_V1','repo':str(self.repo),'source':str(self.source),'work':str(self.work),
            'binding_source':str(self.bdir),'binding':{'path':str(self.root/'binding.json'),'identity':R.identity(b'binding')},
            'profile':{'path':str(self.root/'profile.json'),'identity':R.identity(b'{}')},
            'dependencies':str(self.root/'dependencies.json'),'reuse_binding':str(self.root/'reuse.json')}
        self.reuse={'old_work_readonly':str(self.old)}
        self.read_map={self.config:json.dumps(self.cfg).encode(),Path(self.cfg['dependencies']):json.dumps(self.catalog).encode(),
            Path(self.cfg['reuse_binding']):json.dumps(self.reuse).encode(),self.source/'RELINK_CONTRACT.json':CONTRACT_RAW,
            Path(R.__file__).resolve():(HERE/'run_relink.py').read_bytes()}
        self.buffers={f'source/bridge/include/f{i}.hpp':f'source {i}'.encode() for i in range(28)}
        self.buffers.update({f'cache/obj/f{i}':f'cache {i}'.encode() for i in range(19)})
        def read(path,expected):
            self.reads.append((path,expected)); return self.read_map.get(path,b'fixed helper source')
        self.reader=self.stack.enter_context(mock.patch.object(R,'read',side_effect=read))
        def checked(path,expected,*args,**kwargs):
            if path==Path(self.cfg['binding']['path']): raw=b'binding'
            elif path==Path(self.cfg['profile']['path']): raw=b'{}'
            else: raw=path.read_bytes()
            if R.identity(raw)!=expected: raise ValueError('MOCK_PIN_DRIFT')
            return raw
        self.g=types.SimpleNamespace(checked=checked,clean=Path,binding=lambda *a:self.binding,decode=json.loads)
        self.l=types.SimpleNamespace(validate=mock.Mock())
        self.d=types.SimpleNamespace(verify=mock.Mock(return_value={'stable':True}),check_binary=mock.Mock(return_value={'identity':'binary'}))
        self.support=types.SimpleNamespace(fresh_directory=lambda path:path.mkdir())
        data=bytearray(64); data[:4]=b'\x7fELF'; data[16:18]=(1).to_bytes(2,'little'); self.object=bytes(data)
        def phase(*args):
            self.calls.append(args)
            if self.phase_failure is not None: raise self.phase_failure
            if args[2]=='pc01_driver_compile': (self.work/'pc01_main.o').write_bytes(self.object)
            if self.after_phase: self.after_phase(args[2])
            return {'exit_code':0,'cleanup_confirmed':True},'{}',{'maxrss_kib_cumulative_parent_children':4096}
        self.s=types.SimpleNamespace(fixed_support=lambda repo:(self.support,'base',{}),run_phase=phase)
        modules={'relink_bootstrap':self.g,'relink_observer':object(),'relink_mount':self.l,'relink_supervisor':self.s}
        self.stack.enter_context(mock.patch.object(H,'module',side_effect=lambda path,pin,name:modules[name]))
        self.stack.enter_context(mock.patch.object(R,'module',side_effect=lambda path,pin,name:H if name=='fixed_reference_execution_helpers' else self.d))
        self.input_mock=self.stack.enter_context(mock.patch.object(R,'input_buffers',side_effect=lambda *a:dict(self.buffers)))
        self.stack.enter_context(mock.patch.object(R,'resource_gate',return_value={'mem_available_bytes':8*1024**3,'disk_available_bytes':3*1024**3}))
        self.stack.enter_context(mock.patch.object(R.time,'monotonic',return_value=1.0))
        self.stack.enter_context(mock.patch.object(R.signal,'getitimer',return_value=(0.0,0.0)))
        self.stack.enter_context(mock.patch.object(R.signal,'pthread_sigmask',return_value=set()))
        self.stack.enter_context(mock.patch.object(R.signal,'getsignal',return_value='old_handler'))
        self.sig=self.stack.enter_context(mock.patch.object(R.signal,'signal'))
        self.timer=self.stack.enter_context(mock.patch.object(R.signal,'setitimer'))
        self.stack.enter_context(mock.patch.object(R.resource,'getrlimit',return_value=(R.resource.RLIM_INFINITY,R.resource.RLIM_INFINITY)))
        self.limits=self.stack.enter_context(mock.patch.object(R.resource,'setrlimit'))
        self.stack.enter_context(mock.patch.object(R.os,'sched_getaffinity',return_value={3,7}))
        self.affinity=self.stack.enter_context(mock.patch.object(R.os,'sched_setaffinity'))
    def go(self): return R.run(self.config,True,started=1.0,source_pin=PINS['run_relink.py'])
    def receipt(self): return json.loads((self.work/'EXECUTION_RESULT.json').read_bytes())
    def test_complete_end_to_end_pure_mock(self):
        result=self.go()
        self.assertEqual(result['status'],'COMPLETE_DRIVER_COMPILE_LINK_ONLY')
        self.assertEqual(len(result['staged_files']),47)
        self.assertFalse(result['rtl_executed']); self.assertFalse(result['pc01_executable_invoked']); self.assertFalse(result['full_block_pass'])
        self.assertEqual(result,self.receipt())
        self.assertEqual([x[2] for x in self.calls],['pc01_driver_compile','pc01_driver_link'])
        self.assertTrue(all(x[3][0]==self.programs['g++'] for x in self.calls))
        self.affinity.assert_called_once_with(0,{3})
        self.assertEqual(self.sig.call_args.args,(signal.SIGALRM,'old_handler'))
        self.assertEqual(self.timer.call_args.args,(signal.ITIMER_REAL,0))
        self.assertEqual(len(self.limits.call_args_list),3)
    def test_exact_checked_buffers_staged(self):
        writer=R.write_exact; writes=[]
        def observe(path,raw): writes.append((path,raw)); return writer(path,raw)
        with mock.patch.object(R,'write_exact',side_effect=observe): result=self.go()
        self.assertEqual(len(writes),47)
        for path,raw in writes:
            rel=path.relative_to(self.work).as_posix()
            self.assertIs(raw,self.buffers[rel]); self.assertEqual(path.read_bytes(),raw)
            self.assertEqual(result['staged_files'][rel],R.identity(raw))
    def test_fixed_env_reaches_both_phases(self):
        with mock.patch.dict(os.environ,{'LD_PRELOAD':'/hostile','PATH':'/hostile','CXX':'bad'}): self.go()
        expected=R.environment(self.catalog,self.work)
        for call in self.calls: self.assertEqual(call[6],expected)
    def test_original_helper_sources_rechecked(self):
        self.go(); paths=[path.name for path,pin_value in self.reads]
        for name in ('run_relink.py','run_reference.py','dependency_gate.py','bootstrap.py','binding_observer.py','local_mount_profile.py','ci_support_v3.py'):
            self.assertGreaterEqual(paths.count(name),5)
    def test_original_source_drift_stops_after_compile(self):
        self.after_phase=lambda phase:self.buffers.update({'source/bridge/include/f0.hpp':b'drift'})
        with self.assertRaisesRegex(ValueError,'ORIGINAL_SOURCE_OR_CACHE_CHANGED'): self.go()
        self.assertEqual(len(self.calls),1); self.assertEqual(self.receipt()['status'],'INCOMPLETE')
    def test_compiler_dependency_drift_stops_after_compile(self):
        self.d.verify.side_effect=[{'stable':True},{'stable':True},{'stable':False}]
        with self.assertRaisesRegex(ValueError,'DEPENDENCY_CHANGED'): self.go()
        self.assertEqual(len(self.calls),1)
    def test_staged_copy_drift_stops_after_compile(self):
        self.after_phase=lambda phase:(self.work/'source/bridge/include/f0.hpp').write_bytes(b'drift')
        with self.assertRaisesRegex(ValueError,'MOCK_PIN_DRIFT'): self.go()
        self.assertEqual(len(self.calls),1)
    def test_caller_source_drift_stops_after_compile(self):
        self.after_phase=lambda phase:self.read_map.update({Path(R.__file__).resolve():b'changed'})
        with self.assertRaisesRegex(ValueError,'CALLER_SOURCE_CHANGED'): self.go()
        self.assertEqual(len(self.calls),1)
    def test_compile_first_failure_survives_receipt_failure(self):
        first=RuntimeError('first compile'); self.phase_failure=first
        with mock.patch.object(H,'write_result',side_effect=OSError('receipt')):
            with self.assertRaises(RuntimeError) as caught:self.go()
        self.assertIs(caught.exception,first); self.assertEqual(len(self.calls),1)
        self.assertEqual(self.timer.call_args.args,(signal.ITIMER_REAL,0))
    def test_receipt_failure_after_success_is_raised(self):
        receipt_error=OSError('receipt')
        with mock.patch.object(H,'write_result',side_effect=receipt_error):
            with self.assertRaises(OSError) as caught:self.go()
        self.assertIs(caught.exception,receipt_error); self.assertEqual(len(self.calls),2)
    def test_failure_before_helper_restores_timer(self):
        first=ValueError('bad own source')
        self.reader.side_effect=first
        with self.assertRaises(ValueError) as caught:self.go()
        self.assertIs(caught.exception,first); self.assertEqual(self.calls,[])
        self.assertEqual(self.timer.call_args.args,(signal.ITIMER_REAL,0))
        self.assertEqual(self.sig.call_args.args,(signal.SIGALRM,'old_handler'))
    def test_fixed_program_catalog_mismatch_blocks_before_child(self):
        self.binding['system_programs']['/usr/bin/g++']['path']='/different/g++'
        with self.assertRaisesRegex(ValueError,'FIXED_COMPILER_CATALOG'):self.go()
        self.assertEqual(self.calls,[])
    def test_catalog_must_have_exact_39_rows(self):
        self.catalog['files'].pop(next(iter(self.catalog['files'])))
        self.read_map[Path(self.cfg['dependencies'])]=json.dumps(self.catalog).encode()
        with self.assertRaisesRegex(ValueError,'FIXED_COMPILER_CATALOG'):self.go()
        self.assertEqual(self.calls,[])
    def test_existing_output_rejected(self):
        self.work.mkdir()
        with self.assertRaisesRegex(ValueError,'FRESH_DISJOINT_WORK'):self.go()
        self.assertEqual(self.calls,[])
    def test_first_failure_code_is_sanitized(self):
        self.phase_failure=RuntimeError('/private/path should not be copied into public code')
        with self.assertRaises(RuntimeError):self.go()
        self.assertIsNone(self.receipt()['failure_code'])


class RssGate(unittest.TestCase):
    setUp = Sequence.setUp
    go = Sequence.go
    # Run the same fixture against all invalid sampled RSS forms.
    def test_invalid_rss_stops_before_link(self):
        for value in (-1,True,6*1024**2+1,'4096'):
            with self.subTest(value=value):
                self.calls.clear(); self.result['stages'].clear()
                self.behavior['compile']=({'exit_code':0,'cleanup_confirmed':True},'{}',{'maxrss_kib_cumulative_parent_children':value})
                with self.assertRaisesRegex(ValueError,'CUMULATIVE_RSS_GATE_6G'):self.go()
                self.assertEqual(len(self.calls),1)
    def test_exact_rss_gate_boundary(self):
        self.behavior['compile']=({'exit_code':0,'cleanup_confirmed':True},'{}',{'maxrss_kib_cumulative_parent_children':6*1024**2})
        self.go(); self.assertEqual(len(self.calls),2)


class DependencyGate(unittest.TestCase):
    def setUp(self):
        self.rows={f'/usr/fake/{i}':{'bytes':1,'sha256':'a'*64,'mode':'0755','kind':'dynamic_elf','elf':{'needed':[]}} for i in range(39)}
        self.catalog={'schema':'PC1_FIXED_COMPILER_DEPENDENCIES_V1','files':self.rows,'resolutions':{},'libraries':{'libc.so.6':'/usr/fake/38','libatomic.so.1':'/usr/fake/37'},'programs':dict(zip(('g++','cc1plus','collect2','as','ld'),list(self.rows)[:5]))}
        self.evidence={'euid':1000,'egid':1000,'groups':[],'uid_map':'1000 0 1','gid_map':'1000 0 1','observed':{p:{'covering_mount':{'options':['ro','nosuid','nodev']},'chain':{'parent':{'mode':'0755','writable_by_current_process':False}}} for p in self.rows}}
        self.g=types.SimpleNamespace(need=R.need,MIB=1024**2,checked=lambda *a,**k:b'elf')
        self.observer=types.SimpleNamespace(userns_evidence=lambda *a:self.evidence)
        self.mount=types.SimpleNamespace(descriptor_snapshot=lambda *a:{'stable':True})
        reader=mock.patch.object(D,'elf_reader',return_value=(lambda raw:{'needed':[]},{'inverse_exact':True}));reader.start();self.addCleanup(reader.stop)
        resolve=mock.patch.object(Path,'resolve',lambda p,strict=False:p);resolve.start();self.addCleanup(resolve.stop)
    def go(self):return D.verify(self.g,self.observer,self.mount,Path('/repo'),self.catalog)
    def test_39_fixed_dependencies_with_atomic_allowed(self):self.assertEqual(len(self.go()['files']),39)
    def test_missing_program_rejected(self):
        del self.catalog['programs']['ld']
        with self.assertRaisesRegex(ValueError,'five compiler programs'):self.go()
    def test_extra_program_rejected(self):
        self.catalog['programs']['make']='/usr/fake/6'
        with self.assertRaisesRegex(ValueError,'five compiler programs'):self.go()
    def test_writable_mount_rejected(self):
        self.evidence['observed']['/usr/fake/0']['covering_mount']['options']=['rw','nosuid','nodev']
        with self.assertRaisesRegex(ValueError,'fixed readonly mount'):self.go()
    def test_writable_parent_rejected(self):
        self.evidence['observed']['/usr/fake/0']['chain']['parent']['mode']='0775'
        with self.assertRaisesRegex(ValueError,'fixed protected ancestors'):self.go()
    def test_root_namespace_rejected(self):
        self.evidence['euid']=0
        with self.assertRaisesRegex(ValueError,'fixed local namespace'):self.go()
    def test_unlisted_dependency_rejected(self):
        D.elf_reader.return_value=(lambda raw:{'needed':['unlisted.so']},{})
        for row in self.rows.values():row['elf']={'needed':['unlisted.so']}
        with self.assertRaisesRegex(ValueError,'closed dependency sonames'):self.go()
    def test_resolution_drift_rejected(self):
        self.catalog['resolutions']={'/usr/fake/alias':'/usr/fake/0'}
        with self.assertRaisesRegex(ValueError,'fixed compiler/library resolution'):self.go()
    def test_descriptor_identity_failure_propagates(self):
        self.mount.descriptor_snapshot=mock.Mock(side_effect=ValueError('fixed hash drift'))
        with self.assertRaisesRegex(ValueError,'fixed hash drift'):self.go()


class DescriptorDrift(unittest.TestCase):
    def test_runtime_descriptor_drift_rejected_before_compile(self):
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            path=Path(folder)/'module.py';raw=b'value = 73\n';path.write_bytes(raw);original=os.read;changed=[]
            def read(fd,size):
                data=original(fd,size)
                if data and not changed:path.write_bytes(raw+b'\n');changed.append(True)
                return data
            with mock.patch.object(R.os,'read',side_effect=read),mock.patch.object(builtins,'compile',side_effect=AssertionError('compiled drift')) as compiler:
                with self.assertRaisesRegex(ValueError,'SOURCE_HASH_OR_DRIFT'):R.module(path,pin(raw),'reject_drift')
                compiler.assert_not_called()
    def test_entry_descriptor_drift_rejected(self):
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            path=Path(folder)/'module.py';raw=b'value = 73\n';path.write_bytes(raw);original=os.read;changed=[]
            def read(fd,size):
                data=original(fd,size)
                if data and not changed:path.write_bytes(raw+b'\n');changed.append(True)
                return data
            with mock.patch.object(E.os,'read',side_effect=read):
                with self.assertRaisesRegex(ValueError,'ENTRY_HASH_OR_DRIFT'):E.checked(path,pin(raw))


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromModule(types.SimpleNamespace(**globals()))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.testsRun > 0 and result.wasSuccessful() else 1)
