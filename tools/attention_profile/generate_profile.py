#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Generate a bounded diagnostic driver from two immutable production sources.

This does not elaborate RTL or build/run Verilator. The emitted .cpp is the only
replacement argument in the production build recipe. It is not an acceptance
runner; a bounded prefix always reports numerical_acceptance=false.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

SOURCE_COMMIT = "6959810545203d5f9508075b311dba52f1bee0c9"
SOURCE_HASHES = {
    "chisel/continuous_prefill/tests/host_bf16_attention_core.cpp":
        "fd54f0620b3782dd69c3619ac60e96e2bf1087e7b6bd6c0e3a6cf7edb42085d4",
    "chisel/continuous_prefill/tests/host_physical_axi.h":
        "c328df0b560c26b310b1e8f8b9b91d23acf68a59f5ce1b1122c201a2534ff02e",
}
MIN_CYCLES, MAX_CYCLES = 37, 65536
TRANSFORMS = (
    (b"#pragma once\n", b'#pragma once\n#include "profile_runtime.h"\n'),
    (b"  void step(){\n", b"  void step(){\n    attention_profile::StepTimer attentionProfileStep;\n"),
    (b"    d.eval();\n", b"    attentionProfileStep.eval(d,0);attentionProfileStep.capture(*this);\n"),
    (b"    d.clock=1;d.eval();ticks++;\n", b"    d.clock=1;attentionProfileStep.eval(d,1);ticks++;\n"),
    (b"    d.clock=0;d.eval();\n", b"    d.clock=0;attentionProfileStep.eval(d,2);\n    attentionProfileStep.complete(*this);\n"),
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cycle_limit(text: str) -> int:
    # Reject signs, whitespace, hexadecimal, floats, and excessive decimal input.
    if not text.isascii() or not text.isdigit() or len(text) > 5:
        raise argparse.ArgumentTypeError("cycles must be an unsigned decimal integer")
    value = int(text)
    if not MIN_CYCLES <= value <= MAX_CYCLES:
        raise argparse.ArgumentTypeError(f"cycles must be in [{MIN_CYCLES}, {MAX_CYCLES}]")
    return value


def frozen_sources(repo: Path) -> dict[str, bytes]:
    found = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", SOURCE_COMMIT + "^{commit}"], text=True
    ).strip()
    if found != SOURCE_COMMIT:
        raise ValueError("frozen commit identity mismatch")
    result = {}
    for path, expected in SOURCE_HASHES.items():
        data = subprocess.check_output(["git", "-C", str(repo), "show", SOURCE_COMMIT + ":" + path])
        if sha256(data) != expected:
            raise ValueError("frozen source SHA256 mismatch: " + path)
        result[path] = data
    return result


def instrument_header(original: bytes) -> bytes:
    if original.count(b"d.eval();") != 3:
        raise ValueError("expected exactly three production eval calls")
    patched = original
    for old, new in TRANSFORMS:
        if patched.count(old) != 1:
            raise ValueError("instrumentation anchor missing or ambiguous: " + repr(old))
        patched = patched.replace(old, new, 1)
    restored = patched
    for old, new in reversed(TRANSFORMS):
        if restored.count(new) != 1:
            raise ValueError("instrumentation reversal missing or ambiguous")
        restored = restored.replace(new, old, 1)
    if restored != original or b"d.eval();" in patched:
        raise ValueError("instrumentation not exactly reversible")
    return patched


def generate(repo: Path, output: Path, cycles: int) -> dict:
    if type(cycles) is not int or not MIN_CYCLES <= cycles <= MAX_CYCLES:
        raise ValueError("invalid fixed prefix limit")
    if not output.is_absolute() or output.exists() or output.is_symlink():
        raise ValueError("output must be an absolute, new, nonsymlink directory")
    sources = frozen_sources(repo)
    assets = Path(__file__).resolve().parent
    runtime = (assets / "profile_runtime.h").read_bytes()
    wrapper = (assets / "profile_driver.cpp.in").read_bytes().replace(
        b"@CYCLE_LIMIT@", str(cycles).encode("ascii")
    )
    emitted = {
        "profile_runtime.h": runtime,
        "profile_driver.cpp": wrapper,
    }
    for path, data in sources.items():
        name = Path(path).name
        emitted["original/" + name] = data
        emitted[name] = instrument_header(data) if name == "host_physical_axi.h" else data
    receipt = {
        "schema": "HOST_ATTENTION_PREFIX_TRANSFORMATION_V1",
        "source_base_commit": SOURCE_COMMIT,
        "numerical_acceptance": False,
        "cycle_limit": cycles,
        "prefix_counts_constructor_cycles": True,
        "constructor_cycles": 36,
        "stop_point": "after third eval and original ACK/store bookkeeping of limit step",
        "production_driver_byte_identical": True,
        "original_sources_sha256": SOURCE_HASHES,
        "generated_files_sha256": {name: sha256(data) for name, data in sorted(emitted.items())},
        "generator_sha256": sha256(Path(__file__).read_bytes()),
        "header_edits": [{"old": old.decode(), "new": new.decode(), "count": 1}
                         for old, new in TRANSFORMS],
        "wrapper_changes": "include frozen .cpp under renamed main; catch dedicated non-std prefix stop",
        "compile_source": "profile_driver.cpp",
        "required_cflags": ["-O2", "-std=c++17", "-ffp-contract=off", "-fno-fast-math"],
        "binary_arguments": "FIXTURE FRESH_OUTPUT [pass|cache-v-write-error|context-write-error]",
        "result_files": ["attention_profile.json", "prefix_events.jsonl"],
        "event_digest_input": "exact prefix_events.jsonl bytes; no timings or output paths",
        "exit_contract": {"0": "diagnostic prefix reached, never numerical acceptance",
                          "2": "invalid arguments, driver failure, premature finish or profile error"},
    }
    output.mkdir(parents=True, exist_ok=False)
    for name, data in emitted.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (output / "transformation_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cycles", type=cycle_limit, default=4096)
    args = parser.parse_args()
    try:
        receipt = generate(args.repo.resolve(), args.output, args.cycles)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(2, "PROFILE_GENERATION_FAILED: " + str(exc) + "\n")
    print(json.dumps({"status": "GENERATED_DIAGNOSTIC_DRIVER", "numerical_acceptance": False,
                      "compile_source": str(args.output / receipt["compile_source"]),
                      "receipt": str(args.output / "transformation_receipt.json")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
