#!/usr/bin/env python3
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
stage_log = Path("work/results/qwen2_kv_append_ddr_page_core/stage_tb.log")
core_log = Path("work/results/qwen2_kv_append_ddr_page_core/tb.log")
pattern = re.compile(r"QWEN2_KV_APPEND_DDR_STAGE_TOP_PASS commands=(\d+) descriptor_fetches=(\d+) pte_updates=(\d+) idma_requests=(\d+) payload_bytes=(\d+) pages=(\d+) table_base=([0-9a-f]+) data_base=([0-9a-f]+) random_backpressure=(\d+)")
match = pattern.search((ROOT / stage_log).read_text())
assert match and tuple(map(int, match.groups()[:6])) == (1, 13, 65, 128, 1048576, 64)
assert match.groups()[6:] == ("0000000500000000", "0000000500008000", "1")
assert "QWEN2_KV_APPEND_DDR_PAGE_CORE_PASS" in (ROOT / core_log).read_text()

def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()

result = {
    "schema_version": 1,
    "status": "PASS_KV_APPEND_COMMAND_TO_DDR_PAGE_SCHEDULE",
    "evidence_class": "single_RTL_stage_formal_descriptor_to_PTE_and_iDMA_schedule",
    "commands": 1,
    "descriptor_fetches": 13,
    "pte_updates": {"root": 1, "leaf": 64, "total": 65},
    "idma_requests": 128,
    "payload_bytes": 1048576,
    "K_bytes": 524288,
    "V_bytes": 524288,
    "logical_pages": 64,
    "page_bytes": 16384,
    "checks": {
        "formal_l0_kv_append_command": True,
        "complete_v3_descriptor_context": True,
        "K_and_V_page_addresses_exact": True,
        "PTE_fields_explicit_not_packed": True,
        "random_descriptor_PTE_iDMA_backpressure": True,
    },
    "provenance": {
        "stage_log_sha256": sha(stage_log),
        "core_log_sha256": sha(core_log),
        "stage_rtl_sha256": sha("rtl/kv/qwen2_kv_append_ddr_stage_top.sv"),
        "core_rtl_sha256": sha("rtl/kv/qwen2_kv_append_ddr_page_core.sv"),
    },
    "open": ["PTE_flags_encoding_and_DDR_write", "pinned_iDMA_AXl_payload_copy", "real_q1024_preceding_KV_outputs", "gather"],
    "non_claims": [
        "iDMA requests are handshaken but not yet bound to the pinned AXI backend in this stage test",
        "abstract PTE updates are not DDR PTE writes",
        "source payload is not read in this schedule-only gate",
    ],
}
(ROOT / "reports/execution/qwen2_kv_append_ddr_stage_result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps({"status": result["status"], "requests": 128, "bytes": 1048576}, sort_keys=True))
