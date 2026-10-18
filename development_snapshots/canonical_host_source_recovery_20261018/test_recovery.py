"""Finite stdlib source/assembly tests and synthetic Python hold controls only."""
import argparse
import ast
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
import types
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--source", type=Path, default=HERE / "source")
args, remaining = parser.parse_known_args()
SOURCE = args.source


PROJECT_HASHES = json.loads((HERE / "PROJECT_SOURCE_HASHES.json").read_text())["files"]


def module(name, path, source_key):
    # Verify and execute the SAME bytes. Never consult a project bytecode cache.
    raw = path.read_bytes()
    actual = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    if actual != PROJECT_HASHES[source_key]:
        raise ValueError("project source bytes differ before execution: " + source_key)
    result = types.ModuleType(name)
    result.__file__ = str(path.resolve())
    sys.modules[name] = result
    exec(compile(raw, source_key, "exec", dont_inherit=True), result.__dict__)
    return result


recovery = module("recovery_source_candidate", HERE / "recover.py", "recover.py")
recovery.verify(SOURCE)
hold = module("recovered_hold_contract", SOURCE / "hold_contract_cold.py",
              "source/hold_contract_cold.py")


class RecoveryCold(unittest.TestCase):
    def test_01_exact_source_subset(self):
        result = recovery.verify(SOURCE)
        self.assertEqual(result["files"], 22)
        self.assertFalse(result["cpp_compiled"])
        self.assertFalse(result["full_host_ready"])

    def test_02_source_only_hashes(self):
        records = json.loads((HERE / "PROJECT_SOURCE_HASHES.json").read_text())["files"]
        source_names = {"source/" + r["assembled_path"] for r in recovery.pin()["copied_sources"]}
        self.assertEqual(set(records), source_names | {"recover.py", "test_recovery.py"})
        for name, expected in records.items():
            self.assertEqual(recovery.digest((HERE / name).read_bytes()), expected, name)

    def test_03_python_parse_and_standalone_axi_text(self):
        for path in (HERE / "recover.py", HERE / "test_recovery.py", SOURCE / "hold_contract_cold.py"):
            ast.parse(path.read_text(), filename=path.name)
        text = (SOURCE / "include/axi_protocol.hpp").read_text()
        self.assertEqual(recovery.QUOTED.findall(text), [])
        self.assertIn("class IndependentLedger", text)
        self.assertIn("RLAST mismatch", text)
        self.assertIn("WLAST mismatch", text)

    def test_04_exact_include_audit(self):
        actual = recovery.closure(SOURCE)
        expected = json.loads((HERE / "SOURCE_CLOSURE.json").read_text())
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual["edges"]), 37)
        self.assertEqual(sum(e["status"] == "RECOVERED_PROJECT_SOURCE" for e in actual["edges"]), 20)
        self.assertEqual(actual["missing"], recovery.MISSING)

    def test_05_local_ledger_resolution_not_flattened(self):
        edges = recovery.closure(SOURCE)["edges"]
        for section in ("startup", "pc0"):
            edge = next(e for e in edges if e["source"] == section + "/dpi_forwarders.hpp"
                        and e["header"] == "startup_ledger.hpp")
            self.assertEqual(edge["target"], section + "/startup_ledger.hpp")
        self.assertNotEqual((SOURCE / "startup/startup_ledger.hpp").read_bytes(),
                            (SOURCE / "pc0/startup_ledger.hpp").read_bytes())

    def test_06_reassemble_and_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "repository"
            repository.mkdir()
            for record in recovery.pin()["copied_sources"]:
                path = repository / record["repository_path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((SOURCE / record["assembled_path"]).read_bytes())
            output = root / "assembled"
            self.assertEqual(recovery.assemble(repository, output)["files"], 22)
            self.assertEqual(recovery.closure(output), recovery.closure(SOURCE))
            with self.assertRaisesRegex(ValueError, "already exists"):
                recovery.assemble(repository, output)
            with self.assertRaisesRegex(ValueError, "outside repository"):
                recovery.assemble(repository, repository / "must_not_create")
            self.assertFalse((repository / "must_not_create").exists())
            first = recovery.pin()["copied_sources"][0]
            (repository / first["repository_path"]).write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "source differs"):
                recovery.assemble(repository, root / "must_not_create")
            self.assertFalse((root / "must_not_create").exists())

    def test_07_corrupted_or_extra_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "source"
            shutil.copytree(SOURCE, target)
            extra = target / "unexpected.hpp"
            extra.write_text("// no implicit dependency substitution\n")
            with self.assertRaisesRegex(ValueError, "file set differs"):
                recovery.verify(target)
            extra.unlink()
            (target / "include/axi_protocol.hpp").write_text("// mutated\n")
            with self.assertRaisesRegex(ValueError, "source bytes differ"):
                recovery.verify(target)

    def test_08_unsafe_relative_source_names_are_rejected(self):
        for value in ("", "..", "../source", "/source", "a/../b", "a\\b", "a//b", "./a"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                recovery.relative(value)

    def test_09_result_contract(self):
        hold.normal_result(0, 21, 20, 7)
        for fields in ((1, 21, 20, 7), (0, 20, 20, 7), (0, 21, 19, 7), (0, 21, 20, 8)):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                hold.normal_result(*fields)

    def test_10_first_sample_and_held_request_offers_rejected(self):
        for field in ("ar", "aw", "w"):
            for already_held in (False, True):
                h = hold.Hold()
                if already_held:
                    h.observe(1, hold.Observation())
                with self.subTest(field=field, held=already_held), self.assertRaises(ValueError):
                    h.observe(1, replace(hold.Observation(), **{field: True}))
                self.assertFalse(h.released)

    def test_11_both_debts_must_be_zero(self):
        for field in ("axi_debt", "physical_debt"):
            for debt in (-1, 1):
                h = hold.Hold()
                h.observe(1, hold.Observation())
                with self.subTest(field=field, debt=debt), self.assertRaises(ValueError):
                    h.observe(1, replace(hold.Observation(), **{field: debt}))

    def test_12_all_cumulative_activity_stays_frozen(self):
        for field, value in (("issued", 2), ("axi_counts", (1, 0, 0, 0, 0)),
                             ("hub_counts", (1, 0, 0, 0)), ("owner_activity", (2, 2)),
                             ("matrix_loan_prefix_activity", (1, 0, 0, 0, 0, 0)),
                             ("matrix_loan_prefix_activity", (0, 0, 1, 0, 0, 0)),
                             ("matrix_loan_prefix_activity", (0, 0, 0, 0, 1, 0))):
            h = hold.Hold()
            h.observe(1, hold.Observation())
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                h.observe(1, replace(hold.Observation(), **{field: value}))

    def test_13_payload_stability(self):
        h = hold.Hold()
        h.observe(1, hold.Observation())
        with self.assertRaises(ValueError):
            h.observe(2, hold.Observation())

    def test_14_actual_ack_required(self):
        for valid, ready in ((False, False), (False, True), (True, False)):
            h = hold.Hold()
            h.observe(1, hold.Observation())
            with self.subTest(valid=valid, ready=ready), self.assertRaises(ValueError):
                h.ack(1, hold.Observation(), valid, ready)
            self.assertFalse(h.released)

    def test_15_ack_observation_checked(self):
        h = hold.Hold()
        h.observe(1, hold.Observation())
        with self.assertRaises(ValueError):
            h.ack(1, replace(hold.Observation(), ar=True), True, True)
        self.assertFalse(h.released)

    def test_16_hold_once_then_release_no_restart(self):
        h, observation = hold.Hold(), hold.Observation()
        for _ in range(4):
            h.observe(21, observation)
        self.assertEqual(h.compares, 1)
        h.ack(21, observation, True, True)
        self.assertTrue(h.released)
        self.assertEqual(h.compares, 1)
        with self.assertRaises(ValueError):
            h.observe(21, observation)
        with self.assertRaises(ValueError):
            h.ack(21, observation, True, True)

    def test_17_partial_physical_admission_remains_fail_closed_text(self):
        text = (SOURCE / "include/physical_observer_bridge.hpp").read_text()
        self.assertIn('missing("full reset provenance and remaining physical domains")', text)
        self.assertIn('missing("remaining actual 17-owner reconciliation and all DMA/Matrix/prefix/B debts")', text)
        self.assertIn('max_cycles=2000000', (SOURCE / "pc0/pc0_main.cpp").read_text())

    def test_18_valid_polluted_pyc_never_supplies_project_code(self):
        # Temporary benign marker only. This matches the current interpreter's
        # normal/optimized cache filename, magic, source timestamp and size.
        import importlib.machinery
        import importlib.util
        import marshal
        import struct
        for source_path, key in ((HERE / "recover.py", "recover.py"),
                                 (SOURCE / "hold_contract_cold.py", "source/hold_contract_cold.py")):
            with self.subTest(source=key), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / source_path.name
                raw = source_path.read_bytes()
                path.write_bytes(raw)
                stats = path.stat()
                code = compile(raw + b"\nPYC_INJECTED_MARKER = True\n", key, "exec")
                cache = Path(importlib.util.cache_from_source(str(path)))
                cache.parent.mkdir()
                header = importlib.util.MAGIC_NUMBER + struct.pack(
                    "<III", 0, int(stats.st_mtime) & 0xffffffff, len(raw))
                cache.write_bytes(header + marshal.dumps(code))
                # Positive control proves this is a valid, accepted poisoned
                # cache. Only this intentionally vulnerable temporary control
                # executes the harmless module-attribute marker.
                name = "temporary_legacy_cache_control"
                loader = importlib.machinery.SourceFileLoader(name, str(path))
                spec = importlib.util.spec_from_loader(name, loader)
                legacy = importlib.util.module_from_spec(spec)
                sys.modules[name] = legacy
                try:
                    loader.exec_module(legacy)
                    self.assertTrue(legacy.PYC_INJECTED_MARKER)
                finally:
                    sys.modules.pop(name, None)
                name = "temporary_verified_source_control"
                try:
                    verified = module(name, path, key)
                    self.assertFalse(hasattr(verified, "PYC_INJECTED_MARKER"))
                    self.assertEqual(path.read_bytes(), raw)
                finally:
                    sys.modules.pop(name, None)

    def test_19_changed_source_is_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "recover.py"
            path.write_bytes((HERE / "recover.py").read_bytes() + b"\nSOURCE_INJECTED_MARKER = True\n")
            name = "temporary_changed_source_control"
            with self.assertRaisesRegex(ValueError, "before execution"):
                module(name, path, "recover.py")
            self.assertNotIn(name, sys.modules)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]] + remaining, verbosity=2)
