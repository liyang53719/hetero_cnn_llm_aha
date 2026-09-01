#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


protocol_log = (ROOT / "work/results/qwen2_descriptor_image_protocol/tb.log").read_text()
macro_log = (ROOT / "work/results/qwen2_descriptor_image_macro/tb.log").read_text()
l3 = json.loads((ROOT / "reports/execution/l3_closeout_result.json").read_text())
protocol = re.search(r"QWEN2_DESCRIPTOR_IMAGE_PROTOCOL_PASS records=(\d+) beats=(\d+) "
                     r"descriptor_bytes=(\d+) writes=(\d+) reads=(\d+) lane_coverage=(\d+) "
                     r"random_backpressure=1 mismatches=0", protocol_log)
macro = re.search(r"QWEN2_DESCRIPTOR_IMAGE_MACRO_SAMPLE_PASS formal_records=(\d+) sampled_beats=(\d+) "
                  r"descriptor_bytes=(\d+) physical_writes=(\d+) physical_reads=(\d+) "
                  r"descriptor_fetches=(\d+) bank_groups=(\d+) descriptor_lanes=(\d+) "
                  r"random_backpressure=1 errors=0", macro_log)
if not protocol or not macro:
    raise SystemExit("descriptor image fabric PASS receipt missing")
p = tuple(map(int, protocol.groups()))
m = tuple(map(int, macro.groups()))
checks = {
    "full_protocol_image": p == (6188, 1547, 164544, 1547, 6188, 4),
    "real_macro_sample": m == (6188, 4, 164544, 4, 8, 4, 4, 4),
    "l3_real_macro_100k": l3["status"] == "PASS" and
                          l3["real_macro_support"]["shared_l2_16_macro_separate_100k_gate"] and
                          l3["real_macro_support"]["shared_l2_macro_errors"] == 0,
}
if not all(checks.values()):
    raise SystemExit(f"descriptor image fabric: {checks}")
result = {
    "schema_version": 1,
    "status": "PASS_FORMAL_DESCRIPTOR_IMAGE_PRODUCTION_PORT",
    "checks": checks, "records": 6188, "beats": 1547,
    "descriptor_bytes": 164544, "shared_l2_capacity_bytes": 1572864,
    "full_protocol": {"records": 6188, "writes": 1547, "reads": 6188,
                      "lane_coverage": 4, "mismatches": 0, "random_backpressure": True},
    "real_macro_sample": {"physical_beats": 4, "bank_groups": 4,
                          "descriptor_lanes": 4, "macro_errors": 0},
    "supporting_macro_gate": {"transactions": 100000, "source": "L3 retained gate"},
    "provenance": {
        "protocol_log_sha256": sha("work/results/qwen2_descriptor_image_protocol/tb.log"),
        "macro_log_sha256": sha("work/results/qwen2_descriptor_image_macro/tb.log"),
        "formal_image_sha256": json.loads((ROOT / "reports/execution/qwen2_descriptor_image_result.json").read_text())["packed_records_sha256"],
        "l3_closeout_sha256": sha("reports/execution/l3_closeout_result.json"),
    },
    "non_claims": [
        "the real ARM macro test samples four physical beats; full image coverage uses the production protocol fabric",
        "descriptor image fetch does not yet move Qwen payload tensor data",
    ],
}
output = ROOT / "reports/execution/qwen2_descriptor_image_fabric_result.json"
output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps({"status": result["status"], "records": 6188,
                  "descriptor_bytes": 164544}, sort_keys=True))
