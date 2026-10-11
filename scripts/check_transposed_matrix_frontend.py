#!/usr/bin/env python3
"""Pinned full-service frontend gate. No firtool, SystemVerilog or simulation.

Reuse the verified earlier baseline IR only with exact source/ABI/dependency
identities. New candidate source and parameter combinations are freshly emitted.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / "candidates/qwen2_resident_matrix/transposed_route"
PREFIX = "chisel/continuous_prefill/src/main/scala/heteronpu/continuous/"
BASE = "590f8cfd39a1aa5aa2a2dc481eab29d406d899a2"
TASK_FILES = {"transposed_mode.patch", "combined_service.patch", "TransposedModeElaboration.scala",
              "transposed_model.py", "test_transposed_mode.py"}
DEPENDENCIES = {"scripts/check_matrix_interface_candidate.py", "scripts/check_transposed_matrix_frontend.py",
                "candidates/qwen2_resident_matrix/return_tag.patch",
                "candidates/qwen2_resident_matrix/test_return_tag_contract.py"}


def validate_manifest(manifest):
    expected = {"original_sources": {"BurstProtocol.scala", "MatrixPipeline.scala", "RetainedMatrix.scala", "WideMatrix.scala"},
                "tag_overlay_sources": {"BurstProtocol.scala", "MatrixPipeline.scala"},
                "patched_sources": {"BurstProtocol.scala", "MatrixPipeline.scala"},
                "task_files": TASK_FILES, "dependencies": DEPENDENCIES}
    if manifest.get("source_base_commit") != BASE:
        raise ValueError("source baseline identity changed")
    for field, keys in expected.items():
        if set(manifest.get(field, {})) != keys:
            raise ValueError("manifest file set changed: "+field)
        for path, digest in manifest[field].items():
            if Path(path).is_absolute() or ".." in Path(path).parts or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError("invalid path or SHA256 pin")
    for key in ("abi_declarations_sha256", "maven_lock_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", manifest.get(key, "")):
            raise ValueError("invalid ABI/dependency pin")


def bounded_file(base, relative):
    path = (base/relative).resolve()
    if not path.is_relative_to(base.resolve()):
        raise ValueError("source path escapes its root")
    return path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def check(data, expected, label):
    if sha(data) != expected:
        raise ValueError("identity drift: " + str(label))
    return data


def helper(manifest):
    path = ROOT / "scripts/check_matrix_interface_candidate.py"
    check(path.read_bytes(), manifest["dependencies"][str(path.relative_to(ROOT))], path)
    spec = importlib.util.spec_from_file_location("frontend_helpers", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_inputs(manifest):
    validate_manifest(manifest)
    check(Path(__file__).read_bytes(), manifest["dependencies"]["scripts/check_transposed_matrix_frontend.py"],
          "executing frontend runner")
    for path, digest in manifest["dependencies"].items():
        check(bounded_file(ROOT, path).read_bytes(), digest, path)
    for path, digest in manifest["task_files"].items():
        check(bounded_file(TASK, path).read_bytes(), digest, path)
    source = {}
    for name, digest in manifest["original_sources"].items():
        data = subprocess.check_output(["git", "show", manifest["source_base_commit"]+":"+PREFIX+name], cwd=ROOT)
        source[name] = check(data, digest, name)
    return source


def build_overlay(source, directory, manifest):
    directory.mkdir(parents=True)
    for name in ("BurstProtocol.scala", "MatrixPipeline.scala"):
        path = directory/PREFIX/name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(source[name])
    for patch in (ROOT/"candidates/qwen2_resident_matrix/return_tag.patch", TASK/"transposed_mode.patch"):
        subprocess.run(["git", "apply", "--check", str(patch)], cwd=directory, check=True)
        subprocess.run(["git", "apply", str(patch)], cwd=directory, check=True)
        pins = manifest["tag_overlay_sources" if patch.name == "return_tag.patch" else "patched_sources"]
        for name, digest in pins.items():
            check((directory/PREFIX/name).read_bytes(), digest, name)



def run(out, cache, archived, validate_only=False):
    manifest = json.loads((TASK/"manifest.json").read_text())
    source = check_inputs(manifest)
    helpers = helper(manifest)
    if out.exists():
        raise ValueError("use a fresh output directory; previous evidence is preserved")
    out.mkdir(parents=True)
    report = {"status": "STARTED", "source_base_commit": manifest["source_base_commit"],
              "source_pins": manifest, "rtl_generated": False, "arithmetic_executed": False,
              "hardware_protocol_executed": False, "native_numerical_acceptance": "UNCHANGED_OPEN",
              "commands": []}

    def save():
        (out/"summary.json").write_text(json.dumps(report, indent=2)+"\n")

    def command(argv, log):
        begin = time.monotonic()
        with log.open("w") as stream:
            p = subprocess.run(argv, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=180)
        report["commands"].append({"argv": argv, "log": str(log.relative_to(out)),
                                   "exit_code": p.returncode, "wall_seconds": time.monotonic()-begin})
        save()
        if p.returncode:
            raise RuntimeError("frontend command failed: "+str(log))

    try:
        old = json.loads((archived/"summary.json").read_text())
        if old["status"] != "PASS_FRONTEND_ONLY":
            raise ValueError("archived baseline did not pass")
        for key in ("original_sources", "abi_declarations_sha256", "maven_lock_sha256"):
            if old["source_pins"][key] != manifest[key]:
                raise ValueError("archived baseline source/dependency identity drift")
        if old["source_pins"]["patched_sources"] != manifest["tag_overlay_sources"]:
            raise ValueError("archived return-tag source identity drift")
        for n, digest in manifest["original_sources"].items():
            if n in ("BurstProtocol.scala", "MatrixPipeline.scala"):
                check((archived/"baseline/source"/PREFIX/n).read_bytes(), digest, n)
        for n, digest in manifest["tag_overlay_sources"].items():
            check((archived/"candidate/source"/PREFIX/n).read_bytes(), digest, "archived tag overlay "+n)
        check((archived/"RetainedAbi.scala").read_bytes(), manifest["abi_declarations_sha256"], "archived exact ABI")
        old_jars = json.loads((archived/"dependency_receipt.json").read_text())
        if sha((archived/"dependency_receipt.json").read_bytes()) != old["dependency_receipt_sha256"]:
            raise ValueError("archived dependency receipt drift")
        lock = check((ROOT/"chisel/rope_hardware_oracle/maven-lock.json").read_bytes(), manifest["maven_lock_sha256"], "Maven lock")
        pins = helpers.dependency_paths(json.loads(lock)["artifacts"])
        if len(pins) != 87 or pins != {j["path"]: j["sha256"] for j in old_jars["jars"]}:
            raise ValueError("dependency set drift")
        # Require every cache object before invoking the shared helper; no fetches.
        for path, digest in pins.items():
            check((cache/path).read_bytes(), digest, path)
        cp, plugin, receipt = helpers.prepare_dependencies(ROOT, cache, manifest)
        (out/"dependency_receipt.json").write_text(json.dumps(receipt, indent=2)+"\n")
        report["dependency_receipt_sha256"] = sha((out/"dependency_receipt.json").read_bytes())
        report["baseline_reuse"] = {"directory": str(archived.relative_to(ROOT)) if archived.is_relative_to(ROOT) else str(archived),
            "summary_sha256": sha((archived/"summary.json").read_bytes()),
            "reason": "exact original/return-tag source bytes, constructor parameters, ABI and 87 dependency SHA identities verified",
            "new_baseline_compile": False}
        build_overlay(source, out/"source", manifest)
        abi = "package heteronpu.continuous\nimport chisel3._\nimport chisel3.util._\n"
        for name, declarations in (("RetainedMatrix.scala", ("RetainedMatrixEndpoint", "RetainedMatrixClockGate")),
                                   ("WideMatrix.scala", ("WideMatrixStep", "WideMatrixResult"))):
            for cls in declarations:
                abi += helpers.declaration(source[name].decode(), cls)+"\n"
        check(abi.encode(), manifest["abi_declarations_sha256"], "fresh exact ABI extraction")
        (out/"RetainedAbi.scala").write_text(abi)
        # Validate raw baseline IR before either compilation or validate-only exit.
        comparisons = [("fifo_default.fir", "baseline/chirrtl/fifo_default.fir"),
                       ("service_default.fir", "baseline/chirrtl/service_default.fir")]
        comparisons += [(f"service_{bits}_disabled.fir", f"candidate/chirrtl/service_{bits}.fir")
                        for bits in (0, 1, 16, 32)]
        report["validated_baseline_ir"] = {}
        for fresh, previous in comparisons:
            raw = check((archived/previous).read_bytes(), old["generated_chirrtl"][previous]["sha256"], previous)
            report["validated_baseline_ir"][previous] = sha(raw)
        if validate_only:
            report["status"] = "PASS_SOURCE_BASELINE_CACHE_VALIDATION_ONLY"
            report["new_scala_compile"] = False
            report["new_chirrtl_emission"] = False
            save()
            return report
        sys.path.insert(0, str(TASK))
        from transposed_model import retained_counts, graph_checks
        classes = out/"classes"; classes.mkdir()
        java = ["java", "-Xmx1024m", "-XX:ActiveProcessorCount=1"]
        report["java_version"] = subprocess.check_output(["java", "-version"], stderr=subprocess.STDOUT, text=True).strip()
        if report["java_version"] != old["java_version"]:
            raise ValueError("Java identity drift from reusable baseline")
        sources = [out/"RetainedAbi.scala", out/"source"/PREFIX/"BurstProtocol.scala",
                   out/"source"/PREFIX/"MatrixPipeline.scala", TASK/"TransposedModeElaboration.scala"]
        command(java+["-cp", cp, "scala.tools.nsc.Main", "-classpath", cp, "-Xplugin:"+str(plugin),
                      "-d", str(classes)]+list(map(str, sources)), out/"compile.log")
        print("PASS: Scala compilation of full patched service and exact retained ABI", flush=True)
        command(java+["-cp", str(classes)+":"+cp, "heteronpu.continuous.TransposedModeElaboration", str(out/"chirrtl")], out/"elaboration.log")
        print("PASS: all requested CHIRRTL parameter combinations emitted", flush=True)
        report["default_ir_comparisons"] = {}
        for fresh, previous in comparisons:
            raw = check((archived/previous).read_bytes(), old["generated_chirrtl"][previous]["sha256"], previous)
            before = helpers.normalized_chirrtl(raw.decode())
            after = helpers.normalized_chirrtl((out/"chirrtl"/fresh).read_text())
            equal = before == after
            report["default_ir_comparisons"][fresh] = {"equal": equal, "baseline": previous,
                "normalized_before_sha256": sha(before.encode()), "normalized_after_sha256": sha(after.encode())}
            if not equal:
                raise ValueError("default-off normalized CHIRRTL drift: "+fresh)
        report["resource_declarations"] = {}
        report["emitted_operand_cones"] = {}
        for bits in (0, 1, 16, 32):
            for enabled in (False, True):
                name = f"service_{bits}_{'enabled' if enabled else 'disabled'}.fir"
                fir = helpers.normalized_chirrtl((out/"chirrtl"/name).read_text())
                report["resource_declarations"][name] = retained_counts(fir, bits, enabled)
                report["emitted_operand_cones"][name] = graph_checks(fir, enabled)
        report["generated_chirrtl"] = {str(p.relative_to(out)): {"sha256": sha(p.read_bytes()), "bytes": p.stat().st_size}
                                        for p in sorted((out/"chirrtl").glob("*.fir"))}
        report["status"] = "PASS_FRONTEND_AND_COMBINATIONAL_ROUTE_ONLY"
        save()
    except Exception as error:
        report["status"] = "FAILED"; report["error"] = str(error); save(); raise
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--validate-only", action="store_true", help="validate source/patch/ABI/cache/baseline identities without Scala")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--baseline", required=True, type=Path)
    args = parser.parse_args()
    ROOT = args.repo.resolve()
    TASK = ROOT / "candidates/qwen2_resident_matrix/transposed_route"
    answer = run(args.out.resolve(), args.cache.resolve(), args.baseline.resolve(), args.validate_only)
    print(json.dumps({"status": answer["status"], "rtl_generated": False, "arithmetic_executed": False}))
