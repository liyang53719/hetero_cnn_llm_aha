#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from heteronpu.l10_early_ppa import analyze_ppa, default_component_evidence
from heteronpu.l5_evidence_boundary import audit_l5_boundary
from heteronpu.qwen2_payload_closure import plan_report


def load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports" / "execution" / "sandbox_v78_result.json",
    )
    parser.add_argument(
        "--payload-plan",
        type=Path,
        default=ROOT / "reports" / "execution" / "qwen2_payload_closure_plan.json",
    )
    args = parser.parse_args()

    full_trace = load(ROOT / "reports/execution/l5_qwen2_full_model_trace_result.json")
    cross = load(ROOT / "reports/execution/l5_qwen2_four_layer_cross_replay_result.json")
    final = load(ROOT / "reports/final_validation.json")
    payload_plan = plan_report()

    result = {
        "schema_version": 1,
        "status": "PASS_SANDBOX_V7_8",
        "evidence_class": "sandbox_control_PPA_and_closure_planning_not_local_E4_or_post_route",
        "l5_boundary": audit_l5_boundary(full_trace, cross, final),
        "l10_early_ppa": analyze_ppa(default_component_evidence()),
        "qwen2_payload_closure": payload_plan,
    }
    if result["l5_boundary"]["status"] != "PASS_BOUNDARY_NORMALIZED":
        result["status"] = "FAIL_SANDBOX_V7_8"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.payload_plan.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.payload_plan.write_text(json.dumps(payload_plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS_SANDBOX_V7_8" else 1


if __name__ == "__main__":
    raise SystemExit(main())
