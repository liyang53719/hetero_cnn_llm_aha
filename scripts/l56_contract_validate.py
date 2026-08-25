#!/usr/bin/env python3
"""Validate the persistent L5/L6 RTL contract smoke artifacts."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="work/results/open_rtl")
    parser.add_argument("--output", default="reports/l56_contract_validation.json")
    args = parser.parse_args()
    root = Path(args.input)
    required = {
        "shell": root / "tb_shell.log",
        "integrated_v0": root / "tb_integrated_v0.log",
        "shared_l2": root / "tb_shared_l2.log",
    }
    text = {name: path.read_text(encoding="utf-8") if path.exists() else "" for name, path in required.items()}
    transactions = 0
    match = re.search(r"TB_SHARED_L2_PASS transactions=(\d+)", text["shared_l2"])
    if match:
        transactions = int(match.group(1))
    checks = {
        "shell_dispatch_event_smoke": "TB_SHELL_PASS" in text["shell"],
        "integrated_event_wait_signal": "TB_INTEGRATED_V0_PASS" in text["integrated_v0"],
        "shared_l2_random_transactions_gte_10000": transactions >= 10000,
        "required_logs_present": all(path.exists() for path in required.values()),
    }
    report = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "shared_l2_transactions": transactions,
        "artifacts": {name: str(path) for name, path in required.items()},
        "scope": "L5/L6 contract integration; official Gemmini/AHA macro equivalence remains a separate gate",
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
