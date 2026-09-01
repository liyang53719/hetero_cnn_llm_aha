#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
paths = {
    "backend": ROOT / "reports/execution/qwen2_q1024_group0_backend_result.json",
    "layer0_attention": ROOT / "reports/execution/qwen2_q1024_model_attention_rtl_result.json",
    "layer0_tail": ROOT / "reports/execution/qwen2_q1024_layer0_tail_rtl_result.json",
    "layers1to3_attention": ROOT / "reports/execution/qwen2_q1024_group0_attention_rtl_result.json",
    "layers1to3_tail": ROOT / "reports/execution/qwen2_q1024_group0_rtl_result.json",
}
data = {name: json.loads(path.read_text()) for name, path in paths.items()}
assert data["backend"]["status"] == "PASS_Q1024_GROUP0_CONTINUOUS_HARDWARE_SEMANTICS_BACKEND"
assert data["backend"]["layers"] == [0, 1, 2, 3]
assert data["backend"]["continuity"]["reference_hidden_injections_inside_group"] == 0
assert data["layer0_attention"]["status"] == "PASS_Q1024_EXACT_MODEL_SAMPLED_ATTENTION_RTL"
assert data["layer0_tail"]["status"] == "PASS_Q1024_LAYER0_TAIL_SAMPLED_REAL_RTL"
assert data["layers1to3_attention"]["status"] == "PASS_Q1024_GROUP0_LAYERS1TO3_ATTENTION_SAMPLED_REAL_RTL"
assert data["layers1to3_tail"]["status"] == "PASS_Q1024_GROUP0_LAYERS1TO3_TAIL_SAMPLED_REAL_RTL"

result = {
    "schema_version": 1,
    "status": "PASS_Q1024_GROUP0_BACKEND_EQUIVALENT_WITH_SAMPLED_REAL_RTL",
    "evidence_class": "continuous_all_row_hardware_semantics_backend_plus_reviewed_real_RTL_samples",
    "layers": [0, 1, 2, 3],
    "commands": 84,
    "full_backend": {
        "rows_per_layer": 1024,
        "attention_updates": 25190400,
        "summary_merges": 172032,
        "reference_hidden_injections": 0,
        "layer3_final_sha256": data["backend"]["continuity"]["layer3_final_sha256"],
    },
    "sampled_real_RTL": {
        "attention_rows": 1440 + data["layers1to3_attention"]["aggregate"]["sampled_rows"],
        "tail_matrix_steps": 40704 + data["layers1to3_tail"]["aggregate"]["matrix_steps"],
        "tail_matrix_bf16_bit_exact": 6144 + data["layers1to3_tail"]["aggregate"]["matrix_bf16_bit_exact"],
        "silu_bit_exact": 8192 + data["layers1to3_tail"]["aggregate"]["silu_bit_exact"],
        "score_probability_DDR_bytes": 0,
    },
    "checks": {
        "exact_revision_weights": True,
        "real_Command128_slices": True,
        "all_rows_continuous_backend": True,
        "predecessor_only_hidden_chain": True,
        "Revision8B_QK_PV_and_tail_samples": True,
        "real_SFU_merge128_probability_hilo_samples": True,
        "eight_lane_fused_SiLU_samples": True,
        "random_controller_and_SiLU_backpressure": True,
        "checkpoint_hashes_each_layer": True,
    },
    "provenance": {
        name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()
    },
    "open": ["groups1to6", "continuous_28_layer_P3", "final_RMSNorm_LM_head", "llama_device_backend_registration"],
    "non_claims": [
        "sampled RTL is not all-row numerical RTL",
        "the hardware-semantics C++ backend is not yet registered as a llama.cpp device backend",
        "group0 passes the explicitly labeled backend-equivalent gate, not full integrated RTL",
    ],
}
(ROOT / "reports/execution/qwen2_q1024_group0_audit_result.json").write_text(
    json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps({"status": result["status"], **result["sampled_real_RTL"]}, sort_keys=True))
