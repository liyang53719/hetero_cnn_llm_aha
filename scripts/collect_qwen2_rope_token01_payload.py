#!/usr/bin/env python3
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = Path("work/results/qwen2_rope_token01_payload/tb.log")
CHAIN = Path("work/results/qwen2_raw_qkv_chain/tb.log")
pattern = re.compile(r"QWEN2_ROPE_TOKEN01_PAYLOAD_PASS runs=(\d+) Q_pairs=(\d+) K_pairs=(\d+) coefficient_steps=(\d+) bf16_bit_exact=(\d+) theta=(\d+) split_half=(\d+) Q_K_state_independent=(\d+) random_backpressure=(\d+)")
match = pattern.search((ROOT / LOG).read_text())
assert match and tuple(map(int, match.groups())) == (4, 1536, 256, 128, 3584, 1000000, 1, 1, 1)
assert "QWEN2_FIRST9_CHAIN_PASS commands=9" in (ROOT / CHAIN).read_text()

def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()

result = {
    "schema_version": 1,
    "status": "PASS_ROPE_TOKEN0_TOKEN1_RECURRENCE",
    "evidence_class": "same_RTL_FP32_recurrence_and_split_half_payload",
    "runs": ["Q_position0", "Q_position1", "K_position0", "K_position1"],
    "Q_pairs": 1536,
    "K_pairs": 256,
    "coefficient_steps": 128,
    "bf16_bit_exact": 3584,
    "theta": 1000000,
    "fixed_state_bytes": 1024,
    "checks": {
        "Q_and_K_coefficient_state_independent": True,
        "nonzero_position_numerical": True,
        "split_half_layout": True,
        "random_backpressure": True,
        "token0_first9_compatibility_after_recurrence": True,
        "generated_base_coeff_RTL_reproducible": True,
    },
    "provenance": {
        "log_sha256": sha(LOG),
        "chain_log_sha256": sha(CHAIN),
        "payload_rtl_sha256": sha("rtl/integration/qwen2_shared_l2_rope_payload.sv"),
        "base_coeff_rtl_sha256": sha("rtl/sfu/qwen2_rope_base_coeff64.sv"),
        "base_coeff_generator_sha256": sha("scripts/generate_qwen2_rope_base_coeff_rtl.py"),
    },
    "open": ["token1_full_RMS_QKV_bias_RoPE_chain", "16_token_tile", "q1024_sequential_recurrence", "q1024_real_KV_source"],
    "non_claims": [
        "token1 RoPE uses accepted biased Q/K inputs rather than same-run token1 Matrix outputs",
        "positions beyond one are structurally supported by recurrence but not yet numerically gated",
        "this is not complete layer0 continuity",
    ],
}
(ROOT / "reports/execution/qwen2_rope_token01_payload_result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps({"status": result["status"], "bit_exact": 3584, "steps": 128}, sort_keys=True))
