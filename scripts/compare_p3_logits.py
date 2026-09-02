#!/usr/bin/env python3
"""Compare complete Qwen2 logit files and emit an atomic evidence report."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from heteronpu.logits_parity import LogitThresholds, compare_files


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--actual", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-count", type=int, default=151_936)
    parser.add_argument("--topk", type=int, default=10)
    parser.add_argument("--required-topk-overlap", type=int, default=10)
    parser.add_argument("--relative-l2-max", type=float, default=1.0e-2)
    parser.add_argument("--cosine-min", type=float, default=0.9999)
    parser.add_argument(
        "--allow-nonfinite",
        action="store_true",
        help="diagnostic only; hardware acceptance should keep the default strict finite check",
    )
    args = parser.parse_args()

    thresholds = LogitThresholds(
        topk=args.topk,
        required_topk_overlap=args.required_topk_overlap,
        relative_l2_max=args.relative_l2_max,
        cosine_min=args.cosine_min,
        expected_count=args.expected_count,
        require_all_finite=not args.allow_nonfinite,
    )
    report = compare_files(args.actual, args.reference, thresholds)
    report["artifact"] = "Qwen2_q1024_full_logits"
    report["execution_claim"] = "numerical_parity_only"

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0 if report["status"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
