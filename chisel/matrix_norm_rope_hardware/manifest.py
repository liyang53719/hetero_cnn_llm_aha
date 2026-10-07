#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Validate pinned Maven inputs and record the exact generated hardware closure."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cache_files(root):
    cache = root / "work/rope_hardware_oracle/coursier/https/repo.maven.apache.org/maven2"
    return {str(p.relative_to(cache)): p for p in sorted(cache.rglob("*"))
            if p.is_file() and p.suffix in (".jar", ".pom") and not p.name.startswith(".")}


def verify_project_inventory(root):
    project = root / "chisel/matrix_norm_rope_hardware"
    allowed = {"README.md", "manifest.py", "build.sbt", "repositories",
               "project/build.properties", "src/main/scala/EmitMatrixNormRoPEHardwarePrimitives.scala"}
    found = set()
    for path in project.rglob("*"):
        relative = path.relative_to(project)
        parts = relative.parts
        # Only these actual generated roots are ignored. A target/ directory
        # nested under src/main/scala is still an unmanaged source directory.
        if parts[0] == "target" or parts[:2] == ("project", "target"):
            continue
        if parts[0] == "__pycache__" and path.suffix == ".pyc":
            continue
        if path.is_symlink():
            raise SystemExit(f"Unexpected project symlink: {relative}")
        if path.is_file():
            found.add(str(relative))
    unexpected = sorted(found - allowed)
    missing = sorted(allowed - found)
    if unexpected or missing:
        raise SystemExit(f"RoPE emission workspace inventory mismatch: unexpected={unexpected}, missing={missing}")


def verify_hardfloat_inventory(root):
    work = root / "work/rope_hardware_oracle"
    archive = work / "downloads/hardfloat.tar.gz"
    expected_digest = "55f9c47f73c5a0ff347ff0ff4fc72b6966ffaa6b6d29998a00b3956dce512de7"
    if sha256(archive) != expected_digest:
        raise SystemExit("HardFloat archive checksum mismatch")
    source = work / "deps/berkeley-hardfloat-c1105e6ac6a0dd90fc80893efc4830ab609005d3"
    prefix = ("hardfloat", "src", "main", "scala")
    expected = {}
    with tarfile.open(archive) as tf:
        for member in tf.getmembers():
            relative = Path(*Path(member.name).parts[1:])
            if member.isfile() and relative.parts[:4] == prefix:
                expected[str(relative)] = tf.extractfile(member).read()
    source_root = source.joinpath(*prefix)
    if source_root.is_symlink():
        raise SystemExit("HardFloat compile source root is a symlink")
    actual = {}
    for path in source_root.rglob("*"):
        relative = str(path.relative_to(source))
        if path.is_symlink():
            raise SystemExit(f"HardFloat compile source symlink: {relative}")
        if path.is_file():
            actual[relative] = path.read_bytes()
    if actual != expected:
        unexpected = sorted(set(actual) - set(expected))
        missing = sorted(set(expected) - set(actual))
        changed = sorted(name for name in actual.keys() & expected.keys() if actual[name] != expected[name])
        raise SystemExit(f"HardFloat compile source inventory mismatch: unexpected={unexpected}, missing={missing}, changed={changed}")


def verify_cache(root, complete):
    verify_project_inventory(root)
    verify_hardfloat_inventory(root)
    lock = json.loads((root / "chisel/rope_hardware_oracle/maven-lock.json").read_text())
    actual = cache_files(root)
    for relative, path in actual.items():
        if relative not in lock["artifacts"]:
            raise SystemExit(f"Unpinned Maven dependency: {relative}")
        if sha256(path) != lock["artifacts"][relative]:
            raise SystemExit(f"Maven dependency checksum mismatch: {relative}")
    # sbt executes its copied boot JARs rather than the Coursier originals.
    # Check those copies too; compiled compiler bridges are generated locally.
    pinned_jar_hashes = {digest for name, digest in lock["artifacts"].items() if name.endswith(".jar")}
    for path in (root / "work/rope_hardware_oracle/sbt/boot").rglob("*.jar"):
        if sha256(path) not in pinned_jar_hashes:
            raise SystemExit(f"Unpinned or altered sbt boot JAR: {path}")
    if complete:
        missing = sorted(set(lock["artifacts"]) - set(actual))
        if missing:
            raise SystemExit(f"Missing pinned Maven dependencies: {missing}")


