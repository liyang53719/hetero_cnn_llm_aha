"""Source-only preparation/audit checks. Never invoke Scala, RTL or CI."""
import hashlib
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from candidates.qwen2_resident_matrix.raw_kv_parent import prepare_unit
from candidates.qwen2_resident_matrix.raw_kv_parent import run_unit
from candidates.qwen2_resident_matrix.raw_kv_parent.run_unit import (
    DIAGNOSTIC_BYTES, QUEUE_FIELDS, SCENARIOS, dependency_audit,
    failure_diagnostics, memory_audit_parent, result_audit,
)


def synthetic_chirrtl(*, reverse=False, inferred=False):
    banks = "\n".join(
        f"    smem b{i} : UInt<256>[{1376 if i < 16 else 160}], undefined @[banks.scala 1:1]\n"
        f"    read mport r{i} = b{i}[address], clock\n"
        f"    write mport w{i} = b{i}[address], clock"
        for i in range(32))
    fields = ", ".join(reversed(QUEUE_FIELDS) if reverse else QUEUE_FIELDS)
    read, write = ("infer", "infer") if inferred else ("read", "write")
    return ("FIRRTL version 3.3.0\n"
            "circuit TransposedDenseDownOwner :\n"
            "  module TransposedDownDenseBanks :\n" + banks + "\n"
            "  module Queue4_MatrixStreamStep :\n"
            "    cmem ram : {" + fields + "}[4] @[Queue.scala 1:1]\n"
            f"    {read} mport rd = ram[deq_ptr], clock\n"
            f"    {write} mport wr = ram[enq_ptr], clock\n"
            "    io.deq.bits <= rd\n    wr <= io.enq.bits\n"
            "  module TransposedDenseDownOwner :\n"
            "    inst banks of TransposedDownDenseBanks\n"
            "    inst operands of Queue4_MatrixStreamStep\n")


