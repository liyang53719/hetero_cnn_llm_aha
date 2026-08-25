#!/usr/bin/env python3
"""Lightweight structural checks when no SystemVerilog compiler is installed.

This script is deliberately not presented as a replacement for Verilator,
Slang or Surelog.  It catches truncated files, duplicate module names,
unbalanced delimiters and missing integration-shell dependencies.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"//.*", "", text)
    return text


def check_balanced(text: str, path: Path) -> list[str]:
    errors: list[str] = []
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: list[tuple[str, int]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        # Remove string literals to avoid counting delimiters in messages.
        line = re.sub(r'"(?:\\.|[^"\\])*"', '""', line)
        for char in line:
            if char in "([{":
                stack.append((char, line_no))
            elif char in pairs:
                if not stack or stack[-1][0] != pairs[char]:
                    errors.append(f"{path}:{line_no}: unmatched {char}")
                else:
                    stack.pop()
    for char, line_no in stack:
        errors.append(f"{path}:{line_no}: unclosed {char}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default="rtl")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    root = Path(args.root)
    files = sorted(root.rglob("*.sv"))
    errors: list[str] = []
    modules: dict[str, str] = {}
    per_file: list[dict[str, object]] = []
    for path in files:
        raw = path.read_text(encoding="utf-8")
        text = strip_comments(raw)
        declarations = re.findall(r"\bmodule\s+([A-Za-z_][A-Za-z0-9_$]*)", text)
        endmodules = len(re.findall(r"\bendmodule\b", text))
        if len(declarations) != endmodules:
            errors.append(
                f"{path}: module/endmodule mismatch {len(declarations)} != {endmodules}"
            )
        for module in declarations:
            if module in modules:
                errors.append(f"duplicate module {module}: {modules[module]} and {path}")
            modules[module] = str(path)
        errors.extend(check_balanced(text, path))
        if "<<<<<<<" in raw or ">>>>>>>" in raw:
            errors.append(f"{path}: unresolved merge marker")
        per_file.append(
            {
                "path": str(path),
                "lines": len(raw.splitlines()),
                "modules": declarations,
            }
        )

    required = {
        "rv_fifo",
        "matrix_engine_int8_tile",
        "cgra_sfu_vector",
        "kv_cache_engine",
        "command_dispatch",
        "hetero_npu_shell",
        "command_event_scoreboard",
        "engine_contract_adapter",
        "hetero_npu_integrated_v0",
        "hetero_npu_numerical_integration_v0",
        "gemmini_rocc_command_adapter",
        "gemmini_rocc_program_adapter",
        "aha_garnet_axi_config_loader",
        "aha_garnet_proc_packet_writer",
        "aha_garnet_microsequencer",
        "hetero_npu_gemmini_rocc_integration_v0",
        "shared_l2_fabric",
    }
    missing = sorted(required.difference(modules))
    if missing:
        errors.append(f"missing required modules: {missing}")

    report = {
        "status": "PASS" if not errors else "FAIL",
        "note": "structural check only; run Verilator/Slang/Surelog locally",
        "file_count": len(files),
        "module_count": len(modules),
        "modules": modules,
        "files": per_file,
        "errors": errors,
    }
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
