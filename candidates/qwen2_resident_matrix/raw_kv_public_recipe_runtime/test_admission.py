"""Cold admission tests with synthetic metadata and mocked kernel/runtime checks.

No model array, native library, package install or producer is executed. Export
files are tiny CONTROL_ONLY markers, and the thirteen pinned tensor reads are
explicitly mocked. These tests establish admission control, never numerics.
"""
import builtins
import copy
from contextlib import ExitStack
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from . import admission as a, runtime
from ..raw_kv_native_qk_run.test_phase import fixture, diagnostic_controls


def record(path, size=1, digest='0' * 64):
    return dict(path=path, bytes=size, sha256=digest)


def extension():
    value = dict(generated_module=record(a.GENERATED_MODULE,
        digest=a.native_runtime.GENERATED_MODULE_SHA256))
    for role, kernel in (('qk', a.phase.kernel), ('qkv', a.phase.qkv_kernel)):
        value[role] = dict(binary=record(role + '_library/' + kernel.LIBRARY),
            receipt=record(role + '_library/' + kernel.RECEIPT))
    for name, _, _ in a.CASES:
        value[name] = dict(report=record('phase_' + name + '.json'),
            diagnostics=record('phase_' + name + '_diagnostics.json'))
    return value


class ExtensionTests(unittest.TestCase):
    def test_pure_strict_extension_never_opens_a_path_or_imports(self):
        value = extension()
        with patch.object(Path, 'open', side_effect=AssertionError('artifact opened')), \
                patch('builtins.__import__', side_effect=AssertionError('import attempted')):
            self.assertIs(a.validate_manifest_extension(value), value)

    def test_exact_extension_case_and_library_keys(self):
        for section in (None, 'qk', 'qkv', 'native16', 'native128'):
            for change in ('missing', 'extra', 'wrong_type'):
                value = extension()
                target = value if section is None else value[section]
                if change == 'missing': target.pop(next(iter(target)))
                elif change == 'extra': target['unreviewed'] = True
                elif section is None: value = []
                else: value[section] = []
                with self.subTest(section=section, change=change), self.assertRaises(ValueError):
                    a.validate_manifest_extension(value)

    def test_every_artifact_rejects_noncanonical_paths_types_sizes_and_hashes(self):
        base = extension()
        slots = [('generated_module',)] + [(role, key) for role in ('qk', 'qkv')
            for key in ('binary', 'receipt')] + [(role, key) for role in ('native16', 'native128')
            for key in ('report', 'diagnostics')]
        for slot in slots:
            for key, bad in (('path', '/absolute'), ('path', '../escape'), ('path', 'a//b'),
                    ('path', 'a/./b'), ('path', 'a\\b'), ('path', 'a\0b'), ('path', 'renamed'),
                    ('bytes', True), ('bytes', 0), ('bytes', -1), ('bytes', 1.0),
                    ('bytes', a.files.ARENA_BYTES + 1), ('sha256', 'A' * 64), ('sha256', '0' * 63)):
                value = copy.deepcopy(base)
                target = value
                for part in slot: target = target[part]
                target[key] = bad
                with self.subTest(slot=slot, key=key, bad=bad), self.assertRaises(ValueError):
                    a.validate_manifest_extension(value)
        value = extension(); value['generated_module']['sha256'] = '1' * 64
        with self.assertRaises(ValueError): a.validate_manifest_extension(value)

    def test_each_metadata_and_binary_bound_is_enforced(self):
        limits = [(('generated_module',), a.MAX_MODULE_BYTES)]
        limits += [((role, key), maximum) for role in ('qk', 'qkv')
            for key, maximum in (('binary', a.MAX_LIBRARY_BYTES), ('receipt', a.MAX_RECEIPT_BYTES))]
        limits += [((role, key), maximum) for role in ('native16', 'native128')
            for key, maximum in (('report', a.phase.MAX_REPORT), ('diagnostics', a.phase.MAX_DIAGNOSTICS))]
        for slot, maximum in limits:
            value = extension(); target = value
            for part in slot: target = target[part]
            target['bytes'] = maximum
            a.validate_manifest_extension(value)
            target['bytes'] += 1
            with self.subTest(slot=slot), self.assertRaises(ValueError): a.validate_manifest_extension(value)


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='recipe-admission-control-')
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.generated = b'# CONTROL_ONLY metadata fixture, never imported\n'
        self.generated_sha = a.files.sha(self.generated)
        self.stack.enter_context(patch.object(a.native_runtime, 'GENERATED_MODULE_SHA256', self.generated_sha))
        self.sources = {a.SOURCE: a.IMPORTED_SHA256,
            a.phase.kernel.ORIGINAL: a.phase.qkv_kernel.FIXED[a.phase.kernel.ORIGINAL]}
        self.contract_raw = a.files.encoded(dict(schema=1, CONTROL_ONLY=True))
        self.contract = a.files.json_bytes(self.contract_raw)
        self.contract_sha = a.files.sha(self.contract_raw)
        self.context = dict(workspace=str(self.workspace), source_sha256=self.sources,
            contract_sha256=self.contract_sha, generated_module=str(self.workspace / a.GENERATED_MODULE),
            generated_module_sha256=self.generated_sha, work_deadline_ns=1)
        self.frozen = dict(sources=self.sources, contract_sha256=self.contract_sha, generated={})
        self.source_mock = self.stack.enter_context(patch.object(runtime, 'source_snapshot',
            side_effect=lambda: copy.deepcopy(self.sources)))
        self.snapshot_mock = self.stack.enter_context(patch.object(runtime, 'contract_snapshot',
            side_effect=lambda **kwargs: copy.deepcopy(self.frozen)))
        self.contract_mock = self.stack.enter_context(patch.object(runtime, 'contract_value',
            side_effect=lambda: (self.contract_raw, copy.deepcopy(self.contract))))
        self.context_mock = self.stack.enter_context(patch.object(runtime, 'read_context',
            side_effect=lambda *args, **kwargs: (copy.deepcopy(self.context), self.workspace)))
        self.manifest = dict(source_sha256=self.sources,
            source_manifest_sha256=a.files.sha(a.files.encoded(self.sources)), recipe=extension())
        self.manifest['recipe']['generated_module'] = self.write(a.GENERATED_MODULE, self.generated)
        self.libraries = {}
        for role, kernel in (('qk', a.phase.kernel), ('qkv', a.phase.qkv_kernel)):
            binary = self.write(role + '_library/' + kernel.LIBRARY, b'CONTROL_ONLY_' + role.encode())
            receipt = self.write(role + '_library/' + kernel.RECEIPT, a.files.encoded({'CONTROL_ONLY': role}))
            self.manifest['recipe'][role] = dict(binary=binary, receipt=receipt)
            self.libraries[role] = dict(library_path=str(self.workspace / binary['path']),
                receipt_path=str(self.workspace / receipt['path']), library_sha256=binary['sha256'],
                receipt_sha256=receipt['sha256'], source_sha256={a.phase.kernel.ORIGINAL:
                    a.phase.qkv_kernel.FIXED[a.phase.kernel.ORIGINAL]}, pins_sha256=(
                    a.native_runtime.RECIPE_PINS_SHA256 if role == 'qk' else a.phase.kernel.OLD_PINS_SHA256))
        self.qk_mock = self.stack.enter_context(patch.object(a.phase.kernel, 'verify',
            side_effect=lambda *args: copy.deepcopy(self.libraries['qk'])))
        self.qkv_mock = self.stack.enter_context(patch.object(a.phase.qkv_kernel, 'verify',
            side_effect=lambda *args: copy.deepcopy(self.libraries['qkv'])))
        self.payload = dict(tensors=[dict(local_name=name, shape=pin['shape'], dtype='BF16', sha256=pin['sha256'])
            for name, pin in a.files.TENSOR_PINS.items()])
        self.manifest['payload'] = dict(manifest=self.write('payload/manifest.json', a.files.encoded(self.payload)),
            tensors={name: record('payload/tensors/' + name, pin['bytes'], pin['sha256'])
                for name, pin in a.files.TENSOR_PINS.items()})
        self.results = {}; self.reports = {}; self.observed = {}
        recipe_identity = a.phase.combined_identity(self.libraries['qk'], self.libraries['qkv'])
        for name, role, tokens in a.CASES:
            result, _ = fixture(tokens)
            observed, cpu, environment, backend, _ = diagnostic_controls(tokens)
            result['identity'].update(backend)
            result['identity'].update(runner_sha256=self.generated_sha, independent_qkv_recipe=recipe_identity)
            result['arithmetic']['independent_qkv'] = recipe_identity
            result['payload_manifest_sha256'] = self.manifest['payload']['manifest']['sha256']
            result['m16_gate_sha256'] = None if tokens == 16 else self.manifest['native_m16']['result']['sha256']
            outputs = {}
            for mode in ('bf16', 'fp32'):
                outputs[mode] = {}
                for method, prefix, field in (('official_self_cache', 'native', 'actual_f32_sha256'),
                        ('independent_self_cache', 'independent', 'reference_f32_sha256')):
                    outputs[mode][method] = {}
                    for stage_name, stage in result['modes'][mode]['phases'][0]['stages'].items():
                        path = role + '/' + mode + '/phase_0/' + prefix + '_' + stage_name + '.f32le'
                        item = self.write(path, ('CONTROL_ONLY ' + path).encode())
                        outputs[mode][method][stage_name] = item
                        stage[prefix + '_file_sha256'] = stage[field] = item['sha256']
            self.manifest[role] = dict(result=self.write(role + '/RESULT.json', a.files.encoded(result)), outputs=outputs)
            report = a.phase.project_result(result, tokens=tokens,
                result_sha256=self.manifest[role]['result']['sha256'], source_sha256=self.sources,
                contract_sha256=self.contract_sha, generated_module_sha256=self.generated_sha,
                library=self.libraries['qk'], qkv_library=self.libraries['qkv'],
                payload_manifest_sha256=self.manifest['payload']['manifest']['sha256'],
                m16_result_sha256=result['m16_gate_sha256'])
            diagnostics = a.phase.diagnostic_record(self.context, tokens, self.libraries['qk'], self.libraries['qkv'],
                observed, cpu, a.phase.backend_build(backend), environment, (result, report, self.payload))
            self.manifest['recipe'][name] = dict(
                report=self.write('phase_' + name + '.json', a.files.encoded(report)),
                diagnostics=self.write('phase_' + name + '_diagnostics.json', a.files.encoded(diagnostics)))
            self.results[role] = result; self.reports[name] = report; self.observed[name] = diagnostics
        self.real_checked = a.files.checked_artifact
        self.real_aliases = a.files.reject_aliases
        self.seen = []
        def checked(workspace, item):
            self.seen.append(item['path'])
            if item['path'].startswith('payload/tensors/'):
                return workspace / item['path']  # No model weights are materialized.
            return self.real_checked(workspace, item)
        def aliases(workspace, groups):
            return self.real_aliases(workspace, {role: [item for item in items
                if not item['path'].startswith('payload/tensors/')] for role, items in groups.items()})
        self.stack.enter_context(patch.object(a.files, 'checked_artifact', side_effect=checked))
        self.stack.enter_context(patch.object(a.files, 'reject_aliases', side_effect=aliases))

    def write(self, relative, raw):
        path = self.workspace / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return record(relative, len(raw), a.files.sha(raw))

    def save(self, item, value):
        item.update(self.write(item['path'], a.files.encoded(value)))

    def verify(self):
        return a.verify_recipe(self.workspace, self.manifest)

    def test_real_same_byte_metadata_admission_is_prerequisite_only(self):
        before = copy.deepcopy(self.manifest)
        result = self.verify()
        self.assertEqual(result['identity'], a.phase.combined_identity(self.libraries['qk'], self.libraries['qkv']))
        self.assertEqual(result['generated_module_sha256'], self.generated_sha)
        self.assertEqual(result['prerequisite']['status'], 'NUMERICAL_PREREQUISITE_ONLY')
        for key in ('runtime_ready', 'actual_chain_executed', 'public_execution', 'backend_order_proven',
                    'rtl_execution', 'full_29_node_acceptance'):
            self.assertIs(result['prerequisite'][key], False)
        self.assertEqual(self.manifest, before)
        for mock in (self.qk_mock, self.qkv_mock): self.assertEqual(mock.call_count, 2)
        for call in self.context_mock.call_args_list:
            self.assertEqual(call.args, (self.workspace / 'context.json',))
            self.assertEqual(call.kwargs, dict(check_deadline=False))
        exports = [item['path'] for role in ('native_m16', 'native')
            for item in a.files.records(self.manifest[role]['outputs'])]
        self.assertEqual(len(exports), 232)
        self.assertTrue(all(self.seen.count(path) == 2 for path in exports))

    def test_each_real_artifact_is_rehashed_before_metadata_use(self):
        items = list(a.files.records(self.manifest['recipe'])) + [self.manifest['native_m16']['result'],
            self.manifest['native']['result'], self.manifest['payload']['manifest'],
            self.manifest['native']['outputs']['bf16']['official_self_cache']['y']]
        for item in items:
            path = self.workspace / item['path']; raw = path.read_bytes()
            path.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
            try:
                with self.subTest(path=item['path']), self.assertRaisesRegex(ValueError, 'content drift'):
                    self.verify()
            finally: path.write_bytes(raw)

    def test_changed_export_on_postflight_fails(self):
        original = a.dispatch.validate_pair
        item = self.manifest['native']['outputs']['fp32']['independent_self_cache']['y']
        def tamper(*args, **kwargs):
            answer = original(*args, **kwargs)
            path = self.workspace / item['path']; raw = path.read_bytes()
            path.write_bytes(b'X' + raw[1:])
            return answer
        with patch.object(a.dispatch, 'validate_pair', side_effect=tamper), self.assertRaisesRegex(ValueError, 'content drift'):
            self.verify()

    def test_aliases_and_symlink_artifacts_are_rejected(self):
        first = self.manifest['recipe']['qk']['binary']
        second = self.manifest['recipe']['qkv']['binary']
        path = self.workspace / second['path']; path.unlink()
        os.link(self.workspace / first['path'], path)
        second.update(bytes=first['bytes'], sha256=first['sha256'])
        with self.assertRaisesRegex(ValueError, 'alias'): self.verify()
        path.unlink(); path.symlink_to(self.workspace / first['path'])
        with self.assertRaisesRegex(ValueError, 'symlink'): self.verify()

    def test_symlink_workspace_is_rejected(self):
        link = self.workspace / 'link'; link.symlink_to(self.workspace, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            a.verify_recipe(link, self.manifest)

    def test_metadata_reader_hashes_and_parses_one_bounded_read(self):
        item = self.manifest['recipe']['native16']['report']
        real = a.native_runtime.read_bytes
        with patch.object(a.native_runtime, 'read_bytes', wraps=real) as read:
            self.assertEqual(a._metadata(self.workspace, item, a.phase.MAX_REPORT), self.reports['native16'])
            self.assertEqual(read.call_count, 1)
        with self.assertRaisesRegex(ValueError, 'bound'):
            a._metadata(self.workspace, item, item['bytes'] - 1)
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e999}'):
            item = self.write('bad.json', raw)
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                a._metadata(self.workspace, item, 100)

    def test_rehashed_noncanonical_safe_report_cannot_change_file_identity(self):
        item = self.manifest['recipe']['native16']['report']
        item.update(self.write(item['path'], json.dumps(self.reports['native16'], indent=2).encode()))
        with self.assertRaises(ValueError): self.verify()

    def test_frozen_source_contract_and_context_cannot_be_fabricated_from_reports(self):
        changes = [lambda: self.context.update(contract_sha256='0' * 64),
            lambda: self.context.update(generated_module_sha256='0' * 64),
            lambda: self.context.update(generated_module=str(self.workspace / 'wrong.py')),
            lambda: self.context.update(workspace=str(self.workspace / 'elsewhere')),
            lambda: self.context.update(source_sha256={'untrusted': '0' * 64}),
            lambda: self.manifest.update(source_manifest_sha256='0' * 64),
            lambda: self.manifest.update(source_sha256={'untrusted': '0' * 64}),
            lambda: self.sources.update({a.SOURCE: '0' * 64}),
            lambda: self.sources.update({a.phase.kernel.ORIGINAL: '0' * 64})]
        for index, change in enumerate(changes):
            saved = copy.deepcopy((self.context, self.manifest, self.sources))
            change()
            try:
                with self.subTest(case=index), self.assertRaises(ValueError): self.verify()
            finally: self.context, self.manifest, self.sources = saved

    def test_context_and_frozen_sources_are_rechecked_after_admission(self):
        original = a.dispatch.validate_pair
        def tamper(*args, **kwargs):
            result = original(*args, **kwargs)
            self.context['work_deadline_ns'] += 1
            return result
        with patch.object(a.dispatch, 'validate_pair', side_effect=tamper), self.assertRaisesRegex(ValueError, 'changed'):
            self.verify()

    def test_both_real_kernel_verifiers_are_mandatory(self):
        for mock in (self.qk_mock, self.qkv_mock):
            prior = mock.side_effect
            mock.side_effect = ValueError('CONTROL_ONLY invalid real kernel receipt')
            try:
                with self.subTest(kernel=mock), self.assertRaisesRegex(ValueError, 'kernel receipt'): self.verify()
            finally: mock.side_effect = prior

    def test_library_paths_hashes_receipts_pins_and_source_closures_are_bound(self):
        for role in ('qk', 'qkv'):
            for key in ('library_path', 'receipt_path', 'library_sha256', 'receipt_sha256',
                        'pins_sha256', 'source_sha256'):
                saved = copy.deepcopy(self.libraries[role])
                self.libraries[role][key] = {'unknown.py': '0' * 64} if key == 'source_sha256' else '0' * 64
                try:
                    with self.subTest(role=role, key=key), self.assertRaises(ValueError): self.verify()
                finally: self.libraries[role] = saved

    def test_library_postflight_change_is_rejected(self):
        first = copy.deepcopy(self.libraries['qk'])
        second = copy.deepcopy(first); second['cpp_sha256'] = '0' * 64
        self.qk_mock.side_effect = [first, second]
        with self.assertRaisesRegex(ValueError, 'changed'): self.verify()

    def test_rehashed_reports_must_equal_original_result_projection(self):
        for name in ('native16', 'native128'):
            report = copy.deepcopy(self.reports[name])
            report['bf16_stages']['gate'].update(max_abs=1e-7, mean_abs=1e-8, bit_exact=False)
            self.assertEqual(a.phase.validate_report(report), report)
            item = self.manifest['recipe'][name]['report']; saved = copy.deepcopy(item)
            self.save(item, report)
            try:
                with self.subTest(case=name), self.assertRaisesRegex(ValueError, 'report differs'): self.verify()
            finally: self.write(item['path'], a.files.encoded(self.reports[name])); item.update(saved)

    def test_rehashed_result_cannot_be_paired_with_unchanged_safe_report(self):
        result = copy.deepcopy(self.results['native'])
        result['modes']['bf16']['phases'][0]['stages']['gate'].update(max_abs=1e-7, mean_abs=1e-8, bit_exact=False)
        self.save(self.manifest['native']['result'], result)
        with self.assertRaisesRegex(ValueError, 'report differs'): self.verify()

    def test_rehashed_diagnostics_bind_stage_payload_and_backend_to_results(self):
        for name in ('native16', 'native128'):
            for mutation in ('stage', 'payload', 'backend'):
                observed = copy.deepcopy(self.observed[name])
                if mutation == 'stage': observed['stage_sha256']['bf16']['gate']['actual_f32_sha256'] = '0' * 64
                elif mutation == 'payload':
                    key = next(iter(observed['payload_sha256']))
                    observed['payload_sha256'][key] = '0' * 64
                    observed['payload_tensor_map_sha256'] = a.files.sha(a.files.encoded(observed['payload_sha256']))
                else: observed['backend_build']['torch_build_sha256'] = '0' * 64
                self.assertEqual(a.phase.validate_diagnostics(observed), observed)
                item = self.manifest['recipe'][name]['diagnostics']; saved = copy.deepcopy(item)
                self.save(item, observed)
                try:
                    with self.subTest(case=name, mutation=mutation), self.assertRaisesRegex(ValueError, 'diagnostics differ'):
                        self.verify()
                finally: self.write(item['path'], a.files.encoded(self.observed[name])); item.update(saved)

    def test_exact_bf16_dispatch_and_default_fenv_still_required(self):
        for name in ('native16', 'native128'):
            observed = copy.deepcopy(self.observed[name])
            for item in observed['capture']['bf16']['records']:
                item.update(implementation='brg_matmul:avx512_core_amx', isa='avx512_core_amx')
            self.assertEqual(a.phase.validate_diagnostics(observed), observed)
            item = self.manifest['recipe'][name]['diagnostics']; saved = copy.deepcopy(item)
            self.save(item, observed)
            try:
                with self.subTest(case=name), self.assertRaises(ValueError): self.verify()
            finally: self.write(item['path'], a.files.encoded(self.observed[name])); item.update(saved)

    def test_m128_requires_this_exact_m16_result(self):
        result = copy.deepcopy(self.results['native']); result['m16_gate_sha256'] = '0' * 64
        self.save(self.manifest['native']['result'], result)
        with self.assertRaises(ValueError): self.verify()

    def test_fixed_public_output_directories_are_required(self):
        for role in ('native_m16', 'native'):
            item = self.manifest[role]['result']; saved = copy.deepcopy(item)
            item.update(self.write('relocated_' + role + '/RESULT.json', a.files.encoded(self.results[role])))
            try:
                with self.subTest(role=role), self.assertRaisesRegex(ValueError, 'result path'): self.verify()
            finally: item.update(saved)

    def test_identity_changes_only_generated_runner_and_combined_recipe(self):
        base = dict(runner_sha256=a.phase.qkv_kernel.FIXED[a.phase.kernel.ORIGINAL],
            python='CONTROL_ONLY', source_sha256={'official.py': 'a' * 64}, installed_sources_verified_exact=True)
        native = Mock(); native.runtime_identity.return_value = (None, base)
        before = copy.deepcopy(base)
        result = a.identity(native, self.workspace, self.manifest)
        self.assertEqual(base, before)
        self.assertEqual(result['runner_sha256'], self.generated_sha)
        self.assertEqual(result['independent_qkv_recipe'], a.phase.combined_identity(self.libraries['qk'], self.libraries['qkv']))
        self.assertEqual({k: v for k, v in result.items() if k not in ('runner_sha256', 'independent_qkv_recipe')},
            {k: v for k, v in base.items() if k != 'runner_sha256'})
        native.runtime_identity.assert_called_once_with(a.ROOT)

    def test_identity_requires_the_original_runtime_and_validates_recipe(self):
        for base in ({'runner_sha256': self.generated_sha},
                {'runner_sha256': a.phase.qkv_kernel.FIXED[a.phase.kernel.ORIGINAL], 'independent_qkv_recipe': {}}):
            native = Mock(); native.runtime_identity.return_value = (None, base)
            with self.subTest(base=base), self.assertRaisesRegex(ValueError, 'original native'): a.identity(native, self.workspace, self.manifest)
        native = Mock(); native.runtime_identity.return_value = (None,
            {'runner_sha256': a.phase.qkv_kernel.FIXED[a.phase.kernel.ORIGINAL]})
        with patch.object(a, 'verify_recipe', side_effect=ValueError('CONTROL_ONLY rejection')), self.assertRaises(ValueError):
            a.identity(native, self.workspace, self.manifest)

    def test_admission_does_not_import_numerical_packages_load_libraries_or_run(self):
        imported = builtins.__import__
        before_modules = {key for key in sys.modules if key.split('.')[0] in ('numpy', 'torch', 'transformers')}
        before_env = dict(os.environ)
        def cold(name, *args, **kwargs):
            if name.split('.')[0] in ('numpy', 'torch', 'transformers', 'ctypes'):
                raise AssertionError('numerical/native import: ' + name)
            return imported(name, *args, **kwargs)
        with patch('builtins.__import__', side_effect=cold), \
                patch.object(a.phase, '_generated', side_effect=AssertionError('generated import')), \
                patch.object(a.phase, 'run', side_effect=AssertionError('numerical launch')), \
                patch.object(a.phase.kernel, 'build', side_effect=AssertionError('kernel build')), \
                patch.object(a.phase.qkv_kernel, 'build', side_effect=AssertionError('kernel build')):
            importlib.reload(a)
            self.verify()
        self.assertEqual(before_env, dict(os.environ))
        self.assertEqual(before_modules, {key for key in sys.modules if key.split('.')[0] in ('numpy', 'torch', 'transformers')})


if __name__ == '__main__':
    unittest.main()