class ParentUnitPrepareTests(unittest.TestCase):
    def test_exact_compile_closure_is_reproducible(self):
        with tempfile.TemporaryDirectory(prefix="parent-prepare-test-") as tmp:
            root = Path(tmp)
            first = prepare_unit.prepare(root / "one")
            second = prepare_unit.prepare(root / "two")
            self.assertEqual(len(first["generated"]), 13)
            self.assertEqual(len(first["slices"]), 7)
            self.assertEqual(first["generated"], second["generated"])
            self.assertEqual(first["slices"], second["slices"])
            pins = json.loads((prepare_unit.HERE / "unit_pins.json").read_text())
            self.assertEqual(first["generated"], pins["generated_sha256"])
            self.assertEqual(first["slices"], pins["slice_sha256"])
            for filename, sha in first["generated"].items():
                source = (root / "one" / filename).read_bytes()
                self.assertEqual(hashlib.sha256(source).hexdigest(), sha)
                self.assertEqual(source, (root / "two" / filename).read_bytes())
            with self.assertRaisesRegex(ValueError, "fresh compile-source"):
                prepare_unit.prepare(root / "one")

    def test_original_input_drift_fails_before_composition(self):
        # Corrupt only an isolated copy. Never edit a pinned repository input.
        pins = json.loads((prepare_unit.HERE / "unit_pins.json").read_text())
        first_input = next(iter(pins["inputs"]))
        with tempfile.TemporaryDirectory(prefix="parent-pin-test-") as tmp:
            root = Path(tmp)
            copied = root / first_input
            copied.parent.mkdir(parents=True)
            copied.write_text("deliberately changed source\n")
            with patch.object(prepare_unit, "ROOT", root):
                with self.assertRaisesRegex(ValueError, "unit source drift"):
                    prepare_unit.prepare(root / "out")
            self.assertFalse((root / "out").exists())

    def test_exact_slice_boundaries_fail_closed(self):
        self.assertEqual(prepare_unit.section("before START body END after", "START", "END"), "START body ")
        for text in ("START duplicate START END", "START END duplicate END", "missing END", "END before START"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                prepare_unit.section(text, "START", "END")

    def test_memory_audit_allows_only_existing_geometry(self):
        for reverse in (False, True):
            for inferred in (False, True):
                with self.subTest(reverse=reverse, inferred=inferred):
                    audit = memory_audit_parent(synthetic_chirrtl(reverse=reverse, inferred=inferred))
                    self.assertEqual(audit["sram_memories"], 32)
                    self.assertEqual(audit["total_memory_declarations"], 33)
                    self.assertEqual(audit["operand_fifo"]["depth"], 4)
                    self.assertEqual(audit["operand_fifo"]["element_bits"], 4359)
                    self.assertFalse(audit["matrix_or_hardfloat_instantiated"])

    def test_memory_audit_rejects_extra_memory_and_ports(self):
        good = synthetic_chirrtl()
        bad = (
            good.replace("1376", "1375", 1),
            good.replace("UInt<256>", "UInt<512>", 1),
            good.replace("write mport w0", "read mport w0", 1),
            good.replace("read mport r0 = b0[address], clock", "read mport r0 = b0[address], clock\n    read mport extra = b0[address], clock", 1),
            good.replace("}[4]", "}[2]", 1),
            good.replace("context:UInt<3>", "context:UInt<4>", 1),
            good.replace("emit:UInt<1>", "returnTag:UInt<32>", 1),
            good.replace("cmem ram", "smem ram", 1),
            good.replace("write mport wr", "read mport wr", 1),
            good + "    cmem shadow : UInt<512>[4096]\n",
            good.replace("    cmem ram", "    cmem shadow : UInt<512>[4096]\n    cmem ram", 1),
        )
        for index, text in enumerate(bad):
            with self.subTest(index=index), self.assertRaises(ValueError):
                memory_audit_parent(text)

    def test_memory_audit_rejects_arithmetic_and_replicated_instances(self):
        good = synthetic_chirrtl()
        bad = (
            good + "  module Matrix :\n",
            good + "  extmodule HardFloat :\n",
            good + "  intmodule MulAddRecFN :\n",
            good + "    inst matrix of Matrix\n",
            good + "    inst duplicate of TransposedDownDenseBanks\n",
            good + "    inst duplicate of Queue4_MatrixStreamStep\n",
            good.replace("inst operands of Queue4_MatrixStreamStep", "inst substitute of Queue4_MatrixStreamStep", 1),
            good.replace("circuit TransposedDenseDownOwner", "circuit FakeOwner", 1),
        )
        for index, text in enumerate(bad):
            with self.subTest(index=index), self.assertRaises(ValueError):
                memory_audit_parent(text)

    def test_two_cases_and_every_scenario_are_mandatory(self):
        good = ("Total number of tests run: 2\nAll tests passed.\n"
                + "".join("PARENT_SCENARIO_PASS " + s + "\n" for s in SCENARIOS))
        self.assertEqual(result_audit(good)["completed_scenarios"], list(SCENARIOS))
        bad = [good.replace("run: 2", "run: 1"), good.replace("All tests passed.", "Tests failed."),
               good + "Total number of tests run: 2\n",
               good + "PARENT_SCENARIO_PASS unexpected\n"]
        for name in SCENARIOS:
            marker = "PARENT_SCENARIO_PASS " + name + "\n"
            bad.extend([good.replace(marker, ""), good + marker])
        for index, text in enumerate(bad):
            with self.subTest(index=index), self.assertRaises(ValueError):
                result_audit(text)

    def test_dependency_lock_gate_and_unlocked_hash_disclosure(self):
        names = ["chisel_2.13-6.7.0.jar", "chisel-plugin_2.13.16-6.7.0.jar",
                 "chiseltest_2.13-6.0.0.jar", "scalatest_2.13-3.2.19.jar",
                 "scala-compiler-2.13.16.jar", "scala-library-2.13.16.jar"]
        with tempfile.TemporaryDirectory(prefix="parent-dependency-audit-test-") as tmp:
            root = Path(tmp)
            for name in names:
                (root / name).write_bytes(("synthetic fixture: " + name).encode())
            inventory = root / "dependencies.txt"
            inventory.write_text("\n".join(str(root / n) for n in names))
            pinned = root / names[0]
            lock = root / "lock.json"
            lock.write_text(json.dumps({"artifacts": {"official/path/" + pinned.name: hashlib.sha256(pinned.read_bytes()).hexdigest()}}))
            hashes, receipt = dependency_audit(inventory, lock)
            self.assertEqual(len(hashes), 6)
            self.assertEqual(sum(r["existing_lock_match"] for r in receipt), 1)
            self.assertTrue(all(set(r) == {"jar", "sha256", "existing_lock_match"} for r in receipt))
            original = pinned.read_bytes()
            pinned.write_bytes(b"changed locked fixture")
            with self.assertRaisesRegex(ValueError, "locked dependency digest mismatch"):
                dependency_audit(inventory, lock)
            pinned.write_bytes(original)
            inventory.write_text("\n".join(str(root / n) for n in names[1:]))
            with self.assertRaisesRegex(ValueError, "required exact toolchain"):
                dependency_audit(inventory, lock)

    def test_failure_diagnostics_first_last_bound_and_path_redaction(self):
        with tempfile.TemporaryDirectory(prefix="parent-diagnostic-test-") as tmp:
            root = Path(tmp)
            log = root / "compile.log"
            lines = [f"[error] {root}/project/src/main/scala/Owner.scala:10:2: not found: diagnostic_{i:02d} " + "x" * 400 for i in range(40)]
            log.write_text("\n".join(lines))
            result = failure_diagnostics(log, prefixes=((root / "project", "<PROJECT>"), (root, "<OUT>")),
                                         stage="compile", error="compile failed")
            self.assertLessEqual(len(result.encode("utf-8")), DIAGNOSTIC_BYTES)
            self.assertIn("diagnostic_00", result)
            self.assertIn("diagnostic_39", result)
            self.assertNotIn("diagnostic_20", result)
            self.assertIn("<PROJECT>/src/main/scala/Owner.scala:10:2", result)
            self.assertNotIn(str(root), result)

    def test_failure_diagnostics_reject_payloads_and_source_echoes(self):
        secret = "deadbeef" * 64
        with tempfile.TemporaryDirectory(prefix="parent-diagnostic-data-test-") as tmp:
            log = Path(tmp) / "test.log"
            log.write_text("\n".join([
                "[info] - retirement *** FAILED ***",
                "[error] rawtensor: " + secret,
                "[error] payload: " + secret + " *** FAILED ***",
                "[info] java.lang.AssertionError: Vector(1, 2, 3, 4)",
                "[info] value was not equal to " + " ".join(str(i) for i in range(30)),
                "[error]     p.response.bits.data.expect(BigInt(\"" + secret + "\", 16).U)",
                "[error] " + "bulk" * 2000 + " *** FAILED ***",
                "[info] chiseltest.FailedExpectException: scalar mismatch 0x" + secret,
                "[error] java.lang.RuntimeException: token=private-token-value api_key=private-key-value",
                "[error] java.lang.RuntimeException: Authorization: Bearer private-bearer-value",
                "[error] java.lang.RuntimeException: github_pat_privatepatvalue",
                "[error] java.lang.RuntimeException: https://example.invalid/?token=private-url-token",
                "[info] Tests: succeeded 1, failed 1, canceled 0, ignored 0, pending 0",
            ]))
            result = failure_diagnostics(log, stage="parent_rtl_unit", error="test failed")
            self.assertIn("retirement *** FAILED ***", result)
            self.assertIn("scalar mismatch <VALUE>", result)
            self.assertIn("failed 1", result)
            for excluded in (secret, "rawtensor:", "payload:", "Vector(", "data.expect", "bulkbulk", "0 1 2 3",
                             "private-token-value", "private-key-value", "private-bearer-value", "privatepatvalue", "private-url-token"):
                self.assertNotIn(excluded, result)
            self.assertLessEqual(len(result.encode("utf-8")), DIAGNOSTIC_BYTES)

    def test_failure_diagnostics_bounded_windows_and_timeout(self):
        with tempfile.TemporaryDirectory(prefix="parent-diagnostic-window-test-") as tmp:
            root = Path(tmp)
            log = root / "compile.log"
            log.write_bytes(b"[error] /private/build/Owner.scala:1:2: first error\n"
                            + b"raw bulk data\n" * 30000
                            + b"[error] /private/build/Owner.scala:9:2: last error\n")
            result = failure_diagnostics(log, stage="compile", error=f"Command ['sbt', '{root}/project'] timed out after 120 seconds")
            self.assertIn("first error", result)
            self.assertIn("last error", result)
            self.assertIn("timed out after 120", result)
            self.assertNotIn("/private/build", result)
            self.assertNotIn(str(root), result)
            self.assertNotIn("raw bulk data", result)
            self.assertLessEqual(len(result.encode("utf-8")), DIAGNOSTIC_BYTES)

    def test_runner_exception_payload_and_credential_sanitation(self):
        for message in ("payload: private-payload", "raw tensor=private-tensor", "weight: private-weights",
                        "did not equal " + " ".join(str(i) for i in range(30))):
            with self.subTest(message=message):
                result = failure_diagnostics(None, error=message)
                self.assertNotIn("private-", result)
                self.assertNotIn("0 1 2 3", result)
                self.assertIn("diagnostic omitted", result)
        message = ('token=private-token password="private two words" secret=private-secret '
                   '"api_key": "private-key" Authorization: Bearer private-bearer')
        result = failure_diagnostics(None, error=message)
        self.assertNotIn("private", result)
        self.assertNotIn("two words", result)
        self.assertIn("REDACTED", result)

    def test_failed_stage_writes_and_prints_only_sanitized_receipt(self):
        # The process launcher is replaced: no sbt, dependency resolution,
        # compilation, elaboration or simulation can run in this test.
        def fake_failure(args, *, cwd, env, log, timeout):
            log.write(f"[error] {cwd}/src/main/scala/Owner.scala:4:2: not found: example\n")
            log.flush()
            return 1

        with tempfile.TemporaryDirectory(prefix="parent-failed-run-test-") as tmp:
            out = Path(tmp) / "out"
            stdout = io.StringIO()
            relative_pin = str((prepare_unit.HERE / "unit_pins.json").relative_to(prepare_unit.ROOT))
            with patch.object(run_unit, "LOCK_PATH", relative_pin), patch.object(run_unit, "run_group", side_effect=fake_failure) as launch:
                with redirect_stdout(stdout), self.assertRaisesRegex(ValueError, "dependencies failed"):
                    run_unit.run(out)
            launch.assert_called_once()
            summary = json.loads((out / "evidence/summary.json").read_text())
            self.assertEqual(summary["status"], "FAIL")
            self.assertEqual(stdout.getvalue().strip(), summary["failure_diagnostics"])
            self.assertIn("not found: example", summary["failure_diagnostics"])
            self.assertNotIn(str(out), stdout.getvalue())
            self.assertLessEqual(len(summary["failure_diagnostics"].encode("utf-8")), DIAGNOSTIC_BYTES)
            self.assertLessEqual({p.name for p in (out / "evidence").iterdir()}, run_unit.EVIDENCE_FILES)


if __name__ == "__main__":
    unittest.main()
