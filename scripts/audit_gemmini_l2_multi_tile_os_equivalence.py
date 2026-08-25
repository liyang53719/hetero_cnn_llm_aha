#!/usr/bin/env python3
"""Audit official and project-lowered multi-tile OS Rocket commits."""
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
    Int8OsTilesDescriptor,
    lower_int8_os_tiles,
)


COMMAND = re.compile(
    r"pc=\[([0-9a-f]+)\].*"
    r"R\[r\s*\d+=([0-9a-f]+)\]\s+"
    r"R\[r\s*\d+=([0-9a-f]+)\]\s+inst=\[([0-9a-f]+)\]",
    re.IGNORECASE,
)
PASS_MARKER = "GEMMINI_L2_MULTI_TILE_OS_EQ_PASS checksum=14853676686976657775"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--run-log", type=Path, required=True)
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    commands: list[dict[str, int]] = []
    for line in args.trace.read_text(errors="replace").splitlines():
        match = COMMAND.search(line)
        if match is None:
            continue
        pc, rs1, rs2, inst = (int(value, 16) for value in match.groups())
        if inst & 0x7F == 0x7B:
            commands.append({
                "pc": pc, "rs1": rs1, "rs2": rs2, "inst": inst,
                "funct3": (inst >> 12) & 7, "funct7": (inst >> 25) & 127,
            })
    if len(commands) != 72:
        raise SystemExit(f"expected 72 CUSTOM_3 commits, got {len(commands)}")
    official, lowered = commands[:36], commands[36:]

    differences: list[dict[str, object]] = []
    for index, (left, right) in enumerate(zip(official, lowered, strict=True)):
        for field in ("funct3", "funct7", "rs1", "rs2"):
            if left[field] != right[field]:
                differences.append({
                    "command": index, "field": field,
                    "official": f"0x{left[field]:016x}",
                    "lowered": f"0x{right[field]:016x}",
                })
    if [(d["command"], d["field"]) for d in differences] != [
        (32, "rs1"), (33, "rs1"), (34, "rs1"), (35, "rs1")
    ]:
        raise SystemExit(f"unexpected official/lowered differences: {differences}")

    descriptor = Int8OsTilesDescriptor(
        a_addr=lowered[14]["rs1"], b_addr=lowered[11]["rs1"],
        d_addr=lowered[6]["rs1"], c_addr=lowered[32]["rs1"],
        i_tiles=2, j_tiles=2, k_tiles=2,
        pad_i=15, pad_j=14, pad_k=13,
        a_row_stride=19, b_row_stride=18,
        d_row_stride=18, c_row_stride=18,
    )
    python_ops = lower_int8_os_tiles(descriptor)
    if len(python_ops) != len(lowered):
        raise SystemExit("Python lowerer command count differs from Rocket trace")
    for index, (expected, actual) in enumerate(zip(python_ops, lowered, strict=True)):
        fields = (int(expected.funct), expected.funct3, expected.rs1, expected.rs2)
        observed = (actual["funct7"], actual["funct3"], actual["rs1"], actual["rs2"])
        if fields != observed:
            raise SystemExit(f"Python lowerer differs from Rocket command {index}")
    if PASS_MARKER not in args.run_log.read_text(errors="replace"):
        raise SystemExit("retained-RocketTile numerical PASS marker is absent")

    result = {
        "status": "PASS",
        "scope": "17x18x19 INT8 OS, 2x2x2 tiles, same retained RocketTile run",
        "custom3_commands_per_path": 36,
        "python_lowerer_matches_all_raw_commands": True,
        "expected_mvout_destination_differences": differences,
        "checksum": 14853676686976657775,
        "elf_sha256": hashlib.sha256(args.elf.read_bytes()).hexdigest(),
        "official": official,
        "lowered": lowered,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ("official", "lowered")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
