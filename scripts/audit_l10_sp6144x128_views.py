#!/usr/bin/env python3
"""Audit generated SP SRAM views without copying proprietary files to Git."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    lib = args.root / "l2sp6144x128_tt_typical_0p80v_0p80v_25c.lib"
    verilog = args.root / "l2sp6144x128.v"
    gds2 = args.root / "l2sp6144x128.gds2"
    if not lib.is_file() or not verilog.is_file() or not gds2.is_file():
        raise SystemExit("required Liberty, Verilog, or GDS2 view is missing")
    lib_text = lib.read_text(errors="replace")
    verilog_text = verilog.read_text(errors="replace")
    checks = {
        "lib_nom_voltage_0p8": bool(re.search(r"nom_voltage\s*:\s*0\.8\s*;", lib_text)),
        "lib_nom_temperature_25": bool(re.search(r"nom_temperature\s*:\s*25\s*;", lib_text)),
        "lib_address_width_13": "address_width : 13;" in lib_text,
        "lib_word_width_128": "word_width : 128;" in lib_text,
        "verilog_module": "module l2sp6144x128 " in verilog_text,
        "verilog_address_13": "reg [12:0] a_int;" in verilog_text,
        "verilog_data_128": "reg [127:0] d_int;" in verilog_text,
    }
    if not all(checks.values()):
        raise SystemExit(f"view content mismatch: {checks}")
    lef_files = sorted(args.root.glob("*.lef"))
    result = {
        "status": "PASS" if lef_files else "PARTIAL_BLOCKED_LEF",
        "macro": "l2sp6144x128",
        "words": 6144,
        "bits": 128,
        "mvt": "BASE",
        "corner": "tt_typical_0p80v_0p80v_25c",
        "checks": checks,
        "views": {
            "liberty": {"path": str(lib), "sha256": digest(lib)},
            "verilog": {"path": str(verilog), "sha256": digest(verilog)},
            "gds2": {"path": str(gds2), "sha256": digest(gds2)},
            "lef": [{"path": str(path), "sha256": digest(path)} for path in lef_files],
        },
        "blocker": None if lef_files else "shared ARM bifrun SIGSEGV after opening generated BIF",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
