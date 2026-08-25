#!/usr/bin/env python3
"""Produce a Verdi filelist containing only Verilog/SystemVerilog sources."""
from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    retained = [
        line for line in args.source.read_text(encoding="utf-8").splitlines()
        if line.endswith((".v", ".sv", ".svh")) or line.startswith(("+incdir+", "+define+"))
    ]
    if not retained:
        raise SystemExit("no Verilog/SystemVerilog files were retained")
    args.output.write_text("\n".join(retained) + "\n", encoding="utf-8")
    print(f"retained {len(retained)} RTL entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
