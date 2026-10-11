#!/usr/bin/env python3
"""Source-bound Scala/CHIRRTL gate. Never invokes firtool, Verilator or numerical RTL.

The actual frozen MatrixPipeline and protocol are patched in a fresh workspace.
Only exact existing BlackBox/legacy bundle declarations are extracted from their
larger source files; retained arithmetic remains an unresolved BlackBox. This is
a frontend structural gate, not an executable hardware equivalence proof.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import urllib.request

BASE = "43440dbad48c8e8af3112c1ae658db3ae64d76eb"
PREFIX = "chisel/continuous_prefill/src/main/scala/heteronpu/continuous/"
CANDIDATE = "candidates/qwen2_resident_matrix"
MAVEN = "https://repo.maven.apache.org/maven2/"


def validate_manifest(manifest: dict) -> None:
    expected = {"return_tag.patch", "ReturnTagElaborationCheck.scala", "BaselineElaboration.scala",
                "SeedElaborationCheck.scala", "MatrixAccumulatorSeedProtocol.scala",
                "MatrixAccumulatorSeedController.scala", "seed_protocol_model.py",
                "test_seed_protocol_model.py", "test_return_tag_contract.py"}
    if (manifest["base_commit"] != BASE or set(manifest["candidate_files"]) != expected
        or set(manifest["original_sources"]) != {"BurstProtocol.scala", "MatrixPipeline.scala", "RetainedMatrix.scala", "WideMatrix.scala"}
        or set(manifest["patched_sources"]) != {"BurstProtocol.scala", "MatrixPipeline.scala"}):
        raise ValueError("candidate manifest identity set changed")
    pins = [manifest["maven_lock_sha256"], manifest["abi_declarations_sha256"]]
    for field in ["candidate_files", "original_sources", "patched_sources"]:
        pins.extend(manifest[field].values())
    if any(not isinstance(pin, str) or not re.fullmatch(r"[0-9a-f]{64}", pin) for pin in pins):
        raise ValueError("invalid candidate identity hash")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def checked(data: bytes, expected: str, label: str) -> bytes:
    if digest(data) != expected:
        raise ValueError("identity drift: " + label)
    return data


def frozen_source(root: Path, path: str, expected: str) -> bytes:
    data = subprocess.check_output(["git", "show", BASE + ":" + path], cwd=root)
    return checked(data, expected, path)


def declaration(source: str, name: str) -> str:
    match = re.search(r"^class " + re.escape(name) + r"\b", source, re.M)
    if match is None:
        raise ValueError("missing declaration: " + name)
    start = match.start()
    cursor = source.index("{", start) + 1
    depth = 1
    while depth and cursor < len(source):
        depth += (source[cursor] == "{") - (source[cursor] == "}")
        cursor += 1
    if depth:
        raise ValueError("unterminated declaration: " + name)
    return source[start:cursor]


def normalized_chirrtl(text: str) -> str:
    # Only source locations differ between isolated original/candidate files.
    # A printf string may itself contain " @[... ]". Never start there and
    # accidentally erase real operands up to a later source annotation.
    result = []
    for line in text.splitlines(keepends=True):
        quoted = escaped = False
        normalized = line
        for index, char in enumerate(line):
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif line.startswith(" @[", index):
                tail = re.fullmatch(r" @\[[^\n]*\][ \t]*(\r?\n)?", line[index:])
                if tail:
                    normalized = line[:index] + (tail.group(1) or "")
                    break
        result.append(normalized)
    return "".join(result)


def dependency_paths(artifacts: dict[str, str]) -> dict[str, str]:
    paths = {p: h for p, h in artifacts.items() if p.endswith(".jar")
             and "_2.12" not in p and "/2.12." not in p
             and not p.startswith("org/scala-sbt/")}
    for path, sha in paths.items():
        if path.startswith("/") or ".." in Path(path).parts or not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise ValueError("invalid dependency pin")
    return paths


def structural_counts(seed: str, service: str, tag_bits: int = 16) -> dict:
    """Count actual frontend declarations, with fail-closed expected shapes."""
    if re.search(r"^\s*(?:inst|cmem|smem)\s", seed, re.M):
        raise ValueError("unexpected seed submodule/memory resource")
    registers = re.findall(r"^\s*reg(?:reset)?\s+\w+\s*:\s*(.*?), clock", seed, re.M)
    if len(registers) != 9 or any("[" in item for item in registers):
        raise ValueError("unexpected seed register shape")
    control_bits = sum(int(n) for item in registers for n in re.findall(r"UInt<(\d+)>", item))
    if control_bits != 138:
        raise ValueError("seed control bit count drift")
    leaves = len(re.findall(r"^\s*inst leaves_\d+ of qwen2_matrix_command_endpoint(?:_\d+)?\b", service, re.M))
    gates = len(re.findall(r"^\s*inst gate(?:_\d+)? of tc_clk_gating(?:_\d+)?\b", service, re.M))
    if leaves != 8 or gates != 8:
        raise ValueError("retained resource count drift")
    for kind, name, depth in [("cmem", "ram", 8), ("reg", "storage", 2)]:
        line = re.search(r"^\s*"+kind+r" "+name+r" : ([^\n]+)", service, re.M)
        if line is None or f"returnTag : UInt<{tag_bits}>" not in line.group(1) or not re.search(r"\}\s*\["+str(depth)+r"\]", line.group(1)):
            raise ValueError("tag storage declaration drift")
    return {"seed_control_register_bits": control_bits, "seed_payload_register_bits": 0,
            "retained_endpoint_instances": leaves, "retained_clock_gate_instances": gates,
            "tag_metadata_entries": 8, "tag_result_entries": 2, "added_tag_storage_bits": 10*tag_bits,
            "physical_area_or_timing_measured": False}


def prepare_dependencies(root: Path, cache: Path, manifest: dict) -> tuple[str, Path, dict]:
    lock_path = root / "chisel/rope_hardware_oracle/maven-lock.json"
    lock = checked(lock_path.read_bytes(), manifest["maven_lock_sha256"], "Maven lock")
    selected = dependency_paths(json.loads(lock)["artifacts"])

    def get(item):
        path, expected = item
        dest = cache / path
        if dest.exists():
            data = checked(dest.read_bytes(), expected, path)
        else:
            with urllib.request.urlopen(MAVEN + path, timeout=60) as response:
                data = checked(response.read(), expected, path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        return {"path": path, "sha256": expected, "bytes": len(data)}

    with ThreadPoolExecutor(max_workers=4) as pool:
        receipt = list(pool.map(get, sorted(selected.items())))
    cp = ":".join(str(cache / path) for path in sorted(selected))
    plugin = cache / "org/chipsalliance/chisel-plugin_2.13.16/6.7.0/chisel-plugin_2.13.16-6.7.0.jar"
    return cp, plugin, {"origin": MAVEN, "lock_sha256": digest(lock), "jars": receipt}


def run_gate(root: Path, out: Path, cache: Path) -> dict:
    candidate = root / CANDIDATE
    manifest = json.loads((candidate / "manifest.json").read_text())
    validate_manifest(manifest)
    if out.exists():
        raise ValueError("use a fresh output directory; existing evidence is preserved")
    out.mkdir(parents=True)
    report = {"base_commit": BASE, "status": "STARTED", "rtl_generated": False,
              "arithmetic_executed": False, "hardware_protocol_executed": False,
              "native_numerical_acceptance": "UNCHANGED_OPEN", "commands": []}

    def save():
        (out / "summary.json").write_text(json.dumps(report, indent=2) + "\n")

    def run(command: list[str], log: Path):
        started = time.monotonic()
        with log.open("w") as stream:
            result = subprocess.run(command, cwd=root, stdout=stream, stderr=subprocess.STDOUT, timeout=180)
        report["commands"].append({"argv": command, "log": str(log.relative_to(out)),
                                   "exit_code": result.returncode, "wall_seconds": time.monotonic()-started})
        save()
        if result.returncode:
            raise RuntimeError(f"frontend command failed; preserved log: {log}")

    try:
        for name, sha in manifest["candidate_files"].items():
            checked((candidate / name).read_bytes(), sha, name)
        source = {name: frozen_source(root, PREFIX+name, sha)
                  for name, sha in manifest["original_sources"].items()}
        report["source_pins"] = manifest
        cp, plugin, dep = prepare_dependencies(root, cache, manifest)
        (out / "dependency_receipt.json").write_text(json.dumps(dep, indent=2)+"\n")
        report["dependency_receipt_sha256"] = digest((out / "dependency_receipt.json").read_bytes())
        report["java_version"] = subprocess.check_output(["java", "-version"], stderr=subprocess.STDOUT, text=True).strip()
        java = ["java", "-Xmx1024m", "-XX:ActiveProcessorCount=1"]
        abi = "package heteronpu.continuous\nimport chisel3._\nimport chisel3.util._\n"
        for name, classes in [("RetainedMatrix.scala", ["RetainedMatrixEndpoint", "RetainedMatrixClockGate"]),
                              ("WideMatrix.scala", ["WideMatrixStep", "WideMatrixResult"])]:
            for cls in classes:
                abi += declaration(source[name].decode(), cls)+"\n"
        abi_path = out / "RetainedAbi.scala"
        abi_path.write_text(abi)
        checked(abi_path.read_bytes(), manifest["abi_declarations_sha256"], "exact ABI extraction")
        report["abi_scope"] = "Exact existing declarations. Arithmetic unresolved BlackBoxes, not replacement arithmetic."

        for variant in ["baseline", "candidate"]:
            work = out / variant
            work.mkdir()
            classes = work / "classes"
            classes.mkdir()
            source_root = work / "source"
            for name in ["BurstProtocol.scala", "MatrixPipeline.scala"]:
                path = source_root / PREFIX / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(source[name])
            if variant == "candidate":
                subprocess.run(["git", "apply", "--check", str(candidate/"return_tag.patch")], cwd=source_root, check=True)
                subprocess.run(["git", "apply", str(candidate/"return_tag.patch")], cwd=source_root, check=True)
                for name, sha in manifest["patched_sources"].items():
                    checked((source_root/PREFIX/name).read_bytes(), sha, name)
                harness = candidate / "ReturnTagElaborationCheck.scala"
                main = "heteronpu.continuous.ReturnTagElaborationCheck"
            else:
                harness = candidate / "BaselineElaboration.scala"
                main = "heteronpu.continuous.BaselineElaboration"
            inputs = [abi_path, source_root/PREFIX/"BurstProtocol.scala", source_root/PREFIX/"MatrixPipeline.scala", harness]
            run(java+["-cp", cp, "scala.tools.nsc.Main", "-classpath", cp,
                      "-Xplugin:"+str(plugin), "-d", str(classes)]+list(map(str,inputs)), work/"compile.log")
            run(java+["-cp", str(classes)+":"+cp, main, str(work/"chirrtl")], work/"elaboration.log")

        report["default_ir_comparisons"] = {}
        for name in ["fifo_default.fir", "service_default.fir"]:
            before = normalized_chirrtl((out/"baseline/chirrtl"/name).read_text())
            after = normalized_chirrtl((out/"candidate/chirrtl"/name).read_text())
            report["default_ir_comparisons"][name] = {"equal": before==after, "normalized_sha256": digest(before.encode())}
            if before != after:
                raise ValueError("default-zero CHIRRTL drift: "+name)

        seed = out / "seed"
        seed.mkdir()
        classes = seed / "classes"
        classes.mkdir()
        inputs = [candidate/name for name in ["MatrixAccumulatorSeedProtocol.scala", "MatrixAccumulatorSeedController.scala", "SeedElaborationCheck.scala"]]
        run(java+["-cp", cp, "scala.tools.nsc.Main", "-classpath", cp,
                  "-Xplugin:"+str(plugin), "-d", str(classes)]+list(map(str,inputs)), seed/"compile.log")
        run(java+["-cp", str(classes)+":"+cp, "heteronpu.continuous.SeedElaborationCheck", str(seed/"chirrtl")], seed/"elaboration.log")
        emitted = (seed/"chirrtl/seed_controller.fir").read_text()
        report["frontend_resource_declarations"] = structural_counts(emitted, (out/"candidate/chirrtl/service_16.fir").read_text())
        report["generated_chirrtl"] = {str(p.relative_to(out)): {"sha256": digest(p.read_bytes()), "bytes": p.stat().st_size}
                                       for p in sorted(out.rglob("*.fir"))}
        report["status"] = "PASS_FRONTEND_ONLY"
        save()
        return report
    except Exception as error:
        report["status"] = "FAILED"
        report["error"] = str(error)
        save()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args()
    report = run_gate(args.repo.resolve(), args.out.resolve(), args.cache.resolve())
    print(json.dumps({"status": report["status"], "rtl_generated": False, "arithmetic_executed": False}))


if __name__ == "__main__":
    main()
