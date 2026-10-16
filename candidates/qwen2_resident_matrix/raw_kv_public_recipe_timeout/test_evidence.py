"""Cold regressions for the immutable TIMEOUT archive. No numerical execution."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

if __package__:
    from . import validate_evidence as evidence
else:
    import validate_evidence as evidence


class TimeoutArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Package/discovery imports may generate __pycache__ in the source tree.
        # Check a precise publication snapshot, never relax the archive allowlist.
        cls.temporary_archive = tempfile.TemporaryDirectory()
        cls.archive_root = Path(cls.temporary_archive.name)
        for name in set(evidence.LIMITS) | {'validate_evidence.py', 'test_evidence.py', 'README.md'}:
            (cls.archive_root / name).write_bytes((evidence.HERE / name).read_bytes())

    @classmethod
    def tearDownClass(cls):
        cls.temporary_archive.cleanup()

    def setUp(self):
        self.raw = {name: (evidence.HERE / name).read_bytes() for name in evidence.LIMITS}
        self.value = {name: json.loads(raw) for name, raw in self.raw.items()}

    def rejected_schema(self, name, value):
        with self.assertRaises(evidence.EvidenceError):
            evidence.validate_schema(name, value)

    def test_01_member_hashes_and_sizes_have_independent_anchors(self):
        anchors = {
            'summary.json': (1195, '37dec6d87998010ba7726a6ed17853a8216cb0318f0fdba89364187f414f171d'),
            'progress.json': (80, '513dcd1280fd8380ec7ddcfa7f8f08b24e0f994a76e0284ddc8d461dfa68cdb0'),
            'source_hashes.json': (39391, '0632730cb3a5fbe10cd713f613e23ed41d91cafc24579481ce87ab71ef1aca26'),
        }
        self.assertEqual(evidence.MEMBERS, anchors)
        for name, (size, digest) in anchors.items():
            with self.subTest(name=name):
                self.assertEqual(len(self.raw[name]), size)
                self.assertEqual(hashlib.sha256(self.raw[name]).hexdigest(), digest)

    def test_02_zip_hash_is_independently_pinned(self):
        self.assertEqual(evidence.ZIP_SHA256,
            '85b9554eaedf9904760d1da4363470903dbd04e32c72016c131c55e9c89d4855')
        self.assertEqual(evidence.ZIP_BYTES, 15278)

    def test_03_all_original_members_validate(self):
        for name, raw in self.raw.items():
            with self.subTest(name=name):
                self.assertEqual(evidence.validate_member(name, raw), self.value[name])

    def test_04_directory_success_is_timeout_not_numeric_acceptance(self):
        result = evidence.validate_directory(self.archive_root)
        self.assertEqual(result['status'], 'TIMEOUT')
        self.assertEqual(result['phase'], 'numeric')
        self.assertIs(result['numerical_acceptance'], False)
        self.assertEqual(result['elapsed_seconds'], 2587.336054)

    def test_05_checkpoint_preserves_ids_and_receipt_limits(self):
        checkpoint = self.value['checkpoint.json']
        self.assertEqual(checkpoint['original_run'], {
            'run_id': '38952336951', 'job_id': '117146548710', 'artifact_id': '12071740663',
            'checkout_commit': 'ac3a074cd0e29342447844a7675425af628a39ef'})
        self.assertEqual(checkpoint['setup_completion']['classification'], 'SOURCE_ORDER_INFERENCE_ONLY')
        self.assertIs(checkpoint['setup_completion']['native_private_receipt_preserved'], False)
        self.assertIs(checkpoint['setup_completion']['independent_setup_or_native_verification'], False)

    def test_06_reject_all_fake_pass_statuses(self):
        for name in ('summary.json', 'progress.json'):
            for status in ('PASS', 'ACCEPTED', 'SUCCESS', 'TIMEOUT_PASS', 'timeout', True, None):
                value = copy.deepcopy(self.value[name]); value['status'] = status
                with self.subTest(name=name, status=status):
                    self.rejected_schema(name, value)

    def test_07_reject_all_acceptance_escalations(self):
        for field in ('numerical_acceptance', 'postflight_complete', 'full_29_node_acceptance',
                      'scala_executed', 'rtl_executed'):
            value = copy.deepcopy(self.value['summary.json']); value[field] = True
            with self.subTest(field=field):
                self.rejected_schema('summary.json', value)
        value = copy.deepcopy(self.value['summary.json'])
        value['cpu_eligibility']['backend_qualified'] = True
        self.rejected_schema('summary.json', value)

    def test_08_reject_false_started_flags(self):
        for field in ('numeric_started', 'clone_started', 'setup_started', 'enable_raw_kv', 'fresh_profile'):
            value = copy.deepcopy(self.value['summary.json']); value[field] = False
            with self.subTest(field=field):
                self.rejected_schema('summary.json', value)

    def test_09_reject_unknown_top_fields(self):
        for name in self.value:
            value = copy.deepcopy(self.value[name]); value['unapproved'] = 'private data'
            with self.subTest(name=name):
                self.rejected_schema(name, value)

    def test_10_reject_missing_top_fields(self):
        for name, original in self.value.items():
            for key in original:
                value = copy.deepcopy(original); del value[key]
                with self.subTest(name=name, field=key):
                    self.rejected_schema(name, value)

    def test_11_reject_unknown_fields_in_every_nested_object(self):
        def objects(value, path=()):
            if type(value) is dict:
                yield path
                for key, nested in value.items():
                    yield from objects(nested, path + (key,))
            elif type(value) is list:
                for index, nested in enumerate(value):
                    yield from objects(nested, path + (index,))
        for name, original in self.value.items():
            for path in objects(original):
                value = copy.deepcopy(original); target = value
                for key in path:
                    target = target[key]
                target['unknown_sensitive_field'] = 'must reject'
                with self.subTest(name=name, path=path):
                    self.rejected_schema(name, value)

    def test_12_reject_boolean_numeric_type_confusion(self):
        for name in ('summary.json', 'progress.json', 'source_hashes.json', 'checkpoint.json'):
            value = copy.deepcopy(self.value[name]); value['schema'] = True
            with self.subTest(name=name):
                self.rejected_schema(name, value)
        for field, replacement in [('rows', 128.0), ('elapsed_seconds', True),
                                   ('numerical_acceptance', 0), ('numeric_started', 1)]:
            value = copy.deepcopy(self.value['summary.json']); value[field] = replacement
            self.rejected_schema('summary.json', value)
        value = copy.deepcopy(self.value['summary.json'])
        value['diagnostic']['frames'][0]['line'] = 608.0
        self.rejected_schema('summary.json', value)

    def test_13_reject_changed_phase_elapsed_profile_and_checkout(self):
        for field, replacement in [('phase', 'complete'), ('elapsed_seconds', 2587.336055),
                                   ('profile', 'some-other-profile'), ('rows', 16),
                                   ('checkout_commit', '0' * 40), ('launch_contract_sha256', '0' * 64)]:
            value = copy.deepcopy(self.value['summary.json']); value[field] = replacement
            with self.subTest(field=field):
                self.rejected_schema('summary.json', value)

    def test_14_reject_changed_diagnostic(self):
        for replacement in [[], None, [{'line': 1, 'source': '/tmp/private.log'}], [1, 2, 3]]:
            value = copy.deepcopy(self.value['summary.json'])
            value['diagnostic']['frames'] = replacement
            self.rejected_schema('summary.json', value)
        value = copy.deepcopy(self.value['summary.json'])
        value['diagnostic']['exception'] = 'Success'
        self.rejected_schema('summary.json', value)

    def test_15_reject_arrays_logs_and_weights_fields(self):
        for name in self.value:
            for field, payload in [('weights', [0.1]), ('arrays', [[1, 2]]), ('log', 'private log'),
                                   ('native_receipt', {'status': 'PASS'})]:
                value = copy.deepcopy(self.value[name]); value[field] = payload
                with self.subTest(name=name, field=field):
                    self.rejected_schema(name, value)

    def test_16_reject_nonfinite_json(self):
        for token in (b'NaN', b'Infinity', b'-Infinity', b'1e9999', b'-1e9999'):
            for raw in (b'{"a":' + token + b'}', b'{"a":[{"b":' + token + b'}]}'):
                with self.subTest(raw=raw), self.assertRaises(evidence.EvidenceError):
                    evidence.strict_json(raw, 1024)

    def test_17_reject_duplicate_json_fields_at_any_depth(self):
        for raw in (b'{"schema":1,"schema":1}', b'{"a":{"status":"TIMEOUT","status":"PASS"}}',
                    b'{"a":[{"b":1,"b":2}]}'):
            with self.subTest(raw=raw), self.assertRaises(evidence.EvidenceError):
                evidence.strict_json(raw, 1024)

    def test_18_reject_malformed_nonobject_and_nonbytes_json(self):
        for raw in (b'', b'{', b'{} trailing', b'\xff', b'[]', b'null', b'42', '{}', bytearray(b'{}')):
            with self.subTest(raw=raw), self.assertRaises(evidence.EvidenceError):
                evidence.strict_json(raw, 1024)

    def test_19_reject_oversized_each_member_before_decoding(self):
        for name, limit in evidence.LIMITS.items():
            with self.subTest(name=name), self.assertRaisesRegex(evidence.EvidenceError, 'oversized'):
                evidence.validate_member(name, b' ' * (limit + 1))

    def test_20_reject_excessive_nesting(self):
        raw = b'{"x":' * 20 + b'0' + b'}' * 20
        with self.assertRaises(evidence.EvidenceError):
            evidence.strict_json(raw, 1024)

    def test_21_reject_semantically_same_but_different_member_bytes(self):
        # Reordering equal-length JSON retains schema but fails immutable byte identity.
        for name in evidence.MEMBERS:
            value = self.value[name]
            reordered = dict(reversed(list(value.items())))
            raw = (json.dumps(reordered, separators=(',', ':')) + '\n').encode()
            self.assertEqual(len(raw), len(self.raw[name]))
            self.assertNotEqual(raw, self.raw[name])
            with self.subTest(name=name), self.assertRaisesRegex(evidence.EvidenceError, 'byte identity'):
                evidence.validate_member(name, raw)

    def test_22_reject_unknown_filenames(self):
        for name in ('weights.bin', '../summary.json', 'PASS.json', 'SUMMARY.json'):
            with self.subTest(name=name), self.assertRaises(evidence.EvidenceError):
                evidence.validate_member(name, b'{}')

    def test_23_manifest_counts_are_fixed(self):
        source = self.value['source_hashes.json']
        self.assertEqual(len(source['source_sha256']), 283)
        self.assertEqual(len(source['generated_sha256']), 12)
        for group in evidence.KEYSETS:
            for replacement in ([], {}, None, 'hash'):
                value = copy.deepcopy(source); value[group] = replacement
                self.rejected_schema('source_hashes.json', value)

    def test_24_reject_unknown_manifest_key_even_at_same_count(self):
        for group in evidence.KEYSETS:
            value = copy.deepcopy(self.value['source_hashes.json'])
            key = next(iter(value[group])); digest = value[group].pop(key)
            value[group]['candidates/unknown.py'] = digest
            self.rejected_schema('source_hashes.json', value)

    def test_25_reject_unsafe_manifest_paths(self):
        for path in ('../secrets', '/tmp/log', 'a/../b', 'a//b', 'a/./b', 'a\\b',
                     'https://example.org/weights', 'a' * 257, ''):
            value = copy.deepcopy(self.value['source_hashes.json'])
            entries = value['generated_sha256']; key = next(iter(entries)); digest = entries.pop(key)
            entries[path] = digest
            with self.subTest(path=path):
                self.rejected_schema('source_hashes.json', value)

    def test_26_reject_invalid_manifest_hash_values(self):
        for digest in ('A' * 64, '0' * 63, '0' * 65, '../hash', None, True, [], {}):
            value = copy.deepcopy(self.value['source_hashes.json'])
            entries = value['source_sha256']; entries[next(iter(entries))] = digest
            with self.subTest(digest=digest):
                self.rejected_schema('source_hashes.json', value)

    def test_27_reject_valid_format_but_altered_manifest_digest(self):
        value = copy.deepcopy(self.value['source_hashes.json'])
        entries = value['source_sha256']; entries[next(iter(entries))] = '0' * 64
        evidence.validate_schema('source_hashes.json', value)
        raw = (json.dumps(value, separators=(',', ':')) + '\n').encode()
        with self.assertRaisesRegex(evidence.EvidenceError, 'byte identity'):
            evidence.validate_member('source_hashes.json', raw)

    def test_28_reject_checkpoint_provenance_or_acceptance_changes(self):
        for group, field, replacement in [
            ('original_run', 'artifact_id', '0'), ('archive', 'sha256', '0' * 64),
            ('recorded_facts', 'numerical_acceptance', True),
            ('recorded_facts', 'postflight_complete', True),
            ('setup_completion', 'classification', 'VERIFIED'),
            ('setup_completion', 'native_private_receipt_preserved', True),
        ]:
            value = copy.deepcopy(self.value['checkpoint.json']); value[group][field] = replacement
            with self.subTest(group=group, field=field):
                self.rejected_schema('checkpoint.json', value)

    def test_29_reject_directory_with_unexpected_missing_or_symlink_member(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for source in self.archive_root.iterdir():
                (root / source.name).write_bytes(source.read_bytes())
            extra = root / 'private.log'; extra.write_text('must not be archived')
            with self.assertRaises(evidence.EvidenceError):
                evidence.validate_directory(root)
            extra.unlink()
            summary = root / 'summary.json'; summary.unlink()
            with self.assertRaises(evidence.EvidenceError):
                evidence.validate_directory(root)
            summary.symlink_to(evidence.HERE / 'summary.json')
            with self.assertRaises(evidence.EvidenceError):
                evidence.validate_directory(root)

    def test_30_bounded_reader_rejects_oversize(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'oversized.json'; path.write_bytes(b'1234')
            with self.assertRaises(evidence.EvidenceError):
                evidence.read_bounded(path, 3)

    def test_31_zip_digest_checked_before_parsing(self):
        with mock.patch.object(evidence, 'read_bounded', return_value=b'X' * evidence.ZIP_BYTES), \
             mock.patch.object(evidence.zipfile, 'ZipFile', side_effect=AssertionError('must not parse')):
            with self.assertRaisesRegex(evidence.EvidenceError, 'ZIP identity'):
                evidence.validate_zip(Path('not-read.zip'))

    def test_32_cli_output_never_promotes_acceptance(self):
        with mock.patch('sys.argv', ['validate_evidence.py', '--directory', str(self.archive_root)]), \
             mock.patch('builtins.print') as printed:
            evidence.main()
        result = json.loads(printed.call_args.args[0])
        self.assertEqual(result['status'], 'TIMEOUT')
        self.assertIs(result['numerical_acceptance'], False)

    def test_33_validator_contains_no_assert_or_runtime_project_import(self):
        tree = ast.parse((evidence.HERE / 'validate_evidence.py').read_text())
        imports = set()
        for node in ast.walk(tree):
            self.assertNotIsInstance(node, ast.Assert)
            if isinstance(node, ast.Import):
                imports.update(alias.name.split('.')[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module.split('.')[0])
        self.assertLessEqual(imports, {'__future__', 'argparse', 'hashlib', 'io', 'json',
                                      'math', 'pathlib', 're', 'stat', 'zipfile'})

    def test_34_archive_validator_rejects_runtime_cache_directory(self):
        cache = self.archive_root / '__pycache__'
        cache.mkdir()
        try:
            with self.assertRaises(evidence.EvidenceError):
                evidence.validate_directory(self.archive_root)
        finally:
            cache.rmdir()


if __name__ == '__main__':
    unittest.main()
