#!/usr/bin/env python3
"""Audit the complete generated operator-primitive RTL catalog.

This script never edits or removes generated files. It is intentionally free of
EDA dependencies so the local agent can run it immediately after Chisel/CIRCT
elaboration and before RTL simulation or synthesis.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def catalog_names(path: Path) -> tuple[str, ...]:
    text = path.read_text()
    return tuple(re.findall(r'^\s*"([a-z0-9_]+)",?\s*$', text, re.MULTILINE))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rtl-dir", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    expected = catalog_names(args.catalog)
    failures: list[str] = []
    modules: dict[str, dict[str, object]] = {}
    if not expected:
        failures.append("empty catalog")

    catalog_txt = args.rtl_dir / "catalog.txt"
    listed = tuple(line.strip() for line in catalog_txt.read_text().splitlines()) if catalog_txt.exists() else ()
    if listed != expected:
        failures.append(f"catalog.txt mismatch: expected={expected}, listed={listed}")

    for name in expected:
        path = args.rtl_dir / f"{name}.sv"
        if not path.exists():
            failures.append(f"missing RTL: {path.name}")
            continue
        payload = path.read_bytes()
        text = payload.decode("utf-8", errors="replace")
        declared = re.findall(r"(?m)^\s*module\s+([A-Za-z_][A-Za-z0-9_$]*)\b", text)
        endmodules = len(re.findall(r"(?m)^\s*endmodule\b", text))
        if len(payload) < 100:
            failures.append(f"too-small RTL: {path.name} ({len(payload)} bytes)")
        if not declared:
            failures.append(f"no module declaration: {path.name}")
        if len(declared) != endmodules:
            failures.append(
                f"module/endmodule mismatch: {path.name} {len(declared)} != {endmodules}"
            )
        if re.search(r"\b(?:TODO|FIXME)\b|\?\?\?", text):
            failures.append(f"incomplete marker: {path.name}")
        modules[name] = {
            "path": str(path),
            "bytes": len(payload),
            "sha256": sha256(path),
            "declared_modules": declared,
        }

    unexpected = sorted(
        path.stem for path in args.rtl_dir.glob("*.sv") if path.stem not in set(expected)
    )
    result = {
        "schema_version": 1,
        "status": "PASS_GENERATED_RTL_CATALOG" if not failures else "FAIL_GENERATED_RTL_CATALOG",
        "expected_count": len(expected),
        "verified_count": len(modules),
        "unexpected_sv_files": unexpected,
        "failures": failures,
        "modules": modules,
    }
    output = args.output or (args.rtl_dir / "rtl_generation_audit.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
