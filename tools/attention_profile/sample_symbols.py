#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline main-ELF RIP symbolization. Raw samples stay local; return compact JSON."""
from __future__ import annotations
import argparse
import bisect
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time


def command(args):
    return subprocess.check_output(args, text=True, stderr=subprocess.PIPE, timeout=120)


def identity(tool):
    path = shutil.which(tool)
    if not path:
        raise ValueError(f"Required tool unavailable: {tool}")
    return {"path": path, "sha256": sha256(Path(path).resolve()),
            "version": command([path, "--version"]).splitlines()[0]}


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def source_map(build: Path, functions: list[dict]):
    """Map observed Verilator-like function definitions; source text stays local."""
    names = {item["name"].split("(", 1)[0].split("::")[-1] for item in functions}
    names = {name for name in names if re.fullmatch(r"[A-Za-z_]\w*", name)}
    found = {name: [] for name in names}
    files, total, scanned_chars = [], 0, 0
    deadline = time.monotonic() + 45
    scan_limit_chars = 512 * 1024 * 1024
    truncated = False
    hashes = {}
    # Generated code has one-line void function signatures in normal Verilator
    # output. A multi-line signature may extend up to eight lines. Declarations
    # and calls are excluded; unmatched definitions stay explicitly unmapped.
    signature = re.compile(r"^\s*(?:(?:static|inline|VL_INLINE_OPT)\s+)*(?:void|bool|[A-Za-z_]\w*)\s+([A-Za-z_]\w*)\s*\(")
    for path in sorted(build.rglob("*.cpp")) if build.is_dir() else []:
        if len(files) >= 50000:
            truncated = True; break
        size = path.stat().st_size
        rel = str(path.relative_to(build))
        files.append({"file": rel, "bytes": size}); total += size
        if not names or all(found.values()):
            continue
        if time.monotonic() > deadline or scanned_chars >= scan_limit_chars:
            truncated = True; continue
        with path.open(errors="replace") as f:
            pending = None
            for lineno, line in enumerate(f, 1):
                scanned_chars += len(line)
                if scanned_chars >= scan_limit_chars or (lineno % 256 == 0 and time.monotonic() > deadline):
                    truncated = True; break
                normalized = re.sub(r"__attribute__\s*\(\([^)]*\)\)", "", line)
                match = signature.match(normalized)
                if match and match.group(1) in names:
                    pending = [match.group(1), lineno, ""]
                if pending:
                    pending[2] += line
                    body, declaration = pending[2].find("{"), pending[2].find(";")
                    if body >= 0 and (declaration < 0 or body < declaration):
                        if rel not in hashes:
                            hashes[rel] = sha256(path)
                        found[pending[0]].append({"file": rel, "line": pending[1], "bytes": size, "sha256": hashes[rel]})
                        pending = None
                    elif declaration >= 0 or lineno - pending[1] >= 8:
                        pending = None
    for item in functions:
        short = item["name"].split("(", 1)[0].split("::")[-1]
        item["generated_sources"] = found.get(short, [])
    return {"mapping": "definition-signature scan; unrecognized definitions remain unmapped",
            "cpp_file_count": len(files), "cpp_total_bytes": total,
            "scan_truncated": truncated, "scanned_text_characters": scanned_chars,
            "scan_limit_characters": scan_limit_chars, "scan_time_limit_seconds": 45,
            "largest_cpp_files": sorted(files, key=lambda row: (-row["bytes"], row["file"]))[:20]}


def sized_symbols(path: Path, nm_path: str, dynamic=False):
    args = [nm_path, "-n", "-S", "--defined-only", "--demangle"]
    if dynamic:
        args.append("-D")
    try:
        output = command(args + [str(path)])
    except subprocess.CalledProcessError:
        return {}
    symbols = {}
    for line in output.splitlines():
        fields = line.split(maxsplit=3)
        if len(fields) != 4 or fields[2] not in ("t", "T", "w", "W", "i", "I"):
            continue
        try:
            begin, size = int(fields[0], 16), int(fields[1], 16)
        except ValueError:
            continue
        if not size:
            continue
        item = symbols.setdefault(begin, {"end": begin + size, "names": []})
        item["end"] = max(item["end"], begin + size)
        item["names"].append(fields[3])
    return symbols


