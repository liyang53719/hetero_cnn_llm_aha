#!/usr/bin/env python3
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
log_path = Path("work/results/qwen2_kv_append_descriptor_v3_context/tb.log")
layout_path = Path("work/results/qwen2_kv_append_descriptor_v3_context/layout.log")
text = (ROOT / log_path).read_text()
match = re.search(r"QWEN2_KV_APPEND_DESCRIPTOR_V3_CONTEXT_PASS valid_fetches=(\d+) malformed_preissue=(\d+) table_flag_reject=(\d+) table_base=([0-9a-f]+) data_base=([0-9a-f]+) tokens=(\d+) pages=(\d+) page_bytes=(\d+) random_backpressure=(\d+)", text)
expected = (13, 1, 1, "0000000500000000", "0000000500008000", 1024, 64, 16384, 1)
assert match
observed = (int(match[1]), int(match[2]), int(match[3]), match[4], match[5], int(match[6]), int(match[7]), int(match[8]), int(match[9]))
assert observed == expected
assert "QWEN2_KV_DDR_LAYOUT_PASS layers=28" in (ROOT / layout_path).read_text()

def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()

result = {
    "schema_version": 1,
    "status": "PASS_KV_APPEND_DESCRIPTOR_V3_CONTEXT",
    "evidence_class": "formal_6188_record_image_full_chain_RTL_context",
    "command": "l0.kv_append",
    "descriptor_fetches": 13,
    "tokens": 1024,
    "logical_pages": 64,
    "page_tokens": 16,
    "page_bytes": 16384,
    "table_base": "0x0000000500000000",
    "data_base": "0x0000000500008000",
    "checks": {
        "K_chain_complete": True,
        "V_chain_complete": True,
        "metadata_0x32_to_0x35_complete": True,
        "referenced_table_tensor_chain_complete": True,
        "malformed_command_rejected_preissue": True,
        "reserved_table_flags_rejected": True,
        "random_backpressure": True,
        "all_28_layer_layouts_match_planner": True,
    },
    "provenance": {
        "log_sha256": sha(log_path),
        "layout_log_sha256": sha(layout_path),
        "rtl_sha256": sha("rtl/kv/qwen2_kv_append_descriptor_v3_context.sv"),
        "layout_contract_sha256": sha("config/qwen2_kv_ddr_layout.json"),
    },
    "open": ["DDR_PTE_writes", "64_page_KV_payload_copy", "same_run_after_q1024_QKV", "gather"],
    "non_claims": [
        "descriptor context does not move KV payload",
        "legacy 512 KiB staging adapter is not production DDR KV",
        "token0 first-nine chain still lacks q1024 KV append payload",
    ],
}
(ROOT / "reports/execution/qwen2_kv_append_descriptor_v3_context_result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps({"status": result["status"], "fetches": 13, "pages": 64}, sort_keys=True))