def version(*command):
    return subprocess.run(command, check=True, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout.strip()


def build_manifest(root, out, java, verilator):
    work = root / "work/rope_hardware_oracle"
    project = root / "chisel/matrix_norm_rope_hardware"
    inputs = [root / "integration/gemmini/EmitHeteroFP32Alu.scala",
              root / "integration/gemmini/EmitHeteroFP32Pipelines.scala",
              root / "integration/gemmini/EmitHeteroBF16Fma.scala",
              root / "scripts/generate_matrix_norm_rope_primitives.sh",
              project / "src/main/scala/EmitMatrixNormRoPEHardwarePrimitives.scala",
              project / "build.sbt", project / "project/build.properties",
              project / "repositories", project / "manifest.py", root / "chisel/rope_hardware_oracle/maven-lock.json"]
    hf_commit = "c1105e6ac6a0dd90fc80893efc4830ab609005d3"
    hf = work / "deps" / ("berkeley-hardfloat-" + hf_commit)
    hf_sources = {str(p.relative_to(hf)): sha256(p)
                  for p in sorted((hf / "hardfloat/src/main/scala").rglob("*.scala"))}
    emitted = out / "HeteroMatrixNormRoPEHardwarePrimitives.sv"
    rtl = emitted.read_text()
    forbidden = ("$bitstoshortreal", "$shortrealtobits", "shortreal ", "DPI-C")
    if any(token in rtl for token in forbidden):
        raise SystemExit("Generated RTL contains a behavioral floating-point substitute")
    modules = ("HeteroFP32Alu", "HeteroFP32MulPipeTag12", "HeteroFP32AddPipeTag12",
               "HeteroFP32MulPipeBit1", "HeteroFP32AddPipeBit1",
               "HeteroBF16FmaPre", "HeteroBF16FmaMul", "HeteroBF16FmaPost", "HeteroBF16FmaRound")
    for module in modules:
        if f"module {module}(" not in rtl:
            raise SystemExit(f"Missing arithmetic module: {module}")
    archives = ("hardfloat.tar.gz", "sbt-launch-1.10.2.jar", "llvm-firtool-1.62.1-linux-x64.jar")
    downloads = {n: sha256(work / "downloads" / n) for n in archives}
    deb = work / "downloads/verilator_5.032-1+b2_amd64.deb"
    if deb.exists():
        downloads[deb.name] = sha256(deb)
    manifest = {
        "schema_version": 1,
        "status": "PASS_CHISEL_EMIT_AND_VERILATOR_LINT",
        "arithmetic": "Unmodified production Chisel classes, Berkeley HardFloat RNE, tininess after rounding",
        "emission_top": "MatrixNormRoPEHardwarePrimitives",
        "arithmetic_modules": list(modules),
        "source_sha256": {str(p.relative_to(root)): sha256(p) for p in inputs},
        "emitted_sha256": {emitted.name: sha256(emitted)},
        "hardfloat": {"repository": "https://github.com/ucb-bar/berkeley-hardfloat",
                      "commit": hf_commit, "sources_sha256": hf_sources},
        "download_sha256": downloads,
        "maven_lock_sha256": sha256(root / "chisel/rope_hardware_oracle/maven-lock.json"),
        "maven_artifacts": json.loads((root / "chisel/rope_hardware_oracle/maven-lock.json").read_text())["artifacts"],
        "tool_versions": {"sbt": "1.10.2", "scala": "2.13.16", "chisel": "6.7.0",
                          "firtool": version(str(Path(os.environ.get("CHISEL_FIRTOOL_PATH", str(work / "deps/firtool/org.chipsalliance/llvm-firtool/linux-x64/bin"))) / "firtool"), "--version"),
                          "java": version(java, "-version"), "verilator": version(verilator, "--version"),
                          "python": sys.version.split()[0]},
        "verilator_bin": str(Path(verilator).resolve()),
        "generated_file": str(emitted),
        "lint_log_sha256": sha256(out / "lint.log"),
        "generate_log_sha256": sha256(out / "generate.log"),
        "limitations": ["Emission and lint establish synthesizable arithmetic, not physical synthesis, timing closure, or equivalence by themselves."]
    }
    return manifest


def verify_manifest(root, out):
    """Verify a manifest from this generator against current sources and artifacts.

    This is integrity verification, not remote attestation. Call the generator
    freshly before simulation; an arbitrary pre-existing manifest is not proof
    that its producer ran Chisel.
    """
    verify_cache(root, True)
    path = out / "manifest.json"
    manifest = json.loads(path.read_text())
    if manifest.get("schema_version") != 1 or manifest.get("status") != "PASS_CHISEL_EMIT_AND_VERILATOR_LINT":
        raise SystemExit("Invalid hardware-emission manifest status/schema")
    # Reconstruct the known source list and output filename independently.
    verilator = os.environ.get("VERILATOR_BIN", str(root / "work/rope_hardware_oracle/bin/verilator"))
    rebuilt = build_manifest(root, out, os.environ.get("JAVA_BIN", "java"), verilator)
    if rebuilt != manifest:
        keys = sorted(k for k in set(rebuilt) | set(manifest) if rebuilt.get(k) != manifest.get(k))
        raise SystemExit(f"Hardware manifest no longer matches current inputs/RTL/tools: {keys}")
    print("ROPE_HARDWARE_MANIFEST_VERIFIED")


if __name__ == "__main__":
    mode, root = sys.argv[1], Path(sys.argv[2]).resolve()
    if mode == "verify-cache":
        verify_cache(root, "--complete" in sys.argv[3:])
    elif mode == "verify":
        verify_manifest(root, Path(sys.argv[3]).resolve())
    elif mode == "write":
        out = Path(sys.argv[3]).resolve()
        manifest = build_manifest(root, out, sys.argv[4], sys.argv[5])
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    else:
        raise SystemExit(f"Unknown command: {mode}")
