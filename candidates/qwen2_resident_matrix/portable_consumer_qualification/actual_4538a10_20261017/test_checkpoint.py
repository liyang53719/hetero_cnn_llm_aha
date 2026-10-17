"""Cold offline evidence tests; no arithmetic or native execution."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('archive_verifier', HERE / 'verify_checkpoint.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


class CheckpointTests(unittest.TestCase):
    def records(self):
        c = v.frozen_contract()
        return [c.read(HERE / name) for name in
                ('summary.json', 'identities.json', 'source_hashes.json', 'frozen_input_contract.json')]

    def clone(self, directory):
        target = Path(directory) / 'archive'
        shutil.copytree(HERE, target)
        return target

    def rewrite(self, root, name, value, rebind=True):
        raw = (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
        (root / name).write_bytes(raw)
        if rebind:
            self.rebind(root, name)

    def rebind(self, root, name):
        path = root / 'MANIFEST.json'
        manifest = json.loads(path.read_text())
        raw = (root / name).read_bytes()
        manifest['files'][name] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n')

    def test_original_archive_validates(self):
        result = v.verify()
        self.assertEqual(result['original_status'], 'PASS_FIXED_ACTUAL_CASES')
        self.assertEqual(result['source_counts'], [114, 5, 2])
        self.assertTrue(all(x is False for x in result['claims'].values()))

    def test_relocated_archive_validates(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(v.verify(self.clone(directory))['run_id'], v.RUN)

    def test_original_bytes_cannot_be_replaced_by_rebinding_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.clone(directory)
            summary = self.records()[0]
            summary['elapsed_seconds'] = 5.0
            self.rewrite(root, 'summary.json', summary)
            with self.assertRaisesRegex(ValueError, 'immutable original'):
                v.verify(root)

    def test_reformatting_original_json_is_not_an_exact_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.clone(directory)
            (root / 'identities.json').write_text(json.dumps(self.records()[1]))
            self.rebind(root, 'identities.json')
            with self.assertRaisesRegex(ValueError, 'immutable original'):
                v.verify(root)

    def test_changed_frozen_validator_is_rejected_before_import(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.clone(directory)
            (root / 'frozen_contract.py').write_text("raise RuntimeError('must not execute')\n")
            self.rebind(root, 'frozen_contract.py')
            with self.assertRaisesRegex(ValueError, 'frozen validator identity'):
                v.verify(root)

    def test_missing_extra_and_symlink_files_are_rejected(self):
        for mode in ('missing', 'extra', 'symlink'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = self.clone(directory)
                if mode == 'missing':
                    (root / 'summary.json').unlink()
                elif mode == 'extra':
                    (root / 'private.log').write_text('not publishable')
                else:
                    (root / 'summary.json').unlink()
                    (root / 'summary.json').symlink_to(HERE / 'summary.json')
                with self.assertRaises(ValueError):
                    v.verify(root)

    def test_manifest_identity_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.clone(directory)
            (root / 'README_CN.md').write_text('changed scope note')
            with self.assertRaisesRegex(ValueError, 'manifest file identity'):
                v.verify(root)

    def test_duplicate_and_nonfinite_json_are_rejected(self):
        c = v.frozen_contract()
        for raw in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', '{"a":1e9999}'):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'bad.json'
                path.write_text(raw)
                with self.assertRaises(ValueError):
                    c.read(path)

    def test_bounded_json_reader(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'large.json'
            path.write_bytes(b' ' * 262145)
            with self.assertRaises(ValueError):
                v.frozen_contract().read(path)

    def test_summary_status_phase_and_launch_are_bound(self):
        for key, bad in [('status', 'PASS_FULL_M128'), ('phase', 'fixed_cases'),
                         ('launch_commit', '0' * 40), ('run_id', '1'), ('run_attempt', True),
                         ('contract_sha256', '0' * 64), ('library_sha256', '0' * 64)]:
            with self.subTest(key=key):
                records = self.records()
                records[0][key] = bad
                with self.assertRaises(ValueError):
                    v.validate_records(*records)

    def test_all_widened_or_numeric_false_claims_are_rejected(self):
        for key in v.CLAIMS:
            for value in (True, 0):
                with self.subTest(key=key, value=value):
                    records = self.records()
                    records[0]['claims'][key] = value
                    with self.assertRaises(ValueError):
                        v.validate_records(*records)

    def test_exact_case_counters_and_test_counts(self):
        for kind in ('qk_fmas', 'pv128_steps', 'silu_faults', 'scalar_boolean', 'missing_case', 'silu_digest'):
            with self.subTest(kind=kind):
                records = self.records()
                summary = records[0]
                if kind == 'qk_fmas':
                    summary['observations']['profile2_cases'][0]['fmas'] += 1
                elif kind == 'pv128_steps':
                    summary['observations']['profile2_cases'][2]['steps'] = 127
                elif kind == 'silu_faults':
                    summary['checks']['silu_fault_vectors'] = 2
                elif kind == 'scalar_boolean':
                    summary['checks']['scalar_original_tests'] = True
                elif kind == 'missing_case':
                    summary['observations']['profile2_cases'].pop()
                else:
                    summary['observations']['silu_phase_sha256'][0] = 'invalid'
                with self.assertRaises(ValueError):
                    v.validate_records(*records)

    def test_source_map_changes_and_missing_members_are_rejected(self):
        for group in ('input', 'proposal', 'generated'):
            for mode in ('missing', 'changed', 'extra'):
                with self.subTest(group=group, mode=mode):
                    records = self.records()
                    source = records[2][group]
                    name = next(iter(source))
                    if mode == 'missing':
                        del source[name]
                    elif mode == 'changed':
                        source[name] = '0' * 64
                    else:
                        source['outside.py'] = '0' * 64
                    with self.assertRaises(ValueError):
                        v.validate_records(*records)

    def test_actual_imported_source_drift_and_escape_are_rejected(self):
        for stage in ('build', 'profile2', 'scalar_silu'):
            for mode in ('hash', 'path', 'tree', 'duplicate'):
                with self.subTest(stage=stage, mode=mode):
                    records = self.records()
                    sources = records[1][stage]['python_sources']
                    if mode == 'hash':
                        sources[0]['sha256'] = '0' * 64
                    elif mode == 'path':
                        sources[0]['path'] = '../escape.py'
                    elif mode == 'tree':
                        sources[0]['tree'] = 'unreviewed'
                    else:
                        sources.append(copy.deepcopy(sources[0]))
                    with self.assertRaises(ValueError):
                        v.validate_records(*records)

    def test_actual_loaded_elf_and_source_commit_are_bound(self):
        for mode in ('elf', 'libpython', 'commit'):
            with self.subTest(mode=mode):
                records = self.records()
                identity = records[1]['profile2']
                if mode == 'elf':
                    identity['combined_elf']['sha256'] = '0' * 64
                elif mode == 'libpython':
                    item = identity['loader']['libpython']
                    identity['loaded_elfs'].remove(item)
                else:
                    identity['committed_head'] = '0' * 40
                with self.assertRaises(ValueError):
                    v.validate_records(*records)

    def test_host_capability_and_version_claims_are_bound(self):
        for mode in ('avx512', 'amx', 'missing_avx2', 'python', 'compiler', 'image'):
            with self.subTest(mode=mode):
                records = self.records()
                identity = records[1]['build']
                if mode in ('avx512', 'amx'):
                    identity['cpu_flags_common'] = sorted(identity['cpu_flags_common'] + [mode + '_test'])
                elif mode == 'missing_avx2':
                    identity['cpu_flags_common'].remove('avx2')
                elif mode == 'python':
                    identity['python_version'] = '3.12.14'
                elif mode == 'compiler':
                    identity['compiler']['version'] = 'different compiler'
                else:
                    identity['runner']['image_os'] = 'ubuntu22'
                with self.assertRaises(ValueError):
                    v.validate_records(*records)

    def test_provenance_cannot_expand_claims_or_relabel_run(self):
        for mode in ('claims', 'run', 'artifact', 'boolean'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = self.clone(directory)
                value = json.loads((root / 'PROVENANCE.json').read_text())
                if mode == 'claims':
                    value['claims']['producer_qualified'] = True
                elif mode == 'run':
                    value['run']['id'] = '1'
                elif mode == 'artifact':
                    value['artifact']['sha256'] = '0' * 64
                else:
                    value['artifact']['archive_in_publication'] = 0
                self.rewrite(root, 'PROVENANCE.json', value)
                with self.assertRaises(ValueError):
                    v.verify(root)

    def test_cold_test_receipt_rejects_pending_failure_and_native_claims(self):
        for mode in ('pending', 'failure', 'native', 'boolean_count'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = self.clone(directory)
                value = json.loads((root / 'COLD_TESTS.json').read_text())
                if mode == 'pending':
                    value['status'] = 'PENDING_COLD_CHECKS'
                elif mode == 'failure':
                    value['optimized']['failures'] = 1
                elif mode == 'native':
                    value['native_execution'] = True
                else:
                    value['normal']['tests'] = True
                self.rewrite(root, 'COLD_TESTS.json', value)
                with self.assertRaises(ValueError):
                    v.verify(root)

    def test_cold_guard_rejects_native_process_and_network_events(self):
        for event, args in [('import', ('numpy',)), ('import', ('ctypes',)),
                            ('import', ('candidates.fake',)), ('import', ('worker',)),
                            ('subprocess.Popen', ()), ('os.system', ()), ('os.exec', ()),
                            ('socket.connect', ()), ('ctypes.dlopen', ())]:
            with self.subTest(event=event, args=args), self.assertRaises(RuntimeError):
                v.forbid_execution(event, args)
        self.assertNotIn('numpy', sys.modules)
        self.assertNotIn('ctypes', sys.modules)


if __name__ == '__main__':
    unittest.main(verbosity=2)
