"""Cold backend admission/source checks. No compiler, CDLL, or arithmetic runs."""
from dataclasses import FrozenInstanceError, replace
import inspect
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from . import vector as v


class BackendAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='vector-cold-receipt-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.library = self.root / 'not-a-native-library.so'
        self.compiler = self.root / 'not-a-compiler'
        # These bytes are only receipt-check fixtures and MUST NOT be loaded.
        self.library.write_bytes(b'SYNTHETIC_RECEIPT_CHECK_ONLY')
        self.compiler.write_bytes(b'SYNTHETIC_COMPILER_IDENTITY_ONLY')
        self.load = patch.object(v.C, 'CDLL', side_effect=AssertionError('native load forbidden')).start()
        self.addCleanup(patch.stopall)

    def receipt(self, backend=v.LEGACY_BACKEND, *, original=False):
        source, metadata = v.backend_source(backend)
        receipt = dict(status='PASS_HOST_BUILD_ONLY',
            argv=[str(self.compiler), *v.FLAGS, str(source), '-o', str(self.library)],
            source_sha256=metadata['source_sha256'], library_sha256=v.sha(self.library.read_bytes()),
            compiler_sha256=v.sha(self.compiler.read_bytes()), hardware_simulation=False, compiler_processes=1)
        if not original:
            receipt['arithmetic_backend'] = metadata
        return receipt

    def save(self, receipt):
        self.library.with_suffix('.json').write_text(json.dumps(receipt))

    def reject(self, receipt, backend=v.LEGACY_BACKEND, pattern='Vector16'):
        self.save(receipt)
        with self.assertRaisesRegex(ValueError, pattern):
            v.Vector16(self.library, arithmetic_backend=backend)
        self.load.assert_not_called()

    def test_both_entrypoints_remain_legacy_by_default(self):
        for call in (v.build_library, v.Vector16):
            self.assertEqual(inspect.signature(call).parameters['arithmetic_backend'].default, v.LEGACY_BACKEND)
        self.assertEqual(inspect.signature(v.Vector16).parameters['exception_policy'].default, v.LEGACY_POLICY)
        self.assertEqual(v.POLICY_MASKS, {v.LEGACY_POLICY: 30, v.IEEE_POLICY: 28})

    def test_source_pins_and_same_abi_are_explicit(self):
        for backend in v.ARITHMETIC_BACKENDS:
            source, metadata = v.backend_source(backend)
            self.assertEqual(v.sha(source.read_bytes()), metadata['source_sha256'])
            self.assertEqual(metadata['abi'], v.VECTOR_ABI)
        self.assertEqual(v.backend_source(v.FINITE_MUL_UF_BACKEND)[1]['source_sha256'],
            'a54c125ba27357123c5edb1ec4ff0dad0e883f3dd47b66852d7e2f56fdceeec7')

    def test_unknown_backend_fails_before_loading(self):
        for backend in ('', 'auto', 'anything.so', True, None):
            with self.assertRaisesRegex(ValueError, 'supported Vector arithmetic backend'):
                v.Vector16(self.library, arithmetic_backend=backend)
        self.load.assert_not_called()

    def test_original_legacy_receipt_remains_verifiable_without_loading(self):
        self.save(self.receipt(original=True))
        library, _, identity = v.verify_library(self.library)
        self.assertEqual(library, self.library)
        self.assertEqual(identity.backend, v.LEGACY_BACKEND)
        self.assertEqual(identity.library_sha256, v.sha(self.library.read_bytes()))
        self.load.assert_not_called()

    def test_new_receipt_identity_is_verifiable_without_loading(self):
        self.save(self.receipt(v.FINITE_MUL_UF_BACKEND))
        _, _, identity = v.verify_library(self.library, arithmetic_backend=v.FINITE_MUL_UF_BACKEND)
        self.assertEqual(identity.backend, v.FINITE_MUL_UF_BACKEND)
        with self.assertRaises(FrozenInstanceError):
            identity.abi = 'different'
        self.load.assert_not_called()

    def test_opt_in_never_accepts_old_unversioned_receipt(self):
        self.reject(self.receipt(v.FINITE_MUL_UF_BACKEND, original=True), v.FINITE_MUL_UF_BACKEND,
                    'backend/version/source/ABI')

    def test_receipt_cannot_choose_backend_implicitly(self):
        self.reject(self.receipt(v.FINITE_MUL_UF_BACKEND))
        self.reject(self.receipt(), v.FINITE_MUL_UF_BACKEND)

    def test_each_backend_identity_field_is_required_exact(self):
        for backend in v.ARITHMETIC_BACKENDS:
            for field in self.receipt(backend)['arithmetic_backend']:
                with self.subTest(backend=backend, field=field):
                    receipt = self.receipt(backend)
                    receipt['arithmetic_backend'][field] = 'changed'
                    self.reject(receipt, backend, 'backend/version/source/ABI')
            receipt = self.receipt(backend)
            receipt['arithmetic_backend']['unrecognized'] = 'cannot extend implicitly'
            self.reject(receipt, backend, 'backend/version/source/ABI')

    def test_existing_status_source_elf_compiler_gates_preserved(self):
        for backend in v.ARITHMETIC_BACKENDS:
            for field in ('status', 'source_sha256', 'library_sha256', 'compiler_sha256'):
                with self.subTest(backend=backend, field=field):
                    receipt = self.receipt(backend)
                    receipt[field] = 'changed'
                    self.reject(receipt, backend)

    def test_existing_exact_compiler_arguments_preserved(self):
        for backend in v.ARITHMETIC_BACKENDS:
            for index in range(1, len(self.receipt(backend)['argv'])):
                with self.subTest(backend=backend, index=index):
                    receipt = self.receipt(backend)
                    receipt['argv'][index] = 'changed'
                    self.reject(receipt, backend)

    def test_malformed_receipts_cannot_reach_native_loader(self):
        for receipt in (None, [], {}, {'argv': None}, {'argv': ''}):
            self.reject(receipt)

    def test_pinned_source_drift_rejected_before_build_or_load(self):
        for backend in v.ARITHMETIC_BACKENDS:
            source, _ = v.backend_source(backend)
            original = Path.read_bytes
            def read(path):
                return b'changed source' if path == source else original(path)
            with patch.object(Path, 'read_bytes', read), patch.object(v.subprocess, 'run') as compile_call:
                with self.assertRaisesRegex(ValueError, 'pinned arithmetic source changed'):
                    v.build_library(self.root / 'unused', arithmetic_backend=backend)
                with self.assertRaisesRegex(ValueError, 'pinned arithmetic source changed'):
                    v.Vector16(self.library, arithmetic_backend=backend)
                compile_call.assert_not_called()
        self.load.assert_not_called()

    def test_single_and_batch_source_keep_one_rounded_primitive(self):
        # The complete source SHA is pinned above; these document its routing.
        source = v.backend_source(v.FINITE_MUL_UF_BACKEND)[0].read_text()
        self.assertIn('return compute(op, a, b, out, lanes, lane_flags);', source)
        self.assertIn('compute(1, a, b, b, lanes, lane_flags)', source)
        self.assertIn('compute(0, total, b, out, lanes, lane_flags)', source)
        self.assertIn('if (issue_flags[0] < 0 || (issue_flags[0] & fatal_mask)) return 1;', source)
        self.assertIn('fatal_mask != 30 && fatal_mask != 28', source)

    def constructed_fixture(self):
        # Actual Python constructor/buffer/ABI setup with an explicitly fake
        # loader. This verifies binding control, NEVER native arithmetic.
        self.save(self.receipt())
        lib = SimpleNamespace(**{name: SimpleNamespace() for name in
            ('gdn_vector16', 'gdn_vector16_trace', 'gdn_vector16_mul_add_policy_trace',
             'gdn_vector16_environment')})
        with patch.object(v.C, 'CDLL', return_value=lib):
            return v.Vector16(self.library)

    def test_constructor_binding_rejects_pre_admission_relabel_or_rebind(self):
        for field, change in (
                ('backend_identity', lambda old: replace(old, backend=v.FINITE_MUL_UF_BACKEND)),
                ('library', lambda old: Path('other.so')),
                ('library_sha256', lambda old: 'f' * 64),
                ('lib', lambda old: SimpleNamespace(**vars(old)))):
            with self.subTest(field=field):
                instance = self.constructed_fixture()
                setattr(instance, field, change(getattr(instance, field)))
                with self.assertRaisesRegex(ValueError, 'loaded arithmetic binding changed'):
                    instance.arithmetic_identity()
                with self.assertRaisesRegex(ValueError, 'loaded arithmetic binding changed'):
                    instance.backend_report()

    def test_constructor_binding_rejects_errcheck_and_abi_changes(self):
        for field, changed in (('errcheck', lambda result, function, args: 0),
                               ('argtypes', ()), ('restype', v.C.c_uint)):
            with self.subTest(field=field):
                instance = self.constructed_fixture()
                setattr(instance.lib.gdn_vector16_trace, field, changed)
                with self.assertRaisesRegex(ValueError, 'loaded arithmetic binding changed'):
                    instance.arithmetic_identity()

    def test_constructor_baseline_cannot_be_reset_through_admission_property(self):
        instance = self.constructed_fixture()
        before = instance.arithmetic_identity()
        with self.assertRaises(AttributeError):
            instance._loaded_arithmetic_identity = ('changed',)
        self.assertEqual(instance.arithmetic_identity(), before)

    def test_snapshot_rejects_library_replaced_since_constructor_even_with_new_receipt(self):
        from .. import full_driver as f
        instance = self.constructed_fixture()
        self.library.write_bytes(b'DIFFERENT_SYNTHETIC_LIBRARY_NOT_LOADED')
        self.save(self.receipt())
        with self.assertRaisesRegex(ValueError, 'Vector native build changed after construction'):
            f.freeze_identity(self.root, self.root, {}, {}, self.library, instance, self.root)


if __name__ == '__main__':
    unittest.main()
