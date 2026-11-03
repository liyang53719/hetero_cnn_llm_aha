#!/usr/bin/env python3
"""Offline AVX512 runtime contract tests. Never import or execute real Torch."""
import ast
from contextlib import ExitStack
import hashlib
from pathlib import Path
import shlex
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import prepare_runtime as runtime

HERE = Path(__file__).resolve().parent
FROZEN_SHA256 = 'e93e1a8ff6e54f7f82ddd3d0134785350a09726e257c2cb73b6823625fa09c76'


class ObservedText(str):
    pass


class ObservedInt(int):
    pass


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.site = self.root / 'site-packages'
        self.output = self.root / 'IMPORT_PROBE.json'
        self.frozen = HERE / 'FROZEN_P0.json'
        self.manifest = runtime.read_json(self.frozen)
        self.sidecar = self.manifest['runtime_sidecar']['content']
        self.capability = ObservedText('AVX512')
        self.threads = ObservedInt(4)
        self.interop = ObservedInt(1)
        self.git = ObservedText(runtime.TORCH_GIT)
        self.torch = ModuleType('torch')
        self.torch.__version__ = '2.10.0+cpu'
        self.torch.version = SimpleNamespace(git_version=self.git)
        self.torch.backends = SimpleNamespace(cpu=SimpleNamespace(
            get_cpu_capability=Mock(return_value=self.capability)))
        self.torch.set_num_threads = Mock()
        self.torch.set_num_interop_threads = Mock()
        self.torch.get_num_threads = Mock(return_value=self.threads)
        self.torch.get_num_interop_threads = Mock(return_value=self.interop)
        self.transformers = ModuleType('transformers')
        self.transformers.__version__ = '4.40.1'
        self.stack.enter_context(patch.dict(sys.modules, {
            'torch': self.torch, 'transformers': self.transformers}))
        self.stack.enter_context(patch.dict(runtime.os.environ, runtime.clean_env(), clear=True))
        self.verify = self.stack.enter_context(patch.object(runtime, 'verify_files'))
        self.write = self.stack.enter_context(patch.object(runtime, 'write_json'))
        self.modules = {name: SimpleNamespace(__file__=str(self.site / rel))
                        for name, rel in self.sidecar['module_relative_paths'].items()}
        self.hashes = {(self.site / self.sidecar['module_relative_paths'][name]).resolve():
                       ObservedText(value) for name, value in self.sidecar['module_sha256'].items()}
        self.stack.enter_context(patch.object(runtime.importlib, 'import_module',
                                             side_effect=self.modules.__getitem__))
        self.stack.enter_context(patch.object(runtime, 'sha', side_effect=self.hashes.__getitem__))
        self.distributions = {wheel['name']: SimpleNamespace(
            version=wheel['version'], locate_file=lambda _: self.site)
            for wheel in self.manifest['wheels'] if wheel['role'] == 'runtime'}
        self.stack.enter_context(patch.object(runtime.importlib.metadata, 'distribution',
                                             side_effect=self.distributions.__getitem__))

    def probe(self):
        runtime.probe(self.site, self.frozen, self.output)

    def test_avx512_receipt_uses_observations(self):
        self.probe()
        self.write.assert_called_once()
        path, observed = self.write.call_args.args
        self.assertEqual(path, self.output)
        self.assertIs(observed['observed_capability'], self.capability)
        self.assertIs(observed['threads'], self.threads)
        self.assertIs(observed['interop_threads'], self.interop)
        self.assertIs(observed['torch_git'], self.git)
        for name, value in observed['imported_modules'].items():
            self.assertIs(value, self.hashes[Path(self.modules[name].__file__).resolve()])
        self.assertEqual(observed['versions'], {name: dist.version
                                              for name, dist in self.distributions.items()})
        self.assertEqual(self.verify.call_args_list,
                         [unittest.mock.call(self.site, self.sidecar)] * 2)
        self.torch.set_num_threads.assert_called_once_with(4)
        self.torch.set_num_interop_threads.assert_called_once_with(1)
        self.torch.backends.cpu.get_cpu_capability.assert_called_once_with()
        self.torch.get_num_threads.assert_called_once_with()
        self.torch.get_num_interop_threads.assert_called_once_with()

    def test_default_and_avx2_actual_capabilities_fail_closed(self):
        for value in ('DEFAULT', 'AVX2', 'OTHER', 'avx512', None):
            with self.subTest(capability=value):
                self.torch.backends.cpu.get_cpu_capability.return_value = value
                with self.assertRaisesRegex(ValueError, '^actual dispatch$'):
                    self.probe()
                self.write.assert_not_called()

    def test_non_avx512_environment_fails_before_import(self):
        for value in ('default', 'avx2', 'AVX512', ''):
            with self.subTest(environment=value), patch.dict(runtime.os.environ,
                    {'ATEN_CPU_CAPABILITY': value}):
                with self.assertRaisesRegex(ValueError, '^dispatch environment$'):
                    self.probe()
                self.verify.assert_not_called()
                self.torch.set_num_threads.assert_not_called()
                self.write.assert_not_called()

    def test_thread_environment_stays_four(self):
        for key in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
                    'NUMEXPR_NUM_THREADS'):
            with self.subTest(key=key), patch.dict(runtime.os.environ, {key: '1'}):
                with self.assertRaisesRegex(ValueError, '^thread environment$'):
                    self.probe()
                self.verify.assert_not_called()
                self.write.assert_not_called()

    def test_actual_thread_mismatch_rejected(self):
        for threads, interop in ((1, 1), (4, 4), (8, 1)):
            with self.subTest(threads=threads, interop=interop):
                self.torch.get_num_threads.return_value = threads
                self.torch.get_num_interop_threads.return_value = interop
                with self.assertRaisesRegex(ValueError, '^actual threads$'):
                    self.probe()
                self.write.assert_not_called()

    def test_original_framework_versions_and_git_required(self):
        cases = ((self.torch, '__version__', '2.10.0', 'Torch version'),
                 (self.torch.version, 'git_version', 'wrong', 'Torch version'),
                 (self.transformers, '__version__', '4.40.2', 'Transformers version'))
        for target, key, value, reason in cases:
            with self.subTest(key=key), patch.object(target, key, value):
                with self.assertRaisesRegex(ValueError, '^' + reason + '$'):
                    self.probe()
                self.write.assert_not_called()

    def test_imported_module_hashes_and_paths_required(self):
        name = next(iter(self.modules))
        path = Path(self.modules[name].__file__).resolve()
        with patch.dict(self.hashes, {path: '0' * 64}):
            with self.assertRaisesRegex(ValueError, '^actual imported source$'):
                self.probe()
        other = self.root / 'outside.py'
        with patch.object(self.modules[name], '__file__', str(other)), \
             patch.dict(self.hashes, {other: self.sidecar['module_sha256'][name]}):
            with self.assertRaisesRegex(ValueError, '^actual imported source$'):
                self.probe()
        self.write.assert_not_called()

    def test_every_runtime_distribution_version_and_location_required(self):
        for name, dist in self.distributions.items():
            with self.subTest(name=name), patch.object(dist, 'version', 'wrong'):
                with self.assertRaisesRegex(ValueError, '^installed distribution version/location$'):
                    self.probe()
        dist = self.distributions['torch']
        with patch.object(dist, 'locate_file', lambda _: self.root / 'outside'):
            with self.assertRaisesRegex(ValueError, '^installed distribution version/location$'):
                self.probe()
        self.write.assert_not_called()

    def test_native_verification_failure_prevents_receipt(self):
        for failures in ([ValueError('installed native hash')],
                         [None, ValueError('installed native hash')]):
            with self.subTest(pass_count=len(failures)):
                self.verify.side_effect = failures
                with self.assertRaisesRegex(ValueError, '^installed native hash$'):
                    self.probe()
                self.write.assert_not_called()


