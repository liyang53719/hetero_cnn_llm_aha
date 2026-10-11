#!/usr/bin/env python3
"""Compile the source-bound resident reader and optional real Dense read hook.

Uses the existing locked frontend toolchain. Emits CHIRRTL only; no firtool,
RTL simulation, floating-point execution, owner activation or area measurement.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import time

from check_matrix_interface_candidate import (
    BASE, CANDIDATE, PREFIX, checked, declaration, digest, frozen_source,
    normalized_chirrtl, prepare_dependencies,
)

FILES = {"ResidentCSeedReader.scala", "ResidentCSeedFrontend.scala",
         "ResidentDenseBaselineCheck.scala", "ResidentDenseElaborationCheck.scala",
         "resident_seed_reader_model.py", "test_resident_seed_reader.py",
         "streaming_dense_read_hook.patch"}
SOURCES = {"StreamingDense.scala", "DenseReadPlanner.scala", "Protocol.scala",
           "QwenOwnerProtocol.scala", "BurstProtocol.scala"}
SEED = {"MatrixAccumulatorSeedProtocol.scala", "MatrixAccumulatorSeedController.scala",
        "seed_protocol_model.py"}


def validate_manifest(manifest: dict) -> None:
    if (manifest["base_commit"] != BASE or set(manifest["candidate_files"]) != FILES
        or set(manifest["original_sources"]) != SOURCES
        or set(manifest["seed_dependencies"]) != SEED
        or set(manifest["patched_sources"]) != {"StreamingDense.scala"}):
        raise ValueError("resident manifest identity set changed")
    pins = [manifest["owner_abi_sha256"], manifest["maven_lock_sha256"]]
    for key in ["candidate_files", "original_sources", "seed_dependencies", "patched_sources"]:
        pins.extend(manifest[key].values())
    if any(not isinstance(x, str) or not re.fullmatch(r"[0-9a-f]{64}", x) for x in pins):
        raise ValueError("invalid resident identity hash")


def owner_abi(source: str) -> str:
    # Keep the exact existing package/imports, kind enum and two complete jobs.
    marker = "/** No block launch is exposed."
    if source.count(marker) != 1:
        raise ValueError("owner ABI boundary changed")
    abi = source.split(marker)[0]
    if len(re.findall(r"^class ", abi, re.M)) != 2 or "class QwenOwnerKernel" in abi:
        raise ValueError("owner ABI declaration set changed")
    for name in ["QwenOwnerJob", "QwenOwnerResult"]:
        declaration(abi, name)
    return abi


def module(text: str, name: str) -> str:
    match = re.search(r"^  module " + re.escape(name) + r"\b[^\n]*\n", text, re.M)
    if match is None:
        raise ValueError("missing frontend module: " + name)
    end = re.search(r"^  (?:module|extmodule) ", text[match.end():], re.M)
    return text[match.start():match.end()+end.start()] if end else text[match.start():]


def register_bits(body: str) -> int:
    total = 0
    for item in re.findall(r"^\s*reg(?:reset)?\s+\w+\s*:\s*(.*?), clock", body, re.M):
        residual = re.sub(r"UInt<\d+>", "", item)
        residual = re.sub(r"\b\w+\s*:", "", residual)
        if "[" in item or residual.strip("{}, \t"):
            raise ValueError("unhandled register declaration")
        total += sum(map(int, re.findall(r"UInt<(\d+)>", item)))
    return total


def memory_declarations(body: str) -> list[str]:
    return re.findall(r"^\s*(?:smem|cmem)\s+[^\n]+", normalized_chirrtl(body), re.M)


def dense_source_locations(text: str, baseline_source: str, current_source: str) -> str:
    """Normalize only exact Chisel-generated assertion source coordinates.

    Each assertion's full source line must occur exactly once in each source.
    Its message, source code and operands remain untouched. This does not
    normalize arbitrary printf strings or change any executable IR node.
    """
    current_lines = current_source.splitlines()
    baseline_lines = baseline_source.splitlines()
    for old_index, line in enumerate(baseline_lines, 1):
        if "assert(" not in line:
            continue
        if current_lines.count(line) != 1 or baseline_lines.count(line) != 1:
            raise ValueError("assertion source line changed or became ambiguous")
        new_index = current_lines.index(line)+1
        escaped = json.dumps(line.strip(), ensure_ascii=False)[1:-1]
        old = f"\\n    at StreamingDense.scala:{old_index} {escaped}\\n"
        new = f"\\n    at StreamingDense.scala:{new_index} {escaped}\\n"
        # Chisel's generated diagnostic must be a printf Assertion failed
        # literal, never a user string which happens to mention a source line.
        matches = [ln for ln in text.splitlines() if new in ln]
        if (text.count(new) != 1 or len(matches) != 1
            or not re.match(r'\s*printf\(clock,\s*[^"\n]*,\s*"Assertion failed:', matches[0])
            or new+'"' not in matches[0]):
            raise ValueError("missing or ambiguous generated assertion diagnostic")
        text = text.replace(new, old)
    return normalized_chirrtl(text)


def check_ports(body: str, banks: set[str]) -> None:
    ports = re.findall(r"^\s*(read|write|rdwr) mport\s+\w+\s*=\s*(\w+)\[", body, re.M)
    expected = Counter((direction, bank) for bank in banks for direction in ["read", "write"])
    if Counter(ports) != expected:
        raise ValueError("memory port ledger drift per named bank")


def resource_ledger(reader: str, frontend: str, baseline: str, hooked: str) -> dict:
    rb = module(reader, "ResidentCSeedReader")
    fb = module(frontend, "ResidentCSeedFrontend")
    mb = module(frontend, "ResidentSeedBankReadMux")
    cb = module(frontend, "MatrixAccumulatorSeedController")
    if re.search(r"^\s*(?:inst|smem|cmem)\s", rb, re.M):
        raise ValueError("reader gained a memory or arithmetic submodule")
    if re.search(r"^\s*(?:inst|smem|cmem)\s", mb, re.M):
        raise ValueError("read mux gained memory or submodule")
    instances = re.findall(r"^\s*inst (\w+) of (\w+)", fb, re.M)
    if instances != [("reader", "ResidentCSeedReader"), ("controller", "MatrixAccumulatorSeedController"), ("ports", "ResidentSeedBankReadMux")]:
        raise ValueError("resident frontend instance set drift")
    counts = {"reader_register_bits": register_bits(rb),
              "read_mux_register_bits": register_bits(mb),
              "frontend_register_bits": register_bits(fb),
              "seed_controller_register_bits": register_bits(cb)}
    if counts != {"reader_register_bits": 720, "read_mux_register_bits": 5,
                  "frontend_register_bits": 1, "seed_controller_register_bits": 138}:
        raise ValueError("resident register ledger drift: " + str(counts))
    memories = memory_declarations(fb)
    if len(memories) != 16 or any(not re.search(r"UInt<256>\s*\[1024\]", line) for line in memories):
        raise ValueError("resident A/C physical memory ledger drift")
    check_ports(fb, {f"aBanks_{i}" for i in range(16)})
    before = module(baseline, "StreamingDenseOwner")
    after = module(hooked, "StreamingDenseOwner")
    if memory_declarations(before) != memory_declarations(after):
        raise ValueError("optional read hook changed physical SRAM declarations")
    for body in [before, after]:
        check_ports(body, {f"{bank}_{i}" for bank in ["aBanks", "wBanks"] for i in range(16)})
    if register_bits(module(hooked, "ResidentSeedBankReadMux")) != 5:
        raise ValueError("production hook mux state drift")
    return {**counts, "total_declared_reader_frontend_register_bits": sum(counts.values()),
            "reader_payload_bits_included_above": 512, "resident_frontend_a_c_bytes": 512*1024,
            "resident_frontend_a_c_banks": 16, "resident_frontend_read_ports_per_bank": 1,
            "resident_frontend_write_ports_per_bank": 1,
            "production_hook_preserves_existing_a_words_per_bank": 1376,
            "production_hook_preserves_existing_b_words_per_bank": 160,
            "production_hook_read_mux_added_register_bits": 5,
            "production_owner_lease_metadata_installed": False,
            "leaf_seed_datapath_installed": False, "area_timing_measured": False}


def run_gate(root: Path, out: Path, cache: Path) -> dict:
    candidate = root/CANDIDATE
    manifest = json.loads((candidate/"resident_manifest.json").read_text())
    validate_manifest(manifest)
    if out.exists():
        raise ValueError("use a fresh output directory; existing evidence is preserved")
    out.mkdir(parents=True)
    report = {"base_commit": BASE, "status": "STARTED", "rtl_generated": False,
              "hardware_protocol_executed": False, "arithmetic_executed": False,
              "production_default_enabled": False, "commands": [], "source_pins": manifest}

    def save():
        (out/"summary.json").write_text(json.dumps(report, indent=2)+"\n")

    def run(argv: list[str], log: Path):
        start = time.monotonic()
        with log.open("w") as stream:
            result = subprocess.run(argv, cwd=root, stdout=stream, stderr=subprocess.STDOUT, timeout=180)
        report["commands"].append({"argv": argv, "log": str(log.relative_to(out)),
                                   "exit_code": result.returncode, "wall_seconds": time.monotonic()-start})
        save()
        if result.returncode:
            raise RuntimeError("resident frontend failed; preserved log: " + str(log))

    try:
        for key in ["candidate_files", "seed_dependencies"]:
            for name, sha in manifest[key].items():
                checked((candidate/name).read_bytes(), sha, name)
        sources = {name: frozen_source(root, PREFIX+name, sha) for name, sha in manifest["original_sources"].items()}
        abi = checked(owner_abi(sources["QwenOwnerProtocol.scala"].decode()).encode(), manifest["owner_abi_sha256"], "exact owner ABI")
        (out/"QwenOwnerAbi.scala").write_bytes(abi)
        cp, plugin, deps = prepare_dependencies(root, cache, manifest)
        (out/"dependency_receipt.json").write_text(json.dumps(deps, indent=2)+"\n")
        report["java_version"] = subprocess.check_output(["java", "-version"], stderr=subprocess.STDOUT, text=True).strip()
        java = ["java", "-Xmx1024m", "-XX:ActiveProcessorCount=1"]
        compiler = java+["-cp", cp, "scala.tools.nsc.Main", "-classpath", cp, "-Xplugin:"+str(plugin)]
        common = [candidate/n for n in ["MatrixAccumulatorSeedProtocol.scala", "MatrixAccumulatorSeedController.scala", "ResidentCSeedReader.scala"]]
        for variant in ["baseline", "candidate"]:
            work = out/variant
            classes = work/"classes"
            classes.mkdir(parents=True)
            for name, data in sources.items():
                path = work/"source"/PREFIX/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            inputs = [out/"QwenOwnerAbi.scala"] + [work/"source"/PREFIX/n for n in sorted(SOURCES-{"QwenOwnerProtocol.scala"})]
            if variant == "candidate":
                patch = str(candidate/"streaming_dense_read_hook.patch")
                subprocess.run(["git", "apply", "--check", patch], cwd=work/"source", check=True)
                subprocess.run(["git", "apply", patch], cwd=work/"source", check=True)
                checked((work/"source"/PREFIX/"StreamingDense.scala").read_bytes(), manifest["patched_sources"]["StreamingDense.scala"], "patched StreamingDense")
                inputs += common+[candidate/"ResidentDenseElaborationCheck.scala", candidate/"ResidentCSeedFrontend.scala"]
                main = "ResidentDenseElaborationCheck"
            else:
                inputs += [candidate/"ResidentDenseBaselineCheck.scala"]
                main = "ResidentDenseBaselineCheck"
            run(compiler+["-d", str(classes)]+list(map(str, inputs)), work/"compile.log")
            run(java+["-cp", str(classes)+":"+cp, "heteronpu.continuous."+main, str(work/"chirrtl")], work/"elaboration.log")
        report["default_ir_comparisons"] = {}
        original_dense = sources["StreamingDense.scala"].decode()
        patched_dense = (out/"candidate/source"/PREFIX/"StreamingDense.scala").read_text()
        report["assertion_source_mappings"] = [
            {"baseline_line": index, "candidate_line": patched_dense.splitlines().index(line)+1,
             "source_line_sha256": digest(line.encode()), "matches_per_emitted_module": 1}
            for index, line in enumerate(original_dense.splitlines(), 1) if "assert(" in line]
        for name in ["dense_default.fir", "dense_small.fir"]:
            a = dense_source_locations((out/"baseline/chirrtl"/name).read_text(), original_dense, original_dense)
            b = dense_source_locations((out/"candidate/chirrtl"/name).read_text(), original_dense, patched_dense)
            report["default_ir_comparisons"][name] = {"equal": a == b, "normalized_sha256": digest(a.encode())}
            if a != b:
                raise ValueError("default-off Dense CHIRRTL drift: " + name)
        classes = out/"candidate/classes"
        run(java+["-cp", str(classes)+":"+cp, "heteronpu.continuous.ResidentCSeedElaborationCheck", str(out/"reader/chirrtl")], out/"reader_elaboration.log")
        report["resource_ledger"] = resource_ledger(
            (out/"reader/chirrtl/resident_c_seed_reader.fir").read_text(),
            (out/"reader/chirrtl/resident_c_seed_frontend.fir").read_text(),
            (out/"baseline/chirrtl/dense_default.fir").read_text(),
            (out/"candidate/chirrtl/dense_hook.fir").read_text())
        report["generated_chirrtl"] = {str(p.relative_to(out)): {"sha256": digest(p.read_bytes()), "bytes": p.stat().st_size} for p in sorted(out.rglob("*.fir"))}
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
    result = run_gate(args.repo.resolve(), args.out.resolve(), args.cache.resolve())
    print(json.dumps({"status": result["status"], "rtl_generated": False}))


if __name__ == "__main__":
    main()
