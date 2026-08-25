#!/usr/bin/env python3
"""Extract a generated SystemVerilog module boundary into a stable JSON record.

Generated macros remain outside the source tree.  The manifest is the reviewable
contract used by project-owned wrappers and intentionally contains no copied RTL.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


MODULE_RE = re.compile(r"^\s*module\s+([A-Za-z_][A-Za-z0-9_$]*)\s*\(")
PORT_RE = re.compile(
    r"^\s*(input|output|inout)\s+"
    r"(?:(?:wire|logic|reg)\s+)?(?:signed\s+)?"
    r"(\[[^]]+\])?\s*([A-Za-z_][A-Za-z0-9_$]*)"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("sv", type=Path)
    parser.add_argument("module")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    raw = args.sv.read_bytes()
    lines = raw.decode("utf-8", errors="strict").splitlines()
    start = next(
        (index for index, line in enumerate(lines)
         if (match := MODULE_RE.match(line)) and match.group(1) == args.module),
        None,
    )
    if start is None:
        raise SystemExit(f"module {args.module!r} was not found in {args.sv}")

    ports: list[dict[str, str]] = []
    for line in lines[start + 1:]:
        if line.strip() == ");":
            break
        match = PORT_RE.match(line)
        if match:
            direction, width, name = match.groups()
            ports.append({"name": name, "direction": direction, "width": width or "1"})
    else:
        raise SystemExit(f"unterminated declaration for module {args.module!r}")

    if not ports:
        raise SystemExit(f"module {args.module!r} has no parseable ANSI ports")

    manifest = {
        "schema_version": 1,
        "module": args.module,
        "source": str(args.sv),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "port_count": len(ports),
        "ports": ports,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"module": args.module, "port_count": len(ports),
                      "source_sha256": manifest["source_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
