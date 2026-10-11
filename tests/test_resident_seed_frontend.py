"""Fail-closed source and port guards for the frontend-only reader candidate."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"scripts"))
import check_resident_seed_frontend as runner


class ResidentFrontendGuards(unittest.TestCase):
    def test_exact_manifest_sets_and_hashes(self):
        manifest = json.loads((ROOT/runner.CANDIDATE/"resident_manifest.json").read_text())
        runner.validate_manifest(manifest)
        for field in ["candidate_files", "original_sources", "seed_dependencies", "patched_sources"]:
            for operation in ["missing", "extra", "bad_hash"]:
                changed = copy.deepcopy(manifest)
                name = next(iter(changed[field]))
                if operation == "missing":
                    del changed[field][name]
                elif operation == "extra":
                    changed[field]["../unreviewed.scala"] = "a"*64
                else:
                    changed[field][name] = "not a SHA256"
                with self.subTest(field=field, operation=operation), self.assertRaises(ValueError):
                    runner.validate_manifest(changed)

    def test_owner_abi_boundary_is_exact_and_fail_closed(self):
        source = (ROOT/runner.PREFIX/"QwenOwnerProtocol.scala").read_text()
        abi = runner.owner_abi(source)
        self.assertIn("object QwenOwnerKind", abi)
        self.assertIn("class QwenOwnerJob", abi)
        self.assertIn("class QwenOwnerResult", abi)
        self.assertNotIn("class QwenOwnerKernel", abi)
        self.assertTrue(source.startswith(abi))
        for bad in [source.replace("/** No block launch is exposed.", "/* moved"),
                    source+"\n/** No block launch is exposed.",
                    source.replace("class QwenOwnerResult", "class Unreviewed {}\nclass QwenOwnerResult")]:
            with self.assertRaises(ValueError):
                runner.owner_abi(bad)

    def test_module_boundaries_do_not_hide_neighbor_resources(self):
        text = "circuit Test :\n  module One :\n    reg x : UInt<5>, clock\n  extmodule Other :\n    output a : UInt<32>\n  module Last :\n    reg y : UInt<8>, clock\n"
        self.assertEqual(runner.register_bits(runner.module(text, "One")), 5)
        self.assertEqual(runner.register_bits(runner.module(text, "Last")), 8)
        with self.assertRaisesRegex(ValueError, "missing frontend module"):
            runner.module(text, "Other")

    def test_register_ledger_rejects_unhandled_storage(self):
        self.assertEqual(runner.register_bits("    reg x : {a : UInt<32>, b : UInt<8>}, clock\n"), 40)
        for kind in ["UInt<32>[5]", "SInt<32>", "Clock", "{a : UInt<8>[2]}"]:
            with self.assertRaisesRegex(ValueError, "unhandled register"):
                runner.register_bits("    reg x : "+kind+", clock\n")

    def test_memory_identity_preserves_width_depth_and_name(self):
        before = "    smem banks : UInt<256>[1024], undefined @[one.scala 1:2]\n"
        self.assertEqual(runner.memory_declarations(before), runner.memory_declarations(before.replace("one.scala 1:2", "two.scala 4:9")))
        for changed in [before.replace("1024", "1025"), before.replace("256", "512"), before.replace("banks", "other")]:
            self.assertNotEqual(runner.memory_declarations(before), runner.memory_declarations(changed))

    def test_existing_evidence_is_never_overwritten(self):
        with self.assertRaisesRegex(ValueError, "fresh output directory"):
            runner.run_gate(ROOT, ROOT/runner.CANDIDATE, ROOT/runner.CANDIDATE)

    def test_generated_assertion_only_source_coordinate_normalization(self):
        source = 'assert(x,"message")\n'
        current = '\n\n'+source
        def diagnostic(line, code=source.strip(), message='message', operand='UInt<1>(1)'):
            literal = json.dumps(f'Assertion failed: {message}\n    at StreamingDense.scala:{line} {code}\n')
            return f'    printf(clock, {operand}, {literal}) : printf\n'
        baseline = diagnostic(1)
        candidate = diagnostic(3)
        self.assertEqual(runner.dense_source_locations(candidate, source, current), baseline)
        for text in [diagnostic(3, message='different'), diagnostic(3, operand='UInt<1>(0)')]:
            self.assertNotEqual(runner.dense_source_locations(text, source, current), baseline)
        for text in [candidate.replace('Assertion failed:', 'ordinary text:'), candidate+candidate,
                     diagnostic(3, code='assert(y,"message")'),
                     candidate.replace('"Assertion failed:', '"ordinary \\"Assertion failed:'),
                     candidate.replace('\\n")', '\\nextra")')]:
            with self.assertRaises(ValueError):
                runner.dense_source_locations(text, source, current)
        for text in [source+source, source.replace('x', 'y')]:
            with self.assertRaises(ValueError):
                runner.dense_source_locations(candidate, source, text)

    def test_per_bank_ports_reject_uneven_or_extra_access(self):
        body = '\n'.join(f'    {direction} mport p_{direction}_{bank} = {bank}[addr], clock' for bank in ['a', 'b'] for direction in ['read', 'write'])
        runner.check_ports(body, {'a', 'b'})
        for text in [body.replace('= b[', '= a['), body.replace('read mport', 'rdwr mport', 1), body+'\n    read mport extra = a[addr], clock']:
            with self.assertRaisesRegex(ValueError, 'per named bank'):
                runner.check_ports(text, {'a', 'b'})


if __name__ == "__main__":
    unittest.main()
