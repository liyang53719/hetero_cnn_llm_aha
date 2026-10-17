#!/usr/bin/env python3
"""Separate adapter tests for the exact fixed published member-byte route.

The supplied archive checkout and source view are read-only test inputs. Every
negative fixture is copied privately. No Git, network or numerical execution.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = Path(__file__).absolute().parent
path = HERE / 'verify_archived_members.py'
A = types.ModuleType('archived_member_adapter')
A.__file__ = str(path)
exec(compile(path.read_bytes(), str(path), 'exec'), A.__dict__)
B = A.B
ARCHIVE_CHECKOUT = None
FREEZE = None


class ArchivedMemberTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.publication, cls.members = A.load_publication()
        cls.fixture = {}
        fd = B.open_directory(ARCHIVE_CHECKOUT)
        try:
            for name, digest in cls.members.items():
                raw, _ = B.read_checked(fd, name)
                B.need(B.sha(raw) == digest, 'TEST_ARCHIVE_PIN')
                cls.fixture[name] = raw
        finally:
            os.close(fd)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='archived-member-tests-')
        self.root = Path(self.temp.name)
        self.checkout = self.root / 'checkout'
        for name, raw in self.fixture.items():
            path = self.checkout / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as stream:
                stream.write(raw)
        self.archive = self.checkout / A.PREFIX
        self.output = self.root / 'result.json'

    def tearDown(self):
        self.temp.cleanup()

    def reject(self, code=None, package=HERE, freeze=None):
        context = self.assertRaisesRegex(ValueError, code) if code else self.assertRaises((ValueError, OSError))
        with context:
            A.verify(self.checkout, freeze or FREEZE, package)

    def copied_package(self):
        target = self.root / 'package'
        shutil.copytree(HERE, target, copy_function=shutil.copyfile)
        return target

    def cli(self, *, optimized=False, extra=(), script=None, output=None):
        return subprocess.run([sys.executable, '-I', '-B', *(['-O'] if optimized else []),
            str(script or HERE / 'verify_archived_members.py'), '--archive-checkout', str(self.checkout),
            '--freeze', str(FREEZE), '--out', str(output or self.output), *extra],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)

    def test_01_exact_historical_members(self):
        report = A.verify(self.checkout, FREEZE)
        self.assertEqual(report['status'], 'PASS_ARCHIVED_MEMBER_BINDING')
        self.assertEqual(len(report['archive_members']), 10)
        self.assertEqual(len(report['receipt_files']), 8)
        self.assertEqual(report['stable_identity_sha256'], '7fa82000bb935e651f517f77f50c3c37b9be457a81749129500b6e93e71b6562')
        self.assertEqual(report['publication'], self.publication)
        self.assertEqual(report['original_zip_sha256_recorded'], A.ORIGINAL_ZIP_SHA)
        for flag in ('original_zip_bytes_read', 'original_zip_digest_recomputed', 'zip_container_recovered',
                     'local_git_head_authenticated', 'github_metadata_independently_fetched',
                     'private_tensor_bytes_replayed', 'private_qualification_bytes_replayed',
                     'private_process_proofs_replayed', 'numerical_execution_performed',
                     'full_29_node_acceptance', 'rtl_execution', 'hardware_acceptance',
                     'future_job_admission_authority'):
            self.assertIs(report[flag], False, flag)

    def test_02_missing_member(self):
        (self.archive / 'README.md').unlink()
        self.reject('ARCHIVE_INVENTORY')

    def test_03_extra_member(self):
        (self.archive / 'extra.json').write_bytes(b'{}')
        self.reject('ARCHIVE_INVENTORY')

    def test_04_stale_bytecode_extra(self):
        (self.archive / 'verify_artifact.pyc').write_bytes(b'not code')
        self.reject('ARCHIVE_INVENTORY')

    def test_05_mutated_identity(self):
        (self.archive / 'replay_identity.json').write_bytes(b'{}')
        self.reject('ARCHIVE_MEMBER_PIN')

    def test_06_manifest_claims_cannot_grant_pass(self):
        manifest = json.loads((self.archive / 'MANIFEST.json').read_bytes())
        manifest['verification_scope']['full_29_node_acceptance'] = True
        (self.archive / 'MANIFEST.json').write_bytes(B.encoded(manifest))
        self.reject('ARCHIVE_MEMBER_PIN')

    def test_07_readme_is_pinned_too(self):
        with (self.archive / 'README.md').open('ab') as stream:
            stream.write(b'\nchanged\n')
        self.reject('ARCHIVE_MEMBER_PIN')

    def test_08_hardlink_member(self):
        os.link(self.archive / 'summary.json', self.root / 'alias')
        self.reject('FILE_TYPE_SIZE')

    def test_09_symlink_member(self):
        target = self.root / 'target'
        (self.archive / 'summary.json').rename(target)
        (self.archive / 'summary.json').symlink_to(target)
        self.reject()

    def test_10_symlink_archive_directory(self):
        target = self.root / 'target'
        self.archive.rename(target)
        self.archive.symlink_to(target, target_is_directory=True)
        self.reject()

    def test_11_oversize_member(self):
        with (self.archive / 'summary.json').open('wb') as stream:
            stream.truncate(B.MAX_FILE + 1)
        self.reject('FILE_TYPE_SIZE')

    def test_12_wrong_map(self):
        package = self.copied_package()
        (package / 'ARCHIVED_MEMBER_HASHES.json').write_bytes(b'{}\n')
        self.reject('ARCHIVE_MAP_PIN', package=package)

    def test_13_caller_repin_rejected(self):
        package = self.copied_package()
        pins = json.loads((package / 'archive_publication.json').read_bytes())
        pins['publication_commit'] = '0' * 40
        (package / 'archive_publication.json').write_bytes(B.encoded(pins))
        self.reject('PUBLICATION_PIN', package=package)

    def test_14_pending_publication_fails_closed(self):
        package = self.copied_package()
        pins = json.loads((package / 'archive_publication.json').read_bytes())
        pins.update(status='PENDING_AUTHENTICATED_PUBLICATION', publication_commit=None, publication_tree=None)
        raw = B.encoded(pins)
        (package / 'archive_publication.json').write_bytes(raw)
        # Only this test's in-memory constant changes to exercise the pending state.
        with mock.patch.object(A, 'PUBLICATION_SHA', B.sha(raw)):
            self.reject('PUBLICATION_NOT_AUTHENTICATED', package=package)

    def test_15_verifier_source_mutation(self):
        package = self.copied_package()
        with (package / 'verify_artifact.py').open('ab') as stream:
            stream.write(b'\n# mutation\n')
        self.reject('VERIFIER_PIN', package=package)

    def test_16_schema_source_mutation(self):
        package = self.copied_package()
        with (package / 'identity_schema.py').open('ab') as stream:
            stream.write(b'\n# mutation\n')
        self.reject('VALIDATOR_SOURCE_PIN', package=package)

    def test_17_missing_source_view(self):
        self.reject(freeze=self.root / 'missing-view')

    def test_18_normal_cli(self):
        process = self.cli()
        self.assertEqual(process.returncode, 0, process.stderr.decode())
        report = json.loads(self.output.read_bytes())
        self.assertEqual(report['verification_route'], 'ARCHIVED_MEMBER_BINDING')
        self.assertFalse(report['zip_container_recovered'])
        self.assertFalse(list(self.root.rglob('*.pyc')))

    def test_19_optimized_cli(self):
        process = self.cli(optimized=True)
        self.assertEqual(process.returncode, 0, process.stderr.decode())
        self.assertFalse(json.loads(self.output.read_bytes())['original_zip_digest_recomputed'])

    def test_20_output_no_overwrite(self):
        self.output.write_bytes(b'KEEP')
        process = self.cli()
        self.assertNotEqual(process.returncode, 0)
        self.assertIn(b'OUTPUT_EXISTS', process.stderr)
        self.assertEqual(self.output.read_bytes(), b'KEEP')

    def test_21_no_caller_digest_or_publication_override(self):
        for extra in (('--artifact-sha256', '0'*64), ('--publication-commit', '0'*40)):
            process = self.cli(extra=extra)
            self.assertNotEqual(process.returncode, 0)
            self.assertFalse(self.output.exists())

    def test_22_output_not_in_archive(self):
        process = self.cli(output=self.archive / 'new.json')
        self.assertNotEqual(process.returncode, 0)
        self.assertIn(b'OUTPUT_INPUT_OVERLAP', process.stderr)
        self.assertFalse((self.archive / 'new.json').exists())

    def test_23_helper_pin_before_source_execution(self):
        package = self.copied_package()
        (package / 'build_source_view.py').write_bytes(b'raise RuntimeError("must not execute")\n')
        process = self.cli(script=package / 'verify_archived_members.py')
        self.assertNotEqual(process.returncode, 0)
        self.assertIn(b'BUILDER_PIN', process.stderr)
        self.assertNotIn(b'RuntimeError: must not execute', process.stderr)

    def test_24_same_bytes_replacement_during_validation(self):
        original = A.load_verifier
        def hooked(package=HERE):
            verifier = original(package)
            validate = verifier.validate_provenance
            def replace(*args):
                validate(*args)
                path = self.archive / 'summary.json'
                target = self.root / 'replacement'
                target.write_bytes(path.read_bytes())
                target.replace(path)
            verifier.validate_provenance = replace
            return verifier
        with mock.patch.object(A, 'load_verifier', hooked):
            self.reject('ARCHIVE_DRIFT')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-checkout', required=True, type=Path)
    parser.add_argument('--freeze', required=True, type=Path)
    args, remainder = parser.parse_known_args()
    ARCHIVE_CHECKOUT = args.archive_checkout
    FREEZE = args.freeze
    unittest.main(argv=[sys.argv[0], *remainder], verbosity=2)
