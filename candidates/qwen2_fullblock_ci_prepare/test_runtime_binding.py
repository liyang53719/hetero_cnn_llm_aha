"""Real pure binding checks against original pins, no native reads or imports."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

import runtime_binding as B


def packed(value):
    return json.dumps(value, sort_keys=True).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class BindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = (Path(__file__).resolve().parents[1] /
                   'qwen2_fullblock_reference_m128/pins.json').read_bytes()
        cls.original = json.loads(cls.raw)

    def setUp(self):
        self.root = '/reviewed/ci/checkout'
        self.binding = dict(schema=1, kind='full29-root-binding', root=self.root,
            pythonpath=self.root + '/' + B.RUNTIME, original_pins_sha256=B.ORIGINAL_SHA256,
            native_paths={k:(v['path'] if v['path'].startswith('/') else self.root + '/' + v['path'])
                          for k,v in self.original['runtime_native_files'].items()})

    def call(self, binding=None, **kwargs):
        raw = packed(self.binding if binding is None else binding)
        options = dict(binding_sha256=sha(raw), root=self.root)
        options.update(kwargs)
        return B.bind_runtime(self.raw, raw, **options)

    def platform(self):
        native = copy.deepcopy(self.original['runtime_native_files'])
        for name, rec in native.items():
            rec['path'] = self.binding['native_paths'][name]
        return dict(schema=1, kind='full29-observed-platform', root=self.root,
                    native_files=native, runtime_requirements=copy.deepcopy(self.original['runtime_requirements']))

    def test_preserves_every_other_pin_and_does_not_mutate(self):
        before = copy.deepcopy(self.binding)
        result = self.call()
        pins = result['pins']
        self.assertEqual(self.binding, before)
        self.assertEqual(pins['runtime_requirements'], self.original['runtime_requirements'])
        pins['capture_environment']['PYTHONPATH'] = self.original['capture_environment']['PYTHONPATH']
        for name, rec in pins['runtime_native_files'].items():
            rec['path'] = self.original['runtime_native_files'][name]['path']
        self.assertTrue(B.same(pins, self.original))
        self.assertFalse(result['numeric_execution_allowed'])
        self.assertFalse(result['native_files_verified'])
        self.assertFalse(result['historical_runtime_equivalence_claimed'])

    def test_exact_contract_bytes_external_digest(self):
        raw = packed(self.binding)
        for changed in (raw + b' ', raw.replace(b'reviewed', b'unreviewed')):
            with self.assertRaises(B.Rejected):
                B.bind_runtime(self.raw, changed, binding_sha256=sha(raw), root=self.root)
        for bad in (None, '0'*64, True, 'A'*64):
            with self.assertRaises(B.Rejected): self.call(binding_sha256=bad)

    def test_original_pin_changes_rejected_even_when_root_is_reviewed(self):
        for field in ('acceptance', 'runtime_requirements', 'runtime_native_files', 'contract'):
            changed = copy.deepcopy(self.original)
            changed[field] = {}
            raw = packed(self.binding)
            with self.assertRaises(B.Rejected):
                B.bind_runtime(packed(changed), raw, binding_sha256=sha(raw), root=self.root)

    def test_root_path_unknown_keys_and_unreviewed_remaps(self):
        mutations = [lambda b:b.update(extra=True), lambda b:b.update(schema=True),
            lambda b:b.update(root='/other'), lambda b:b.update(original_pins_sha256='0'*64),
            lambda b:b.update(pythonpath=b['pythonpath']+':/tmp'),
            lambda b:b['native_paths'].pop('python'),
            lambda b:b['native_paths'].update(extra='/tmp/x'),
            lambda b:b['native_paths'].update(python='/tmp/python'),
            lambda b:b['native_paths'].update(torch_C='/tmp/torch.so')]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                binding=copy.deepcopy(self.binding); mutate(binding)
                with self.assertRaises(B.Rejected): self.call(binding)
        for root in ('/', '/reviewed//ci', '/a/../b', '/a/./b', '/a/', '//host/a',
                     'relative', '/a:b', '/a\n', '/a\\b', None):
            with self.subTest(root=root), self.assertRaises(B.Rejected): self.call(root=root)

    def test_separate_observed_platform_explicit_and_bounded(self):
        platform = self.platform()
        platform['native_files']['python'].update(path='/opt/reviewed/python3.13', bytes=50, sha256='a'*64)
        platform['runtime_requirements']['python_major_minor'] = [3,13]
        self.binding['native_paths']['python'] = '/opt/reviewed/python3.13'
        with self.assertRaises(B.Rejected): self.call()
        raw = packed(platform)
        result = self.call(platform_bytes=raw, platform_sha256=sha(raw))
        self.assertEqual(result['pins']['runtime_requirements']['python_major_minor'], [3,13])
        self.assertEqual(result['pins']['acceptance'], self.original['acceptance'])
        self.assertFalse(result['runtime_initialized'])
        for kwargs in ({'platform_bytes':raw}, {'platform_sha256':sha(raw)},
                       {'platform_bytes':raw,'platform_sha256':'0'*64}):
            with self.assertRaises(B.Rejected): self.call(**kwargs)

    def test_platform_missing_unknown_and_policy_changes_rejected(self):
        mutations = [lambda p:p.update(extra=True), lambda p:p.update(schema=True),
            lambda p:p.update(root='/other'), lambda p:p['native_files'].pop('torch_C'),
            lambda p:p['native_files']['torch_C'].update(bytes=True),
            lambda p:p['native_files']['torch_C'].update(bytes=0),
            lambda p:p['native_files']['torch_C'].update(sha256='x'*64),
            lambda p:p['native_files']['torch_C'].update(extra=True),
            lambda p:p['runtime_requirements'].update(threads=8),
            lambda p:p['runtime_requirements'].update(deterministic_algorithms=False),
            lambda p:p['runtime_requirements'].update(interop_threads=True),
            lambda p:p['runtime_requirements'].update(python_major_minor=[True,12]),
            lambda p:p['runtime_requirements'].update(torch_commit='bad'),
            lambda p:p['runtime_requirements'].update(extra=True)]
        for mutate in mutations:
            p=self.platform(); mutate(p); raw=packed(p)
            with self.subTest(mutate=mutate), self.assertRaises(B.Rejected):
                self.call(platform_bytes=raw,platform_sha256=sha(raw))

    def test_platform_paths_are_exact_and_all_six_distinct(self):
        for path in ('/tmp/lib.so', self.binding['native_paths']['numpy_multiarray'],
                     self.root + '/' + B.RUNTIME + '/a/../evil.so'):
            p=self.platform(); p['native_files']['torch_C']['path']=path
            binding=copy.deepcopy(self.binding); binding['native_paths']['torch_C']=path
            raw=packed(p)
            with self.subTest(path=path), self.assertRaises(B.Rejected):
                self.call(binding,platform_bytes=raw,platform_sha256=sha(raw))

    def test_duplicate_json_and_nonfinite_rejected(self):
        for raw in (b'{"schema":1,"schema":1}', b'{"a":NaN}', b'{"a":Infinity}', b'bad json', b'\xff'):
            with self.assertRaises(B.Rejected): B.document(raw,sha(raw))

    def test_pure_call_performs_no_io_or_imports(self):
        with mock.patch('builtins.open',side_effect=AssertionError('file I/O')), \
             mock.patch('builtins.__import__',side_effect=AssertionError('import')):
            self.call()
        self.assertFalse(any(n.split('.')[0] in ('numpy','torch','transformers') for n in sys.modules))


    def test_z_audited_calls_have_no_external_activity(self):
        def audit(event, args):
            if event == 'open' or event.startswith(('socket.', 'subprocess.', 'ctypes.')) or event in (
                    'os.system', 'os.fork', 'os.exec', 'os.posix_spawn'):
                raise AssertionError('forbidden cold activity: ' + event)
            if event == 'import' and args[0].split('.')[0] in ('torch', 'numpy', 'transformers'):
                raise AssertionError('forbidden numeric import')
        sys.addaudithook(audit)
        result = self.call()
        self.assertFalse(result['numeric_execution_allowed'])
        platform = packed(self.platform())
        self.call(platform_bytes=platform, platform_sha256=sha(platform))


if __name__ == '__main__':
    unittest.main()