def code_windows(sites, modules, all_symbols, objdump):
    """At most five short windows, starting at sampled instruction boundaries."""
    windows = []
    for (index, start, offset), count in sites.most_common(5):
        path = Path(modules[index]["path"])
        before = sha256(path)
        address = start + offset
        output = command([objdump, "-d", "-C", "--no-show-raw-insn",
                          f"--start-address={address}",
                          f"--stop-address={min(address + 64, all_symbols[(index, start)]['end'])}", str(path)])
        if sha256(path) != before:
            raise ValueError("ELF changed while extracting a code window")
        instructions = []
        for line in output.splitlines():
            match = re.match(r"^\s*[0-9a-f]+:\s+(.+)$", line)
            if not match:
                continue
            # Omit virtual-address columns/comments and replace branch targets
            # with their symbolic operand. Preserve instruction immediates.
            instruction = match.group(1).split("#", 1)[0].strip()
            instruction = re.sub(r"\b[0-9a-f]+\s+(<[^>]+>)", r"\1", instruction)
            instruction = re.sub(r"(?<![\w$])(?:0x)?[0-9a-f]{6,}(?![\w])", "<address-or-large-constant>", instruction)
            instructions.append(instruction)
            if len(instructions) == 10:
                break
        windows.append({"module": path.name, "function": all_symbols[(index, start)]["names"][0],
                        "offset": hex(offset), "samples_at_offset": count, "instructions": instructions,
                        "scope": "up to 10 instructions starting at sampled instruction; address columns removed"})
    return windows


