#!/usr/bin/env python3
"""Extract the generated Gemmini top-level port contract without modifying it."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


PORT_RE = re.compile(r"^\s*(input|output)\s+(?:(\[[^]]+\])\s+)?([A-Za-z0-9_]+)")


def family(name: str) -> str:
    if name.startswith("io_cmd_"):
        return "rocc_cmd"
    if name.startswith("io_resp_"):
        return "rocc_resp"
    if name.startswith("io_ptw_"):
        return "ptw"
    if name.startswith("auto_spad_id_out_"):
        return "tilelink_spad"
    if name in {"clock", "reset", "io_busy", "io_interrupt"}:
        return "lifecycle"
    return "other"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("sv", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    lines = args.sv.read_text(errors="strict").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("module Gemmini("))
    ports = []
    for line in lines[start + 1 :]:
        if line.strip() == ");":
            break
        match = PORT_RE.match(line)
        if match:
            direction, width, name = match.groups()
            ports.append({"name": name, "direction": direction, "width": width or "1", "family": family(name)})
    counts: dict[str, int] = {}
    for port in ports:
        counts[port["family"]] = counts.get(port["family"], 0) + 1
    manifest = {"module": "Gemmini", "source": str(args.sv), "port_count": len(ports), "family_counts": counts, "ports": ports}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"port_count": len(ports), "family_counts": counts}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
