#!/usr/bin/env python3
"""Convert locked AHA macro headers from SVH syntax to C preprocessor syntax."""
from __future__ import annotations

import argparse
import re
from pathlib import Path


DEFINE = re.compile(r"^`define\s+([A-Za-z_][A-Za-z0-9_]*)\s+(.+)$")
LOCALPARAM = re.compile(r"^localparam\s+(?:int|bit|logic(?:\s*\[[^]]+\])?)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+);$")


def convert(src: Path, dst: Path) -> None:
    lines = [f"/* Generated from {src.name}; do not edit. */", "#pragma once"]
    for raw in src.read_text(encoding="utf-8").splitlines():
        match = DEFINE.match(raw) or LOCALPARAM.match(raw)
        if match is None:
            continue
        name, value = match.groups()
        value = value.strip().replace("'h", "0x").replace("'d", "")
        value = value.replace("true", "1").replace("false", "0")
        lines.append(f"#define {name} ({value})")
    dst.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    mapping = {
        "global_buffer/header/global_buffer_param.svh": "global_buffer_param.h",
        "global_buffer/header/glb.svh": "glb.h",
        "global_controller/header/glc.svh": "glc.h",
        "matrix_unit/header/matrix_unit_param.svh": "matrix_unit_param.h",
        "matrix_unit/header/matrix_unit_regspace.svh": "matrix_unit_regspace.h",
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for relative, output in mapping.items():
        convert(args.source_root / relative, args.output_dir / output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