class FixedContractTests(unittest.TestCase):
    def test_clean_environment_always_requests_avx512(self):
        for inherited in ('default', 'avx2', 'AVX512', ''):
            with self.subTest(inherited=inherited), patch.dict(runtime.os.environ,
                    {'ATEN_CPU_CAPABILITY': inherited}):
                self.assertEqual(runtime.clean_env()['ATEN_CPU_CAPABILITY'], 'avx512')
                for key in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS',
                            'OPENBLAS_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
                    self.assertEqual(runtime.clean_env()[key], '4')

    def test_generated_wrapper_and_receipt_identity(self):
        # Evaluate only the shell-text expression, never prepare/install/probe.
        tree = ast.parse((HERE / 'prepare_runtime.py').read_text())
        prepare = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                       and n.name == 'prepare')
        call = next(n for n in ast.walk(prepare) if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute) and n.func.attr == 'write_text'
                    and isinstance(n.func.value, ast.Name) and n.func.value.id == 'wrapper')
        wrapper = eval(compile(ast.Expression(call.args[0]), '<wrapper-text>', 'eval'),
                       {'shlex': shlex, 'sys': SimpleNamespace(executable='/mock/python')})
        self.assertIn('export ATEN_CPU_CAPABILITY=avx512 OMP_NUM_THREADS=4 ', wrapper)
        self.assertIn('MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 NUMEXPR_NUM_THREADS=4\n', wrapper)
        self.assertNotIn('ATEN_CPU_CAPABILITY=default', wrapper)
        self.assertNotIn('ATEN_CPU_CAPABILITY=avx2', wrapper)
        assignment = next(n for n in ast.walk(prepare) if isinstance(n, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == 'receipt' for t in n.targets))
        schema = next(v for k, v in zip(assignment.value.keys, assignment.value.values)
                      if isinstance(k, ast.Constant) and k.value == 'schema')
        self.assertEqual(ast.literal_eval(schema), 'P0_AVX512_FRESH_RUNTIME_V1')
        self.assertTrue(any(k is None and isinstance(v, ast.Name) and v.id == 'observed'
                            for k, v in zip(assignment.value.keys, assignment.value.values)))

    def test_frozen_pins_remain_byte_identical(self):
        self.assertEqual(hashlib.sha256((HERE / 'FROZEN_P0.json').read_bytes()).hexdigest(),
                         FROZEN_SHA256)

    def test_module_and_native_file_pin_checks_remain_active(self):
        with tempfile.TemporaryDirectory() as td:
            site = Path(td)
            module = site / 'module.py'
            native = site / 'native.so'
            module.write_bytes(b'module fixture')
            native.write_bytes(b'native fixture')
            sidecar = {'module_relative_paths': {'fixture': module.name},
                       'module_sha256': {'fixture': runtime.sha(module)},
                       'native_file_sha256': {native.name: runtime.sha(native)}}
            runtime.verify_files(site, sidecar)
            native.write_bytes(b'tampered native fixture')
            with self.assertRaisesRegex(ValueError, '^installed native hash$'):
                runtime.verify_files(site, sidecar)
            module.write_bytes(b'tampered module fixture')
            with self.assertRaisesRegex(ValueError, '^installed module hash$'):
                runtime.verify_files(site, sidecar)


if __name__ == '__main__':
    unittest.main()
