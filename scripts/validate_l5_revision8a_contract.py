#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from heteronpu.revision8_early_commit import sandbox_approval_report

parser = argparse.ArgumentParser()
parser.add_argument("--operations", type=int, default=1_000_000)
parser.add_argument("--output", type=Path, default=ROOT / "reports/execution/l5_revision8a_sandbox_result.json")
args = parser.parse_args()
result = sandbox_approval_report(ROOT, primary_operations=args.operations)
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps(result, indent=2, sort_keys=True))
raise SystemExit(0 if result["status"] == "PASS" else 1)
