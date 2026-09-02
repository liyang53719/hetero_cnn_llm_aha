#!/usr/bin/env python3
"""Classify the existing 588-command and two-command RTL tests."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from heteronpu.rtl_transport_evidence import classify_existing_rtl_evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports/execution/L9_4_EXISTING_RTL_EVIDENCE.json",
    )
    args = parser.parse_args()
    root = args.root
    report = classify_existing_rtl_evidence(
        submission_script=(root / "scripts/run_qwen2_real_command_submission.sh").read_text(encoding="utf-8"),
        submission_tb=(root / "tb/tb_qwen2_real_command_submission.sv").read_text(encoding="utf-8"),
        payload_script=(root / "scripts/run_qwen2_real_payload_endpoint.sh").read_text(encoding="utf-8"),
        payload_tb=(root / "tb/tb_qwen2_real_payload_endpoint.sv").read_text(encoding="utf-8"),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0 if report["status"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
