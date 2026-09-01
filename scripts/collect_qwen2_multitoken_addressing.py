#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
plan_log = Path("work/results/qwen2_tile_dma_plan/tb.log")
chain_log = Path("work/results/qwen2_raw_qkv_chain/tb.log")
plan = (ROOT / plan_log).read_text()
chain = (ROOT / chain_log).read_text()
assert "QWEN2_TILE_DMA_PLAN_PASS requests=4" in plan
assert "token_index=1 address_offset=1" in plan
assert "QWEN2_FIRST9_CHAIN_PASS commands=9" in chain

def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()

result = {
    "schema_version": 1,
    "status": "PASS_MULTITOKEN_ADDRESSING_PRIMITIVE",
    "evidence_class": "token1_DMA_dynamic_plus_token0_full_chain_regression",
    "token1_dynamic": {
        "projection_hidden_offset_bytes": 3072,
        "projection_output_offset": "output_columns * 2",
        "random_backpressure": True,
    },
    "implemented_same_RTL_paths": [
        "RMS hidden token offset",
        "projection output token offset",
        "bias source and destination token offsets",
        "RoPE source and destination token offsets",
        "RoPE 16-position DDR beat and lane selection",
    ],
    "checks": {
        "token1_projection_DMA_addresses": True,
        "token0_first9_regression_after_change": True,
        "different_RTL_per_sequence_length": False,
    },
    "provenance": {
        "plan_log_sha256": sha(plan_log),
        "chain_log_sha256": sha(chain_log),
        "dma_plan_sha256": sha("rtl/integration/qwen2_tile_dma_plan.sv"),
        "rms_stage_sha256": sha("rtl/integration/qwen2_rms_stage_top.sv"),
        "bias_stage_sha256": sha("rtl/integration/qwen2_bias_stage_top.sv"),
        "rope_stage_sha256": sha("rtl/integration/qwen2_rope_stage_top.sv"),
    },
    "open": ["token1_numerical_replay", "nonzero_position_RoPE_coefficients", "16_token_tile_controller", "q1024_real_source_to_KV"],
    "non_claims": [
        "only projection token1 addresses are dynamically checked",
        "RMS bias and RoPE token1 numerical output is not yet checked",
        "token0 compatibility is not multi-token continuity",
    ],
}
(ROOT / "reports/execution/qwen2_multitoken_addressing_result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps({"status": result["status"], "token1_dynamic": True}, sort_keys=True))
