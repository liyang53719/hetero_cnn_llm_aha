"""Tiny retained-source checks only: no temporary files, processes or models."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import types
import unittest

HERE = Path(__file__).resolve().parent
RAW = (HERE / "idma_source_contract.json").read_bytes()
SOURCE = (HERE / "idma_recipe.py").read_bytes()
module = types.ModuleType("idma_recipe_verified_test")
exec(compile(SOURCE, "idma_recipe.py", "exec"), module.__dict__)
CATALOG = json.loads(RAW)


class SourceOnly(unittest.TestCase):
    def test_raw_and_semantic_identity(self):
        self.assertEqual(hashlib.sha256(RAW).hexdigest(), module.CATALOG_SHA256)
        self.assertEqual(module.validate(CATALOG)["status"], "PASS_SOURCE_CONTRACT_ONLY")

    def test_describe_no_input_mutation_and_deterministic(self):
        before = copy.deepcopy(CATALOG)
        self.assertEqual(module.describe(CATALOG), module.describe(CATALOG))
        self.assertEqual(before, CATALOG)

    def test_exact_order_and_headers(self):
        self.assertEqual(len(CATALOG["ordered_rtl_units"]), 296)
        self.assertEqual(len(CATALOG["include_headers"]), 18)
        self.assertEqual(CATALOG["ordered_rtl_units"][-2]["path"], "tc_clk.sv")
        self.assertEqual(CATALOG["ordered_rtl_units"][-1]["repository"], "rtl/integration/idma_backend_rw_axi_flat_wrap.sv")

    def test_filelist_is_text_only(self):
        text = module.render_filelist(CATALOG)
        self.assertEqual(len(text.splitlines()), 4 + 8 + 296)
        self.assertTrue(text.endswith("\n"))
        self.assertEqual(text.splitlines()[-1], "{repo}/rtl/integration/idma_backend_rw_axi_flat_wrap.sv")
        self.assertNotIn("/workspace/", text)

    def test_reordered_or_modified_source_rejected(self):
        for mutation in ("order", "hash", "missing", "basename"):
            c = copy.deepcopy(CATALOG)
            if mutation == "order":
                c["ordered_rtl_units"][:2] = c["ordered_rtl_units"][1::-1]
            elif mutation == "hash":
                c["ordered_rtl_units"][0]["sha256"] = "0" * 64
            elif mutation == "missing":
                c["ordered_rtl_units"].pop()
            else:
                c["ordered_rtl_units"][1]["path"] = c["ordered_rtl_units"][0]["path"]
            with self.assertRaises(ValueError):
                module.validate(c)

    def test_parameter_and_warning_drift_rejected(self):
        for name in ("wrapper_parameters", "adapter_parameters", "leaf_warning_sites", "adapter_warning_sites"):
            c = copy.deepcopy(CATALOG)
            if isinstance(c[name], dict):
                c[name][next(iter(c[name]))] = "changed"
            else:
                c[name].pop()
            with self.assertRaises(ValueError):
                module.describe(c)

    def test_relative_paths_fail_closed(self):
        for path in ("", "/tmp/a", "../a", "a/../b", "a//b", "a\\b", "a/./b"):
            with self.assertRaises(ValueError):
                module.relative(path)

    def test_every_stage_is_unexecuted_unique_and_ordered(self):
        p = module.describe(CATALOG)
        ids = [s["id"] for s in p["stages"]]
        outs = [r for s in p["stages"] for r in s["outputs"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(outs), len(set(outs)))
        self.assertLess(ids.index("idma_syntax_leaf"), ids.index("idma_archive_leaf"))
        self.assertLess(ids.index("idma_syntax_adapter"), ids.index("idma_archive_adapter"))
        self.assertTrue(all(s["unexecuted"] is True for s in p["stages"]))
        self.assertTrue(all(s["cwd"].startswith("{build}/") for s in p["stages"]))

    def test_no_authority_or_acceptance(self):
        p = module.describe(CATALOG)
        self.assertEqual(p["status"], "UNRUN_PORTABLE_BUILD_RECIPE")
        self.assertIs(p["execution_authority"], False)
        self.assertIs(p["readiness"], False)
        self.assertTrue(p["unresolved_prerequisites"])
        self.assertTrue(all(v is False for v in p["qualification"].values()))

    def test_native_links_preserve_flags_without_rpath(self):
        p = module.describe(CATALOG)
        links = [s for s in p["stages"] if "_link_" in s["id"]]
        self.assertEqual(len(links), 3)
        for s in links:
            for flag in ("-std=c++17", "-O1", "-fPIC", "-pthread"):
                self.assertIn(flag, s["argv"])
            self.assertFalse(any("rpath" in a.lower() for a in s["argv"]))
        self.assertIn("-shared", links[0]["argv"])
        self.assertIn("-Wl,-z,defs", links[0]["argv"])

    def test_generation_is_exact_semantic_flag_set_with_unresolved_warning_gate(self):
        for s in module.describe(CATALOG)["stages"]:
            if "_generate_" in s["id"]:
                self.assertIn("--cc", s["argv"])
                self.assertIn("-Wno-fatal", s["argv"])
                self.assertFalse(any(a.startswith(("--timing", "--threads", "--converge-limit", "-Wno-UNOPT")) for a in s["argv"]))
                self.assertTrue(any("full ordered diagnostic-byte gate is unresolved" in x for x in s["preconditions"]))

    def test_original_no_pch_fragments(self):
        for row in CATALOG["no_pch_fragments"]:
            b = (HERE / row["path"]).read_bytes()
            self.assertEqual(hashlib.sha256(b).hexdigest(), row["sha256"])
            self.assertNotIn(b"/workspace/", b)
            self.assertIn(b"VM_DEFAULT_RULES := 0", b)

    def test_unique_sources_and_aggregate(self):
        p = module.describe(CATALOG)
        roles = [r["role"] for r in p["inputs"]]
        self.assertEqual(len(roles), len(set(roles)))
        self.assertEqual(p["aggregate_roles"]["idma_native_sources"], roles[:6])
        self.assertEqual(len(p["prerequisite_roles"]), 7)
        self.assertTrue(all(r["status"] == "UNRESOLVED" for r in p["prerequisite_roles"].values()))
        module.validate_role_order(p)

    def test_role_order_missing_duplicate_and_dangling_rejected(self):
        for change in ("missing", "duplicate", "dangling", "order", "output"):
            p = module.describe(CATALOG)
            if change == "missing":
                del p["prerequisite_roles"]["idma_296_rtl_units"]
            elif change == "duplicate":
                p["inputs"][1]["role"] = p["inputs"][0]["role"]
            elif change == "dangling":
                p["aggregate_roles"]["idma_native_sources"].append("undeclared")
            elif change == "order":
                p["stages"][1], p["stages"][2] = p["stages"][2], p["stages"][1]
            else:
                p["stages"][0]["outputs"].append(p["inputs"][0]["role"])
            with self.assertRaises(ValueError):
                module.validate_role_order(p)

    def test_exact_description_contract(self):
        p = module.describe(CATALOG)
        before = copy.deepcopy(p)
        self.assertEqual(hashlib.sha256(module.canonical(p)).hexdigest(), module.DESCRIPTION_SHA256)
        self.assertEqual(module.validate_description(p, CATALOG)["status"], "PASS_EXACT_UNRUN_DESCRIPTION_ONLY")
        self.assertEqual(p, before)

    def test_description_tampering_rejected(self):
        for change in ("argv", "cwd", "stage", "tool", "prerequisite", "input", "aggregate", "artifact", "environment", "unresolved", "extra", "type"):
            p = module.describe(CATALOG)
            if change == "argv": p["stages"][0]["argv"].append("--timing")
            elif change == "cwd": p["stages"][0]["cwd"] = "{build}/other"
            elif change == "stage": p["stages"][:2] = p["stages"][1::-1]
            elif change == "tool": p["tools"][0]["version"] = "changed"
            elif change == "prerequisite": p["prerequisite_roles"]["idma_296_rtl_units"]["status"] = "ACCEPTED"
            elif change == "input": p["inputs"][0]["sha256"] = "0" * 64
            elif change == "aggregate": p["aggregate_roles"]["idma_native_sources"].pop()
            elif change == "artifact": p["artifacts"]["idma_export"]["status"] = "ACCEPTED"
            elif change == "environment": p["environment"]["MAKEFLAGS"] = "-j8"
            elif change == "unresolved": p["unresolved_prerequisites"] = []
            elif change == "extra": p["additional_authority"] = True
            else: p["execution_authority"] = 0
            with self.assertRaises(ValueError):
                module.validate_description(p, CATALOG)

    def test_fragment_has_no_io_or_execution_api(self):
        tree = ast.parse(SOURCE)
        imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
        forbidden = {"os", "subprocess", "socket", "urllib", "requests", "ctypes", "shutil"}
        for n in imports:
            names = [a.name.split(".")[0] for a in n.names] if isinstance(n, ast.Import) else [n.module.split(".")[0]]
            self.assertTrue(forbidden.isdisjoint(names))
        for n in ast.walk(tree):
            if isinstance(n, ast.Call):
                name = n.func.id if isinstance(n.func, ast.Name) else n.func.attr if isinstance(n.func, ast.Attribute) else ""
                self.assertNotIn(name, {"open", "read_bytes", "read_text", "write_bytes", "write_text", "unlink", "mkdir", "Popen", "system", "exec", "eval", "compile", "run"})


if __name__ == "__main__":
    unittest.main()