def summarize(binary: Path, samples_path: Path, build: Path) -> dict:
    binary, samples_path, build = Path(binary).resolve(strict=True), Path(samples_path), Path(build)
    sample = json.loads(samples_path.read_text())
    if (sample.get("schema") != "ATTENTION_RIP_SAMPLES_V1" or
        sample.get("enabled") is not True or sample.get("completed") is not True):
        raise ValueError("Requires an enabled, completed sampler receipt")
    if Path(sample["executable"]).resolve(strict=True) != binary:
        raise ValueError("Sampled /proc/self/exe path differs from supplied ELF")
    if sample["target_tid"] <= 0 or sample["threads_at_start"] < 1 or sample["threads_at_finish"] < 1:
        raise ValueError("Missing target-thread receipt")
    rows = sample["samples"]
    if len(rows) != sample["sample_count"] or not 0 <= len(rows) <= sample["capacity"]:
        raise ValueError("Sample buffer accounting mismatch")
    if any(not 0 <= row["phase"] < 4 for row in rows):
        raise ValueError("Invalid eval phase")
    tools = {tool: identity(tool) for tool in ("nm", "objdump", "readelf")}
    before_hash = sha256(binary)
    # Exercise objdump against the exact executable, without rebuilding it.
    command([tools["objdump"]["path"], "-f", str(binary)])
    notes = command([tools["readelf"]["path"], "-n", str(binary)])
    match = re.search(r"Build ID:\s*([0-9a-fA-F]+)", notes)
    build_id = match.group(1).lower() if match else ""
    recorded_build_id = sample.get("elf_build_id", "").lower()
    if recorded_build_id and recorded_build_id != build_id:
        raise ValueError("Sampled executable GNU build ID differs from supplied ELF")
    with binary.open("rb") as f:
        header = f.read(20)
    if header[:6] != b"\x7fELF\x02\x01":
        raise ValueError("Requires ELF64 little endian")
    elf_type = int.from_bytes(header[16:18], "little")
    bias = int(sample["load_bias"], 16)
    if elf_type not in (2, 3) or (elf_type == 2 and bias):
        raise ValueError("Invalid executable type/load bias")
    modules = sample["modules"]
    if len(modules) > 128:
        raise ValueError("Too many sampled modules")
    main_indexes = [i for i, m in enumerate(modules) if Path(m["path"]).is_file() and Path(m["path"]).resolve() == binary]
    if len(main_indexes) != 1:
        raise ValueError("Missing or duplicate main executable mapping")
    main_index = main_indexes[0]
    if int(modules[main_index]["load_bias"], 16) != bias:
        raise ValueError("Main executable load bias mismatch")
    mapped = []
    for m in modules:
        ranges = [(int(lo, 16), int(hi, 16)) for lo, hi in m["executable_ranges"]]
        if any(lo >= hi for lo, hi in ranges):
            raise ValueError("Invalid executable segment")
        mapped.append(ranges)
    grouped = [[] for _ in modules]
    phases = Counter()
    unmapped = 0
    for row in rows:
        pc = int(row["pc"], 16); phases[row["phase"]] += 1
        hits = [i for i, ranges in enumerate(mapped) if any(lo <= pc < hi for lo, hi in ranges)]
        if len(hits) > 1:
            raise ValueError("Overlapping executable mappings")
        if not hits:
            unmapped += 1
        else:
            grouped[hits[0]].append(pc)
    # Parse only hit DSOs, with a hard bound. The main ELF is always checked.
    selected = [main_index] + [i for i, values in enumerate(grouped) if values and i != main_index]
    if len(selected) > 32:
        raise ValueError("Too many hit executable modules for bounded symbolization")
    function_counts, sites, all_symbols, module_reports = Counter(), Counter(), {}, []
    unknown = unmapped
    for index in selected:
        module = modules[index]; path = Path(module["path"])
        report = {"module": path.name, "is_main_executable": index == main_index,
                  "samples": len(grouped[index]), "resolved_samples": 0, "unknown_samples": 0}
        symbols, digest = {}, None
        if path.is_file():
            digest = sha256(path)
            symbols = sized_symbols(path, tools["nm"]["path"])
            if not symbols and index != main_index:
                symbols = sized_symbols(path, tools["nm"]["path"], dynamic=True)
            if sha256(path) != digest:
                raise ValueError(f"ELF changed while reading symbols: {path.name}")
            if index == main_index and digest != before_hash:
                raise ValueError("Main ELF changed during symbolization")
        if index == main_index and not symbols:
            raise ValueError("No sized main function symbols; retain the unstripped executable")
        starts = sorted(symbols)
        module_bias = int(module["load_bias"], 16)
        for pc in grouped[index]:
            rel = pc - module_bias
            ix = bisect.bisect_right(starts, rel) - 1
            if ix < 0 or rel >= symbols[starts[ix]]["end"]:
                report["unknown_samples"] += 1; unknown += 1; continue
            start = starts[ix]; key = (index, start)
            all_symbols[key] = symbols[start]
            function_counts[key] += 1; sites[(index, start, rel - start)] += 1
            report["resolved_samples"] += 1
        report["sha256"] = digest
        report["symbol_count"] = len(symbols)
        module_reports.append(report)
    windows = code_windows(sites, modules, all_symbols, tools["objdump"]["path"])
    if sha256(binary) != before_hash:
        raise ValueError("Main ELF changed after nm/objdump analysis")
    count = len(rows)
    percent = lambda n: round(100.0 * n / count, 4) if count else 0.0
    top = [{"module": Path(modules[index]["path"]).name,
            "is_main_executable": index == main_index,
            "name": all_symbols[(index, start)]["names"][0],
            "aliases": all_symbols[(index, start)]["names"][1:], "samples": n,
            "percent_of_all_samples": percent(n), "symbol_bytes": all_symbols[(index, start)]["end"] - start}
           for (index, start), n in function_counts.most_common(30)]
    generated = source_map(build, [item for item in top if item["is_main_executable"]])
    for item in top:
        item.setdefault("generated_sources", [])
    return {"schema": "ATTENTION_RIP_SUMMARY_V1", "sample_count": count,
            "scope": "eval caller thread self CPU only; helper/worker CPU is excluded",
            "sampling_route": "CLOCK_THREAD_CPUTIME_ID + SIGEV_THREAD_ID + SIGPROF/ucontext RIP",
            "elf_sha256": before_hash, "elf_build_id": build_id,
            "sample_elf_identity_verified": bool(recorded_build_id),
            "elf_path_verified": True, "elf_stable_across_analysis": True,
            "elf_type": "ET_EXEC" if elf_type == 2 else "ET_DYN/PIE", "tools": tools,
            "interval_ns": sample["interval_ns"], "capacity": sample["capacity"],
            "dropped_buffer_full": sample["dropped_buffer_full"], "buffer_saturated": sample["dropped_buffer_full"] > 0,
            "timer_overruns": sample["timer_overruns"], "outside_eval_events": sample["outside_eval_events"],
            "counter_max": sample["counter_max"], "window_counts": sample["window_counts"],
            "target_tid": sample["target_tid"], "threads_at_start": sample["threads_at_start"],
            "threads_at_finish": sample["threads_at_finish"],
            "phase_sample_counts": [phases[i] for i in range(4)], "modules": module_reports,
            "unmapped_module_samples": unmapped, "unknown_count": unknown, "unknown_percent": percent(unknown),
            "resolved_sample_fraction": (count - unknown) / count if count else 0.0,
            "functions": top,
            "instruction_offsets": [{"module": Path(modules[index]["path"]).name,
                                     "function": all_symbols[(index, start)]["names"][0],
                                     "offset": hex(offset), "samples": n}
                                    for (index, start, offset), n in sites.most_common(30)],
            "generated_cpp": generated, "code_windows": windows, "raw_instruction_addresses_included": False,
            "limitations": ["Statistical user RIP samples; no call stacks or RTL attribution",
                            "Inlining is charged to containing function unless resolved with existing debug info",
                            "Unexported libc implementations and stripped/zero-sized symbols may be unresolved; consult module unknown counts",
                            "Timer quantization, delayed delivery and periodic sampling can bias instruction counts",
                            "Buffer saturation truncates the sampled interval; counters saturate at counter_max",
                            "High unknown fraction or few samples prevents a confident hotspot conclusion",
                            "DSO mappings are captured at first eval; later dlopen/dlclose is unsupported"]}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--elf", type=Path, required=True)
    ap.add_argument("--samples", type=Path, required=True)
    ap.add_argument("--generated-dir", type=Path, default=Path("__no_generated_cpp__"))
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    text = json.dumps(summarize(args.elf, args.samples, args.generated_dir), indent=2) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end="")

if __name__ == "__main__":
    main()
