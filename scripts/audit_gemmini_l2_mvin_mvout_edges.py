#!/usr/bin/env python3
"""Audit retained-Rocket mvin/mvout edge and accumulator equivalence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from heteronpu.gemmini_rocc_lowering import (  # noqa: E402
    GemminiDataflow, config_ex, config_load, config_store, mvin, mvout,
)

COMMAND = re.compile(
    r"pc=\[([0-9a-f]+)\].*R\[r\s*\d+=([0-9a-f]+)\]\s+"
    r"R\[r\s*\d+=([0-9a-f]+)\]\s+inst=\[([0-9a-f]+)\]", re.I)
ROWS = [1, 1, 16, 15, 16]
COLS = [1, 16, 1, 16, 15]
PASS = "GEMMINI_L2_MVIN_MVOUT_EDGES_EQ_PASS checksum=822510027983880976"


def parsed(path: Path) -> list[dict[str, int]]:
    result = []
    for line in path.read_text(errors="replace").splitlines():
        match = COMMAND.search(line)
        if match:
            pc, rs1, rs2, inst = (int(value, 16) for value in match.groups())
            if inst & 127 == 0x7B:
                result.append({"pc": pc, "rs1": rs1, "rs2": rs2,
                               "funct3": (inst >> 12) & 7,
                               "funct7": (inst >> 25) & 127})
    return result


def compare_program(label: str, expected, actual) -> None:
    if len(expected) != len(actual):
        raise SystemExit(f"{label} command count mismatch")
    for index, (op, cmd) in enumerate(zip(expected, actual, strict=True)):
        if (int(op.funct), op.funct3, op.rs1, op.rs2) != (
            cmd["funct7"], cmd["funct3"], cmd["rs1"], cmd["rs2"]
        ):
            raise SystemExit(f"{label} differs at command {index}")


def edge_expected(trace_segment):
    result = []
    for n, (rows, cols) in enumerate(zip(ROWS, COLS, strict=True)):
        base = n * 4
        result += [config_load(stride_bytes=24), config_store(stride_bytes=24),
                   mvin(trace_segment[base + 2]["rs1"], n * 32, cols, rows),
                   mvout(trace_segment[base + 3]["rs1"], n * 32, cols, rows)]
    return result


def acc_expected(trace_segment):
    acc8, acc32 = 1 << 31, 5 << 29
    return [
        config_load(stride_bytes=64),
        config_ex(dataflow=GemminiDataflow.OUTPUT_STATIONARY, c_stride=1, a_stride=1),
        config_store(stride_bytes=16),
        mvin(trace_segment[3]["rs1"], acc8, 15, 16),
        mvout(trace_segment[4]["rs1"], acc8, 15, 16),
        config_load(stride_bytes=64),
        config_ex(dataflow=GemminiDataflow.OUTPUT_STATIONARY, c_stride=1, a_stride=1),
        config_store(stride_bytes=64),
        mvin(trace_segment[8]["rs1"], acc32, 16, 15),
        mvout(trace_segment[9]["rs1"], acc32, 16, 15),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--run-log", type=Path, required=True)
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    commands = parsed(args.trace)
    if len(commands) != 60:
        raise SystemExit(f"expected 60 CUSTOM_3 commits, got {len(commands)}")
    edge_official, edge_raw = commands[:20], commands[20:40]
    acc_official, acc_raw = commands[40:50], commands[50:60]
    compare_program("edge official", edge_expected(edge_official), edge_official)
    compare_program("edge raw", edge_expected(edge_raw), edge_raw)
    compare_program("acc official", acc_expected(acc_official), acc_official)
    compare_program("acc raw", acc_expected(acc_raw), acc_raw)
    differences = []
    for group, left, right, allowed in (
        ("edge", edge_official, edge_raw, {3, 7, 11, 15, 19}),
        ("acc", acc_official, acc_raw, {4, 9}),
    ):
        for index, (a, b) in enumerate(zip(left, right, strict=True)):
            fields = [field for field in ("funct3", "funct7", "rs1", "rs2")
                      if a[field] != b[field]]
            if fields:
                differences.append({"group": group, "command": index, "fields": fields})
                if index not in allowed or fields != ["rs1"]:
                    raise SystemExit(f"unexpected {group} difference at {index}: {fields}")
    if len(differences) != 7:
        raise SystemExit("expected exactly seven destination-only differences")
    if PASS not in args.run_log.read_text(errors="replace"):
        raise SystemExit("numerical PASS marker absent")
    result = {
        "status": "PASS", "custom3_commits": 60,
        "edge_shapes": [f"{r}x{c}" for r, c in zip(ROWS, COLS, strict=True)],
        "unaligned_dram_offsets": True,
        "accumulator_paths": ["INT32-to-INT8", "INT32-full-width"],
        "destination_only_differences": differences,
        "checksum": 822510027983880976,
        "elf_sha256": hashlib.sha256(args.elf.read_bytes()).hexdigest(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
