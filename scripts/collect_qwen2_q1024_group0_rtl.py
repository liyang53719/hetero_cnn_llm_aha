#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "work/results/qwen2_q1024_group0_rtl"
LAYER0 = ROOT / "reports/execution/qwen2_q1024_layer0_tail_rtl_result.json"
BACKEND = json.loads((ROOT / "reports/execution/qwen2_q1024_group0_backend_result.json").read_text())

records = []
for layer in range(1, 4):
    text = (BASE / f"layer{layer}/tb.log").read_text()
    for operation, ksteps in (("oproj", 1536), ("gate", 1536), ("up", 1536), ("down", 8960)):
        assert f"QWEN2_LAYER0_MATRIX_SAMPLE_PASS operation={operation} tiles=3 k={ksteps} values=1536 layer={layer}" in text
    marker = f"QWEN2_Q1024_LAYER0_TAIL_RTL_PASS matrix_steps=40704 matrix_values=6144 silu_lanes=8 silu_values=8192 silu_random_backpressure=1 matrix_out_ready=1 same_RTL=1 layer={layer}"
    assert marker in text
    vector_manifest = BASE / f"layer{layer}/vectors/manifest.json"
    manifest = json.loads(vector_manifest.read_text())
    assert manifest["layer"] == layer and manifest["matrix_steps"] == 40704
    records.append({
        "layer": layer,
        "matrix_steps": 40704,
        "matrix_bf16_bit_exact": 6144,
        "silu_lanes": 8,
        "silu_bit_exact": 8192,
        "log_sha256": hashlib.sha256((BASE / f"layer{layer}/tb.log").read_bytes()).hexdigest(),
        "vector_manifest_sha256": hashlib.sha256(vector_manifest.read_bytes()).hexdigest(),
    })

binary = ROOT / "work/results/qwen2_q1024_layer0_tail_rtl/obj/tb"
result = {
    "schema_version": 1,
    "status": "PASS_Q1024_GROUP0_LAYERS1TO3_TAIL_SAMPLED_REAL_RTL",
    "evidence_class": "continuous_backend_anchored_by_same_Revision8B_and_8lane_SiLU_binary",
    "layers": [1, 2, 3],
    "records": records,
    "aggregate": {
        "matrix_steps": 3 * 40704,
        "matrix_bf16_bit_exact": 3 * 6144,
        "silu_bit_exact": 3 * 8192,
    },
    "checks": {
        "same_binary_all_layers": True,
        "same_RTL_all_sequence_lengths": True,
        "first_middle_last_physical_tiles": True,
        "eight_physical_SiLU_lanes": True,
        "silu_random_backpressure": True,
        "generated_or_upstream_RTL_modified": False,
        "backend_hidden_injections_inside_group": BACKEND["continuity"]["reference_hidden_injections_inside_group"] == 0,
    },
    "provenance": {
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "layer0_tail_rtl_report_sha256": hashlib.sha256(LAYER0.read_bytes()).hexdigest(),
        "group0_backend_report_sha256": hashlib.sha256((ROOT / "reports/execution/qwen2_q1024_group0_backend_result.json").read_bytes()).hexdigest(),
        "testbench_sha256": hashlib.sha256((ROOT / "tb/tb_qwen2_q1024_layer0_tail_rtl.sv").read_bytes()).hexdigest(),
    },
    "open": ["layers1to3_attention_sampled_RTL", "all_tail_tiles_RTL", "groups1to6", "P3"],
    "non_claims": [
        "tail first-middle-last tiles are sampled rather than full payload RTL",
        "layers1-3 QK-softmax-PV sampled RTL anchors remain open",
        "this does not yet promote group0 to a formal full-device-payload PASS",
    ],
}
(ROOT / "reports/execution/qwen2_q1024_group0_rtl_result.json").write_text(
    json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps({"status": result["status"], **result["aggregate"]}, sort_keys=True))
