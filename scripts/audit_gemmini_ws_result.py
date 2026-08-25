#!/usr/bin/env python3
"""Classify the canonical Gemmini WS revalidation without running a simulator."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("result_dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    directory = args.result_dir
    runner_result = directory / "result.json"
    transcript = directory / "verilator_matmul_ws.log"
    report: dict[str, object] = {"result_dir": str(directory), "status": "INCOMPLETE"}
    if runner_result.is_file():
        report["runner_result"] = json.loads(runner_result.read_text())
    if transcript.is_file():
        text = transcript.read_text(errors="replace")
        if "*** FAILED ***" in text and "timeout" in text:
            report["status"] = "TIMEOUT"
            report["terminal"] = "TestDriver timeout"
        elif "$finish" in text and "*** FAILED ***" not in text:
            report["status"] = "PASS"
            report["terminal"] = "$finish"
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    print(encoded, end="")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
