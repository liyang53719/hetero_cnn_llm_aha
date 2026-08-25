#!/usr/bin/env python3
"""Audit official versus raw multi-tile LOOP_WS in retained RocketTile."""
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
EXPECTED_FUNCTS = [0, 0, 0, 0, 0, 9, 10, 11, 12, 13, 8]
PASS_MARKER = "GEMMINI_L2_LOOP_WS_EQ_PASS checksum=14853676686976657775"


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
    if [cmd["funct7"] for cmd in official] != EXPECTED_FUNCTS:
        raise SystemExit("official CONFIG plus LOOP_WS funct sequence changed")
    if [cmd["funct7"] for cmd in lowered] != EXPECTED_FUNCTS:
        raise SystemExit("raw CONFIG plus LOOP_WS funct sequence changed")

    differences: list[dict[str, object]] = []
    for index, (left, right) in enumerate(zip(official, lowered, strict=True)):
        for field in ("funct3", "funct7", "rs1", "rs2"):
            if left[field] != right[field]:
                differences.append({
                    "command": index,
                    "field": field,
                    "official": f"0x{left[field]:016x}",
                    "lowered": f"0x{right[field]:016x}",
                })
    if len(differences) != 1 or differences[0]["command"] != 7 or differences[0]["field"] != "rs2":
        raise SystemExit(f"unexpected command differences: {differences}")

    # Bounds are 2x2x2 tiles with 15/14/13 tail padding; strides are element
    # counts 19/18 and 18/18. The final loop flags request bias accumulation.
    expected_payloads = {
        5: (0x0000000D000E000F, 0x0000000200020002),
        8: (19, 18),
        9: (18, 18),
        10: (1, 0),
    }
    for index, expected in expected_payloads.items():
        actual = (lowered[index]["rs1"], lowered[index]["rs2"])
        if actual != expected:
            raise SystemExit(f"command {index} payload {actual} != {expected}")
    if PASS_MARKER not in args.run_log.read_text(errors="replace"):
        raise SystemExit("retained-RocketTile numerical PASS marker is absent")

    import hashlib
    result = {
        "status": "PASS",
        "scope": "17x18x19 INT8 WS, 2x2x2 tiles, same retained RocketTile run",
        "custom3_commands_per_path": 11,
        "matching_payload_fields": "all except expected output DRAM address",
        "expected_difference": differences[0],
        "checksum": 14853676686976657775,
        "elf_sha256": hashlib.sha256(args.elf.read_bytes()).hexdigest(),
        "official": official,
        "lowered": lowered,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
