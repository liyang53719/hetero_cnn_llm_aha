#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    macro = "ctsp4096x128wm"
    lib = args.root / f"{macro}_tt_typical_0p80v_0p80v_25c.lib"
    verilog = args.root / f"{macro}.v"
    gds2 = args.root / f"{macro}.gds2"
    for path in (lib, verilog, gds2):
        if not path.is_file():
            raise SystemExit(f"missing required view: {path}")
    lib_text = lib.read_text(errors="replace")
    verilog_text = verilog.read_text(errors="replace")
    checks = {
        "voltage_0p8": bool(re.search(r"nom_voltage\s*:\s*0\.8\s*;", lib_text)),
        "temperature_25": bool(re.search(r"nom_temperature\s*:\s*25\s*;", lib_text)),
        "address_width_12": "address_width : 12;" in lib_text,
        "word_width_128": "word_width : 128;" in lib_text,
        "module": f"module {macro} " in verilog_text,
        "write_mask_128": "input [127:0] wen;" in verilog_text,
    }
    if not all(checks.values()):
        raise SystemExit(f"view content mismatch: {checks}")
    lef = sorted(args.root.glob("*.lef"))
    result = {
        "status": "PASS" if lef else "PARTIAL_BLOCKED_LEF",
        "macro": macro, "words": 4096, "bits": 128,
        "mvt": "BASE", "write_mask": "bit",
        "corner": "tt_typical_0p80v_0p80v_25c", "checks": checks,
        "views": {
            "liberty": {"path": str(lib), "sha256": sha256(lib)},
            "verilog": {"path": str(verilog), "sha256": sha256(verilog)},
            "gds2": {"path": str(gds2), "sha256": sha256(gds2)},
            "lef": [{"path": str(path), "sha256": sha256(path)} for path in lef],
        },
        "blocker": None if lef else "shared ARM bifrun SIGSEGV in ReplaceDummyPinsWithObs",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
