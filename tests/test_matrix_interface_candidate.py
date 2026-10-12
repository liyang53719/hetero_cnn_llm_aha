"""Small negative guards for the source-bound frontend runner; no RTL."""
import importlib.util
import ast
import re
import copy
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("matrix_frontend", ROOT/"scripts/check_matrix_interface_candidate.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def required_baseline_commits():
    """Source literals and source manifests are the authority, not Git depth."""
    commits = set()
    files = [ROOT/'scripts/check_matrix_interface_candidate.py',
             ROOT/'scripts/check_transposed_matrix_frontend.py']
    files += sorted((ROOT/runner.CANDIDATE).glob('*/check_frontend.py'))
    files.append(ROOT/runner.CANDIDATE/'ffn_public/check_numeric.py')
    for path in files:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in {'BASE', 'COMMIT', 'PUBLISHED_BASELINE'} for t in node.targets):
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    if re.fullmatch('[0-9a-f]{40}', node.value.value):
                        commits.add(node.value.value)
    for relative, keys in [('manifest.json', ('base_commit',)),
                           ('resident_manifest.json', ('base_commit',)),
                           ('transposed_route/manifest.json', ('source_base_commit',)),
                           ('transposed_owner/source_pins.json', ('source_commit', 'source_base_commit'))]:
        manifest = json.loads((ROOT/runner.CANDIDATE/relative).read_text())
        for key in keys:
            value = manifest[key]
            if not re.fullmatch('[0-9a-f]{40}', value):
                raise ValueError('unfrozen source baseline')
            commits.add(value)
    return commits


def validate_baseline_fetches(workflow, required):
    fetches = re.findall(r'^\s*git fetch --no-tags --depth=1 origin (\S+)\s*$', workflow, re.M)
    probes = re.findall(r'^\s*git cat-file -e ([0-9a-f]{40}):\S+\s*$', workflow, re.M)
    if set(fetches) != required or len(fetches) != len(required) or set(probes) != required:
        raise ValueError('explicit immutable baseline fetch/probe closure')
    if any(not re.fullmatch('[0-9a-f]{40}', ref) for ref in fetches):
        raise ValueError('unfrozen source baseline')


