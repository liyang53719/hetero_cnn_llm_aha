#!/usr/bin/env python3
"""Audit official-macro versus raw-lowered Gemmini commands in one Rocket run."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


COMMAND = re.compile(
    r"pc=\[([0-9a-f]+)\].*"
    r"R\[r\s*\d+=([0-9a-f]+)\]\s+"
    r"R\[r\s*\d+=([0-9a-f]+)\]\s+inst=\[([0-9a-f]+)\]",
    re.IGNORECASE,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--run-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    commands: list[dict[str, int]] = []
    for line in args.trace.read_text(errors="replace").splitlines():
        match = COMMAND.search(line)
        if match is None:
            continue
        pc, rs1, rs2, inst = (int(value, 16) for value in match.groups())
        if inst & 0x7F != 0x7B:
            continue
        commands.append({
            "pc": pc,
            "rs1": rs1,
            "rs2": rs2,
            "inst": inst,
            "funct3": (inst >> 12) & 0x7,
            "funct7": (inst >> 25) & 0x7F,
        })

    if len(commands) != 22:
        raise SystemExit(f"expected 22 CUSTOM_3 commits, got {len(commands)}")
    official, lowered = commands[:11], commands[11:]
    for index, (left, right) in enumerate(zip(official, lowered, strict=True)):
        for field in ("funct3", "funct7", "rs2"):
            if left[field] != right[field]:
                raise SystemExit(f"command {index} {field} mismatch")
        if index < 10 and left["rs1"] != right["rs1"]:
            raise SystemExit(f"command {index} rs1 mismatch")
    if lowered[-1]["rs1"] - official[-1]["rs1"] != 0x10:
        raise SystemExit("final mvout destinations are not the adjacent C_macro/C_raw arrays")

    run_log = args.run_log.read_text(errors="replace")
    marker = "GEMMINI_L2_ROCC_EQ_PASS checksum=6954858531263039530"
    if marker not in run_log:
        raise SystemExit("retained-RocketTile numerical PASS marker is absent")

    result = {
        "status": "PASS",
        "scope": "same retained RocketTile/GemminiRocketConfig run",
        "custom3_commands_per_path": 11,
        "matching_payload_commands": 10,
        "mvout_only_difference": {
            "official_destination": f"0x{official[-1]['rs1']:016x}",
            "lowered_destination": f"0x{lowered[-1]['rs1']:016x}",
            "shared_rs2": f"0x{official[-1]['rs2']:016x}",
        },
        "checksum": 6954858531263039530,
        "official": official,
        "lowered": lowered,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
