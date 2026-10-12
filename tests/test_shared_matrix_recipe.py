"""Build provenance guards only; synthetic receipts never claim a real build."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('shared_recipe', ROOT / 'scripts/build_shared_matrix_recipe.py')
recipe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recipe)


class RecipeGuards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name).resolve()
        for name in recipe.SOURCES:
            p = self.repo / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('// synthetic provenance fixture\n' + name)
        self.compiler, self.library = self.repo / 'g++', self.repo / 'recipe.so'
        self.compiler.write_bytes(b'synthetic compiler identity')
        self.library.write_bytes(b'synthetic library identity; never loaded')
        self.receipt = self.repo / 'compile.json'
        self.good = dict(schema=1, status='PASS_HOST_BUILD_ONLY', repo=str(self.repo),
                         library=str(self.library), compiler=str(self.compiler),
                         compiler_sha256=recipe.sha(self.compiler),
                         argv=recipe.command(self.repo, self.compiler, self.library),
                         returncode=0, sources_before=recipe.source_hashes(self.repo),
                         sources_after=recipe.source_hashes(self.repo),
                         library_bytes=self.library.stat().st_size,
                         library_sha256=recipe.sha(self.library))
        self.save(self.good)

    def save(self, receipt):
        self.receipt.write_text(json.dumps(receipt))

    def check(self):
        return recipe.validate(self.repo, self.library, self.receipt)

    def test_matching_explicit_paths_and_hashes(self):
        self.assertEqual(self.check(), self.library)
        self.assertEqual(recipe.from_environment(self.repo, {
            'MATRIX_SERVICE_LIBRARY': str(self.library),
            'MATRIX_SERVICE_COMPILE_RECEIPT': str(self.receipt)}), self.library)

    def test_missing_environment_has_no_cached_fallback_or_skip(self):
        for env in ({}, {'MATRIX_SERVICE_LIBRARY': str(self.library)},
                    {'MATRIX_SERVICE_COMPILE_RECEIPT': str(self.receipt)}):
            with self.assertRaisesRegex(ValueError, 'explicit MATRIX_SERVICE'):
                recipe.from_environment(self.repo, env)

    def test_each_source_missing_extra_or_drift_fails(self):
        for field in ('sources_before', 'sources_after'):
            for name in recipe.SOURCES:
                for mode in ('missing', 'drift'):
                    r = copy.deepcopy(self.good)
                    if mode == 'missing':
                        del r[field][name]
                    else:
                        r[field][name] = '0' * 64
                    self.save(r)
                    with self.assertRaisesRegex(ValueError, 'source closure'):
                        self.check()
            r = copy.deepcopy(self.good)
            r[field]['unlisted.cpp'] = '0' * 64
            self.save(r)
            with self.assertRaisesRegex(ValueError, 'source closure'):
                self.check()

    def test_changed_binary_or_compiler_fails(self):
        for path, message in ((self.library, 'library identity'), (self.compiler, 'compiler identity')):
            before = path.read_bytes()
            path.write_bytes(before + b'drift')
            with self.assertRaisesRegex(ValueError, message):
                self.check()
            path.write_bytes(before)

    def test_failed_build_path_or_command_fails(self):
        variants = [('status', 'FAILED'), ('schema', 2), ('repo', '/other/checkout'),
                    ('library', '/other/recipe.so'), ('returncode', 1),
                    ('argv', self.good['argv'] + ['-ffast-math']),
                    ('argv', [x for x in self.good['argv'] if x != '-ffp-contract=off']),
                    ('argv', self.good['argv'][:-2] + ['extra.cpp', *self.good['argv'][-2:]])]
        for key, value in variants:
            r = copy.deepcopy(self.good)
            r[key] = value
            self.save(r)
            with self.assertRaises(ValueError):
                self.check()

    def test_workflow_builds_before_tests_and_preserves_receipt(self):
        text = (ROOT / '.github/workflows/qwen2-matrix-interface-frontend.yml').read_text()
        build = 'python scripts/build_shared_matrix_recipe.py --repo . --out work/matrix-interface-frontend/attention-tests'
        self.assertEqual(text.count(build), 1)
        self.assertLess(text.index(build), text.index('python -m unittest'))
        self.assertIn('work/matrix-interface-frontend/**/*.json', text)
        self.assertIn('test_shared_matrix_recipe.py -v', text)
        source = (ROOT / 'candidates/qwen2_resident_matrix/ffn_public/test_fullgraph_memory.py').read_text()
        self.assertIn('from_environment(ROOT)', source)
        self.assertNotIn('SkipTest', source)
        self.assertNotIn('work/', source)


if __name__ == '__main__':
    unittest.main()
