"""Portable cold regression tests; no runtime/native/numerical imports."""
from __future__ import annotations
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
from unittest import mock
import warnings
import zipfile

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('cpu_placement_archive_validator', HERE / 'validate_evidence.py')
v = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / 'evidence'
        self.directory.mkdir()
        # Copy only the intended ten files; interpreter caches are not evidence.
        for name in v.ROOT_FILES:
            shutil.copyfile(HERE / name, self.directory / name)
        for placement in v.PLACEMENTS:
            (self.directory / placement).mkdir()
            for name in v.MEMBERS:
                shutil.copyfile(HERE / placement / name, self.directory / placement / name)

    def raw(self, name='summary.json', placement='placement_1'):
        return (self.directory / placement / name).read_bytes()

    def data(self, name='summary.json', placement='placement_1'):
        return json.loads(self.raw(name, placement))

    def reject_summary(self, path, value):
        for placement in v.PLACEMENTS:
            data = self.data(placement=placement)
            target = data
            for part in path[:-1]:
                target = target[part]
            target[path[-1]] = value
            with self.assertRaises(v.EvidenceError):
                v.validate_schema(placement, 'summary.json', data)

    def test_exact_directory_retains_failure(self):
        result = v.validate_directory(self.directory)
        self.assertEqual(result['status'], 'CPU_UNSUITABLE')
        self.assertIs(result['numerical_acceptance'], False)
        for name in ['clone_started', 'setup_started', 'numeric_started']:
            self.assertIs(result[name], False)

    def test_each_original_member(self):
        for placement in v.PLACEMENTS:
            for name in v.MEMBERS:
                v.validate_member(placement, name, self.raw(name, placement))

    def test_identical_source_manifests(self):
        self.assertEqual(self.raw('source_hashes.json'), self.raw('source_hashes.json', 'placement_2'))

    def test_no_synthetic_pass(self):
        self.reject_summary(['status'], 'PASS')
        self.reject_summary(['cpu_eligibility', 'status'], 'ELIGIBLE_FOR_BACKEND_CHECK')

    def test_no_acceptance_or_execution(self):
        for field in ['clone_started', 'setup_started', 'numeric_started', 'postflight_complete',
                      'numerical_acceptance', 'full_29_node_acceptance', 'scala_executed', 'rtl_executed']:
            self.reject_summary([field], True)
        self.reject_summary(['cpu_eligibility', 'backend_qualified'], True)
        self.reject_summary(['cpu_eligibility', 'eligibility_only'], False)

    def test_bool_not_number(self):
        for field in ['schema', 'rows', 'elapsed_seconds']:
            self.reject_summary([field], True)
        self.reject_summary(['cpu_eligibility', 'processor_records'], True)

    def test_number_not_bool(self):
        self.reject_summary(['numeric_started'], 0)
        self.reject_summary(['cpu_eligibility', 'flags', 'avx512_bf16'], 0)

    def test_known_fields_fixed(self):
        for field, value in [('checkout_commit', '0' * 40), ('phase', 'numeric'),
                             ('launch_contract_sha256', '0' * 64), ('rows', 16),
                             ('elapsed_seconds', 0.0), ('profile', 'unknown')]:
            self.reject_summary([field], value)
        self.reject_summary(['diagnostic', 'frames', 0, 'line'], 498)

    def test_missing_and_unknown_summary_fields(self):
        for remove in [True, False]:
            data = self.data()
            if remove:
                del data['phase']
            else:
                data['numeric_progress'] = {'status': 'PASS'}
            with self.assertRaises(v.EvidenceError):
                v.validate_schema('placement_1', 'summary.json', data)

    def test_cpu_flags_and_exclusions_fixed(self):
        self.reject_summary(['cpu_eligibility', 'flags', 'avx512_bf16'], True)
        self.reject_summary(['cpu_eligibility', 'excluded_flags', 'amx_tile'], True)

    def test_progress_correspondence(self):
        data = self.data('progress.json')
        data['elapsed_seconds'] = v.PROGRESSES['placement_2']['elapsed_seconds']
        with self.assertRaises(v.EvidenceError):
            v.validate_schema('placement_1', 'progress.json', data)

    def test_duplicate_keys_rejected(self):
        with self.assertRaises(v.EvidenceError):
            v.strict_json(b'{"schema":1,"schema":1}', 100)

    def test_nonfinite_rejected(self):
        for token in ['NaN', 'Infinity', '-Infinity', '1e9999']:
            with self.assertRaises(v.EvidenceError):
                v.strict_json(('{"x":' + token + '}').encode(), 100)

    def test_json_top_level_encoding_and_size(self):
        for raw in [b'[]', b'null', b'\xff', b'{}' * 100, b'', '{}']:
            with self.assertRaises(v.EvidenceError):
                v.strict_json(raw, 20)

    def test_deep_json_rejected(self):
        with self.assertRaises(v.EvidenceError):
            v.strict_json(b'{"x":' * 20 + b'1' + b'}' * 20, 1000)

    def test_source_path_traversal_aliases_rejected(self):
        for path in ['/absolute', '../escape', 'a/../b', './file', 'a//b', 'a\\b', 'a\x00b', 'x' * 257]:
            with self.assertRaises(v.EvidenceError):
                v.safe_relative(path)

    def test_source_manifest_types_count_and_keys(self):
        data = self.data('source_hashes.json')
        for mutation in ['count', 'key', 'schema', 'extra']:
            changed = copy.deepcopy(data)
            first = next(iter(changed['source_sha256']))
            if mutation == 'count':
                del changed['source_sha256'][first]
            elif mutation == 'key':
                changed['source_sha256']['unknown.py'] = changed['source_sha256'].pop(first)
            elif mutation == 'schema':
                changed['schema'] = True
            else:
                changed['unexpected'] = False
            with self.assertRaises(v.EvidenceError):
                v.validate_source_schema(changed)

    def test_source_digest_shape_and_contract(self):
        for digest in ['G' * 64, True, '0' * 63]:
            data = self.data('source_hashes.json')
            data['source_sha256'][next(iter(data['source_sha256']))] = digest
            with self.assertRaises(v.EvidenceError):
                v.validate_source_schema(data)
        data = self.data('source_hashes.json')
        data['source_sha256'][v.CONTRACT_PATH] = '0' * 64
        with self.assertRaises(v.EvidenceError):
            v.validate_source_schema(data)

    def test_changed_valid_source_hash_rejected_by_byte_anchor(self):
        data = self.data('source_hashes.json')
        data['source_sha256'][next(iter(data['source_sha256']))] = '0' * 64
        raw = json.dumps(data, separators=(',', ':')).encode()
        with self.assertRaises(v.EvidenceError):
            v.validate_member('placement_1', 'source_hashes.json', raw)

    def test_formatted_original_rejected_by_byte_anchor(self):
        raw = json.dumps(self.data(), indent=1).encode()
        with self.assertRaises(v.EvidenceError):
            v.validate_member('placement_1', 'summary.json', raw)

    def test_swapped_placements_rejected(self):
        with self.assertRaises(v.EvidenceError):
            v.validate_member('placement_1', 'summary.json', self.raw(placement='placement_2'))

    def test_unknown_placement_or_member_rejected(self):
        for placement, name in [('placement_3', 'summary.json'), ('placement_1', 'private.log')]:
            with self.assertRaises(v.EvidenceError):
                v.validate_member(placement, name, b'{}')

    def test_extra_or_missing_file_rejected(self):
        for target in [self.directory / 'private.log', self.directory / 'placement_1/private.log']:
            target.write_text('no')
            with self.assertRaises(v.EvidenceError):
                v.validate_directory(self.directory)
            target.unlink()
        (self.directory / 'placement_1/progress.json').unlink()
        with self.assertRaises(v.EvidenceError):
            v.validate_directory(self.directory)

    def test_cache_directory_rejected(self):
        (self.directory / '__pycache__').mkdir()
        with self.assertRaises(v.EvidenceError):
            v.validate_directory(self.directory)

    def test_symlink_member_and_root_rejected(self):
        target = self.directory / 'placement_1/summary.json'
        target.unlink()
        target.symlink_to(HERE / 'placement_1/summary.json')
        with self.assertRaises(v.EvidenceError):
            v.validate_directory(self.directory)
        link = Path(self.temp.name) / 'linked'
        link.symlink_to(self.directory)
        with self.assertRaises(v.EvidenceError):
            v.validate_directory(link)

    def test_symlink_directory_and_code_rejected(self):
        placement = self.directory / 'placement_1'
        shutil.rmtree(placement)
        placement.symlink_to(HERE / 'placement_1')
        with self.assertRaises(v.EvidenceError):
            v.validate_directory(self.directory)
        placement.unlink()
        shutil.copytree(HERE / 'placement_1', placement)
        code = self.directory / 'validate_evidence.py'
        code.unlink()
        code.symlink_to(HERE / 'validate_evidence.py')
        with self.assertRaises(v.EvidenceError):
            v.validate_directory(self.directory)

    def test_fifo_rejected_without_blocking(self):
        fifo = Path(self.temp.name) / 'fifo'
        os.mkfifo(fifo)
        with self.assertRaises(v.EvidenceError):
            v.read_bounded(fifo, 10)

    def test_oversized_file_rejected(self):
        target = self.directory / 'placement_1/progress.json'
        target.write_bytes(b'x' * 95)
        with self.assertRaises(v.EvidenceError):
            v.validate_directory(self.directory)

    def test_checkpoint_mutation_rejected(self):
        target = self.directory / 'checkpoint.json'
        data = json.loads(target.read_bytes())
        data['recorded_facts']['numerical_acceptance'] = True
        target.write_text(json.dumps(data))
        with self.assertRaises(v.EvidenceError):
            v.validate_directory(self.directory)

    def make_zip(self, names=None, symlink=False):
        output = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
                for name in names or sorted(v.MEMBERS):
                    info = zipfile.ZipInfo(name)
                    info.compress_type = zipfile.ZIP_DEFLATED
                    if symlink and name == 'summary.json':
                        info.external_attr = (stat.S_IFLNK | 0o777) << 16
                    z.writestr(info, self.raw(name) if name in v.MEMBERS else b'{}')
        target = Path(self.temp.name) / 'test.zip'
        target.write_bytes(output.getvalue())
        return target

    def patched_zip_record(self, path):
        record = copy.deepcopy(v.PLACEMENTS['placement_1'])
        raw = path.read_bytes()
        record['archive']['bytes'] = len(raw)
        record['archive']['sha256'] = v.sha256(raw)
        return mock.patch.dict(v.PLACEMENTS, {'placement_1': record})

    def test_changed_zip_identity_rejected(self):
        target = self.make_zip()
        with self.assertRaises(v.EvidenceError):
            v.validate_zip('placement_1', target, self.directory)

    def test_zip_content_defenses_independent_of_digest(self):
        for names in [['summary.json', 'progress.json', 'source_hashes.json', 'summary.json'],
                      ['summary.json', 'progress.json', '../source_hashes.json'],
                      ['summary.json', 'progress.json', 'source_hashes.json', 'private.log'],
                      ['summary.json', 'progress.json']]:
            target = self.make_zip(names)
            with self.patched_zip_record(target), self.assertRaises(v.EvidenceError):
                v.validate_zip('placement_1', target, self.directory)
        target = self.make_zip(symlink=True)
        with self.patched_zip_record(target), self.assertRaises(v.EvidenceError):
            v.validate_zip('placement_1', target, self.directory)

    def test_zip_matching_members_safe_parser(self):
        # Synthetic ZIP exercises parsing only; it is not claimed to be GitHub evidence.
        target = self.make_zip()
        with self.patched_zip_record(target):
            result = v.validate_zip('placement_1', target, self.directory)
        self.assertEqual(result['status'], 'CPU_UNSUITABLE')

    def test_empty_or_symlink_source_tree_rejected(self):
        empty = Path(self.temp.name) / 'source'
        empty.mkdir()
        with self.assertRaises(v.EvidenceError):
            v.validate_source_tree(empty, self.directory)
        link = Path(self.temp.name) / 'source-link'
        link.symlink_to(empty)
        with self.assertRaises(v.EvidenceError):
            v.validate_source_tree(link, self.directory)

    def test_archive_outside_frozen_source_closure(self):
        data = self.data('source_hashes.json')
        self.assertFalse(any(path.startswith(v.TARGET_PREFIX) for path in data['source_sha256']))
        self.assertEqual(len(data['source_sha256']), 285)
        self.assertEqual(len(data['generated_sha256']), 12)


if __name__ == '__main__':
    unittest.main()
