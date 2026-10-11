"""Small negative guards for the source-bound frontend runner; no RTL."""
import importlib.util
import copy
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("matrix_frontend", ROOT/"scripts/check_matrix_interface_candidate.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class CandidateRunnerGuards(unittest.TestCase):
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
