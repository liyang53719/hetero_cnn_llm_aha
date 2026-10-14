#!/usr/bin/env python3
"""Cold, standard-library tests. Run identically with python and python -O.

All mutations are confined to private temporary work copies or mocked reads.
No live sources, original evidence, pinned artifacts, index, or commits change.
"""
from pathlib import Path
import copy
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location('public21_source_gate', HERE / 'compose.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class SourceCompositionGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest, cls.overlay, cls.assets, cls.compile_evidence = c.load_inputs()
        cls.head = c.git(ROOT, 'rev-parse', 'HEAD').decode().strip()
        cls.groups = c.repo_inputs(cls.manifest, cls.overlay, cls.compile_evidence)
        cls.frozen, cls.consumed = c.verify_repo(ROOT, cls.groups, cls.head)
        cls.temp = tempfile.TemporaryDirectory(prefix='public21-cold-tests-', dir=ROOT / 'work')
        cls.work = Path(cls.temp.name)
        cls.out = cls.work / 'composed'
        cls.report = c.compose(ROOT, cls.out)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def copy_candidate(self, suffix):
        dest = self.work / suffix
        shutil.copytree(HERE, dest, ignore=shutil.ignore_patterns('__pycache__'))
        return dest

    def test_real_current_head_and_exact_source_contract(self):
        self.assertEqual(self.report['execution_head'], self.head)
        self.assertEqual(self.report['status'], 'PASS_SOURCE_COMPOSITION_ONLY')
        self.assertFalse(self.report['execution_head_is_semantic_proof'])
        self.assertFalse(self.report['compile_inputs_ready'])
        contract = json.loads((self.out / 'compile_inputs.json').read_bytes())
        self.assertEqual(len(contract['compile_sources']), 91)
        self.assertEqual(len(contract['test_sources']), 2)
        self.assertEqual(len(set(contract['compile_sources'])), 91)
        self.assertEqual(sum(p.startswith('source/') for p in contract['compile_sources']), 71)
        self.assertEqual(sum(p.startswith('hardfloat_snapshot/') for p in contract['compile_sources']), 20)
        self.assertFalse(contract['fixture_generated'])
        self.assertFalse(contract['compiled'])
        self.assertFalse(contract['rtl_simulated'])

    def test_fixed_base_and_execution_working_sources_all_match(self):
        self.assertEqual(self.overlay['base_commit'], c.BASE_COMMIT)
        self.assertEqual(len(self.overlay['before_sha256']), 76)
        self.assertEqual(len(self.overlay['original_patch_order']), 15)
        self.assertEqual(len(self.overlay['changed_sources']), 20)
        self.assertGreaterEqual(len(self.consumed), 113)

    def test_metadata_only_execution_head_has_no_brittle_allowlist(self):
        actual = c.git
        alternate = 'f' * 40
        def read(repo, *args):
            if args == ('rev-parse', 'HEAD'):
                return (alternate + '\n').encode()
            if args[0] == 'show' and args[1].startswith(alternate + ':'):
                return actual(repo, 'show', self.head + ':' + args[1].split(':', 1)[1])
            return actual(repo, *args)
        with mock.patch.object(c, 'git', side_effect=read):
            report = c.compose(ROOT, self.work / 'metadata-head')
        self.assertEqual(report['execution_head'], alternate)
        self.assertFalse(report['execution_head_is_semantic_proof'])

    def test_manifest_and_every_candidate_asset_tamper_rejected(self):
        for index, name in enumerate(['pinned_source_manifest.json', *self.manifest['asset_sha256']]):
            with self.subTest(name=name):
                candidate = self.copy_candidate('asset-tamper-' + str(index))
                path = candidate / name
                original = path.read_bytes()
                path.write_bytes(original + b'\n')
                with self.assertRaisesRegex(ValueError, 'identity drift'):
                    c.load_inputs(candidate)
                self.assertEqual(path.read_bytes(), original + b'\n')  # no automatic pin/patch refresh

    def test_working_byte_drift_rejected_without_mutating_live_tree(self):
        name = next(iter(self.overlay['before_sha256']))
        root = self.work / 'drift-copy'; target = root / name
        target.parent.mkdir(parents=True); target.write_bytes(self.frozen[name] + b'\n')
        actual = c.git
        with mock.patch.object(c, 'git', side_effect=lambda _repo, *args: actual(ROOT, *args)):
            with self.assertRaisesRegex(ValueError, 'current working source'):
                c.verify_repo(root, [(c.BASE_COMMIT, {name: self.overlay['before_sha256'][name]})], self.head)
        self.assertEqual((ROOT / name).read_bytes(), self.frozen[name])

    def test_execution_head_consumed_drift_rejected(self):
        actual = c.git
        name = next(iter(self.overlay['before_sha256']))
        def read(repo, *args):
            if args == ('show', self.head + ':' + name):
                return b'drifted execution source'
            return actual(repo, *args)
        with mock.patch.object(c, 'git', side_effect=read):
            with self.assertRaisesRegex(ValueError, 'execution HEAD source'):
                c.verify_repo(ROOT, [(c.BASE_COMMIT, {name: self.overlay['before_sha256'][name]})], self.head)

    def test_fixed_git_source_drift_rejected(self):
        name = next(iter(self.overlay['before_sha256']))
        with mock.patch.object(c, 'git', return_value=b'wrong fixed source'):
            with self.assertRaisesRegex(ValueError, 'fixed Git source'):
                c.verify_repo(ROOT, [(c.BASE_COMMIT, {name: self.overlay['before_sha256'][name]})], self.head)

    def test_full_helper_and_patch_provenance_is_consumed(self):
        for pins in (self.overlay['original_patch_sha256'], self.overlay['composition_helper_sha256']):
            for name, digest in pins.items():
                self.assertEqual(self.consumed[name], digest)
        helper = next(iter(self.overlay['composition_helper_sha256']))
        actual = c.read_regular
        def read(root, name):
            data = actual(root, name)
            return data + b'\n' if root == ROOT and name == helper else data
        with mock.patch.object(c, 'read_regular', side_effect=read):
            with self.assertRaisesRegex(ValueError, 'current working source'):
                c.verify_repo(ROOT, [(c.BASE_COMMIT, {helper: self.consumed[helper]})], self.head)

    def test_patch_exact_context_no_fuzz_no_offset(self):
        source = {'x.scala': b'a\nb\nc\n'}
        valid = b'--- a/x.scala\n+++ b/x.scala\n@@ -1,3 +1,3 @@\n a\n-b\n+B\n c\n'
        self.assertEqual(c.strict_patch(source, valid, ['x.scala']), {'x.scala': b'a\nB\nc\n'})
        for patch in (valid.replace(b'@@ -1,3 +1,3', b'@@ -2,3 +2,3'),
                      valid.replace(b' a\n', b' z\n'), valid.replace(b'@@ -1,3 +1,3', b'@@ -1,4 +1,3')):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                c.strict_patch(source, patch, ['x.scala'])

    def test_unsafe_source_paths_and_patch_scope_rejected(self):
        for name in ('../x', '/x', 'a/../x', 'a//x', './x', 'x\\y', 'x\ny', '', '.', 'a/.'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'unsafe path'):
                c.relative(name)
        patch = b'--- a/../x\n+++ b/../x\n@@ -1 +1 @@\n-a\n+b\n'
        with self.assertRaisesRegex(ValueError, 'unsafe path'):
            c.strict_patch({'../x': b'a\n'}, patch, ['../x'])
        with self.assertRaisesRegex(ValueError, 'patch target scope'):
            c.strict_patch({p: self.frozen[p] for p in self.overlay['before_sha256']},
                           self.assets['current_overlay.patch'], [c.HOST])

    def test_symlink_candidate_and_consumed_source_rejected(self):
        candidate = self.copy_candidate('symlink-candidate')
        original = candidate / 'current_overlay.patch'; original.unlink()
        original.symlink_to(HERE / 'current_overlay.patch')
        with self.assertRaisesRegex(ValueError, 'symlink input'):
            c.load_inputs(candidate)
        root = self.work / 'symlink-source'; root.mkdir()
        (root / 'source').symlink_to(ROOT / 'chisel', target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink input'):
            c.read_regular(root, 'source/continuous_prefill/src/main/scala/heteronpu/continuous/HostBlockCommands.scala')

    def test_fresh_output_no_overwrite_or_path_escape(self):
        receipt = (self.out / 'source_receipt.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'fresh output'):
            c.compose(ROOT, self.out)
        self.assertEqual((self.out / 'source_receipt.json').read_bytes(), receipt)
        for path in (ROOT / 'candidates/unsafe-output', ROOT / 'work', self.work / '..' / 'unsafe'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                c.output_path(ROOT, path)
        link = self.work / 'output-link'; link.symlink_to(self.work, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink output'):
            c.output_path(ROOT, link / 'escaped')

    def test_final_postimages_only_explicit_deltas_no_old_kernel_copy(self):
        actual = {}
        for name, digest in self.manifest['final_post_sha256'].items():
            data = (self.out / 'source' / name).read_bytes()
            self.assertEqual(c.sha(data), digest)
            actual[name] = data
        baseline = {name: self.frozen[name] for name in self.overlay['before_sha256']}
        first = c.strict_patch(baseline, self.assets['current_overlay.patch'], self.overlay['changed_sources'])
        self.assertEqual(sorted(p for p in first if first[p] != baseline[p]), sorted(self.overlay['changed_sources']))
        self.assertEqual([p for p in first if actual[p] != first[p]], [c.HOST])
        self.assertTrue(self.report['no_historical_kernel_file_copied'])

    def test_loan_and_borrower_defaults_and_92_current_lines_preserved(self):
        self.assertFalse(self.report['h2048_borrower_default'])
        self.assertFalse(self.report['elementwise_loan_default'])
        audit = self.report['audit']
        self.assertEqual(audit['current_added_feature_lines'], 92)
        self.assertEqual(audit['explicit_feature_line_adaptations'], 8)
        self.assertEqual(audit['conflict_resolutions'], 9)
        self.assertEqual(audit['default_policy'], 'LegacyV0')
        for name in self.overlay['unchanged_current_new_sources']:
            self.assertEqual((self.out / 'source' / name).read_bytes(), self.frozen[name])
        host = (self.out / 'source' / c.HOST).read_text()
        self.assertIn('scanAttention=if(enableResidentFfn && officialBf16)', host)
        self.assertIn('enableResidentFfn:Boolean=false', host)

    def test_external_hardfloat_missing_or_extra_sources_rejected(self):
        hf = self.work / 'wrong-hardfloat'; hf.mkdir()
        with self.assertRaisesRegex(ValueError, 'external HardFloat source set drift'):
            c.compose(ROOT, self.work / 'wrong-hardfloat-output', hf)
        self.assertFalse((self.work / 'wrong-hardfloat-output').exists())

    def test_external_hardfloat_byte_drift_rejected_even_with_exact_count(self):
        hf = self.work / 'exact-count-wrong-hardfloat'; hf.mkdir()
        for name in self.compile_evidence['hardfloat_sha256']:
            p = hf / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b'wrong source bytes\n')
        with self.assertRaisesRegex(ValueError, 'identity drift: external HardFloat'):
            c.compose(ROOT, self.work / 'drifted-hardfloat-output', hf)
        self.assertFalse((self.work / 'drifted-hardfloat-output').exists())

    def test_rtl_flag_fails_closed_without_silent_source_success(self):
        result = subprocess.run([sys.executable, str(HERE / 'compose.py'), '--run-rtl',
                                 '--out', str(self.work / 'never-rtl')], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('RTL execution is not part', result.stderr)
        self.assertFalse((self.work / 'never-rtl').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
