#!/usr/bin/env python3
"""Audit the frozen 21-command Qwen2 layer-0 manifest contract."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from heteronpu.l9_transport_contract import audit_manifest_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "reports/execution/llama_cpp_qwen2_graph_lowering_manifest.jsonl",
    )
    parser.add_argument("--layer", type=int, default=0)
    parser.add_argument("--expected-total-commands", type=int, default=588)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports/execution/L9_4_LAYER0_MANIFEST_CONTRACT.json",
    )
    args = parser.parse_args()

    report = audit_manifest_file(
        args.manifest,
        layer=args.layer,
        expected_total_commands=args.expected_total_commands,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0 if report["status"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
