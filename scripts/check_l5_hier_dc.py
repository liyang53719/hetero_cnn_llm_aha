#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def fields(path: Path) -> dict[str, str]:
    return dict(
        line.strip().split("=", 1)
        for line in path.read_text().splitlines()
        if "=" in line
    )


p = argparse.ArgumentParser()
p.add_argument("phase", choices=("leaf", "lane", "array", "context"))
p.add_argument("result_dir", type=Path)
p.add_argument("--json-out", type=Path)
args = p.parse_args()

status_path = args.result_dir / "status.txt"
log_path = args.result_dir / "dc.log"
if not status_path.is_file() or not log_path.is_file():
    raise SystemExit("missing status or log")
s = fields(status_path)
log = log_path.read_text(errors="replace")

errors: list[str] = []
if s.get("LINK_STATUS") != "1":
    errors.append("link")
if int(s.get("UNMAPPED_CELLS", "-1")) != 0:
    errors.append("unmapped")
if int(s.get("UNRESOLVED_REFERENCES", "-1")) != 0:
    errors.append("unresolved")
try:
    wns = float(s["WORST_SLACK_NS"])
except (KeyError, ValueError):
    wns = float("-inf")
    errors.append("wns_missing")
if wns < 0:
    errors.append("timing")

bad_link = re.findall(
    r"(?:Unable to resolve|Can't find design|Could not resolve|unresolved reference)",
    log,
    flags=re.IGNORECASE,
)
if bad_link:
    errors.append("unresolved_log")

if args.phase == "lane":
    for stage in (
        "HeteroBF16FmaPre",
        "HeteroBF16FmaMul",
        "HeteroBF16FmaPost",
        "HeteroBF16FmaRound",
    ):
        if int(s.get(f"DESIGN_VARIANTS_{stage}", "-1")) != 1:
            errors.append(f"variants_{stage}")
        if int(s.get(f"INSTANCES_{stage}", "-1")) != 1:
            errors.append(f"instances_{stage}")
if args.phase == "array":
    if re.search(r"Uniquified 512 instances of design 'bf16_fma_pipeline_lane", log):
        errors.append("lane_uniquified_512")
    if int(s.get("DESIGN_VARIANTS_bf16_fma_pipeline_lane", "-1")) != 1:
        errors.append("variants_lane")
    if int(s.get("INSTANCES_bf16_fma_pipeline_lane", "-1")) != 512:
        errors.append("instances_lane")
    if s.get("COMPILE_COMMANDS") != "0":
        errors.append("top_compile_present")
    for ref in (
        "bf16_outer_product_array_control512",
        "bf16_outer_product_array_glue512",
    ):
        if int(s.get(f"DESIGN_VARIANTS_{ref}", "-1")) != 1:
            errors.append(f"variants_{ref}")
        if int(s.get(f"INSTANCES_{ref}", "-1")) != 1:
            errors.append(f"instances_{ref}")
if args.phase == "context":
    if s.get("COMPILE_COMMANDS") != "0":
        errors.append("top_compile_present")
    if int(s.get("DESIGN_VARIANTS_bf16_context_fma_pipeline_lane4", "-1")) != 1:
        errors.append("variants_context_lane")
    if int(s.get("INSTANCES_bf16_context_fma_pipeline_lane4", "-1")) != 512:
        errors.append("instances_context_lane")
    for ref in (
        "bf16_context_scheduler4",
        "bf16_context_control_broadcast512",
        "bf16_outer_product_array_control512",
        "bf16_outer_product_array_glue512",
    ):
        if int(s.get(f"DESIGN_VARIANTS_{ref}", "-1")) != 1:
            errors.append(f"variants_{ref}")
        if int(s.get(f"INSTANCES_{ref}", "-1")) != 1:
            errors.append(f"instances_{ref}")

result = {
    "schema_version": 1,
    "phase": args.phase,
    "status": "PASS" if not errors else "FAIL",
    "wns_ns": None if wns == float("-inf") else wns,
    "unmapped": int(s.get("UNMAPPED_CELLS", "-1")),
    "unresolved": int(s.get("UNRESOLVED_REFERENCES", "-1")),
    "errors": errors,
}
if args.json_out:
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps(result, indent=2, sort_keys=True))
raise SystemExit(0 if not errors else (10 if errors == ["timing"] else 1))
