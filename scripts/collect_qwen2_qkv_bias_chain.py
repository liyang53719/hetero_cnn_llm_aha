#!/usr/bin/env python3
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = Path("work/results/qwen2_raw_qkv_chain/tb.log")
pattern = re.compile(
    r"QWEN2_QKV_BIAS_CHAIN_PASS commands=(\d+) descriptor_fetches=(\d+) "
    r"flat_idma=(\d+) axi_beats=(\d+) ddr_read_bytes=(\d+) "
    r"ddr_write_bytes=(\d+) l2_read_beats=(\d+) l2_write_beats=(\d+) "
    r"raw_values=(\d+) biased_values=(\d+) bf16_bit_exact=(\d+) "
    r"matrix_completions=(\d+) sfu_completions=(\d+) no_reference_injection=(\d+)"
)
match = pattern.search((ROOT / LOG).read_text())
expected = (7, 42, 98440, 98768, 6312960, 8192, 98784, 176, 3584, 2048, 5632, 3, 4, 1)
assert match and tuple(map(int, match.groups())) == expected

def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()

result = {
    "schema_version": 1,
    "status": "PASS_QKV_BIAS_CHAIN_NO_INJECTION",
    "evidence_class": "single_VCS_formal_descriptor_pinned_iDMA_SharedL2_RMS_Revision8B_B_Matrix_HardFloat_bias",
    "commands": ["l0.input_norm", "l0.q", "l0.q_bias", "l0.k", "l0.k_bias", "l0.v", "l0.v_bias"],
    "descriptor_fetches": 42,
    "flat_idma_requests": 98440,
    "axi_beats_each_direction": 98768,
    "ddr_read_bytes": 6312960,
    "ddr_write_bytes": 8192,
    "shared_l2_read_beats": 98784,
    "shared_l2_write_beats": 176,
    "raw_values": 3584,
    "biased_values": 2048,
    "bf16_bit_exact": 5632,
    "matrix_completions": 3,
    "sfu_completions": 4,
    "checks": {
        "single_vcs_run": True,
        "formal_descriptor_fetch": True,
        "projection_output_feeds_bias_src0": True,
        "bias_input_format_fp32_dtype7": True,
        "reference_injection_between_stages": False,
        "generated_rtl_hand_edits": False,
    },
    "provenance": {
        "log_sha256": sha(LOG),
        "testbench_sha256": sha("tb/tb_qwen2_raw_qkv_chain.sv"),
        "projection_top_sha256": sha("rtl/integration/qwen2_projection_pingpong_top.sv"),
        "bias_top_sha256": sha("rtl/integration/qwen2_bias_stage_top.sv"),
    },
    "open": ["Q_K_RoPE_in_same_chain", "first_nine_commands", "complete_layer", "seven_groups", "continuous_28_layers"],
    "non_claims": [
        "seven of the first nine formal operations execute in this run",
        "Q and K RoPE are not yet data-connected in this run",
        "only token0 numerical payload executes",
    ],
}
(ROOT / "reports/execution/qwen2_qkv_bias_chain_result.json").write_text(
    json.dumps(result, indent=2, sort_keys=True) + "\n"
)
print(json.dumps({"status": result["status"], "commands": 7, "bf16_bit_exact": 5632}, sort_keys=True))
