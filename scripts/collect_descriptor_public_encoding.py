#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text())


def sha(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


encoding = load("config/descriptor_public_encoding.json")
image = load("reports/execution/qwen2_descriptor_image_result.json")
rtl_log = (ROOT / "work/results/descriptor_public_encoding_rtl/tb.log").read_text()
checks = {
    "user_approved": encoding["approval_status"] == "APPROVED" and
                     encoding["approval_source"] == "user_explicit_2026-09-01",
    "dtype_codes": encoding["tensor_base"]["dtype_codes"] == {
        "INVALID": 0, "INT8": 1, "INT32": 4, "BF16": 5, "FP16": 6, "FP32": 7,
    },
    "formal_image": image["status"] == "PASS_PACKED_DESCRIPTOR_IMAGE" and
                    image["encoding_approved"] and not image["test_only_override"],
    "records": image["commands"] == 588 and image["chains"] == 1764 and
               image["records"] == 6188,
    "rtl_decode": "DESCRIPTOR_PUBLIC_RECORD_DECODE_PASS cases=12" in rtl_log,
}
if not all(checks.values()):
    raise SystemExit(f"descriptor public encoding: {checks}")
result = {
    "schema_version": 1,
    "status": "PASS_APPROVED_DESCRIPTOR_PUBLIC_ENCODING_AND_FORMAL_IMAGE",
    "approval_source": encoding["approval_source"], "checks": checks,
    "commands": 588, "chains": 1764, "records": 6188,
    "packed_records_sha256": image["packed_records_sha256"],
    "provenance": {
        "encoding_sha256": sha("config/descriptor_public_encoding.json"),
        "formal_image_report_sha256": sha("reports/execution/qwen2_descriptor_image_result.json"),
        "software_contract_sha256": sha("src/heteronpu/descriptor_chain.py"),
        "rtl_decoder_sha256": sha("rtl/integration/descriptor_public_record_decode.sv"),
        "rtl_log_sha256": sha("work/results/descriptor_public_encoding_rtl/tb.log"),
    },
    "non_claim": "formal descriptor packing does not yet execute descriptor-backed payload RTL",
}
output = ROOT / "reports/execution/descriptor_public_encoding_result.json"
output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps({"status": result["status"], "records": result["records"],
                  "sha256": result["packed_records_sha256"]}, sort_keys=True))
