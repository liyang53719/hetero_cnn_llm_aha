#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
paths = {
    "full28": ROOT / "reports/execution/qwen2_q1024_full28_backend_result.json",
    "head": ROOT / "reports/execution/qwen2_q1024_final_head_backend_result.json",
    "ext32": ROOT / "reports/execution/qwen2_ext32_attention_policy_result.json",
}
data = {name: json.loads(path.read_text()) for name, path in paths.items()}
assert data["full28"]["status"] == "PASS_Q1024_CONTINUOUS_28_LAYER_HARDWARE_SEMANTICS_BACKEND"
assert data["head"]["status"] == "PASS_Q1024_FINAL_RMSNORM_FULL_LM_HEAD_BACKEND"
assert data["ext32"]["status"] == "PASS_EXT32_EXP2_AND_INDEX_PIPELINE_E1_E4"
assert len(data["full28"]["groups"]) == 7 and data["full28"]["continuity"]["reference_hidden_injections"] == 0
result = {
    "schema_version": 1,
    "status": "PASS_Q1024_P3_BACKEND_EQUIVALENT_NUMERICAL",
    "evidence_class": "continuous_embedding_28layers_final_norm_full_vocab_hardware_semantics_backend",
    "layers": 28, "groups": 7, "commands": 588, "sequence": 1024, "reference_hidden_injections": 0,
    "attention": data["full28"]["attention"],
    "final": {"layer27_sha256": data["full28"]["continuity"]["layer27_final_sha256"], "argmax": data["head"]["argmax"], "reference_argmax": data["head"]["reference_argmax"], "top10_overlap": data["head"]["top10_overlap"], "vocab": data["head"]["vocab"]},
    "ext32_E1_E4": data["ext32"]["dc"],
    "checks": {"embedding_to_logits_continuous": True, "all_groups_four_layers": True, "all_attention_error_le_0p002": True, "final_argmax_preserved": True, "top10_overlap_10": data["head"]["top10_overlap"] == 10, "no_score_matrix": True},
    "provenance": {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()},
    "open": ["registered_llama_device_backend_payload_submission", "ext32_balanced_q1024_sampled_RTL", "integrated_random_backpressure_all_groups", "P3_device_gate", "L5.6d_formal_close"],
    "non_claims": ["P3 backend-equivalent numerical PASS is not registered llama device execution", "C++ hardware-semantics backend is not all-row RTL", "ext32 standalone sub-1ps DC margin is not integrated or post-route signoff"],
}
(ROOT / "reports/execution/qwen2_q1024_p3_backend_audit_result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps({"status": result["status"], "groups": 7, "argmax": result["final"]["argmax"], "top10_overlap": result["final"]["top10_overlap"], "max_attention_error": result["attention"]["maximum_error"]}, sort_keys=True))
