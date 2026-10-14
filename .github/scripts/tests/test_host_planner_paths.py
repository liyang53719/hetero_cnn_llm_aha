"""Cold Host path-policy checks: no Git history, compilers or numerical runs."""
from functools import lru_cache
from pathlib import Path
import re
import unittest

import yaml

PROJECT = 'chisel/continuous_prefill/'
WORKFLOWS = {
    'host-bf16-v.yml', 'host-bf16-qkv-rope.yml',
    'host-bf16-attention-core.yml', 'host-bf16-attention-block.yml',
    'host-bf16-gdn.yml', 'host-bf16-gdn-core.yml', 'host-bf16-gdn-block.yml',
}
EXCLUDED = {PROJECT + 'scripts/' + name for name in (
    'plan_continuous_suites.py', 'test_plan_continuous_suites.py',
    'run_continuous_ci_gate.sh',
)}
PROTECTED = [PROJECT + path for path in (
    'src/main/scala/heteronpu/continuous/Qwen2Block.scala',
    'src/main/scala/heteronpu/continuous/QwenOwnerProtocol.scala',
    'src/main/scala/heteronpu/continuous/GdnRmsNormFixedBankOwner.scala',
    'src/main/scala/heteronpu/continuous/NewDependency.scala',
    'src/test/scala/heteronpu/continuous/ElementwiseRegisterLoanReplaySpec.scala',
    'src/test/scala/heteronpu/continuous/GdnRmsNormFixedBankReplaySpec.scala',
    'src/test/scala/heteronpu/continuous/GdnRmsNormFixedBankOwnerSpec.scala',
    'src/test/scala/heteronpu/continuous/NewControlSpec.scala',
    'src/main/resources/new_rom.bin', 'src/test/resources/new_fixture.json',
    'build.sbt', 'project/build.properties', 'project/plugins.sbt',
    'scripts/run_host_bf16_gdn_gate.sh', 'tests/host_bf16_gdn_block.cpp',
    'scripts/production_source_identity.py', 'unknown/new_dependency.any',
    'scripts/plan_continuous_suites_future.py',
)]
CLASSIFIERS = ['.github/scripts/' + name for name in (
    'host_attention_block_ci_scope.py', 'tests/test_host_attention_block_ci_scope.py',
)]
ATTENTION_CHECKS = ['.github/scripts/' + name for name in (
    'attention_readonly_ci_scope.py', 'tests/test_attention_readonly_ci_scope.py',
    'verify_attention_block_split.py', 'tests/test_attention_block_split_acceptance.py',
)]


def repository_root():
    # Works in its installed repository path or when run as an external draft
    # with the repository as the current directory. Never consult Git history.
    candidates = (*Path(__file__).resolve().parents, Path.cwd(), *Path.cwd().parents)
    for path in candidates:
        if (path / 'pyproject.toml').is_file() and (path / '.github/workflows').is_dir():
            return path
    raise RuntimeError('Run from the repository or install under .github/scripts/tests')


@lru_cache(None)
def pattern_regex(pattern):
    # Only the literal/*/** subset used by this policy is implemented. New
    # unsupported glob syntax fails the cold gate instead of guessing a skip.
    if any(char in pattern for char in '?[]+{}!\\'):
        raise ValueError('Unaudited path-filter syntax: ' + pattern)
    result = ''; index = 0
    while index < len(pattern):
        if pattern[index:index + 3] == '**/':
            result += '(?:.*/)?'; index += 3
        elif pattern[index:index + 2] == '**':
            result += '.*'; index += 2
        elif pattern[index] == '*':
            result += '[^/]*'; index += 1
        else:
            result += re.escape(pattern[index]); index += 1
    return re.compile(result)


def matches(patterns, path):
    included = False
    for pattern in patterns:
        negative = pattern.startswith('!')
        if pattern_regex(pattern[1:] if negative else pattern).fullmatch(path):
            included = not negative
    return included


class HostPlannerPathsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = repository_root() / '.github/workflows'
        cls.flows = {path.name: yaml.load(path.read_text(), Loader=yaml.BaseLoader)
                     for path in directory.glob('host-bf16-*.yml')}
        cls.continuous = yaml.load((directory / 'chisel-continuous-prefill.yml').read_text(),
                                   Loader=yaml.BaseLoader)

    def test_exact_seven_hosts_keep_dispatch_and_original_runs(self):
        self.assertEqual(set(self.flows), WORKFLOWS)
        for name, flow in self.flows.items():
            with self.subTest(workflow=name):
                self.assertIn('workflow_dispatch', flow['on'])
                self.assertEqual(flow['on']['push']['branches'], ['main'])
                self.assertEqual(flow['concurrency']['cancel-in-progress'], 'false')

    def test_only_three_exact_exclusions_keep_the_broad_project_trigger(self):
        for name, flow in self.flows.items():
            with self.subTest(workflow=name):
                push = flow['on']['push']; patterns = push['paths']
                self.assertNotIn('paths-ignore', push)
                self.assertIn(PROJECT + '**', patterns)
                negatives = [path[1:] for path in patterns if path.startswith('!')]
                self.assertEqual(len(negatives), 3)
                self.assertEqual(set(negatives), EXCLUDED)
                for pattern in patterns:
                    pattern_regex(pattern[1:] if pattern.startswith('!') else pattern)

    def test_planner_only_changes_do_not_trigger_hosts(self):
        for name, flow in self.flows.items():
            for path in EXCLUDED:
                with self.subTest(workflow=name, path=path):
                    self.assertFalse(matches(flow['on']['push']['paths'], path))

    def test_production_tests_build_resources_and_unknown_changes_trigger_hosts(self):
        for name, flow in self.flows.items():
            for path in PROTECTED:
                with self.subTest(workflow=name, path=path):
                    self.assertTrue(matches(flow['on']['push']['paths'], path))

    def test_mixed_planner_and_production_changes_trigger_all_hosts(self):
        for name, flow in self.flows.items():
            for source in PROTECTED[:3]:
                with self.subTest(workflow=name, source=source):
                    changed = [*EXCLUDED, source]
                    self.assertTrue(any(matches(flow['on']['push']['paths'], p) for p in changed))

    def test_continuous_gate_still_covers_planners_and_protected_project_files(self):
        patterns = self.continuous['on']['push']['paths']
        for path in [*EXCLUDED, *PROTECTED]:
            with self.subTest(path=path):
                self.assertTrue(matches(patterns, path))

    def test_classifier_and_attention_verifier_changes_have_triggers(self):
        for name, flow in self.flows.items():
            required = CLASSIFIERS + (ATTENTION_CHECKS if name == 'host-bf16-attention-block.yml' else [])
            for path in required:
                with self.subTest(workflow=name, path=path):
                    self.assertTrue(matches(flow['on']['push']['paths'], path))

    def test_host_steps_do_not_directly_invoke_excluded_helpers(self):
        for name, flow in self.flows.items():
            commands = '\n'.join(step.get('run', '') for job in flow['jobs'].values()
                                 for step in job.get('steps', []))
            for path in EXCLUDED:
                with self.subTest(workflow=name, path=path):
                    self.assertNotIn(Path(path).name, commands)

    def test_matcher_preserves_order_and_path_segment_boundaries(self):
        self.assertFalse(matches(['a/**', '!a/skip.py'], 'a/skip.py'))
        self.assertTrue(matches(['a/**', '!a/skip.py', 'a/skip.py'], 'a/skip.py'))
        self.assertFalse(matches(['a/*.py'], 'a/nested/file.py'))
        self.assertTrue(matches(['a/**/*.py'], 'a/file.py'))
        self.assertTrue(matches(['a/**/*.py'], 'a/nested/file.py'))
        with self.assertRaises(ValueError):
            matches(['a/[ab].py'], 'a/a.py')


if __name__ == '__main__':
    unittest.main(verbosity=2)
