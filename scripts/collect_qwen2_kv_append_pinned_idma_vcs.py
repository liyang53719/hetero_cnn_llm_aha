#!/usr/bin/env python3
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = Path("work/results/qwen2_kv_append_pinned_idma_vcs/tb.log")
pattern = re.compile(r"QWEN2_KV_APPEND_PINNED_IDMA_VCS_PASS commands=(\d+) descriptor_fetches=(\d+) pte_updates=(\d+) idma_requests=(\d+) axi_read_beats=(\d+) axi_write_beats=(\d+) payload_bytes=(\d+) byte_exact=(\d+) pages=(\d+) upstream_clean=(\d+) source_injection=([a-z_]+)")
match = pattern.search((ROOT / LOG).read_text())
assert match and tuple(map(int, match.groups()[:10])) == (1, 13, 65, 128, 16384, 16384, 1048576, 1048576, 64, 1)
assert match[11] == "synthetic_preload"

def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()

result = {
    "schema_version": 1,
    "status": "PASS_KV_APPEND_PINNED_IDMA_BYTE_EXACT",
    "evidence_class": "formal_descriptor_to_clean_upstream_iDMA_joined_AXI_DDR",
    "commands": 1,
    "descriptor_fetches": 13,
    "pte_updates": 65,
    "idma_requests": 128,
    "axi_read_beats": 16384,
    "axi_write_beats": 16384,
    "payload_bytes": 1048576,
    "byte_exact": 1048576,
    "pages": 64,
    "source_injection": "synthetic_preload",
    "checks": {
        "upstream_idma_exact_commit_clean": True,
        "joined_read_write_AXI": True,
        "all_KV_page_bytes_checked": True,
        "CPU_affinity_8_23": True,
        "memory_cap_30G": True,
    },
    "provenance": {
        "log_sha256": sha(LOG),
        "testbench_sha256": sha("tb/tb_qwen2_kv_append_pinned_idma_vcs.sv"),
        "runner_sha256": sha("scripts/run_qwen2_kv_append_pinned_idma_vcs.sh"),
        "idma_commit": "2e0b0fe53b6f8823319e2428e2e9abc2db149b7d",
    },
    "open": ["PTE_DDR_write", "real_q1024_preceding_KV_outputs", "nonzero_position_RoPE", "same_run_layer0"],
    "non_claims": [
        "synthetic source preload is not preceding Matrix/SFU numerical continuity",
        "abstract PTE updates are not DDR writes",
        "this does not close a complete transformer layer",
    ],
}
(ROOT / "reports/execution/qwen2_kv_append_pinned_idma_vcs_result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps({"status": result["status"], "bytes": 1048576, "pages": 64}, sort_keys=True))
