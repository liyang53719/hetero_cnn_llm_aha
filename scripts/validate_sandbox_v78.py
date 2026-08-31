#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--result",
        type=Path,
        default=ROOT / "reports/execution/sandbox_v78_result.json",
    )
    args = parser.parse_args()
    result = json.loads(args.result.read_text(encoding="utf-8"))
    assert result["status"] == "PASS_SANDBOX_V7_8"
    boundary = result["l5_boundary"]
    assert boundary["status"] == "PASS_BOUNDARY_NORMALIZED"
    assert boundary["subgates"]["L5.6d_full_28_layer_payload_numerical_RTL"] == "OPEN"
    ppa = result["l10_early_ppa"]
    assert ppa["status"] == "PASS_EARLY_PPA_PREFLIGHT_WITH_CRITICAL_MARGIN_RISK"
    assert ppa["minimum_margin"]["margin_ps"] < 0.1
    assert len(ppa["critical_sub_1ps"]) >= 5
    assert ppa["route_scenarios"]["five_ps"]["failing_count"] >= 1
    closure = result["qwen2_payload_closure"]
    assert closure["status"] == "PASS_FULL_PAYLOAD_CLOSURE_PLAN"
    assert closure["checkpoint_count"] == 168
    assert closure["continuity_groups"] == list(range(7))
    print(json.dumps({
        "schema_version": 1,
        "status": "PASS_VALIDATE_SANDBOX_V7_8",
        "minimum_margin_ps": ppa["minimum_margin"]["margin_ps"],
        "critical_sub_1ps": len(ppa["critical_sub_1ps"]),
        "payload_checkpoints": closure["checkpoint_count"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