class CandidateRunnerGuards(unittest.TestCase):
    def test_workflow_fetches_all_frozen_source_baselines(self):
        workflow = (ROOT/'.github/workflows/qwen2-matrix-interface-frontend.yml').read_text()
        required = required_baseline_commits()
        self.assertEqual(len(required), 6)
        validate_baseline_fetches(workflow, required)

    def test_missing_or_changed_baseline_fetch_fails_closed(self):
        workflow = (ROOT/'.github/workflows/qwen2-matrix-interface-frontend.yml').read_text()
        for ref in required_baseline_commits():
            fetch = 'git fetch --no-tags --depth=1 origin ' + ref
            for broken in [workflow.replace(fetch, '# omitted baseline'),
                           workflow.replace(fetch, fetch[:-40]+'main'),
                           workflow.replace('git cat-file -e '+ref+':', 'git cat-file -e '+'0'*40+':')]:
                with self.subTest(ref=ref), self.assertRaisesRegex(ValueError, 'baseline'):
                    validate_baseline_fetches(broken, required_baseline_commits())

    def test_exact_bytes_and_drift(self):
        data = b"source\n"
        self.assertEqual(runner.checked(data, runner.digest(data), "x"), data)
        for other in [b"source", b"Source\n", b"source\n\0"]:
            with self.assertRaisesRegex(ValueError, "identity drift"):
                runner.checked(other, runner.digest(data), "x")

    def test_only_locations_are_normalized(self):
        a = "node a = add(x,y) @[one.scala 1:2]\nnode b = a\n"
        b = "node a = add(x,y) @[two.scala 91:22]\nnode b = a\n"
        self.assertEqual(runner.normalized_chirrtl(a), runner.normalized_chirrtl(b))
        self.assertNotEqual(runner.normalized_chirrtl(a), runner.normalized_chirrtl(b.replace("add", "sub")))
        literal = 'printf(clock, UInt<1>(1), " @[%d]", x)\n'
        self.assertEqual(runner.normalized_chirrtl(literal), literal)
        located = literal.rstrip('\n') + ' @[a.scala 1:2]\n'
        self.assertEqual(runner.normalized_chirrtl(located), literal)
        self.assertNotEqual(runner.normalized_chirrtl(located), runner.normalized_chirrtl(located.replace(', x)', ', y)')))
        escaped = 'printf(clock, UInt<1>(1), "\\\" @[%d]", x) @[a.scala 1:2]\n'
        self.assertEqual(runner.normalized_chirrtl(escaped), escaped.replace(' @[a.scala 1:2]', ''))

    def test_declaration_keeps_complete_nested_body(self):
        text = "class Before {}\nclass Wanted(x:Int) { val io=IO(new Bundle {val x=UInt(3.W)}) }\nclass After {}"
        self.assertEqual(runner.declaration(text, "Wanted"), "class Wanted(x:Int) { val io=IO(new Bundle {val x=UInt(3.W)}) }")
        with self.assertRaisesRegex(ValueError, "missing"):
            runner.declaration(text, "Missing")
        with self.assertRaisesRegex(ValueError, "unterminated"):
            runner.declaration("class Broken {", "Broken")

    def test_dependency_paths_fail_closed(self):
        good = "org/scala-lang/scala-library/2.13.16/scala-library-2.13.16.jar"
        sha = "a"*64
        self.assertEqual(runner.dependency_paths({good:sha,"unused.pom":sha}), {good:sha})
        for key, value in [("../escape.jar",sha),("/absolute.jar",sha),(good,"a"*63),(good,"A"*64)]:
            with self.assertRaisesRegex(ValueError, "dependency pin"):
                runner.dependency_paths({key:value})

    def test_existing_evidence_directory_is_not_overwritten(self):
        candidate = ROOT/runner.CANDIDATE
        with self.assertRaisesRegex(ValueError, "fresh output directory"):
            runner.run_gate(ROOT, candidate, candidate)

    def test_exact_manifest_source_set(self):
        manifest = json.loads((ROOT/runner.CANDIDATE/'manifest.json').read_text())
        runner.validate_manifest(manifest)
        for key in ['candidate_files', 'original_sources', 'patched_sources']:
            missing = copy.deepcopy(manifest)
            del missing[key][next(iter(missing[key]))]
            with self.assertRaisesRegex(ValueError, 'identity set'):
                runner.validate_manifest(missing)
            extra = copy.deepcopy(manifest)
            extra[key]['../unreviewed.scala'] = 'a'*64
            with self.assertRaisesRegex(ValueError, 'identity set'):
                runner.validate_manifest(extra)

    def test_declared_resources_detect_extra_state_or_array(self):
        types = ['UInt<3>', '{ a : UInt<32>, b : UInt<32>, c : UInt<32>, d : UInt<3>, e : UInt<8>}',
                 'UInt<9>', 'UInt<3>', 'UInt<5>', 'UInt<8>', 'UInt<1>', 'UInt<1>', 'UInt<1>']
        seed = '\n'.join(f'    reg r{i} : {kind}, clock' for i, kind in enumerate(types))
        service = '\n'.join(f'    inst leaves_{i} of qwen2_matrix_command_endpoint_{i}\n    inst gate_{i} of tc_clk_gating_{i}' for i in range(8))
        service += '\n    cmem ram : { returnTag : UInt<16>} [8]\n    reg storage : { returnTag : UInt<16>} [2], clock\n'
        self.assertEqual(runner.structural_counts(seed, service)['added_tag_storage_bits'], 160)
        for changed in [seed+'\n    inst extra of FakeFMA', seed+'\n    cmem payload : UInt<512>[4]', seed.replace('UInt<9>', 'UInt<10>')]:
            with self.assertRaises(ValueError):
                runner.structural_counts(changed, service)
        with self.assertRaisesRegex(ValueError, 'retained resource'):
            runner.structural_counts(seed, service.replace('leaves_7', 'hidden_extra'))
        with self.assertRaisesRegex(ValueError, 'tag storage'):
            runner.structural_counts(seed, service.replace('[2]', '[3]'))


if __name__ == "__main__":
    unittest.main()
