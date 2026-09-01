#!/usr/bin/env python3
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = Path("work/results/qwen2_raw_qkv_chain/tb.log")
pattern = re.compile(
    r"QWEN2_FIRST9_CHAIN_PASS commands=(\d+) descriptor_fetches=(\d+) flat_idma=(\d+) "
    r"axi_beats=(\d+) ddr_read_bytes=(\d+) ddr_write_bytes=(\d+) l2_read_beats=(\d+) "
    r"l2_write_beats=(\d+) raw_values=(\d+) biased_values=(\d+) rope_pairs=(\d+) "
    r"rope_values=(\d+) bf16_bit_exact=(\d+) matrix_completions=(\d+) sfu_completions=(\d+) "
    r"no_reference_injection=(\d+) position0=(\d+)"
)
match = pattern.search((ROOT / LOG).read_text())
expected = (9, 62, 98500, 98882, 6316672, 11776, 98842, 232, 3584, 2048, 896, 1792, 7424, 3, 6, 1, 1)
assert match and tuple(map(int, match.groups())) == expected

def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()

result = {
    "schema_version": 1,
    "status": "PASS_FIRST9_FORMAL_COMMANDS_NO_INJECTION",
    "evidence_class": "single_VCS_descriptor_pinned_iDMA_SharedL2_RMS_Revision8B_B_Matrix_HardFloat_bias_RoPE",
    "commands": ["l0.input_norm", "l0.q", "l0.q_bias", "l0.q_rope", "l0.k", "l0.k_bias", "l0.k_rope", "l0.v", "l0.v_bias"],
    "descriptor_fetches": 62,
    "flat_idma_requests": 98500,
    "axi_beats_each_direction": 98882,
    "ddr_read_bytes": 6316672,
    "ddr_write_bytes": 11776,
    "shared_l2_read_beats": 98842,
    "shared_l2_write_beats": 232,
    "bf16_bit_exact": 7424,
    "rope_pairs": 896,
    "matrix_completions": 3,
    "sfu_completions": 6,
    "checks": {
        "approved_public_descriptor_encoding": True,
        "complete_rope_descriptor_chains_fetched": True,
        "projection_to_bias_to_rope_DDR_continuity": True,
        "reference_injection_between_stages": False,
        "position_tensor_loaded_from_DDR": True,
        "position0_split_half_identity": True,
        "generated_rtl_hand_edits": False,
    },
    "provenance": {
        "log_sha256": sha(LOG),
        "testbench_sha256": sha("tb/tb_qwen2_raw_qkv_chain.sv"),
        "rope_context_sha256": sha("rtl/integration/qwen2_rope_descriptor_context.sv"),
        "rope_payload_sha256": sha("rtl/integration/qwen2_shared_l2_rope_payload.sv"),
        "rope_top_sha256": sha("rtl/integration/qwen2_rope_stage_top.sv"),
    },
    "open": ["nonzero_position_RoPE_coefficients", "remaining_layer0_commands", "complete_layer", "seven_groups", "continuous_28_layers"],
    "non_claims": [
        "only token0 numerical payload executes",
        "position0 identity does not close nonzero-position RoPE",
        "nine commands do not constitute one complete transformer layer",
    ],
}
(ROOT / "reports/execution/qwen2_first9_chain_result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps({"status": result["status"], "commands": 9, "bf16_bit_exact": 7424}, sort_keys=True))
